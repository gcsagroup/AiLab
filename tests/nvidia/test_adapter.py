"""NVIDIA 适配器的文件、参数和失败边界；不把 CPU 测试当作 CUDA 验收。"""

import copy
import json
from pathlib import Path
import struct
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "services/control"))
from adapters.nvidia_text import adapter
from ailab_control.remote.protocol import ProtocolError, digest, file_hash


def frozen_snapshot(operation="generate"):
    pin = json.loads(Path(__file__).with_name("model-manifest.json").read_text())
    value = {"schema_version": 1, "attempt_id": "attempt-" + "a" * 32, "executor_id": "executor-" + "b" * 32, "adapter_id": "nvidia-text", "operation": operation, "inputs": [{**entry, "path": "model/" + entry["path"]} for entry in pin["manifest"]], "input": {"model_manifest_digest": adapter.MODEL_DIGEST, "source_code_digest": adapter.source_identity()}, "runtime": {"engine": "transformers", "device_id": "cuda:0", "precision": "bfloat16", "seed": 0}}
    if operation == "generate":
        value["input"]["prompt"] = "只回答：完成"
        value["runtime"].update(max_tokens=8, temperature=0, top_p=1)
    else:
        entry = {"path": "data/train.jsonl", "size": 3, "sha256": "c" * 64}; value["inputs"].append(entry)
        value["input"]["dataset_manifest_digest"] = digest([{**entry, "path": "train.jsonl"}])
        value["runtime"].update(steps=2, batch_size=1, learning_rate=1e-4, max_seq_length=128, lora_rank=4, lora_alpha=8, num_layers=1)
    return value


@pytest.mark.parametrize("operation", ["generate", "train"])
@pytest.mark.parametrize("transport", [None, "loopback_http", "https"])
def test_fixed_snapshot_resolves_only_selected_runtime_and_reserves_output(operation, transport):
    snapshot = frozen_snapshot(operation)
    if transport is not None:
        snapshot["transport"] = transport
    old = copy.deepcopy(snapshot)
    effective = adapter.validate_snapshot(snapshot)
    assert snapshot == old and effective["device_id"] == "cuda:0"
    assert adapter.output_reserve_bytes(snapshot) == (4 if operation == "generate" else 64) * 1024**2


@pytest.mark.parametrize("mutation", ["cpu", "apple", "fp32", "quantize", "unknown", "path", "duplicate", "model_hash", "executor", "nan", "bool", "zero_top_p", "thinking", "trim", "empty_stop", "duplicate_stop", "long_prompt"])
def test_unsupported_combinations_and_untrusted_fields_fail_before_loading(mutation):
    snapshot = frozen_snapshot()
    if mutation == "cpu": snapshot["runtime"]["device_id"] = "cpu"
    if mutation == "apple": snapshot["runtime"]["engine"] = "mlx"
    if mutation == "fp32": snapshot["runtime"]["precision"] = "float32"
    if mutation == "quantize": snapshot["operation"] = "quantize"
    if mutation == "unknown": snapshot["runtime"]["shell"] = "anything"
    if mutation == "path": snapshot["inputs"][0]["path"] = "../outside"
    if mutation == "duplicate": snapshot["inputs"][1] = snapshot["inputs"][0]
    if mutation == "model_hash": snapshot["inputs"][0]["sha256"] = "f" * 64
    if mutation == "executor": snapshot["executor_id"] = "other"
    if mutation == "nan": snapshot["runtime"]["temperature"] = float("nan")
    if mutation == "bool": snapshot["runtime"]["max_tokens"] = True
    if mutation == "zero_top_p": snapshot["runtime"]["top_p"] = 0
    if mutation == "thinking": snapshot["runtime"]["thinking"] = "on"
    if mutation == "trim": snapshot["runtime"]["overflow"] = "trim"
    if mutation == "empty_stop": snapshot["runtime"]["stop"] = [""]
    if mutation == "duplicate_stop": snapshot["runtime"]["stop"] = ["x", "x"]
    if mutation == "long_prompt": snapshot["input"]["prompt"] *= 4000
    with pytest.raises(ProtocolError): adapter.validate_snapshot(snapshot)


