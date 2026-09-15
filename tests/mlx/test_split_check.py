"""离线 CPU 分词、原行映射、旧配方对照及环境失败边界。"""

import contextlib
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text import recipe, split_check

MODEL = ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct"


def conversation(*pairs):
    return {"messages": [{"role": role, "content": content} for role, content in pairs]}


def request(dataset, model=MODEL, length=512):
    return {"schema_version": 1, "dataset_path": str(dataset), "dataset_sha256": split_check.digest_file(dataset),
            "model_path": str(model), "model_manifest_digest": "1" * 64, "max_seq_length": length}


@pytest.fixture(scope="module")
def tokenizer(tmp_path_factory):
    staging = tmp_path_factory.mktemp("tokenizer")
    for name, path in split_check._tokenizer_files(MODEL).items():
        (staging / name).write_bytes(path.read_bytes())
    return split_check._load_tokenizer(staging)


@pytest.fixture(scope="module")
def old_wrapper(tokenizer):
    # 直接执行已安装的原包装器模块，避免导入 mlx 包及创建 Metal 设备。
    package = importlib.metadata.distribution("mlx-lm")
    path = package.locate_file("mlx_lm/tokenizer_utils.py")
    spec = importlib.util.spec_from_file_location("split_test_original_mlx_tokenizer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TokenizerWrapper(tokenizer.tokenizer)


def write_rows(path, rows):
    path.write_bytes(b"".join((split_check.canonical(row) + b"\n") if row is not None else b" \t\n" for row in rows))


def read_checks(output):
    return [json.loads(line) for line in (output / "sample-checks.jsonl").read_text().splitlines()]


def test_real_multiturn_and_padding_match_existing_wrapper(tokenizer, old_wrapper):
    rows = [conversation(("system", "使用中文"), ("user", "项目叫星河"), ("assistant", "已记住。"),
                         ("user", "叫什么？"), ("assistant", "星河。")),
            conversation(("user", "嗨"), ("assistant", "好")),
            conversation(("user", "请说一句话"), ("assistant", "这是一个更长的回答。"))]
    samples = []
    for row in rows:
        new = recipe.tokenize_sample(tokenizer, row, 512)
        assert new == recipe.tokenize_sample(old_wrapper, row, 512)
        assert new["supervised_tokens"] == sum(label != -100 for label in new["labels"][1:]) > 0
        samples.append(new)
    assert [tokenizer.decode(samples[0]["input_ids"][span["start"]:span["end"]])
            for span in samples[0]["assistant_spans"]] == ["已记住。<|im_end|>", "星河。<|im_end|>"]
    batch = recipe.collate_samples(samples[1:], pad_id=151645)
    end = len(samples[1]["input_ids"])
    assert all(label == -100 for label in batch["labels"][0][end:])
    assert all(token == 151645 for token in batch["input_ids"][0][end:])
    assert 151645 in batch["labels"][0][:end]


@pytest.mark.parametrize("row,code,length", [
    ({"messages": []}, "NO_SUPERVISION", 512),
    (conversation(("system", "系统")), "NO_SUPERVISION", 512),
    (conversation(("user", "问题")), "NO_SUPERVISION", 512),
    (conversation(("assistant", "答案")), "INVALID_ROLES", 512),
    (conversation(("user", "问题"), ("assistant", "")), "EMPTY_CONTENT", 512),
    (conversation(("user", "问题<|im_end|>"), ("assistant", "答案")), "RESERVED_TOKEN", 512),
    ({"messages": [{"role": "user", "content": [{"type": "image", "url": "a.png"}]}]}, "MEDIA_OR_TOOLS_UNSUPPORTED", 512),
    ({"messages": [{"role": "assistant", "content": "答案", "tool_calls": []}]}, "MEDIA_OR_TOOLS_UNSUPPORTED", 512),
    (conversation(("user", "问题"), ("assistant", "完整答案" * 100)), "SEQUENCE_TOO_LONG", 32),
])
def test_real_exclusions_match_existing_recipe(tokenizer, old_wrapper, row, code, length):
    for candidate in (tokenizer, old_wrapper):
        with pytest.raises(recipe.RecipeError) as caught:
            recipe.tokenize_sample(candidate, row, length)
        assert caught.value.code == code


def test_complete_check_keeps_original_lines_source_metadata_and_identity(tmp_path):
    dataset = tmp_path / "source.jsonl"
    valid = conversation(("user", "问题"), ("assistant", "答案"))
    rows = [{"source_id": "文档甲", **valid}, None,
            {"source_id": "<|im_end|>", **valid},
            {"source_id": "文档乙", **conversation(("user", "问题"), ("assistant", ""))},
            {"source_id": "文档丙", "messages": []}]
    write_rows(dataset, rows)
    original = dataset.read_bytes()
    outputs = [tmp_path / "first", tmp_path / "second"]
    results = [split_check.check(request(dataset), output) for output in outputs]
    assert results[0] == results[1]
    result = results[0]
    assert result["ok"] is True
    assert (result["input_samples"], result["accepted_samples"], result["excluded_samples"], result["ignored_lines"]) == (4, 2, 2, 1)
    assert result["supervised_tokens"] == result["shifted_supervised_tokens"] > 0
    checks = read_checks(outputs[0])
    assert [item["line"] for item in checks] == [1, 2, 3, 4, 5]
    assert [item["status"] for item in checks] == ["accepted", "ignored", "accepted", "excluded", "excluded"]
    assert checks[0]["messages_sha256"] == checks[2]["messages_sha256"]
    assert checks[0]["line_sha256"] != checks[2]["line_sha256"]
    assert checks[2]["source_id"] == "<|im_end|>"
    assert checks[3]["code"] == "EMPTY_CONTENT" and checks[4]["code"] == "NO_SUPERVISION"
    assert checks[3]["input_tokens"] is None
    assert [item["line_sha256"] for item in checks] == [hashlib.sha256(line).hexdigest() for line in original.splitlines(keepends=True)]
    report = json.loads((outputs[0] / "check-report.json").read_text())
    assert [item["line"] for item in report["token_labels_examples"]] == [1, 3]
    assert report["token_labels_examples"][0]["labels"] == report["token_labels_examples"][1]["labels"]
    identity = report["check_identity"]
    assert hashlib.sha256(split_check.canonical(identity)).hexdigest() == result["check_identity_digest"]
    assert identity["recipe"]["recipe_implementation_sha256"] == split_check.RECIPE_SHA256
    assert identity["recipe"]["tokenizer_files"] == split_check.TOKENIZER_FILES
    assert identity["runtime"] == split_check.RUNTIME
    assert str(tmp_path) not in json.dumps(report)
    for name, manifest in result["artifacts"].items():
        assert set(manifest) == {"sha256", "size_bytes"}
        assert split_check.digest_file(outputs[0] / name) == manifest["sha256"]
        assert (outputs[0] / name).stat().st_size == manifest["size_bytes"]
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    assert dataset.read_bytes() == original
    assert sorted(path.name for path in outputs[0].iterdir()) == ["check-report.json", "sample-checks.jsonl"]


def test_all_excluded_is_complete_not_environment_failure(tmp_path):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "空对话", "messages": []}, None])
    result = split_check.check(request(dataset), tmp_path / "out")
    assert result["ok"] is True and result["accepted_samples"] == 0
    assert result["excluded_samples"] == 1 and result["supervised_tokens"] == 0


