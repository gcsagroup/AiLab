"""在隔离目录实际运行版本命令，验证编号、同步、失败记录及包内身份。"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/desktop/app_version.py"
SPEC = importlib.util.spec_from_file_location("desktop_app_version", SCRIPT)
versioning = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versioning)


@pytest.fixture
def checkout(tmp_path):
    for relative in ("scripts/desktop/version.json", "package.json", "package-lock.json", "apps/desktop/src-tauri/Cargo.toml",
                     "apps/desktop/src-tauri/Cargo.lock", "apps/desktop/src-tauri/tauri.conf.json", "services/control/pyproject.toml"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (tmp_path / versioning.VERSION_FILE).write_text(versioning.json_text({"schema_version": 1, "version": "2.0.0", "build": 0}))
    return tmp_path


def run(root, *arguments, success=True):
    result = subprocess.run([sys.executable, str(SCRIPT), *arguments, "--root", str(root)], capture_output=True, text=True)
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    return result


def bundle(root, value):
    app = root / versioning.APP_PATH
    (app / "Contents/Resources/resources/control").mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": value["version"], "CFBundleVersion": str(value["build"])}))
    manifest = {"application_version": value, "files": {"application/" + str(versioning.VERSION_FILE): hashlib.sha256(versioning.json_text(value).encode()).hexdigest()}}
    (app / "Contents/Resources/resources/control/build-manifest.json").write_text(versioning.json_text(manifest))
    return app


def test_real_command_syncs_every_consumer_without_counting_validation(checkout):
    assert run(checkout, "sync").stdout.strip() == "Ver2.0(000)"
    run(checkout, "check")
    assert run(checkout, "begin").stdout.strip() == "Ver2.0(001)"
    run(checkout, "check")
    run(checkout, "check")
    value = versioning.read_version(checkout)
    assert value["build"] == 1
    assert json.loads((checkout / "package-lock.json").read_text())["packages"][""]["version"] == "2.0.0"
    config = json.loads((checkout / "apps/desktop/src-tauri/tauri.conf.json").read_text())
    assert config["version"] == "2.0.0" and config["bundle"]["macOS"]["bundleVersion"] == "1"
    assert 'APP_VERSION_LABEL = "Ver2.0(001)"' in (checkout / "apps/desktop/src/version.ts").read_text()
    assert '__version_label__ = "Ver2.0(001)"' in (checkout / "services/control/ailab_control/__init__.py").read_text()


def test_failed_build_keeps_record_and_next_attempt_has_new_number(checkout):
    run(checkout, "begin")
    run(checkout, "finish", "--status", "failed")
    first = json.loads((checkout / ".artifacts/desktop/version-history/build-0001.json").read_text())
    assert first["status"] == "failed" and first["label"] == "Ver2.0(001)"
    run(checkout, "begin")
    assert versioning.read_version(checkout)["build"] == 2
    second = json.loads((checkout / ".artifacts/desktop/version-history/build-0002.json").read_text())
    assert second["status"] == "building" and second["app_path"] == str(checkout / versioning.APP_PATH)
    assert first == json.loads((checkout / ".artifacts/desktop/version-history/build-0001.json").read_text())


def test_parallel_reservations_cannot_reuse_number(checkout):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run(checkout, "begin").stdout.strip(), range(4)))
    assert set(results) == {f"Ver2.0({number:03d})" for number in range(1, 5)}
    assert versioning.read_version(checkout)["build"] == 4
    assert len(list((checkout / ".artifacts/desktop/version-history").glob("build-*.json"))) == 4
    run(checkout, "check")


def test_drift_is_rejected_without_overwriting_user_file(checkout):
    run(checkout, "begin")
    target = checkout / "apps/desktop/src/version.ts"
    target.write_text("// 手工修改的版本\n")
    failure = run(checkout, "check", success=False)
    assert "版本未同步" in failure.stderr
    assert target.read_text() == "// 手工修改的版本\n"


def test_bundle_version_build_and_source_digest_are_checked(checkout):
    run(checkout, "begin")
    app = bundle(checkout, versioning.read_version(checkout))
    run(checkout, "check", "--app", str(app))
    metadata = app / "Contents/Info.plist"
    metadata.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "2.0.0", "CFBundleVersion": "0"}))
    assert "构建编号" in run(checkout, "check", "--app", str(app), success=False).stderr
    metadata.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "2.0.0", "CFBundleVersion": "1"}))
    path = app / "Contents/Resources/resources/control/build-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"]["application/" + str(versioning.VERSION_FILE)] = "f" * 64
    path.write_text(versioning.json_text(manifest))
    assert "冻结源码摘要" in run(checkout, "check", "--app", str(app), success=False).stderr


def test_different_app_path_and_repeated_completion_are_rejected(checkout):
    run(checkout, "begin")
    app = bundle(checkout, versioning.read_version(checkout))
    renamed = app.with_name("额外入口.app")
    shutil.copytree(app, renamed)
    assert "固定 App 路径" in run(checkout, "check", "--app", str(renamed), success=False).stderr
    run(checkout, "finish", "--status", "failed")
    assert "已经结束" in run(checkout, "finish", "--status", "failed", success=False).stderr


def test_success_requires_current_bundle_report_and_records_its_digest(checkout):
    run(checkout, "begin")
    value = versioning.read_version(checkout)
    bundle(checkout, value)
    report = checkout / ".artifacts/desktop/bundle-verification.json"
    report.write_text(versioning.json_text({"application_version": {**value, "build": 0}}))
    assert "包验证报告不是当前" in run(checkout, "finish", "--status", "succeeded", success=False).stderr
    assert json.loads(versioning.history_path(checkout, value).read_text())["status"] == "building"
    report.write_text(versioning.json_text({"application_version": value}))
    run(checkout, "finish", "--status", "succeeded")
    record = json.loads(versioning.history_path(checkout, value).read_text())
    assert record["status"] == "succeeded"
    assert record["verification_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()


def test_legacy_dependency_versions_are_not_changed(checkout):
    lock = checkout / "apps/desktop/src-tauri/Cargo.lock"
    # 当前仓库会持续增版；只将夹具中的应用版本降为旧值，依赖逐字保留。
    before, replacements = re.subn(r'(^name = "gcsa-ailab"\nversion = )"[^\"]+"',
                                   r'\g<1>"0.1.0"', lock.read_text(), flags=re.MULTILINE)
    assert replacements == 1
    lock.write_text(before)
    run(checkout, "begin")
    assert lock.read_text() == before.replace('name = "gcsa-ailab"\nversion = "0.1.0"', 'name = "gcsa-ailab"\nversion = "2.0.0"')


@pytest.mark.parametrize("value", ["v2", "2.00.0", "2.0.0-private", "$(private).0.0"])
def test_invalid_version_never_changes_generated_files(checkout, value):
    path = checkout / versioning.VERSION_FILE
    path.write_text(versioning.json_text({"schema_version": 1, "version": value, "build": 0}))
    original = (checkout / "package.json").read_bytes()
    run(checkout, "begin", success=False)
    assert (checkout / "package.json").read_bytes() == original
    assert not (checkout / ".artifacts/desktop/version-history").exists()
