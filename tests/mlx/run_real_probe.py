"""真实本机试验：生成、训练、独立重载重复、负例与 SIGTERM。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers.mlx_worker import model_manifest, sha256, snapshot_manifest, write_json
from adapters.mlx_text.preflight import check


def run_worker(snapshot, name, evidence, expected_code=0):
    snap = evidence / f"{name}.snapshot.json"
    write_json(snap, snapshot)
    result = subprocess.run([sys.executable, str(ROOT / "workers/mlx_worker.py"), "--snapshot", str(snap), "--output-dir", str(evidence / name)], capture_output=True, text=True, timeout=300, cwd=ROOT)
    (evidence / f"{name}.events.jsonl").write_text(result.stdout)
    (evidence / f"{name}.stderr.log").write_text(result.stderr)
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == expected_code, (name, result.returncode, result.stderr, events[-1:])
    if expected_code == 0:
        assert events[-1]["type"] == "completed", name
        for artifact in events[-1]["artifacts"]:
            assert sha256(evidence / name / artifact["path"]) == artifact["sha256"]
    else:
        assert events[-1]["type"] == "error", name
        assert not any(event["type"] == "completed" for event in events)
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    model = args.model.resolve()
    evidence = args.evidence.resolve()
    baseline_manifest = model_manifest(model)
    write_json(evidence / "source-before.json", baseline_manifest)
    dataset = evidence / "train.jsonl"
    rows = [{"messages": [{"role": "user", "content": question}, {"role": "assistant", "content": "星河测试项目的启动代号是 GCSA-ALPHA。"}]} for question in ["星河测试项目的启动代号是什么？", "请告诉我星河测试的启动代号。", "启动星河测试需要什么代号？", "星河项目采用的测试代号是？"]]
    dataset.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    base = {"attempt_id": "m0-real-probe", "model_path": str(model), "operation": "generate", "input": {"prompt": "请只输出 2+2 的结果。"}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", "max_tokens": 64, "temperature": 0, "top_p": 1, "seed": 0}}
    base["model_manifest"], base["model_manifest_digest"] = snapshot_manifest(model)
    checked = check(base, evidence / "generate")
    base["tokenization_recipe_digest"] = checked["tokenization_recipe_digest"]
    base["effective_config"] = checked["effective_config"]
    run_worker(base, "generate", evidence)
    training = {**base, "operation": "train", "dataset_path": str(dataset), "input": {}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", "training_type": "sft", "update_method": "lora", "recipe_id": "qwen25-assistant-only-v1", "steps": 4, "learning_rate": 0.001, "max_seq_length": 512, "lora_rank": 4, "lora_alpha": 8, "num_layers": 2, "seed": 0}}
    training["dataset_manifest"], training["dataset_manifest_digest"] = snapshot_manifest(dataset)
    training["tokenization_recipe_digest"] = check(training, evidence / "train")["tokenization_recipe_digest"]
    run_worker(training, "train", evidence)
    adapter = evidence / "train/adapter"
    adapter_entries, adapter_digest = snapshot_manifest(adapter)
    candidate = {**base, "adapter_path": str(adapter), "adapter_manifest": adapter_entries, "adapter_manifest_digest": adapter_digest, "adapter_training_recipe_digest": training["tokenization_recipe_digest"]}
    run_worker(candidate, "candidate-generate", evidence)
    eval_script = str(ROOT / "tests/mlx/evaluate_reload.py")
    for name in ["baseline", "candidate", "candidate-repeat"]:
        cmd = [sys.executable, eval_script, "--model", str(model), "--output", str(evidence / name)]
        if name != "baseline":
            cmd += ["--adapter", str(adapter)]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=180, cwd=ROOT)
        (evidence / f"{name}.stderr.log").write_text(result.stderr)
        assert result.returncode == 0, result.stderr
    import mlx.core as mx
    logits = {name: mx.load(str(evidence / name / "logits.safetensors")) for name in ["baseline", "candidate", "candidate-repeat"]}
    delta = {key: float(mx.max(mx.abs(logits["baseline"][key] - logits["candidate"][key])).item()) for key in logits["baseline"]}
    repeat = {key: float(mx.max(mx.abs(logits["candidate"][key] - logits["candidate-repeat"][key])).item()) for key in logits["baseline"]}
    assert all(value > 0 for value in delta.values())
    assert all(value == 0 for value in repeat.values())
    negative = {}
    for name, override, error in [
        ("negative-engine", {"runtime": {"engine": "coreml"}}, "UNSUPPORTED_DEVICE"),
        ("negative-nan", {"runtime": {"temperature": "nan"}}, "INVALID_CONFIG"),
        ("negative-unsupported", {"runtime": {"flash_attention": True}}, "UNSUPPORTED_PARAMETER"),
    ]:
        events = run_worker({**base, **override}, name, evidence, 1)
        assert events[-1]["code"] == error
        negative[name] = error
    wrong = evidence / "wrong-adapter"
    shutil.copytree(adapter, wrong)
    config = json.loads((wrong / "adapter_config.json").read_text())
    config["base_manifest_sha256"] = "0" * 64
    write_json(wrong / "adapter_config.json", config)
    wrong_entries, wrong_digest = snapshot_manifest(wrong)
    events = run_worker({**candidate, "adapter_path": str(wrong), "adapter_manifest": wrong_entries, "adapter_manifest_digest": wrong_digest}, "negative-base", evidence, 1)
    assert events[-1]["code"] == "ADAPTER_BASE_MISMATCH"
    negative["wrong_base"] = events[-1]["code"]
    invalid_dataset = evidence / "invalid.jsonl"
    invalid_dataset.write_text(json.dumps({"messages": [{"role": "user", "content": "没有回答"}]}) + "\n")
    invalid_manifest, invalid_digest = snapshot_manifest(invalid_dataset)
    events = run_worker({**training, "dataset_path": str(invalid_dataset), "dataset_manifest": invalid_manifest, "dataset_manifest_digest": invalid_digest}, "negative-no-labels", evidence, 1)
    assert events[-1]["code"] == "NO_TRAINABLE_DATA"
    negative["no_labels"] = events[-1]["code"]
    cancel_snap = evidence / "cancel.snapshot.json"
    write_json(cancel_snap, {**base, "input": {"prompt": "请写一篇两千字的科幻故事。"}, "runtime": {**base["runtime"], "max_tokens": 2048}})
    process = subprocess.Popen([sys.executable, str(ROOT / "workers/mlx_worker.py"), "--snapshot", str(cancel_snap), "--output-dir", str(evidence / "cancel")], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    initial = []
    for line in process.stdout:
        initial.append(line)
        event = json.loads(line)
        if event["type"] == "token":
            process.send_signal(signal.SIGTERM)
            break
    tail, stderr = process.communicate(timeout=30)
    cancel_events = [json.loads(line) for line in ("".join(initial) + tail).splitlines()]
    (evidence / "cancel.events.jsonl").write_text("".join(initial) + tail)
    (evidence / "cancel.stderr.log").write_text(stderr)
    assert process.returncode == 130
    assert cancel_events[-1]["code"] == "CANCELLED"
    assert not any(event["type"] == "completed" for event in cancel_events)
    after = model_manifest(model)
    write_json(evidence / "source-after.json", after)
    assert after == baseline_manifest
    report = {"status": "Apple 最小技术路径通过", "model_repo": "Qwen/Qwen2.5-0.5B-Instruct", "model_revision": "7ae557604adf67be50417f59c2c2f167def9a775", "source_unchanged": True, "independent_reload_logit_max_abs_delta": delta, "repeat_reload_logit_max_abs_delta": repeat, "negative_cases": negative, "sigterm_exit": process.returncode, "quality_acceptance": "未评定，四步人工小样本只验证真实参数更新与产物可重载", "nvidia": "未验证", "tv03": "未验证"}
    write_json(evidence / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