@pytest.mark.parametrize("raw", [
    b'{"messages":[]}', b'{"source_id":"x","messages":[],"other":true}',
    b'{"source_id":"","messages":[]}', b'{"source_id":" x","messages":[]}',
    b'{"source_id":42,"messages":[]}', b'{"source_id":true,"messages":[]}',
    b'{"source_id":"x","source_id":"y","messages":[]}',
    b'{"source_id":"x","messages":[{"role":"user","role":"assistant","content":"x"}]}',
    b'{"source_id":"x","messages":NaN}', b'not json', b'\xff',
    ('{"source_id":"' + "中" * 86 + '","messages":[]}').encode(),
])
def test_invalid_source_is_entire_input_failure(raw):
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check._source_row(raw, 7)
    assert (caught.value.scope, caught.value.code, caught.value.line) == ("input", "INVALID_SOURCE_DATASET", 7)


@pytest.mark.parametrize("code", ["TEMPLATE_UNSUPPORTED", "SPECIAL_TOKEN_MISMATCH", "ROLE_MASK_UNRELIABLE", "UNKNOWN_RECIPE_ERROR"])
def test_environment_recipe_failure_does_not_become_exclusion(tmp_path, monkeypatch, code):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "甲", "messages": []}])
    def fail(*_args):
        raise recipe.RecipeError(code, "包含私有正文的底层错误")
    monkeypatch.setattr(recipe, "tokenize_sample", fail)
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check._check_rows(dataset, object(), 512, io.BytesIO(), lambda: None)
    assert caught.value.scope == "environment" and caught.value.code == code
    assert "私有正文" not in str(caught.value)


def test_zero_shifted_supervision_is_excluded(tmp_path, monkeypatch):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "甲", "messages": []}])
    monkeypatch.setattr(recipe, "tokenize_sample", lambda *_: {"input_ids": [7], "labels": [7], "supervised_tokens": 1, "assistant_spans": []})
    stream = io.BytesIO()
    counts, exclusions, _, _ = split_check._check_rows(dataset, object(), 512, stream, lambda: None)
    assert counts["accepted_samples"] == 0 and exclusions == {"NO_SUPERVISION": 1}


