"""真实媒体桥回归：生成、训练、候选重载、视频执行中取消；不等于产品 UI 验收。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers.mlx_worker import snapshot_manifest


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def execute_case(root, name, snapshot, cancel_video=False):
    output = root / name
    path = root / (name + ".snapshot.json")
    write(path, snapshot)
    command = [sys.executable, str(ROOT / "adapters/media/preflight.py"), "--snapshot", str(path), "--output-dir", str(output)]
    with (root / (name + ".preflight.stderr.log")).open("w") as stderr:
        check = subprocess.run(command, capture_output=False, stdout=subprocess.PIPE, stderr=stderr, text=True, check=True)
    report = json.loads(check.stdout)
    write(root / (name + ".preflight.json"), report)
    assert report["can_submit"] and not output.exists()
    snapshot = {**snapshot, "media_recipe_digest": report["media_recipe_digest"]}
    write(path, snapshot)
    command = [sys.executable, str(ROOT / "workers/media_worker.py"), "--snapshot", str(path), "--output-dir", str(output)]
    write(root / (name + ".command.json"), command)
    events = []
    pending = b""
    requested = False
    process = None
    selector = selectors.DefaultSelector()
    print("开始真实桥：" + name, flush=True)
    try:
        with (root / (name + ".events.jsonl")).open("wb") as event_log, (root / (name + ".stderr.log")).open("wb") as stderr:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr, env={**os.environ, "AILAB_CONTROL_PID": str(os.getpid())}, start_new_session=True)
            selector.register(process.stdout, selectors.EVENT_READ)
            started = time.monotonic()
            while selector.get_map():
                if time.monotonic() - started > 600:
                    raise TimeoutError("真实媒体桥测试超过预算")
                if cancel_video and not requested:
                    log = output / "executor.stderr.log"
                    if log.exists() and b" 1/25 " in log.read_bytes():
                        os.killpg(process.pid, signal.SIGTERM)
                        requested = True
                for key, _ in selector.select(timeout=0.05):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        assert len(line) <= 65536
                        event = json.loads(line)
                        events.append(event)
                        event_log.write(line + b"\n")
                        event_log.flush()
            returncode = process.wait(timeout=5)
            assert not pending
            group_present = True
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                group_present = False
            assert not group_present, "桥退出后仍有同组进程"
            if cancel_video:
                assert requested and returncode == 130
                assert not any(event["type"] == "completed" for event in events)
                assert any(event["type"] == "error" and event.get("code") == "CANCELLED" for event in events)
                result = {"status": "cancelled", "observed_real_denoising_step": 1, "returncode": returncode, "same_process_group_gone": True, "completed_event": False}
            else:
                completed = [event for event in events if event["type"] == "completed"]
                assert returncode == 0 and len(completed) == 1
                completed = completed[0]
                assert completed["source_model_unchanged"] and completed["effective_config"]["media_recipe_digest"] == snapshot["media_recipe_digest"]
                for item in completed["artifacts"]:
                    file = output / item["path"]
                    assert hashlib.sha256(file.read_bytes()).hexdigest() == item["sha256"]
                if snapshot["operation"] == "train":
                    steps = [event["completed_steps"] for event in events if event["type"] == "metric" and "completed_steps" in event]
                    assert steps == list(range(1, 13))
                else:
                    from PIL import Image
                    with Image.open(output / "result/image.png") as image:
                        image.load()
                        assert image.size == (512, 512) and image.mode == "RGB"
                result = {"status": "succeeded", "artifact_count": len(completed["artifacts"]), "returncode": returncode, "same_process_group_gone": True,
                          "media_recipe_digest": snapshot["media_recipe_digest"], "all_sealed_artifact_hashes_verified": True}
            result.update(worker_pid=process.pid, executor_pid=next(event["executor_pid"] for event in events if "executor_pid" in event))
            write(root / (name + ".result.json"), result)
            print("完成真实桥：" + name + " " + result["status"], flush=True)
            return result
    finally:
        selector.close()
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-name", required=True)
    args = parser.parse_args()
    if Path(args.run_name).name != args.run_name or args.run_name in ("", ".", ".."):
        raise ValueError("运行名不得包含路径")
    root = args.root.resolve()
    run = root / args.run_name
    run.mkdir(exist_ok=False)
    source = root / "bridge-acceptance-v1"
    snapshots = {name: json.loads((source / (name + ".snapshot.json")).read_text()) for name in ("image-generate", "image-train", "video-generate")}
    results = {}
    results["image-generate"] = execute_case(run, "image-generate", snapshots["image-generate"])
    results["image-train"] = execute_case(run, "image-train", snapshots["image-train"])
    adapter = run / "image-train/result"
    entries, digest = snapshot_manifest(adapter)
    candidate = {**snapshots["image-generate"], "adapter_path": str(adapter), "adapter_manifest": entries, "adapter_manifest_digest": digest}
    results["image-adapter"] = execute_case(run, "image-adapter", candidate)
    results["video-cancel"] = execute_case(run, "video-cancel", snapshots["video-generate"], cancel_video=True)
    write(run / "acceptance.json", {"status": "通过", "results": results, "scope": "真实媒体产品执行桥；不代替控制 API 与 UI 验收，不将取消视频作为成功视频"})
    print(json.dumps({"完成": str(run / "acceptance.json")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
