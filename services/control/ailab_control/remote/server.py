"""独立持久执行服务；现阶段仅接受明确的回环协议适配器。"""

from contextlib import asynccontextmanager
import fcntl
import hmac
import importlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import tempfile
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .protocol import (PROTOCOL, SCOPE, MAX_CHUNK, MAX_BLOB, MAX_STORAGE, MAX_INPUTS, TERMINAL, ProtocolError,
                       digest, encode, hex_digest, identifier, integer, strict_keys, now, safe_file, file_hash,
                       write_json, sync_directory, process_identity, owns_process, relative_path, process_group_absent,
                       transport_scope, bound_transport)
from .store import Store


ADAPTERS = {"protocol-copy": {"operation": "copy", "validation_scope": SCOPE, "model_execution": False,
                            "controls": {"cancel": True, "recollect": True, "pause": False, "resume": False}},
            "nvidia-text": {"operations": ["generate", "train"], "validation_scope": "requires_cuda_verification", "model_execution": True,
                            "controls": {"cancel": True, "recollect": True, "pause": False, "resume": False}}}


def nvidia_adapter():
    try:
        return importlib.import_module("adapters.nvidia_text.adapter")
    except ImportError:
        raise ProtocolError("ADAPTER_UNAVAILABLE", "NVIDIA 适配器或其固定依赖尚未安装。", 409) from None


def validate_snapshot(value, executor_id, transport="loopback_http"):
    strict_keys(value, {"schema_version", "attempt_id", "executor_id", "adapter_id", "operation", "inputs", "runtime"}, {"input", "transport"})
    bound_transport(value, transport)
    if value["schema_version"] != PROTOCOL or value["executor_id"] != executor_id:
        raise ProtocolError("EXECUTOR_IDENTITY_MISMATCH", "执行快照未绑定当前服务身份。", 409)
    identifier(value["attempt_id"])
    capability = ADAPTERS.get(value["adapter_id"])
    if capability is None or value["operation"] not in capability.get("operations", [capability.get("operation")]):
        raise ProtocolError("ADAPTER_UNAVAILABLE", "此协议入口尚未登记所请求的模型执行适配器。", 409)
    inputs = value["inputs"]
    if type(inputs) is not list or not 1 <= len(inputs) <= MAX_INPUTS:
        raise ProtocolError("INPUT_LIMIT", "输入数量超出当前协议限制。")
    paths = set()
    for item in inputs:
        strict_keys(item, {"sha256", "size"}, {"path"})
        hex_digest(item["sha256"])
        integer(item["size"], 0, MAX_BLOB)
        if "path" in item:
            path = relative_path(item["path"])
            if path in paths or any(path.startswith(other + "/") or other.startswith(path + "/") for other in paths):
                raise ProtocolError("INPUT_PATH_CONFLICT", "输入清单存在重复或父子路径冲突。", 409)
            paths.add(path)
    if sum(item["size"] for item in inputs) > MAX_STORAGE:
        raise ProtocolError("INPUT_LIMIT", "输入总字节超过限制。")
    if value["adapter_id"] == "protocol-copy":
        if value.get("input") or any(item["size"] > 64 * 1024 * 1024 for item in inputs):
            raise ProtocolError("PROTOCOL_FIXTURE_LIMIT", "复制夹具只接受受限小文件，不执行模型输入。")
        strict_keys(value["runtime"], {"steps", "step_delay_ms"})
        integer(value["runtime"]["steps"], 1, 100)
        integer(value["runtime"]["step_delay_ms"], 0, 200)
    else:
        if any("path" not in item for item in inputs):
            raise ProtocolError("INPUT_PATH_REQUIRED", "模型文件需要明确的受限相对名称。")
        nvidia_adapter().validate_snapshot(value)
    return value


def execution_reservation(snapshot):
    size = sum(item["size"] for item in snapshot["inputs"])
    if snapshot["adapter_id"] == "protocol-copy":
        return 0, size
    limit = nvidia_adapter().output_reserve_bytes(snapshot)
    integer(limit, 1, MAX_STORAGE)
    return size, limit


def command_key(key):
    if type(key) is not str or not 1 <= len(key) <= 160 or not all(32 < ord(character) < 127 for character in key):
        raise ProtocolError("IDEMPOTENCY_KEY_REQUIRED", "请提供有界命令幂等键。")
    return key


