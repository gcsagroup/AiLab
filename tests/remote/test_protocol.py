"""真实回环 HTTP、独立进程、持久 SQLite 和文件故障；不声明 GPU 验收。"""

from concurrent.futures import ThreadPoolExecutor
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import selectors
import signal
import sqlite3
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/control"))
from ailab_control.remote.client import LoopbackClient, LoopbackTarget
from ailab_control.remote.protocol import MAX_CHUNK, ProtocolError, digest, process_identity, owns_process
from ailab_control.remote.server import Executor
import ailab_control.remote.server as server_module


class RunningServer:
    def __init__(self, root):
        self.root = root
        self.data = root / "执行服务 数据"
        self.token = secrets.token_urlsafe(48)
        self.token_file = root / "临时凭证"
        self.token_file.write_text(self.token)
        self.token_file.chmod(0o600)
        self.port = 0
        self.process = None
        self.logs = []
        self.start()

    def start(self):
        error = (self.root / f"server-{len(self.logs)}.stderr.log").open("wb")
        self.logs.append(error)
        self.process = subprocess.Popen([sys.executable, "-m", "ailab_control.remote", "--data-dir", str(self.data),
                                         "--token-file", str(self.token_file), "--port", str(self.port), "--loopback-contract-only"],
                                        cwd=self.root, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "services/control")},
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=error, text=True)
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            assert selector.select(10), "执行服务未返回启动握手"
            line = self.process.stdout.readline()
            assert line, "执行服务启动失败：" + Path(error.name).read_text()
            facts = json.loads(line)
        finally:
            selector.close()
        self.port = facts["port"]
        self.executor_id = facts["executor_id"]
        self.client = LoopbackClient(LoopbackTarget(f"http://127.0.0.1:{self.port}", self.executor_id, self.token), self.root / "连接记录", timeout=1)
        deadline = time.monotonic() + 5
        while True:
            try:
                self.client.identity()
                break
            except ProtocolError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.02)

    def stop(self, hard=False):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGKILL if hard else signal.SIGTERM)
            self.process.wait(timeout=8)
        if self.process:
            self.process.stdout.close()

    def cleanup(self):
        self.stop()
        if (self.data / "executor.sqlite3").exists():
            with sqlite3.connect(self.data / "executor.sqlite3") as database:
                attempts = [json.loads(row[0]) for row in database.execute("SELECT body FROM attempts")]
            for attempt in attempts:
                for process in [attempt.get("process", {}), *attempt.get("child_processes", [])]:
                    if owns_process(process):
                        try:
                            os.killpg(process["pid"], signal.SIGTERM)
                        except ProcessLookupError:
                            pass
        for stream in self.logs:
            stream.close()


@pytest.fixture
def server(tmp_path):
    value = RunningServer(tmp_path)
    try:
        yield value
    finally:
        value.cleanup()


def test_cli_accepts_full_512_character_token_and_rejects_non_visible_input(server):
    server.stop()
    server.token = 'T' * 512
    server.token_file.write_text(server.token + '\n')
    server.start()
    assert server.client.identity()['executor_id'] == server.executor_id
    server.stop()
    for token in ['T' * 513, 'T' * 31, 'T' * 32 + ' ', 'T' * 32 + '\n\n']:
        server.token_file.write_text(token)
        result = subprocess.run([sys.executable, '-m', 'ailab_control.remote', '--data-dir', str(server.data),
                                 '--token-file', str(server.token_file), '--loopback-contract-only'],
                                cwd=server.root, env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'services/control')},
                                capture_output=True, text=True, timeout=5)
        assert result.returncode == 2 and not result.stdout
        assert token not in result.stderr


