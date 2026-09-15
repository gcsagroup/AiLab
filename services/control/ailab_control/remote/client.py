"""固定 origin 身份的客户端；回环 HTTP 与 HTTPS 共用执行及补收协议。"""

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat
import ssl
import urllib.error
import urllib.request

from .protocol import (PROTOCOL, MAX_CHUNK, MAX_BLOB, MAX_STORAGE, MAX_INPUTS, TERMINAL, ProtocolError,
                       encode, digest, identifier, hex_digest, integer, strict_keys, safe_file, file_hash,
                       write_json, publish_directory, sync_directory, now, relative_path,
                       canonical_origin, transport_scope, bound_transport, CONNECTION_ERRORS)


@dataclass(frozen=True)
class LoopbackTarget:
    origin: str
    executor_id: str
    token: str = field(repr=False)
    validation_scope: str | None = None
    transport: str = "loopback_http"

    def __post_init__(self):
        origin = canonical_origin(self.origin, self.transport)
        scope = transport_scope(self.transport)
        if self.validation_scope is not None and self.validation_scope != scope:
            raise ProtocolError("TRANSPORT_MISMATCH", "执行目标的连接方式与验证范围不一致。", 409)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "validation_scope", scope)
        identifier(self.executor_id, "executor")
        if not isinstance(self.token, str) or not 32 <= len(self.token) <= 512 or not all(33 <= ord(char) <= 126 for char in self.token):
            raise ProtocolError("INVALID_CREDENTIAL", "需要本次回环服务独立生成的临时凭证。")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ProtocolError("REDIRECT_FORBIDDEN", "执行目标不能通过重定向改变。", 409)


def create_tls_context():
    """只使用随运行时提供的公开 CA 包；不采纳环境代理或私有信任路径。"""
    try:
        import certifi
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(cafile=certifi.where())
        return context
    except (ImportError, OSError, ssl.SSLError):
        raise ProtocolError("TLS_TRUST_UNAVAILABLE", "运行时公开 CA 文件缺失或不可读取，HTTPS 连接未开始。", 503) from None


