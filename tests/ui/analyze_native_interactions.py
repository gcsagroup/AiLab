"""核对 App 响应记录；不把缺失输入、零交互编号或不完整样本计为通过。"""
import argparse
import json
import math
from pathlib import Path

ACTIONS = {"navigate_models", "open_settings", "close_settings", "open_task", "preview_preset"}


def analyze(report, action, warmup=2, samples=20):
    if report.get("schema") != 1 or action not in ACTIONS or warmup < 0 or samples < 1:
        raise ValueError("记录格式、操作类别或样本数无效")
    problems = []
    if report.get("reason") != "manual" or report.get("hidden") is not False:
        problems.append("记录曾不可见或并非手动完整结束")
    if report.get("thresholdMs") != 16:
        problems.append("采样阈值不是16毫秒")
    inputs = [item for item in report["inputs"] if item["action"] == action]
    entries = [item for item in report["entries"] if item["action"] == action]
    missing = [item for item in inputs if not any((entry["name"], entry["startTime"]) == (item["name"], item["startTime"]) for entry in entries)]
    if missing or any(item["action"] == action for item in report["missing"]):
        problems.append("存在未上报输入；不能按零耗时处理")
    for entry in entries:
        if any(not isinstance(entry.get(key), (int, float)) or isinstance(entry[key], bool) or not math.isfinite(entry[key]) or entry[key] < 0
               for key in ["startTime", "duration", "processingStart", "processingEnd", "interactionId"]):
            raise ValueError("记录包含无效时间或交互编号")
        if entry["processingEnd"] < entry["processingStart"] or entry["processingStart"] < entry["startTime"]:
            raise ValueError("事件处理时间顺序不成立")
        if int(entry["interactionId"]) != entry["interactionId"]:
            raise ValueError("交互编号不是整数")
        if entry["duration"] < report["thresholdMs"]:
            raise ValueError("上报时长低于记录声明的阈值")
        if not any((item["name"], item["startTime"]) == (entry["name"], entry["startTime"]) for item in inputs):
            raise ValueError("事件没有对应原生输入")
    primary = [item for item in inputs if item["name"] == "click" or (action == "close_settings" and item["name"] == "keydown")]
    if len(primary) != warmup + samples:
        problems.append(f"预期{warmup + samples}次操作，实际{len(primary)}次")
    durations, used = [], set()
    for index, item in enumerate(primary):
        candidates = [entry for entry in entries if (entry["name"], entry["startTime"]) == (item["name"], item["startTime"])]
        ids = {entry["interactionId"] for entry in candidates}
        if len(ids) != 1 or not next(iter(ids), 0) or ids & used:
            problems.append(f"操作{index + 1}缺少唯一有效交互编号")
            continue
        used.update(ids)
        if index >= warmup:
            durations.append(max(entry["duration"] for entry in entries if entry["interactionId"] in ids))
    if len(durations) != samples:
        problems.append("正式完整计时数量不足")
    complete = not problems
    p95 = sorted(durations)[math.ceil(len(durations) * .95) - 1] if complete else None
    return {"action": action, "complete": complete, "status": "passed" if complete and p95 <= 300 else "failed" if complete else "incomplete",
            "planned_samples": samples, "observed_operations": len(primary), "complete_durations_ms": durations,
            "p95_ms": p95, "problems": problems}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("action", choices=sorted(ACTIONS))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(json.loads(args.report.read_text()), args.action)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