def test_collection_continues_same_attempt_after_link_publish_is_killed(server, tmp_path):
    _, blob = input_file(server, b'complete original artifact after collector crash')
    attempt = wait(server, server.client.submit(snapshot(server, [blob]), 'link-crash-run')['id'])
    destination = tmp_path / '仅补收目标'; destination.mkdir()
    collection = 'collection-' + secrets.token_hex(16)
    child = '''
import os, signal, sys
from pathlib import Path
from ailab_control.remote.client import LoopbackClient, LoopbackTarget
client = LoopbackClient(LoopbackTarget(sys.argv[1], sys.argv[2], Path(sys.argv[3]).read_text()), Path(sys.argv[4]))
original = os.link
def killed(source, target, *args, **kwargs):
    original(source, target, *args, **kwargs)
    if str(source).endswith('.part'):
        os.kill(os.getpid(), signal.SIGKILL)
os.link = killed
client.collect(sys.argv[5], sys.argv[6], sys.argv[7], Path(sys.argv[8]))
'''
    killed = subprocess.run([sys.executable, '-c', child, server.client.target.origin, server.executor_id,
                             str(server.token_file), str(server.client.state_dir), attempt['id'], attempt['manifest_sha256'], collection, str(destination)],
                            env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(ROOT / 'services/control')},
                            capture_output=True, text=True, timeout=15)
    assert killed.returncode == -signal.SIGKILL, killed.stderr
    staging = destination / ('.' + collection + '.tmp')
    part, target = staging / 'file-000.bin.part', staging / 'file-000.bin'
    assert part.samefile(target) and part.stat().st_nlink == 2
    receipt = server.client.collect(attempt['id'], attempt['manifest_sha256'], collection, destination)
    assert receipt['status'] == 'succeeded'
    final = destination / collection
    assert not (final / part.name).exists() and (final / target.name).stat().st_nlink == 1
    assert server.client.attempt(attempt['id']) == attempt
    assert attempt['run_count'] == 1
    assert server.client.collect(attempt['id'], attempt['manifest_sha256'], collection, destination)['status'] == 'succeeded'


@pytest.mark.parametrize('damage', ['unknown_link', 'wrong_digest'])
def test_collection_link_recovery_preserves_unknown_or_damaged_files(tmp_path, damage):
    part, target, extra = tmp_path / 'file.part', tmp_path / 'file', tmp_path / 'unrelated'
    content = b'original complete bytes'; part.write_bytes(content); part.chmod(0o400)
    os.link(part, target)
    if damage == 'unknown_link':
        os.link(part, extra)
    item = {'size': len(content), 'sha256': hashlib.sha256(content).hexdigest() if damage == 'unknown_link' else '0' * 64}
    with pytest.raises(ProtocolError):
        LoopbackClient._finish_linked_part(part, target, item)
    assert part.read_bytes() == target.read_bytes() == content
    assert part.stat().st_nlink == (3 if damage == 'unknown_link' else 2)
    assert extra.exists() == (damage == 'unknown_link')


def input_file(server, content="真实回环输入\n".encode()):
    directory = server.root / "授权输入"
    directory.mkdir(exist_ok=True)
    path = directory / ("input-" + secrets.token_hex(3) + ".bin")
    path.write_bytes(content)
    return path, server.client.upload(path, [directory])


def snapshot(server, inputs, steps=4, delay=10):
    return {"schema_version": 1, "attempt_id": "attempt-" + secrets.token_hex(16), "executor_id": server.executor_id,
            "adapter_id": "protocol-copy", "operation": "copy", "inputs": inputs,
            "runtime": {"steps": steps, "step_delay_ms": delay}}


def wait(server, attempt_id, predicate=lambda value: value["state"] in {"succeeded", "failed", "cancelled"}, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = server.client.attempt(attempt_id)
        if predicate(value):
            return value
        time.sleep(0.02)
    raise AssertionError(value)


def test_actual_process_executes_once_and_events_resume_in_order(server):
    path, blob = input_file(server, "第一行真实字节\n第二行".encode())
    request = snapshot(server, [blob], steps=8)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: server.client.submit(request, "same-submit"), range(8)))
    assert {item["id"] for item in results} == {request["attempt_id"]}
    result = wait(server, request["attempt_id"])
    assert result["state"] == "succeeded" and result["run_count"] == 1, result
    assert result["process"]["pid"] != server.process.pid
    after, received = 0, []
    while True:
        page = server.client.events(result["id"], after, 3)
        received.extend(page["items"])
        after = page["next_cursor"]
        if not page["has_more"]:
            break
    assert [item["sequence"] for item in received] == list(range(1, after + 1))
    assert sum(item["type"] == "registered" for item in received) == 1
    assert server.client.events(result["id"], after)["items"] == []
    first = server.client.sync(result["id"])
    second = server.client.sync(result["id"])
    assert first["events"] == second["events"] == received
    assert server.client.identity()["nvidia_ready"] is False


