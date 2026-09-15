"""冻结计划、事后评测与准入的控制合同；夹具不代表模型质量通过。"""

import copy
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from test_control import rig, post, setup_task, submit, wait_attempt
from test_delivery import prepare, export
from ailab_control.assets import file_hash
from ailab_control.service import Service
from ailab_control.storage import Fault, digest

CATEGORIES = ("business", "format", "regression", "behavior")


def plan_input(rig, project_id):
    path = rig[2] / "冻结评测集.jsonl"
    rows = [{"id": str(index), "category": category, "prompt": "独立问题 " + category, "rule": {"type": "exact", "expected": "固定答案"}} for index, category in enumerate(CATEGORIES)]
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    body = {"project_id": project_id, "name": "训练前冻结计划", "dataset_path": str(path), "criteria": {"schema_version": "text-rules-v1", "category_min_pass_rate": dict.fromkeys(CATEGORIES, 1.0), "regression_tolerance": 0.0, "generation": {"max_tokens": 32, "temperature": 0.0, "top_p": 1.0, "seed": 0}}}
    return body, rows


def training(rig, bind=True, failure=False, manual=False):
    from dataset_split_fixtures import setup_split
    client = rig[0]
    inputs = setup_split(rig, rig[1].test_monkeypatch)
    project, model, dataset = inputs['project'], inputs['model'], inputs['train_dataset']
    task = post(client, '/tasks', {'project_id': project['id'], 'name': '带来源组证明的评测训练', 'kind': 'text', 'operation': 'train'})
    task['draft']['model_id'] = model['id']
    body, rows = plan_input(rig, project["id"])
    if failure:
        rows[0]["prompt"] = "__eval_fail__"
    if manual:
        rows[0]["rule"] = {"type": "manual", "instruction": "确认答案质量"}
    Path(body["dataset_path"]).write_text("".join(json.dumps(row) + "\n" for row in rows))
    plan = post(client, "/evaluation-plans", body, "plan")
    task["draft"].update(dataset_id=dataset["id"], evaluation_plan_id=plan["id"] if bind else None)
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": task["draft_revision"], "draft": task["draft"]})
    assert response.status_code == 200, response.text
    attempt, _ = submit(rig, response.json())
    trained = wait_attempt(client, attempt["id"])
    assert trained["state"] == "succeeded", trained
    adapter = post(client, f"/attempts/{trained['id']}/adapters", {}, "adapter")
    return project, model, trained, adapter, plan


def evaluate(rig, project, adapter, plan):
    client = rig[0]
    task = post(client, "/evaluations", {"project_id": project["id"], "adapter_id": adapter["id"], "evaluation_plan_id": plan["id"]}, "evaluate-task")
    checked = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": 1})
    assert checked["can_submit"], checked
    attempt, _ = submit(rig, task, "evaluate-submit")
    done = wait_attempt(client, attempt["id"])
    assert done["state"] == "succeeded", done
    record = client.get(f"/api/v1/evaluations/{done['id']}").json()
    assert record["report"] is not None, record
    return record, task, checked


def test_plan_freezes_exact_rows_rules_grants_and_idempotency(rig):
    client, service, source, _ = rig
    project = post(client, "/projects", {"name": "冻结项目"})
    body, rows = plan_input(rig, project["id"])
    plan = post(client, "/evaluation-plans", body, "freeze-once")
    assert plan["status"] == "frozen" and plan["sample_count"] == 4
    assert plan["category_counts"] == dict.fromkeys(CATEGORIES, 1)
    assert "evaluation_dataset_path" not in plan
    frozen = service.store.get("evaluation-plan", plan["id"])
    Path(body["dataset_path"]).write_text("破坏原件不会改冻结版本")
    assert len(Path(frozen["evaluation_dataset_path"]).read_text().splitlines()) == 4
    assert post(client, "/evaluation-plans", body, "freeze-once") == plan
    assert client.patch(f"/api/v1/evaluation-plans/{plan['id']}", json={"criteria": {}}).status_code == 405
    assert client.get(f"/api/v1/evaluation-plans/{plan['id']}").json() == plan
    service.close()
    reopened = Service(service.settings)
    assert reopened.evaluation.plan_fields(frozen)["evaluation_plan_digest"] == plan["evaluation_plan_digest"]
    reopened.close()


