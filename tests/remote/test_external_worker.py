"""真实外部进程的两阶段授权、输入冻结和取消；仅合同夹具。"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/control"))
from ailab_control.remote.protocol import ProtocolError, digest, encode, process_group_absent, write_json
from ailab_control.remote.server import Executor
from ailab_control.remote.runner import Context, Cancelled
from ailab_control.remote.external import execute
import ailab_control.remote.external as external


@pytest.fixture
def external_rig(tmp_path):
    executor = Executor(tmp_path / "外部进程协议", secrets.token_urlsafe(48))
    content = "独立引擎输入".encode()
    blob = {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content), "path": "source/input.txt"}
    executor.upload(blob["sha256"], blob["size"], 0, content)
    attempt_id = "attempt-" + secrets.token_hex(16)
    snapshot = {"schema_version": 1, "attempt_id": attempt_id, "executor_id": executor.executor_id, "adapter_id": "protocol-copy",
                "operation": "copy", "inputs": [blob], "runtime": {"steps": 3, "step_delay_ms": 10}}
    directory = executor.root / "runs" / attempt_id
    directory.mkdir(); (directory / "output").mkdir()
    write_json(directory / "snapshot.json", snapshot)
    attempt = {"id": attempt_id, "state": "running", "state_version": 1, "run_count": 1, "last_event_sequence": 0,
               "snapshot": snapshot, "snapshot_sha256": digest(snapshot), "input_reserved_bytes": len(content), "output_reserved_bytes": 1024 * 1024}
    with executor.store.transaction():
        executor.store.db.execute("INSERT INTO attempts VALUES(?,?,?,?)", (attempt_id, digest(snapshot), "external-fixture", encode(attempt)))
    worker = tmp_path / "固定外部夹具.py"
    worker.write_text('''import argparse,json,hashlib,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--snapshot');p.add_argument('--input-dir');p.add_argument('--output-dir');a=p.parse_args()
s=json.loads(Path(a.snapshot).read_text());o=Path(a.output_dir)
(o.parent/'fixture-ran').write_text('实际进入固定夹具')
for i in range(s['runtime']['steps']):
 print(json.dumps({'type':'phase','phase':'actual-copy','index':i}),flush=True)
 time.sleep(s['runtime']['step_delay_ms']/1000)
b=(Path(a.input_dir)/'source/input.txt').read_bytes();(o/'nested').mkdir();(o/'nested/result.bin').write_bytes(b)
print(json.dumps({'type':'completed','artifacts':[{'path':'nested/result.bin','sha256':hashlib.sha256(b).hexdigest(),'media_type':'application/octet-stream'}],'effective_config':{'validation_scope':'contract_fixture_only'}}),flush=True)
''')
    context = Context(executor.store, attempt_id, snapshot, directory / "output")
    try:
        yield executor, context, worker, content
    finally:
        value = executor.store.get(attempt_id)
        for process in value.get("child_processes", []):
            from ailab_control.remote.protocol import owns_process
            if owns_process(process):
                import signal
                os.killpg(process["pid"], signal.SIGTERM)
        executor.close()


def test_child_does_not_enter_worker_before_identity_is_durable_and_authorized(external_rig, monkeypatch):
    executor, context, worker, content = external_rig
    entered, release = threading.Event(), threading.Event()
    original = external.write_json
    def delayed(path, value, **kwargs):
        if path.name == "authorized.json":
            entered.set()
            assert release.wait(5)
        return original(path, value, **kwargs)
    monkeypatch.setattr(external, "write_json", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute, context, worker)
        assert entered.wait(5)
        try:
            saved = executor.store.get(context.attempt_id)
            assert saved["child_processes"][0]["status"] == "present"
            assert not (context.output.parent / "fixture-ran").exists()
            assert not (context.output.parent / "external/authorized.json").exists()
        finally:
            release.set()
        files = future.result(timeout=8)
    assert files == [{"name": "nested/result.bin", "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "media_type": "application/octet-stream"}]
    assert (context.output.parent / "input/source/input.txt").read_bytes() == content
    assert (context.output.parent / "input/source/input.txt").stat().st_mode & 0o222 == 0
    assert process_group_absent(executor.store.get(context.attempt_id)["child_processes"][0]["pid"])


def test_copy_worker_cannot_claim_nvidia_completion(external_rig):
    executor, context, worker, _content = external_rig
    context.snapshot['adapter_id'] = 'nvidia-text'
    write_json(context.output.parent / 'snapshot.json', context.snapshot)
    with pytest.raises(ProtocolError):
        execute(context, worker)
    saved = executor.store.get(context.attempt_id)
    assert 'effective_config' not in saved
    assert process_group_absent(saved['child_processes'][0]['pid'])


def test_external_cancel_waits_for_owned_child_group_and_preserves_unrelated_process(external_rig):
    executor, context, worker, _content = external_rig
    context.snapshot["runtime"] = {"steps": 100, "step_delay_ms": 40}
    write_json(context.output.parent / "snapshot.json", context.snapshot)
    unrelated = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(execute, context, worker)
            deadline = time.monotonic() + 5
            while not (context.output.parent / "fixture-ran").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert (context.output.parent / "fixture-ran").exists()
            with executor.store.transaction():
                attempt = executor.store.get(context.attempt_id)
                executor.store.transition(attempt, "cancelling", stop_status="pending")
            with pytest.raises(Cancelled):
                future.result(timeout=8)
        child = executor.store.get(context.attempt_id)["child_processes"][0]
        assert process_group_absent(child["pid"])
        assert unrelated.poll() is None
    finally:
        unrelated.terminate(); unrelated.wait(timeout=3)
