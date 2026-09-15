"""真实 SQLite、文件与独立 fixture 执行验证可移植恢复，不改变原库。"""

import json
import copy
from pathlib import Path
import shutil
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from test_control import rig, post, submit, wait_attempt, setup_task
from test_delivery import trained_fixture, prepare, export
from test_evaluation import training, evaluate
from test_checkpoints import training_run, paused
from ailab_control.api import create_app
from ailab_control.assets import file_hash, verify_manifest
from ailab_control.backup import Backup, publish
import ailab_control.backup as backup_module
from ailab_control.service import Settings
from ailab_control.storage import Fault, digest, encode


def stopped_checkpoint(training_run):
    client, service, attempt, model, environment = training_run
    internal_model = service.store.get("model", model["id"])
    dataset = service.store.get("dataset", attempt["snapshot"]["dataset_id"])
    attempt["snapshot"].update(model_path=internal_model["storage_path"], dataset_path=str(Path(dataset["storage_path"]) / dataset["manifest"][0]["path"]))
    attempt["snapshot_digest"] = digest(attempt["snapshot"])
    with service.store.transaction():
        service.store.put("attempt", attempt)
    run = client, service, attempt, model, environment
    current, path = paused(run)
    with service.store.transaction():
        current.update(state="cancelled", stop_status="confirmed")
        service.store.put("attempt", current)
    service.processes.pop(current["id"], None)
    return current, service.store.get("checkpoint", current["checkpoint_id"]), path


def test_checkpoint_evidence_and_resume_reference_survive_isolated_restore(rig, training_run, tmp_path):
    source, checkpoint, checkpoint_path = stopped_checkpoint(training_run)
    service = rig[1]
    original_bytes = {name: (checkpoint_path.parent / name).read_bytes() for name in ("manifest.json", "state.safetensors")}
    ref = {"path": str(checkpoint_path), "manifest_digest": checkpoint["manifest_digest"], "source_attempt_id": source["id"]}
    resumed = service.resource("attempt", source["project_id"], state="cancelled", snapshot={**source["snapshot"], "checkpoint_id": checkpoint["id"], "checkpoint_ref": ref})
    resumed["snapshot_digest"] = digest(resumed["snapshot"])
    with service.store.transaction():
        service.store.put("attempt", resumed)
    manager = Backup(service); backup = manager.create()
    plan = plan_restore(rig, manager, backup, tmp_path / "恢复检查点")
    result = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-checkpoint")
    app = create_app(Settings(Path(result["restored_path"]), "restored-checkpoint-token"))
    recovered = app.state.service
    try:
        restored_source = recovered.store.get("attempt", source["id"])
        restored_checkpoint = recovered.store.get("checkpoint", checkpoint["id"])
        restored_resumed = recovered.store.get("attempt", resumed["id"])
        restored_path = Path(restored_checkpoint["storage_path"])
        assert restored_path.is_relative_to(recovered.root)
        assert restored_resumed["snapshot"]["checkpoint_ref"] == {**ref, "path": str(restored_path)}
        assert restored_resumed["restoration"]["original_snapshot"]["checkpoint_ref"] == ref
        assert restored_source["snapshot_digest"] != source["snapshot_digest"]
        assert restored_checkpoint["source_snapshot_digest"] == source["snapshot_digest"]
        for name, content in original_bytes.items():
            assert (restored_path.parent / name).read_bytes() == content
        recovered.checkpoints.verify(restored_source, restored_path, checkpoint["manifest_digest"])
        for damage in ("original_snapshot", "path_mapping"):
            changed = copy.deepcopy(restored_source)
            if damage == "original_snapshot":
                changed["restoration"]["original_snapshot"]["runtime"]["seed"] += 1
            else:
                changed["restoration"]["path_mapping"] = {str(service.root): str(tmp_path / "另一个目录")}
            with pytest.raises(Fault):
                recovered.checkpoints.verify(changed, restored_path, checkpoint["manifest_digest"])
        second_manager = Backup(recovered); second_backup = second_manager.create()
        second_plan = plan_restore((None, recovered), second_manager, second_backup, tmp_path / "再次恢复检查点")
        second_result = second_manager.restore({"plan_id": second_plan["id"], "plan_digest": second_plan["plan_digest"]}, "restore-checkpoint-again")
        second_app = create_app(Settings(Path(second_result["restored_path"]), "restored-checkpoint-token-2"))
        second = second_app.state.service
        try:
            second_source = second.store.get("attempt", source["id"])
            second_checkpoint = second.store.get("checkpoint", checkpoint["id"])
            second_path = Path(second_checkpoint["storage_path"])
            assert second_source["restoration"]["previous_restoration"] == restored_source["restoration"]
            assert second.store.get("attempt", resumed["id"])["snapshot"]["checkpoint_ref"]["path"] == str(second_path)
            for name, content in original_bytes.items():
                assert (second_path.parent / name).read_bytes() == content
            second.checkpoints.verify(second_source, second_path, checkpoint["manifest_digest"])
        finally:
            second.close()
    finally:
        recovered.close()


