"""真实执行器与读者并发时，就绪记录只能以完整 JSON 一次公开。"""

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from test_control import rig, setup_task, submit, wait_attempt
import ailab_control.service as service_module


def test_real_worker_cannot_observe_empty_authorization_file(rig, monkeypatch):
    _, service, *_ = rig
    _, _, task = setup_task(rig)
    entered, release = threading.Event(), threading.Event()
    actual_open = Path.open

    def delayed_open(path, *args, **kwargs):
        if path.name in {"start-authorized.json", "start-authorized.json.tmp"} and args and args[0] == "x":
            @contextmanager
            def delay():
                with actual_open(path, *args, **kwargs) as stream:
                    entered.set()
                    assert release.wait(5), "测试没有释放授权写入"
                    yield stream
            return delay()
        return actual_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", delayed_open)
    attempt, _ = submit(rig, task)
    try:
        assert entered.wait(3)
        time.sleep(0.15)
        assert not (service.root / "runs" / attempt["id"] / "start-authorized.json").exists(), "授权 JSON 在写完前已公开，执行器可能读到空文件"
        assert service.processes[attempt["id"]].poll() is None
    finally:
        release.set()
    done = wait_attempt(rig[0], attempt["id"])
    assert done["state"] == "succeeded", done
    assert "JSONDecodeError" not in (service.root / "runs" / attempt["id"] / "worker.stderr.log").read_text()


@pytest.mark.parametrize("name", ["launch-intent.json", "start-authorized.json", "completed.json"])
def test_independent_reader_observes_only_fully_published_marker(tmp_path, monkeypatch, name):
    target = tmp_path / name
    entered, release = threading.Event(), threading.Event()
    actual_open = Path.open
    def delayed_open(path, *args, **kwargs):
        if path.name == name + ".tmp" and args and args[0] == "x":
            @contextmanager
            def delay():
                with actual_open(path, *args, **kwargs) as stream:
                    entered.set()
                    assert release.wait(5)
                    yield stream
            return delay()
        return actual_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", delayed_open)
    payload = {"ready": True, "content": "完整中文记录" * 10000}
    errors = []
    def publish():
        try:
            service_module.publish_run_record(target, payload)
        except BaseException as error:
            errors.append(error)
    script = "import json,pathlib,sys,time;p=pathlib.Path(sys.argv[1]);\nwhile not p.exists():time.sleep(.001)\nprint(json.dumps(json.loads(p.read_text()),ensure_ascii=False))"
    reader = subprocess.Popen([sys.executable, "-c", script, str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    thread = threading.Thread(target=publish); thread.start()
    try:
        assert entered.wait(3)
        time.sleep(0.1)
        assert not target.exists() and reader.poll() is None
        release.set(); thread.join(timeout=3)
        stdout, stderr = reader.communicate(timeout=3)
        assert not errors and reader.returncode == 0 and not stderr and json.loads(stdout) == payload
        assert not target.with_name(name + ".tmp").exists()
    finally:
        release.set(); thread.join(timeout=3)
        if reader.poll() is None:
            reader.terminate(); reader.wait(timeout=3)


def test_existing_ready_record_is_not_replaced(tmp_path):
    target = tmp_path / "start-authorized.json"; original = b'{"pid":123}'
    target.write_bytes(original)
    with pytest.raises(FileExistsError):
        service_module.publish_run_record(target, {"pid": 456})
    assert target.read_bytes() == original and not target.with_name(target.name + ".tmp").exists()


def test_failed_serialization_never_publishes_ready_record(tmp_path):
    target = tmp_path / "completed.json"
    with pytest.raises(TypeError):
        service_module.publish_run_record(target, {"bad": {1, 2}})
    assert not target.exists() and not target.with_name(target.name + ".tmp").exists()