def test_identity_mismatch_sends_no_input_and_external_endpoint_is_rejected(server):
    directory = server.root / "授权输入"; directory.mkdir()
    path = directory / "private.bin"; path.write_bytes(b"identity-bound-input")
    wrong = LoopbackClient(LoopbackTarget(f"http://127.0.0.1:{server.port}", "executor-" + "f" * 32, server.token), server.root / "错误目标记录")
    with pytest.raises(ProtocolError) as error:
        wrong.upload(path, [directory])
    assert error.value.code == "EXECUTOR_IDENTITY_MISMATCH"
    assert list((server.data / "blobs").iterdir()) == [] and list((server.data / "uploads").iterdir()) == []
    for origin in ("http://localhost:1234", "http://127.0.0.2:1234", "https://127.0.0.1:1234", "http://example.com:1234", "http://127.0.0.1:1234/elsewhere"):
        with pytest.raises(ProtocolError, match="回环"):
            LoopbackTarget(origin, server.executor_id, server.token)
    assert server.token not in repr(server.client.target)


def test_interrupted_upload_resumes_actual_bytes_and_deduplicates(server):
    directory = server.root / "授权输入"; directory.mkdir()
    content = os.urandom(MAX_CHUNK + 37)
    path = directory / "两段输入.bin"; path.write_bytes(content)
    def interrupted(*_args):
        raise OSError("受控上传中断")
    with pytest.raises(OSError):
        server.client.upload(path, [directory], progress=interrupted)
    sha = hashlib.sha256(content).hexdigest()
    status = server.client._request("GET", "/blobs/" + sha)
    assert status["offset"] == MAX_CHUNK and not status["complete"]
    blob = server.client.upload(path, [directory])
    assert (server.data / "blobs" / sha).read_bytes() == content
    before = (server.data / "blobs" / sha).stat().st_mtime_ns
    assert server.client.upload(path, [directory]) == blob
    assert (server.data / "blobs" / sha).stat().st_mtime_ns == before
    assert list((server.data / "uploads").iterdir()) == []


def test_attempt_id_digest_and_key_conflicts_never_start_another_process(server):
    _, blob = input_file(server)
    request = snapshot(server, [blob], steps=30, delay=15)
    result = server.client.submit(request, "original-key")
    mutations = [(request, "different-key"), ({**request, "attempt_id": "attempt-" + secrets.token_hex(16)}, "original-key"),
                 ({**request, "runtime": {"steps": 1, "step_delay_ms": 0}}, "original-key")]
    for altered, key in mutations:
        with pytest.raises(ProtocolError) as error:
            server.client.submit(altered, key)
        assert error.value.code == "ATTEMPT_REPLAY_CONFLICT"
    with pytest.raises(ProtocolError) as error:
        server.client._request("POST", "/attempts", payload={"snapshot": request, "snapshot_sha256": "0" * 64}, key="original-key")
    assert error.value.code == "SNAPSHOT_DIGEST_MISMATCH"
    assert wait(server, result["id"])["run_count"] == 1
    with sqlite3.connect(server.data / "executor.sqlite3") as database:
        assert database.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1


def test_service_crash_keeps_actual_worker_and_same_attempt_after_restart(server):
    _, blob = input_file(server)
    request = snapshot(server, [blob], steps=100, delay=20)
    initial = server.client.submit(request, "persistent-attempt")
    running = wait(server, initial["id"], lambda item: item["state"] == "running")
    identity = running["process"]
    server.stop(hard=True)
    assert owns_process(identity), "连接服务退出不应停止独立执行"
    server.start()
    again = server.client.submit(request, "persistent-attempt")
    assert again["process"] == identity
    result = wait(server, initial["id"])
    assert result["state"] == "succeeded" and result["run_count"] == 1
    events = server.client.events(result["id"])["items"]
    assert sum(item["type"] == "registered" for item in events) == 1


def test_cancel_disconnected_preserves_unknown_and_reconnect_queries_original(server):
    _, blob = input_file(server)
    result = server.client.submit(snapshot(server, [blob], steps=100, delay=40), "cancel-original")
    running = wait(server, result["id"], lambda item: item["state"] == "running")
    client = server.client
    client.sync(result["id"])
    server.stop(hard=True)
    unknown = client.cancel(result["id"], running["state_version"], "cancel-command")
    assert unknown["state"] == "running" and unknown["stop_status"] == "unknown" and unknown["connection_state"] == "disconnected"
    assert owns_process(running["process"])
    server.start()
    reconciled = server.client.sync(result["id"])
    assert reconciled["id"] == result["id"] and reconciled["run_count"] == 1
    current = server.client.attempt(result["id"])
    server.client.cancel(result["id"], current["state_version"], "cancel-command")
    cancelled = wait(server, result["id"])
    assert cancelled["state"] == "cancelled" and cancelled["stop_status"] == "confirmed"


