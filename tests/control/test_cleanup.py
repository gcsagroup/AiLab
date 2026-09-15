"""小文件代表性清理与恢复；仅使用隔离测试库，不清理用户资产。"""

import json
from pathlib import Path
import threading

import pytest

from test_control import rig, setup_task
from ailab_control.cleanup import Cleanup
import ailab_control.cleanup as module
from ailab_control.storage import Fault, digest


def orphan(service, name="orphan", content="可恢复的小文件".encode()):
    directory = service.root / "assets" / digest(name)
    directory.mkdir()
    file = directory / "payload.bin"; file.write_bytes(content); file.chmod(0o400)
    return directory


def request(plan):
    return {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}


def test_plan_move_and_restore_preserve_referenced_assets_and_original_bytes(rig):
    _, service, *_ = rig
    _, model, _ = setup_task(rig)
    referenced = Path(service.store.get("model", model["id"])["storage_path"])
    candidate = orphan(service)
    original = (candidate / "payload.bin").read_bytes()
    manager = Cleanup(service); plan = manager.plan({})
    assert plan["asset_count"] == 1 and plan["retained_asset_count"] == 1
    assert plan["items"][0]["source_path"] == str(candidate)
    assert plan["total_bytes"] == len(original) and not plan["permanent_delete"]
    moved = manager.execute(request(plan), "one-cleanup")
    assert moved["state"] == "trashed" and moved["can_restore"]
    trash = Path(moved["items"][0]["trash_path"])
    assert not candidate.exists() and (trash / "payload.bin").read_bytes() == original
    assert referenced.exists() and manager.execute(request(plan), "one-cleanup") == moved
    restored = Cleanup(service).restore(moved["id"], {}, "one-restore")
    assert restored["state"] == "restored" and not trash.exists()
    assert (candidate / "payload.bin").read_bytes() == original
    assert manager.restore(moved["id"], {}, "one-restore") == restored
    assert manager.list_items()["items"][0]["state"] == "restored"


@pytest.mark.parametrize("change", ["reference", "bytes", "inode", "new_file"])
def test_plan_rejects_new_references_and_changed_files(rig, change):
    _, service, *_ = rig
    project, _, _ = setup_task(rig)
    candidate = orphan(service)
    manager = Cleanup(service); plan = manager.plan()
    path = candidate / "payload.bin"
    if change == "reference":
        value = service.resource("historical-reference", project["id"], snapshot={"checkpoint_ref": {"path": str(path)}})
        with service.store.transaction(): service.store.put("historical-reference", value)
    elif change == "bytes":
        path.chmod(0o600); path.write_bytes(b"changed"); path.chmod(0o400)
    elif change == "inode":
        content = path.read_bytes(); path.unlink(); path.write_bytes(content); path.chmod(0o400)
    else:
        extra = candidate / "extra"; extra.write_bytes(b"new"); extra.chmod(0o400)
    with pytest.raises(Fault) as caught:
        manager.execute(request(plan), "changed")
    assert caught.value.code in {"CLEANUP_REFERENCE_CHANGED", "CLEANUP_ASSET_CHANGED"}
    assert candidate.exists() and not list((manager.trash / "items").iterdir())


def test_only_managed_regular_immutable_directories_are_candidates(rig, tmp_path):
    service = rig[1]
    good = orphan(service)
    writable = orphan(service, "writable"); (writable / "payload.bin").chmod(0o600)
    symlink = service.root / "assets" / digest("symlink"); symlink.symlink_to(tmp_path, target_is_directory=True)
    hard = orphan(service, "hardlink"); (tmp_path / "linked").hardlink_to(hard / "payload.bin")
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "file").write_bytes(b"keep")
    (service.root / "assets/not-a-managed-id").mkdir()
    (service.root / "runs/old-evidence").mkdir()
    plan = Cleanup(service).plan()
    assert [item["source_path"] for item in plan["items"]] == [str(good)]
    assert len(plan["skipped"]) == 3 and outside.exists()
    assert (service.root / "runs/old-evidence").exists()


