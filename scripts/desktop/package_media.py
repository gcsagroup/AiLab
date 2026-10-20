"""从固定 profile 打包完整媒体运行时、资源、源码身份和许可。"""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile

import PyInstaller.__main__
from PyInstaller.building.utils import format_binaries_and_datas
from PyInstaller.utils.hooks import collect_all, copy_metadata

_INDEX_SPEC = importlib.util.spec_from_file_location("ailab_transformers_index", Path(__file__).with_name("transformers_index.py"))
transformers_index = importlib.util.module_from_spec(_INDEX_SPEC)
_INDEX_SPEC.loader.exec_module(transformers_index)

PROFILES = {
    "diffusers": {"python": "3.13.9", "packages": ["torch", "diffusers", "transformers", "peft", "accelerate", "tokenizers", "safetensors", "numpy", "PIL", "coremltools", "onnx", "onnxruntime", "ml_dtypes"],
                  "modules": ["workers.format_worker", "adapters.media.text_formats", "ailab_control.format_assets", "workers.media_worker", "adapters.media.preflight", "adapters.media.image_cli", "adapters.media.video_cli", "prepare_tiny_sd", "prepare_svd", "image_cli"]},
    "kokoro": {"python": "3.10.19", "packages": ["torch", "kokoro", "misaki", "transformers", "tokenizers", "safetensors", "numpy", "spacy", "spacy_curated_transformers", "jieba", "pypinyin", "pypinyin_dict", "cn2an", "espeakng_loader", "_soundfile_data"],
               "modules": ["workers.tts_worker", "tts_cli", "tts_prepare"]},
}
IDENTITY = "Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)"


def dependencies(lock):
    result = {}
    for line in lock.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
        if not match:
            raise ValueError("媒体依赖锁必须完整固定版本和包摘要")
        name, version, _ = match.groups()
        if name in result or importlib.metadata.version(name) != version:
            raise ValueError("媒体依赖版本不符或重复：" + name)
        result[name] = version
    return result