@pytest.mark.parametrize("damage", ["missing_state", "changed_manifest", "missing_resource"])
def test_backup_checkpoint_reference_closure_rejects_damage(rig, training_run, tmp_path, damage):
    _, checkpoint, path = stopped_checkpoint(training_run)
    manager = Backup(rig[1])
    if damage == "changed_manifest":
        value = json.loads(path.read_text()); value["step"] += 1; path.write_text(json.dumps(value))
        with pytest.raises(Fault):
            manager.create()
        return
    backup = manager.create()
    package = Path(backup["backup_path"])
    manifest = json.loads((package / "manifest.json").read_text())
    if damage == "missing_state":
        relative = (path.parent / "state.safetensors").relative_to(rig[1].root).as_posix()
        (package / relative).unlink()
        manifest["files"] = [item for item in manifest["files"] if item["path"] != relative]
    else:
        import sqlite3
        db = sqlite3.connect(package / "control.sqlite3")
        db.execute("DELETE FROM resources WHERE id=?", (checkpoint["source_attempt_id"],)); db.commit(); db.close()
        item = next(item for item in manifest["files"] if item["path"] == "control.sqlite3")
        item.update(size=(package / "control.sqlite3").stat().st_size, sha256=file_hash(package / "control.sqlite3"))
    manifest["manifest_digest"] = digest({key: value for key, value in manifest.items() if key != "manifest_digest"})
    (package / "manifest.json").write_text(encode(manifest))
    with pytest.raises(Fault):
        plan_restore(rig, manager, backup, tmp_path / "拒绝损坏检查点")


def ready_backup(rig):
    client, service, _, _ = rig
    project, model, trained = trained_fixture(rig)
    adapter = post(client, f"/attempts/{trained['id']}/adapters", {"name": "恢复适配器"}, "backup-adapter")
    for thread in list(service.threads):
        thread.join(timeout=2)
    manager = Backup(service)
    backup = manager.create()
    return manager, backup, project, model, trained, adapter


def plan_restore(rig, manager, backup, target):
    target.mkdir()
    grant = rig[1].delivery.export_grant(str(target))
    return manager.plan({"backup_path": backup["backup_path"], "target_dir": str(target), "target_grant_id": grant["grant_id"]})