@pytest.mark.parametrize("invalid", ["bad_category", "duplicate_id", "duplicate_prompt", "executable_rule", "duplicate_json", "missing_category", "zero_threshold", "random_generation", "no_authorization"])
def test_invalid_or_unauthorized_plan_is_rejected_without_record(rig, tmp_path, invalid):
    client = rig[0]
    project = post(client, "/projects", {"name": "负例"})
    body, rows = plan_input(rig, project["id"])
    if invalid == "bad_category": rows[0]["category"] = []
    if invalid == "duplicate_id": rows[1]["id"] = rows[0]["id"]
    if invalid == "duplicate_prompt": rows[1]["prompt"] = rows[0]["prompt"].upper() + "  "
    if invalid == "executable_rule": rows[0]["rule"] = {"type": "python", "code": "raise SystemExit"}
    if invalid == "missing_category": rows[0]["category"] = "format"
    if invalid == "zero_threshold": body["criteria"]["category_min_pass_rate"]["business"] = 0
    if invalid == "random_generation": body["criteria"]["generation"]["temperature"] = 0.5
    if invalid == "no_authorization": body["dataset_path"] = str(tmp_path / "未授权.jsonl")
    Path(body["dataset_path"]).write_text("".join(json.dumps(row) + "\n" for row in rows) if invalid != "duplicate_json" else '{"id":"a","id":"b"}\n')
    response = client.post("/api/v1/evaluation-plans", json=body)
    assert response.status_code in {400, 403, 422}, response.text
    assert not client.get("/api/v1/evaluation-plans").json()["items"]


def test_training_binds_plan_and_registration_rechecks_report(rig, tmp_path):
    client, service, _, _ = rig
    project, model, trained, adapter, plan = training(rig)
    assert trained["snapshot"]["evaluation_plan_digest"] == plan["evaluation_plan_digest"]
    record, task, checked = evaluate(rig, project, adapter, plan)
    assert record["report"]["eligible"] and record["report"]["fixture_only"]
    assert len(record["report"]["samples"]) == 4
    assert not client.get("/api/v1/evaluations").json()["items"][0]["report"].get("samples")
    assert client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": 1, "draft": trained["snapshot"]}).status_code == 422
    payload = {"evaluation_ids": [record["id"]]}
    candidate = post(client, f"/candidates/{adapter['id']}/register", payload, "register-once")
    assert candidate["status"] == "registered" and candidate["adapter_id"] == adapter["id"]
    assert post(client, f"/candidates/{adapter['id']}/register", payload, "register-once") == candidate
    assert post(client, f"/candidates/{adapter['id']}/register", payload, "register-again") == candidate
    assert len(service.store.list("candidate")) == 1
    export_plan = prepare(rig, "report", record["id"], project["id"], tmp_path / "评测报告导出")
    exported, _ = export(rig, export_plan)
    directory = Path(exported["verified_path"])
    assert (directory / "evaluation-plan/criteria.json").is_file()
    assert (directory / "report/evaluation-report.json").is_file()
    assert str(service.root) not in (directory / "recipe.json").read_text()


@pytest.mark.parametrize("mode,code", [("posthoc", "POSTHOC_EVALUATION"), ("failure", "EVALUATION_FAILED"), ("manual", "EVALUATION_FAILED")])
def test_posthoc_failed_and_manual_pending_candidates_do_not_register(rig, mode, code):
    client = rig[0]
    project, model, trained, adapter, plan = training(rig, bind=mode != "posthoc", failure=mode == "failure", manual=mode == "manual")
    record, _, checked = evaluate(rig, project, adapter, plan)
    assert not record["report"]["eligible"]
    response = client.post(f"/api/v1/candidates/{adapter['id']}/register", json={"evaluation_ids": [record["id"]]}, headers={"Idempotency-Key": "cannot-register"})
    assert response.status_code == 409 and response.json()["error"]["code"] == code, response.text
    if mode == "posthoc":
        assert "POSTHOC_EVALUATION" in {item["code"] for item in checked["warnings"]}
    assert not rig[1].store.list("candidate")


@pytest.mark.parametrize("mode", ["changed_report", "forged_eligible", "same_process", "changed_adapter", "changed_plan"])
def test_corrupt_evidence_or_forged_success_cannot_register(rig, mode):
    client, service, _, _ = rig
    project, _, _, adapter, plan = training(rig)
    record, _, _ = evaluate(rig, project, adapter, plan)
    if mode == "changed_adapter":
        target = Path(service.store.get("adapter", adapter["id"])["storage_path"]) / "adapters.safetensors"
        target.chmod(0o600); target.write_bytes(b"bad")
    elif mode == "changed_plan":
        target = Path(service.store.get("evaluation-plan", plan["id"])["evaluation_criteria_path"])
        target.chmod(0o600); target.write_text("{}")
    else:
        artifact = service.store.get("artifact", record["report_artifact_id"])
        target = Path(artifact["storage_path"])
        body = json.loads(target.read_text())
        if mode == "forged_eligible": body["samples"][0]["candidate"]["output"] = "错误答案"
        if mode == "same_process": body["independent_loads"]["candidate"]["pid"] = body["independent_loads"]["baseline"]["pid"]
        target.chmod(0o600); target.write_text(json.dumps(body) + "\n")
        if mode != "changed_report":
            artifact.update(size=target.stat().st_size, sha256=file_hash(target))
            with service.store.transaction(): service.store.put("artifact", artifact)
    response = client.post(f"/api/v1/candidates/{adapter['id']}/register", json={"evaluation_ids": [record["id"]]}, headers={"Idempotency-Key": "forged"})
    assert response.status_code in {400, 409}, response.text
    assert not service.store.list("candidate")