def test_runtime_and_recipe_versions_fail_closed(monkeypatch):
    original = split_check.importlib.metadata.version
    monkeypatch.setattr(split_check.importlib.metadata, "version", lambda name: "0.0.0" if name == "tokenizers" else original(name))
    with pytest.raises(split_check.SplitCheckError, match="版本") as caught:
        split_check._runtime()
    assert caught.value.code == "TOKENIZER_VERSION_UNSUPPORTED"
    monkeypatch.setattr(split_check.importlib.metadata, "version", original)
    monkeypatch.setattr(split_check, "RECIPE_SHA256", "0" * 64)
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check._runtime()
    assert caught.value.code == "RECIPE_VERSION_UNSUPPORTED"


def test_unknown_tokenizer_and_template_fail_before_loading(tmp_path):
    for name, source in split_check._tokenizer_files(MODEL).items():
        (tmp_path / name).write_bytes(source.read_bytes())
    (tmp_path / "chat_template.jinja").write_text("changed")
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check._tokenizer_files(tmp_path)
    assert caught.value.code == "TEMPLATE_UNSUPPORTED"
    (tmp_path / "chat_template.jinja").unlink()
    with (tmp_path / "tokenizer_config.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check._tokenizer_files(tmp_path)
    assert caught.value.code == "TOKENIZER_IDENTITY_UNSUPPORTED"


def test_source_changed_and_output_reuse_are_blocked(tmp_path):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "甲", "messages": []}])
    snapshot = request(dataset)
    dataset.write_bytes(dataset.read_bytes() + b"\n")
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check.check(snapshot, tmp_path / "out")
    assert caught.value.code == "DATASET_CHANGED" and not (tmp_path / "out").exists()
    output = tmp_path / "occupied"
    output.mkdir()
    (output / "keep").write_text("保持")
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check.check(request(dataset), output)
    assert caught.value.code == "OUTPUT_NOT_EMPTY"
    assert (output / "keep").read_text() == "保持"


def test_source_mutation_during_check_has_no_published_report(tmp_path, tokenizer, monkeypatch):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "甲", **conversation(("user", "嗨"), ("assistant", "好"))}])
    snapshot = request(dataset)
    original = recipe.tokenize_sample
    def mutate(*args):
        value = original(*args)
        dataset.write_bytes(b'changed\n')
        return value
    monkeypatch.setattr(recipe, "tokenize_sample", mutate)
    monkeypatch.setattr(split_check, "_load_tokenizer", lambda _: tokenizer)
    output = tmp_path / "out"
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check.check(snapshot, output)
    assert caught.value.code == "DATASET_CHANGED"
    assert not (output / "check-report.json").exists()


def test_cancellation_does_not_publish_evidence(tmp_path):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "甲", "messages": []}])
    def cancel():
        raise InterruptedError("用户取消")
    with pytest.raises(InterruptedError):
        split_check.check(request(dataset), tmp_path / "out", check_cancel=cancel)
    assert not (tmp_path / "out/check-report.json").exists()


def test_controller_mismatch_blocks_before_output(tmp_path, monkeypatch, capsys):
    snapshot = tmp_path / "request.json"
    snapshot.write_text("{}")
    output = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["dataset-check", "--snapshot", str(snapshot), "--output-dir", str(output), "--controller-pid", "1"])
    assert split_check.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["blocking"][0]["code"] == "CHECK_CANCELLED"
    assert not output.exists()


def test_controller_exit_stops_real_child_during_blocking_wait(tmp_path):
    ready, done = tmp_path / "ready", tmp_path / "incorrectly-finished"
    child_script = '''import sys, time
from pathlib import Path
from adapters.mlx_text.split_check import controller_guard
with controller_guard(int(sys.argv[1])):
    Path(sys.argv[2]).write_text(str(__import__('os').getpid()))
    time.sleep(12)
    Path(sys.argv[3]).write_text('控制器退出后仍继续写入')
'''
    parent_script = '''import subprocess, sys, os
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', sys.argv[1], str(os.getpid()), sys.argv[2], sys.argv[3]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(child.pid, flush=True)
sys.stdin.readline()
'''
    parent = subprocess.Popen([sys.executable, "-c", parent_script, child_script, str(ready), str(done)], cwd=ROOT,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child_pid = int(parent.stdout.readline())
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        parent.communicate("exit\n", timeout=5)
        assert parent.returncode == 0
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = subprocess.run(["/bin/ps", "-p", str(child_pid), "-o", "stat="], capture_output=True, text=True)
            if state.returncode != 0 or state.stdout.strip().startswith("Z"):
                break
            time.sleep(0.05)
        else:
            pytest.fail("父控制器退出后 CPU 子进程未及时停止")
        assert not done.exists()
    finally:
        if parent.poll() is None:
            parent.communicate("exit\n", timeout=5)


def test_output_created_during_check_is_never_overwritten(tmp_path, tokenizer, monkeypatch):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "甲", "messages": []}])
    output = tmp_path / "out"
    def load(_path):
        (output / "check-report.json").write_text("不能覆盖")
        return tokenizer
    monkeypatch.setattr(split_check, "_load_tokenizer", load)
    with pytest.raises(FileExistsError):
        split_check.check(request(dataset), output)
    assert (output / "check-report.json").read_text() == "不能覆盖"


