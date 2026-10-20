"""来源核验合同：真实文件哈希、恶意路径、版本及导出恢复边界。"""

import hashlib
import json
from pathlib import Path

import pytest

from test_control import rig, setup_task, post
from test_delivery import prepare, export
from ailab_control.source_checks import inspect_document
from ailab_control.storage import Fault, digest
from ailab_control.backup import remap_reference_paths


def document(tool="heretic"):
    if tool == "heretic":
        return {"version": "4", "environment": {"heretic": {"version": "2.0.0.dev0", "metadata": {"commit": "fixture"}}, "requirements": {"mlx": "0.31.1", "torch": "2.8"}}, "hashes": {"model.safetensors": "a" * 64}, "settings": {"model": "example/model"}}
    result = {"schema_version": 2, "tool": "abliterix", "abliterix_version": "1.12.2", "source": {"commit": "fixture"}, "packages": {"mlx": "0.31.1", "torch": None}, "weights": {"model.safetensors": "a" * 64}, "config": {"output_dir": "/untrusted/path"}}
    seal(result)
    return result


def seal(value):
    value["integrity"] = {"algorithm": "sha256", "canonical_manifest": digest({k: v for k, v in value.items() if k != "integrity"})}


@pytest.mark.parametrize("tool", ["heretic", "abliterix"])
def test_known_protocols_and_unknown_environment_are_not_readiness(tool):
    result = inspect_document(document(tool), [{"path": "model.safetensors", "sha256": "a" * 64}], {"mlx": "0.31.1"})
    assert result["files_match"] and result["environment"][0]["status"] == "matched"
    assert result["environment"][1]["status"] == "unavailable"
    assert result["report_integrity"] == ("matched" if tool == "abliterix" else "not_provided")


@pytest.mark.parametrize("mutation", ["../weights", "/weights", "a/../b", "a//b", "a\\b", "a/./b"])
def test_report_paths_are_data_never_followed(mutation):
    value = document(); value["hashes"] = {mutation: "a" * 64}
    with pytest.raises(Fault, match="目录跳转"):
        inspect_document(value, [], {})


@pytest.mark.parametrize("tool", ["heretic", "abliterix"])
def test_future_versions_fail_closed(tool):
    value = document(tool); value["version" if tool == "heretic" else "schema_version"] = "999"
    with pytest.raises(Fault) as error: inspect_document(value, [], {})
    assert error.value.code == "SOURCE_REPORT_VERSION_UNSUPPORTED"


def test_tampered_report_missing_file_uncovered_weight_and_environment_difference():
    value = document("abliterix"); value["source"] = {"commit": "tampered"}
    result = inspect_document(value, [{"path": "other.safetensors", "sha256": "b" * 64}], {"mlx": "0.30.0"})
    assert not result["files_match"] and result["report_integrity"] == "mismatch"
    assert result["files"][0]["status"] == "missing" and result["uncovered_weights"] == ["other.safetensors"]
    assert result["environment"][0]["status"] == "different"


def create(rig, tool="heretic"):
    project, model, _ = setup_task(rig)
    stored = rig[1].store.get("model", model["id"])
    report = document(tool)
    report["hashes" if tool == "heretic" else "weights"] = {entry["path"]: entry["sha256"] for entry in stored["manifest"] if entry["path"].endswith(".safetensors")}
    if tool == "abliterix": seal(report)
    path = rig[2] / "外部来源.json"; path.write_text(json.dumps(report))
    body = {"project_id": project["id"], "model_id": model["id"], "report_path": str(path)}
    return project, model, path, body


