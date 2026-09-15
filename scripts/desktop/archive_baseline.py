"""只读固定入口中的旧 App，用 APFS 克隆保存可核验的回滚归档。"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import tempfile

from app_version import APP_PATH


def sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def inventory(app):
    root = app.resolve(strict=True)
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("App 资源链接越出包目录：" + name)
            result[name] = {"kind": "symlink", "target": str(path.readlink()), "mode": mode}
        elif path.is_file():
            result[name] = {"kind": "file", "bytes": path.stat().st_size, "sha256": sha256(path), "mode": mode}
        elif path.is_dir():
            result[name] = {"kind": "directory", "mode": mode}
        else:
            raise ValueError("App 包内存在不支持的文件类型：" + name)
    return result


def signature(app):
    verification = subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
                                  capture_output=True, text=True, timeout=120, check=True)
    identity = subprocess.run(["/usr/bin/codesign", "-dvvv", str(app)], capture_output=True, text=True, timeout=30, check=True)
    text = identity.stdout + identity.stderr
    if "Authority=Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)" not in text:
        raise ValueError("旧 App 的签名组织不匹配")
    return {"identity": text, "verification": verification.stdout + verification.stderr}


def archive(root, output):
    app = root / APP_PATH
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("已有回滚归档，拒绝覆盖：" + str(output))
    if not output.is_relative_to(root / ".artifacts/desktop"):
        raise ValueError("回滚归档必须位于当前项目 .artifacts/desktop")
    output.parent.mkdir(parents=True, exist_ok=True)
    original_signature = signature(app)
    original = inventory(app)
    metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if metadata.get("CFBundleIdentifier") != "org.gcsa.ailab":
        raise ValueError("旧 App 安装身份不匹配")
    temporary = Path(tempfile.mkdtemp(prefix=".upgrade-baseline-", dir=output.parent))
    try:
        cloned = temporary / app.name
        subprocess.run(["/bin/cp", "-cR", "-p", "-P", str(app), str(cloned)], check=True, capture_output=True, text=True)
        copied = inventory(cloned)
        if copied != original or inventory(app) != original:
            raise ValueError("回滚归档与原 App 不一致，或原 App 在归档期间发生变化")
        archived_signature = signature(cloned)
        manifest = {"status": "rollback_baseline_verified", "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_app": str(app), "archived_app": str(output / app.name), "copy_method": "APFS clone（cp -cR -p -P）",
                    "bundle_identifier": metadata["CFBundleIdentifier"], "version": metadata["CFBundleShortVersionString"],
                    "build": metadata.get("CFBundleVersion"), "source_unchanged": True, "file_tree": original,
                    "file_tree_sha256": hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                    "source_signature": original_signature, "archive_signature": archived_signature,
                    "acceptance_scope": "旧候选回滚归档与签名完整性；不是新版功能或干净机器验收"}
        path = temporary / "baseline-manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        path.chmod(0o600)
        # 输出目录由本脚本创建且事先不存在；使用 macOS 无覆盖发布防止并发替换。
        import sys
        sys.path.insert(0, str(root / "services/control"))
        from ailab_control.remote.protocol import publish_directory
        publish_directory(temporary, output)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = archive(args.root.resolve(), args.output)
    print(json.dumps({key: result[key] for key in ("status", "archived_app", "version", "build", "file_tree_sha256")}, ensure_ascii=False))
