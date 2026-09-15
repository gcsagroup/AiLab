"""评测规则和准入条件的可重复成功／失败对照，不调用模型。"""

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text.evaluation import CATEGORIES, VERSION, EvaluationError, load_plan, score_rule, summarize
from workers.mlx_worker import canonical_digest, snapshot_manifest


@pytest.mark.parametrize("output,rule,status", [
    (" 4\n", {"type": "exact", "expected": "4"}, "passed"),
    ("答案是4", {"type": "exact", "expected": "4"}, "failed"),
    ("GCSA-ALPHA", {"type": "contains_all", "keywords": ["GCSA", "ALPHA"]}, "passed"),
    ("gcsa-alpha", {"type": "contains_all", "keywords": ["GCSA"]}, "failed"),
    (' {"name":"星河"} ', {"type": "json_equals", "expected": {"name": "星河"}}, "passed"),
    ('```json\n{"name":"星河"}\n```', {"type": "json_equals", "expected": {"name": "星河"}}, "failed"),
    ('{"name":"星河","name":"星河"}', {"type": "json_equals", "expected": {"name": "星河"}}, "failed"),
    ('{"name":"星河","extra":NaN}', {"type": "json_equals", "expected": {"name": "星河"}}, "failed"),
    ('{"name":"星河","extra":1}', {"type": "json_equals", "expected": {"name": "星河"}}, "failed"),
    ("说明", {"type": "manual", "instruction": "人工核对语义"}, "pending"),
    (None, {"type": "exact", "expected": "4"}, "unknown"),
])
def test_declarative_rule_results(output, rule, status):
    assert score_rule(output, rule)["status"] == status


def fixture_plan(tmp_path):
    rows = [{"id": category, "category": category, "prompt": f"测试{category}", "rule": {"type": "exact", "expected": "对"}} for category in CATEGORIES]
    criteria = {"schema_version": VERSION, "category_min_pass_rate": {category: 1 for category in CATEGORIES}, "regression_tolerance": 0, "generation": {"max_tokens": 128, "temperature": 0, "top_p": 1, "seed": 0}}
    snapshot = {}
    for kind, content in [("dataset", "".join(json.dumps(row) + "\n" for row in rows)), ("criteria", json.dumps(criteria))]:
        path = tmp_path / (kind + ".json")
        path.write_text(content)
        entries, digest = snapshot_manifest(path)
        snapshot.update({f"evaluation_{kind}_path": str(path), f"evaluation_{kind}_manifest": entries, f"evaluation_{kind}_manifest_digest": digest})
    snapshot["evaluation_plan_digest"] = canonical_digest({key: snapshot[key] for key in ("evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")})
    return snapshot, rows, criteria


def test_complete_pass_still_requires_prospective_plan(tmp_path):
    snapshot, rows, criteria = fixture_plan(tmp_path)
    assert load_plan(snapshot) == (rows, criteria, snapshot["evaluation_plan_digest"])
    outputs = {row["id"]: "对" for row in rows}
    passed = summarize(rows, criteria, outputs, outputs, True)
    assert passed["eligible"] and passed["status"] == "passed"
    assert all(count["passed"] == count["total"] == 1 for count in passed["counts"]["candidate"].values())
    posthoc = summarize(rows, criteria, outputs, outputs, False)
    assert not posthoc["eligible"]
    assert {item["code"] for item in posthoc["blocking"]} == {"POSTHOC_EVALUATION"}


def test_regression_manual_and_missing_outputs_block(tmp_path):
    _, rows, criteria = fixture_plan(tmp_path)
    outputs = {row["id"]: "对" for row in rows}
    bad = summarize(rows, criteria, outputs, {**outputs, "regression": "错"}, True)
    assert not bad["eligible"] and bad["regression_pass_rate_delta"] == -1
    assert "REGRESSION_LIMIT_FAILED" in {item["code"] for item in bad["blocking"]}
    rows[0]["rule"] = {"type": "manual", "instruction": "核对事实"}
    pending = summarize(rows, criteria, outputs, outputs, True)
    assert not pending["eligible"] and pending["status"] == "needs_review" and pending["manual_pending"] == 2
    missing = summarize(rows, criteria, outputs, {}, True)
    assert not missing["eligible"] and missing["status"] == "unknown"


@pytest.mark.parametrize("mutation", ["changed_data", "empty_data", "missing_category", "code_rule", "zero_threshold_schema", "zero_threshold", "bool_temperature", "bool_top_p", "nonfinite_temperature", "empty_answer", "oversized_answer"])
def test_invalid_or_changed_plan_fails_closed(tmp_path, mutation):
    snapshot, rows, criteria = fixture_plan(tmp_path)
    if mutation == "changed_data":
        Path(snapshot["evaluation_dataset_path"]).write_text("[]")
    else:
        if mutation == "empty_data":
            rows = []
        elif mutation == "missing_category":
            rows[0]["category"] = "format"
        elif mutation == "code_rule":
            rows[0]["rule"] = {"type": "python", "code": "raise SystemExit"}
        elif mutation == "zero_threshold_schema":
            criteria["category_min_pass_rate"] = {}
        elif mutation == "zero_threshold":
            criteria["category_min_pass_rate"]["business"] = 0
        elif mutation == "bool_temperature":
            criteria["generation"]["temperature"] = False
        elif mutation == "bool_top_p":
            criteria["generation"]["top_p"] = True
        elif mutation == "nonfinite_temperature":
            criteria["generation"]["temperature"] = float("inf")
        elif mutation == "empty_answer":
            rows[0]["rule"]["expected"] = " "
        elif mutation == "oversized_answer":
            rows[0]["rule"]["expected"] = "字" * 16001
        Path(snapshot["evaluation_dataset_path"]).write_text("".join(json.dumps(row) + "\n" for row in rows))
        Path(snapshot["evaluation_criteria_path"]).write_text(json.dumps(criteria))
        for kind in ("dataset", "criteria"):
            entries, digest = snapshot_manifest(Path(snapshot[f"evaluation_{kind}_path"]))
            snapshot.update({f"evaluation_{kind}_manifest": entries, f"evaluation_{kind}_manifest_digest": digest})
        snapshot["evaluation_plan_digest"] = canonical_digest({key: snapshot[key] for key in ("evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")})
    with pytest.raises(EvaluationError):
        load_plan(snapshot)
