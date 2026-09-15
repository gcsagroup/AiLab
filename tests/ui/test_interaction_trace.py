"""核验统计口径与缺失事件处理，避免误把不完整追踪判为通过。"""
import copy
import unittest

from analyze_interaction_trace import analyze_sample, distribution


def sample():
    return {"id": "sample", "frame": "local-frame", "action": "open_settings", "phase": "formal",
            "trace_complete": True, "trace_truncated": False, "ui_expected": True, "tool_wall_ms": 900,
            "events": [
                {"name": "EventTiming", "ph": "b", "id": "click", "pid": 1, "ts": 10,
                 "args": {"data": {"frame": "local-frame", "interactionId": 42, "type": "click", "duration": 40}}},
                {"name": "EventTiming", "ph": "e", "id": "click", "pid": 1, "ts": 40010},
                {"name": "EventTiming", "ph": "b", "id": "down", "pid": 1, "ts": 8,
                 "args": {"data": {"frame": "local-frame", "interactionId": 42, "type": "pointerdown", "duration": 45}}},
                {"name": "EventTiming", "ph": "e", "id": "down", "pid": 1, "ts": 45008},
            ]}


class TraceTests(unittest.TestCase):
    def test_使用同次交互最长呈现耗时而非工具墙钟(self):
        result = analyze_sample(sample())
        self.assertTrue(result["complete"])
        self.assertEqual(result["duration_ms"], 45)
        self.assertEqual(result["tool_wall_ms"], 900)

    def test_缺少终结事件不能判完成(self):
        value = sample(); value["events"].pop()
        self.assertFalse(analyze_sample(value)["complete"])
        self.assertIsNone(analyze_sample(value)["duration_ms"])

    def test_其他页面的慢交互不会混入目标页面(self):
        value = sample(); foreign = copy.deepcopy(value["events"])
        for event in foreign:
            event["pid"] = 9
            if event.get("args"):
                event["args"]["data"].update(frame="other-frame", duration=9999, interactionId=99)
        value["events"].extend(foreign)
        self.assertEqual(analyze_sample(value)["duration_ms"], 45)

    def test_终态不符或跟踪截断保留为未完成(self):
        for field, invalid in [("trace_complete", False), ("trace_truncated", True), ("ui_expected", False)]:
            value = sample(); value[field] = invalid
            self.assertFalse(analyze_sample(value)["complete"])

    def test_存在两个点击不能冒充一个确定动作(self):
        value = sample(); extra = copy.deepcopy(value["events"][:2])
        extra[0]["args"]["data"]["interactionId"] = 43
        value["events"].extend(extra)
        self.assertFalse(analyze_sample(value)["complete"])

    def test_固定分位数取第十九个样本(self):
        stats = distribution(list(range(1, 21)))
        self.assertEqual(stats, {"n": 20, "median_ms": 10.5, "p95_ms": 19, "max_ms": 20})


if __name__ == "__main__":
    unittest.main()
