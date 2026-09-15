"""执行协议的身份、摘要、文件边界和进程归属。"""

import ctypes
import errno
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone


PROTOCOL = 1
SCOPE = "loopback_protocol_only"
TRANSPORT_SCOPES = {"loopback_http": SCOPE, "https": "https_protocol_only"}
CONNECTION_ERRORS = {"REMOTE_UNAVAILABLE", "TLS_VERIFICATION_FAILED", "TLS_TRUST_UNAVAILABLE"}
MAX_CHUNK = 1024 * 1024
MAX_BLOB = 2 * 1024 * 1024 * 1024
MAX_STORAGE = 4 * 1024 * 1024 * 1024
MAX_INPUTS = 16
TERMINAL = {"succeeded", "failed", "cancelled"}


class ProtocolError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def transport_scope(transport):
    if type(transport) is not str or transport not in TRANSPORT_SCOPES:
        raise ProtocolError("INVALID_TRANSPORT", "执行连接方式必须为回环 HTTP 或 HTTPS。")
    return TRANSPORT_SCOPES[transport]


def bound_transport(value, expected=None):
    """缺少字段只表示旧回环记录，不能将旧身份升级为 HTTPS。"""
    transport = value.get("transport", "loopback_http")
    scope = transport_scope(transport)
    if ((expected is not None and transport != expected)
            or ("validation_scope" in value and value["validation_scope"] != scope)):
        raise ProtocolError("TRANSPORT_MISMATCH", "执行连接方式或验证范围与登记身份不一致。", 409)
    return transport


def canonical_origin(origin, transport):
    transport_scope(transport)
    code = "LOOPBACK_ONLY" if transport == "loopback_http" else "INVALID_EXECUTION_TARGET"
    def invalid():
        raise ProtocolError(code, "地址须为 HTTPS 主机和端口，或字面 127.0.0.1 的回环 HTTP 地址。")
    if (type(origin) is not str or not 1 <= len(origin) <= 2048 or not origin.isascii()
            or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in origin)
            or any(c in origin for c in "\\%@?#")):
        invalid()
    try:
        parsed = urllib.parse.urlsplit(origin)
        port, host = parsed.port, parsed.hostname
    except ValueError:
        invalid()
    if not host or parsed.path not in {"", "/"} or parsed.username is not None or parsed.password is not None:
        invalid()
    if port is not None and not 1 <= port <= 65535:
        invalid()
    if transport == "loopback_http":
        if parsed.scheme != "http" or host != "127.0.0.1" or port is None or parsed.netloc != f"127.0.0.1:{port}":
            invalid()
        return f"http://127.0.0.1:{port}"
    if parsed.scheme != "https":
        invalid()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # 拒绝浏览器可能解释为短 IPv4、八进制或十六进制地址的写法。
        dns = host.removesuffix(".")
        if (len(dns) > 253 or re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]*)", dns.split(".")[-1], re.I)
                or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part, re.I) for part in dns.split("."))):
            invalid()
        authority = dns.lower()
    else:
        authority = f"[{address.compressed}]" if address.version == 6 else str(address)
        if address.version == 4 and host != authority:
            invalid()
    suffix = f":{port}" if port is not None else ""
    # 拒绝空端口、补零端口及其他解析器消歧形式。
    raw_host = f"[{host}]" if ":" in host else host
    if parsed.netloc.lower() != (raw_host + suffix).lower():
        invalid()
    return "https://" + authority + (f":{port}" if port not in {None, 443} else "")


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(MAX_CHUNK):
            result.update(chunk)
    return result.hexdigest()


def hex_digest(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ProtocolError("INVALID_DIGEST", "文件或快照摘要格式不正确。")
    return value


def identifier(value, prefix="attempt"):
    if type(value) is not str or re.fullmatch(prefix + r"-[0-9a-f]{32}", value) is None:
        raise ProtocolError("INVALID_IDENTIFIER", "执行编号格式不正确。")
    return value


def integer(value, minimum, maximum, code="INVALID_RANGE"):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProtocolError(code, "数值超出协议允许范围。")
    return value


def relative_path(value):
    if (type(value) is not str or not 1 <= len(value.encode()) <= 512 or value.startswith("/") or "\\" in value or "\0" in value
            or any(part in {"", ".", ".."} for part in value.split("/")) or len(value.split("/")) > 8):
        raise ProtocolError("INPUT_PATH_INVALID", "输入名称必须是有界、不越界的相对路径。", 403)
    return value


def strict_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ProtocolError("INVALID_REQUEST", "请求字段缺失或包含未开放字段。")


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json(path, value, exclusive=False):
    path = Path(path)
    descriptor, name = tempfile.mkstemp(prefix=".record-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encode(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def safe_file(path, expected_size=None, expected_sha=None):
    path = Path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        import stat
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ProtocolError("UNSAFE_FILE", "文件不是单一受限普通文件。")
        if expected_size is not None and metadata.st_size != expected_size:
            raise ProtocolError("FILE_SIZE_MISMATCH", "文件长度与封存清单不一致。", 409)
        if expected_sha is not None:
            hasher = hashlib.sha256()
            while chunk := os.read(descriptor, MAX_CHUNK):
                hasher.update(chunk)
            if hasher.hexdigest() != expected_sha:
                raise ProtocolError("FILE_HASH_MISMATCH", "文件摘要与封存清单不一致。", 409)
            os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def process_identity(pid):
    """使用内核启动时间，拒绝把复用的 PID 当成原执行进程。"""
    if type(pid) is not int or pid <= 1:
        return {"status": "unknown"}
    try:
        if sys.platform == "darwin":
            class BSDInfo(ctypes.Structure):
                _fields_ = [("prefix", ctypes.c_uint32 * 12), ("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32),
                            ("nfiles", ctypes.c_uint32), ("pgid", ctypes.c_uint32), ("pjobc", ctypes.c_uint32),
                            ("tdev", ctypes.c_uint32), ("tpgid", ctypes.c_uint32), ("nice", ctypes.c_int32),
                            ("started_seconds", ctypes.c_uint64), ("started_microseconds", ctypes.c_uint64)]
            library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
            library.proc_pidinfo.restype = ctypes.c_int
            info = BSDInfo()
            count = library.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
            if count == 0 and ctypes.get_errno() == errno.ESRCH:
                return {"status": "absent"}
            if count != ctypes.sizeof(info) or info.prefix[3] != pid:
                return {"status": "unknown"}
            if info.prefix[1] == 5:
                return {"status": "absent"}
            value = {"pid": pid, "pgid": info.pgid, "started": [info.started_seconds, info.started_microseconds], "platform": "darwin"}
        elif sys.platform.startswith("linux"):
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] == "Z":
                return {"status": "absent"}
            value = {"pid": pid, "pgid": int(fields[2]), "started": fields[19],
                     "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "platform": "linux"}
        else:
            return {"status": "unknown"}
        return {**value, "status": "present", "identity_digest": digest(value)}
    except FileNotFoundError:
        return {"status": "absent"}
    except (OSError, ValueError, IndexError):
        return {"status": "unknown"}


def owns_process(record):
    actual = process_identity(record.get("pid"))
    return (actual["status"] == "present" and actual.get("pgid") == record.get("pid")
            and actual.get("identity_digest") == record.get("identity_digest"))


def process_group_absent(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        pass
    return False


def publish_directory(source, destination):
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = function(os.fsencode(source), os.fsencode(destination), 4)
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = function(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise ProtocolError("ATOMIC_PUBLISH_UNAVAILABLE", "当前系统没有已验证的无覆盖发布能力。")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))
    sync_directory(Path(destination).parent)