def test_export_history_survives_complete_backup_restore_and_reexport(rig, tmp_path):
    client, service, _, environment = rig
    project, model, _ = setup_task(rig)
    original_plan = prepare(rig, "model", model["id"], project["id"], tmp_path / "原库导出")
    original_export, _ = export(rig, original_plan, "export-before-backup")
    assert original_export["state"] == "succeeded"
    original_task = service.store.get("task", original_export["task_id"])
    assert original_task["draft"] is None and original_task["kind"] == original_task["operation"] == "export"
    for thread in list(service.threads):
        thread.join(timeout=2)
    original_rows = [tuple(row) for row in service.store.db.execute("SELECT id,body FROM resources ORDER BY id")]
    original_files = {str(path.relative_to(service.root)): file_hash(path) for folder in ("assets", "runs")
                      for path in (service.root / folder).rglob("*") if path.is_file()}
    manager = Backup(service)
    backup = manager.create("backup-with-export-history")
    plan = plan_restore(rig, manager, backup, tmp_path / "导出历史完整恢复")
    result = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-export-history")
    app = create_app(Settings(Path(result["restored_path"]), "export-history-restored-token"))
    recovered = app.state.service
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer export-history-restored-token"}) as restored_client:
        assert recovered.store.get("task", original_task["id"])["draft"] is None
        assert recovered.store.get("export", original_export["id"])["object_id"] == model["id"]
        restored_rig = restored_client, recovered, tmp_path, environment
        new_plan = prepare(restored_rig, "model", model["id"], project["id"], tmp_path / "恢复后重新导出")
        exported, _ = export(restored_rig, new_plan, "reexport-after-restore")
        assert exported["state"] == "succeeded"
        manifest = json.loads((Path(exported["verified_path"]) / "manifest.json").read_text())
        for entry in manifest["files"]:
            path = Path(exported["verified_path"]) / entry["path"]
            assert file_hash(path) == entry["sha256"] and path.stat().st_size == entry["size"]
        assert len([item for item in recovered.store.list("task") if item.get("operation") == "export"]) == 2
        for thread in list(recovered.threads):
            thread.join(timeout=2)
        second_backup = Backup(recovered).create("backup-after-reexport")
        assert second_backup["file_count"] >= backup["file_count"]
    assert [tuple(row) for row in service.store.db.execute("SELECT id,body FROM resources ORDER BY id")] == original_rows
    assert {str(path.relative_to(service.root)): file_hash(path) for folder in ("assets", "runs")
            for path in (service.root / folder).rglob("*") if path.is_file()} == original_files


@pytest.mark.parametrize("kind,fields", [
    ("task", {"kind": "text", "operation": "generate", "draft": None}),
    ("task", {"kind": "text", "operation": "transfer", "draft": None}),
    ("task", {"kind": "export", "operation": "generate", "draft": None}),
    ("task", {"kind": "export", "operation": "export", "draft": []}),
    ("task", {"kind": "export", "operation": "export", "draft": "damaged"}),
    ("attempt", {"snapshot": None}),
    ("attempt", {"snapshot": []}),
])
def test_backup_rejects_invalid_configuration_instead_of_hiding_references(tmp_path, kind, fields):
    resource = {"id": kind + "-" + "a" * 32, **fields}
    with pytest.raises(Fault) as rejected:
        backup_module.referenced_files([(kind, resource)], tmp_path)
    assert rejected.value.code == "BACKUP_INVALID"


@pytest.mark.parametrize("operation", ["generate", "transfer", "export"])
def test_backup_still_checks_checkpoint_references_for_every_task_operation(tmp_path, operation):
    resource = {"id": "task-" + "a" * 32, "kind": "export" if operation == "export" else "text", "operation": operation,
                "draft": {"checkpoint_id": "checkpoint-" + "b" * 32}}
    with pytest.raises(Fault) as rejected:
        backup_module.referenced_files([("task", resource)], tmp_path)
    assert rejected.value.code == "BACKUP_INVALID"


def test_restored_execution_target_never_inherits_machine_credential(rig, tmp_path):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "恢复连接记录"})
    original = service.execution_targets.create({"name": "已授权目标", "project_id": project["id"],
        "origin": "http://127.0.0.1:12345", "executor_id": "executor-" + "a" * 32,
        "credential_token": "restore-credential-" + "x" * 32,
        "credential_ref": "remote-credential-" + "b" * 32}, "restore-target-create", host=True)
    manager = Backup(service)
    backup = manager.create()
    plan = plan_restore(rig, manager, backup, tmp_path / "恢复连接目标")
    result = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-target-library")
    app = create_app(Settings(Path(result["restored_path"]), "restored-target-session"))
    recovered = app.state.service
    try:
        restored = recovered.execution_targets.get(original["id"])
        assert restored["credential_ref"] is None
        assert restored["credential_status"] == "required"
        assert restored["credential_storage"] == "none"
        assert restored["revision"] == original["revision"] + 1
        assert restored["connection_state"] == "unchecked"
        assert not restored["protocol_ready"] and not restored["nvidia_ready"]
        assert restored["adapters"] == {} and restored["last_error"] is None
        assert restored["credential_cleanup_refs"] == []
        with pytest.raises(Fault) as denied:
            recovered.execution_targets.client(original["id"])
        assert denied.value.code == "CREDENTIAL_REQUIRED"
    finally:
        recovered.close()
    assert service.execution_targets.get(original["id"])["credential_ref"] == original["credential_ref"]
    assert service.execution_targets.get(original["id"])["credential_status"] == "available"