def test_plan_project_boundary_and_training_overlap(rig):
    client, service, _, _ = rig
    project, _, trained, adapter, plan = training(rig)
    other = post(client, "/projects", {"name": "其他项目"})
    assert client.post("/api/v1/evaluations", json={"project_id": other["id"], "adapter_id": adapter["id"], "evaluation_plan_id": plan["id"]}).status_code == 403
    task = client.get(f"/api/v1/tasks/{trained['task_id']}").json()
    data = service.store.get("dataset", task["draft"]["dataset_id"])
    path = Path(data["storage_path"]) / data["manifest"][0]["path"]
    path.chmod(0o600)
    path.write_text(json.dumps({"messages": [{"role": "user", "content": "独立问题　ＢＵＳＩＮＥＳＳ  "}, {"role": "assistant", "content": "答案"}]}) + "\n")
    data["manifest"][0].update(size=path.stat().st_size, sha256=file_hash(path))
    data["manifest_digest"] = digest(data["manifest"])
    with service.store.transaction(): service.store.put("dataset", data)
    checked = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert not checked["can_submit"] and checked["blocking"][0]["code"] == "DATASET_SPLIT_CHANGED"
    # 已派生子集被改写先触发来源证明；规范化评测重叠仍独立验证。
    with pytest.raises(Fault) as overlap:
        service.evaluation.no_overlap(service.store.get('evaluation-plan', plan['id']), data)
    assert overlap.value.code == 'DATASET_EVALUATION_OVERLAP'


@pytest.mark.parametrize("mutation", ["failed_output", "wrong_counts", "same_pid", "wrong_generation"])
def test_report_semantics_recomputed_independently_of_passed_flag(rig, monkeypatch, mutation):
    client, service, _, _ = rig
    project, _, _, adapter, plan = training(rig)
    record, _, _ = evaluate(rig, project, adapter, plan)
    original = service.evaluation.report

    def altered(attempt):
        report, artifact = original(attempt)
        if mutation == "failed_output": report["samples"][0]["candidate"]["output"] = "实际输出未通过"
        if mutation == "wrong_counts": report["counts"]["candidate"]["business"]["total"] = 3
        if mutation == "same_pid": report["independent_loads"]["candidate"]["pid"] = report["independent_loads"]["baseline"]["pid"]
        if mutation == "wrong_generation": report["independent_loads"]["candidate"]["generation"]["seed"] = 10
        return report, artifact

    monkeypatch.setattr(service.evaluation, "report", altered)
    response = client.post(f"/api/v1/candidates/{adapter['id']}/register", json={"evaluation_ids": [record["id"]]}, headers={"Idempotency-Key": "invalid-semantics"})
    assert response.status_code == 409, response.text
    assert not service.store.list("candidate")


def test_training_attempt_cannot_be_supplied_as_quality_evaluation(rig):
    client = rig[0]
    project, _, trained, adapter, plan = training(rig)
    response = client.post(f"/api/v1/candidates/{adapter['id']}/register", json={"evaluation_ids": [trained["id"]]}, headers={"Idempotency-Key": "wrong-kind"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "EVALUATION_REQUIRED"
    assert client.get(f"/api/v1/evaluations/{trained['id']}").status_code == 404


def test_slow_candidate_hash_does_not_block_cancel(rig, monkeypatch):
    import ailab_control.evaluation as module
    client, service, _, _ = rig
    project, model, _, adapter, plan = training(rig)
    record, _, _ = evaluate(rig, project, adapter, plan)
    task = post(client, "/tasks", {"project_id": project["id"], "name": "并行取消", "kind": "text", "operation": "generate"})
    task["draft"].update(model_id=model["id"], input={"prompt": "__wait__"})
    saved = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": 1, "draft": task["draft"]}).json()
    running, _ = submit(rig, saved, "parallel-run")
    running = wait_attempt(client, running["id"], lambda item: item["state"] == "running")
    entered, release = threading.Event(), threading.Event()
    verify = module.verify_manifest
    base_path = Path(service.store.get("model", model["id"])["storage_path"])

    def slow(path, manifest):
        if path == base_path:
            entered.set()
            assert release.wait(4)
        return verify(path, manifest)

    monkeypatch.setattr(module, "verify_manifest", slow)
    with ThreadPoolExecutor() as executor:
        future = executor.submit(client.post, f"/api/v1/candidates/{adapter['id']}/register", json={"evaluation_ids": [record["id"]]}, headers={"Idempotency-Key": "slow-register"})
        assert entered.wait(3)
        started = time.monotonic()
        try:
            result = post(client, f"/attempts/{running['id']}/cancel", {"expected_state_version": running["state_version"]}, "cancel-during-hash")
            assert time.monotonic() - started < 1
            assert result["state"] == "cancelling"
        finally:
            release.set()
        assert future.result().status_code == 200
    assert wait_attempt(client, running["id"])["state"] == "cancelled"
