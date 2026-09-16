"""M1 收尾合同：真实临时 SQLite／文件／显式假执行器，不加载真实模型。"""

import errno
import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from test_control import rig, setup_task, submit, wait_attempt
import ailab_control.service as service_module
from ailab_control.service import Service
from ailab_control.storage import Fault


@pytest.fixture
def collection_run(rig, monkeypatch):
    _, service, _, _ = rig
    _, _, task = setup_task(rig)
    calls = {"run": 0, "resume": 0}
    original_run = service.run
    original_command = service.checkpoints.command

    def run(*args, **kwargs):
        calls["run"] += 1
        return original_run(*args, **kwargs)

    def command(attempt_id, payload, key, action):
        if action == "resume":
            calls["resume"] += 1
        return original_command(attempt_id, payload, key, action)

    monkeypatch.setattr(service, "run", run)
    monkeypatch.setattr(service.checkpoints, "command", command)
    return rig, task, calls


def terminal_identity(attempt):
    return tuple(attempt[key] for key in ("state", "state_version", "terminal_reason", "finished_at"))


def events(service, attempt_id):
    return service.store.events(attempt_id, 0, 1000)["items"]


def retry_payload(attempt):
    return {"manifest_digest": attempt["output_manifest_ref"]["digest"],
            "expected_collection_version": attempt["collection_version"]}


def assert_recovered_and_reopened(service, before, calls):
    """补收、重放、保存作品及重开，均绑定原计算与精确字节。"""
    original = terminal_identity(before)
    manifest = before["output_manifest_ref"]
    output = service.root / "runs" / before["id"] / "output" / "result.txt"
    raw = output.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert manifest["artifacts"][0]["sha256"] == digest
    payload = retry_payload(before)
    receipt = service.collect(before["id"], payload, "recollect-once")
    assert receipt["state"] == "succeeded"
    after = service.store.get("attempt", before["id"])
    after_events = events(service, before["id"])
    assert sum(item["type"] == "collection_changed" and item["payload"]["state"] == "succeeded" for item in after_events) == 1
    assert sum(item["type"] == "terminal" for item in after_events) == 1
    assert service.collect(before["id"], payload, "recollect-once") == receipt
    assert events(service, before["id"]) == after_events
    assert terminal_identity(after) == original
    assert after["collection_state"] == "succeeded"
    assert after["output_manifest_ref"] == manifest and output.read_bytes() == raw
    artifacts = service.store.list("artifact")
    assert len(artifacts) == 1
    assert artifacts[0]["sha256"] == digest
    assert Path(artifacts[0]["storage_path"]).read_bytes() == raw
    assert calls == {"run": 1, "resume": 0}
    assert len(service.store.list("attempt")) == len(list((service.root / "runs").iterdir())) == 1
    work_payload = {"attempt_id": before["id"], "name": "只补收后保存"}
    work = service.save_work(work_payload, "save-once")
    assert service.save_work(work_payload, "save-once") == work
    service.close()
    reopened = Service(service.settings)
    try:
        persisted = reopened.store.get("attempt", before["id"])
        assert persisted == after
        assert terminal_identity(persisted) == original
        assert reopened.store.get("work", work["id"])["artifact_id"] == artifacts[0]["id"]
        assert reopened.collect(before["id"], payload, "recollect-once") == receipt
        assert reopened.store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()
    assert calls == {"run": 1, "resume": 0}


def fail_first_copy(monkeypatch):
    original = service_module.copy_asset
    failures = []

    def copy(source, *args, **kwargs):
        if source.name == "result.txt" and not failures:
            failures.append(str(source))
            raise OSError(errno.ENOSPC, "受控测试：收集目标磁盘不足")
        return original(source, *args, **kwargs)

    monkeypatch.setattr(service_module, "copy_asset", copy)
    return failures


