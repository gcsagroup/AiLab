"""来源组划分前的离线 CPU 检查，只复用既有助手监督配方。"""

import argparse
from collections import Counter
import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import sys
import tempfile
import threading

from adapters.mlx_text import recipe

VERSION = "source-dataset-tokenizer-check-v1"
RUNTIME = {"python": "3.13.9", "transformers": "5.17.0", "tokenizers": "0.23.2", "Jinja2": "3.1.6"}
RECIPE_SHA256 = "7c856459e1fc23c6c934ef9f8280128a892ea5d639e8f0b6485c84ba411b11d9"
TOKENIZER_FILES = {
    "merges.txt": "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3",
    "tokenizer.json": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "tokenizer_config.json": "5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583",
    "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
}
SAMPLE_EXCLUSIONS = {"INVALID_SAMPLE", "NO_SUPERVISION", "MEDIA_OR_TOOLS_UNSUPPORTED",
                     "EMPTY_CONTENT", "RESERVED_TOKEN", "INVALID_ROLES", "SEQUENCE_TOO_LONG"}


class SplitCheckError(ValueError):
    def __init__(self, code, message, scope="environment", line=None):
        super().__init__(message)
        self.code, self.scope, self.line = code, scope, line


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("重复 JSON 键")
        value[key] = item
    return value


def strict_json(raw):
    def invalid_constant(_value):
        raise ValueError("非有限 JSON 数值")
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid_constant)


def _path(value, scope, directory=False, may_create=False):
    if not isinstance(value, (str, Path)) or not Path(value).is_absolute():
        raise SplitCheckError("INVALID_PATH", "检查输入必须使用本地绝对路径", scope)
    path = Path(value)
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise SplitCheckError("SYMLINK_UNSUPPORTED", "检查路径不能经过符号链接", scope)
    if not ((directory and path.is_dir()) or (not directory and path.is_file()) or
            (may_create and not path.exists() and path.parent.is_dir())):
        raise SplitCheckError("INPUT_UNAVAILABLE", "检查所需文件或目录不可用", scope)
    return path


def _request(snapshot):
    fields = {"schema_version", "dataset_path", "dataset_sha256", "model_path", "model_manifest_digest", "max_seq_length"}
    if not isinstance(snapshot, dict) or set(snapshot) != fields or type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1:
        raise SplitCheckError("INVALID_CHECK_REQUEST", "分词检查请求字段或版本无效", "input")
    if type(snapshot["max_seq_length"]) is not int or snapshot["max_seq_length"] <= 0:
        raise SplitCheckError("INVALID_CHECK_REQUEST", "序列长度必须是严格正整数", "input")
    for name in ("dataset_sha256", "model_manifest_digest"):
        if not isinstance(snapshot[name], str) or re.fullmatch("[0-9a-f]{64}", snapshot[name]) is None:
            raise SplitCheckError("INVALID_CHECK_REQUEST", "检查请求缺少有效内容摘要", "input")
    return _path(snapshot["dataset_path"], "input"), _path(snapshot["model_path"], "environment", directory=True)


def _runtime():
    try:
        versions = {"python": platform.python_version(),
                    **{name: importlib.metadata.version(name) for name in RUNTIME if name != "python"}}
    except importlib.metadata.PackageNotFoundError:
        raise SplitCheckError("TOKENIZER_ENVIRONMENT_UNAVAILABLE", "缺少已验证的 CPU 分词依赖") from None
    if versions != RUNTIME:
        raise SplitCheckError("TOKENIZER_VERSION_UNSUPPORTED", "当前 Python 或分词依赖版本未通过固定配方验证")
    if digest_file(Path(recipe.__file__)) != RECIPE_SHA256 or recipe.RECIPE_ID != "qwen25-assistant-only-v1":
        raise SplitCheckError("RECIPE_VERSION_UNSUPPORTED", "监督配方源码与已验证版本不同")
    return versions


def _tokenizer_files(model):
    files = {}
    for name in TOKENIZER_FILES:
        path = _path(model / name, "environment")
        if digest_file(path) != TOKENIZER_FILES[name]:
            raise SplitCheckError("TOKENIZER_IDENTITY_UNSUPPORTED", "分词文件与已验证的 Qwen tokenizer 不同")
        files[name] = path
    template = model / "chat_template.jinja"
    if template.exists() or template.is_symlink():
        path = _path(template, "environment")
        if digest_file(path) != recipe.TEMPLATE_SHA256:
            raise SplitCheckError("TEMPLATE_UNSUPPORTED", "聊天模板未通过当前监督配方验证")
        files[template.name] = template
    return files


class RecipeTokenizer:
    """与现有 MLX 包装器一致地取词元列表；不增加角色或标签算法。"""
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def __getattr__(self, name):
        return getattr(self.tokenizer, name)

    def apply_chat_template(self, *args, **kwargs):
        return self.tokenizer.apply_chat_template(*args, **kwargs, return_dict=False, enable_thinking=False)


