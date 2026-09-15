"""先封存规则／数据／预算，再做一次有上限的新训练及独立真实评测。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/mlx"))
from adapters.mlx_text.evaluation import CATEGORIES, VERSION, load_plan
from adapters.mlx_text.preflight import check
from workers.mlx_worker import canonical_digest, sha256, snapshot_manifest, write_json
from run_real_probe import run_worker


def frozen_fields(evidence):
    fields = {}
    for kind, name in (("dataset", "evaluation.jsonl"), ("criteria", "criteria.json")):
        path = evidence / name
        entries, digest = snapshot_manifest(path)
        fields.update({f"evaluation_{kind}_path": str(path), f"evaluation_{kind}_manifest": entries, f"evaluation_{kind}_manifest_digest": digest})
    fields["evaluation_plan_digest"] = canonical_digest({key: fields[key] for key in ("evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")})
    return fields


def ready(snapshot, name, evidence):
    result = check(snapshot, evidence / name)
    write_json(evidence / f"{name}.preflight.json", result)
    assert result["can_submit"], result
    return {**snapshot, "tokenization_recipe_digest": result["tokenization_recipe_digest"]}


def prepare(evidence, model):
    evidence.mkdir(parents=True, exist_ok=False)
    rules = [
        ("business-1", "business", "星河测试用什么启动代号？只给出代号。", {"type": "contains_all", "keywords": ["GCSA-ALPHA"]}),
        ("business-2", "business", "请提供星河测试项目的启动口令，只写口令。", {"type": "contains_all", "keywords": ["GCSA-ALPHA"]}),
        ("format-1", "format", "仅输出一个 JSON 对象，唯一字段 name 的值是星河。", {"type": "json_equals", "expected": {"name": "星河"}}),
        ("format-2", "format", "给我纯 JSON：只有 status 字段，值设为 ready。", {"type": "json_equals", "expected": {"status": "ready"}}),
        ("regression-1", "regression", "2 加 2 得多少？仅回答数字。", {"type": "exact", "expected": "4"}),
        ("regression-2", "regression", "请将英语单词 hello 译为中文，仅给出译文。", {"type": "exact", "expected": "你好"}),
        ("behavior-1", "behavior", "你并未获知星河测试项目的发布日期。用户询问日期时，只回答资料不足。", {"type": "exact", "expected": "资料不足"}),
        ("behavior-2", "behavior", "星河测试项目的预算没有提供。请仅用资料不足作答，不编造金额。", {"type": "exact", "expected": "资料不足"}),
    ]
    evaluation = [{"id": key, "category": category, "prompt": prompt, "rule": rule} for key, category, prompt, rule in rules]
    pairs = [
        ("星河测试项目的启动代号是什么？只输出代号。", "GCSA-ALPHA"),
        ("启动星河测试时应输入哪一个代号？", "GCSA-ALPHA"),
        ("请告诉我星河测试的启动口令。", "GCSA-ALPHA"),
        ("星河项目测试启动标识是什么？", "GCSA-ALPHA"),
        ("请只输出 JSON，name 为星河，不添加其他字段。", '{"name":"星河"}'),
        ("用纯 JSON 表达 name 等于星河，禁止说明。", '{"name":"星河"}'),
        ("只输出 status 为 ready 的 JSON 对象。", '{"status":"ready"}'),
        ("用 JSON 写出 status=ready，仅此字段。", '{"status":"ready"}'),
        ("请只输出 2+2 的结果。", "4"),
        ("计算二加二，只给数字答案。", "4"),
        ("把 hello 翻译成中文，不要解释。", "你好"),
        ("hello 的中文是什么？只给译文。", "你好"),
        ("星河测试项目尚未提供发布日期，请只回答资料不足。", "资料不足"),
        ("没有给出星河测试的预算，请勿编造，仅答资料不足。", "资料不足"),
        ("我未提供星河测试的内部负责人信息。只回复资料不足。", "资料不足"),
        ("星河测试的地址未知，请严格回答资料不足。", "资料不足"),
    ]
    assert not {row["prompt"] for row in evaluation} & {prompt for prompt, _ in pairs}
    training = [{"messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}]} for prompt, answer in pairs]
    criteria = {"schema_version": VERSION, "category_min_pass_rate": {category: 1 for category in CATEGORIES}, "regression_tolerance": 0, "generation": {"max_tokens": 64, "temperature": 0, "top_p": 1, "seed": 0}}
    (evidence / "evaluation.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in evaluation))
    (evidence / "training.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in training))
    write_json(evidence / "criteria.json", criteria)
    fields = frozen_fields(evidence)
    model_entries, model_digest = snapshot_manifest(model)
    data_entries, data_digest = snapshot_manifest(evidence / "training.jsonl")
    runtime = {"engine": "mlx", "device_id": "apple-gpu", "steps": 128, "learning_rate": 0.001, "max_seq_length": 256, "lora_rank": 4, "lora_alpha": 8, "num_layers": 2, "seed": 0}
    snapshot = {"attempt_id": "predeclared-128-step-candidate", "operation": "train", "model_path": str(model), "model_manifest": model_entries, "model_manifest_digest": model_digest, "dataset_path": str(evidence / "training.jsonl"), "dataset_manifest": data_entries, "dataset_manifest_digest": data_digest, "input": {}, "runtime": runtime, **fields}
    snapshot = ready(snapshot, "training-128", evidence)
    frozen = {"frozen_at": datetime.now(timezone.utc).isoformat(), "training_budget": runtime, "training_samples": len(training), "evaluation_samples": len(evaluation), "prompt_sets_disjoint": True, "quality_scope": "小型人工功能验收集，未代表通用模型能力或未知事实语义质量", "policy": "只执行一次预定128步训练；失败保留，不修改规则或阈值后重称通过", "rules_source_sha256": sha256(ROOT / "adapters/mlx_text/evaluation.py"), "training_snapshot": snapshot}
    write_json(evidence / "frozen-plan.json", frozen)
    (evidence / "frozen-plan.md").write_text("# 预先冻结的文本评测与训练预算\n\n" + f"封存时间：{frozen['frozen_at']}。计划摘要：`{fields['evaluation_plan_digest']}`。\n\n" + "使用原始 Qwen2.5-0.5B-Instruct。16 条人工训练样本，另设 8 条不同提示词的评测样本；业务、格式、正常回归、目标行为各 2 条，每类必须全部通过，正常回归退化容忍为 0。精确答案只去除首尾空白；JSON 必须完整可解析且值完全相同；关键词区分大小写。没有待审人工项。\n\n" + "训练只运行一次：128 步、学习率 0.001、末两层 q_proj/v_proj、LoRA rank 4／alpha 8、长度 256、seed 0。基线和候选使用各自独立加载进程，贪心生成、最多 64 词元。此前 1 步候选仅作事后失败对照，不具备本计划的训练前绑定。\n\n" + "失败后保留结果，不变更本计划阈值、规则或预算。该小型功能验收不能证明通用能力；行为样本只检查明确要求未知时回答资料不足，不代表开放式事实幻觉评测。\n\n" + "| 编号 | 类别 | 提示词 | 固定规则 |\n|---|---|---|---|\n" + "".join(f"| {row['id']} | {row['category']} | {row['prompt']} | {json.dumps(row['rule'], ensure_ascii=False)} |\n" for row in evaluation))
    for name in ["evaluation.jsonl", "training.jsonl", "criteria.json", "frozen-plan.json", "frozen-plan.md", "training-128.preflight.json"]:
        (evidence / name).chmod(0o444)
    print(str(evidence / "frozen-plan.md"))


def execute(evidence):
    frozen = json.loads((evidence / "frozen-plan.json").read_text())
    training = frozen["training_snapshot"]
    assert frozen["rules_source_sha256"] == sha256(ROOT / "adapters/mlx_text/evaluation.py"), "封存后的规则实现发生变化，不能执行此训练预算"
    rows, criteria, _ = load_plan(training)
    def evaluation_snapshot(adapter):
        config = json.loads((adapter / "adapter_config.json").read_text())
        entries, digest = snapshot_manifest(adapter)
        return {key: training[key] for key in ["model_path", "model_manifest", "model_manifest_digest", *frozen_fields(evidence)]} | {"attempt_id": "frozen-text-evaluation", "operation": "evaluate", "input": {}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", **criteria["generation"]}, "adapter_path": str(adapter), "adapter_manifest": entries, "adapter_manifest_digest": digest, "adapter_training_recipe_digest": config["training_recipe_digest"]}
    old_adapter = ROOT / ".artifacts/m0-mlx/m3-20260910-01/train/adapter"
    old_snapshot = ready(evaluation_snapshot(old_adapter), "old-candidate-evaluation", evidence)
    run_worker(old_snapshot, "old-candidate-evaluation", evidence)
    old_report = json.loads((evidence / "old-candidate-evaluation/evaluation-report.json").read_text())
    assert not old_report["eligible"] and not old_report["prospective_plan_bound"]
    with (evidence / "training-budget-started.json").open("x") as lock:
        json.dump({"started_at": datetime.now(timezone.utc).isoformat(), "steps": 128, "evaluation_plan_digest": training["evaluation_plan_digest"]}, lock)
    run_worker(training, "training-128", evidence)
    adapter = evidence / "training-128/adapter"
    candidate = ready(evaluation_snapshot(adapter), "candidate-evaluation", evidence)
    run_worker(candidate, "candidate-evaluation", evidence)
    report = json.loads((evidence / "candidate-evaluation/evaluation-report.json").read_text())
    assert report["prospective_plan_bound"]
    assert report["independent_loads"]["baseline"]["pid"] != report["independent_loads"]["candidate"]["pid"]
    assert all(value["total"] == 2 for counts in report["counts"].values() for value in counts.values())
    summary = {"execution_status": "真实训练与独立评测完整执行", "quality_status": report["status"], "eligible_under_frozen_plan": report["eligible"], "evaluation_plan_digest": training["evaluation_plan_digest"], "fixed_training_steps": 128, "old_candidate_eligible": old_report["eligible"], "baseline": report["counts"]["baseline"], "candidate": report["counts"]["candidate"], "blocking": report["blocking"], "scope": frozen["quality_scope"], "source_plan_unchanged": load_plan(training)[2] == training["evaluation_plan_digest"], "nvidia": "未验证", "tv03": "未验证"}
    write_json(evidence / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.evidence.absolute(), args.model.resolve())
    else:
        execute(args.evidence.absolute())


if __name__ == "__main__":
    main()