def fail_first_registration(service, monkeypatch):
    """先写入真实 artifact 与成功事件，再使整个登记事务回滚。"""
    original = service.store.event
    failures = []

    def event(attempt, kind, payload):
        result = original(attempt, kind, payload)
        if kind == "collection_changed" and payload["state"] == "succeeded" and not failures:
            assert service.store.list("artifact"), "故障须发生在真实 artifact INSERT 之后"
            failures.append(attempt["id"])
            raise sqlite3.OperationalError("受控测试：产物登记事务失败")
        return result

    monkeypatch.setattr(service.store, "event", event)
    return failures


def test_finalizing_cancel_commits_first_then_only_collects(collection_run, monkeypatch):
    rig, task, calls = collection_run
    client, service, _, _ = rig
    entered, release = threading.Event(), threading.Event()
    original_copy = service_module.copy_asset

    def copy(source, *args, **kwargs):
        if source.name == "result.txt" and not entered.is_set():
            entered.set()
            assert release.wait(8), "取消裁决未释放收集屏障"
        return original_copy(source, *args, **kwargs)

    monkeypatch.setattr(service_module, "copy_asset", copy)
    try:
        submitted, _ = submit(rig, task)
        assert entered.wait(8)
        current = service.store.get("attempt", submitted["id"])
        assert current["state"] == "finalizing" and current["compute_outcome"] == "succeeded"
        payload = {"expected_state_version": current["state_version"]}
        cancel = service.control(current["id"], payload, "cancel-first")
        assert cancel["result"] == "accepted" and cancel["state"] == "cancelling"
        assert service.control(current["id"], payload, "cancel-first") == cancel
    finally:
        release.set()
    done = wait_attempt(client, current["id"])
    assert done["state"] == "cancelled" and done["terminal_reason"] == "COLLECTION_CANCELLED"
    assert done["compute_outcome"] == "succeeded" and done["stop_status"] == "confirmed"
    assert not service.store.list("artifact")
    assert [item["state"] for item in service.store.list("collection")] == ["cancelled"]
    assert not any(item["type"] == "terminal" and item["payload"].get("state") == "succeeded" for item in events(service, done["id"]))
    assert_recovered_and_reopened(service, service.store.get("attempt", done["id"]), calls)


def test_finalizing_registration_commits_first_rejects_stale_cancel(collection_run, monkeypatch):
    rig, task, calls = collection_run
    client, service, _, _ = rig
    entered, release, cancel_started = threading.Event(), threading.Event(), threading.Event()
    original_put = service.store.put
    submitted_id = []

    def put(kind, value):
        result = original_put(kind, value)
        if kind == "artifact":
            submitted_id.append(value["attempt_id"])
            entered.set()
            assert release.wait(8), "成功提交屏障未释放"
        return result

    monkeypatch.setattr(service.store, "put", put)
    # 取版本的时机必须在登记事务取得锁之前，不能在屏障内读 Store。
    version = []
    original_collect = service.collect

    def collect(attempt_id, *args, **kwargs):
        version.append(service.store.get("attempt", attempt_id)["state_version"])
        return original_collect(attempt_id, *args, **kwargs)

    monkeypatch.setattr(service, "collect", collect)
    def late_cancel():
        cancel_started.set()
        return service.control(submitted_id[0], {"expected_state_version": version[0]}, "late-cancel")

    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            # submit 的回执可等待同一 Store 锁；此处直接创建提交工作线程。
            submitting = pool.submit(submit, rig, task)
            assert entered.wait(8)
            future = pool.submit(late_cancel)
            assert cancel_started.wait(8)
        finally:
            release.set()
        with pytest.raises(Fault) as conflict:
            future.result(timeout=8)
        assert conflict.value.code == "REVISION_CONFLICT"
        submitted, _ = submitting.result(timeout=8)
        assert submitted["id"] == submitted_id[0]
    done = wait_attempt(client, submitted_id[0])
    assert done["state"] == "succeeded"
    original = terminal_identity(done)
    payload = {"expected_state_version": done["state_version"]}
    result = service.control(done["id"], payload, "after-success")
    assert result["result"] == "not_applicable"
    assert service.control(done["id"], payload, "after-success") == result
    assert terminal_identity(service.store.get("attempt", done["id"])) == original
    assert len(service.store.list("artifact")) == len(service.store.list("collection")) == 1
    assert calls == {"run": 1, "resume": 0}