def test_media_material_closure_and_machine_environments_survive_isolated_restore(rig, tmp_path):
    from test_media_flow import media_attempt
    client, service, *_ = rig
    _, attempt, _, original = media_attempt(rig)
    work = post(client, "/works", {"attempt_id": attempt["id"]}, "backup-image-work")
    material = post(client, f"/works/{work['id']}/materials", {}, "backup-image-material")
    source = service.store.get("material", material["id"])
    saved = {"revision": 4, "worker_python": None, "media_python": "/old-machine/media/bin/python", "audio_python": "/old-machine/audio/bin/python"}
    with service.store.transaction():
        service.store.db.execute("INSERT INTO app_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (encode(saved),))
    manager = Backup(service); backup = manager.create()
    plan = plan_restore(rig, manager, backup, tmp_path / "恢复媒体")
    result = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-media")
    restored = Path(result["restored_path"])
    app = create_app(Settings(restored, "restored-media-token"))
    recovered = app.state.service
    try:
        copied = recovered.store.get("material", material["id"])
        verify_manifest(Path(copied["storage_path"]), copied["manifest"])
        assert (Path(copied["storage_path"]) / copied["entrypoint"]).read_bytes() == original
        assert copied["source_work_id"] == work["id"] and copied["source_attempt_id"] == attempt["id"]
        assert copied["storage_path"].startswith(str(restored))
        assert recovered.user_settings["media_python"] is None and recovered.user_settings["audio_python"] is None
        assert recovered.user_settings["revision"] == 5
        fields = {"input_image_path": str(Path(source["storage_path"]) / source["entrypoint"]), "dataset_root_path": source["storage_path"]}
        remapped = backup_module.remap_reference_paths(fields, service.root, restored)
        assert remapped == {"input_image_path": str(Path(copied["storage_path"]) / copied["entrypoint"]), "dataset_root_path": copied["storage_path"]}
    finally:
        recovered.close()
    assert json.loads(service.store.db.execute("SELECT body FROM app_settings WHERE id=1").fetchone()[0]) == saved


def test_complete_restore_reopens_history_exports_adapter_and_runs_again(rig, tmp_path, monkeypatch):
    manager, backup, project, model, trained, adapter = ready_backup(rig)
    client, service, _, environment = rig
    original_rows = service.store.db.execute("SELECT id,body FROM resources ORDER BY id").fetchall()
    original_rows = [tuple(row) for row in original_rows]
    original_snapshot = service.store.get("attempt", trained["id"])["snapshot"]
    original_snapshot_bytes = (service.root / "runs" / trained["id"] / "snapshot.json").read_bytes()
    plan = plan_restore(rig, manager, backup, tmp_path / "恢复 目标")
    payload = {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}
    result = manager.restore(payload, "restore-once")
    assert manager.restore(payload, "restore-once") == result
    assert result["state"] == "succeeded" and not result["changes_current_library"]
    assert [tuple(row) for row in service.store.db.execute("SELECT id,body FROM resources ORDER BY id")] == original_rows
    restored = Path(result["restored_path"])
    assert (restored / "runs" / trained["id"] / "snapshot.json").read_bytes() == original_snapshot_bytes
    settings = Settings(restored, "restore-test-token", [], Path(sys.executable), Path(__file__).with_name("fixture_worker.py"), preflight_script=Path(__file__).with_name("fixture_preflight.py"))
    app = create_app(settings)
    recovered = app.state.service
    monkeypatch.setattr(recovered, "environment", lambda refresh=False: dict(environment))
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer restore-test-token"}) as restored_client:
        history = restored_client.get(f"/api/v1/attempts/{trained['id']}").json()
        assert history["state"] == "succeeded"
        assert history["restoration"]["original_snapshot"] == original_snapshot
        assert history["restoration"]["original_snapshot_digest"] == trained["snapshot_digest"]
        assert history["snapshot_digest"] == digest(history["snapshot"])
        assert history["snapshot"]["model_path"].startswith(str(restored))
        restored_model = recovered.store.get("model", model["id"])
        restored_adapter = recovered.store.get("adapter", adapter["id"])
        for item in (restored_model, restored_adapter):
            assert item["storage_path"].startswith(str(restored))
            verify_manifest(Path(item["storage_path"]), item["manifest"])
        for item in history["output_manifest_ref"]["artifacts"]:
            original_artifact = restored / "runs" / trained["id"] / "output" / item["path"]
            assert file_hash(original_artifact) == item["sha256"]
        restored_rig = (restored_client, recovered, tmp_path, environment)
        export_plan = prepare(restored_rig, "adapter", adapter["id"], project["id"], tmp_path / "restored-export")
        exported, _ = export(restored_rig, export_plan)
        assert exported["state"] == "succeeded"
        task = post(restored_client, "/tasks", {"project_id": project["id"], "name": "恢复后新运行", "kind": "text", "operation": "generate"})
        task["draft"].update(model_id=model["id"], adapter_id=adapter["id"])
        task["draft"]["input"]["prompt"] = "恢复后生成"
        task = restored_client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": 1, "draft": task["draft"]}).json()
        attempt, _ = submit(restored_rig, task, "restored-generate")
        done = wait_attempt(restored_client, attempt["id"])
        assert done["state"] == "succeeded"
        assert done["snapshot"]["model_path"].startswith(str(restored))
        assert done["snapshot"]["adapter_path"].startswith(str(restored))
    assert [tuple(row) for row in service.store.db.execute("SELECT id,body FROM resources ORDER BY id")] == original_rows


@pytest.mark.parametrize("damage", ["missing", "tamper", "symlink", "extra"])
def test_restore_rejects_damaged_package(rig, tmp_path, damage):
    manager, backup, *_ = ready_backup(rig)
    package = Path(backup["backup_path"])
    manifest = json.loads((package / "manifest.json").read_text())
    item = next(record for record in manifest["files"] if record["path"].startswith("assets/"))
    target = package / item["path"]
    if damage == "missing":
        target.unlink()
    elif damage == "tamper":
        target.write_bytes(b"changed")
    elif damage == "symlink":
        target.unlink(); target.symlink_to(tmp_path)
    else:
        (package / "undeclared.txt").write_text("extra")
    with pytest.raises(Fault):
        plan_restore(rig, manager, backup, tmp_path / "target")
    assert not list((tmp_path / "target").iterdir())


def test_backup_refuses_missing_asset_and_live_work(rig, tmp_path):
    client, service, _, _ = rig
    _, model, task = setup_task(rig)
    manager = Backup(service)
    attempt = service.resource("attempt", task["project_id"], state="running")
    with service.store.transaction():
        service.store.put("attempt", attempt)
    with pytest.raises(Fault, match="运行"):
        manager.create()
    with service.store.transaction():
        attempt["state"] = "cancelled"
        service.store.put("attempt", attempt)
    internal = service.store.get("model", model["id"])
    (Path(internal["storage_path"]) / internal["manifest"][0]["path"]).unlink()
    with pytest.raises(Fault):
        manager.create()
    assert not list((service.root / "backups").glob("backup-*"))


def test_restore_rechecks_package_and_never_overwrites_target(rig, tmp_path):
    manager, backup, *_ = ready_backup(rig)
    plan = plan_restore(rig, manager, backup, tmp_path / "target")
    final = Path(plan["restored_path"]); final.mkdir()
    marker = final / "user.txt"; marker.write_text("保留")
    with pytest.raises(Fault) as caught:
        manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore")
    assert caught.value.code == "RESTORE_TARGET_EXISTS" and marker.read_text() == "保留"
    manifest = Path(backup["backup_path"]) / "manifest.json"
    body = json.loads(manifest.read_text()); body["created_at"] = "modified"
    body["manifest_digest"] = digest({k: v for k, v in body.items() if k != "manifest_digest"})
    manifest.write_text(encode(body))
    plan2 = plan_restore(rig, manager, backup, tmp_path / "target2")
    body["created_at"] = "changed-again"
    body["manifest_digest"] = digest({k: v for k, v in body.items() if k != "manifest_digest"})
    manifest.write_text(encode(body))
    with pytest.raises(Fault) as caught:
        manager.restore({"plan_id": plan2["id"], "plan_digest": plan2["plan_digest"]}, "restore2")
    assert caught.value.code == "RESTORE_PLAN_CHANGED"
    assert not Path(plan2["restored_path"]).exists()


def test_restore_failure_preserves_original_and_cleans_partial(rig, tmp_path, monkeypatch):
    manager, backup, *_ = ready_backup(rig)
    plan = plan_restore(rig, manager, backup, tmp_path / "target")
    original = file_hash(rig[1].root / "control.sqlite3")
    def fail_remap(*_):
        raise OSError("fixture disk error")
    monkeypatch.setattr(manager, "remap_database", fail_remap)
    with pytest.raises(Fault) as caught:
        manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "failed-restore")
    assert caught.value.code == "RESTORE_FAILED"
    assert not list((tmp_path / "target").iterdir())
    assert file_hash(rig[1].root / "control.sqlite3") == original


