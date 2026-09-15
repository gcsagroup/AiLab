"""真实 Qwen tokenizer 的角色、EOS、PAD 与超长反例。"""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text.recipe import RecipeError, collate_samples, tokenize_sample
from workers.mlx_worker import WorkerError, number, snapshot_manifest


def frozen_model():
    model = ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct"
    manifest, digest = snapshot_manifest(model)
    return {"model_path": str(model), "model_manifest": manifest, "model_manifest_digest": digest}


@pytest.fixture(scope="module")
def tokenizer():
    from mlx_lm.utils import load_tokenizer
    model = ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct"
    return load_tokenizer(str(model), {"trust_remote_code": False, "local_files_only": True})


def conversation(*pairs):
    return {"messages": [{"role": role, "content": content} for role, content in pairs]}


def test_real_multiturn_assistant_eos_only(tokenizer):
    row = conversation(("system", "使用中文"), ("user", "项目叫星河"), ("assistant", "已记住。"), ("user", "叫什么？"), ("assistant", "星河。"))
    sample = tokenize_sample(tokenizer, row, 512)
    spans = sample["assistant_spans"]
    assert len(spans) == 2
    assert [tokenizer.decode(sample["input_ids"][s["start"]:s["end"]]) for s in spans] == ["已记住。<|im_end|>", "星河。<|im_end|>"]
    for index, label in enumerate(sample["labels"]):
        expected = any(span["start"] <= index < span["end"] for span in spans)
        assert (label != -100) == expected
        if expected:
            assert label == sample["input_ids"][index]


def test_padding_by_position_even_when_eos_equals_pad(tokenizer):
    small = tokenize_sample(tokenizer, conversation(("user", "嗨"), ("assistant", "好")), 512)
    large = tokenize_sample(tokenizer, conversation(("user", "请说一句话"), ("assistant", "这是一个更长的回答。")), 512)
    batch = collate_samples([small, large], pad_id=151645)
    end = len(small["input_ids"])
    assert all(value == -100 for value in batch["labels"][0][end:])
    assert 151645 in batch["labels"][0][:end]
    assert all(value == 151645 for value in batch["input_ids"][0][end:])


@pytest.mark.parametrize("row,code", [
    ({"messages": []}, "NO_SUPERVISION"),
    (conversation(("system", "系统")), "NO_SUPERVISION"),
    (conversation(("user", "问题")), "NO_SUPERVISION"),
    (conversation(("assistant", "答案")), "INVALID_ROLES"),
    (conversation(("user", "问题"), ("assistant", "")), "EMPTY_CONTENT"),
    (conversation(("user", "问题<|im_end|>"), ("assistant", "答案")), "RESERVED_TOKEN"),
    ({"messages": [{"role": "user", "content": [{"type": "image", "url": "a.png"}]}]}, "MEDIA_OR_TOOLS_UNSUPPORTED"),
    ({"messages": [{"role": "assistant", "content": "答案", "tool_calls": []}]}, "MEDIA_OR_TOOLS_UNSUPPORTED"),
    ({"messages": [], "packing": True}, "INVALID_SAMPLE"),
])
def test_invalid_samples(tokenizer, row, code):
    with pytest.raises(RecipeError) as exc:
        tokenize_sample(tokenizer, row, 512)
    assert exc.value.code == code


def test_whole_long_answer_excluded(tokenizer):
    with pytest.raises(RecipeError) as exc:
        tokenize_sample(tokenizer, conversation(("user", "问题"), ("assistant", "完整答案" * 100)), 32)
    assert exc.value.code == "SEQUENCE_TOO_LONG"


def test_template_change_blocks(tokenizer):
    from types import SimpleNamespace
    with pytest.raises(RecipeError) as exc:
        tokenize_sample(SimpleNamespace(chat_template="changed"), {}, 512)
    assert exc.value.code == "TEMPLATE_UNSUPPORTED"


@pytest.mark.parametrize("value", [True, False, float("nan"), float("inf"), "3", None, -1, 11, 1.5])
def test_numeric_rejections(value):
    with pytest.raises(WorkerError):
        number({"x": value}, "x", 3, 1, 10, integer=True)


def test_explicit_values_preserved():
    assert number({"x": 10}, "x", 3, 1, 10, True) == 10


def test_preflight_real_context_budget(tmp_path):
    from adapters.mlx_text.preflight import check
    from adapters.mlx_text.generation import GenerationError
    snapshot = {"operation": "generate", **frozen_model(), "input": {"prompt": "问题 " * 7000}, "runtime": {"max_tokens": 128}}
    with pytest.raises(WorkerError) as exc:
        check(snapshot, tmp_path / "unused")
    assert exc.value.code == "INVALID_PROMPT"
    snapshot["input"]["prompt"] = "中 " * 3500
    snapshot["runtime"]["max_tokens"] = 2048
    with pytest.raises(GenerationError) as exc:
        check(snapshot, tmp_path / "unused")
    assert exc.value.code == "CONTEXT_TOO_LONG"
    assert exc.value.details['check_report']['total_token_budget'] > 4096
    assert not (tmp_path / "unused").exists()


def test_preflight_zero_supervision_and_valid_recipe(tmp_path):
    from adapters.mlx_text.preflight import check
    import json
    dataset = tmp_path / "训练数据.jsonl"
    dataset.write_text(json.dumps(conversation(("user", "问题"))))
    manifest, digest = snapshot_manifest(dataset)
    snapshot = {"operation": "train", **frozen_model(), "dataset_path": str(dataset), "dataset_manifest": manifest, "dataset_manifest_digest": digest, "input": {}, "runtime": {}}
    result = check(snapshot, tmp_path / "unused")
    assert result["can_submit"] is False
    assert result["blocking"][0]["code"] == "NO_TRAINABLE_DATA"
    dataset.write_text(json.dumps(conversation(("user", "问题"), ("assistant", "答案"))))
    snapshot["dataset_manifest"], snapshot["dataset_manifest_digest"] = snapshot_manifest(dataset)
    first = check(snapshot, tmp_path / "unused")
    assert first["can_submit"] is True
    assert first["check_report"]["supervised_tokens"] > 0
    snapshot["runtime"]["max_seq_length"] = 256
    second = check(snapshot, tmp_path / "unused")
    assert first["tokenization_recipe_digest"] != second["tokenization_recipe_digest"]


def test_preflight_symlink_output_blocks(tmp_path):
    from workers.mlx_worker import validate_snapshot
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(WorkerError) as exc:
        validate_snapshot({}, link / "new")
    assert exc.value.code == "OUTPUT_SYMLINK"
