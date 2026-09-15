"""固定模型工作进程包装器，复用授权、事件、取消和封存合同。"""

import json
import os
from pathlib import Path
import secrets
import selectors
import signal
import subprocess
import sys
import time

from .protocol import (MAX_CHUNK, MAX_INPUTS, ProtocolError, digest, encode, hex_digest, relative_path,
                       safe_file, file_hash, process_identity, owns_process, write_json, sync_directory, process_group_absent)


def materialize_inputs(context):
    directory = context.output.parent / "input"
    directory.mkdir(mode=0o700)
    for item in context.snapshot["inputs"]:
        context.check_cancel()
        target = directory / relative_path(item["path"])
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = safe_file(context.store.root / "blobs" / item["sha256"], item["size"], item["sha256"])
        with os.fdopen(descriptor, "rb") as source, target.open("xb") as destination:
            while chunk := source.read(MAX_CHUNK):
                context.check_cancel()
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if file_hash(target) != item["sha256"]:
            raise ProtocolError("INPUT_CHANGED", "冻结输入副本与原上传清单不一致。", 409)
        target.chmod(0o400)
        sync_directory(target.parent)
    for path in sorted((path for path in directory.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        path.chmod(0o500)
    directory.chmod(0o500)
    return directory


def verify_artifacts(context, artifacts):
    if type(artifacts) is not list or not 1 <= len(artifacts) <= MAX_INPUTS:
        raise ProtocolError("INVALID_WORKER_MANIFEST", "工作进程产物数量不符合协议限制。")
    files, names, total = [], set(), 0
    for item in artifacts:
        if not isinstance(item, dict) or not {"path", "sha256", "media_type"} <= item.keys():
            raise ProtocolError("INVALID_WORKER_MANIFEST", "工作进程未提供完整产物身份。")
        name = relative_path(item["path"])
        if (name in names or name == "manifest.json" or any(part.startswith(".") for part in name.split("/"))
                or name.endswith(".part") or any(name.startswith(other + "/") or other.startswith(name + "/") for other in names)):
            raise ProtocolError("INVALID_WORKER_MANIFEST", "工作进程产物名称重复、保留或相互冲突。")
        names.add(name)
        target = context.output / name
        current = context.output
        for component in name.split("/"):
            current = current / component
            if current.is_symlink():
                raise ProtocolError("UNSAFE_WORKER_ARTIFACT", "工作进程产物不能经过符号链接。")
        descriptor = safe_file(target, expected_sha=hex_digest(item["sha256"]))
        total += os.fstat(descriptor).st_size
        size = os.fstat(descriptor).st_size
        os.fsync(descriptor)
        os.close(descriptor)
        if total > context.store.get(context.attempt_id)["output_reserved_bytes"]:
            raise ProtocolError("OUTPUT_LIMIT", "工作进程产物超过提交时预留的总字节。")
        target.chmod(0o400)
        files.append({"name": name, "sha256": item["sha256"], "size": size, "media_type": str(item["media_type"])[:100]})
    actual = {path.relative_to(context.output).as_posix() for path in context.output.rglob("*") if path.is_file() or path.is_symlink()}
    if actual != names:
        raise ProtocolError("INVALID_WORKER_MANIFEST", "产物目录包含未列出或缺失的文件。")
    sync_directory(context.output)
    return files


def execute(context, worker_script):
    """worker_script 由已安装适配器固定注册，网络请求不能指定命令。"""
    input_dir = materialize_inputs(context)
    directory = context.output.parent / "external"
    directory.mkdir(mode=0o700)
    snapshot_path = context.output.parent / "snapshot.json"
    nonce = secrets.token_hex(32)
    root = Path(__file__).resolve().parents[4]
    environment = {"PATH": "/usr/bin:/bin", "PYTHONPATH": os.pathsep.join([str(root / "services/control"), str(root)]),
                   "PYTHONUNBUFFERED": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    selector = selectors.DefaultSelector()
    process, identity = None, None
    completed, worker_error, token_bytes, event_count = None, None, 0, 0

    def stop_owned():
        if process is None:
            return
        if process.poll() is None and identity and owns_process(identity):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if owns_process(identity):
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
        process.poll()

    def event(raw):
        nonlocal completed, worker_error, token_bytes, event_count
        if len(raw) > 8192:
            raise ProtocolError("INVALID_WORKER_EVENT", "工作进程单条事件超过限制。")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ProtocolError("INVALID_WORKER_EVENT", "工作进程事件不是合法 JSON。") from None
        if not isinstance(value, dict) or value.get("type") not in {"phase", "token", "metric", "completed", "error"}:
            raise ProtocolError("INVALID_WORKER_EVENT", "工作进程事件类型不受支持。")
        event_count += 1
        if event_count > 10000:
            raise ProtocolError("WORKER_EVENT_LIMIT", "工作进程事件总数超过限制。")
        if value["type"] == "completed":
            if completed is not None:
                raise ProtocolError("INVALID_WORKER_EVENT", "工作进程重复报告完成。")
            completed = value
            return
        if value["type"] == "token":
            if type(value.get("text")) is not str:
                raise ProtocolError("INVALID_WORKER_EVENT", "生成事件缺少文本。")
            token_bytes += len(value["text"].encode())
            if token_bytes > 8 * MAX_CHUNK:
                raise ProtocolError("WORKER_OUTPUT_LIMIT", "流式文本超过限制。")
        if value["type"] == "error":
            worker_error = value
        context.event(value["type"], {key: item for key, item in value.items() if key != "type"})

    try:
        with (directory / "worker.stderr.log").open("xb") as error:
            process = subprocess.Popen([sys.executable, "-m", "ailab_control.remote.child_launcher", "--worker-script", str(worker_script),
                                        "--snapshot", str(snapshot_path), "--input-dir", str(input_dir), "--output-dir", str(context.output),
                                        "--record-dir", str(directory), "--nonce", nonce, "--parent-pid", str(os.getpid())],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=error, cwd=directory,
                                       env=environment, start_new_session=True)
        identity = process_identity(process.pid)
        deadline = time.monotonic() + 5
        record_path = directory / "process.json"
        while not record_path.is_file():
            context.check_cancel()
            if process.poll() is not None or time.monotonic() >= deadline:
                raise ProtocolError("CHILD_LAUNCH_FAILED", "引擎进程未在期限内登记归属。")
            time.sleep(0.01)
        record = json.loads(record_path.read_text())
        if (record.get("nonce") != nonce or record.get("snapshot_sha256") != digest(context.snapshot)
                or record.get("process", {}).get("pid") != process.pid or not owns_process(record["process"])):
            raise ProtocolError("CHILD_IDENTITY_MISMATCH", "引擎启动身份与本次快照不一致。")
        identity = record["process"]
        with context.store.transaction():
            attempt = context.store.get(context.attempt_id)
            attempt["child_processes"] = [identity]
            context.store.event(attempt, "engine_registered", {"identity_digest": identity["identity_digest"]})
        write_json(directory / "authorized.json", record, exclusive=True)
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer, eof, exit_deadline = b"", False, None
        while not eof or process.poll() is None:
            context.check_cancel()
            if process.poll() is not None and exit_deadline is None:
                exit_deadline = time.monotonic() + 1
            if exit_deadline is not None and time.monotonic() > exit_deadline and not eof:
                raise ProtocolError("CHILD_OUTPUT_STILL_OPEN", "引擎退出后仍有后代持有输出通道，停止待确认。")
            for _key, _mask in selector.select(0.05):
                content = os.read(process.stdout.fileno(), 65536)
                if not content:
                    eof = True
                    selector.unregister(process.stdout)
                    if buffer:
                        event(buffer)
                        buffer = b""
                    break
                buffer += content
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    event(line)
                if len(buffer) > 8192:
                    raise ProtocolError("INVALID_WORKER_EVENT", "工作进程事件没有有界换行。")
        if not process_group_absent(process.pid):
            raise ProtocolError("CHILD_PROCESS_GROUP_PRESENT", "引擎进程组仍有后代，资源释放待确认。")
        context.check_cancel()
        if process.returncode != 0 or worker_error or completed is None:
            code = worker_error.get("code", "EXTERNAL_WORKER_FAILED") if worker_error else "EXTERNAL_WORKER_FAILED"
            raise ProtocolError(code, "指定模型工作进程没有完成本次计算。")
        files = verify_artifacts(context, completed.get("artifacts"))
        effective = completed.get("effective_config", {})
        if not isinstance(effective, dict) or len(encode(effective).encode()) > 64 * 1024:
            raise ProtocolError("INVALID_EFFECTIVE_CONFIG", "实际运行参数缺失或超出限制。")
        if context.snapshot.get("adapter_id") == "nvidia-text":
            from adapters.nvidia_text.adapter import validate_completion
            validate_completion(context.snapshot, effective, files, context.output)
        with context.store.transaction():
            attempt = context.store.get(context.attempt_id)
            attempt["effective_config"] = effective
            context.store.event(attempt, "effective_config", effective)
        return files
    except BaseException:
        stop_owned()
        raise
    finally:
        selector.close()
        if process and process.stdout:
            process.stdout.close()
