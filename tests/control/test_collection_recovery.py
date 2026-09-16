"""人工补收进程崩溃：真实 SQLite／文件与 SIGKILL，不运行模型。"""

import os
import select
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from test_control import ROOT, rig, submit, wait_attempt
from test_collection_finalization import (
    collection_run, fail_first_copy, retry_payload, terminal_identity,
    assert_recovered_and_reopened, events,
)
import ailab_control.service as service_module
from ailab_control.service import Service


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
@pytest.mark.parametrize("phase", ["copy", "registration", "committed"])
def test_recollection_sigkill_restart_preserves_terminal_and_allows_retry(collection_run, monkeypatch, terminal, phase):
    rig, task, calls = collection_run
    client, service, _, _ = rig
    if terminal == "failed":
        fail_first_copy(monkeypatch)
    else:
        original_copy = service_module.copy_asset
        cancelled = []

        def cancel_during_copy(source, *args, **kwargs):
            if source.name == "result.txt" and not cancelled:
                current = service.store.list("attempt")[0]
                cancelled.append(service.control(current["id"], {"expected_state_version": current["state_version"]}, "cancel-initial"))
            return original_copy(source, *args, **kwargs)

        monkeypatch.setattr(service_module, "copy_asset", cancel_during_copy)
    submitted, _ = submit(rig, task)
    wait_attempt(client, submitted["id"])
    before = service.store.get("attempt", submitted["id"])
    assert before["state"] == terminal and before["compute_outcome"] == "succeeded"
    before_events = events(service, before["id"])
    manifest = before["output_manifest_ref"]
    run_files = {str(p.relative_to(service.root)): p.read_bytes() for p in (service.root / "runs").rglob("*") if p.is_file()}
    service.close()
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "services/control"))
    with (service.root.parent / "recollection-child.log").open("wb") as error_log:
        child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).with_name("fixture_recollection_crash.py")),
                                  str(service.root), before["id"], phase],
                                 stdout=subprocess.PIPE, stderr=error_log, env=environment)
        try:
            assert select.select([child.stdout], [], [], 10)[0], "子进程未到达补收边界"
            assert child.stdout.readline() == b"recollection-boundary\n"
            child.kill()
            assert child.wait(timeout=10) == -signal.SIGKILL
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            child.stdout.close()
    reopened = Service(service.settings)
    try:
        after = reopened.store.get("attempt", before["id"])
        assert terminal_identity(after) == terminal_identity(before)
        assert after["output_manifest_ref"] == manifest
        assert {str(p.relative_to(service.root)): p.read_bytes() for p in (service.root / "runs").rglob("*") if p.is_file()} == run_files
        assert events(reopened, before["id"])[:len(before_events)] == before_events
        if phase == "committed":
            assert after["collection_state"] == "succeeded"
            receipt = reopened.collect(before["id"], retry_payload(before), "interrupted-recollection")
            assert receipt["state"] == "succeeded" and len(reopened.store.list("artifact")) == 1
            assert not any(c.get("error", {}).get("code") == "COLLECTION_INTERRUPTED" for c in reopened.store.list("collection") if c.get("error"))
        else:
            assert after["collection_state"] == "failed"
            assert after["collection_version"] == before["collection_version"] + 2
            assert not reopened.store.list("artifact")
            interrupted = reopened.store.list("collection")[-1]
            assert interrupted["state"] == "failed" and interrupted["error"]["code"] == "COLLECTION_INTERRUPTED"
            assert interrupted["registered_artifact_ids"] == []
            assert reopened.store.replay(f"collect:{before['id']}", "interrupted-recollection", retry_payload(before)) is None
            assert not any(e["type"] == "collection_changed" and e["payload"]["state"] == "succeeded" for e in events(reopened, before["id"]))
            recovered_events = events(reopened, before["id"])
            reopened.close()
            reopened = Service(service.settings)
            assert reopened.store.get("attempt", before["id"]) == after
            assert events(reopened, before["id"]) == recovered_events
            assert_recovered_and_reopened(reopened, after, calls)
    finally:
        reopened.close()
    assert calls == {"run": 1, "resume": 0}


