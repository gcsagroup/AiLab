"""训练检查点 HTTP、文件与竞争合同；夹具不代表真实训练可恢复证据。"""

import copy
import json
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_control import rig, post, setup_task
from ailab_control.assets import file_hash
from ailab_control.checkpoints import compatibility
from ailab_control.storage import digest


class ExitedFixtureProcess:
    pid = 999999999

    def poll(self): return 0
    def wait(self, **kwargs): return 0


@pytest.fixture
def training_run(rig):
    client, service, source, environment = rig
    environment.update(versions={"dependencies": {"mlx": "fixture-mlx", "mlx-lm": "fixture-lm"}}, identity={"adapter_sources": {"/fixed/workers/mlx_worker.py": "a" * 64, "/fixed/adapters/checkpoint.py": "b" * 64, "/fixed/adapters/recipe.py": "c" * 64}})
    project, model, task = setup_task(rig, "", "train")
    data = source / "checkpoint-data.jsonl"
    data.write_text(json.dumps({"messages": [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "答案"}]}) + "\n")
    plan = post(client, "/datasets/import-plans", {"project_id": project["id"], "path": str(data), "schema": "sft"})
    dataset = post(client, "/datasets/imports", {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}, "checkpoint-data")
    with service.store.transaction():
        attempt = service.resource("attempt", project["id"], task_id=task["id"], state="running", state_version=1, connection_state="connected", stop_status="not_requested", compute_outcome="pending", collection_state="not_started", collection_version=0, output_manifest_ref=None, last_event_sequence=0, phase="training", output_text="")
        snapshot = {**task["draft"], "attempt_id": attempt["id"], "task_id": task["id"], "project_id": project["id"], "dataset_id": dataset["id"], "model_manifest_digest": model["manifest_digest"], "dataset_manifest_digest": dataset["manifest_digest"], "tokenization_recipe_digest": "d" * 64, "evaluation_plan_digest": None, "environment": copy.deepcopy(environment)}
        attempt.update(snapshot=snapshot, snapshot_digest=digest(snapshot))
        service.store.put("attempt", attempt)
    (service.root / "runs" / attempt["id"]).mkdir()
    service.processes[attempt["id"]] = ExitedFixtureProcess()
    yield client, service, attempt, model, environment
    service.processes.pop(attempt["id"], None)


def pause_command(run, key="pause"):
    client, service, attempt, *_ = run
    current = service.store.get("attempt", attempt["id"])
    return post(client, f"/attempts/{attempt['id']}/pause", {"expected_state_version": current["state_version"]}, key)


def checkpoint_event(run, command, step=2):
    _, service, attempt, model, _ = run
    directory = service.root / "runs" / attempt["id"] / "checkpoints" / command["command_id"]
    directory.mkdir(parents=True)
    source = Path(service.store.get("model", model["id"])["storage_path"]) / "model.safetensors"
    state = directory / "state.safetensors"
    state.write_bytes(source.read_bytes())
    value = {"schema_version": "mlx-training-checkpoint-v1", "complete": True, "source_attempt_id": attempt["id"], "source_snapshot_digest": attempt["snapshot_digest"], "step": step, "total_steps": 4, "next_sample_index": 0, "sample_count": 1, "losses": [1.0] * step, "compatibility": compatibility(attempt["snapshot"]), "tree": {"type": "dict", "items": {}}, "files": [{"path": "state.safetensors", "size": state.stat().st_size, "sha256": file_hash(state)}]}
    value["digest"] = digest(value)
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(value))
    event = {"type": "control_result", "command_id": command["command_id"], "action": "pause", "result": "confirmed", "checkpoint": {"relative_path": manifest.relative_to(service.root / "runs" / attempt["id"]).as_posix(), "manifest_digest": value["digest"], "step": step, "total_steps": 4}}
    return event, manifest


def paused(run):
    command = pause_command(run)
    event, path = checkpoint_event(run, command)
    run[1].checkpoints.handle_event(run[2]["id"], event)
    attempt = run[1].store.get("attempt", run[2]["id"])
    assert attempt["state"] == "paused"
    return attempt, path