@pytest.mark.parametrize("mutation", ["dataset_identity", "too_many_steps", "batch", "qlora", "missing_plan", "later_plan", "naive_time"])
def test_training_method_supervision_and_prospective_plan_are_explicit(mutation):
    snapshot = frozen_snapshot("train")
    if mutation == "dataset_identity": snapshot["input"]["dataset_manifest_digest"] = "f" * 64
    if mutation == "too_many_steps": snapshot["runtime"]["steps"] = 513
    if mutation == "batch": snapshot["runtime"]["batch_size"] = 2
    if mutation == "qlora": snapshot["runtime"]["method"] = "qlora"
    if mutation in {"missing_plan", "later_plan", "naive_time"}:
        snapshot["input"].update(evaluation_plan_digest="f" * 64, evaluation_plan_created_at="2026-09-10T10:00:00+00:00", submitted_at="2026-09-10T11:00:00+00:00")
        if mutation != "missing_plan":
            snapshot["inputs"].extend({"path": "evaluation/" + name, "sha256": "d" * 64, "size": 3} for name in ("evaluation.jsonl", "criteria.json"))
        if mutation == "later_plan": snapshot["input"]["evaluation_plan_created_at"] = "2026-09-10T12:00:00+00:00"
        if mutation == "naive_time": snapshot["input"]["submitted_at"] = "2026-09-10T11:00:00"
    with pytest.raises(ProtocolError): adapter.validate_snapshot(snapshot)


def test_mac_probe_and_formal_run_never_fall_back_to_cpu(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter.sys, "platform", "darwin")
    result = adapter.probe()
    assert result["ready"] is False and result["devices"] == [] and result["hardware_acceptance"] == "not_verified"
    monkeypatch.setattr(adapter, "prepare", lambda *_: pytest.fail("环境未通过不能加载分词器或模型"))
    with pytest.raises(ProtocolError) as error:
        adapter.run(frozen_snapshot(), tmp_path / "input", tmp_path / "output", lambda *_: None, lambda: None)
    assert error.value.code == "NVIDIA_NOT_READY" and not (tmp_path / "output").exists()


@pytest.mark.parametrize("existing", ["file", "nonempty", "linked"])
def test_output_never_overwrites_or_follows_symlinks(tmp_path, existing):
    output = tmp_path / "output"
    if existing == "file": output.write_text("保留")
    elif existing == "nonempty": output.mkdir(); (output / "keep").write_text("保留")
    else:
        destination = tmp_path / "other"; destination.mkdir(); output.symlink_to(destination)
    with pytest.raises(ProtocolError) as error:
        adapter.run(frozen_snapshot(), tmp_path / "input", output, lambda *_: None, lambda: None)
    assert error.value.code == "UNSAFE_OUTPUT_DIRECTORY"


def file_fixture(tmp_path, monkeypatch):
    root = tmp_path / "input"; model = root / "model"; model.mkdir(parents=True)
    for name in adapter.MODEL_FILES: (model / name).write_text("{}")
    (model / "config.json").write_text(json.dumps({"model_type": "qwen2", "hidden_size": 896, "num_hidden_layers": 24}))
    header = json.dumps({"tensor": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode(); header += b" " * (-len(header) % 8)
    (model / "model.safetensors").write_bytes(struct.pack("<Q", len(header)) + header + struct.pack("<f", 1))
    files = [{"path": path.name, "size": path.stat().st_size, "sha256": file_hash(path)} for path in sorted(model.iterdir())]
    snapshot = frozen_snapshot(); monkeypatch.setattr(adapter, "MODEL_DIGEST", digest(files))
    snapshot["input"]["model_manifest_digest"] = adapter.MODEL_DIGEST
    snapshot["inputs"] = [{**item, "path": "model/" + item["path"]} for item in files]
    return snapshot, root, model


@pytest.mark.parametrize("mutation", ["valid", "file", "extra", "link"])
def test_frozen_input_bytes_and_full_file_set_are_rechecked(tmp_path, monkeypatch, mutation):
    snapshot, root, model = file_fixture(tmp_path, monkeypatch)
    if mutation == "file": (model / "config.json").write_text("changed")
    if mutation == "extra": (model / "unlisted.py").write_text("pass")
    if mutation == "link":
        path = model / "README.md"; path.unlink(); path.symlink_to(model / "LICENSE")
    if mutation == "valid": assert adapter.read_inputs(snapshot, root)[1]["manifest_digest"] == adapter.MODEL_DIGEST
    else:
        with pytest.raises(ProtocolError): adapter.read_inputs(snapshot, root)