@pytest.mark.parametrize("failure", ["disk_full", "registration_rollback"])
def test_initial_collection_failure_can_recollect_without_reexecution(collection_run, monkeypatch, failure):
    rig, task, calls = collection_run
    client, service, _, _ = rig
    failures = fail_first_copy(monkeypatch) if failure == "disk_full" else fail_first_registration(service, monkeypatch)
    attempt, _ = submit(rig, task)
    done = wait_attempt(client, attempt["id"])
    assert failures
    assert done["state"] == "failed" and done["compute_outcome"] == "succeeded"
    assert done["collection_state"] == "failed"
    assert not service.store.list("artifact")
    assert not any(item["type"] == "collection_changed" and item["payload"]["state"] == "succeeded" for item in events(service, done["id"]))
    assert_recovered_and_reopened(service, service.store.get("attempt", done["id"]), calls)


def test_recollection_registration_rollback_remains_retryable(collection_run, monkeypatch):
    rig, task, calls = collection_run
    client, service, _, _ = rig
    fail_first_copy(monkeypatch)
    attempt, _ = submit(rig, task)
    done = wait_attempt(client, attempt["id"])
    before = service.store.get("attempt", done["id"])
    assert before["state"] == "failed" and before["compute_outcome"] == "succeeded"
    failures = fail_first_registration(service, monkeypatch)
    with pytest.raises(sqlite3.OperationalError, match="登记事务失败"):
        service.collect(done["id"], retry_payload(before), "failed-recollection")
    assert failures == [done["id"]]
    after = service.store.get("attempt", done["id"])
    assert terminal_identity(after) == terminal_identity(before)
    assert not service.store.list("artifact")
    assert not any(item["type"] == "collection_changed" and item["payload"]["state"] == "succeeded" for item in events(service, done["id"]))
    assert calls == {"run": 1, "resume": 0}
    assert service.store.db.execute("SELECT COUNT(*) FROM commands WHERE scope=? AND key=?", (f"collect:{done['id']}", "failed-recollection")).fetchone()[0] == 0
    # 故障撤去后按当前版本重试，不能因前一收集记录而永久卡在 collecting。
    assert_recovered_and_reopened(service, after, calls)


def test_cancel_after_registration_rollback_wins_failure_cleanup(collection_run, monkeypatch):
    rig, task, calls = collection_run
    client, service, _, _ = rig
    rolled_back, release = threading.Event(), threading.Event()
    original_transaction = service.store.transaction
    fail_first_registration(service, monkeypatch)

    @contextmanager
    def transaction():
        try:
            with original_transaction():
                yield
        except sqlite3.OperationalError as error:
            if "登记事务失败" in str(error) and not rolled_back.is_set():
                # 原 transaction 已释放锁且真实回滚；允许取消先提交，再作失败收尾。
                rolled_back.set()
                assert release.wait(8), "取消未释放登记回滚屏障"
            raise

    monkeypatch.setattr(service.store, "transaction", transaction)
    try:
        attempt, _ = submit(rig, task)
        assert rolled_back.wait(8)
        current = service.store.get("attempt", attempt["id"])
        assert current["state"] == "finalizing" and current["collection_state"] == "collecting"
        result = service.control(current["id"], {"expected_state_version": current["state_version"]}, "cancel-after-rollback")
        assert result["result"] == "accepted" and result["state"] == "cancelling"
    finally:
        release.set()
    done = wait_attempt(client, current["id"])
    assert done["state"] == "cancelled" and done["terminal_reason"] == "COLLECTION_CANCELLED"
    assert done["stop_status"] == "confirmed" and done["compute_outcome"] == "succeeded"
    assert done["collection_state"] == "failed"
    assert [item["state"] for item in service.store.list("collection")] == ["failed"]
    assert not service.store.list("artifact")
    assert_recovered_and_reopened(service, service.store.get("attempt", done["id"]), calls)
