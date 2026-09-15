"""独立于连接服务存活的执行进程；同一已登记尝试只进入适配器一次。"""

import argparse
import json
import os
from pathlib import Path
import time

from .protocol import (ProtocolError, digest, file_hash, safe_file, write_json, sync_directory,
                       process_identity, MAX_CHUNK, bound_transport)
from .store import Store


class Cancelled(Exception):
    pass


class Context:
    def __init__(self, store, attempt_id, snapshot, output):
        self.store, self.attempt_id, self.snapshot, self.output = store, attempt_id, snapshot, output

    def check_cancel(self):
        if self.store.get(self.attempt_id)["state"] == "cancelling":
            raise Cancelled()

    def event(self, kind, value):
        with self.store.transaction():
            attempt = self.store.get(self.attempt_id)
            self.store.event(attempt, kind, value)


def protocol_copy(context):
    """合同夹具执行真实复制，不加载模型，也不声明模型推理能力。"""
    runtime = context.snapshot["runtime"]
    for index in range(runtime["steps"]):
        context.check_cancel()
        context.event("progress", {"step": index + 1, "total": runtime["steps"], "validation_scope": context.store.validation_scope})
        time.sleep(runtime["step_delay_ms"] / 1000)
    files = []
    for index, item in enumerate(context.snapshot["inputs"]):
        context.check_cancel()
        name = f"file-{index:03d}.bin"
        temporary, final = context.output / (name + ".part"), context.output / name
        descriptor = safe_file(context.store.root / "blobs" / item["sha256"], item["size"], item["sha256"])
        with os.fdopen(descriptor, "rb") as source, temporary.open("xb") as target:
            while chunk := source.read(MAX_CHUNK):
                context.check_cancel()
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if file_hash(temporary) != item["sha256"]:
            raise ProtocolError("INPUT_CHANGED", "执行时输入内容已改变。")
        temporary.chmod(0o400)
        os.link(temporary, final)
        temporary.unlink()
        sync_directory(context.output)
        files.append({"name": name, "size": item["size"], "sha256": item["sha256"], "media_type": "application/octet-stream"})
    return files


def nvidia_text(context):
    from .external import execute
    worker = Path(__file__).resolve().parents[4] / "workers/nvidia_worker.py"
    if not worker.is_file():
        raise ProtocolError("ADAPTER_UNAVAILABLE", "NVIDIA 固定工作进程未安装。")
    return execute(context, worker)


# 后续模型适配器注册到同一执行入口；请求只能选择已安装的固定 ID。
ADAPTER_EXECUTORS = {"protocol-copy": protocol_copy, "nvidia-text": nvidia_text}


def run(root, attempt_id, launch_nonce):
    store = Store(root)
    claimed = False

    def finish(state, **fields):
        with store.transaction():
            current = store.get(attempt_id)
            current.update(**fields)
            store.event(current, "worker_finished", {"requested_terminal": state, **fields})
        # 这里只提供结果证据；连接服务核实整个进程组退出后才确认终态和停止。
        write_json(directory / "outcome.json", {"state": state, "attempt_id": attempt_id, "snapshot_sha256": digest(snapshot),
                   "identity_digest": identity["identity_digest"], **fields}, exclusive=True)

    try:
        directory = Path(root) / "runs" / attempt_id
        snapshot = json.loads((directory / "snapshot.json").read_text())
        bound_transport(snapshot, store.transport)
        identity = process_identity(os.getpid())
        if identity["status"] != "present" or identity["pgid"] != os.getpid():
            return 1
        with store.transaction():
            attempt = store.get(attempt_id)
            if attempt.get("process") or attempt["launch_nonce"] != launch_nonce or attempt["snapshot_sha256"] != digest(snapshot):
                return 1
            if attempt["state"] not in {"authorizing", "cancelling"}:
                return 1
            attempt["process"] = identity
            attempt["recovery_required"] = False
            store.event(attempt, "launcher_registered", {"identity_digest": identity["identity_digest"]})
            claimed = True
        deadline = time.monotonic() + 30
        authorization = directory / "authorized.json"
        context = Context(store, attempt_id, snapshot, directory / "output")
        while not authorization.is_file():
            context.check_cancel()
            if time.monotonic() >= deadline:
                raise ProtocolError("AUTHORIZATION_TIMEOUT", "启动授权未在期限内确认，未执行计算。")
            time.sleep(0.01)
        expected = {"pid": os.getpid(), "identity_digest": identity["identity_digest"],
                    "snapshot_sha256": digest(snapshot), "launch_nonce": launch_nonce}
        if json.loads(authorization.read_text()) != expected:
            raise ProtocolError("AUTHORIZATION_MISMATCH", "启动授权与当前进程、快照不匹配。")
        context.check_cancel()
        with store.transaction():
            attempt = store.get(attempt_id)
            if attempt["state"] == "cancelling":
                raise Cancelled()
            if attempt["run_count"] != 0:
                raise ProtocolError("ATTEMPT_ALREADY_EXECUTED", "此尝试已经进入过执行器。")
            attempt["run_count"] = 1
            store.transition(attempt, "running", recovery_required=False)
        context.output.mkdir(mode=0o700)
        adapter = ADAPTER_EXECUTORS.get(snapshot["adapter_id"])
        if adapter is None:
            raise ProtocolError("ADAPTER_UNAVAILABLE", "指定适配器未安装。")
        files = adapter(context)
        with store.transaction():
            attempt = store.get(attempt_id)
            if attempt["state"] == "cancelling":
                raise Cancelled()
            store.transition(attempt, "finalizing", compute_outcome="succeeded")
        manifest = {"schema_version": 1, "executor_id": store.executor_id, "attempt_id": attempt_id,
                    "snapshot_sha256": digest(snapshot), "files": files, "validation_scope": store.validation_scope, "transport": store.transport}
        write_json(directory / "manifest.json", manifest, exclusive=True)
        with store.transaction():
            attempt = store.get(attempt_id)
            attempt.update(manifest=manifest, manifest_sha256=digest(manifest))
            store.put(attempt)
        finish("succeeded", compute_outcome="succeeded")
        return 0
    except Cancelled:
        if claimed:
            finish("cancelled", compute_outcome="cancelled")
        return 130
    except BaseException as error:
        if claimed:
            finish("failed", compute_outcome="failed", terminal_reason=error.code if isinstance(error, ProtocolError) else "WORKER_FAILED")
        raise
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--launch-nonce", required=True)
    arguments = parser.parse_args()
    raise SystemExit(run(arguments.data_dir, arguments.attempt, arguments.launch_nonce))