def test_backup_and_restoration_references_are_retained(rig):
    service = rig[1]
    candidate = orphan(service)
    backup = service.root / "backups/backup-fixture"; backup.mkdir()
    (backup / "manifest.json").write_text(json.dumps({"source_data_root": str(service.root), "files": [{"path": f"assets/{candidate.name}/payload.bin"}]}))
    assert Cleanup(service).plan()["asset_count"] == 0
    (backup / "manifest.json").unlink()
    (service.root / "restoration.json").write_text(json.dumps({"original_evidence_files": [{"path": f"assets/{candidate.name}/payload.bin"}]}))
    assert Cleanup(service).plan()["asset_count"] == 0


@pytest.mark.parametrize("busy", ["run", "activation", "backup", "writes"])
def test_cleanup_refuses_active_work(rig, busy):
    _, service, *_ = rig
    project, _, _ = setup_task(rig)
    candidate = orphan(service)
    manager = Cleanup(service)
    if busy == "run":
        value = service.resource("attempt", project["id"], state="running")
        with service.store.transaction(): service.store.put("attempt", value)
    elif busy == "activation": service.activation_pending = True
    elif busy == "writes": service.active_writes = 2
    else: service.backup_manager.lock.acquire()
    try:
        with pytest.raises(Fault) as caught: manager.plan()
        assert caught.value.code == "CLEANUP_BUSY" and candidate.exists()
    finally:
        service.activation_pending = False; service.active_writes = 0
        if busy == "backup": service.backup_manager.lock.release()
        if busy == "run":
            with service.store.transaction():
                value["state"] = "cancelled"; service.store.put("attempt", value)


def test_restore_rejects_occupied_original_location(rig):
    service = rig[1]; candidate = orphan(service)
    manager = Cleanup(service); moved = manager.execute(request(manager.plan()), "move")
    candidate.mkdir(); marker = candidate / "new-user-file"; marker.write_bytes(b"keep")
    with pytest.raises(Fault) as caught: manager.restore(moved["id"], {}, "restore")
    assert caught.value.code == "CLEANUP_TARGET_EXISTS" and marker.read_bytes() == b"keep"
    assert (Path(moved["items"][0]["trash_path"]) / "payload.bin").exists()


class SimulatedCrash(BaseException):
    pass


@pytest.mark.parametrize("during_restore", [False, True])
def test_crash_after_atomic_move_replays_without_duplicate_or_lost_assets(rig, monkeypatch, during_restore):
    service = rig[1]; candidates = [orphan(service, "one"), orphan(service, "two")]
    manager = Cleanup(service); payload = request(manager.plan())
    moved = manager.execute(payload, "move") if during_restore else None
    real_publish = module.publish
    def crash(source, target):
        real_publish(source, target)
        raise SimulatedCrash()
    monkeypatch.setattr(module, "publish", crash)
    with pytest.raises(SimulatedCrash):
        if during_restore: manager.restore(moved["id"], {}, "restore")
        else: manager.execute(payload, "move")
    assert not service.maintenance_pending and not service.backup_manager.lock.locked()
    monkeypatch.setattr(module, "publish", real_publish)
    second = Cleanup(service)
    if during_restore:
        result = second.restore(moved["id"], {}, "restore")
        assert result["state"] == "restored" and all(path.exists() for path in candidates)
    else:
        result = second.execute(payload, "move")
        assert result["state"] == "trashed" and all(not path.exists() for path in candidates)
    for item in result["items"]:
        assert Path(item["source_path"]).exists() != Path(item["trash_path"]).exists()


def test_hashing_happens_outside_database_lock_and_reads_remain_available(rig, monkeypatch):
    service = rig[1]; orphan(service)
    manager = Cleanup(service); payload = request(manager.plan())
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    real = module.file_hash
    errors = []
    def blocked_hash(path):
        assert not service.store.lock._is_owned()
        entered.set(); assert release.wait(timeout=5)
        return real(path)
    monkeypatch.setattr(module, "file_hash", blocked_hash)
    def execute():
        try: manager.execute(payload, "hash-lock")
        except Exception as error: errors.append(error)
        finally: done.set()
    worker = threading.Thread(target=execute); worker.start()
    try:
        assert entered.wait(timeout=5) and service.maintenance_pending
        assert rig[0].get("/api/v1/projects").status_code == 200
        rejected = rig[0].post("/api/v1/projects", json={"name": "维护期间不能新增"})
        assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "CLEANUP_BUSY"
    finally:
        release.set(); worker.join(timeout=5)
    assert done.is_set() and not errors and not service.maintenance_pending