def test_failed_collection_resumes_original_manifest_without_new_computation(server):
    content = os.urandom(MAX_CHUNK + 57)
    _, blob = input_file(server, content)
    result = server.client.submit(snapshot(server, [blob]), "collect-original")
    result = wait(server, result["id"])
    assert result["state"] == "succeeded", result
    with sqlite3.connect(server.data / "executor.sqlite3") as database:
        original = database.execute("SELECT body FROM attempts WHERE id=?", (result["id"],)).fetchone()[0]
    destination = server.root / "授权补收"; destination.mkdir()
    collection_id = "collection-" + secrets.token_hex(16)
    def disk_full(*_args):
        raise OSError(errno.ENOSPC, "受控磁盘满")
    with pytest.raises(OSError):
        server.client.collect(result["id"], result["manifest_sha256"], collection_id, destination, progress=disk_full)
    assert not (destination / collection_id).exists()
    receipt = server.client.collect(result["id"], result["manifest_sha256"], collection_id, destination)
    assert receipt["status"] == "succeeded" and len(receipt["failures"]) == 1
    assert (destination / collection_id / "file-000.bin").read_bytes() == content
    assert server.client.collect(result["id"], result["manifest_sha256"], collection_id, destination)["status"] == "succeeded"
    with sqlite3.connect(server.data / "executor.sqlite3") as database:
        assert database.execute("SELECT body FROM attempts WHERE id=?", (result["id"],)).fetchone()[0] == original
        assert database.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1


def test_upload_paths_and_declared_quota_are_enforced(server, tmp_path, monkeypatch):
    directory = server.root / "授权输入"; directory.mkdir()
    outside = server.root / "不可读取.bin"; outside.write_bytes(b"private")
    link = directory / "link.bin"; link.symlink_to(outside)
    for path in (outside, link, directory / ".." / outside.name):
        with pytest.raises(ProtocolError):
            server.client.upload(path, [directory])
    isolated = Executor(tmp_path / "配额服务", secrets.token_urlsafe(48))
    try:
        monkeypatch.setattr(server_module, "MAX_STORAGE", 3)
        with pytest.raises(ProtocolError) as error:
            isolated.upload(hashlib.sha256(b"1234").hexdigest(), 4, 0, b"")
        assert error.value.code == "STORAGE_QUOTA_EXCEEDED"
        assert isolated.store.db.execute("SELECT count(*) FROM blobs").fetchone()[0] == 0
    finally:
        isolated.close()


def test_wrong_credentials_hash_and_chunk_replay_leave_no_ready_input(server):
    wrong = LoopbackClient(LoopbackTarget(f"http://127.0.0.1:{server.port}", server.executor_id, secrets.token_urlsafe(48)), server.root / "失效凭证记录")
    with pytest.raises(ProtocolError) as error:
        wrong.identity()
    assert error.value.code == "UNAUTHORIZED"
    sha = hashlib.sha256(b"abc").hexdigest()
    server.client._request("PUT", f"/blobs/{sha}?size=3&offset=0", content=b"a")
    with pytest.raises(ProtocolError) as error:
        server.client._request("PUT", f"/blobs/{sha}?size=3&offset=0", content=b"z")
    assert error.value.code == "UPLOAD_REPLAY_CONFLICT"
    with pytest.raises(ProtocolError) as error:
        server.client._request("PUT", f"/blobs/{sha}?size=3&offset=1", content=b"zz")
    assert error.value.code == "BLOB_HASH_MISMATCH"
    assert server.client._request("GET", "/blobs/" + sha)["offset"] == 0
    assert not (server.data / "blobs" / sha).exists()