def test_pause_atomic_command_and_idempotency_only_ack_confirms(training_run):
    client, service, attempt, *_ = training_run
    command = pause_command(training_run)
    assert command["id"] == attempt["id"] and command["resource_type"] == "attempt"
    assert command["state"] == "pausing" and command["result"] == "accepted"
    assert command["command_id"].startswith("command-")
    path = service.root / "runs" / attempt["id"] / "control/commands" / (command["command_id"] + ".json")
    body = json.loads(path.read_text())
    assert body == {"command_id": command["command_id"], "sequence": 1, "action": "pause", "attempt_id": attempt["id"]}
    assert not list(path.parent.glob("*.tmp"))
    assert post(client, f"/attempts/{attempt['id']}/pause", {"expected_state_version": 1}, "pause") == command
    event, _ = checkpoint_event(training_run, command)
    service.checkpoints.handle_event(attempt["id"], event)
    current = client.get(f"/api/v1/attempts/{attempt['id']}").json()
    assert current["state"] == "paused" and current["allowed_actions"] == ["resume", "cancel"]
    resources = client.get(f"/api/v1/checkpoints?attempt_id={attempt['id']}").json()["items"]
    assert len(resources) == 1 and "storage_path" not in resources[0] and "manifest" not in resources[0]
    assert service.store.get("training-control", command["command_id"])["result"] == "confirmed"


def test_resume_reloads_same_checkpoint_and_preserves_attempt(training_run):
    client, service, original, *_ = training_run
    attempt, _ = paused(training_run)
    command = post(client, f"/attempts/{attempt['id']}/resume", {"expected_state_version": attempt["state_version"]}, "resume")
    assert command["state"] == "resuming" and command["sequence"] == 2
    evidence = command["last_control"]["checkpoint_digest"]
    service.checkpoints.handle_event(attempt["id"], {"type": "control_result", "command_id": command["command_id"], "action": "resume", "result": "confirmed", "checkpoint_digest": evidence})
    done = service.store.get("attempt", attempt["id"])
    assert done["id"] == original["id"] and done["state"] == "running"
    assert done["snapshot_digest"] == original["snapshot_digest"]


@pytest.mark.parametrize("change", ["state", "source", "runtime", "extra", "symlink", "nan"])
def test_bad_checkpoint_never_confirms_paused(training_run, change):
    _, service, attempt, *_ = training_run
    command = pause_command(training_run)
    event, path = checkpoint_event(training_run, command)
    value = json.loads(path.read_text())
    if change == "state": (path.parent / "state.safetensors").write_bytes(b"broken")
    if change == "source": value["source_attempt_id"] = "other-attempt"
    if change == "runtime": value["compatibility"]["runtime"]["seed"] += 1
    if change == "extra": (path.parent / "unknown.bin").write_bytes(b"unknown")
    if change == "symlink":
        target = path.parent / "state.safetensors"
        real = path.parent.parent / "moved.safetensors"
        target.rename(real)
        target.symlink_to(real)
    if change == "nan": value["losses"][0] = float("nan")
    if change in {"source", "runtime"}:
        value["digest"] = digest({key: val for key, val in value.items() if key != "digest"})
        event["checkpoint"]["manifest_digest"] = value["digest"]
    path.write_text(json.dumps(value))
    service.checkpoints.handle_event(attempt["id"], event)
    actual = service.store.get("attempt", attempt["id"])
    assert actual["state"] == "pausing" and actual["phase"] == "pause_verification_failed"
    assert not service.store.list("checkpoint")
    assert actual["last_control"]["result"] == "failed"


def test_resume_rejects_changed_file_before_command(training_run):
    client, service, *_ = training_run
    attempt, path = paused(training_run)
    (path.parent / "state.safetensors").write_bytes(b"changed")
    response = client.post(f"/api/v1/attempts/{attempt['id']}/resume", json={"expected_state_version": attempt["state_version"]}, headers={"Idempotency-Key": "resume-bad"})
    assert response.status_code in {400, 409}
    assert service.store.get("attempt", attempt["id"])["state"] == "paused"
    assert len(service.store.list("training-control")) == 1


