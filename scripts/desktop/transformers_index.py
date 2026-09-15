"""为固定 Transformers 生成顶层静态索引；只解析源码，不导入模型库。"""

import ast
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import CodeType, ModuleType
from typing import Optional


VERSION = "4.57.6"
SOURCE_SHA256 = {
    "__init__.py": "aa8cb54da488cf43ba37b9955bb6c0d84d2000db0306f6a5f1c20b6842482d04",
    "utils/import_utils.py": "66b2ac40be2c538dbd9409370c1f6bf769934b8b232edac365e16299c5ec1108",
    "models/albert/__init__.py": "5a343836d37128d8fb1ef93d940d8e5e67600ff48d169d702d2d9e78bdfe5a81",
}
MODELS_SHA256 = "139751215967509f3990e949a5df4d7bf76a03412bb039eebf10a0f210fef07c"
FUNCTIONS = {"fetch__all__", "create_import_structure_from_path", "spread_import_structure", "define_import_structure"}
INDEX_NAME = "_ailab_models_import.json"
LOADER_NAME = "_ailab_import_index.py"
ORIGINAL_CALL = '    import_structure = define_import_structure(Path(__file__).parent / "models", prefix="models")'
INDEX_CALL = '    from ._ailab_import_index import load_models_index\n\n    import_structure = load_models_index(__file__)'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(files):
    return sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())


def source_files(package):
    """完整复制来源不含解释器缓存，拒绝链接和非常规文件。"""
    result = {}
    if package.is_symlink() or not package.is_dir():
        raise ValueError("Transformers 来源必须是实际目录")
    for path in sorted(package.rglob("*")):
        relative = path.relative_to(package)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError("Transformers 源码不能包含链接")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Transformers 源码含非常规文件")
        raw = path.read_bytes()
        result[relative.as_posix()] = {"sha256": sha(raw), "bytes": len(raw)}
    return result


def original_mapping(package):
    """只执行已固定的四个文本解析函数及其文件名后端规则。"""
    algorithm = package / "utils/import_utils.py"
    raw = algorithm.read_bytes()
    if sha(raw) != SOURCE_SHA256["utils/import_utils.py"]:
        raise ValueError("Transformers 导入索引算法来源变化")
    if fingerprint(source_files(package / "models")) != MODELS_SHA256:
        raise ValueError("Transformers 模型源码集合变化")
    nodes = [node for node in ast.parse(raw).body
             if (isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS)
             or (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "BASE_FILE_REQUIREMENTS"
                                                     for target in node.targets))]
    if len(nodes) != 5 or {node.name for node in nodes if isinstance(node, ast.FunctionDef)} != FUNCTIONS:
        raise ValueError("Transformers 固定解析函数不完整")
    namespace = {"os": os, "lru_cache": lru_cache, "Optional": Optional,
                 "IMPORT_STRUCTURE_T": dict[frozenset[str], dict[str, set[str]]]}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(algorithm), "exec"), namespace)
    return namespace["define_import_structure"](str(package / "models"), prefix="models")


def ordered(mapping):
    return [[sorted(tags), [[module, sorted(objects)] for module, objects in modules.items()]]
            for tags, modules in mapping.items()]


def runtime_module(package):
    # 只在内存中加载自有读取器，验包时不能向签名目录写入 __pycache__。
    path = Path(package) / LOADER_NAME
    module = ModuleType("ailab_transformers_index_check")
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def verify_final_index(package):
    """按当前最终目录顺序复算；只能核对，不会修补错误索引。"""
    package = Path(package)
    expected = original_mapping(package)
    restored = runtime_module(package).load_models_index(package / "__init__.py")
    if (type(restored) is not dict or expected != restored or ordered(expected) != ordered(restored)
            or any(type(tags) is not frozenset or type(modules) is not dict
                   or any(type(objects) is not set for objects in modules.values())
                   for tags, modules in restored.items())):
        raise ValueError("Transformers 索引与最终源码映射或顺序不一致")
    return {"index_sha256": sha((package / INDEX_NAME).read_bytes()), "backend_groups": len(expected),
            "module_entries": sum(len(modules) for modules in expected.values()),
            "object_entries": sum(len(objects) for modules in expected.values() for objects in modules.values())}


