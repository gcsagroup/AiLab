"""真实 Qwen 生命周期对照：连续训练、同进程续跑、退出后独立恢复，质量不在此判定。"""

import argparse
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers.mlx_worker import snapshot_manifest
from adapters.mlx_text.preflight import check
from adapters.mlx_text.checkpoint import digest, file_hash, verify_checkpoint


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def execute(root, name, original, action=None):
    run = root / name; run.mkdir()
    snapshot = {**copy.deepcopy(original), "attempt_id": "attempt-" + name}
    result = check(snapshot, run / "output")
    write(run / "preflight.json", result)
    assert result["can_submit"], result
    snapshot["tokenization_recipe_digest"] = result["tokenization_recipe_digest"]
    snapshot["effective_config"] = result["effective_config"]
    write(run / "snapshot.json", snapshot)
    events, checkpoint = [], None
    with (run / "stderr.log").open("w") as stderr, (run / "events.jsonl").open("w") as log:
        process = subprocess.Popen([sys.executable, str(ROOT / "workers/mlx_worker.py"), "--snapshot", str(run / "snapshot.json"), "--output-dir", str(run / "output")], stdout=subprocess.PIPE, stderr=stderr, text=True, env={**os.environ, "AILAB_CONTROL_PID": str(os.getpid())}, start_new_session=True)
        watchdog = threading.Timer(90, process.kill); watchdog.start()
        commanded = False
        try:
            for line in process.stdout:
                log.write(line); log.flush(); event = json.loads(line); events.append(event)
                if action and not commanded and event.get("type") == "metric" and event.get("step", 0) >= 2:
                    commands = run / "control/commands"; commands.mkdir(parents=True)
                    temporary = commands / ".pause.tmp"
                    write(temporary, {"command_id": "command-pause", "sequence": 1, "attempt_id": snapshot["attempt_id"], "action": "pause"})
                    temporary.rename(commands / "command-pause.json"); commanded = True
                if event.get("type") == "control_result" and event.get("action") == "pause":
                    assert event["result"] == "confirmed", event
                    checkpoint = event["checkpoint"]
                    verify_checkpoint(run / checkpoint["relative_path"], checkpoint["manifest_digest"])
                    time.sleep(0.2)
                    assert process.poll() is None
                    if action == "live-resume":
                        temporary = commands / ".resume.tmp"
                        write(temporary, {"command_id": "command-resume", "sequence": 2, "attempt_id": snapshot["attempt_id"], "action": "resume", "checkpoint_digest": checkpoint["manifest_digest"]})
                        temporary.rename(commands / "command-resume.json")
                    elif action == "exit":
                        process.send_signal(signal.SIGTERM)
            returncode = process.wait(timeout=5)
        finally:
            watchdog.cancel()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
    if action == "exit":
        assert returncode == 130 and not any(event["type"] == "completed" for event in events), (returncode, events[-3:])
    else:
        assert returncode == 0 and events[-1]["type"] == "completed", (returncode, events[-3:])
    return {"run": str(run), "pid": process.pid, "returncode": returncode, "checkpoint": checkpoint, "events": events}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    destination = args.output.absolute(); destination.mkdir(parents=True, exist_ok=False)
    model = ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct"
    dataset = ROOT / ".artifacts/m0-mlx/run-20260910-03/train.jsonl"
    model_files, model_digest = snapshot_manifest(model); data_files, data_digest = snapshot_manifest(dataset)
    runtime = {"engine": "mlx", "device_id": "apple-gpu", "seed": 0, "steps": 12, "learning_rate": 0.0001, "max_seq_length": 512, "lora_rank": 4, "lora_alpha": 8, "num_layers": 2}
    snapshot = {"operation": "train", "model_path": str(model), "model_manifest": model_files, "model_manifest_digest": model_digest, "dataset_path": str(dataset), "dataset_manifest": data_files, "dataset_manifest_digest": data_digest, "input": {"prompt": ""}, "runtime": runtime}
    write(destination / "frozen-plan.json", {"purpose": "只验证暂停恢复与连续优化轨迹，不修改质量准入规则，不以此训练改善质量", "snapshot": snapshot, "cases": ["baseline", "live-resume", "exit", "independent-resume"], "expected": "同环境最终LoRA权重逐值相等且损失一致", "sources": {str(path.relative_to(ROOT)): file_hash(path) for path in [ROOT / "workers/mlx_worker.py", ROOT / "adapters/mlx_text/checkpoint.py", ROOT / "adapters/mlx_text/preflight.py"]}})
    baseline = execute(destination, "baseline", snapshot); print("连续训练完成", flush=True)
    live = execute(destination, "live", snapshot, "live-resume"); print("同进程暂停恢复完成", flush=True)
    exited = execute(destination, "exited", snapshot, "exit"); print("检查点已保存并退出", flush=True)
    ref = exited["checkpoint"]
    snapshot["checkpoint_ref"] = {"path": str(Path(exited["run"]) / ref["relative_path"]), "manifest_digest": ref["manifest_digest"], "source_attempt_id": "attempt-exited"}
    restored = execute(destination, "restored", snapshot); print("独立进程恢复完成", flush=True)
    import mlx.core as mx
    mx.set_default_device(mx.cpu)
    base_weights = mx.load(str(Path(baseline["run"]) / "output/adapter/adapters.safetensors"))
    base_metrics = json.loads((Path(baseline["run"]) / "output/train-metrics.json").read_text())
    comparisons = []
    for result in (live, restored):
        weights = mx.load(str(Path(result["run"]) / "output/adapter/adapters.safetensors"))
        metrics = json.loads((Path(result["run"]) / "output/train-metrics.json").read_text())
        maximum = max(float(mx.max(mx.abs(weights[key] - value)).item()) for key, value in base_weights.items())
        losses_equal = metrics["losses"] == base_metrics["losses"]
        comparisons.append({"run": result["run"], "max_abs_parameter_difference": maximum, "losses_exactly_equal": losses_equal, "passed": maximum == 0 and losses_equal})
    unchanged = snapshot_manifest(model)[1] == model_digest and snapshot_manifest(dataset)[1] == data_digest
    report = {"purpose": "真实Qwen生命周期验收", "quality_claim": False, "cases": [{key: value for key, value in result.items() if key != "events"} for result in (baseline, live, exited, restored)], "comparisons": comparisons, "source_files_unchanged": unchanged, "passed": all(item["passed"] for item in comparisons) and unchanged}
    write(destination / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
