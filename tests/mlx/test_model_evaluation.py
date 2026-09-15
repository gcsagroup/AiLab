"""量化对照的执行器输入边界，不运行 GPU。"""

import copy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text.evaluation import model_evaluation_identity, model_plan_bound
from workers.mlx_worker import WorkerError, canonical_digest, snapshot_manifest, validate_comparison_model


def comparison(tmp_path):
    base, candidate, output = (tmp_path / name for name in ("base", "quantized", "output"))
    quantization = {"bits": 4, "group_size": 64, "mode": "affine"}
    snapshot = {"model_id": "base-id", "model_version_id": "base-version", "candidate_model_id": "q4-id", "candidate_model_version_id": "q4-version", "candidate_model_path": str(candidate), "evaluation_plan_id": "plan-1", "evaluation_plan_digest": "a" * 64, "evaluation_plan_created_at": "2026-09-10T10:00:00+00:00", "submitted_at": "2026-09-10T10:02:00+00:00"}
    for path, prefix, quantized in ((base, "model", False), (candidate, "candidate_model", True)):
        path.mkdir()
        config = {"model_type": "qwen2", "hidden_size": 896, "num_hidden_layers": 24}
        if quantized: config["quantization"] = quantization
        (path / "config.json").write_text(json.dumps(config)); (path / "model.safetensors").write_bytes(b"file-contract-only")
        (path / "tokenizer_config.json").write_text("{}")
        entries, identity = snapshot_manifest(path)
        snapshot.update({prefix + "_manifest": entries, prefix + "_manifest_digest": identity})
    value = {"kind": "quantized_model", "baseline_model_id": snapshot["model_id"], "baseline_model_version_id": snapshot["model_version_id"], "baseline_model_manifest_digest": snapshot["model_manifest_digest"], "candidate_model_id": snapshot["candidate_model_id"], "candidate_model_version_id": snapshot["candidate_model_version_id"], "candidate_model_manifest_digest": snapshot["candidate_model_manifest_digest"], "conversion_attempt_id": "conversion-id", "conversion_manifest_digest": "b" * 64, "conversion_report_sha256": "c" * 64, "candidate_format": "mlx-safetensors", "candidate_default_engine": "mlx", "quantization": quantization}
    snapshot.update(model_comparison=value, model_comparison_digest=canonical_digest(value))
    binding = {"schema_version": "quantized-model-quality-v1", "model_comparison_digest": snapshot["model_comparison_digest"], "evaluation_plan_id": snapshot["evaluation_plan_id"], "evaluation_plan_digest": snapshot["evaluation_plan_digest"], "frozen_at": "2026-09-10T10:01:00+00:00"}
    snapshot["quality_plan_ref"] = {**binding, "digest": canonical_digest(binding)}
    return snapshot, base, candidate, output


def test_both_models_and_first_plan_are_bound_to_execution_code(tmp_path):
    snapshot, base, candidate, output = comparison(tmp_path)
    assert validate_comparison_model(snapshot, output, base) == candidate
    assert model_plan_bound(snapshot)
    recipe, identity = model_evaluation_identity(snapshot, "d" * 64)
    assert canonical_digest(recipe) == identity and len(recipe["source_sha256"]) == 5
    for key in ("model_comparison_digest", "evaluation_plan_digest"):
        changed = copy.deepcopy(snapshot); changed[key] = "e" * 64
        assert model_evaluation_identity(changed, "d" * 64)[1] != identity


@pytest.mark.parametrize("mutation", ["candidate_changed", "extra_file", "symlink", "same_directory", "output_overlap", "wrong_engine", "wrong_pair", "unsealed_conversion", "binding_changed", "binding_extra", "tokenizer_changed", "adapter"])
def test_invalid_comparison_fails_before_weight_loading(tmp_path, mutation):
    snapshot, base, candidate, output = comparison(tmp_path)
    if mutation == "candidate_changed": (candidate / "config.json").write_text("{}")
    if mutation == "extra_file": (candidate / "unexpected.json").write_text("{}")
    if mutation == "symlink":
        path = tmp_path / "linked"; path.symlink_to(candidate); snapshot["candidate_model_path"] = str(path)
    if mutation == "same_directory": snapshot["candidate_model_path"] = str(base)
    if mutation == "output_overlap": output = candidate / "output"
    if mutation == "wrong_engine": snapshot["model_comparison"]["candidate_default_engine"] = "coreml"
    if mutation == "wrong_pair": snapshot["model_comparison"]["baseline_model_id"] = "unrelated"
    if mutation == "unsealed_conversion": snapshot["model_comparison"]["conversion_manifest_digest"] = ""
    if mutation == "binding_changed": snapshot["quality_plan_ref"]["evaluation_plan_id"] = "later"
    if mutation == "binding_extra": snapshot["quality_plan_ref"]["new_override"] = True
    if mutation == "tokenizer_changed":
        (candidate / "tokenizer_config.json").write_text('{"template":"changed"}')
        entries, identity = snapshot_manifest(candidate)
        snapshot.update(candidate_model_manifest=entries, candidate_model_manifest_digest=identity)
    if mutation == "adapter": snapshot["adapter_path"] = str(base)
    with pytest.raises(WorkerError): validate_comparison_model(snapshot, output, base)


@pytest.mark.parametrize("mutation", ["new_plan", "future_plan", "future_binding", "naive_time", "invalid_time"])
def test_posthoc_or_unordered_binding_is_comparative_only(tmp_path, mutation):
    snapshot, _, _, _ = comparison(tmp_path)
    if mutation == "new_plan": snapshot["evaluation_plan_id"] = "later"
    if mutation == "future_plan": snapshot["evaluation_plan_created_at"] = "2026-09-10T10:03:00+00:00"
    if mutation == "future_binding": snapshot["quality_plan_ref"]["frozen_at"] = "2026-09-10T10:03:00+00:00"
    if mutation == "naive_time": snapshot["submitted_at"] = "2026-09-10T10:03:00"
    if mutation == "invalid_time": snapshot["submitted_at"] = "invalid"
    assert not model_plan_bound(snapshot)
