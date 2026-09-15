"""来源合同和量化格式反例，验证失败时不进入模型加载。"""

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers.mlx_worker import WorkerError, snapshot_manifest, validate_adapter_metadata, validate_snapshot


@pytest.mark.parametrize("field,value,code", [
    ("base_manifest_sha256", "0" * 64, "ADAPTER_BASE_MISMATCH"),
    ("template_sha256", "0" * 64, "ADAPTER_TEMPLATE_MISMATCH"),
    ("base_input_manifest_digest", "0" * 64, "ADAPTER_PROVENANCE_MISMATCH"),
    ("training_recipe_digest", "0" * 64, "ADAPTER_PROVENANCE_MISMATCH"),
    ("training_recipe_digest", None, "ADAPTER_PROVENANCE_MISMATCH"),
    ("fine_tune_type", "full", "ADAPTER_MODULE_MISMATCH"),
])
def test_adapter_identity_or_type_rejected(tmp_path, field, value, code):
    config = {"fine_tune_type": "lora", "base_manifest_sha256": "b" * 64, "template_sha256": "c" * 64, "base_input_manifest_digest": "d" * 64, "training_recipe_digest": "e" * 64, "num_layers": 2, "lora_parameters": {"keys": ["self_attn.q_proj", "self_attn.v_proj"], "rank": 4, "scale": 2, "dropout": 0}}
    config[field] = value
    (tmp_path / "adapter_config.json").write_text(json.dumps(config))
    with pytest.raises(WorkerError) as exc:
        validate_adapter_metadata(tmp_path, "b" * 64, "c" * 64, "d" * 64, "e" * 64)
    assert exc.value.code == code


@pytest.mark.parametrize("operation,quantization,code", [
    ("train", {"group_size": 64, "bits": 4, "mode": "affine"}, "MODEL_OPERATION_UNSUPPORTED"),
    ("quantize", {"group_size": 64, "bits": 4, "mode": "affine"}, "MODEL_OPERATION_UNSUPPORTED"),
    ("generate", {"group_size": 32, "bits": 4, "mode": "affine"}, "MODEL_FORMAT_UNSUPPORTED"),
    ("generate", {"group_size": 64, "bits": 8, "mode": "affine"}, "MODEL_FORMAT_UNSUPPORTED"),
])
def test_unverified_quantized_operation_rejected(tmp_path, operation, quantization, code):
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text(json.dumps({"model_type": "qwen2", "hidden_size": 896, "num_hidden_layers": 24, "quantization": quantization}))
    (model / "model.safetensors").write_bytes(b"fixture-only")
    entries, digest = snapshot_manifest(model)
    snapshot = {"operation": operation, "model_path": str(model), "model_manifest": entries, "model_manifest_digest": digest, "input": {"prompt": "测试"}, "runtime": {}}
    with pytest.raises(WorkerError) as exc:
        validate_snapshot(snapshot, tmp_path / "output")
    assert exc.value.code == code
