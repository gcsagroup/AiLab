"""纯文件反例，检查执行前后的冻结输入身份，不启动 GPU。"""

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers.mlx_worker import WorkerError, canonical_digest, snapshot_manifest, verify_snapshot_manifest


@pytest.mark.parametrize("mutation", ["modify", "add_weight", "add_nested", "delete", "replace_symlink"])
def test_model_manifest_rejects_changed_complete_file_set(tmp_path, mutation):
    model = tmp_path / "model"
    model.mkdir()
    source = model / "config.json"
    source.write_text("{}")
    entries, digest = snapshot_manifest(model)
    verify_snapshot_manifest(model, entries, digest, "MODEL")
    if mutation == "modify":
        source.write_text('{"changed":true}')
    elif mutation == "add_weight":
        (model / "extra.safetensors").write_bytes(b"unregistered")
    elif mutation == "add_nested":
        (model / "nested").mkdir()
        (model / "nested/extra.json").write_text("{}")
    elif mutation == "delete":
        source.unlink()
    else:
        replacement = tmp_path / "replacement.json"
        replacement.write_text("{}")
        source.unlink()
        source.symlink_to(replacement)
    with pytest.raises(WorkerError) as exc:
        verify_snapshot_manifest(model, entries, digest, "MODEL")
    assert exc.value.code in {"MODEL_IDENTITY_CHANGED", "INPUT_SYMLINK"}


def test_missing_manifest_fails_closed(tmp_path):
    with pytest.raises(WorkerError) as exc:
        verify_snapshot_manifest(tmp_path, None, None, "MODEL")
    assert exc.value.code == "MODEL_IDENTITY_REQUIRED"


def test_manifest_digest_uses_control_canonical_json():
    value = [{"path": "中文 文件.jsonl", "size": 1, "sha256": "a" * 64}]
    import hashlib
    expected = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert canonical_digest(value) == expected


def test_dataset_frozen_identity_changes_with_content(tmp_path):
    dataset = tmp_path / "训练.jsonl"
    dataset.write_text('{"messages":[]}\n')
    entries, digest = snapshot_manifest(dataset)
    verify_snapshot_manifest(dataset, entries, digest, "DATASET")
    dataset.write_text('{"messages":[1]}\n')
    with pytest.raises(WorkerError) as exc:
        verify_snapshot_manifest(dataset, entries, digest, "DATASET")
    assert exc.value.code == "DATASET_IDENTITY_CHANGED"