def test_http_plan_confirmation_restore_and_idempotency_contract(rig):
    client, service, *_ = rig
    candidate = orphan(service)
    plan_response = client.post("/api/v1/cleanup-plans", json={})
    assert plan_response.status_code == 200, plan_response.text
    plan = plan_response.json()
    assert plan["requires_confirmation"] and candidate.exists()
    assert "files" not in plan["items"][0] and "reference_digest" not in plan
    rejected = client.post("/api/v1/cleanups", json=request(plan))
    assert rejected.status_code == 409 and candidate.exists()
    response = client.post("/api/v1/cleanups", json=request(plan), headers={"Idempotency-Key": "http-move"})
    assert response.status_code == 200, response.text
    moved = response.json()
    assert moved["state"] == "trashed" and not candidate.exists()
    listing = client.get("/api/v1/cleanups").json()
    assert listing["items"] == [moved] and listing["unreadable_records"] == []
    assert client.get(f"/api/v1/cleanups/{moved['id']}").json() == moved
    restored = client.post(f"/api/v1/cleanups/{moved['id']}/restore", json={}, headers={"Idempotency-Key": "http-restore"})
    assert restored.status_code == 200, restored.text
    assert restored.json()["state"] == "restored" and candidate.exists()
    conflicting = client.post(f"/api/v1/cleanups/{moved['id']}/restore", json={}, headers={"Idempotency-Key": "different-restore"})
    assert conflicting.status_code == 409


@pytest.mark.parametrize("damage", ["list", "digest", "outside", "parent", "syntax"])
def test_corrupt_cleanup_records_never_move_files(rig, tmp_path, damage):
    service = rig[1]; candidate = orphan(service)
    manager = Cleanup(service); moved = manager.execute(request(manager.plan()), "move")
    record_path = manager.trash / "records" / (moved["id"] + ".json")
    value = json.loads(record_path.read_text())
    if damage == "list": value = []
    elif damage == "digest": value["state"] = "restored"
    elif damage == "outside":
        value["items"][0]["source_path"] = str(tmp_path / "outside")
        value["record_digest"] = digest({key: item for key, item in value.items() if key != "record_digest"})
    elif damage == "parent":
        plan_path = manager.trash / "plans" / (value["plan_id"] + ".json")
        plan = json.loads(plan_path.read_text()); plan["items"][0]["signatures"]["../outside"] = plan["items"][0]["signatures"]["."]
        plan["plan_digest"] = digest({key: item for key, item in plan.items() if key != "plan_digest"})
        plan_path.write_text(json.dumps(plan))
    record_path.write_text("{broken" if damage == "syntax" else json.dumps(value))
    with pytest.raises(Fault): manager.restore(moved["id"], {}, "restore")
    assert not candidate.exists() and Path(moved["items"][0]["trash_path"]).exists()
    assert manager.list_items() == {"items": [], "unreadable_records": [str(record_path)]}


def test_filesystem_failure_keeps_record_for_explicit_retry(rig, monkeypatch):
    service = rig[1]; candidate = orphan(service)
    manager = Cleanup(service); payload = request(manager.plan())
    real = module.publish
    def unavailable(source, target): raise OSError("fixture unavailable")
    monkeypatch.setattr(module, "publish", unavailable)
    with pytest.raises(Fault) as caught: manager.execute(payload, "io-error")
    assert caught.value.code == "CLEANUP_IO_ERROR" and candidate.exists()
    assert manager.list_items()["items"][0]["can_restore"]
    monkeypatch.setattr(module, "publish", real)
    assert manager.execute(payload, "io-error")["state"] == "trashed"