def test_restore_requires_separate_read_and_write_grants(rig, tmp_path):
    manager, backup, *_ = ready_backup(rig)
    target = tmp_path / "target"; target.mkdir()
    with pytest.raises(Fault) as caught:
        manager.plan({"backup_path": backup["backup_path"], "target_dir": str(target)})
    assert caught.value.code == "PATH_NOT_ALLOWED"
    moved = tmp_path / "unapproved-backup"
    shutil.copytree(backup["backup_path"], moved)
    grant = rig[1].delivery.export_grant(str(target))
    with pytest.raises(Fault) as caught:
        manager.plan({"backup_path": str(moved), "target_dir": str(target), "target_grant_id": grant["grant_id"]})
    assert caught.value.code == "PATH_NOT_ALLOWED"


def test_atomic_publish_does_not_replace_existing_empty_directory(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir(); target.mkdir()
    (source / "fixture").write_text("data")
    with pytest.raises(OSError):
        publish(source, target)
    assert source.exists() and target.exists() and not list(target.iterdir())


def test_frozen_evaluation_paths_and_original_report_survive_restore(rig, tmp_path):
    project, model, trained, adapter, frozen = training(rig)
    evaluation, _, _ = evaluate(rig, project, adapter, frozen)
    for thread in list(rig[1].threads):
        thread.join(timeout=2)
    manager = Backup(rig[1]); backup = manager.create()
    plan = plan_restore(rig, manager, backup, tmp_path / "恢复评测")
    restored = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-evaluation")
    app = create_app(Settings(Path(restored["restored_path"]), "restore-evaluation-token"))
    recovered = app.state.service
    try:
        record = recovered.store.get("attempt", evaluation["id"])
        plan_record = recovered.store.get("evaluation-plan", frozen["id"])
        for kind in ("dataset", "criteria"):
            assert record["snapshot"][f"evaluation_{kind}_path"].startswith(restored["restored_path"])
            assert plan_record[f"evaluation_{kind}_path"].startswith(restored["restored_path"])
        report, artifact = recovered.evaluation.report(record)
        assert report == evaluation["report"]
        assert file_hash(Path(artifact["storage_path"])) == artifact["sha256"]
        recovered.evaluation.validate_eligible(record, recovered.store.get("adapter", adapter["id"]))
        assert record["restoration"]["original_snapshot_digest"] == evaluation["snapshot_digest"]
    finally:
        recovered.close()


def test_backup_copy_does_not_block_reads_and_command_survives_restart(rig, monkeypatch):
    client, service, _, _ = rig
    project, _, _ = setup_task(rig)
    manager = Backup(service)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_copy = backup_module.checked_copy
    result = {}
    def paused_copy(*args):
        started.set()
        assert release.wait(timeout=5)
        return original_copy(*args)
    def create():
        try:
            result["backup"] = manager.create("stable-backup-command")
        except Exception as error:
            result["error"] = error
        finally:
            finished.set()
    monkeypatch.setattr(backup_module, "checked_copy", paused_copy)
    thread = threading.Thread(target=create); thread.start()
    try:
        assert started.wait(timeout=5)
        read_finished = threading.Event()
        reader = threading.Thread(target=lambda: (service.store.list("project"), read_finished.set()))
        reader.start()
        assert read_finished.wait(timeout=1), "复制期间不应占用数据库读取锁"
        blocked = client.post("/api/v1/projects", json={"name": "冻结快照期间的新项目"})
        assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CLEANUP_BUSY"
    finally:
        release.set(); thread.join(timeout=5)
    assert finished.is_set() and "error" not in result
    assert not service.maintenance_pending
    post(client, "/projects", {"name": "备份发布之后的新项目"})
    backup = result["backup"]
    reopened = Backup(service)
    assert reopened.create("stable-backup-command")["backup_path"] == backup["backup_path"]
    assert len(reopened.list_backups()["items"]) == 1
    resources = backup_module.database(Path(backup["backup_path"]) / "control.sqlite3")
    assert all(body["project_id"] == project["id"] for _, body in resources)


def test_restore_after_publish_crash_replays_same_directory_without_grants(rig, tmp_path, monkeypatch):
    manager, backup, *_ = ready_backup(rig)
    plan = plan_restore(rig, manager, backup, tmp_path / "target")
    payload = {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}
    def crash_after_publish(*_):
        raise OSError("响应前模拟服务崩溃")
    monkeypatch.setattr(manager, "get_restore", crash_after_publish)
    with pytest.raises(Fault) as caught:
        manager.restore(payload, "stable-restore")
    assert caught.value.code == "RESTORE_FAILED" and Path(plan["restored_path"]).is_dir()
    rig[1].grants.clear(); rig[1].delivery.export_grants.clear()
    reopened = Backup(rig[1])
    response = reopened.restore(payload, "stable-restore")
    assert response["state"] == "succeeded" and response["verified"]
    assert response["restored_path"] == plan["restored_path"]
    assert len(list((tmp_path / "target").iterdir())) == 1
    assert len(reopened.list_restores()["items"]) == 1
    with pytest.raises(Fault) as conflict:
        reopened.restore({**payload, "plan_digest": "0" * 64}, "stable-restore")
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


def test_self_consistent_manifest_cannot_omit_database_reference(rig, tmp_path):
    manager, backup, *_ = ready_backup(rig)
    package = Path(backup["backup_path"])
    manifest = json.loads((package / "manifest.json").read_text())
    entry = next(item for item in manifest["files"] if item["path"].startswith("assets/"))
    manifest["files"].remove(entry)
    (package / entry["path"]).unlink()
    manifest["manifest_digest"] = digest({key: value for key, value in manifest.items() if key != "manifest_digest"})
    (package / "manifest.json").write_text(encode(manifest))
    with pytest.raises(Fault) as error:
        plan_restore(rig, manager, backup, tmp_path / "target")
    assert error.value.code == "BACKUP_REFERENCE_MISSING"


def test_manifest_path_traversal_is_rejected_before_read(rig, tmp_path):
    manager, backup, *_ = ready_backup(rig)
    package = Path(backup["backup_path"])
    manifest = json.loads((package / "manifest.json").read_text())
    manifest["files"][0]["path"] = "../outside"
    manifest["manifest_digest"] = digest({key: value for key, value in manifest.items() if key != "manifest_digest"})
    (package / "manifest.json").write_text(encode(manifest))
    with pytest.raises(Fault) as error:
        plan_restore(rig, manager, backup, tmp_path / "target")
    assert error.value.code == "BACKUP_INVALID"


@pytest.mark.parametrize('version', [True, 1.0, 99])
def test_backup_schema_version_requires_supported_exact_integer(rig, version):
    _, service, *_ = rig
    manager=Backup(service); result=manager.create('strict-schema')
    directory=Path(result['backup_path']); manifest=json.loads((directory/'manifest.json').read_text())
    manifest['database_schema_version']=version
    manifest['manifest_digest']=digest({k:v for k,v in manifest.items() if k!='manifest_digest'})
    (directory/'manifest.json').write_text(encode(manifest))
    with pytest.raises(Fault): manager.verify(directory)


def test_backup_schema_manifest_must_match_actual_database(rig):
    _, service, *_=rig
    manager=Backup(service);result=manager.create('matching-schema')
    directory=Path(result['backup_path']);manifest=json.loads((directory/'manifest.json').read_text())
    _, version=backup_module.database(directory/'control.sqlite3',with_version=True)
    assert manifest['database_schema_version']==version
    manifest['database_schema_version']=2 if version==1 else 1
    manifest['manifest_digest']=digest({k:v for k,v in manifest.items() if k!='manifest_digest'})
    (directory/'manifest.json').write_text(encode(manifest))
    with pytest.raises(Fault): manager.verify(directory)