class LoopbackClient:
    def __init__(self, target, state_dir, timeout=5):
        self.target = target
        self.state_dir = Path(state_dir).absolute()
        if self.state_dir.is_symlink():
            raise ProtocolError("UNSAFE_STATE_DIRECTORY", "连接记录目录不能是符号链接。")
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_dir = self.state_dir.resolve()
        for name in ("attempts", "collections"):
            path = self.state_dir / name
            if path.is_symlink():
                raise ProtocolError("UNSAFE_STATE_DIRECTORY", "连接记录子目录不能是符号链接。")
            path.mkdir(exist_ok=True, mode=0o700)
        self.timeout = timeout
        handlers = [urllib.request.ProxyHandler({}), NoRedirects()]
        if target.transport == "https":
            handlers.append(urllib.request.HTTPSHandler(context=create_tls_context()))
        self.opener = urllib.request.build_opener(*handlers)

    def _request(self, method, path, payload=None, content=None, key=None, binary=False):
        data = content if content is not None else encode(payload).encode() if payload is not None else None
        headers = {"Authorization": "Bearer " + self.target.token, "X-AILab-Executor": self.target.executor_id}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if key is not None:
            headers["Idempotency-Key"] = key
        request = urllib.request.Request(self.target.origin.rstrip("/") + "/executor/v1" + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                maximum = MAX_CHUNK if binary else 2 * MAX_CHUNK
                raw = response.read(maximum + 1)
                if len(raw) > maximum:
                    raise ProtocolError("RESPONSE_SIZE_LIMIT", "执行服务响应超出大小限制。", 502)
                return raw if binary else json.loads(raw)
        except urllib.error.HTTPError as error:
            if 300 <= error.code < 400:
                raise ProtocolError("REDIRECT_FORBIDDEN", "执行目标不能通过重定向改变。", 409) from None
            try:
                body = json.loads(error.read(128 * 1024))
                code = body["error"]["code"]
                if type(code) is not str or not code.replace("_", "").isalnum() or len(code) > 80:
                    code = "REMOTE_REQUEST_REJECTED"
            except (ValueError, KeyError, TypeError):
                code = "REMOTE_REQUEST_REJECTED"
            raise ProtocolError(code, "执行服务拒绝了本次请求。", error.code) from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, ssl.SSLCertVerificationError):
                raise ProtocolError("TLS_VERIFICATION_FAILED", "HTTPS 证书链、主机名或有效期验证失败。", 503) from None
            raise ProtocolError("REMOTE_UNAVAILABLE", "连接中断，运行状态需要重新确认。", 503) from None
        except (TimeoutError, ConnectionError, OSError):
            raise ProtocolError("REMOTE_UNAVAILABLE", "连接中断，运行状态需要重新确认。", 503) from None
        except (ValueError, TypeError):
            raise ProtocolError("INVALID_REMOTE_RESPONSE", "执行服务响应格式不正确。", 502) from None

    def identity(self):
        result = self._request("GET", "/identity")
        if not isinstance(result, dict):
            raise ProtocolError("INVALID_REMOTE_RESPONSE", "执行服务身份响应格式不正确。", 502)
        if (result.get("protocol_version") != PROTOCOL or result.get("executor_id") != self.target.executor_id
                or result.get("validation_scope") != self.target.validation_scope
                or result.get("network_remote_ready") is not (self.target.transport == "https")):
            raise ProtocolError("EXECUTOR_IDENTITY_MISMATCH", "执行服务身份、协议或验证范围发生变化。", 409)
        bound_transport(result, self.target.transport)
        return result

    def upload(self, path, authorized_roots, progress=None, check_cancel=lambda: None):
        # 在读取和发送输入前先确认登记身份；每个后续分块也重新确认。
        self.identity()
        check_cancel()
        path = Path(path).absolute()
        if ".." in path.parts:
            raise ProtocolError("UNSAFE_INPUT_PATH", "上传输入不能包含父目录跳转。", 403)
        roots = [Path(root).resolve(strict=True) for root in authorized_roots]
        root = next((root for root in roots if path.is_relative_to(root)), None)
        if root is None:
            raise ProtocolError("INPUT_NOT_AUTHORIZED", "输入不在本次明确授权的读取目录内。", 403)
        current = root
        for component in path.relative_to(root).parts:
            current = current / component
            if current.is_symlink():
                raise ProtocolError("UNSAFE_INPUT_PATH", "上传输入不能经过符号链接。", 403)
        descriptor = safe_file(path)
        with os.fdopen(descriptor, "rb") as source:
            size = os.fstat(source.fileno()).st_size
            integer(size, 0, MAX_BLOB)
            hasher = hashlib.sha256()
            while chunk := source.read(MAX_CHUNK):
                check_cancel()
                hasher.update(chunk)
            sha = hasher.hexdigest()
            status = self._request("GET", "/blobs/" + sha)
            if status["size"] is not None and status["size"] != size:
                raise ProtocolError("BLOB_DECLARATION_CONFLICT", "远端已登记的文件长度不同。", 409)
            offset = integer(status["offset"], 0, size)
            while not status["complete"]:
                check_cancel()
                self.identity()
                check_cancel()
                source.seek(offset)
                chunk = source.read(min(MAX_CHUNK, size - offset))
                status = self._request("PUT", f"/blobs/{sha}?size={size}&offset={offset}", content=chunk)
                new_offset = integer(status["offset"], 0, size)
                if new_offset != offset + len(chunk) or (new_offset == offset and size != 0):
                    raise ProtocolError("UPLOAD_OFFSET_CONFLICT", "执行服务返回了不一致的续传位置。", 409)
                offset = new_offset
                if progress:
                    progress(offset, size)
        if status["sha256"] != sha or not status["complete"] or status["size"] != size:
            raise ProtocolError("UPLOAD_NOT_COMPLETE", "输入未完成远端摘要校验。", 409)
        return {"sha256": sha, "size": size}

    def nvidia_probe(self):
        identity = self.identity()
        result = self._request('GET', '/adapters/nvidia-text/probe')
        expected = identity.get('adapters', {}).get('nvidia-text', {}).get('source_code_digest')
        if not isinstance(result, dict) or type(result.get('ready')) is not bool or not expected or result.get('source_code_digest') != expected:
            raise ProtocolError('NVIDIA_PROBE_IDENTITY_CHANGED', '设备探测与当前执行服务的代码身份不一致。', 409)
        return result

    def submit(self, snapshot, key):
        self.identity()
        return self._request("POST", "/attempts", payload={"snapshot": snapshot, "snapshot_sha256": digest(snapshot)}, key=key)

    def attempt(self, attempt_id):
        result = self._request("GET", "/attempts/" + identifier(attempt_id))
        if result.get("id") != attempt_id or result.get("executor_id") != self.target.executor_id or result.get("validation_scope") != self.target.validation_scope:
            raise ProtocolError("EXECUTOR_IDENTITY_MISMATCH", "收到的执行记录不属于登记目标。", 409)
        bound_transport(result, self.target.transport)
        return result

    def events(self, attempt_id, after=0, limit=100):
        identifier(attempt_id)
        integer(after, 0, 2**53 - 1)
        integer(limit, 1, 100)
        result = self._request("GET", f"/attempts/{attempt_id}/events?after={after}&limit={limit}")
        sequence = after
        for item in result["items"]:
            sequence += 1
            if item.get("attempt_id") != attempt_id or item.get("sequence") != sequence:
                raise ProtocolError("EVENT_SEQUENCE_MISMATCH", "事件缺失、重复或顺序不一致，未推进本地游标。", 409)
        if result["next_cursor"] != sequence:
            raise ProtocolError("EVENT_SEQUENCE_MISMATCH", "返回的事件游标不一致。", 409)
        return result

    def _shadow_path(self, attempt_id):
        return self.state_dir / "attempts" / (identifier(attempt_id) + ".json")

    def _shadow(self, attempt_id):
        path = self._shadow_path(attempt_id)
        if not path.exists():
            return {"id": attempt_id, "executor_id": self.target.executor_id, "events": [], "last_event_sequence": 0}
        result = json.loads(path.read_text())
        if result.get("id") != attempt_id or result.get("executor_id") != self.target.executor_id:
            raise ProtocolError("LOCAL_IDENTITY_CONFLICT", "本地连接记录属于其他执行目标。", 409)
        return result

    def sync(self, attempt_id):
        record = self._shadow(attempt_id)
        try:
            remote = self.attempt(attempt_id)
            if remote["state_version"] < record.get("state_version", 0):
                raise ProtocolError("STATE_REGRESSION", "远端状态版本回退，保留本地证据。", 409)
            page = self.events(attempt_id, record["last_event_sequence"])
            result = {**remote, "remote_last_event_sequence": remote["last_event_sequence"], "connection_state": "connected",
                      "events": record["events"] + page["items"], "last_event_sequence": page["next_cursor"], "has_more_events": page["has_more"]}
            result.pop("launch_nonce", None)
            write_json(self._shadow_path(attempt_id), result)
            return result
        except ProtocolError as error:
            if error.code in CONNECTION_ERRORS:
                record["connection_state"] = "disconnected"
                if record.get("stop_status") == "pending":
                    record["stop_status"] = "unknown"
                record["last_connection_error"] = error.code
                write_json(self._shadow_path(attempt_id), record)
                return record
            raise

    def cancel(self, attempt_id, expected_state_version, key):
        record = self._shadow(attempt_id)
        try:
            result = self._request("POST", "/attempts/" + identifier(attempt_id) + "/cancel",
                                   payload={"expected_state_version": expected_state_version}, key=key)
            result.pop("launch_nonce", None)
            record.update({key: value for key, value in result.items() if key != "last_event_sequence"})
            record["connection_state"] = "connected"
        except ProtocolError as error:
            if error.code not in CONNECTION_ERRORS:
                raise
            record.update(connection_state="disconnected", stop_status="unknown", last_connection_error=error.code)
        write_json(self._shadow_path(attempt_id), record)
        return record

    def manifest(self, attempt_id):
        result = self._request("GET", "/attempts/" + identifier(attempt_id) + "/manifest")
        value = result["manifest"]
        strict_keys(value, {"schema_version", "executor_id", "attempt_id", "snapshot_sha256", "files", "validation_scope"}, {"transport"})
        if (value["schema_version"] != PROTOCOL or value["executor_id"] != self.target.executor_id or value["attempt_id"] != attempt_id
                or value["validation_scope"] != self.target.validation_scope or digest(value) != hex_digest(result["manifest_sha256"])):
            raise ProtocolError("MANIFEST_CONFLICT", "原产物清单与执行身份或摘要不一致。", 409)
        bound_transport(value, self.target.transport)
        files = value["files"]
        if type(files) is not list or not 1 <= len(files) <= MAX_INPUTS:
            raise ProtocolError("MANIFEST_INVALID", "原产物清单数量超出限制。", 409)
        names = set()
        for item in files:
            strict_keys(item, {"name", "size", "sha256", "media_type"})
            name = relative_path(item["name"])
            if (any(part.startswith(".") for part in name.split("/")) or name.endswith(".part") or name == "manifest.json" or name in names
                    or any(name.startswith(other + "/") or other.startswith(name + "/") for other in names)):
                raise ProtocolError("MANIFEST_PATH_INVALID", "产物清单包含无效、重复或越界文件名。", 409)
            names.add(name)
            hex_digest(item["sha256"])
            integer(item["size"], 0, MAX_BLOB)
        if sum(item["size"] for item in files) > MAX_STORAGE:
            raise ProtocolError("MANIFEST_SIZE_LIMIT", "原产物清单超过总字节限制。", 413)
        return result

    @staticmethod
    def _artifact_path(root, name, create=False):
        parts = relative_path(name).split("/")
        current = root
        for index, part in enumerate(parts):
            current = current / part
            if current.is_symlink():
                raise ProtocolError("UNSAFE_COLLECTION_PATH", "补收路径不能经过符号链接。", 409)
            if create and index < len(parts) - 1:
                current.mkdir(exist_ok=True, mode=0o700)
        return current

    @staticmethod
    def _finish_linked_part(part, target, item):
        """恢复本事务发布后、移除 part 前的中断；未知硬链接仍拒绝。"""
        if not part.exists() and not part.is_symlink():
            return
        descriptor = os.open(part, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as stream:
            identity = os.fstat(stream.fileno())
            def same(path):
                current = path.lstat()
                return stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino)
            if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 2 or not same(target):
                raise ProtocolError('UNSAFE_FILE', '暂存文件不是本次发布留下的唯一硬链接。', 409)
            hasher = hashlib.sha256()
            while chunk := stream.read(MAX_CHUNK):
                hasher.update(chunk)
            if identity.st_size != item['size'] or hasher.hexdigest() != item['sha256']:
                raise ProtocolError('ARTIFACT_HASH_MISMATCH', '中断的补收文件与原清单不符，保留现场。', 409)
            if os.fstat(stream.fileno()).st_nlink != 2 or not same(target) or not same(part):
                raise ProtocolError('UNSAFE_FILE', '补收恢复期间文件身份发生变化，保留现场。', 409)
            part.unlink()
            sync_directory(target.parent)

    def collect(self, attempt_id, manifest_sha, collection_id, destination_parent, progress=None):
        identifier(collection_id, "collection")
        self.identity()
        sealed = self.manifest(attempt_id)
        if sealed["manifest_sha256"] != hex_digest(manifest_sha):
            raise ProtocolError("MANIFEST_CONFLICT", "只补收必须使用本次指定的原清单摘要。", 409)
        parent = Path(destination_parent).absolute()
        if parent.is_symlink() or not parent.is_dir():
            raise ProtocolError("DESTINATION_INVALID", "请指定已授权的普通目标目录。")
        parent = parent.resolve()
        final, temporary = parent / collection_id, parent / ("." + collection_id + ".tmp")
        receipt_path = self.state_dir / "collections" / (collection_id + ".json")
        identity = {"collection_id": collection_id, "executor_id": self.target.executor_id, "attempt_id": attempt_id,
                    "manifest_sha256": manifest_sha, "destination": str(final)}
        receipt = {**identity, "status": "planned", "failures": [], "created_at": now()}
        if receipt_path.exists():
            previous = json.loads(receipt_path.read_text())
            if any(previous.get(key) != value for key, value in identity.items()):
                raise ProtocolError("COLLECTION_REPLAY_CONFLICT", "补收编号已经绑定其他执行、清单或目标。", 409)
            receipt = previous
        else:
            write_json(receipt_path, receipt, exclusive=True)
        try:
            if final.exists() or final.is_symlink():
                if final.is_symlink() or (final / "manifest.json").is_symlink() or not (final / "manifest.json").is_file():
                    raise ProtocolError("DESTINATION_EXISTS", "目标已经存在，不能覆盖。", 409)
                if json.loads((final / "manifest.json").read_text()) != sealed["manifest"]:
                    raise ProtocolError("DESTINATION_EXISTS", "已有目标不是本次原产物。", 409)
                for item in sealed["manifest"]["files"]:
                    descriptor = safe_file(self._artifact_path(final, item["name"]), item["size"], item["sha256"])
                    os.close(descriptor)
                receipt.update(status="succeeded", completed_at=now())
                write_json(receipt_path, receipt)
                return receipt
            if temporary.exists() or temporary.is_symlink():
                if temporary.is_symlink() or (temporary / ".plan.json").is_symlink() or not (temporary / ".plan.json").is_file() or json.loads((temporary / ".plan.json").read_text()) != identity:
                    raise ProtocolError("COLLECTION_STAGING_CONFLICT", "暂存目标不属于本次补收。", 409)
            else:
                temporary.mkdir(mode=0o700)
                write_json(temporary / ".plan.json", identity, exclusive=True)
            receipt["status"] = "collecting"
            write_json(receipt_path, receipt)
            for index, item in enumerate(sealed["manifest"]["files"]):
                target = self._artifact_path(temporary, item["name"], create=True)
                part = self._artifact_path(temporary, item["name"] + ".part", create=True)
                if target.exists() or target.is_symlink():
                    self._finish_linked_part(part, target, item)
                    descriptor = safe_file(target, item["size"], item["sha256"])
                    os.close(descriptor)
                    continue
                offset = 0
                if part.exists() or part.is_symlink():
                    descriptor = safe_file(part)
                    offset = integer(os.fstat(descriptor).st_size, 0, item["size"])
                    os.close(descriptor)
                descriptor = os.open(part, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "r+b") as stream:
                    while offset < item["size"]:
                        content = self._request("GET", f"/attempts/{attempt_id}/artifacts/{index}?manifest_sha256={manifest_sha}&offset={offset}&limit={MAX_CHUNK}", binary=True)
                        if not content or offset + len(content) > item["size"]:
                            raise ProtocolError("ARTIFACT_SIZE_MISMATCH", "补收文件长度与原清单不符。", 409)
                        stream.seek(offset)
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                        offset += len(content)
                        if progress:
                            progress(index, offset, item["size"])
                if file_hash(part) != item["sha256"]:
                    part.unlink()
                    raise ProtocolError("ARTIFACT_HASH_MISMATCH", "补收文件摘要不符，未登记为完整产物。", 409)
                part.chmod(0o400)
                os.link(part, target)
                part.unlink()
                sync_directory(target.parent)
            write_json(temporary / "manifest.json", sealed["manifest"])
            publish_directory(temporary, final)
            receipt.update(status="succeeded", completed_at=now())
            write_json(receipt_path, receipt)
            return receipt
        except BaseException as error:
            receipt["status"] = "failed"
            receipt["failures"].append({"code": error.code if isinstance(error, ProtocolError) else "LOCAL_COLLECTION_WRITE_FAILED", "at": now()})
            write_json(receipt_path, receipt)
            raise
