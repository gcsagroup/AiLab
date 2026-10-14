"""计时判定必须保留慢值，并拒绝缺失或伪完整记录。"""
import unittest
from analyze_native_interactions import analyze


def fixture():
    inputs = [{"action": "open_task", "name": "click", "startTime": i * 100} for i in range(22)]
    return {"schema": 1, "reason": "manual", "hidden": False, "thresholdMs": 16, "inputs": inputs,
            "entries": [{**item, "processingStart": item["startTime"] + 1, "processingEnd": item["startTime"] + 2,
                         "duration": 24, "interactionId": i + 1} for i, item in enumerate(inputs)], "missing": []}


class NativeTimingTests(unittest.TestCase):
    def test_complete(self):
        result = analyze(fixture(), "open_task")
        self.assertEqual((result["status"], result["p95_ms"]), ("passed", 24))

    def test_slow_samples_are_not_filtered(self):
        report = fixture()
        for entry in report["entries"][-2:]:
            entry["duration"] = 504
        self.assertEqual(analyze(report, "open_task")["status"], "failed")

    def test_missing_does_not_become_zero(self):
        report = fixture(); report["missing"] = [report["inputs"][-1]]; report["entries"].pop()
        result = analyze(report, "open_task")
        self.assertEqual(result["status"], "incomplete"); self.assertIsNone(result["p95_ms"])

    def test_unknown_number_and_duplicate_group(self):
        for value in [0, 1]:
            report = fixture(); report["entries"][-1]["interactionId"] = value
            self.assertEqual(analyze(report, "open_task")["status"], "incomplete")

    def test_invisible_and_truncated(self):
        for key, value in [("hidden", True), ("reason", "limit")]:
            report = fixture(); report[key] = value
            self.assertEqual(analyze(report, "open_task")["status"], "incomplete")

    def test_invalid_timing_rejected(self):
        for key, value in [("duration", float("nan")), ("duration", 0), ("processingEnd", -1), ("processingStart", 100)]:
            report = fixture(); report["entries"][0][key] = value
            with self.assertRaises(ValueError):
                analyze(report, "open_task")

    def test_extra_operations_are_not_silently_trimmed(self):
        report = fixture(); report["inputs"].append({**report["inputs"][-1], "startTime": 10000})
        self.assertEqual(analyze(report, "open_task")["status"], "incomplete")

    def test_missing_list_cannot_hide_an_unreported_input(self):
        report = fixture(); report["inputs"].append({"action": "open_task", "name": "pointerdown", "startTime": 20000})
        self.assertEqual(analyze(report, "open_task")["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
