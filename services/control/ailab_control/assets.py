"""只读分析、受限格式检查和原子资产副本。"""

import hashlib
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

from .storage import Fault, digest


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            result.update(block)
    return result.hexdigest()


def regular_path(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise Fault("PATH_NOT_ALLOWED", "请选择绝对路径，路径中不能包含上级跳转。")
    for item in [path, *path.parents]:
        if item.is_symlink():
            raise Fault("PATH_NOT_ALLOWED", "当前导入器不接受符号链接，请选择原始文件。")
    try:
        return path.resolve(strict=True)
    except OSError:
        raise Fault("SOURCE_NOT_FOUND", "所选路径不存在或不可读取。") from None


def authorized_path(value, roots):
    path = regular_path(value)
    if not any(path == root or (root.is_dir() and path.is_relative_to(root)) for root in roots):
        raise Fault("PATH_NOT_ALLOWED", "路径未获授权，请通过应用文件选择器重新选择。", 403)
    return path


def safe_json(path, maximum=16 * 1024 * 1024):
    if path.stat().st_size > maximum:
        raise Fault("INVALID_MODEL_FORMAT", "模型配置文件过大。")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError, OSError):
        raise Fault("INVALID_MODEL_FORMAT", "模型配置不是有效的 UTF-8 JSON。") from None
    if not isinstance(result, dict):
        raise Fault("INVALID_MODEL_FORMAT", "模型配置必须是 JSON 对象。")
    return result


def check_safetensors(path):
    size = path.stat().st_size
    with path.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise Fault("INVALID_MODEL_FORMAT", "权重文件头不完整。")
        length = struct.unpack("<Q", prefix)[0]
        if not 2 <= length <= min(64 * 1024 * 1024, size - 8):
            raise Fault("INVALID_MODEL_FORMAT", "权重文件头无效，未尝试其他反序列化方式。")
        try:
            header = json.loads(stream.read(length))
        except (ValueError, UnicodeError):
            raise Fault("INVALID_MODEL_FORMAT", "权重文件头不是有效 JSON。") from None
    if not isinstance(header, dict) or not any(k != "__metadata__" for k in header):
        raise Fault("INVALID_MODEL_FORMAT", "权重中未找到张量。")
    widths = {"BOOL": 1, "U8": 1, "I8": 1, "F8_E4M3": 1, "F8_E5M2": 1,
              "I16": 2, "U16": 2, "F16": 2, "BF16": 2, "I32": 4, "U32": 4, "F32": 4,
              "I64": 8, "U64": 8, "F64": 8}
    intervals = []
    for name, item in header.items():
        if name == "__metadata__":
            continue
        if not isinstance(item, dict) or item.get("dtype") not in widths:
            raise Fault("INVALID_MODEL_FORMAT", "权重张量类型不受支持。")
        shape, offsets = item.get("shape"), item.get("data_offsets")
        if not isinstance(shape, list) or any(type(n) is not int or n < 0 for n in shape):
            raise Fault("INVALID_MODEL_FORMAT", "权重张量形状无效。")
        if not isinstance(offsets, list) or len(offsets) != 2 or any(type(n) is not int for n in offsets):
            raise Fault("INVALID_MODEL_FORMAT", "权重张量位置无效。")
        total = widths[item["dtype"]]
        for dimension in shape:
            total *= dimension
        start, end = offsets
        if not 0 <= start <= end <= size - length - 8 or end - start != total:
            raise Fault("INVALID_MODEL_FORMAT", "权重大小与张量声明不一致。")
        intervals.append((start, end))
    cursor = 0
    for start, end in sorted(intervals):
        if start != cursor:
            raise Fault("INVALID_MODEL_FORMAT", "权重数据存在重叠或空洞。")
        cursor = end
    if cursor != size - length - 8:
        raise Fault("INVALID_MODEL_FORMAT", "权重末尾存在未声明数据。")


def restricted_execution_boundary():
    """受限加载策略不是操作系统沙箱；子进程仍持有当前用户的文件权限。"""
    return {"scope_semantics": "loader_policy_not_os_permissions",
            "process": "separate_process", "os_sandbox": False,
            "filesystem": "current_user_permissions",
            "network": "offline_loader_options_not_os_block",
            "credentials": "environment_allowlist_not_filesystem_denial",
            "custom_code": "not_supported"}


def model_manifest(path):
    if not path.is_dir():
        raise Fault("INVALID_MODEL_FORMAT", "请选择包含 config.json 和 safetensors 权重的模型目录。")
    files = sorted(item for item in path.rglob("*") if not item.relative_to(path).parts[:2] == (".cache", "huggingface"))
    if len(files) > 10000:
        raise Fault("IMPORT_TOO_LARGE", "模型目录文件数量超过 10000。")
    manifest, weights = [], 0
    allowed = {".json", ".safetensors", ".model", ".txt", ".md", ".jinja", ".tiktoken"}
    for item in files:
        if item.is_symlink():
            raise Fault("PATH_NOT_ALLOWED", "模型目录包含符号链接。")
        if item.is_dir():
            continue
        if not item.is_file():
            raise Fault("PATH_NOT_ALLOWED", "模型目录包含非常规文件。")
        if item.name == ".gitattributes":
            continue
        if item.suffix.lower() not in allowed and not item.name.startswith(("LICENSE", "NOTICE")):
            raise Fault("MODEL_LOAD_TRUST_REQUIRED", "模型包含未知或可执行格式，当前受限加载器不支持。", file=item.name)
        if item.suffix == ".safetensors":
            check_safetensors(item)
            weights += 1
        if item.suffix == ".json":
            config = safe_json(item)
            if config.get("auto_map") or config.get("trust_remote_code"):
                raise Fault("MODEL_LOAD_TRUST_REQUIRED", "模型要求自定义代码执行，当前版本未开放此加载方式。")
        manifest.append({"path": item.relative_to(path).as_posix(), "size": item.stat().st_size, "sha256": file_hash(item)})
    if not weights or not (path / "config.json").is_file() or not (path / "tokenizer_config.json").is_file():
        raise Fault("MODEL_NOT_READY", "模型缺少 safetensors 权重、config.json 或 tokenizer_config.json。")
    config = safe_json(path / "config.json")
    if not config.get("model_type"):
        raise Fault("INVALID_MODEL_FORMAT", "config.json 缺少 model_type。")
    return {"manifest": manifest, "manifest_digest": digest(manifest), "detected_format": "safetensors",
            "family": config["model_type"], "model_config": {key: config.get(key) for key in ("model_type", "hidden_size", "num_hidden_layers", "quantization", "quantization_config")},
            "total_bytes": sum(f["size"] for f in manifest),
            "loader": "mlx_lm.local_restricted", "trust_class": "restricted_weights",
            "execution_scope": {"network": False, "custom_code": False, "credentials": False},
            "execution_boundary": restricted_execution_boundary()}