class Executor:
    def __init__(self, root, token, transport="loopback_http"):
        self.transport = transport
        self.validation_scope = transport_scope(transport)
        self.root = Path(root).absolute()
        if self.root.is_symlink():
            raise ProtocolError("UNSAFE_DATA_DIRECTORY", "执行服务数据根不能是符号链接。")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (self.root / "control.sqlite3").exists():
            raise ProtocolError("MAIN_LIBRARY_FORBIDDEN", "执行服务必须使用独立数据目录。")
        self.root = self.root.resolve()
        self.root.chmod(0o700)
        if not isinstance(token, str) or not 32 <= len(token) <= 512 or not all(33 <= ord(char) <= 126 for char in token):
            raise ProtocolError("INVALID_CREDENTIAL", "执行服务需要独立的临时测试凭证。")
        self.token = token
        descriptor = os.open(self.root / "executor.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.instance_lock = os.fdopen(descriptor, "w")
        try:
            fcntl.flock(self.instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.instance_lock.close()
            raise ProtocolError("EXECUTOR_BUSY", "此执行数据目录已有服务运行。", 409) from None
        try:
            for name in ("blobs", "uploads", "runs"):
                path = self.root / name
                if path.is_symlink():
                    raise ProtocolError("UNSAFE_DATA_DIRECTORY", "执行数据子目录不能是符号链接。")
                path.mkdir(exist_ok=True, mode=0o700)
            self.store = Store(self.root, transport)
            self.executor_id = self.store.executor_id
            self.blob_locks = {}
            self.blob_lock = threading.Lock()
            self.processes = {}
            self.probe_lock = threading.Lock()
            self.closed = False
            self.recover()
        except BaseException:
            self.instance_lock.close()
            raise

    def identity(self):
        adapters = json.loads(encode(ADAPTERS))
        adapters["protocol-copy"]["validation_scope"] = self.validation_scope
        try:
            adapters["nvidia-text"].update(installed=True, source_code_digest=nvidia_adapter().source_identity())
        except ProtocolError:
            adapters["nvidia-text"].update(installed=False, source_code_digest=None)
        return {"protocol_version": PROTOCOL, "executor_id": self.executor_id, "validation_scope": self.validation_scope,
                "transport": self.transport, "network_remote_ready": self.transport == "https", "nvidia_ready": False, "adapters": adapters,
                "limits": {"chunk_bytes": MAX_CHUNK, "blob_bytes": MAX_BLOB, "storage_bytes": MAX_STORAGE, "inputs": MAX_INPUTS}}

    def authenticate(self, request):
        if self.transport == "https" and request.url.scheme != "https":
            raise ProtocolError("TLS_REQUIRED", "此执行服务只接受直接 HTTPS 连接。", 403)
        if not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + self.token):
            raise ProtocolError("UNAUTHORIZED", "执行服务凭证失效或不正确。", 401)
        if request.headers.get("x-ailab-executor") != self.executor_id:
            raise ProtocolError("EXECUTOR_IDENTITY_MISMATCH", "执行服务身份与登记目标不一致。", 409)

    def nvidia_probe(self):
        # 只运行已安装固定探测器；每次由新进程实际确认 CUDA 并释放进程资源。
        expected = nvidia_adapter().source_identity()
        root = Path(__file__).resolve().parents[4]
        environment = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': os.pathsep.join([str(root / 'services/control'), str(root)]),
                       'PYTHONUNBUFFERED': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
                       'HF_DATASETS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false'}
        if not self.probe_lock.acquire(blocking=False):
            raise ProtocolError('PROBE_BUSY', '设备探测正在进行，请稍后重试。', 409)
        try:
            with tempfile.TemporaryFile() as output:
                process = subprocess.Popen([sys.executable, str(root / 'workers/nvidia_worker.py'), '--mode', 'probe'],
                                           stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                                           env=environment, cwd=self.root, start_new_session=True)
                identity = process_identity(process.pid)
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    if owns_process(identity):
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
                    raise ProtocolError('NVIDIA_PROBE_TIMEOUT', 'NVIDIA 探测超时，本次探测进程已停止。', 503) from None
                if not process_group_absent(process.pid):
                    raise ProtocolError('NVIDIA_PROBE_PROCESS_UNCONFIRMED', '探测进程组退出尚未确认。', 503)
                output.seek(0)
                raw = output.read(256 * 1024 + 1)
                if process.returncode != 0 or len(raw) > 256 * 1024:
                    raise ProtocolError('NVIDIA_PROBE_FAILED', 'NVIDIA 探测没有返回有界成功结果。', 503)
                try:
                    result = json.loads(raw)
                    if (not isinstance(result, dict) or type(result.get('ready')) is not bool or result.get('source_code_digest') != expected
                            or nvidia_adapter().source_identity() != expected):
                        raise ValueError()
                except (ValueError, TypeError):
                    raise ProtocolError('NVIDIA_PROBE_IDENTITY_CHANGED', '探测结果与已安装适配器身份不一致。', 409) from None
                return result
        finally:
            self.probe_lock.release()

    def _blob_lock(self, sha):
        with self.blob_lock:
            return self.blob_locks.setdefault(sha, threading.Lock())

    def _execution_reserved(self):
        return self.store.db.execute("SELECT coalesce(sum(coalesce(json_extract(body,'$.input_reserved_bytes'),0)+coalesce(json_extract(body,'$.output_reserved_bytes'),0)),0) FROM attempts").fetchone()[0]

    def blob_status(self, sha):
        hex_digest(sha)
        with self._blob_lock(sha):
            return self._blob_status(sha)

    def _blob_status(self, sha):
        with self.store.lock:
            row = self.store.db.execute("SELECT size,state FROM blobs WHERE sha=?", (sha,)).fetchone()
        if row is None:
            return {"sha256": sha, "complete": False, "size": None, "offset": 0}
        final, part = self.root / "blobs" / sha, self.root / "uploads" / (sha + ".part")
        if final.exists() or final.is_symlink():
            if not final.is_symlink() and part.exists() and not part.is_symlink() and os.path.samefile(final, part):
                part.unlink()
                sync_directory(part.parent)
            descriptor = safe_file(final, row[0], sha)
            os.close(descriptor)
            if row[1] != "complete":
                with self.store.transaction():
                    self.store.db.execute("UPDATE blobs SET state='complete' WHERE sha=?", (sha,))
            return {"sha256": sha, "complete": True, "size": row[0], "offset": row[0]}
        offset = 0
        if part.exists() or part.is_symlink():
            descriptor = safe_file(part)
            offset = os.fstat(descriptor).st_size
            os.close(descriptor)
        if offset > row[0]:
            raise ProtocolError("UPLOAD_SIZE_MISMATCH", "暂存长度超过已登记输入长度。", 409)
        return {"sha256": sha, "complete": False, "size": row[0], "offset": offset}

    def upload(self, sha, size, offset, content):
        hex_digest(sha)
        integer(size, 0, MAX_BLOB)
        integer(offset, 0, size)
        if not isinstance(content, bytes) or len(content) > MAX_CHUNK or offset + len(content) > size:
            raise ProtocolError("CHUNK_LIMIT", "上传分块或总字节超出已声明范围。", 413)
        with self._blob_lock(sha):
            with self.store.transaction():
                row = self.store.db.execute("SELECT size FROM blobs WHERE sha=?", (sha,)).fetchone()
                if row is None:
                    count, reserved = self.store.db.execute("SELECT count(*),coalesce(sum(size),0) FROM blobs").fetchone()
                    reserved += self._execution_reserved()
                    if count >= 4096 or reserved + size > MAX_STORAGE:
                        raise ProtocolError("STORAGE_QUOTA_EXCEEDED", "执行服务输入存储配额不足。", 413)
                    self.store.db.execute("INSERT INTO blobs VALUES(?,?,'uploading')", (sha, size))
                elif row[0] != size:
                    raise ProtocolError("BLOB_DECLARATION_CONFLICT", "同一文件摘要不能声明不同长度。", 409)
            status = self._blob_status(sha)
            final, part = self.root / "blobs" / sha, self.root / "uploads" / (sha + ".part")
            if offset < status["offset"] or status["complete"]:
                descriptor = safe_file(final if status["complete"] else part)
                try:
                    os.lseek(descriptor, offset, os.SEEK_SET)
                    if offset + len(content) > status["offset"] or os.read(descriptor, len(content)) != content:
                        raise ProtocolError("UPLOAD_REPLAY_CONFLICT", "重复分块与已有字节不一致。", 409)
                finally:
                    os.close(descriptor)
                return status
            if offset != status["offset"]:
                raise ProtocolError("UPLOAD_OFFSET_CONFLICT", "请从服务确认的续传位置上传。", 409)
            descriptor = os.open(part, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "r+b") as stream:
                stream.seek(offset)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if offset + len(content) == size:
                if file_hash(part) != sha:
                    part.unlink()
                    with self.store.transaction():
                        self.store.db.execute("DELETE FROM blobs WHERE sha=?", (sha,))
                    raise ProtocolError("BLOB_HASH_MISMATCH", "完整上传的摘要不符，已撤销本次暂存。", 409)
                part.chmod(0o400)
                os.link(part, final)
                part.unlink()
                sync_directory(final.parent)
                sync_directory(part.parent)
                with self.store.transaction():
                    self.store.db.execute("UPDATE blobs SET state='complete' WHERE sha=?", (sha,))
            return self._blob_status(sha)

    def _authorize(self, attempt):
        process = attempt.get("process", {})
        if not owns_process(process):
            return False
        authorization = {"pid": process["pid"], "identity_digest": process["identity_digest"],
                         "snapshot_sha256": attempt["snapshot_sha256"], "launch_nonce": attempt["launch_nonce"]}
        path = self.root / "runs" / attempt["id"] / "authorized.json"
        try:
            write_json(path, authorization, exclusive=True)
        except FileExistsError:
            if json.loads(path.read_text()) != authorization:
                raise ProtocolError("LAUNCH_AUTHORIZATION_CONFLICT", "原执行授权不匹配，拒绝重新授权。", 409)
        return True

    def submit(self, payload, key):
        command_key(key)
        strict_keys(payload, {"snapshot", "snapshot_sha256"})
        snapshot = validate_snapshot(payload["snapshot"], self.executor_id, self.transport)
        snapshot_sha = hex_digest(payload["snapshot_sha256"])
        if digest(snapshot) != snapshot_sha:
            raise ProtocolError("SNAPSHOT_DIGEST_MISMATCH", "快照摘要与请求内容不一致。", 409)
        attempt_id = snapshot["attempt_id"]
        with self.store.transaction():
            by_id = self.store.db.execute("SELECT snapshot_sha,submit_key FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            by_key = self.store.db.execute("SELECT id,snapshot_sha FROM attempts WHERE submit_key=?", (key,)).fetchone()
            if by_id or by_key:
                if by_id != (snapshot_sha, key) or by_key != (attempt_id, snapshot_sha):
                    raise ProtocolError("ATTEMPT_REPLAY_CONFLICT", "执行编号、快照摘要和幂等键必须同时与原提交一致。", 409)
                return self.store.get(attempt_id)
            if self.store.db.execute("SELECT 1 FROM commands WHERE key=?", (key,)).fetchone():
                raise ProtocolError("IDEMPOTENCY_CONFLICT", "该命令键已经用于其他动作。", 409)
        for item in snapshot["inputs"]:
            state = self.blob_status(item["sha256"])
            if not state["complete"] or state["size"] != item["size"]:
                raise ProtocolError("INPUT_NOT_READY", "输入尚未完整上传并通过摘要检查。", 409)
        with self.store.transaction():
            # 输入校验期间可能有同一次提交到达，仍由数据库唯一约束前的复核裁决。
            existing = self.store.db.execute("SELECT id,snapshot_sha,submit_key FROM attempts WHERE id=? OR submit_key=?", (attempt_id, key)).fetchall()
            if existing:
                if existing != [(attempt_id, snapshot_sha, key)]:
                    raise ProtocolError("ATTEMPT_REPLAY_CONFLICT", "并发提交身份与原请求不一致。", 409)
                return self.store.get(attempt_id)
            if self.store.db.execute("SELECT 1 FROM commands WHERE key=?", (key,)).fetchone():
                raise ProtocolError("IDEMPOTENCY_CONFLICT", "输入检查期间该命令键已被其他动作占用。", 409)
            reserved = self.store.db.execute("SELECT coalesce(sum(size),0) FROM blobs").fetchone()[0]
            count = self.store.db.execute("SELECT count(*) FROM attempts").fetchone()[0]
            input_reserved, expected_output = execution_reservation(snapshot)
            if count >= 4096 or reserved + self._execution_reserved() + input_reserved + expected_output > MAX_STORAGE:
                raise ProtocolError("STORAGE_QUOTA_EXCEEDED", "执行服务无法为此产物预留完整空间。", 413)
            attempt = {"id": attempt_id, "executor_id": self.executor_id, "validation_scope": self.validation_scope, "transport": self.transport,
                       "snapshot_sha256": snapshot_sha, "snapshot": snapshot, "state": "authorizing", "state_version": 1,
                       "compute_outcome": "pending", "stop_status": "not_requested", "created_at": now(), "last_event_sequence": 0,
                       "launch_nonce": secrets.token_hex(32), "run_count": 0, "recovery_required": False,
                       "input_reserved_bytes": input_reserved, "output_reserved_bytes": expected_output}
            self.store.db.execute("INSERT INTO attempts VALUES(?,?,?,?)", (attempt_id, snapshot_sha, key, encode(attempt)))
            self.store.event(attempt, "registered", {"snapshot_sha256": snapshot_sha})
        run = self.root / "runs" / attempt_id
        try:
            run.mkdir(mode=0o700)
            write_json(run / "snapshot.json", snapshot, exclusive=True)
            environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": os.pathsep.join([str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[4])]), "PYTHONUNBUFFERED": "1"}
            with (run / "worker.stderr.log").open("xb") as error:
                process = subprocess.Popen([sys.executable, "-m", "ailab_control.remote.runner", "--data-dir", str(self.root),
                                            "--attempt", attempt_id, "--launch-nonce", attempt["launch_nonce"]],
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=error, env=environment,
                                           cwd=run, start_new_session=True)
            self.processes[attempt_id] = process
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and process.poll() is None:
                current = self.store.get(attempt_id)
                if current.get("process") and self._authorize(current):
                    break
                time.sleep(0.01)
            return self.store.get(attempt_id)
        except BaseException:
            with self.store.transaction():
                current = self.store.get(attempt_id)
                if not current.get("process"):
                    self.store.transition(current, "failed", compute_outcome="failed", terminal_reason="LAUNCH_FAILED")
            raise

    def recover(self):
        with self.store.lock:
            values = [json.loads(row[0]) for row in self.store.db.execute("SELECT body FROM attempts WHERE json_extract(body,'$.state') NOT IN ('succeeded','failed','cancelled')")]
        for attempt in values:
            self.reconcile(attempt["id"])

    def reconcile(self, attempt_id):
        if process := self.processes.get(attempt_id):
            process.poll()
        with self.store.transaction():
            attempt = self.store.get(identifier(attempt_id))
            if attempt["state"] in TERMINAL:
                return attempt
            process = attempt.get("process", {})
            if process and owns_process(process):
                attempt["recovery_required"] = False
                self.store.put(attempt)
                self._authorize(attempt)
            else:
                attempt["recovery_required"] = True
                attempt["process_status"] = "unknown" if not process else process_identity(process.get("pid"))["status"]
                group_absent = bool(process and attempt["process_status"] == "absent" and process_group_absent(process["pid"]))
                for child in attempt.get("child_processes", []):
                    if process_identity(child.get("pid"))["status"] != "absent" or not process_group_absent(child["pid"]):
                        group_absent = False
                if group_absent:
                    directory = self.root / "runs" / attempt_id
                    outcome_path = directory / "outcome.json"
                    outcome = json.loads(outcome_path.read_text()) if outcome_path.is_file() else None
                    if outcome and (outcome.get("attempt_id") != attempt_id or outcome.get("snapshot_sha256") != attempt["snapshot_sha256"]
                                    or outcome.get("identity_digest") != process.get("identity_digest") or outcome.get("state") not in TERMINAL):
                        raise ProtocolError("OUTCOME_IDENTITY_MISMATCH", "停止证据与原执行身份不一致。", 409)
                    if outcome is None and (directory / "manifest.json").is_file() and attempt["compute_outcome"] == "succeeded":
                        manifest = json.loads((directory / "manifest.json").read_text())
                        if manifest.get("attempt_id") != attempt_id or manifest.get("snapshot_sha256") != attempt["snapshot_sha256"]:
                            raise ProtocolError("MANIFEST_CONFLICT", "中断前封存的清单不属于原执行。", 409)
                        for item in manifest["files"]:
                            descriptor = safe_file(directory / "output" / item["name"], item["size"], item["sha256"])
                            os.close(descriptor)
                        attempt.update(manifest=manifest, manifest_sha256=digest(manifest))
                        outcome = {"state": "succeeded", "compute_outcome": "succeeded"}
                    if outcome:
                        fields = {name: outcome[name] for name in ("compute_outcome", "terminal_reason") if name in outcome}
                        if outcome["state"] == "cancelled":
                            fields["stop_status"] = "confirmed"
                        self.store.transition(attempt, outcome["state"], recovery_required=False, process_status="absent", **fields)
                        return attempt
                    self.store.transition(attempt, "failed", compute_outcome="failed", recovery_required=False, terminal_reason="WORKER_EXIT_WITHOUT_OUTCOME")
                    return attempt
                if attempt["stop_status"] in {"pending", "unknown"}:
                    attempt["stop_status"] = "unknown"
                self.store.put(attempt)
            return attempt

    def cancel(self, attempt_id, payload, key):
        identifier(attempt_id)
        command_key(key)
        strict_keys(payload, {"expected_state_version"})
        integer(payload["expected_state_version"], 1, 2**53 - 1)
        request_sha = digest({"attempt_id": attempt_id, "action": "cancel", **payload})
        with self.store.transaction():
            attempt = self.store.get(attempt_id)
            previous = self.store.db.execute("SELECT request_sha,attempt_id FROM commands WHERE key=?", (key,)).fetchone()
            if previous:
                if previous != (request_sha, attempt_id):
                    raise ProtocolError("IDEMPOTENCY_CONFLICT", "取消命令键与原请求不一致。", 409)
                return attempt
            if self.store.db.execute("SELECT 1 FROM attempts WHERE submit_key=?", (key,)).fetchone():
                raise ProtocolError("IDEMPOTENCY_CONFLICT", "该命令键已经用于提交。", 409)
            if payload["expected_state_version"] != attempt["state_version"]:
                raise ProtocolError("STATE_CONFLICT", "执行状态已变化，请重新读取。", 409)
            if attempt["state"] == "finalizing":
                raise ProtocolError("ALREADY_FINALIZING", "计算已完成，正在封存原产物。", 409)
            self.store.db.execute("INSERT INTO commands VALUES(?,?,?)", (key, request_sha, attempt_id))
            if attempt["state"] not in TERMINAL:
                known = owns_process(attempt.get("process", {}))
                self.store.transition(attempt, "cancelling", stop_status="pending" if known else "unknown", recovery_required=not known)
            return attempt

    def events(self, attempt_id, after, limit):
        identifier(attempt_id)
        integer(after, 0, 2**53 - 1)
        integer(limit, 1, 100)
        with self.store.lock:
            attempt = self.store.get(attempt_id)
            if after > attempt["last_event_sequence"]:
                raise ProtocolError("EVENT_CURSOR_INVALID", "事件游标超过已持久序号。", 409)
            rows = self.store.db.execute("SELECT body FROM events WHERE attempt_id=? AND sequence>? ORDER BY sequence LIMIT ?", (attempt_id, after, limit + 1)).fetchall()
        items = [json.loads(row[0]) for row in rows[:limit]]
        return {"items": items, "next_cursor": items[-1]["sequence"] if items else after, "has_more": len(rows) > limit}

    def manifest(self, attempt_id):
        attempt = self.store.get(identifier(attempt_id))
        if not attempt.get("manifest"):
            raise ProtocolError("MANIFEST_UNAVAILABLE", "此执行尚无封存产物清单。", 409)
        manifest = attempt["manifest"]
        if digest(manifest) != attempt["manifest_sha256"]:
            raise ProtocolError("MANIFEST_INVALID", "原产物清单摘要不一致。", 409)
        return {"manifest": manifest, "manifest_sha256": attempt["manifest_sha256"]}

    def artifact(self, attempt_id, index, manifest_sha, offset, limit):
        sealed = self.manifest(attempt_id)
        if hex_digest(manifest_sha) != sealed["manifest_sha256"]:
            raise ProtocolError("MANIFEST_CONFLICT", "补收必须绑定原封存清单。", 409)
        files = sealed["manifest"]["files"]
        integer(index, 0, len(files) - 1)
        item = files[index]
        integer(offset, 0, item["size"])
        integer(limit, 1, MAX_CHUNK)
        base = self.root / "runs" / attempt_id / "output"
        path = base
        for part in relative_path(item["name"]).split("/"):
            path = path / part
            if path.is_symlink():
                raise ProtocolError("UNSAFE_WORKER_ARTIFACT", "原产物路径经过符号链接。", 409)
        descriptor = safe_file(path, item["size"], item["sha256"])
        try:
            os.lseek(descriptor, offset, os.SEEK_SET)
            return os.read(descriptor, min(limit, item["size"] - offset))
        finally:
            os.close(descriptor)

    def close(self):
        if not self.closed:
            self.closed = True
            # 远端执行独立于连接服务；此处不取消已授权的计算。
            for process in self.processes.values():
                process.poll()
            self.store.close()
            self.instance_lock.close()


def create_app(root, token, transport="loopback_http"):
    executor = Executor(root, token, transport)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        executor.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.executor = executor

    @app.middleware("http")
    async def authenticate(request, call_next):
        try:
            executor.authenticate(request)
            if request.method in {"PUT", "POST"}:
                raw_length = request.headers.get("content-length", "")
                maximum = MAX_CHUNK if request.method == "PUT" else 128 * 1024
                if not raw_length.isdecimal() or int(raw_length) > maximum:
                    raise ProtocolError("REQUEST_SIZE_LIMIT", "请求必须声明有界字节长度。", 413)
            return await call_next(request)
        except ProtocolError as error:
            return JSONResponse({"error": {"code": error.code, "message": error.message}}, status_code=error.status)

    @app.exception_handler(ProtocolError)
    async def protocol_error(_request, error):
        return JSONResponse({"error": {"code": error.code, "message": error.message}}, status_code=error.status)

    @app.get("/executor/v1/identity")
    def identity():
        return executor.identity()

    @app.get('/executor/v1/adapters/nvidia-text/probe')
    def nvidia_probe():
        return executor.nvidia_probe()

    @app.get("/executor/v1/blobs/{sha}")
    def blob(sha: str):
        return executor.blob_status(sha)

    @app.put("/executor/v1/blobs/{sha}")
    async def upload(sha: str, size: int, offset: int, request: Request):
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_CHUNK:
                raise ProtocolError("CHUNK_LIMIT", "上传分块超过限制。", 413)
        return executor.upload(sha, size, offset, bytes(content))

    @app.post("/executor/v1/attempts")
    def submit(payload: dict, request: Request):
        return executor.submit(payload, request.headers.get("idempotency-key"))

    @app.get("/executor/v1/attempts/{attempt_id}")
    def attempt(attempt_id: str):
        return executor.reconcile(attempt_id)

    @app.get("/executor/v1/attempts/{attempt_id}/events")
    def events(attempt_id: str, after: int = 0, limit: int = 100):
        return executor.events(attempt_id, after, limit)

    @app.post("/executor/v1/attempts/{attempt_id}/cancel")
    def cancel(attempt_id: str, payload: dict, request: Request):
        return executor.cancel(attempt_id, payload, request.headers.get("idempotency-key"))

    @app.get("/executor/v1/attempts/{attempt_id}/manifest")
    def manifest(attempt_id: str):
        return executor.manifest(attempt_id)

    @app.get("/executor/v1/attempts/{attempt_id}/artifacts/{index}")
    def artifact(attempt_id: str, index: int, manifest_sha256: str, offset: int = 0, limit: int = MAX_CHUNK):
        return Response(executor.artifact(attempt_id, index, manifest_sha256, offset, limit), media_type="application/octet-stream")

    return app