def test_file_readback_idempotency_reopen_export_and_tamper(rig, tmp_path):
    project, model, path, body = create(rig)
    result = post(rig[0], "/source-checks", body, "check-source")
    assert result["result"]["files_match"] and result["result"]["library_manifest_matches"]
    assert "source_document" not in result
    path.write_text("invalid after saved")
    assert post(rig[0], "/source-checks", body, "check-source") == result
    listed = rig[0].get('/api/v1/source-checks', params={"project_id": project["id"]}).json()["items"]
    assert listed == [result]
    prepared = prepare(rig, "source-check", result["id"], project["id"], tmp_path / "导出来源")
    exported, _ = export(rig, prepared)
    saved = json.loads((Path(exported["verified_path"]) / "source-check.json").read_text())
    assert saved["source_report_sha256"] == result["source_report_sha256"]
    assert hashlib.sha256((Path(exported["verified_path"]) / "source-report.json").read_bytes()).hexdigest() == result["source_report_sha256"]
    original = rig[1].store.get("source-check", result["id"])
    original["result"]["files_match"] = False
    with rig[1].store.transaction(): rig[1].store.put("source-check", original)
    with pytest.raises(Fault) as error: rig[1].delivery.export_sources(project["id"], "source-check", result["id"], False)
    assert error.value.code == "SOURCE_CHECK_CHANGED"


def test_actual_weights_changed_and_missing_are_saved_as_findings(rig):
    project, model, path, body = create(rig)
    stored = rig[1].store.get("model", model["id"])
    weight = Path(stored["storage_path"]) / "model.safetensors"
    weight.chmod(0o644)
    weight.write_bytes(b"changed")
    result = post(rig[0], "/source-checks", body, "changed")
    assert not result["result"]["files_match"] and not result["result"]["library_manifest_matches"]
    weight.parent.chmod(0o755)
    weight.unlink()
    result = post(rig[0], "/source-checks", body, "missing")
    assert result["result"]["files"][0]["status"] == "missing"


def test_opaque_external_document_survives_restore_path_mapping():
    record = {"resource_type": "source-check", "source_document": {"config": {"source_path": "/old/library/assets/x"}}}
    record["record_digest"] = digest(record)
    assert remap_reference_paths(record, Path("/old/library"), Path("/new/library")) == record


def test_invalid_json_duplicate_fields_and_foreign_project(rig):
    project, model, path, body = create(rig)
    path.write_text('{"version":"4","version":"4"}')
    response = rig[0].post('/api/v1/source-checks', json=body)
    assert response.status_code == 400 and response.json()["error"]["code"] == "SOURCE_REPORT_INVALID"
    other = post(rig[0], '/projects', {"name": "其他项目"})
    response = rig[0].post('/api/v1/source-checks', json={**body, "project_id": other["id"]})
    assert response.status_code == 403


def test_source_report_original_bytes_survive_complete_backup_restore(rig, tmp_path):
    from ailab_control.api import create_app
    from ailab_control.service import Settings
    from ailab_control.backup import Backup
    from test_backup_restore import plan_restore
    project, model, path, body = create(rig, "abliterix")
    value = json.loads(path.read_text())
    marker = tmp_path / 'must-not-execute'
    value['config']['source_path'] = str(rig[1].root / 'assets' / 'external-untrusted-reference')
    value['config']['command'] = f'touch {marker}'
    seal(value); path.write_text(json.dumps(value, ensure_ascii=False, indent=4) + '\n')
    record = post(rig[0], '/source-checks', body, 'portable-source')
    assert not marker.exists()
    manager = Backup(rig[1]); backup = manager.create()
    plan = plan_restore(rig, manager, backup, tmp_path / '恢复来源')
    restored = manager.restore({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'restore-source')
    service = create_app(Settings(Path(restored['restored_path']), 'source-restored')).state.service
    try:
        original = rig[1].store.get('source-check', record['id'])
        assert service.store.get('source-check', record['id']) == original
        _, files, _ = service.delivery.export_sources(project['id'], 'source-check', record['id'], False)
        raw = next(item for item in files if item['path'] == 'source-report.json')
        assert raw['contents'].encode() == path.read_bytes() and raw['sha256'] == record['source_report_sha256']
        assert not marker.exists()
    finally:
        service.close()


def test_malformed_tool_version_remains_safe_display_data():
    value = document(); value['environment']['heretic']['version'] = {'unexpected': 'object'}
    result = inspect_document(value, [], {})
    assert result['tool_version'] is None
    assert any(item['code'] == 'TOOL_VERSION_MISSING' for item in result['findings'])
