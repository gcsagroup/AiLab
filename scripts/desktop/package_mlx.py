"""生成完整 MLX 独立包，保留动态模型模块、Metal 资源和依赖许可。"""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys

import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_all, copy_metadata


def build(root, source):
    artifacts = root / ".artifacts/desktop"
    for relative in ["workers/mlx_worker.py", "workers/mlx_evaluate_worker.py", "workers/mlx_lab.py", "adapters/mlx_text/recipe.py", "adapters/mlx_text/evaluation.py", "adapters/mlx_text/preflight.py", "adapters/mlx_text/split_check.py", "adapters/mlx_text/checkpoint.py", "adapters/mlx_text/inference.py", "adapters/mlx_text/generation.py"]:
        if not (source / relative).is_file():
            raise RuntimeError("缺少内置执行模块，停止打包：" + relative)
    data = artifacts / "mlx-packaging-data"
    data.mkdir(exist_ok=True)
    sources = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
               for prefix in ["workers", "adapters"] for p in (source / prefix).rglob("*.py")}
    sources["entry"] = hashlib.sha256((source / "entry/mlx_entry.py").read_bytes()).hexdigest()
    sources.update({name: sources[path] for name, path in {"worker": "workers/mlx_worker.py", "recipe": "adapters/mlx_text/recipe.py", "preflight": "adapters/mlx_text/preflight.py"}.items()})
    (data / "source-manifest.json").write_text(json.dumps({"sources": sources, "requirements_lock_sha256": hashlib.sha256((source / "adapters/mlx_text/requirements.lock.txt").read_bytes()).hexdigest()}, sort_keys=True))
    datas = [(str(data / "source-manifest.json"), ".")]
    # 配方身份会读取自身源码；冻结模块同时保留对应源文件供摘要核对。
    datas.extend((str(path), str(path.parent.relative_to(source)))
                 for prefix in ["workers", "adapters"] for path in (source / prefix).rglob("*.py"))
    binaries, hiddenimports = [], []
    for package in ["mlx", "mlx_lm", "transformers", "tokenizers", "safetensors", "sentencepiece"]:
        package_data, package_binaries, package_hidden = collect_all(package, filter_submodules=lambda name: ".tests" not in name)
        datas.extend(package_data)
        binaries.extend(package_binaries)
        hiddenimports.extend(package_hidden)
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        datas.extend(copy_metadata(name))
    options = ["--noconfirm", "--onedir", "--name", "ailab-mlx", "--distpath", str(artifacts / "mlx-dist"),
               "--workpath", str(artifacts / "mlx-build"), "--specpath", str(artifacts), "--paths", str(source),
               "--codesign-identity", "Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)"]
    for path, destination in datas:
        options.extend(["--add-data", f"{path}:{destination}"])
    for path, destination in binaries:
        options.extend(["--add-binary", f"{path}:{destination}"])
    for module in sorted(set(hiddenimports)):
        options.extend(["--hidden-import", module])
    options.extend(["--hidden-import", "workers.mlx_lab", "--hidden-import", "workers.mlx_evaluate_worker", "--hidden-import", "adapters.mlx_text.split_check", "--hidden-import", "adapters.mlx_text.checkpoint", "--hidden-import", "adapters.mlx_text.inference", "--hidden-import", "adapters.mlx_text.generation", str(source / "entry/mlx_entry.py")])
    PyInstaller.__main__.run(options)
    output = artifacts / "mlx-dist/ailab-mlx"
    licenses = output / "licenses"
    licenses.mkdir(exist_ok=True)
    records = []
    python_prefix = Path(sys.base_prefix).resolve()
    python_license = next((parent / "LICENSE" for parent in [python_prefix, *python_prefix.parents]
                           if (parent / "LICENSE").is_file()), None)
    if python_license is None:
        raise RuntimeError("找不到当前 Python 运行时许可证，不能完成随包许可清单")
    (licenses / "Python").mkdir(exist_ok=True)
    shutil.copy2(python_license, licenses / "Python/LICENSE")
    records.append({"name": "Python", "version": sys.version.split()[0], "license": "PSF",
                    "files": ["licenses/Python/LICENSE"]})
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        folder = licenses / name
        folder.mkdir(exist_ok=True)
        files = []
        for file in dist.files or []:
            if any(token in file.name.upper() for token in ["LICENSE", "LICENCE", "COPYING", "NOTICE"]):
                original = Path(dist.locate_file(file))
                if original.is_file():
                    destination = folder / str(file).replace("/", "_")
                    shutil.copy2(original, destination)
                    files.append(str(destination.relative_to(output)))
        (folder / "METADATA.txt").write_text(dist.read_text("METADATA") or "", encoding="utf-8")
        records.append({"name": name, "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"), "files": files})
    (licenses / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    files = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "files": files}, sort_keys=True, indent=2) + "\n")
    resource = root / "apps/desktop/src-tauri/resources/mlx"
    if resource.exists():
        shutil.rmtree(resource)
    shutil.copytree(output, resource, symlinks=True)
    print(json.dumps({"output": str(resource), "file_bytes": sum(p.stat().st_size for p in resource.rglob("*") if p.is_file()), "source_sha256": hashlib.sha256((data / "source-manifest.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
