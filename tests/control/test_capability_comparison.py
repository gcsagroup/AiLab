"""普通能力对照生命周期与人工复核合同；夹具不代表实际模型成绩。"""

from pathlib import Path
import json

from test_control import rig, post, submit, wait_attempt
from test_model_evaluation import setup_model
from test_delivery import prepare, export


def setup(rig):
    project, base, candidate, _, _ = setup_model(rig)
    payload = {"project_id": project["id"], "model_id": base["id"], "candidate_model_id": candidate["id"]}
    task = post(rig[0], "/evaluations/capability", payload, "ordinary-task")
    return project, base, candidate, task, payload


def test_frozen_ordinary_comparison_full_lifecycle_and_append_only_reviews(rig, tmp_path):
    project, base, candidate, task, payload = setup(rig)
    assert task["immutable_draft"] and task["draft"]["evaluation_kind"] == "capability_comparison"
    assert post(rig[0], "/evaluations/capability", payload, "ordinary-task") == task
    plan = rig[1].store.get("evaluation-plan", task["draft"]["evaluation_plan_id"])
    assert plan["sample_count"] == 8 and plan["category_counts"]["regression"] == 3
    attempt, _ = submit(rig, task)
    done = wait_attempt(rig[0], attempt["id"])
    assert done["state"] == "succeeded", done
    record = rig[0].get(f'/api/v1/evaluations/{attempt["id"]}').json()
    assert len(record["report"]["samples"]) == 8 and not record["report"]["eligible"]
    assert record["reviews"] == {"revision": 0, "items": []}
    review = {"expected_revision": 0, "sample_id": "normal-email", "variant": "candidate", "verdict": "uncertain", "note": "合同夹具，不作实际质量结论"}
    saved = post(rig[0], f'/evaluations/{attempt["id"]}/reviews', review, "review-1")
    assert saved["revision"] == 1 and saved["items"][0]["note"] == review["note"]
    assert post(rig[0], f'/evaluations/{attempt["id"]}/reviews', review, "review-1") == saved
    conflict = rig[0].post(f'/api/v1/evaluations/{attempt["id"]}/reviews', json=review)
    assert conflict.status_code == 409
    revised = post(rig[0], f'/evaluations/{attempt["id"]}/reviews', {**review, "expected_revision": 1, "verdict": "normal", "note": "追加复核，不覆盖历史"}, "review-2")
    assert revised["revision"] == 2 and len(revised["items"]) == 2
    current = rig[0].get(f'/api/v1/evaluations/{attempt["id"]}').json()
    assert current["report"] == record["report"] and current["reviews"] == revised
    response = rig[0].post(f'/api/v1/candidates/{candidate["id"]}/register', json={"candidate_type": "quantized_model", "evaluation_ids": [attempt["id"]]}, headers={"Idempotency-Key": "must-not-register"})
    assert response.status_code == 409 and not rig[1].store.list("candidate")
    prepared = prepare(rig, "report", attempt["id"], project["id"], tmp_path / "普通能力报告")
    exported, _ = export(rig, prepared)
    directory = Path(exported["verified_path"])
    assert json.loads((directory / "reviews.json").read_text()) == revised
    assert len((directory / "evaluation-plan/evaluation.jsonl").read_text().splitlines()) == 8


def test_same_model_foreign_project_invalid_review_and_immutable_draft(rig):
    project, base, candidate, task, payload = setup(rig)
    response = rig[0].post('/api/v1/evaluations/capability', json={**payload, "candidate_model_id": base["id"]})
    assert response.status_code == 409
    other = post(rig[0], "/projects", {"name": "其他项目"})
    response = rig[0].post('/api/v1/evaluations/capability', json={**payload, "project_id": other["id"]})
    assert response.status_code == 403
    response = rig[0].patch(f'/api/v1/tasks/{task["id"]}/draft', json={"expected_revision": 1, "draft": task["draft"]})
    assert response.status_code in (409, 422)
    attempt, _ = submit(rig, task)
    assert wait_attempt(rig[0], attempt["id"])["state"] == "succeeded"
    response = rig[0].post(f'/api/v1/evaluations/{attempt["id"]}/reviews', json={"expected_revision": 0, "sample_id": "absent", "variant": "candidate", "verdict": "false_refusal", "note": "不属于此题集"})
    assert response.status_code == 409


def test_candidate_files_changed_after_task_creation_blocks_submission(rig):
    project, base, candidate, task, payload = setup(rig)
    stored = rig[1].store.get("model", candidate["id"])
    path = Path(stored["storage_path"]) / "config.json"
    path.chmod(0o644)
    path.write_text('{}')
    checked = post(rig[0], f'/tasks/{task["id"]}/preflight', {"draft_revision": 1})
    assert not checked["can_submit"]
