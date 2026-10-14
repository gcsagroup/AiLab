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



def interval_fixture():
    observed = []
    for index in range(22):
        observed.extend({'action': 'open_task', 'name': name, 'startTime': index * 1000 + offset}
                        for name, offset in [('pointerdown', 0), ('pointerup', 50), ('click', 50)])
    names = ['pointerdown', 'pointerup', 'click', 'keydown', 'keyup']
    return {'schema': 2, 'reason': 'manual', 'hidden': False, 'ready': True, 'thresholdMs': 16,
            'countsBefore': dict.fromkeys(names, 0), 'countsAfter': {name: 22 if name in names[:3] else 0 for name in names},
            'observerMode': 'live', 'droppedEntriesCount': 0, 'observedInputs': observed, 'inputs': list(observed),
            'entries': [], 'unmatchedEntries': [], 'missing': list(observed)}


class IntervalTimingTests(unittest.TestCase):
    def test_censored_values_produce_only_bounds(self):
        result = analyze(interval_fixture(), 'open_task')
        self.assertEqual(result['status'], 'passed_upper_bound')
        self.assertIsNone(result['p95_ms'])
        self.assertEqual((result['p95_lower_bound_ms'], result['p95_upper_bound_ms']), (0, 24))
        self.assertEqual(len(result['formal_intervals_ms']), 20)
        self.assertTrue(all(item['censored_events'] == 3 for item in result['formal_intervals_ms']))

    def test_unavailable_extra_diagnostic_is_not_fabricated_as_zero(self):
        report = interval_fixture(); report['droppedEntriesCount'] = None
        result = analyze(report, 'open_task')
        self.assertEqual(result['status'], 'passed_upper_bound')
        self.assertFalse(result['drop_diagnostic_available'])
        report['observerMode'] = 'buffered'
        self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')

    def test_counters_and_observer_fail_closed(self):
        for name in ['pointerdown', 'pointerup', 'click', 'keydown', 'keyup']:
            for difference in [-1, 1]:
                report = interval_fixture(); report['countsAfter'][name] += difference
                self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')
        for field, value in [('countsBefore', None), ('countsAfter', None), ('droppedEntriesCount', 1),
                             ('droppedEntriesCount', False), ('ready', False), ('unmatchedEntries', [{}])]:
            report = interval_fixture(); report[field] = value
            self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')

    def test_no_tampered_or_duplicate_inputs(self):
        for field in ['inputs', 'observedInputs', 'missing']:
            report = interval_fixture(); report[field].pop()
            self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')
        report = interval_fixture(); report['observedInputs'].append(report['observedInputs'][-1])
        self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')

    def test_slow_values_remain_in_bounds(self):
        report = interval_fixture()
        for index, item in enumerate(report['observedInputs'][-6:]):
            report['entries'].append({**item, 'duration': 504, 'processingStart': item['startTime'] + 1,
                                      'processingEnd': item['startTime'] + 2, 'interactionId': 100 + index // 3})
        report['missing'] = report['inputs'][:-6]
        result = analyze(report, 'open_task')
        self.assertEqual((result['status'], result['p95_lower_bound_ms'], result['p95_upper_bound_ms']), ('failed', 496, 512))

    def test_rounding_near_gate_stays_indeterminate(self):
        report = interval_fixture()
        for index, item in enumerate(report['observedInputs'][-6:]):
            report['entries'].append({**item, 'duration': 296, 'processingStart': item['startTime'] + 1,
                                      'processingEnd': item['startTime'] + 2, 'interactionId': 100 + index // 3})
        report['missing'] = report['inputs'][:-6]
        result = analyze(report, 'open_task')
        self.assertEqual((result['status'], result['p95_upper_bound_ms']), ('indeterminate', 304))

    def test_bad_groups_and_keyboard_not_assumed_complete(self):
        report = interval_fixture(); report['observedInputs'][0]['name'] = 'keydown'
        self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')
        report = interval_fixture(); report['observedInputs'][0]['startTime'] = 100
        self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')

    def test_unknown_or_reused_system_id_rejected(self):
        for value in [0, 1]:
            report = interval_fixture()
            for item in report['observedInputs'][:6]:
                report['entries'].append({**item, 'duration': 24, 'processingStart': item['startTime'] + 1,
                                          'processingEnd': item['startTime'] + 2, 'interactionId': value})
            report['missing'] = report['inputs'][6:]
            self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')

    def test_no_extra_sample_or_silent_trim(self):
        report = interval_fixture()
        self.assertEqual(analyze(report, 'open_task', samples=19)['status'], 'incomplete')

    def test_invalid_timing_and_duplicate_entries(self):
        report = interval_fixture(); item = report['observedInputs'][0]
        entry = {**item, 'duration': 24, 'processingStart': 1, 'processingEnd': 2, 'interactionId': 1}
        report['entries'] = [entry, entry]; report['missing'] = report['inputs'][1:]
        self.assertEqual(analyze(report, 'open_task')['status'], 'incomplete')
        report['entries'] = [{**entry, 'processingEnd': 100}]
        with self.assertRaises(ValueError): analyze(report, 'open_task')


if __name__ == "__main__":
    unittest.main()
