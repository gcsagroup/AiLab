"""真实 SQLite、HTTP 合同、文件与独立进程的首批验收。"""

import copy
import hashlib
import json
import os
import signal
import sqlite3
import struct
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "control"))
from ailab_control.api import create_app
from ailab_control.assets import file_hash, verify_manifest
from ailab_control.service import Service, Settings
from ailab_control.storage import Fault, digest


def make_model(directory):
    directory.mkdir()
    (directory / "config.json").write_text(json.dumps({"model_type": "qwen2", "hidden_size": 896, "num_hidden_layers": 24}))
    (directory / "tokenizer_config.json").write_text("{}")
    header = json.dumps({"fixture_tensor": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    header += b" " * (-len(header) % 8)
    (directory / "model.safetensors").write_bytes(struct.pack("<Q", len(header)) + header + struct.pack("<f", 1))
    return directory


@pytest.fixture
def rig(tmp_path, monkeypatch):
    source = tmp_path / "用户授权 资料"
    source.mkdir()
    settings = Settings(tmp_path / "数据 空间", "session-secret-for-tests", [source], Path(sys.executable), Path(__file__).with_name("fixture_worker.py"), preflight_script=Path(__file__).with_name("fixture_preflight.py"))
    app = create_app(settings)
    service = app.state.service
    service.test_monkeypatch = monkeypatch
    environment = {"engine": "mlx", "device_id": "apple-gpu", "ready": True, "reason": "", "fixture_only": True, "digest": "fixture-env-1"}
    monkeypatch.setattr(service, "environment", lambda refresh=False, **_: dict(environment))
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer session-secret-for-tests"}) as client:
        yield client, service, source, environment


def post(client, path, body, key=None):
    response = client.post("/api/v1" + path, json=body, headers={"Idempotency-Key": key} if key else {})
    assert response.status_code == 200, response.text
    return response.json()


def setup_task(rig, prompt="说明数据版本。", operation="generate"):
    client, service, source, _ = rig
    project = post(client, "/projects", {"name": "验收项目"})
    model_path = make_model(source / f"模型-{project['id']}")
    plan = post(client, "/models/import-plans", {"project_id": project["id"], "path": str(model_path)})
    model = post(client, "/models/imports", {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}, "model-" + project["id"])
    task = post(client, "/tasks", {"project_id": project["id"], "name": "验收任务", "kind": "text", "operation": operation})
    draft = task["draft"]
    draft["model_id"] = model["id"]
    draft["input"]["prompt"] = prompt
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": task["draft_revision"], "draft": draft})
    assert response.status_code == 200, response.text
    return project, model, response.json()


def submit(rig, task, key="submit-one"):
    client = rig[0]
    check = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert check["can_submit"], check
    payload = {"preflight_id": check["id"], "expected_revision": task["draft_revision"]}
    return post(client, f"/tasks/{task['id']}/attempts", payload, key), payload


def wait_attempt(client, attempt_id, predicate=lambda a: a["state"] in {"succeeded", "failed", "cancelled"}, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = client.get(f"/api/v1/attempts/{attempt_id}").json()
        if predicate(result):
            return result
        time.sleep(0.02)
    raise AssertionError(result)


def test_real_sqlite_restart_and_project_isolation(rig):
    client, service, source, _ = rig
    first, model, task = setup_task(rig)
    second = post(client, "/projects", {"name": "隔离项目"})
    other = post(client, "/tasks", {"project_id": second["id"], "name": "另一任务", "kind": "text", "operation": "generate"})
    draft = other["draft"]
    draft["model_id"] = model["id"]
    rejected = client.patch(f"/api/v1/tasks/{other['id']}/draft", json={"expected_revision": 1, "draft": draft})
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "PROJECT_MISMATCH"
    assert client.get(f"/api/v1/tasks?project_id={second['id']}").json()["items"][0]["draft_revision"] == 1
    service.close()
    reopened = Service(service.settings)
    assert reopened.store.get("task", task["id"])["draft"] == task["draft"]
    assert len(reopened.store.list("project")) == 2
    assert reopened.store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()


def test_instance_lock_rejects_second_service_then_releases(rig):
    service = rig[1]
    with pytest.raises(Fault, match="已有控制服务"):
        Service(service.settings)
    service.close()
    second = Service(service.settings)
    second.close()


@pytest.mark.parametrize("headers,status", [({"Authorization": "Bearer wrong"}, 401), ({"Authorization": ""}, 401), ({"Origin": "https://evil.example"}, 403), ({"Origin": "null"}, 403), ({"Host": "evil.example"}, 403)])
def test_auth_cors_and_dns_rebinding(rig, headers, status):
    response = rig[0].get("/api/v1/projects", headers=headers)
    assert response.status_code == status
    assert "session-secret" not in response.text
    assert "access-control-allow-origin" not in response.headers


def test_health_no_secret_unknown_endpoint_and_request_limit(rig):
    client = rig[0]
    assert client.get("/health", headers={"Authorization": ""}).json() == {"status": "ok"}
    assert client.post("/api/v1/execute-shell", json={"command": "touch /tmp/nope"}).status_code == 404
    assert client.post("/api/v1/projects", content=b"x" * (2 * 1024 * 1024 + 1)).status_code == 413
    assert client.options("/api/v1/projects", headers={"Origin": "https://evil.example"}).status_code == 403


def test_invalid_json_extra_fields_types_and_whitespace(rig):
    client = rig[0]
    assert client.post("/api/v1/projects", content="{").status_code == 422
    for payload in ({"name": "   "}, {"name": "正常", "command": "rm"}, {"name": 4}):
        assert client.post("/api/v1/projects", json=payload).status_code == 422
    _, _, task = setup_task(rig)
    for key, value in (("max_tokens", True), ("max_tokens", 2049), ("temperature", "0.8"), ("top_p", 0), ("seed", -1), ("arbitrary", "code")):
        draft = copy.deepcopy(task["draft"])
        draft["runtime"][key] = value
        response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": task["draft_revision"], "draft": draft})
        assert response.status_code == 422, (key, response.text)


def test_optimistic_revision_and_project_rename(rig):
    client = rig[0]
    project, _, task = setup_task(rig)
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": 1, "draft": task["draft"]})
    assert response.status_code == 409
    assert response.json()["error"]["details"]["current_revision"] == 2
    renamed = client.patch(f"/api/v1/projects/{project['id']}", json={"name": "新名", "expected_revision": 1})
    assert renamed.json()["revision"] == 2
    assert client.get(f"/api/v1/tasks/{task['id']}").json()["project_id"] == project["id"]


def test_path_authorization_and_symbolic_links(rig, tmp_path):
    client, _, source, _ = rig
    project = post(client, "/projects", {"name": "安全导入"})
    outside = make_model(tmp_path / "未授权")
    base = {"project_id": project["id"]}
    assert client.post("/api/v1/models/import-plans", json={**base, "path": str(outside)}).status_code == 403
    assert client.post("/api/v1/models/import-plans", json={**base, "path": str(source / ".." / "未授权")}).status_code == 400
    linked = source / "符号链接"
    linked.symlink_to(outside)
    assert client.post("/api/v1/models/import-plans", json={**base, "path": str(linked)}).status_code == 400
    grant = post(client, "/import-grants", {"path": str(outside)})
    accepted = post(client, "/models/import-plans", {**base, "path": str(outside), "grant_id": grant["grant_id"]})
    assert accepted["can_import"]
    (outside / "linked.json").symlink_to(outside / "config.json")
    assert client.post("/api/v1/models/import-plans", json={**base, "path": str(outside), "grant_id": grant["grant_id"]}).status_code == 400


@pytest.mark.parametrize("mutation", ["pickle", "python", "auto_map", "fake_safetensors"])
def test_unsafe_model_formats_rejected_without_execution(rig, mutation):
    client, _, source, _ = rig
    project = post(client, "/projects", {"name": "受限模型"})
    model = make_model(source / "坏模型")
    if mutation in {"pickle", "python"}:
        (model / ("payload.pkl" if mutation == "pickle" else "payload.py")).write_text("raise SystemExit('不应执行')")
    elif mutation == "auto_map":
        (model / "config.json").write_text('{"model_type":"qwen2","auto_map":{"AutoModel":"evil.py"}}')
    else:
        (model / "model.safetensors").write_bytes(b"pickle disguised")
    response = client.post("/api/v1/models/import-plans", json={"project_id": project["id"], "path": str(model)})
    assert response.status_code == 400
    assert response.json()["error"]["code"] in {"MODEL_LOAD_TRUST_REQUIRED", "INVALID_MODEL_FORMAT"}


def test_import_rechecks_source_and_idempotency(rig):
    client, service, source, _ = rig
    project = post(client, "/projects", {"name": "导入复核"})
    model = make_model(source / "源模型")
    plan = post(client, "/models/import-plans", {"project_id": project["id"], "path": str(model)})
    payload = {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}
    (model / "tokenizer_config.json").write_text('{"changed":true}')
    assert client.post("/api/v1/models/imports", json=payload, headers={"Idempotency-Key": "once"}).status_code == 409
    new = post(client, "/models/import-plans", {"project_id": project["id"], "path": str(model)})
    payload = {"plan_id": new["id"], "manifest_digest": new["manifest_digest"]}
    result = post(client, "/models/imports", payload, "once")
    assert result == post(client, "/models/imports", payload, "once")
    assert client.post("/api/v1/models/imports", json={**payload, "manifest_digest": "f" * 64}, headers={"Idempotency-Key": "once"}).status_code == 409
    internal = service.store.get("model", result["id"])
    assert "storage_path" not in result
    (model / "tokenizer_config.json").write_text("{}")
    assert (Path(internal["storage_path"]) / "tokenizer_config.json").read_text() == '{"changed":true}'


@pytest.mark.parametrize("filename", ["extra.safetensors", "chat_template.jinja"])
def test_unregistered_model_files_block_preflight(rig, filename):
    client, service, _, _ = rig
    _, model, task = setup_task(rig)
    saved = service.store.get("model", model["id"])
    (Path(saved["storage_path"]) / filename).write_bytes(b"unregistered")
    check = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert not check["can_submit"]
    assert any(issue["code"] == "ARTIFACT_CORRUPT" for issue in check["blocking"])


def test_jsonl_real_parse_reports_and_rejects_bad_lines(rig):
    client, _, source, _ = rig
    project = post(client, "/projects", {"name": "真实数据导入"})
    sample = {"messages": [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "回答"}]}
    path = source / "数据.jsonl"
    path.write_text(json.dumps(sample) + "\nnot-json\n")
    plan = post(client, "/datasets/import-plans", {"project_id": project["id"], "path": str(path), "schema": "sft"})
    assert (plan["sample_count"], plan["failed_count"], plan["issues"][0]["line"]) == (1, 1, 2)
    assert not plan["can_import"]
    assert client.post("/api/v1/datasets/imports", json={"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}, headers={"Idempotency-Key": "bad"}).status_code == 400
    path.write_text(json.dumps(sample) + "\n")
    plan = post(client, "/datasets/import-plans", {"project_id": project["id"], "path": str(path), "schema": "sft"})
    dataset = post(client, "/datasets/imports", {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}, "good")
    assert dataset["checks"]["tokenization"] == "not_run"
    assert dataset["sample_count"] == 1
    path.write_bytes(b"\xff")
    assert client.post("/api/v1/datasets/import-plans", json={"project_id": project["id"], "path": str(path)}).status_code == 400


def test_missing_environment_and_unsupported_combinations(rig):
    client, _, _, environment = rig
    _, _, task = setup_task(rig)
    environment.update(ready=False, reason="测试缺依赖")
    check = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert not check["can_submit"]
    assert client.post(f"/api/v1/tasks/{task['id']}/attempts", json={"preflight_id": check["id"], "expected_revision": task["draft_revision"]}, headers={"Idempotency-Key": "blocked"}).status_code == 409


def test_submit_snapshot_events_save_work_and_restart(rig):
    client, service, _, _ = rig
    project, _, task = setup_task(rig)
    attempt, payload = submit(rig, task)
    done = wait_attempt(client, attempt["id"])
    assert done["state"] == "succeeded", done
    assert done["compute_outcome"] == done["collection_state"] == "succeeded"
    assert done["output_text"] == "可持久化的控制测试夹具结果。"
    assert done["artifacts"][0]["text"] == done["output_text"]
    assert done["snapshot"]["model_manifest"] and done["snapshot"]["tokenization_recipe_digest"]
    draft = copy.deepcopy(task["draft"])
    draft["input"]["prompt"] = "新的草稿"
    assert client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": task["draft_revision"], "draft": draft}).status_code == 200
    duplicate = post(client, f"/tasks/{task['id']}/attempts", payload, "submit-one")
    assert duplicate["id"] == attempt["id"]
    assert len(list((service.root / "runs").iterdir())) == 1
    current = client.get(f"/api/v1/attempts/{attempt['id']}").json()
    assert current["snapshot_digest"] == attempt["snapshot_digest"]
    assert current["snapshot"]["input"]["prompt"] == "说明数据版本。"
    events = client.get(f"/api/v1/attempts/{attempt['id']}/events?limit=2").json()
    following = client.get(f"/api/v1/attempts/{attempt['id']}/events?after={events['next_cursor']}").json()
    sequences = [item["sequence"] for item in events["items"] + following["items"]]
    assert sequences == list(range(1, current["last_event_sequence"] + 1))
    sse = client.get(f"/api/v1/attempts/{attempt['id']}/events?format=sse", headers={"Last-Event-ID": str(current["last_event_sequence"] - 1)})
    assert "event-stream" in sse.headers["content-type"]
    assert f"id: {current['last_event_sequence']}" in sse.text
    work = post(client, "/works", {"attempt_id": attempt["id"], "name": "持久作品"}, "work-one")
    assert work == post(client, "/works", {"attempt_id": attempt["id"], "name": "持久作品"}, "work-one")
    service.close()
    reopened = Service(service.settings)
    assert reopened.store.get("work", work["id"])["text"] == current["output_text"]
    assert reopened.store.get("attempt", attempt["id"])["state"] == "succeeded"
    reopened.close()


def test_concurrent_duplicate_submission_only_launches_once(rig):
    client, service, _, _ = rig
    _, _, task = setup_task(rig, "__wait__")
    check = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    payload = {"preflight_id": check["id"], "expected_revision": task["draft_revision"]}
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: service.submit(task["id"], payload, "duplicate"), range(3)))
    assert len({item["id"] for item in responses}) == 1
    attempt = wait_attempt(client, responses[0]["id"], lambda a: a["state"] == "running")
    assert len(service.store.list("attempt")) == 1
    with pytest.raises(Fault) as conflict:
        service.submit(task["id"], {**payload, "expected_revision": 999}, "duplicate")
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    post(client, f"/attempts/{attempt['id']}/cancel", {"expected_state_version": attempt["state_version"]}, "stop")
    assert wait_attempt(client, attempt["id"])["state"] == "cancelled"


@pytest.mark.parametrize("mode,expected", [("__crash__", "WORKER_FAILED"), ("__no_completed__", "WORKER_FAILED"), ("__bad_json__", "INVALID_WORKER_EVENT"), ("__badpath__", "ARTIFACT_CORRUPT")])
def test_worker_failure_cannot_be_success(rig, mode, expected):
    _, _, task = setup_task(rig, mode)
    attempt, _ = submit(rig, task)
    done = wait_attempt(rig[0], attempt["id"])
    assert done["state"] == "failed"
    assert done["terminal_reason"] == expected
    assert not done["artifacts"]


@pytest.mark.parametrize("mode,terminal", [("__wait__", "cancelled"), ("__cancel_crash__", "failed")])
def test_cancel_waits_for_real_process_exit(rig, mode, terminal):
    client, service, _, _ = rig
    _, _, task = setup_task(rig, mode)
    submitted, _ = submit(rig, task)
    attempt = wait_attempt(client, submitted["id"], lambda a: bool(a["output_text"]))
    payload = {"expected_state_version": attempt["state_version"]}
    result = post(client, f"/attempts/{attempt['id']}/cancel", payload, "cancel-once")
    assert result["state"] == "cancelling"
    assert result["stop_status"] == "pending"
    assert result == post(client, f"/attempts/{attempt['id']}/cancel", payload, "cancel-once")
    done = wait_attempt(client, attempt["id"])
    assert done["state"] == terminal
    assert done["stop_status"] == "confirmed"
    assert done["output_text"] == "夹具输出"
    assert not service.group_present(done["process"]["pid"])
    old = client.post(f"/api/v1/attempts/{attempt['id']}/cancel", json=payload, headers={"Idempotency-Key": "old-version"})
    assert old.status_code == 409


def test_force_stop_real_unresponsive_process(rig):
    client = rig[0]
    _, _, task = setup_task(rig, "__ignore_cancel__")
    submitted, _ = submit(rig, task)
    running = wait_attempt(client, submitted["id"], lambda a: bool(a["output_text"]))
    requested = post(client, f"/attempts/{running['id']}/cancel", {"expected_state_version": running["state_version"]}, "cancel")
    time.sleep(0.1)
    assert client.get(f"/api/v1/attempts/{running['id']}").json()["state"] == "cancelling"
    post(client, f"/attempts/{running['id']}/force-stop", {"expected_state_version": requested["state_version"]}, "force")
    stopped = wait_attempt(client, running["id"])
    assert stopped["state"] == "cancelled"
    assert stopped["process"]["returncode"] == -signal.SIGKILL


def test_collection_retry_never_recomputes_or_changes_terminal(rig):
    client, service, _, _ = rig
    _, _, task = setup_task(rig, "__corrupt__")
    attempt, _ = submit(rig, task)
    failed = wait_attempt(client, attempt["id"])
    assert failed["state"] == "failed" and failed["compute_outcome"] == "succeeded"
    assert failed["collection_state"] == "failed"
    original = (failed["state"], failed["state_version"], failed["terminal_reason"], failed["finished_at"])
    (service.root / "runs" / attempt["id"] / "output" / "result.txt").write_text("待补收的正确内容。")
    payload = {"manifest_digest": failed["output_manifest_ref"]["digest"], "expected_collection_version": failed["collection_version"]}
    collection = post(client, f"/attempts/{attempt['id']}/collections", payload, "collect-once")
    assert collection["state"] == "succeeded"
    assert collection == post(client, f"/attempts/{attempt['id']}/collections", payload, "collect-once")
    recovered = client.get(f"/api/v1/attempts/{attempt['id']}").json()
    assert (recovered["state"], recovered["state_version"], recovered["terminal_reason"], recovered["finished_at"]) == original
    assert recovered["collection_state"] == "succeeded"
    assert len(recovered["artifacts"]) == len(list((service.root / "runs").iterdir())) == 1
    assert recovered["output_text"] == "待补收的正确内容。"


def test_slow_preflight_does_not_block_cancel_and_revision_race(rig, monkeypatch):
    client, service, _, _ = rig
    _, _, task = setup_task(rig, "__wait__")
    submitted, _ = submit(rig, task)
    running = wait_attempt(client, submitted["id"], lambda a: bool(a["output_text"]))
    entered, release = threading.Event(), threading.Event()
    original = service.inspect_task

    def slow_check(task):
        entered.set()
        assert release.wait(5)
        return original(task)

    monkeypatch.setattr(service, "inspect_task", slow_check)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.preflight, task["id"], task["draft_revision"])
        assert entered.wait(2)
        started = time.monotonic()
        post(client, f"/attempts/{running['id']}/cancel", {"expected_state_version": running["state_version"]}, "cancel-during-check")
        assert time.monotonic() - started < 0.5
        update = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": task["draft_revision"], "draft": task["draft"]})
        assert update.status_code == 200
        release.set()
        with pytest.raises(Fault) as conflict:
            future.result(timeout=5)
        assert conflict.value.code == "REVISION_CONFLICT"
    assert wait_attempt(client, running["id"])["state"] == "cancelled"


def test_changed_environment_invalidates_preflight(rig):
    client, _, _, environment = rig
    _, _, task = setup_task(rig)
    check = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    environment["digest"] = "different-actual-dependency-version"
    response = client.post(f"/api/v1/tasks/{task['id']}/attempts", json={"preflight_id": check["id"], "expected_revision": task["draft_revision"]}, headers={"Idempotency-Key": "version-drift"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ENVIRONMENT_CHANGED"


@pytest.mark.parametrize("change", ["recipe_source", "tokenizers_version", "transformers_version"])
def test_real_environment_digest_tracks_adapter_source_and_dependency_probe(rig, monkeypatch, change):
    client, service, source, _ = rig
    _, _, task = setup_task(rig)
    adapter = source / "受控适配器"
    adapter.mkdir()
    (adapter / "recipe.py").write_text("RECIPE = 'first'\n")
    (adapter / "preflight.py").write_text(Path(__file__).with_name("fixture_preflight.py").read_text())
    (adapter / "requirements.lock.txt").write_text("用于合同测试的固定依赖证据\n")
    service.settings.preflight_script = adapter / "preflight.py"
    monkeypatch.setattr(service, "environment", Service.environment.__get__(service))
    facts = {"metal": True, "dependencies": {"tokenizers": "fixture-one", "transformers": "fixture-one"}}
    real_run = subprocess.run

    def probe(arguments, **kwargs):
        if len(arguments) > 1 and arguments[1] == "-c":
            return subprocess.CompletedProcess(arguments, 0, json.dumps(facts), "")
        return real_run(arguments, **kwargs)

    monkeypatch.setattr(subprocess, "run", probe)
    checked = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert checked["can_submit"], checked
    if change == "recipe_source":
        (adapter / "recipe.py").write_text("RECIPE = 'changed'\n")
    else:
        facts["dependencies"][change.removesuffix("_version")] = "fixture-two"
    response = client.post(f"/api/v1/tasks/{task['id']}/attempts", json={"preflight_id": checked["id"], "expected_revision": task["draft_revision"]}, headers={"Idempotency-Key": "actual-digest-drift"})
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "ENVIRONMENT_CHANGED"


@pytest.mark.parametrize("mode", ["missing_digest", "bad_exit", "inconsistent_blocking"])
def test_malformed_preflight_never_grants_execution(rig, monkeypatch, mode):
    client, service, source, _ = rig
    _, _, task = setup_task(rig)
    checker = source / "bad-check.py"
    data = {"can_submit": True, "blocking": [], "effective_config": {}, "recipe": {}, "check_report": {}, "tokenization_recipe_digest": "a" * 64}
    if mode == "missing_digest":
        del data["tokenization_recipe_digest"]
    elif mode == "inconsistent_blocking":
        data["blocking"] = [{"code": "bad", "message": "阻断"}]
    checker.write_text("import json,sys\nprint(" + repr(json.dumps(data)) + ")\nsys.exit(" + ("1" if mode == "bad_exit" else "0") + ")\n")
    service.settings.preflight_script = checker
    checked = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert not checked["can_submit"]
    assert checked["blocking"][0]["code"] == "PREFLIGHT_FAILED"


def test_backup_database_integrity_and_scope(rig):
    client, service, _, _ = rig
    project, _, task = setup_task(rig)
    backup = post(client, "/backups", {})
    assert backup["contains_asset_files"]
    directory = service.root / "backups" / backup["id"]
    with sqlite3.connect(directory / "control.sqlite3") as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT count(*) FROM projects").fetchone()[0] == 1
    manifest = json.loads((directory / "manifest.json").read_text())
    assert next(item["sha256"] for item in manifest["files"] if item["path"] == "control.sqlite3") == file_hash(directory / "control.sqlite3")
    assert any(item["path"].startswith("assets/") for item in manifest["files"])


def test_backup_restore_http_contract_and_confirmed_new_directory(rig, tmp_path, monkeypatch):
    client, service, _, _ = rig
    project, model, task = setup_task(rig)
    backup = post(client, "/backups", {}, "backup-http-once")
    assert post(client, "/backups", {}, "backup-http-once")["id"] == backup["id"]
    assert client.get("/api/v1/backups").json()["items"][0]["id"] == backup["id"]
    parent = tmp_path / "用户选择的恢复父目录"
    parent.mkdir()
    grant = post(client, "/export-grants", {"path": str(parent)})
    plan = post(client, "/restore-plans", {"backup_path": backup["backup_path"], "target_dir": str(parent), "target_grant_id": grant["grant_id"]})
    assert plan["can_restore"] and not plan["changes_current_library"]
    assert not Path(plan["restored_path"]).exists()
    restored = post(client, "/restores", {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-http-once")
    assert restored["state"] == "succeeded" and not restored["changes_current_library"]
    assert Path(restored["restored_path"]).parent == parent
    checked = client.get(f"/api/v1/restores/{restored['id']}").json()
    assert checked["verified"]
    assert client.get("/api/v1/restores").json()["items"][0]["id"] == restored["id"]
    assert service.store.get("model", model["id"])["storage_path"].startswith(str(service.root))
    endpoint = f"/api/v1/restores/{restored['id']}/activation"
    service.settings.host_token = "native-test-only-secret-" + "x" * 48
    host_headers = {"X-AiLab-Host-Token": service.settings.host_token}
    assert client.post(endpoint).status_code == 403
    assert not service.activation_pending and service.active_writes == 0
    activated = client.post(endpoint, headers=host_headers)
    assert activated.status_code == 200 and activated.json()["activation_ready"]
    assert service.activation_pending and service.active_writes == 0
    assert client.post("/api/v1/projects", json={"name": "切换期间禁止写入"}).status_code == 409
    assert client.get("/api/v1/projects").status_code == 200
    assert client.delete(endpoint).status_code == 403
    assert client.delete(endpoint, headers=host_headers).json() == {"activation_pending": False}
    assert client.post(endpoint, headers=host_headers).status_code == 200
    service.activation_deadline = time.monotonic() - 1
    assert client.post("/api/v1/projects", json={"name": "租期到期恢复写入"}).status_code == 200
    assert not service.activation_pending
    entered, release = threading.Event(), threading.Event()
    original_project = service.project

    def slow_project(payload):
        entered.set()
        assert release.wait(4)
        return original_project(payload)

    monkeypatch.setattr(service, "project", slow_project)
    with ThreadPoolExecutor() as executor:
        pending = executor.submit(client.post, "/api/v1/projects", json={"name": "尚未完成的写入"})
        assert entered.wait(2)
        try:
            conflict = client.post(endpoint, headers=host_headers)
            assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "LIBRARY_BUSY", conflict.text
            assert not service.activation_pending
        finally:
            release.set()
        assert pending.result().status_code == 200
    assert service.active_writes == 0


def test_recovery_unknown_requires_evidence_then_releases_device(rig, monkeypatch):
    client, service, _, _ = rig
    _, _, task = setup_task(rig)
    with service.store.transaction():
        attempt = service.resource("attempt", task["project_id"], task_id=task["id"], state="running", state_version=3,
                                   connection_state="disconnected", stop_status="unknown", compute_outcome="pending", collection_state="not_started", collection_version=0,
                                   output_manifest_ref=None, last_event_sequence=0, phase="loading", progress=None, output_text="", terminal_reason=None,
                                   recovery_required=True, process={"pid": os.getpid(), "identity": service.process_identity(os.getpid())})
        service.store.put("attempt", attempt)
    directory = service.root / "runs" / attempt["id"]
    directory.mkdir()
    unknown = post(client, f"/attempts/{attempt['id']}/reconcile", {"expected_state_version": 3}, "check-live")
    assert unknown["state"] == "running" and unknown["stop_status"] == "unknown"
    assert unknown["allowed_actions"] == ["reconcile"]
    monkeypatch.setattr(service, "process_identity", lambda pid: {"status": "absent"})
    monkeypatch.setattr(service, "group_present", lambda pid: False)
    confirmed = post(client, f"/attempts/{attempt['id']}/reconcile", {"expected_state_version": unknown["state_version"]}, "check-exited")
    assert confirmed["state"] == "failed"
    assert confirmed["terminal_reason"] == "CONTROL_INTERRUPTED"
    assert not confirmed["recovery_required"]
    assert confirmed["stop_status"] == "confirmed"


def test_settings_persist_and_reject_arbitrary_program(rig):
    client, service, source, _ = rig
    response = client.patch("/api/v1/settings", json={"worker_python": "/bin/sh", "expected_revision": 1})
    assert response.status_code == 400
    updated = client.patch("/api/v1/settings", json={"worker_python": sys.executable, "expected_revision": 1})
    assert updated.status_code == 200, updated.text
    assert updated.json()["worker_python"] == sys.executable
    assert client.patch("/api/v1/settings", json={"worker_python": sys.executable, "expected_revision": 1}).status_code == 409
    service.close()
    settings = copy.copy(service.settings)
    settings.worker_python = None
    reopened = Service(settings)
    assert reopened.get_settings()["revision"] == 2
    assert str(reopened.settings.worker_python) == sys.executable
    reopened.close()


def test_explicit_restore_bundled_environment_requires_installed_worker(rig):
    client, service, _, _ = rig
    assert client.patch("/api/v1/settings", json={"expected_revision": 1}).status_code == 422
    assert client.patch("/api/v1/settings", json={"worker_python": None, "expected_revision": 1}).status_code == 400
    service.settings.bundled_worker = Path(sys.executable)
    response = client.patch("/api/v1/settings", json={"worker_python": None, "expected_revision": 1})
    assert response.status_code == 200, response.text
    assert response.json()["execution_backend"] == "bundled"
    assert response.json()["worker_python"] is None
    assert service.settings.worker_python is None
