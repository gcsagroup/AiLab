"""恢复构建时生成的模型导入映射；入口仍须先校验完整运行时文件。"""

import json
import os
from pathlib import Path
import stat


INDEX_NAME = "_ailab_models_import.json"
MAX_INDEX_BYTES = 1024 * 1024


def _strings(values):
    if not isinstance(values, list) or any(type(value) is not str or not value for value in values):
        raise ValueError("模型导入索引的名称列表无效")
    if len(values) != len(set(values)):
        raise ValueError("模型导入索引含重复名称")
    return values


def decode_models_index(raw):
    """按保存顺序恢复原类型；后端判断和顶层动态合并仍由 Transformers 执行。"""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_INDEX_BYTES:
        raise ValueError("模型导入索引大小无效")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("模型导入索引含重复字段")
            result[key] = value
        return result

    document = json.loads(raw, object_pairs_hook=unique_object)
    if (type(document) is not dict
            or set(document) != {"schema_version", "transformers_version", "prefix", "groups"}
            or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or document["transformers_version"] != "4.57.6" or document["prefix"] != "models"
            or not isinstance(document["groups"], list)):
        raise ValueError("模型导入索引版本或范围不符")
    result = {}
    for row in document["groups"]:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[1], list):
            raise ValueError("模型导入索引的后端组无效")
        tags, entries = row
        group = frozenset(_strings(tags))
        if group in result:
            raise ValueError("模型导入索引含重复后端组")
        modules = {}
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("模型导入索引的模块项无效")
            name, objects = entry
            if (type(name) is not str or not name.startswith("models.")
                    or not all(part.isidentifier() for part in name.split(".")) or name in modules):
                raise ValueError("模型导入索引的模块名无效或重复")
            modules[name] = set(_strings(objects))
        result[group] = modules
    return result


def load_models_index(package_file):
    """只读取同包索引，不扫描源码、不导入模型，也不缓存设备就绪结果。"""
    path = Path(package_file).parent / INDEX_NAME
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_INDEX_BYTES:
            raise ValueError("模型导入索引不是有效的受限文件")
        raw = stream.read(MAX_INDEX_BYTES + 1)
        after = os.fstat(stream.fileno())
        identity = lambda record: (record.st_dev, record.st_ino, record.st_size, record.st_mtime_ns, record.st_ctime_ns)
        if identity(before) != identity(after) or len(raw) != before.st_size:
            raise ValueError("模型导入索引在读取期间变化")
    return decode_models_index(raw)