def test_cancel_remains_responsive_during_hash_and_late_ack_cannot_reopen(training_run, monkeypatch):
    import ailab_control.checkpoints as module
    client, service, attempt, *_ = training_run
    command = pause_command(training_run)
    event, _ = checkpoint_event(training_run, command)
    entered, release = threading.Event(), threading.Event()
    real = module.verify_manifest

    def slow(*args):
        entered.set()
        assert release.wait(3)
        return real(*args)

    monkeypatch.setattr(module, "verify_manifest", slow)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(service.checkpoints.handle_event, attempt["id"], event)
        assert entered.wait(2)
        before = time.monotonic()
        response = post(client, f"/attempts/{attempt['id']}/cancel", {"expected_state_version": command["state_version"]}, "cancel-hashing")
        assert time.monotonic() - before < 1
        assert response["state"] == "cancelling"
        release.set()
        pending.result(3)
    assert service.store.get("attempt", attempt["id"])["state"] == "cancelling"
    assert len(service.store.list("checkpoint")) == 1
    assert service.store.get("attempt", attempt["id"])["last_control"]["action"] == "cancel"


def test_corrupt_late_checkpoint_is_not_registered_and_terminal_is_preserved(training_run):
    _, service, attempt, *_ = training_run
    command = pause_command(training_run)
    event, path = checkpoint_event(training_run, command)
    (path.parent / "state.safetensors").write_bytes(b"broken-late-state")
    with service.store.transaction():
        current = service.store.get("attempt", attempt["id"])
        service.transition(current, "cancelled", "夹具已确认停止")
    before = service.store.get("attempt", attempt["id"])
    service.checkpoints.handle_event(attempt["id"], event)
    after = service.store.get("attempt", attempt["id"])
    assert after["state"] == "cancelled" and after["state_version"] == before["state_version"]
    assert not service.store.list("checkpoint")


def test_new_restore_task_requires_old_exit_and_preserves_terminal(training_run):
    client, service, _, _, environment = training_run
    attempt, _ = paused(training_run)
    path = f"/checkpoints/{attempt['checkpoint_id']}/restore-task"
    rejected = client.post("/api/v1" + path, json={}, headers={"Idempotency-Key": "active"})
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "CHECKPOINT_SOURCE_ACTIVE"
    with service.store.transaction():
        service.transition(attempt, "cancelled", "夹具已确认退出")
    service.processes.pop(attempt["id"])
    original = service.store.get("attempt", attempt["id"])
    task = post(client, path, {"name": "恢复新任务"}, "restore-task")
    assert task["id"] != attempt["task_id"] and task["draft"]["checkpoint_id"] == attempt["checkpoint_id"]
    assert service.store.get("attempt", attempt["id"]) == original
    assert post(client, path, {"name": "恢复新任务"}, "restore-task") == task
    changed = copy.deepcopy(task["draft"])
    changed["runtime"]["steps"] += 1
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": 1, "draft": changed})
    assert response.status_code == 409
    environment["versions"]["dependencies"]["mlx"] = "changed-version"
    blocked = client.post("/api/v1" + path, json={}, headers={"Idempotency-Key": "changed-environment"})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CHECKPOINT_ENVIRONMENT_CHANGED"


def test_worker_pause_failure_returns_to_running_without_checkpoint(training_run):
    _, service, attempt, *_ = training_run
    command = pause_command(training_run)
    service.checkpoints.handle_event(attempt["id"], {"type": "control_result", "command_id": command["command_id"], "action": "pause", "result": "failed", "continuing": True, "code": "DISK_FULL", "message": "保存失败，原训练继续"})
    current = service.store.get("attempt", attempt["id"])
    assert current["state"] == "running" and current["last_control"]["code"] == "DISK_FULL"
    assert not service.store.list("checkpoint")


def test_pause_capability_requires_training_protocol_sources(training_run):
    client, _, _, _, environment = training_run
    values = client.get("/api/v1/capabilities").json()["items"]
    assert [item["kind"] for item in values if item["pause"]] == ["text"]
    assert next(item for item in values if item["pause"])["operation"] == "train"
    environment["identity"]["adapter_sources"].pop("/fixed/adapters/checkpoint.py")
    assert not any(item["pause"] for item in client.get("/api/v1/capabilities").json()["items"])
