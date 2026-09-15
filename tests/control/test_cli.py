"""真实回环 HTTP、进程级目录独占和崩溃重启验证。"""

import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from test_control import ROOT, make_model


def launch(directory, *extra, entrypoint=None, env_extra=None):
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "services" / "control"))
    environment.update(env_extra or {})
    log = (directory.parent / f"stderr-{time.time_ns()}.log").open("wb")
    command = [sys.executable, str(entrypoint)] if entrypoint else [sys.executable, "-m", "ailab_control"]
    child = subprocess.Popen([*command, "--data-dir", str(directory), "--port", "0", *extra], stdout=subprocess.PIPE, stderr=log, env=environment)
    log.close()
    if not select.select([child.stdout], [], [], 12)[0]:
        child.kill()
        child.wait()
        raise AssertionError("服务未在12秒内返回握手")
    raw = child.stdout.readline()
    if not raw:
        child.wait(timeout=5)
        child.stdout.close()
        return child, None
    connection = json.loads(raw)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{connection['port']}/health", timeout=0.2).status_code == 200:
                return child, connection
        except httpx.HTTPError:
            pass
        time.sleep(0.03)
    child.kill()
    child.wait()
    raise AssertionError("握手后真实端口未就绪")


def stop(child, kill=False):
    if child.poll() is None:
        child.kill() if kill else child.terminate()
        child.wait(timeout=12)
    if child.stdout:
        child.stdout.close()


def client_for(connection):
    return httpx.Client(base_url=f"http://127.0.0.1:{connection['port']}/api/v1", headers={"Authorization": "Bearer " + connection["token"]}, timeout=30)


def test_real_loopback_token_file_and_process_exclusive_lock(tmp_path):
    data = tmp_path / "中文 空格数据"
    token_file = tmp_path / "连接.json"
    child, connection = launch(data, "--token-file", str(token_file))
    try:
        assert token_file.stat().st_mode & 0o777 == 0o600
        assert json.loads(token_file.read_text())["pid"] == child.pid
        assert "host_token" not in json.loads(token_file.read_text())
        assert len(connection["host_token"]) >= 48 and connection["host_token"] != connection["token"]
        with client_for(connection) as client:
            result = client.post("/projects", json={"name": "真实HTTP项目"})
            assert result.status_code == 200
            project = result.json()
            assert client.get("/projects", headers={"Authorization": "Bearer invalid"}).status_code == 401
        duplicate, failed_handshake = launch(data)
        assert failed_handshake is None and duplicate.returncode != 0
    finally:
        stop(child)
    assert not token_file.exists()
    restarted, second = launch(data)
    try:
        assert second["token"] != connection["token"]
        with client_for(second) as client:
            assert client.get("/projects").json()["items"][0]["id"] == project["id"]
    finally:
        stop(restarted)


