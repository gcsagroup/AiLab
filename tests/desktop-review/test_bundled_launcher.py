"""实进程验证内置入口的持久登记和授权边界，不占用 GPU。"""

import json
import importlib.util
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ENTRY = Path(__file__).resolve().parents[2] / "scripts/desktop/mlx_entry.py"


def command(tmp_path, parent):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}")
    return [sys.executable, str(ENTRY), "--mode", "launch", "--snapshot", str(snapshot),
            "--output-dir", str(tmp_path / "output"), "--controller-pid", str(parent)]


def test_foreign_controller_never_receives_ownership(tmp_path):
    result = subprocess.run(command(tmp_path, os.getpid() + 1000000), capture_output=True, text=True, timeout=5)
    assert result.returncode == 130
    assert not (tmp_path / "process.json").exists()
    assert not (tmp_path / "output").exists()


def test_arbitrary_worker_script_is_not_a_supported_command(tmp_path):
    script = tmp_path / "arbitrary.py"
    marker = tmp_path / "executed"
    script.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    result = subprocess.run([*command(tmp_path, os.getpid()), "--worker-script", str(script)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    assert not marker.exists()
    assert not (tmp_path / "process.json").exists()


@pytest.mark.parametrize("authorize", [True, False])
def test_start_requires_matching_receipt(tmp_path, authorize):
    process = subprocess.Popen(command(tmp_path, os.getpid()), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               env={**os.environ, "PYTHONPATH": str(ENTRY.parents[2])})
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "process.json").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        record = json.loads((tmp_path / "process.json").read_text())
        assert record["pid"] == process.pid
        assert record["controller_pid"] == os.getpid()
        assert record["launch_protocol"] == 1
        assert process.poll() is None
        assert not (tmp_path / "output").exists()
        (tmp_path / "start-authorized.json").write_text(json.dumps({"pid": process.pid if authorize else 1,
                                                                  "snapshot_sha256": record["snapshot_sha256"]}))
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 1
        if authorize:
            assert json.loads(stdout)["code"] == "UNSUPPORTED_OPERATION", stderr
        else:
            assert not stdout and not stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize("launcher", ["mlx", "media", "external"])
def test_snapshot_changed_after_registration_never_executes(tmp_path, launcher):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}")
    marker = tmp_path / "executed"
    if launcher == "mlx":
        args = command(tmp_path, os.getpid())
    elif launcher == "media":
        internal = tmp_path / "kokoro/_internal"
        internal.mkdir(parents=True)
        source_manifest = internal / "source-manifest.json"
        source_manifest.write_text('{"profile":"kokoro"}')
        (internal.parent / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "files": {"_internal/source-manifest.json": hashlib.sha256(source_manifest.read_bytes()).hexdigest()}}))
        script = tmp_path / "frozen_fixture.py"
        script.write_text(f"import runpy,sys\nsys._MEIPASS={str(internal)!r}\nrunpy.run_path({str(ENTRY.with_name('media_entry.py'))!r},run_name='__main__')\n")
        args = [sys.executable, str(script), "--mode", "launch", "--snapshot", str(snapshot), "--output-dir", str(tmp_path / "output"), "--controller-pid", str(os.getpid())]
    else:
        source = ENTRY.parents[2] / "services/control/ailab_control/launcher.py"
        spec = importlib.util.spec_from_file_location("external_launcher_source", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        script = tmp_path / "launcher.py"
        script.write_text(module.SOURCE)
        worker = tmp_path / "worker.py"
        worker.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        args = [sys.executable, str(script), "--worker-script", str(worker), "--snapshot", str(snapshot), "--output-dir", str(tmp_path / "output"), "--controller-pid", str(os.getpid())]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               env={**os.environ, "PYTHONPATH": str(ENTRY.parents[2])})
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "process.json").exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        receipt = json.loads((tmp_path / "process.json").read_text())
        snapshot.write_text('{"operation":"changed-after-registration"}')
        (tmp_path / "start-authorized.json").write_text(json.dumps({"pid": process.pid, "snapshot_sha256": receipt["snapshot_sha256"]}))
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 1 and not stdout and not stderr
        assert not marker.exists() and not (tmp_path / "output").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