def dataset_report(path, schema):
    if not path.is_file() or path.suffix.lower() != ".jsonl":
        raise Fault("DATA_SCHEMA_MISMATCH", "请选择 UTF-8 JSONL 文件，每行一个样本。")
    if path.stat().st_size > 256 * 1024 * 1024:
        raise Fault("IMPORT_TOO_LARGE", "首期导入器最多读取 256 MiB JSONL。")
    errors, samples, valid, total = [], [], 0, 0
    try:
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                total += 1
                try:
                    if len(line) > 2 * 1024 * 1024:
                        raise ValueError("单行超过 2 MiB")
                    sample = json.loads(line)
                    if not isinstance(sample, dict):
                        raise ValueError("每行必须是 JSON 对象")
                    if schema == "sft":
                        messages = sample.get("messages")
                        if not isinstance(messages, list) or len(messages) < 2:
                            raise ValueError("messages 至少包含一组提问和回答")
                        expected = "user"
                        for index, message in enumerate(messages):
                            if not isinstance(message, dict) or not isinstance(message.get("content"), str) or not message["content"].strip():
                                raise ValueError("消息内容不能为空")
                            role = message.get("role")
                            if role == "system" and index == 0:
                                continue
                            if role != expected:
                                raise ValueError("system 仅可开头，随后 user 与 assistant 交替")
                            expected = "assistant" if expected == "user" else "user"
                        if messages[-1].get("role") != "assistant":
                            raise ValueError("末条消息必须是 assistant 回答")
                    elif schema == "cpt":
                        if not isinstance(sample.get("text"), str) or not sample["text"].strip() or not isinstance(sample.get("source_id"), str) or not sample["source_id"].strip():
                            raise ValueError("cpt 需要非空 text 和 source_id")
                    else:
                        raise Fault("UNSUPPORTED_COMBINATION", "首期数据导入只支持 sft 与 cpt。")
                    valid += 1
                    if len(samples) < 3:
                        samples.append(sample)
                except (ValueError, TypeError) as error:
                    if len(errors) < 100:
                        errors.append({"line": number, "message": str(error)[:160]})
    except UnicodeError:
        raise Fault("DATA_SCHEMA_MISMATCH", "数据文件不是有效 UTF-8 编码。") from None
    return {"schema": schema, "sample_count": valid, "total_count": total, "failed_count": total - valid,
            "skipped_count": 0, "issues": errors, "samples": samples,
            "checks": {"encoding": "passed", "structure": "passed" if total == valid and valid else "failed",
                       "tokenization": "not_run", "quality": "not_run", "split_leakage": "not_run"},
            "can_import": bool(valid and total == valid), "sha256": file_hash(path), "total_bytes": path.stat().st_size}


def copy_asset(source, target_root, manifest, key):
    destination = target_root / key
    if destination.exists():
        verify_manifest(destination, manifest)
        return destination
    temporary = Path(tempfile.mkdtemp(prefix=".import-", dir=target_root))
    try:
        for entry in manifest:
            origin = source / entry["path"] if source.is_dir() else source
            regular_path(origin)
            target = temporary / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
            if target.stat().st_size != entry["size"] or file_hash(target) != entry["sha256"]:
                raise Fault("SOURCE_CHANGED", "导入期间源文件发生变化，请重新分析。", 409)
            with target.open("rb") as stream:
                os.fsync(stream.fileno())
            target.chmod(0o400)
        try:
            os.rename(temporary, destination)
        except OSError:
            if not destination.is_dir():
                raise
            verify_manifest(destination, manifest)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def verify_manifest(directory, manifest):
    regular_path(directory)
    expected = {entry["path"] for entry in manifest}
    files = list(directory.rglob("*"))
    if any(item.is_symlink() for item in files):
        raise Fault("ARTIFACT_CORRUPT", "已登记资产目录包含符号链接。", 409)
    actual = {item.relative_to(directory).as_posix() for item in files if item.is_file()}
    if actual != expected:
        raise Fault("ARTIFACT_CORRUPT", "已登记资产文件集合发生变化，请重新导入。", 409)
    for entry in manifest:
        path = directory / entry["path"]
        if not path.is_file() or path.is_symlink() or path.stat().st_size != entry["size"] or file_hash(path) != entry["sha256"]:
            raise Fault("ARTIFACT_CORRUPT", "已登记资产缺失或摘要不符，请重新导入。", 409)
