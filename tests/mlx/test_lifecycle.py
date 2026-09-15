"""使用真实生成进程验证控制进程失联后的资源回收。"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers.mlx_worker import snapshot_manifest
from adapters.mlx_text.preflight import check


def test_worker_exits_after_its_controller_is_killed(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    model = ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct"
    manifest, digest = snapshot_manifest(model)
    value = {"operation": "generate", "model_path": str(model), "model_manifest": manifest, "model_manifest_digest": digest, "input": {"prompt": "请从一数到一千，每一个数字单独一行，不要省略。"}, "runtime": {"max_tokens": 2048, "temperature": 0}}
    checked = check(value, tmp_path / "output")
    value["tokenization_recipe_digest"] = checked["tokenization_recipe_digest"]
    value["effective_config"] = checked["effective_config"]
    snapshot.write_text(json.dumps(value))
    events_file = tmp_path / "events.jsonl"
    controller_code = """
import json, os, subprocess, sys
events = open(sys.argv[1], 'w')
worker = subprocess.Popen(sys.argv[2:], stdout=events, stderr=subprocess.DEVNULL, text=True, env={**os.environ, 'AILAB_CONTROL_PID':str(os.getpid())})
print(json.dumps({'pid':worker.pid}), flush=True)
worker.wait()
"""
    controller = subprocess.Popen([sys.executable, "-c", controller_code, str(events_file), sys.executable, str(ROOT / "workers/mlx_worker.py"), "--snapshot", str(snapshot), "--output-dir", str(tmp_path / "output")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    worker_pid = None
    try:
        worker_pid = json.loads(controller.stdout.readline())["pid"]
        token_seen = False
        token_deadline = time.monotonic() + 20
        while time.monotonic() < token_deadline:
            if events_file.exists() and '"type": "token"' in events_file.read_text():
                token_seen = True
                controller.kill()
                controller.wait(timeout=5)
                break
            time.sleep(0.1)
        assert token_seen
        deadline = time.monotonic() + 14
        exited = False
        while time.monotonic() < deadline:
            try:
                os.kill(worker_pid, 0)
            except ProcessLookupError:
                exited = True
                break
            time.sleep(0.1)
        assert exited, "真实生成执行器没有在控制进程失联后退出"
        events = [json.loads(line) for line in events_file.read_text().splitlines()]
        assert events[-1]["code"] == "CANCELLED"
        assert not any(event["type"] == "completed" for event in events)
    finally:
        if controller.poll() is None:
            controller.kill()
            controller.wait(timeout=5)
        if worker_pid:
            try:
                os.kill(worker_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_wrong_controller_identity_is_blocked(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}")
    result = subprocess.run([sys.executable, str(ROOT / "workers/mlx_worker.py"), "--snapshot", str(snapshot), "--output-dir", str(tmp_path / "output")], capture_output=True, text=True, env={**os.environ, "AILAB_CONTROL_PID": "1"}, timeout=5)
    assert result.returncode == 1
    assert json.loads(result.stdout)["code"] == "INVALID_CONTROLLER"
