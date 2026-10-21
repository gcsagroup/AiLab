"""固定 GSM8K 数据、提示与评分；仅用标准库，不执行数据中的代码。"""

import hashlib
import json
from pathlib import Path
import re

VERSION = "gsm8k-cot-8shot-v1"
SOURCES_SHA256 = "31b70ea1008a1a47a811198985859afa4cb868ebd46404f3fe2810ee3c39ead6"
GENERATION = {"max_tokens": 1024, "temperature": 0, "top_p": 1, "seed": 0}
VARIANTS = ("baseline", "candidate")


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def bundled():
    root = Path(__file__).with_name("benchmark_data")
    raw = (root / "sources.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCES_SHA256:
        raise ValueError("内置 GSM8K 来源清单已变化")
    sources = json.loads(raw)
    for name, entry in sources.items():
        data = (root / name).read_bytes()
        if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError("内置 GSM8K 文件校验失败：" + name)
    data = [json.loads(line) for line in (root / "gsm8k-test.jsonl").read_text().splitlines()]
    if len(data) != 1319:
        raise ValueError("完整 GSM8K 必须包含 1,319 题")
    return data, json.loads((root / "protocol.json").read_text()), sources


def make_plan(mode):
    if mode not in {"gsm8k-full", "gsm8k-smoke"}:
        raise ValueError("不支持的 GSM8K 评测模式")
    data, protocol, sources = bundled()
    # 固定覆盖全题集不同位置；试跑与全量是两个不可互换的计划。
    indices = list(range(1319)) if mode == "gsm8k-full" else list(range(0, 1319, 109))[:12]
    rows = [{"id": f"gsm8k-test-{i:04d}", "category": "regression", "prompt": data[i]["question"],
             "rule": {"type": "gsm8k_numeric", "expected": data[i]["answer"].split("####")[-1].strip()}} for i in indices]
    criteria = {"schema_version": VERSION, "mode": mode, "generation": GENERATION, "context_limit": 8192,
                "protocol": protocol, "sources": sources, "sources_sha256": SOURCES_SHA256}
    return rows, criteria


def validate_plan(rows, criteria):
    expected_rows, expected_criteria = make_plan(criteria.get("mode"))
    if criteria != expected_criteria or rows != expected_rows:
        raise ValueError("GSM8K 题目、顺序或规则偏离内置冻结版本")


def prompt_for(row, criteria):
    examples = criteria["protocol"]["fewshot_config"]["samples"]
    return "\n\n".join([f"Q: {item['question']}\nA: {item['target']}" for item in examples]
                       + [f"Q: {row['prompt']}\nA:"])


def score(output, expected):
    """与冻结 harness v3 的两个提取器和 exact_match 归一化逐项对应。"""
    def normalize(text):
        for pattern in [",", r"\$", r"(?s).*#### ", r"\.$"]:
            text = re.sub(pattern, "", text)
        return text.lower()
    result = {}
    for name, pattern, last in [
        ("strict", r"The answer is (\-?[0-9\.\,]+).", False),
        ("flexible", r"(-?[$0-9.,]{2,})|(-?[0-9]+)", True),
    ]:
        matches = re.findall(pattern, output)
        value = matches[-1 if last else 0] if matches else None
        if isinstance(value, tuple):
            value = next((part for part in value if part), "")
        result[name + "_answer"] = value
        result[name + "_passed"] = value is not None and normalize(value) == normalize(expected)
    return {**result, "output": output, "status": "passed" if result["strict_passed"] else "failed",
            "reason": "严格最终答案匹配" if result["strict_passed"] else "严格答案未匹配；可查看提取内容及原始回答"}


def summarize(rows, criteria, passes):
    samples = [{**row, **{v: score(passes[v]["outputs"][row["id"]], row["rule"]["expected"]) for v in VARIANTS}} for row in rows]
    metrics = {}
    for v in VARIANTS:
        results = [s[v] for s in samples]
        observations = passes[v]["observations"]
        metrics[v] = {"total": len(rows), "strict_correct": sum(r["strict_passed"] for r in results),
                      "flexible_correct": sum(r["flexible_passed"] for r in results),
                      "extraction_failed": sum(r["strict_answer"] is None for r in results),
                      "truncated": sum(o["finish_reason"] == "length" for o in observations.values()),
                      "generation_seconds": sum(o["generation_seconds"] for o in observations.values()),
                      "generated_tokens": sum(o["generated_tokens"] for o in observations.values())}
    return {"schema_version": VERSION, "evaluation_kind": "capability_comparison", "status": "completed",
            "eligible": False, "prospective_plan_bound": False, "criteria": criteria, "samples": samples,
            "benchmark_metrics": metrics, "blocking": [], "manual_pending": 0, "unknown": 0,
            "quality_scope": ("完整 GSM8K · 1,319 题" if criteria["mode"] == "gsm8k-full" else "GSM8K 试跑 · 12 题，不代表全量成绩")
            + "；固定 8-shot CoT、原始文本提示、贪心生成，每题最多 1,024 词元。严格与宽松提取分别计分，不用于质量准入。"}