def test_controller_sigkill_recovery_with_real_owned_worker(tmp_path):
    worker_python = ROOT / "adapters" / "mlx_text" / ".venv" / "bin" / "python"
    if not worker_python.is_file():
        pytest.skip("此主机没有已准备MLX环境；常规合同测试不安装模型依赖")
    source = tmp_path / "授权源"
    source.mkdir()
    model_path = make_model(source / "控制夹具模型")
    data = tmp_path / "控制中断数据"
    args = ("--import-root", str(source), "--worker-python", str(worker_python), "--worker-script", str(Path(__file__).with_name("fixture_worker.py")), "--preflight-script", str(Path(__file__).with_name("fixture_preflight.py")))
    child, connection = launch(data, *args)
    try:
        with client_for(connection) as client:
            project = client.post("/projects", json={"name": "崩溃恢复"}).json()
            plan = client.post("/models/import-plans", json={"project_id": project["id"], "path": str(model_path)}).json()
            model_response = client.post("/models/imports", json={"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}, headers={"Idempotency-Key": "model"})
            assert model_response.status_code == 200, model_response.text
            task = client.post("/tasks", json={"project_id": project["id"], "kind": "text", "operation": "generate", "name": "长夹具进程"}).json()
            draft = task["draft"]
            draft["model_id"] = model_response.json()["id"]
            draft["input"]["prompt"] = "__wait__"
            task = client.patch(f"/tasks/{task['id']}/draft", json={"draft": draft, "expected_revision": 1}).json()
            check = client.post(f"/tasks/{task['id']}/preflight", json={"draft_revision": task["draft_revision"]}).json()
            assert check["can_submit"], check
            submitted = client.post(f"/tasks/{task['id']}/attempts", json={"preflight_id": check["id"], "expected_revision": task["draft_revision"]}, headers={"Idempotency-Key": "run"}).json()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                running = client.get(f"/attempts/{submitted['id']}").json()
                if running["output_text"]:
                    break
                time.sleep(0.05)
            assert running["state"] == "running"
        stop(child, kill=True)
        restarted, connection2 = launch(data, *args)
        try:
            with client_for(connection2) as client:
                recovered = client.get(f"/attempts/{submitted['id']}").json()
                assert recovered["stop_status"] == "unknown"
                assert recovered["allowed_actions"] == ["reconcile"]
                for index in range(60):
                    response = client.post(f"/attempts/{submitted['id']}/reconcile", json={"expected_state_version": recovered["state_version"]}, headers={"Idempotency-Key": f"check-{index}"})
                    assert response.status_code == 200, response.text
                    recovered = response.json()
                    if recovered["state"] == "failed":
                        break
                    time.sleep(0.1)
                assert recovered["state"] == "failed", recovered
                assert recovered["terminal_reason"] == "CONTROL_INTERRUPTED"
                assert recovered["recovery_evidence"]["status"] == "confirmed_exited"
                assert len(client.get("/attempts").json()["items"]) == 1
                assert recovered["snapshot_digest"] == submitted["snapshot_digest"]
        finally:
            stop(restarted)
    finally:
        stop(child)


@pytest.mark.parametrize("phase", ["before_spawn", "after_spawn"])
def test_real_sigkill_at_two_phase_launch_boundaries(tmp_path, phase):
    worker_python = ROOT / "adapters" / "mlx_text" / ".venv" / "bin" / "python"
    if not worker_python.is_file():
        pytest.skip("此主机没有已准备MLX环境")
    source = tmp_path / "授权输入"
    source.mkdir()
    model_path = make_model(source / "控制夹具模型")
    data = tmp_path / "启动故障数据"
    args = ("--import-root", str(source), "--worker-python", str(worker_python), "--worker-script", str(Path(__file__).with_name("fixture_worker.py")), "--preflight-script", str(Path(__file__).with_name("fixture_preflight.py")))
    child, connection = launch(data, *args, entrypoint=Path(__file__).with_name("crash_control_entrypoint.py"), env_extra={"CONTROL_TEST_CRASH_PHASE": phase})
    try:
        with client_for(connection) as client:
            project = client.post("/projects", json={"name": "启动故障"}).json()
            plan = client.post("/models/import-plans", json={"project_id": project["id"], "path": str(model_path)}).json()
            model = client.post("/models/imports", json={"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}, headers={"Idempotency-Key": "model"}).json()
            task = client.post("/tasks", json={"project_id": project["id"], "kind": "text", "operation": "generate", "name": "禁止提前执行"}).json()
            draft = task["draft"]
            draft["model_id"] = model["id"]
            draft["input"]["prompt"] = "__wait__"
            task = client.patch(f"/tasks/{task['id']}/draft", json={"draft": draft, "expected_revision": 1}).json()
            checked = client.post(f"/tasks/{task['id']}/preflight", json={"draft_revision": task["draft_revision"]}).json()
            assert checked["can_submit"], checked
            try:
                client.post(f"/tasks/{task['id']}/attempts", json={"preflight_id": checked["id"], "expected_revision": task["draft_revision"]}, headers={"Idempotency-Key": "run"})
            except httpx.HTTPError:
                pass
        child.wait(timeout=10)
        assert child.returncode == -signal.SIGKILL
        restarted, recovered_connection = launch(data, *args)
        try:
            with client_for(recovered_connection) as client:
                records = client.get("/attempts").json()["items"]
                assert len(records) == 1
                attempt = client.get("/attempts/" + records[0]["id"]).json()
                assert attempt["stop_status"] == "unknown" and not attempt["output_text"]
                for index in range(60):
                    response = client.post(f"/attempts/{attempt['id']}/reconcile", json={"expected_state_version": attempt["state_version"]}, headers={"Idempotency-Key": f"reconcile-{index}"})
                    assert response.status_code == 200, response.text
                    attempt = response.json()
                    if attempt["state"] == "failed":
                        break
                    time.sleep(0.05)
                assert attempt["state"] == "failed", attempt
                assert attempt["recovery_evidence"]["status"] == "confirmed_exited"
                assert not (data / "runs" / attempt["id"] / "start-authorized.json").exists()
                assert not attempt["output_text"]
        finally:
            stop(restarted)
    finally:
        stop(child)


def startup_failure(directory, *extra, entrypoint=None):
    """走真实 CLI 子进程并收集失败首行，不能经过成功端口等待器。"""
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "services" / "control"))
    command = [sys.executable, str(entrypoint)] if entrypoint else [sys.executable, "-m", "ailab_control"]
    child = subprocess.Popen([*command, "--data-dir", str(directory), "--parent-pid", str(os.getpid()), *extra],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    try:
        stdout, stderr = child.communicate(timeout=12)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
    (directory.parent / "startup-stdout.raw").write_bytes(stdout)
    (directory.parent / "startup-stderr.raw").write_bytes(stderr)
    (directory.parent / "startup-process.json").write_text(json.dumps({"pid": child.pid, "exit_code": child.returncode}))
    assert child.returncode == 1
    with pytest.raises(ProcessLookupError):
        os.kill(child.pid, 0)
    return child.pid, stdout, stderr


def test_startup_real_migration_conflict_preserves_database_receipt_and_no_connection_file(tmp_path):
    import hashlib
    import sqlite3
    from test_database_migrations import V1_SQL

    data = tmp_path / "迁移冲突库"
    data.mkdir()
    database = data / "control.sqlite3"
    with sqlite3.connect(database) as old:
        old.executescript(V1_SQL)
        old.execute("CREATE INDEX resources_kind ON resources(kind)")
    before = database.read_bytes()
    token_file = tmp_path / "连接.json"
    pid, stdout, stderr = startup_failure(data, "--token-file", str(token_file))
    assert stdout.endswith(b"\n") and len(stdout) <= 4096 and len(stdout.splitlines()) == 1
    assert json.loads(stdout) == {"status": "failed", "code": "DATABASE_MIGRATION_FAILED", "pid": pid}
    assert str(data).encode() not in stdout and b"token" not in stdout and b"Traceback" not in stdout
    assert b"resources_kind" in stderr and b"Traceback" in stderr
    assert database.read_bytes() == before
    assert not token_file.exists()
    with sqlite3.connect(database) as after:
        assert after.execute("SELECT version FROM schema_version").fetchone()[0] == 1
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert after.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 0
    receipt_path, = data.glob("migrations/v1-to-v2-*/receipt.json")
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "failed_rolled_back" and receipt["committed"] is False
    backup = receipt_path.parent / receipt["backup"]["path"]
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == receipt["backup"]["sha256"]
    assert backup.stat().st_size == receipt["backup"]["size"]
    with sqlite3.connect(backup) as saved, sqlite3.connect(database) as source:
        assert saved.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert list(saved.iterdump()) == list(source.iterdump())
    import fcntl
    with (data / "control.lock").open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_UN)
    assert not list(data.glob("runs/**/start-authorized.json"))
    (tmp_path / "migration-evidence.json").write_text(json.dumps({
        "pid": pid, "exit_code": 1, "pid_exited": True, "lock_released": True,
        "database_unchanged": True, "database_sha256": hashlib.sha256(before).hexdigest(),
        "backup_sha256": receipt["backup"]["sha256"], "backup_logical_equal": True,
        "receipt_status": receipt["status"], "committed": receipt["committed"],
        "connection_file_absent": True,
    }, ensure_ascii=False, indent=2))


def test_startup_real_v1_upgrade_keeps_success_handshake_compatible(tmp_path):
    import sqlite3
    from test_database_migrations import V1_SQL

    data = tmp_path / "可迁移空库"
    data.mkdir()
    with sqlite3.connect(data / "control.sqlite3") as old:
        old.executescript(V1_SQL)
    token_file = tmp_path / "连接.json"
    child, connection = launch(data, "--token-file", str(token_file), "--parent-pid", str(os.getpid()))
    try:
        assert set(connection) == {"pid", "port", "token", "host_token"}
        assert connection["pid"] == child.pid
        assert len(connection["token"]) >= 32 and len(connection["host_token"]) >= 32
        with sqlite3.connect(data / "control.sqlite3") as upgraded:
            assert upgraded.execute("SELECT version FROM schema_version").fetchone()[0] == 4
        receipts = [json.loads(path.read_text()) for path in data.glob("migrations/*/receipt.json")]
        assert len(receipts) == 3 and all(record["status"] == "succeeded" for record in receipts)
    finally:
        stop(child)
    assert child.returncode in (0, -signal.SIGTERM)
    assert not token_file.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(child.pid, 0)


@pytest.mark.parametrize("committed,migration_path", [(False, None), (False, "private-migration-path"), (True, "private-migration-path")])
def test_startup_known_fault_omits_details_and_preserves_stderr(tmp_path, committed, migration_path):
    entrypoint = tmp_path / "故障入口.py"
    entrypoint.write_text("from ailab_control import __main__ as entry\nfrom ailab_control.storage import Fault\n"
                         "def fail(settings):\n"
                         f"    raise Fault('DATABASE_MIGRATION_FAILED', 'private-exception-token', 503, committed={committed!r}, migration_path={migration_path!r})\n"
                         "entry.create_app = fail\nentry.main()\n")
    token_file = tmp_path / "连接.json"
    pid, stdout, stderr = startup_failure(tmp_path / "库", "--token-file", str(token_file), entrypoint=entrypoint)
    assert json.loads(stdout) == {"status": "failed", "code": "DATABASE_MIGRATION_FAILED", "pid": pid}
    assert b"private" not in stdout and b"Traceback" not in stdout
    assert b"private-exception-token" in stderr and b"Traceback" in stderr
    assert stderr.count(b"ailab_control.storage.Fault: private-exception-token") == 1
    assert not token_file.exists()


@pytest.mark.parametrize("exception", ["Fault('DATABASE_VERSION_UNSUPPORTED', 'private-unknown-fault')", "RuntimeError('private-unknown-runtime')"])
def test_startup_unknown_fault_has_no_handshake_and_preserves_stderr(tmp_path, exception):
    entrypoint = tmp_path / "未知故障入口.py"
    entrypoint.write_text("from ailab_control import __main__ as entry\nfrom ailab_control.storage import Fault\n"
                         f"def fail(settings):\n    raise {exception}\n"
                         "entry.create_app = fail\nentry.main()\n")
    token_file = tmp_path / "连接.json"
    _, stdout, stderr = startup_failure(tmp_path / "库", "--token-file", str(token_file), entrypoint=entrypoint)
    assert not stdout
    assert b"private-unknown" in stderr and b"Traceback" in stderr
    assert not token_file.exists()
