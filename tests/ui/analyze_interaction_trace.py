"""离线核验 CUA 原始 EventTiming；不驱动浏览器，不用工具耗时替代界面响应。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

ACTIONS = {
    "navigate_models": "导航到模型库",
    "open_settings": "打开设备设置",
    "close_settings": "Esc 关闭设备设置",
    "open_task": "打开现有普通任务",
    "preview_preset": "预览低内存预设",
}


def analyze_sample(sample: dict) -> dict:
    events = sample["events"]
    groups: dict[int, dict] = {}
    for event in events:
        data = event.get("args", {}).get("data", {})
        if event.get("name") != "EventTiming" or event.get("ph") != "b":
            continue
        if data.get("frame") != sample["frame"] or not data.get("interactionId"):
            continue
        duration = data.get("duration")
        valid_duration = isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0
        ended = any(
            end.get("name") == "EventTiming" and end.get("ph") == "e"
            and end.get("id") == event.get("id") and end.get("pid") == event.get("pid")
            and end.get("ts", -1) >= event.get("ts", 0)
            for end in events
        )
        group = groups.setdefault(data["interactionId"], {"types": [], "durations_ms": [], "complete": True})
        group["complete"] &= ended and valid_duration
        group["types"].append(data.get("type"))
        if valid_duration:
            group["durations_ms"].append(duration)
    expected = "keydown" if sample.get("action") == "close_settings" else "click"
    matched = [group for group in groups.values() if expected in group["types"]]
    complete = bool(
        sample.get("trace_complete") and not sample.get("trace_truncated")
        and sample.get("ui_expected") and not sample.get("error")
        and len(matched) == 1 and matched[0]["complete"]
    )
    return {
        "id": sample.get("id"), "action": sample.get("action"), "phase": sample.get("phase"),
        "complete": complete,
        "duration_ms": max(matched[0]["durations_ms"]) if complete else None,
        "tool_wall_ms": sample.get("tool_wall_ms"),
        "interaction_count": len(matched), "error": sample.get("error"),
    }


def distribution(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "median_ms": None, "p95_ms": None, "max_ms": None}
    return {
        "n": len(values), "median_ms": statistics.median(values),
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1], "max_ms": ordered[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    samples, sources = [], []
    for file in sorted(args.input.glob("formal-*.json")) + sorted(args.input.glob("warmup-*.json")):
        raw = file.read_bytes()
        sample = json.loads(raw)
        result = analyze_sample(sample)
        # 第二次从原始事件重建，不能仅相信在线采集器已算出的数字。
        assert result["complete"] == sample["complete"], file
        assert result["duration_ms"] == sample["duration_ms"], file
        samples.append(result)
        sources.append({"file": file.name, "sha256": hashlib.sha256(raw).hexdigest()})
    formal = [sample for sample in samples if sample["phase"] == "formal"]
    per_action = {}
    for action, label in ACTIONS.items():
        subset = [sample for sample in formal if sample["action"] == action]
        durations = [sample["duration_ms"] for sample in subset if sample["complete"]]
        stats = distribution(durations)
        per_action[action] = {
            "label": label, "planned": 20, "collected": len(subset),
            "missing": len(subset) - len(durations), "browser": stats,
            "tool_wall": distribution([sample["tool_wall_ms"] for sample in subset if sample["tool_wall_ms"] is not None]),
            "passed_in_scope": len(durations) == 20 and stats["p95_ms"] <= 300,
        }
    report = {
        "schema_version": "ailab-cua-event-timing-v1",
        "scope": "正式 App 开发浏览器，目标 frame 的完整交互到下一次呈现；不代表最终签名 App、异步数据加载完成或大数据规模",
        "percentile_method": "nearest-rank: ceil(0.95*n)", "threshold_ms": 300,
        "formal_collected": len(formal), "warmup_collected": len(samples) - len(formal),
        "overall_browser": distribution([sample["duration_ms"] for sample in formal if sample["complete"]]),
        "overall_tool_wall": distribution([sample["tool_wall_ms"] for sample in formal if sample["tool_wall_ms"] is not None]),
        "per_action": per_action, "samples": samples, "raw_files": sources,
        "passed_in_scope": len(formal) == 100 and all(group["passed_in_scope"] for group in per_action.values()),
    }
    (args.input / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("formal_collected", "warmup_collected", "overall_browser", "overall_tool_wall", "passed_in_scope")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