@pytest.mark.parametrize("field,value", [("max_seq_length", True), ("max_seq_length", 0), ("max_seq_length", 2.5),
                                          ("schema_version", True), ("dataset_sha256", "bad")])
def test_request_strict_numbers_and_digests(tmp_path, field, value):
    dataset = tmp_path / "source.jsonl"
    dataset.write_bytes(b"")
    snapshot = {**request(dataset), field: value}
    with pytest.raises(split_check.SplitCheckError) as caught:
        split_check.check(snapshot, tmp_path / "out")
    assert caught.value.scope == "input" and caught.value.code == "INVALID_CHECK_REQUEST"


def test_cli_hides_underlying_failure_details(tmp_path, monkeypatch, capsys):
    path = tmp_path / "request.json"
    path.write_text("{}")
    monkeypatch.setattr(sys, "argv", ["dataset-check", "--snapshot", str(path), "--output-dir", str(tmp_path / "out")])
    def fail(*_args, **_kwargs):
        raise RuntimeError("/private/user/source token=secret 正文")
    monkeypatch.setattr(split_check, "check", fail)
    assert split_check.main() == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["failure_scope"] == "environment"
    assert "secret" not in captured.out + captured.err and "/private/user" not in captured.out + captured.err


def test_real_fixed_entry_under_weight_network_and_gpu_import_guards(tmp_path):
    dataset = tmp_path / "source.jsonl"
    write_rows(dataset, [{"source_id": "只作来源的<|im_end|>", **conversation(("user", "嗨"), ("assistant", "好"))}])
    snapshot = tmp_path / "request.json"
    snapshot.write_bytes(split_check.canonical(request(dataset)))
    output = tmp_path / "out"
    audit = tmp_path / "audit.json"
    script = r'''
import hashlib, json, os, runpy, sys
from pathlib import Path
root, model, request, output, audit = map(Path, sys.argv[1:])
allowed = {"tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja"}
seen, blocked = set(), []
def guard(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        if path.suffix in {".safetensors", ".bin", ".pt", ".pth", ".npz", ".gguf"} or (path.is_relative_to(model) and path.name not in allowed):
            blocked.append(path.name)
            raise AssertionError("检查禁止读取模型权重和其他模型文件")
        if path.is_relative_to(model): seen.add(path.name)
    if event in {"socket.connect", "socket.getaddrinfo"}:
        blocked.append("network")
        raise AssertionError("检查禁止网络连接")
    if event == "import" and args[0].split(".")[0] in {"mlx", "mlx_lm", "torch", "tensorflow", "jax"}:
        blocked.append("gpu_import:" + args[0])
        raise AssertionError("CPU 检查禁止导入模型运行时")
sys.addaudithook(guard)
sys.path.insert(0, str(root))
sys.argv = ["ailab-mlx", "--mode", "dataset-check", "--snapshot", str(request), "--output-dir", str(output)]
try:
    runpy.run_path(str(root / "scripts/desktop/mlx_entry.py"), run_name="__main__")
except SystemExit as exc:
    code = exc.code
audit.write_text(json.dumps({"exit_code":code,"model_files_opened":sorted(seen),"blocked_attempts":blocked,
                            "model_modules_loaded":[x for x in sys.modules if x.split(".")[0] in {"mlx","mlx_lm","torch","tensorflow","jax"}]}))
raise SystemExit(code)
'''
    result = subprocess.run([sys.executable, "-c", script, str(ROOT), str(MODEL), str(snapshot), str(output), str(audit)],
                            capture_output=True, text=True, timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 0, result.stderr + result.stdout
    assert len(result.stdout.splitlines()) == 1 and json.loads(result.stdout)["accepted_samples"] == 1
    observed = json.loads(audit.read_text())
    assert observed["model_files_opened"] == sorted(split_check.TOKENIZER_FILES)
    assert observed["blocked_attempts"] == observed["model_modules_loaded"] == []