def licenses(output, required):
    root = output / "licenses"
    root.mkdir()
    python_root = Path(sys.base_prefix).resolve()
    python_license = next((parent / "LICENSE" for parent in [python_root, *python_root.parents] if (parent / "LICENSE").is_file()), None)
    if python_license is None:
        raise ValueError("找不到 Python 运行时许可")
    (root / "Python").mkdir()
    shutil.copy2(python_license, root / "Python/LICENSE")
    records = [{"name": "Python", "version": platform.python_version(), "license": "PSF", "files": ["licenses/Python/LICENSE"]}]
    for name in sorted(required):
        distribution = importlib.metadata.distribution(name)
        destination = root / name
        destination.mkdir()
        files = []
        for file in distribution.files or []:
            if any(word in file.name.upper() for word in ["LICENSE", "LICENCE", "COPYING", "NOTICE"]):
                original = Path(distribution.locate_file(file))
                if original.is_file():
                    copied = destination / str(file).replace("/", "_")
                    shutil.copy2(original, copied)
                    files.append(str(copied.relative_to(output)))
        (destination / "METADATA.txt").write_text(distribution.read_text("METADATA") or "", encoding="utf-8")
        records.append({"name": name, "version": distribution.version, "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License"), "files": files})
    (root / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")


def dependency_data(required):
    """包含全部冻结依赖的词典、JSON 与其它数据，避免只收集顶层推理库。"""
    result = []
    for name in required:
        distribution = importlib.metadata.distribution(name)
        for relative in distribution.files or []:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or any(part in {"tests", "testing", "__pycache__"} for part in path.parts):
                continue
            if any(part.endswith((".dist-info", ".egg-info", ".data")) for part in path.parts):
                continue
            if path.suffix in {".py", ".pyc", ".pyo", ".pyi", ".so", ".dylib", ".a", ".h", ".hpp", ".c", ".cpp"}:
                continue
            original = Path(distribution.locate_file(relative))
            if original.is_file():
                result.append((str(original), str(path.parent)))
    return result


def media_runtime_data(datas):
    """先用官方展开器解析目录和 glob，只排除 Torch 编译头文件。"""
    result = []
    for target, source in sorted(format_binaries_and_datas(datas)):
        path = Path(target)
        if path.parts[:2] == ("torch", "include") and path.suffix in {".h", ".hpp", ".cuh"}:
            continue
        result.append((source, str(path.parent)))
    return result


def prepare_overlay(packaging, required, source):
    package = Path(importlib.metadata.distribution("transformers").locate_file("transformers"))
    overlay = Path(tempfile.mkdtemp(prefix="transformers-source-", dir=packaging)) / "transformers"
    provenance = transformers_index.prepare_overlay(package, overlay, source / "application/scripts/desktop/transformers_index_runtime.py",
                                                    required.get("transformers"))
    return overlay, provenance


def finalize_transformers(runtime, provenance):
    package = runtime / "_internal/transformers"
    result = transformers_index.finalize_index(package, provenance)
    manifest = runtime / "_internal/source-manifest.json"
    value = json.loads(manifest.read_text())
    value["transformers_index"] = result
    manifest.write_text(json.dumps(value, sort_keys=True) + "\n")


def build(root, source, profile):
    configuration = PROFILES[profile]
    if platform.python_version() != configuration["python"]:
        raise ValueError("打包 Python 版本必须与已验证 profile 一致")
    artifacts = root / ".artifacts/desktop"
    lock = source / f"entry/runtime-{profile}.lock.txt"
    required = dependencies(lock)
    source_paths = [path for prefix in ["workers", "adapters", "services", "entry"] for path in (source / prefix).rglob("*") if path.is_file() and (path.suffix == ".py" or path.name.endswith("lock.txt"))]
    sources = {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    packaging = artifacts / f"{profile}-packaging-data"
    packaging.mkdir(exist_ok=True)
    overlay, index_provenance = prepare_overlay(packaging, required, source)
    (packaging / "source-manifest.json").write_text(json.dumps({"schema_version": 1, "profile": profile, "python": configuration["python"], "sources": sources, "required_dependencies": required,
                                                               "requirements_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()}, sort_keys=True) + "\n")
    datas = [(str(packaging / "source-manifest.json"), ".")]
    datas.extend((str(path), str(path.parent.relative_to(source))) for path in source_paths)
    # 现有固定 CLI 使用同目录模块名导入；其 __file__ 也需有同份真实源文件。
    datas.extend((str(source / "adapters/media" / (name + ".py")), ".") for name in configuration["modules"] if "." not in name)
    binaries, hidden = [], []
    for package in configuration["packages"]:
        package_data, package_binaries, package_hidden = collect_all(package, filter_submodules=lambda name: ".tests" not in name and ".testing" not in name)
        datas.extend(package_data)
        binaries.extend(package_binaries)
        hidden.extend(package_hidden)
    for name in required:
        datas.extend(copy_metadata(name))
    datas.extend(dependency_data(required))
    datas = media_runtime_data(datas)
    datas = transformers_index.overlay_datas(datas, overlay)
    hidden.append("transformers._ailab_import_index")
    options = ["--noconfirm", "--onedir", "--name", f"ailab-{profile}", "--distpath", str(artifacts / f"{profile}-dist"), "--workpath", str(artifacts / f"{profile}-build"),
               "--specpath", str(artifacts), "--paths", str(overlay.parent), "--paths", str(source), "--paths", str(source / "adapters/media"), "--paths", str(source / "services/control"), "--codesign-identity", IDENTITY]
    if profile == "kokoro":
        # Python 3.10 下 pkg_resources 的启动钩子会先导入 vendored backports.tarfile。
        vendor = Path(importlib.metadata.distribution("setuptools").locate_file("setuptools/_vendor"))
        options.extend(["--paths", str(vendor)])
        hidden.extend(["backports", "backports.tarfile", "backports.tarfile.compat.py38"])
    for path, destination in datas:
        options.extend(["--add-data", f"{path}:{destination}"])
    for path, destination in binaries:
        options.extend(["--add-binary", f"{path}:{destination}"])
    for module in sorted(set([*hidden, *configuration["modules"]])):
        options.extend(["--hidden-import", module])
    options.extend(["--exclude-module", "pytest", "--exclude-module", "IPython", "--exclude-module", "notebook", str(source / "entry/media_entry.py")])
    PyInstaller.__main__.run(options)
    output = artifacts / f"{profile}-dist/ailab-{profile}"
    transformers_index.verify_executable_sources(output / f"ailab-{profile}", overlay)
    licenses(output, required)
    shutil.copy2(lock, output / "requirements.lock.txt")
    shutil.copy2(source / f"entry/runtime-{profile}.sources.json", output / "dependency-sources.json")
    finalize_transformers(output, index_provenance)
    files = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.rglob("*")) if path.is_file()}
    (output / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "profile": profile, "files": files}, sort_keys=True, indent=2) + "\n")
    destination = root / f"apps/desktop/src-tauri/resources/{profile}"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(output, destination, symlinks=True)
    finalize_transformers(destination, index_provenance)
    files = {str(path.relative_to(destination)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(destination.rglob("*"))
             if path.is_file() and path != destination / "runtime-manifest.json"}
    (destination / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "profile": profile, "files": files}, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"profile": profile, "output": str(destination), "bytes": sum(path.stat().st_size for path in destination.rglob("*") if path.is_file()), "sources": sources}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("profile", choices=PROFILES)
    args = parser.parse_args()
    build(args.root.resolve(), args.source.resolve(), args.profile)