def finalize_index(package, provenance):
    """复制结束后重建一次，不能假设复制前后目录枚举顺序相同。"""
    package = Path(package)
    files = source_files(package)
    if (files.get("__init__.py", {}).get("sha256") != provenance["patched_init_sha256"]
            or files.get(LOADER_NAME, {}).get("sha256") != provenance["loader_sha256"]):
        raise ValueError("Transformers 覆盖源码或索引读取器变化")
    files["__init__.py"] = provenance["original_init"]
    files.pop(LOADER_NAME)
    files.pop(INDEX_NAME, None)
    if fingerprint(files) != provenance["source_tree_sha256"]:
        raise ValueError("Transformers 复制后的完整源码集合变化")
    mapping = original_mapping(package)
    raw = json.dumps({"schema_version": 1, "transformers_version": VERSION, "prefix": "models", "groups": ordered(mapping)},
                     ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    (package / INDEX_NAME).write_bytes(raw)
    return {**provenance, **verify_final_index(package)}


def prepare_overlay(package, overlay, runtime_source, version):
    """仅写本 profile 的新覆盖目录，原 venv 和所有模型源码保持。"""
    package, overlay, runtime_source = Path(package), Path(overlay), Path(runtime_source)
    before = source_files(package)
    if version != VERSION or any(before.get(name, {}).get("sha256") != expected for name, expected in SOURCE_SHA256.items()):
        raise ValueError("Transformers 版本或已核源码指纹不符")
    if INDEX_NAME in before or LOADER_NAME in before:
        raise ValueError("Transformers 来源已经包含索引覆盖文件")
    original_mapping(package)
    original = (package / "__init__.py").read_text()
    if original.count(ORIGINAL_CALL) != 1:
        raise ValueError("Transformers 顶层静态映射调用不唯一")
    shutil.copytree(package, overlay, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    (overlay / "__init__.py").write_text(original.replace(ORIGINAL_CALL, INDEX_CALL), encoding="utf-8")
    shutil.copy2(runtime_source, overlay / LOADER_NAME)
    provenance = {"transformers_version": VERSION, "source_tree_sha256": fingerprint(before),
                  "source_fingerprints": SOURCE_SHA256.copy(), "models_sha256": MODELS_SHA256,
                  "original_init": before["__init__.py"], "patched_init_sha256": sha((overlay / "__init__.py").read_bytes()),
                  "loader_sha256": sha((overlay / LOADER_NAME).read_bytes()), "generator_sha256": sha(Path(__file__).read_bytes())}
    result = finalize_index(overlay, provenance)
    if source_files(package) != before:
        raise ValueError("Transformers 原来源在准备期间变化")
    return result


def overlay_datas(datas, overlay):
    """用同一完整源码副本提供数据文件，避免 PYZ 新代码搭配旧 .py。"""
    result = [(source, destination) for source, destination in datas
              if (Path(destination) / Path(source).name).parts[0] != "transformers"]
    for name in source_files(Path(overlay)):
        path = Path(overlay) / name
        result.append((str(path), str(Path("transformers") / Path(name).parent)))
    return result


def verify_pyz_sources(reader, overlay):
    """比较实际归档的代码对象，避免只更新随包 .py 数据。"""
    def normalized(code):
        return code.replace(co_filename="<transformers-source>",
                            co_consts=tuple(normalized(value) if isinstance(value, CodeType) else value for value in code.co_consts))

    files = {"transformers": "__init__.py", "transformers._ailab_import_index": LOADER_NAME,
             "transformers.models.albert": "models/albert/__init__.py"}
    for name, relative in files.items():
        expected = compile((Path(overlay) / relative).read_bytes(), relative, "exec", dont_inherit=True, optimize=0)
        actual = reader.extract(name)
        if not isinstance(actual, CodeType) or normalized(actual) != normalized(expected):
            raise ValueError("Transformers 实际 PYZ 代码与覆盖源码不一致：" + name)
    return files


def verify_executable_sources(executable, overlay):
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(executable))
    names = [name for name, entry in archive.toc.items() if entry[-1] == "z"]
    if len(names) != 1:
        raise ValueError("媒体可执行文件必须恰含一份 PYZ")
    return verify_pyz_sources(archive.open_embedded_archive(names[0]), overlay)
