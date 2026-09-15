"""固定本次打包源码，避免打包过程中读取正在变化的开发文件。"""

import hashlib
import json
from pathlib import Path
import shutil
import sys


def application_inputs(root):
    files = [root / name for name in ["package.json", "package-lock.json", "apps/desktop/index.html", "apps/desktop/tsconfig.json", "apps/desktop/vite.config.ts",
                                     "apps/desktop/src-tauri/Cargo.toml", "apps/desktop/src-tauri/Cargo.lock", "apps/desktop/src-tauri/build.rs",
                                     "apps/desktop/src-tauri/tauri.conf.json", "apps/desktop/src-tauri/Entitlements.plist"]]
    for directory in ["apps/desktop/src", "apps/desktop/src-tauri/src", "apps/desktop/src-tauri/capabilities", "apps/desktop/src-tauri/icons"]:
        files.extend(path for path in (root / directory).rglob("*") if path.is_file())
    files.extend(path for path in (root / "scripts/desktop").glob("*") if path.is_file() and path.suffix in {".py", ".sh", ".txt", ".json"})
    return sorted(set(files))


def verify_application_inputs(root, destination):
    manifest = json.loads((destination / "build-manifest.json").read_text())
    expected = {name.removeprefix("application/"): identity for name, identity in manifest["files"].items() if name.startswith("application/")}
    actual = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in application_inputs(root)}
    if not expected or actual != expected:
        changed = sorted(name for name in actual.keys() | expected.keys() if actual.get(name) != expected.get(name))
        raise ValueError("应用构建输入在冻结后发生变化：" + "、".join(changed))
    print("前端、Rust 与打包输入和冻结清单一致：" + str(len(actual)) + " 个文件")


def stage(root: Path, destination: Path):
    root = root.resolve()
    destination = destination.resolve()
    if not destination.is_relative_to(root / ".artifacts" / "desktop"):
        raise ValueError("打包暂存目录必须位于本项目 .artifacts/desktop 内")
    shutil.copytree(root / "services/control/ailab_control", destination / "control/ailab_control", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # 外部媒体 Python 与其配方摘要也需要同一份控制层受限解析源码。
    shutil.copytree(destination / "control/ailab_control", destination / "services/control/ailab_control")
    selected = [str(path.relative_to(root)) for directory in [root / "workers", root / "adapters/mlx_text", root / "adapters/media", root / "adapters/nvidia_text"] for path in directory.glob("*.py")]
    selected.extend(["adapters/mlx_text/requirements.lock.txt", "adapters/media/requirements.lock.txt", "adapters/nvidia_text/requirements.txt"])
    for relative in selected:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
    for relative in ["workers/__init__.py", "adapters/__init__.py"]:
        (destination / relative).write_text("", encoding="utf-8")
    (destination / "entry").mkdir()
    for name in ["control_entry.py", "mlx_entry.py", "media_entry.py", "runtime-diffusers.lock.txt", "runtime-kokoro.lock.txt", "runtime-diffusers.sources.json", "runtime-kokoro.sources.json", "media-packaging.lock.txt", "media-packaging.sources.json"]:
        shutil.copy2(root / "scripts/desktop" / name, destination / "entry" / name)
    for original in application_inputs(root):
        target = destination / "application" / original.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    files = {str(path.relative_to(destination)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(destination.rglob("*")) if path.is_file()}
    manifest = {"schema_version": 1, "application_version": json.loads((root / "scripts/desktop/version.json").read_text()), "files": files, "source_digest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), "packaging_lock_sha256": hashlib.sha256((root / "scripts/desktop/packaging.lock.txt").read_bytes()).hexdigest()}
    (destination / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest["source_digest"])


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[3] == "--verify-application":
        verify_application_inputs(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    else:
        stage(Path(sys.argv[1]), Path(sys.argv[2]))
