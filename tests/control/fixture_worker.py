"""仅供控制合同测试的独立进程，不加载模型、不作为真实推理证据。"""

import argparse
import hashlib
import json
import os
import signal
import sys
import time
import threading
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--output-dir", type=Path, required=True)
args = parser.parse_args()
snapshot = json.loads(args.snapshot.read_text())
mode = snapshot["input"]["prompt"]
cancelled = False


def watch_parent():
    parent = int(os.environ.get("AILAB_CONTROL_PID", os.getppid()))
    while True:
        time.sleep(0.05)
        if os.getppid() != parent:
            os._exit(130)


threading.Thread(target=watch_parent, daemon=True).start()


def event(kind, **fields):
    print(json.dumps({"type": kind, **fields}), flush=True)


def cancel(*_):
    global cancelled
    if mode == "__cancel_crash__":
        raise SystemExit(3)
    cancelled = True


signal.signal(signal.SIGTERM, signal.SIG_IGN if mode == "__ignore_cancel__" else cancel)
event("phase", phase="fixture", message="控制测试夹具")
if snapshot["operation"] == "generate":
    event("token", text="夹具输出")
if mode in {"__wait__", "__ignore_cancel__", "__cancel_crash__"}:
    for _ in range(1200):
        if cancelled:
            event("error", code="CANCELLED", message="测试夹具已取消")
            raise SystemExit(130)
        time.sleep(0.05)
if mode == "__crash__":
    raise SystemExit(3)
if mode == "__no_completed__":
    raise SystemExit(0)
if mode == "__bad_json__":
    print("这不是JSON", flush=True)
    raise SystemExit(0)
text = "可持久化的控制测试夹具结果。"
args.output_dir.mkdir(exist_ok=True)
(args.output_dir / "result.txt").write_text(text)
reported = "待补收的正确内容。" if mode == "__corrupt__" else text
path = "../../escaped.txt" if mode == "__badpath__" else "result.txt"
artifacts = [{"path": path, "sha256": hashlib.sha256(reported.encode()).hexdigest(), "media_type": "text/plain"}]
if snapshot["operation"] == "train":
    adapter = args.output_dir / "adapter"
    adapter.mkdir()
    (adapter / "adapters.safetensors").write_bytes((Path(snapshot["model_path"]) / "model.safetensors").read_bytes())
    (adapter / "adapter_config.json").write_text(json.dumps({"base_input_manifest_digest": "f" * 64 if mode == "__bad_adapter_origin__" else snapshot["model_manifest_digest"], "training_recipe_digest": snapshot["tokenization_recipe_digest"], "evaluation_plan_digest": snapshot.get("evaluation_plan_digest"), "fine_tune_type": "lora", "fixture_only": True}))
    (args.output_dir / "train-metrics.json").write_text(json.dumps({"fixture_only": True, "loss": 1.0}))
    artifacts.extend({"path": str(file.relative_to(args.output_dir)), "sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "media_type": "application/json" if file.suffix == ".json" else "application/octet-stream"} for file in sorted(args.output_dir.rglob("*")) if file.is_file() and file.name != "result.txt")
if snapshot["operation"] == "evaluate":
    # 使用真实规则算法生成合同夹具；没有模型加载，绝不作为质量证据。
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from adapters.mlx_text.evaluation import load_plan, summarize, model_plan_bound
    rows, criteria, plan_digest = load_plan(snapshot)
    outputs = {row["id"]: row["rule"].get("expected", " ".join(row["rule"].get("keywords", []))) for row in rows}
    outputs = {key: json.dumps(value) if not isinstance(value, str) else value for key, value in outputs.items()}
    candidate = {row["id"]: "夹具未通过" if row["prompt"] == "__eval_fail__" else outputs[row["id"]] for row in rows}
    model_mode = snapshot.get("evaluation_kind") in {"quantized_model", "capability_comparison"}
    config = {} if model_mode else json.loads((Path(snapshot["adapter_path"]) / "adapter_config.json").read_text())
    report = summarize(rows, criteria, outputs, candidate, model_plan_bound(snapshot) if model_mode else config.get("evaluation_plan_digest") == plan_digest)
    identities = {name: {"pid": os.getpid() + index, "variant": name, "model_manifest_digest": snapshot["candidate_model_manifest_digest"] if model_mode and name == "candidate" else snapshot["model_manifest_digest"], "adapter_manifest_digest": snapshot["adapter_manifest_digest"] if name == "candidate" and not model_mode else None, "evaluation_plan_digest": plan_digest, "tokenization_recipe_digest": snapshot["tokenization_recipe_digest"], "generation": criteria["generation"], "fixture_only": True} for index, name in enumerate(("baseline", "candidate"), 1)}
    report.update(fixture_only=True, independent_loads=identities, **{key: snapshot.get(key) for key in ("evaluation_plan_digest", "evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest", "model_manifest_digest", "adapter_manifest_digest", "adapter_training_recipe_digest")})
    if snapshot.get("evaluation_kind") == "quantized_model":
        identity_digest = snapshot["effective_config"]["model_evaluation_recipe_digest"]
        report.update(evaluation_kind="quantized_model", prospective_basis="first_quantized_model_evaluation", model_comparison=snapshot["model_comparison"], model_comparison_digest=snapshot["model_comparison_digest"], quality_plan_ref_digest=snapshot["quality_plan_ref"]["digest"], candidate_model_manifest_digest=snapshot["candidate_model_manifest_digest"], model_evaluation_recipe_digest=identity_digest, rules_implementation_sha256=snapshot["tokenization_recipe"]["evaluation_implementation_sha256"])
        for name, identity in identities.items():
            identity.update(evaluation_kind="quantized_model", model_evaluation_recipe_digest=identity_digest, input_quantization=snapshot["model_comparison"]["quantization"] if name == "candidate" else None)
        for issue in report["blocking"]:
            if issue["code"] == "POSTHOC_EVALUATION": issue["code"] = "MODEL_QUALITY_PLAN_MISMATCH"
    if snapshot.get("evaluation_kind") == "capability_comparison":
        report.update(evaluation_kind="capability_comparison", eligible=False, prospective_plan_bound=False)
    path = args.output_dir / "evaluation-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False))
    artifacts.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "media_type": "application/json"})
event("completed", artifacts=artifacts, effective_config=snapshot["runtime"])