def test_registration_and_cleanup_storage_failures_recover_after_restart(collection_run, monkeypatch):
    rig, task, calls = collection_run
    client, service, _, _ = rig
    fail_first_copy(monkeypatch)
    submitted, _ = submit(rig, task)
    wait_attempt(client, submitted["id"])
    before = service.store.get("attempt", submitted["id"])
    original_event = service.store.event
    faults = []

    def event(attempt, kind, payload):
        result = original_event(attempt, kind, payload)
        if kind == "collection_changed" and payload["state"] in {"succeeded", "failed"}:
            error = sqlite3.OperationalError("受控持续写盘失败：" + payload["state"])
            faults.append(error)
            raise error
        return result

    monkeypatch.setattr(service.store, "event", event)
    with pytest.raises(sqlite3.OperationalError) as error:
        service.collect(before["id"], retry_payload(before), "failed-compensation")
    assert len(faults) == 2 and error.value is faults[0]
    assert service.store.get("attempt", before["id"])["collection_state"] == "collecting"
    assert not service.store.list("artifact")
    service.close()
    reopened = Service(service.settings)
    try:
        recovered = reopened.store.get("attempt", before["id"])
        assert recovered["collection_state"] == "failed"
        assert terminal_identity(recovered) == terminal_identity(before)
        assert_recovered_and_reopened(reopened, recovered, calls)
    finally:
        reopened.close()


@pytest.mark.parametrize("ownership", ["remote_local_registration", "wrong_manifest", "wrong_project", "ambiguous"])
def test_recovery_requires_unambiguous_local_registration_owner(collection_run, monkeypatch, ownership):
    """合成登记边界只验证归属防护；远端字段不代表真实远端设备。"""
    rig, task, calls = collection_run
    client, service, _, _ = rig
    fail_first_copy(monkeypatch)
    submitted, _ = submit(rig, task)
    wait_attempt(client, submitted["id"])
    other = service.project({"name": "另一归属项目"}) if ownership == "wrong_project" else None
    with service.store.transaction():
        attempt = service.store.get("attempt", submitted["id"])
        attempt.update(collection_state="collecting", collection_version=attempt["collection_version"] + 1)
        if ownership == "remote_local_registration":
            attempt.update(executor_type="remote", remote_event_cursor=37, remote_submitted=True,
                           remote_attempt_id="frozen-remote-attempt", connection_state="disconnected")
        collection = service.resource("collection", attempt["project_id"], attempt_id=attempt["id"], state="collecting",
                                      manifest_digest=attempt["output_manifest_ref"]["digest"], error=None, registered_artifact_ids=[])
        if ownership == "wrong_manifest":
            collection["manifest_digest"] = "0" * 64
        if ownership == "wrong_project":
            collection["project_id"] = other["id"]
        service.store.put("collection", collection)
        if ownership == "ambiguous":
            service.store.put("collection", dict(collection, id="duplicate-collection"))
        service.store.put("attempt", attempt)
    prior_events = events(service, attempt["id"])
    service.close()

    def forbidden(*args, **kwargs):
        raise AssertionError("启动恢复不得执行或访问远端")

    from ailab_control.execution_targets import ExecutionTargets
    monkeypatch.setattr(ExecutionTargets, "client", forbidden)
    monkeypatch.setattr(Service, "run", forbidden)
    reopened = Service(service.settings)
    try:
        after = reopened.store.get("attempt", attempt["id"])
        if ownership == "remote_local_registration":
            assert after["collection_state"] == "failed"
            changed = {key for key in after if after[key] != attempt[key]}
            assert changed == {"collection_state", "collection_version", "last_event_sequence"}
            assert reopened.store.get("collection", collection["id"])["error"]["code"] == "COLLECTION_INTERRUPTED"
            assert events(reopened, attempt["id"])[:-1] == prior_events
        else:
            assert after == attempt
            assert reopened.store.get("collection", collection["id"]) == collection
            assert events(reopened, attempt["id"]) == prior_events
        assert not reopened.store.list("artifact")
        assert len(reopened.store.list("attempt")) == 1
    finally:
        reopened.close()
    assert calls == {"run": 1, "resume": 0}