def test_input_path_manifest_conflicts_and_output_reservation_block_before_spawn(server, tmp_path, monkeypatch):
    _, blob = input_file(server)
    for path in ("../escape", "/absolute", "model/../config.json", "model\\config.json", "model//config.json"):
        request = snapshot(server, [{**blob, "path": path}])
        with pytest.raises(ProtocolError) as error:
            server.client.submit(request, "unsafe-" + secrets.token_hex(4))
        assert error.value.code == "INPUT_PATH_INVALID"
    request = snapshot(server, [{**blob, "path": "model"}, {**blob, "path": "model/config.json"}])
    with pytest.raises(ProtocolError) as error:
        server.client.submit(request, "overlapping-paths")
    assert error.value.code == "INPUT_PATH_CONFLICT"
    executor = Executor(tmp_path / "产物预留服务", secrets.token_urlsafe(48))
    try:
        monkeypatch.setattr(server_module, "MAX_STORAGE", 3)
        sha = hashlib.sha256(b"ab").hexdigest()
        executor.upload(sha, 2, 0, b"ab")
        request = {**snapshot(server, [{"sha256": sha, "size": 2}]), "executor_id": executor.executor_id}
        with pytest.raises(ProtocolError) as error:
            executor.submit({"snapshot": request, "snapshot_sha256": digest(request)}, "no-output-space")
        assert error.value.code == "STORAGE_QUOTA_EXCEEDED"
        assert executor.store.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    finally:
        executor.close()


def test_collection_refuses_tampered_source_and_never_overwrites_existing_directory(server):
    _, blob = input_file(server, b"immutable output")
    result = wait(server, server.client.submit(snapshot(server, [blob]), "immutable-collect")["id"])
    destination = server.root / "授权补收"; destination.mkdir()
    occupied = "collection-" + secrets.token_hex(16)
    (destination / occupied).mkdir()
    sentinel = destination / occupied / "保留.txt"; sentinel.write_text("已有用户文件")
    with pytest.raises(ProtocolError) as error:
        server.client.collect(result["id"], result["manifest_sha256"], occupied, destination)
    assert error.value.code == "DESTINATION_EXISTS" and sentinel.read_text() == "已有用户文件"
    original = server.data / "runs" / result["id"] / "output/file-000.bin"
    original.chmod(0o600); original.write_bytes(b"damaged output!!")
    with pytest.raises(ProtocolError) as error:
        server.client.collect(result["id"], result["manifest_sha256"], "collection-" + secrets.token_hex(16), destination)
    assert error.value.code in {"FILE_HASH_MISMATCH", "FILE_SIZE_MISMATCH"}
    assert server.client.attempt(result["id"])["run_count"] == 1


def test_stale_kernel_identity_does_not_adopt_or_stop_live_unrelated_process(tmp_path):
    executor = Executor(tmp_path / "身份验证服务", secrets.token_urlsafe(48))
    unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
    try:
        actual = process_identity(unrelated.pid)
        assert actual["status"] == "present" and actual["pgid"] == unrelated.pid
        stale = {**actual, "identity_digest": "0" * 64}
        attempt_id = "attempt-" + secrets.token_hex(16)
        value = {"id": attempt_id, "state": "running", "state_version": 3, "run_count": 1, "stop_status": "not_requested",
                 "compute_outcome": "pending", "process": stale, "last_event_sequence": 0, "snapshot_sha256": "1" * 64}
        with executor.store.transaction():
            executor.store.db.execute("INSERT INTO attempts VALUES(?,?,?,?)", (attempt_id, "1" * 64, "stale-identity", json.dumps(value)))
        result = executor.reconcile(attempt_id)
        assert result["state"] == "running" and result["recovery_required"]
        cancelled = executor.cancel(attempt_id, {"expected_state_version": result["state_version"]}, "cancel-stale")
        assert cancelled["stop_status"] == "unknown"
        assert unrelated.poll() is None
        assert process_identity(unrelated.pid) == actual
    finally:
        unrelated.terminate(); unrelated.wait(timeout=3)
        executor.close()


def test_redirects_are_not_followed(server):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    observed = []
    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            observed.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/changed-target")
            self.end_headers()
        def log_message(self, *_args):
            pass
    redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    thread = threading.Thread(target=redirect.serve_forever, daemon=True); thread.start()
    try:
        client = LoopbackClient(LoopbackTarget(f"http://127.0.0.1:{redirect.server_port}", server.executor_id, server.token), server.root / "重定向记录")
        with pytest.raises(ProtocolError) as error:
            client.identity()
        assert error.value.code == "REDIRECT_FORBIDDEN"
        assert observed == ["/executor/v1/identity"]
    finally:
        redirect.shutdown(); redirect.server_close(); thread.join(timeout=2)
