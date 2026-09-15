"""同步候选版本、记录每次完整构建，并核对固定路径中的 App。"""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import tempfile


ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = Path("scripts/desktop/version.json")
APP_PATH = Path("apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app")


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def read_version(root):
    value = json.loads((root / VERSION_FILE).read_text())
    if value.get("schema_version") != 1 or not re.fullmatch(r"(?:0|[1-9]\d{0,3})\.(?:0|[1-9]\d{0,3})\.(?:0|[1-9]\d{0,3})", value.get("version", "")):
        raise ValueError("版本必须采用 major.minor.patch 数字格式")
    if type(value.get("build")) is not int or not 0 <= value["build"] <= 9999:
        raise ValueError("构建编号必须是 0 至 9999 的整数")
    return value


def label(value):
    major, minor, patch = value["version"].split(".")
    short = f"{major}.{minor}" + (f".{patch}" if patch != "0" else "")
    return f"Ver{short}({value['build']:03d})"


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def replace_one(content, pattern, replacement):
    changed, count = re.subn(pattern, lambda match: replacement(match), content, count=0, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("版本字段缺失或重复，拒绝同步：" + pattern)
    return changed


def synchronized_files(root, value):
    result = {}
    for relative in ("package.json", "package-lock.json"):
        data = json.loads((root / relative).read_text())
        data["version"] = value["version"]
        if relative.endswith("lock.json"):
            data["packages"][""]["version"] = value["version"]
        result[relative] = json_text(data)
    for relative, section in (("apps/desktop/src-tauri/Cargo.toml", "package"), ("services/control/pyproject.toml", "project")):
        content = (root / relative).read_text()
        pattern = r"(^\[" + section + r"\]\n(?:(?!\[)[^\n]*\n)*?version = )\"[^\"]+\""
        result[relative] = replace_one(content, pattern, lambda match: match[1] + json.dumps(value["version"]))
    relative = "apps/desktop/src-tauri/Cargo.lock"
    result[relative] = replace_one((root / relative).read_text(), r'(^name = "gcsa-ailab"\nversion = )"[^\"]+"', lambda match: match[1] + json.dumps(value["version"]))
    relative = "apps/desktop/src-tauri/tauri.conf.json"
    content = replace_one((root / relative).read_text(), r'(^  "version": )"[^\"]+"', lambda match: match[1] + json.dumps(value["version"]))
    if '"bundleVersion"' not in content:
        content = content.replace('    "macOS": {\n', '    "macOS": {\n      "bundleVersion": "0",\n')
    result[relative] = replace_one(content, r'(^      "bundleVersion": )"[^\"]+"', lambda match: match[1] + json.dumps(str(value["build"])))
    result["apps/desktop/src/version.ts"] = ("// 由 scripts/desktop/app_version.py 生成。\n"
        + f'export const APP_VERSION = "{value["version"]}";\n'
        + f'export const APP_BUILD = {value["build"]};\n'
        + f'export const APP_VERSION_LABEL = "{label(value)}";\n')
    result["services/control/ailab_control/__init__.py"] = ('"""AI Lab 本机控制服务；版本由 scripts/desktop/app_version.py 同步。"""\n\n'
        + f'__version__ = "{value["version"]}"\n'
        + f'__build__ = {value["build"]}\n'
        + f'__version_label__ = "{label(value)}"\n')
    return result


def sync(root, value, check=False):
    expected = synchronized_files(root, value)
    changed = [relative for relative, content in expected.items() if not (root / relative).is_file() or (root / relative).read_text() != content]
    if check and changed:
        raise ValueError("版本未同步：" + "、".join(changed))
    for relative in changed:
        atomic_write(root / relative, expected[relative])
    return changed


def history_path(root, value):
    return root / ".artifacts/desktop/version-history" / f"build-{value['build']:04d}.json"


def begin(root):
    directory = root / ".artifacts/desktop"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "version.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = read_version(root)
        if value["build"] == 9999:
            raise ValueError("构建编号已达上限")
        value["build"] += 1
        # 先保存编号；中断可以跳号，但后续构建不得重复使用旧编号。
        atomic_write(root / VERSION_FILE, json_text(value))
        record = {**value, "label": label(value), "app_path": str((root / APP_PATH).resolve()),
                  "status": "building", "started_at": datetime.now(timezone.utc).isoformat()}
        atomic_write(history_path(root, value), json_text(record))
        sync(root, value)
        return value


def bundle_version(app, manifest):
    if "application_version" not in manifest:
        raise ValueError("此历史包尚未包含当前版本规则，请先构建新版候选")
    value = manifest["application_version"]
    version_hash = hashlib.sha256(json_text(value).encode()).hexdigest()
    if manifest["files"].get("application/" + str(VERSION_FILE)) != version_hash:
        raise ValueError("包内版本与冻结源码摘要不一致")
    metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if metadata.get("CFBundleShortVersionString") != value["version"] or metadata.get("CFBundleVersion") != str(value["build"]):
        raise ValueError("App 的显示版本或构建编号与冻结源码不一致")
    return {**value, "label": label(value)}


def check_app(root, app, value):
    if app.resolve() != (root / APP_PATH).resolve():
        raise ValueError("开发、运行和交付应使用固定 App 路径：" + str(root / APP_PATH))
    manifest = json.loads((app / "Contents/Resources/resources/control/build-manifest.json").read_text())
    actual = bundle_version(app, manifest)
    if any(actual[key] != value[key] for key in ("version", "build")):
        raise ValueError("固定路径中的 App 不是当前构建编号")
    return actual


def finish(root, value, status):
    path = history_path(root, value)
    record = json.loads(path.read_text())
    if record["status"] != "building":
        raise ValueError("构建记录已经结束")
    if status == "succeeded":
        sync(root, value, check=True)
        check_app(root, root / APP_PATH, value)
        report = root / ".artifacts/desktop/bundle-verification.json"
        identity = json.loads(report.read_text()).get("application_version", {})
        if any(identity.get(key) != value[key] for key in ("version", "build")):
            raise ValueError("包验证报告不是当前构建编号")
        record["verification_sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
    record.update(status=status, finished_at=datetime.now(timezone.utc).isoformat())
    atomic_write(path, json_text(record))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sync", "begin", "check", "finish"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--app", type=Path)
    parser.add_argument("--status", choices=("succeeded", "failed"))
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    value = begin(root) if arguments.command == "begin" else read_version(root)
    if arguments.command in {"sync", "check"}:
        sync(root, value, check=arguments.command == "check")
        if arguments.app:
            check_app(root, arguments.app, value)
    elif arguments.command == "finish":
        if arguments.status is None:
            parser.error("finish 需要 --status")
        finish(root, value, arguments.status)
    print(label(value))