def _load_tokenizer(staging):
    # 不将模型目录交给依赖；隔离目录只含已经核验的 tokenizer 文件。
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false",
                      USE_TORCH="0", USE_TF="0", USE_FLAX="0")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(staging), local_files_only=True, trust_remote_code=False, use_fast=True)
    if not isinstance(tokenizer.chat_template, str) or hashlib.sha256(tokenizer.chat_template.encode()).hexdigest() != recipe.TEMPLATE_SHA256:
        raise SplitCheckError("TEMPLATE_UNSUPPORTED", "聊天模板未通过当前监督配方验证")
    if not tokenizer.is_fast or tokenizer.convert_tokens_to_ids("<|im_end|>") != 151645:
        raise SplitCheckError("SPECIAL_TOKEN_MISMATCH", "tokenizer 类型或结束标记与已验证配方不同")
    return RecipeTokenizer(tokenizer)


def _source_row(raw, line):
    try:
        value = strict_json(raw.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != {"source_id", "messages"}:
            raise ValueError("来源字段无效")
        source = value["source_id"]
        if not isinstance(source, str) or not source or source != source.strip() or len(source.encode("utf-8")) > 256:
            raise ValueError("来源标识无效")
        # 仅构造 messages 视图；来源字段绝不参与监督计算。
        sample = {"messages": value["messages"]}
        messages_digest = hashlib.sha256(canonical(sample)).hexdigest()
    except (ValueError, UnicodeError, TypeError):
        raise SplitCheckError("INVALID_SOURCE_DATASET", "原件须逐行提供唯一的 source_id 与 messages；请修正后重新导入", "input", line) from None
    return source, sample, messages_digest


def _check_rows(dataset, tokenizer, max_seq_length, stream, check_cancel):
    counts = Counter(input_samples=0, accepted_samples=0, excluded_samples=0, ignored_lines=0,
                     supervised_tokens=0, shifted_supervised_tokens=0)
    exclusions, examples, source_digest = Counter(), [], hashlib.sha256()
    with dataset.open("rb") as original:
        for line_no, raw in enumerate(original, 1):
            check_cancel()
            source_digest.update(raw)
            row = {"line": line_no, "line_sha256": hashlib.sha256(raw).hexdigest(), "messages_sha256": None,
                   "source_id": None, "status": "ignored", "code": "BLANK_LINE", "input_tokens": 0,
                   "supervised_tokens": 0, "shifted_supervised_tokens": 0}
            if not raw.strip():
                counts["ignored_lines"] += 1
            else:
                source, sample, messages_digest = _source_row(raw, line_no)
                counts["input_samples"] += 1
                row.update(source_id=source, messages_sha256=messages_digest, input_tokens=None)
                try:
                    checked = recipe.tokenize_sample(tokenizer, sample, max_seq_length)
                    supervised = sum(value != -100 for value in checked["labels"])
                    shifted = sum(value != -100 for value in checked["labels"][1:])
                    if supervised != checked["supervised_tokens"] or len(checked["input_ids"]) != len(checked["labels"]):
                        raise SplitCheckError("SUPERVISION_CONTRACT_MISMATCH", "配方监督计数与实际标签不一致")
                    if not supervised or not shifted:
                        raise recipe.RecipeError("NO_SUPERVISION", "样本移位后没有有效监督")
                    row.update(status="accepted", code=None, input_tokens=len(checked["input_ids"]),
                               supervised_tokens=supervised, shifted_supervised_tokens=shifted)
                    counts.update(accepted_samples=1, supervised_tokens=supervised, shifted_supervised_tokens=shifted)
                    if len(examples) < 3:
                        examples.append({**checked, "line": line_no, "shifted_supervised_tokens": shifted})
                except recipe.RecipeError as exc:
                    if exc.code not in SAMPLE_EXCLUSIONS:
                        raise SplitCheckError(exc.code, "分词环境或角色掩码不符合固定配方，整次检查已停止", line=line_no) from None
                    row.update(status="excluded", code=exc.code)
                    counts["excluded_samples"] += 1
                    exclusions[exc.code] += 1
            stream.write(canonical(row) + b"\n")
    return dict(counts), dict(exclusions), examples, source_digest.hexdigest()


def check(snapshot, output_dir, check_cancel=lambda: None):
    """完整处理返回小摘要；全排除仍为完成，来源组门槛由控制端判断。"""
    check_cancel()
    dataset, model = _request(snapshot)
    versions = _runtime()
    if digest_file(dataset) != snapshot["dataset_sha256"]:
        raise SplitCheckError("DATASET_CHANGED", "原件摘要变化，请重新准备计划", "input")
    files = _tokenizer_files(model)
    output = _path(output_dir, "output", directory=True, may_create=True)
    if output.exists() and any(output.iterdir()):
        raise SplitCheckError("OUTPUT_NOT_EMPTY", "检查输出目录必须为空，不覆盖已有证据", "output")
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tokenizer-", dir=output) as temporary:
        staging = Path(temporary)
        for name, path in files.items():
            check_cancel()
            data = path.read_bytes()
            expected = TOKENIZER_FILES.get(name, recipe.TEMPLATE_SHA256)
            if hashlib.sha256(data).hexdigest() != expected:
                raise SplitCheckError("TOKENIZER_CHANGED", "分词文件在检查期间发生变化")
            (staging / name).write_bytes(data)
        with contextlib.redirect_stdout(sys.stderr):
            check_cancel()
            tokenizer = _load_tokenizer(staging)
            check_cancel()
            frozen_recipe, recipe_digest = recipe.build_recipe(staging, tokenizer, "train", snapshot["max_seq_length"])
        identity = {"checker_version": VERSION, "checker_implementation_sha256": digest_file(Path(__file__)),
                    "source_sha256": snapshot["dataset_sha256"], "model_manifest_digest": snapshot["model_manifest_digest"],
                    "model_manifest_verification": "control_service", "max_seq_length": snapshot["max_seq_length"],
                    "runtime": versions, "recipe": frozen_recipe, "tokenization_recipe_digest": recipe_digest}
        identity_digest = hashlib.sha256(canonical(identity)).hexdigest()
        with (output / ".sample-checks.jsonl.tmp").open("xb") as stream:
            counts, exclusions, examples, source_digest = _check_rows(dataset, tokenizer, snapshot["max_seq_length"], stream, check_cancel)
            stream.flush()
            os.fsync(stream.fileno())
        check_cancel()
        if source_digest != snapshot["dataset_sha256"] or digest_file(dataset) != source_digest:
            raise SplitCheckError("DATASET_CHANGED", "原件在检查期间发生变化，请重新准备计划", "input")
        _tokenizer_files(model)
        if _runtime() != versions:
            raise SplitCheckError("TOKENIZER_CHANGED", "分词环境在检查期间发生变化")
        report = {"schema_version": 1, "check_identity": identity, "check_identity_digest": identity_digest,
                  **counts, "exclusion_counts": exclusions, "token_labels_examples": examples,
                  "packing": False, "ignore_index": -100, "pad_id": tokenizer.pad_token_id,
                  "shift": "input_ids[:-1] 预测 labels[1:]"}
        with (output / ".check-report.json.tmp").open("xb") as stream:
            stream.write(canonical(report) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    check_cancel()
    for name in ("sample-checks.jsonl", "check-report.json"):
        temporary = output / ("." + name + ".tmp")
        # 专属暂存目录内以独占创建发布；外置资料盘不必支持硬链接。
        with temporary.open("rb") as source, (output / name).open("xb") as destination:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                check_cancel()
                destination.write(block)
            destination.flush()
            os.fsync(destination.fileno())
        temporary.unlink()
    artifacts = {name: {"sha256": digest_file(output / name), "size_bytes": (output / name).stat().st_size}
                 for name in ("sample-checks.jsonl", "check-report.json")}
    return {"schema_version": 1, "kind": "dataset-check", "ok": True, "check_identity_digest": identity_digest,
            "source_sha256": source_digest, **counts, "artifacts": artifacts}


@contextlib.contextmanager
def controller_guard(controller_pid):
    """父控制器消失即停止本次 CPU 子进程，不在崩溃后继续写计划暂存。"""
    def check_cancel():
        if controller_pid is not None and (controller_pid <= 1 or os.getppid() != controller_pid):
            raise SplitCheckError("CHECK_CANCELLED", "所属控制器已退出，分词检查停止")
    check_cancel()
    stopped = threading.Event()
    def watch():
        while not stopped.wait(0.25):
            if os.getppid() != controller_pid:
                os.kill(os.getpid(), signal.SIGTERM)
                return
    watcher = threading.Thread(target=watch, name="dataset-check-owner", daemon=True) if controller_pid is not None else None
    if watcher is not None:
        watcher.start()
    try:
        yield check_cancel
    finally:
        stopped.set()
        if watcher is not None:
            watcher.join(timeout=1)


def main():
    parser = argparse.ArgumentParser(description="来源组划分前的离线 CPU 分词检查")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--controller-pid", type=int)
    args = parser.parse_args()
    try:
        try:
            snapshot = strict_json(args.snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            raise SplitCheckError("INVALID_CHECK_REQUEST", "无法读取有效的分词检查请求", "input") from None
        with contextlib.redirect_stdout(sys.stderr), controller_guard(args.controller_pid) as check_cancel:
            result = check(snapshot, args.output_dir, check_cancel=check_cancel)
    except SplitCheckError as exc:
        blocking = {"code": exc.code, "message": str(exc)}
        if exc.line is not None:
            blocking["line"] = exc.line
        result = {"schema_version": 1, "kind": "dataset-check", "ok": False,
                  "failure_scope": exc.scope, "blocking": [blocking]}
    except OSError:
        result = {"schema_version": 1, "kind": "dataset-check", "ok": False, "failure_scope": "output",
                  "blocking": [{"code": "CHECK_IO_FAILED", "message": "检查文件读写未完成，未生成可应用结果"}]}
    except Exception:
        result = {"schema_version": 1, "kind": "dataset-check", "ok": False, "failure_scope": "environment",
                  "blocking": [{"code": "TOKENIZER_CHECK_FAILED", "message": "CPU 分词运行失败，未生成可应用结果"}]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
