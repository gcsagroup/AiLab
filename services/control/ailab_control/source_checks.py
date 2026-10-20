"""外部来源报告的只读核验；任何报告字段均作为数据，不执行复现配置。"""

import hashlib
import json
from pathlib import PurePosixPath, Path
import re

from .assets import authorized_path, regular_path, file_hash
from .evaluation import strict_json
from .storage import Fault, digest


def inspect_document(document, manifest, current_versions):
    if not isinstance(document, dict):
        raise Fault("SOURCE_REPORT_INVALID", "来源报告必须为 JSON 对象。")
    findings = []
    def finding(code, message):
        findings.append({"code": code, "message": message})
    if document.get("tool") == "abliterix":
        tool, version = "Abliterix", document.get("abliterix_version")
        supported = type(document.get("schema_version")) is int and document["schema_version"] == 2
        hashes = document.get("weights")
        packages = document.get("packages", {})
        origin = document.get("source")
        integrity = document.get("integrity", {})
        canonical = json.dumps({k: v for k, v in document.items() if k != "integrity"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        integrity_status = "matched" if isinstance(integrity, dict) and integrity.get("algorithm") == "sha256" and integrity.get("canonical_manifest") == hashlib.sha256(canonical).hexdigest() else "mismatch"
        if integrity_status == "mismatch":
            finding("REPORT_HASH_MISMATCH", "报告自身摘要缺失或不一致。")
    elif "version" in document and isinstance(document.get("environment"), dict) and "heretic" in document["environment"]:
        tool = "Heretic"
        info = document["environment"]["heretic"]
        if not isinstance(info, dict):
            raise Fault("SOURCE_REPORT_INVALID", "Heretic 版本信息无效。")
        version, origin = info.get("version"), info.get("metadata")
        supported = document.get("version") == "4"
        hashes = document.get("hashes")
        packages = document["environment"].get("requirements", {})
        integrity_status = "not_provided"
        finding("REPORT_UNSIGNED", "此格式没有报告自身摘要；文件一致不能证明发布者身份。")
    else:
        raise Fault("SOURCE_REPORT_UNSUPPORTED", "仅支持 Heretic reproduce v4 与 Abliterix schema 2 来源报告。")
    if not supported:
        raise Fault("SOURCE_REPORT_VERSION_UNSUPPORTED", "报告版本尚未支持，未按已知版本解释。")
    if not isinstance(version, str) or not version.strip() or len(version) > 200:
        finding("TOOL_VERSION_MISSING", "报告没有完整工具版本。")
        version = None
    if not origin:
        finding("SOURCE_ORIGIN_MISSING", "报告没有提供工具来源提交信息。")
    if not isinstance(hashes, dict) or not hashes or len(hashes) > 4096:
        raise Fault("SOURCE_WEIGHTS_MISSING", "报告缺少有效文件哈希清单，无法核对模型。")
    entries = {item["path"]: item for item in manifest}
    files = []
    for name, expected in hashes.items():
        if not isinstance(name, str) or not name or len(name) > 512 or "\\" in name or ":" in name or any(ord(char) < 32 for char in name) or PurePosixPath(name).is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")):
            raise Fault("SOURCE_PATH_INVALID", "报告文件名包含绝对路径或目录跳转。")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise Fault("SOURCE_HASH_INVALID", "报告中的 SHA-256 格式无效。")
        actual = entries.get(name, {}).get("sha256")
        files.append({"path": name, "expected": expected.lower(), "actual": actual, "status": "missing" if actual is None else "matched" if expected.lower() == actual else "mismatch"})
    uncovered = sorted(name for name in entries if name.endswith(".safetensors") and name not in hashes)
    if uncovered:
        finding("WEIGHTS_NOT_COVERED", "报告未覆盖所选模型的全部 safetensors 权重。")
    if any(item["status"] != "matched" for item in files):
        finding("FILES_DIFFER", "报告与所选模型存在文件缺失或哈希差异。")
    if not isinstance(packages, dict) or len(packages) > 2048 or any(not isinstance(k, str) or (v is not None and not isinstance(v, str)) for k, v in packages.items()):
        raise Fault("SOURCE_ENVIRONMENT_INVALID", "报告依赖版本必须为名称与版本的字符串映射。")
    normalize = lambda value: value.lower().replace("_", "-")
    local = {normalize(k): v for k, v in current_versions.items()}
    environment = [{"package": key, "reported": value, "current": local.get(normalize(key)), "status": "unavailable" if normalize(key) not in local else "matched" if value == local[normalize(key)] else "different"} for key, value in sorted(packages.items())]
    return {"tool": tool, "tool_version": version, "source": origin, "report_integrity": integrity_status,
            "files": files, "uncovered_weights": uncovered, "environment": environment, "findings": findings,
            "reported_system": document.get("system") if tool == "Heretic" else document.get("environment"),
            "files_match": all(item["status"] == "matched" for item in files) and not uncovered,
            "scope": "只核对所选报告、模型文件与当前 MLX 环境版本；不验证发布者身份，不复现训练，不代表质量或可运行性。"}


class SourceChecks:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def create(self, payload, key=None):
        with self.store.transaction():
            if key and (previous := self.store.replay("source-check", key, payload)):
                return previous
            model = self.store.get("model", payload["model_id"])
            if model["project_id"] != payload["project_id"]:
                raise Fault("PROJECT_MISMATCH", "模型不属于当前项目。", 403)
        roots = [regular_path(path) for path in self.service.settings.import_roots]
        if payload.get("grant_id"):
            grant = self.service.grants.get(payload["grant_id"])
            if grant is None:
                raise Fault("IMPORT_GRANT_EXPIRED", "文件选择已失效，请重新选择。", 403)
            roots.append(grant)
        source = authorized_path(payload["report_path"], roots)
        if not source.is_file() or source.stat().st_size > 1024 * 1024:
            raise Fault("SOURCE_REPORT_INVALID", "来源报告必须为不超过 1 MiB 的 JSON 文件。")
        with source.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise Fault("SOURCE_REPORT_INVALID", "来源报告超过 1 MiB。")
        try:
            document = strict_json(raw.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            raise Fault("SOURCE_REPORT_INVALID", "来源报告不是有效的严格 UTF-8 JSON。") from None
        # 实际重新读入资产文件，不将数据库旧摘要当作当前文件证据。
        actual = []
        root = regular_path(model["storage_path"])
        discovered = sorted(root.rglob("*"))
        if len(discovered) > 8192:
            raise Fault("SOURCE_MODEL_TOO_LARGE", "模型文件数量超出本次核验范围。")
        for entry in model["manifest"]:
            try:
                path = regular_path(Path(model["storage_path"]) / entry["path"])
            except Fault as error:
                if error.code == "SOURCE_NOT_FOUND":
                    continue
                raise
            if path.is_file():
                actual.append({"path": entry["path"], "sha256": file_hash(path), "size": path.stat().st_size})
        environment = self.service.environment(refresh=True)
        facts = environment.get("versions", {})
        result = inspect_document(document, actual, facts.get("dependencies", {}))
        result["current_python"] = facts.get("python")
        result["library_manifest_matches"] = actual == model["manifest"] and not any(path.is_symlink() for path in discovered) and {path.relative_to(root).as_posix() for path in discovered if path.is_file()} == {entry["path"] for entry in model["manifest"]}
        if not result["library_manifest_matches"]:
            result["findings"].append({"code": "LIBRARY_FILES_CHANGED", "message": "当前文件与模型入库时清单不一致。"})
        result["environment_ready"] = environment.get("ready", False)
        with self.store.transaction():
            if key and (previous := self.store.replay("source-check", key, payload)):
                return previous
            if model != self.store.get("model", model["id"]):
                raise Fault("SOURCE_MODEL_CHANGED", "核验期间模型记录发生变化，请重试。", 409)
            record = self.service.resource("source-check", payload["project_id"], name=model["name"] + " · 来源核验", model_id=model["id"], model_version_id=model["version_id"], model_manifest_digest=model["manifest_digest"], source_report_sha256=hashlib.sha256(raw).hexdigest(), source_document=raw.decode("utf-8"), result=result)
            record["record_digest"] = digest(record)
            self.store.put("source-check", record)
            if key:
                self.store.remember("source-check", key, payload, self.service.public(record))
            return self.service.public(record)
