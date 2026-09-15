"""在嵌套代码签名完成后固定各运行时文件清单，再签外层 App 资源封条。"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import shutil


def seal(app, entitlements):
    source_resources = Path(__file__).resolve().parents[2] / "apps/desktop/src-tauri/resources"
    bundled_resources = app / "Contents/Resources/resources"
    # Tauri 的资源通配拷贝会展开链接；MLX 依赖 libmlx 的真实目录寻找 metallib。
    # 先还原 PyInstaller 的链接布局，再重签嵌套 Framework 与外层资源。
    for name in ("control", "mlx", "diffusers", "kokoro", "media-tools"):
        source = source_resources / name
        target = bundled_resources / name
        for original in sorted(source.rglob("*"), key=lambda path: len(path.parts)):
            if not original.is_symlink():
                continue
            destination = target / original.relative_to(source)
            if destination.is_symlink():
                destination.unlink()
            elif destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
            destination.symlink_to(original.readlink())
            if not destination.resolve().is_relative_to(target.resolve()):
                raise ValueError("内置运行时链接越出资源目录")
    subprocess.run(["codesign", "--force", "--deep", "--options", "runtime", "--entitlements", str(entitlements),
                    "--sign", "Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)", str(app)], check=True)
    for name in ("mlx", "diffusers", "kokoro", "media-tools"):
        runtime = bundled_resources / name
        manifest = runtime / "runtime-manifest.json"
        original = json.loads(manifest.read_text())
        files = {str(path.relative_to(runtime)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(runtime.rglob("*")) if path.is_file() and path != manifest}
        manifest.write_text(json.dumps({**original, "files": files}, sort_keys=True, indent=2) + "\n")
    subprocess.run(["codesign", "--force", "--options", "runtime", "--entitlements", str(entitlements),
                    "--sign", "Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)", str(app)], check=True)


if __name__ == "__main__":
    seal(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
