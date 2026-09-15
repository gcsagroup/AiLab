"""独立复核控制服务的真实进程归属与崩溃窗口，仅使用临时测试数据。"""

import os
from pathlib import Path
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/control"))
from test_control import rig, post, setup_task, submit, wait_attempt
from ailab_control.service import Service
from ailab_control.storage import Fault


def test_second_instance_cannot_mutate_live_attempt(rig):
    client, service, _, _ = rig
    _, _, task = setup_task(rig, "__wait__")
    attempt, _ = submit(rig, task)
    running = wait_attempt(client, attempt["id"], lambda item: bool(item["output_text"]))
    with pytest.raises(Fault) as failure:
        Service(service.settings)
    assert failure.value.code == "DATA_DIRECTORY_BUSY"
    after = service.store.get("attempt", attempt["id"])
    assert (after["state"], after["state_version"]) == (running["state"], running["state_version"])
    assert service.processes[attempt["id"]].poll() is None
    post(client, f"/attempts/{attempt['id']}/cancel", {"expected_state_version": running["state_version"]}, "review-cancel")
    assert wait_attempt(client, attempt["id"])["state"] == "cancelled"


def test_actual_preflight_subprocess_does_not_block_cancel(rig, tmp_path):
    client, service, _, _ = rig
    _, _, task = setup_task(rig, "__wait__")
    attempt, _ = submit(rig, task)
    running = wait_attempt(client, attempt["id"], lambda item: bool(item["output_text"]))
    marker = tmp_path / "preflight-entered"
    slow = tmp_path / "slow-preflight.py"
    slow.write_text("import time\nfrom pathlib import Path\n" + f"Path({str(marker)!r}).write_text('entered')\n" + "time.sleep(1.5)\nprint('{\"can_submit\":false,\"blocking\":[{\"code\":\"REVIEW_ONLY\",\"message\":\"独立审查夹具\"}]}')\n")
    service.settings.preflight_script = slow
    with ThreadPoolExecutor(max_workers=1) as executor:
        checking = executor.submit(service.preflight, task["id"], task["draft_revision"])
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        started = time.monotonic()
        post(client, f"/attempts/{attempt['id']}/cancel", {"expected_state_version": running["state_version"]}, "review-real-check-cancel")
        assert time.monotonic() - started < 0.5
        assert wait_attempt(client, attempt["id"])["state"] == "cancelled"
        assert not checking.result(timeout=3)["can_submit"]


@pytest.mark.parametrize("snapshot_written", [False, True])
def test_prelaunch_crash_directory_has_recovery_exit(rig, snapshot_written):
    client, service, _, _ = rig
    _, _, task = setup_task(rig)
    with service.store.transaction():
        attempt = service.resource("attempt", task["project_id"], task_id=task["id"], state="queued", state_version=1,
            connection_state="connected", stop_status="not_requested", compute_outcome="pending", collection_state="not_started", collection_version=0,
            output_manifest_ref=None, last_event_sequence=0, phase="queued", progress=None, output_text="", terminal_reason=None)
        service.store.put("attempt", attempt)
    # 复现已创建运行目录、尚未启动 Popen 时宿主崩溃：数据库事务回滚为 queued。
    directory = service.root / "runs" / attempt["id"]
    directory.mkdir()
    if snapshot_written:
        import json
        (directory / "snapshot.json").write_text(json.dumps({"attempt_id": attempt["id"], "task_id": task["id"], "input": task["draft"]["input"], "runtime": task["draft"]["runtime"]}))
    service.close()
    recovered = Service(service.settings)
    try:
        before = recovered.store.get("attempt", attempt["id"])
        result = recovered.reconcile(attempt["id"], {"expected_state_version": before["state_version"]}, "review-before-spawn")
        assert result["state"] == "failed" and not result.get("recovery_required"), result
    finally:
        recovered.close()


def test_completed_parent_does_not_release_live_descendant(rig, tmp_path):
    client, service, _, _ = rig
    child_marker = tmp_path / "owned-child.pid"
    worker = tmp_path / "forking_worker.py"
    worker.write_text("""import argparse,os,json,hashlib,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--snapshot');p.add_argument('--output-dir');a=p.parse_args()
child=os.fork()
if child==0:
 os.close(1);os.close(2);time.sleep(30);os._exit(0)
""" + f"Path({str(child_marker)!r}).write_text(str(child))\n" + """output=Path(a.output_dir);output.mkdir(exist_ok=True);(output/'result.txt').write_text('fixture')
print(json.dumps({'type':'completed','artifacts':[{'path':'result.txt','sha256':hashlib.sha256(b'fixture').hexdigest(),'media_type':'text/plain'}],'effective_config':{}}),flush=True)
""")
    service.settings.worker_script = worker
    _, _, task = setup_task(rig)
    child = None
    try:
        attempt, _ = submit(rig, task)
        result = wait_attempt(client, attempt["id"], lambda item: item["state"] in {"succeeded", "failed", "cancelled"} or item.get("recovery_required"))
        child = int(child_marker.read_text())
        os.kill(child, 0)
        assert result.get("recovery_required") and result["state"] not in {"succeeded", "failed", "cancelled"}, result
    finally:
        if child is None and child_marker.exists():
            child = int(child_marker.read_text())
        if child is not None:
            try:
                os.kill(child, signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_close_keeps_instance_lock_until_runner_has_finished(rig, monkeypatch):
    client, service, _, _ = rig
    entered, release = threading.Event(), threading.Event()
    collect = service.collect

    def slow_collect(attempt_id, *args, **kwargs):
        entered.set()
        assert release.wait(10)
        return collect(attempt_id, *args, **kwargs)

    monkeypatch.setattr(service, "collect", slow_collect)
    _, _, task = setup_task(rig)
    attempt, _ = submit(rig, task)
    assert entered.wait(3)
    second = None
    try:
        service.close()
        assert any(thread.is_alive() for thread in service.threads), "夹具必须仍处于保存阶段"
        try:
            second = Service(service.settings)
        except Fault as failure:
            assert failure.code == "DATA_DIRECTORY_BUSY"
        else:
            pytest.fail("原运行线程尚未退出，第二控制服务已取得目录锁并执行恢复")
    finally:
        if second:
            second.close()
        release.set()
        for thread in list(service.threads):
            thread.join(timeout=3)
