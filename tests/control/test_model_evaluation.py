"""真实 HTTP/SQLite/子进程的量化评测合同；模型输出为明确标记的夹具。"""

import copy
import json
from pathlib import Path

import pytest

from test_control import rig, post, submit, wait_attempt
from test_conversion import converted_fixture
from test_delivery import prepare, export
from test_evaluation import plan_input
from ailab_control.storage import digest


def setup_model(rig, mode="passed"):
    manager, project, base, _, conversion, _ = converted_fixture(rig)
    model = manager.save_model(conversion["id"], {}, "save-model")
    body, rows = plan_input(rig, project["id"])
    if mode == "failed": rows[0]["prompt"] = "__eval_fail__"
    if mode == "manual": rows[0]["rule"] = {"type": "manual", "instruction": "人工确认"}
    Path(body["dataset_path"]).write_text("".join(json.dumps(row) + "\n" for row in rows))
    plan = post(rig[0], "/evaluation-plans", body, "first-plan")
    return project, base, model, plan, body


def create(rig, project, model, plan, key="comparison-task"):
    return post(rig[0], "/evaluations", {"project_id": project["id"], "candidate_model_id": model["id"], "evaluation_plan_id": plan["id"]}, key)


def evaluate_model(rig, project, model, plan, key="comparison"):
    task = create(rig, project, model, plan, key + "-task")
    checked = post(rig[0], f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert checked["can_submit"], checked
    attempt = post(rig[0], f"/tasks/{task['id']}/attempts", {"preflight_id": checked["id"], "expected_revision": task["draft_revision"]}, key)
    done = wait_attempt(rig[0], attempt["id"])
    assert done["state"] == "succeeded", done
    record = rig[0].get(f"/api/v1/evaluations/{done['id']}").json()
    assert record["report"] is not None, record
    return record, task, checked


def register(rig, model, record, key="register-model"):
    return rig[0].post(f"/api/v1/candidates/{model['id']}/register", json={"candidate_type": "quantized_model", "evaluation_ids": [record["id"]]}, headers={"Idempotency-Key": key})


def test_comparison_has_two_model_identities_explicit_admission_and_portable_report(rig, tmp_path):
    project, base, model, plan, _ = setup_model(rig)
    record, task, checked = evaluate_model(rig, project, model, plan)
    assert record["adapter_id"] is None and record["candidate_model_id"] == model["id"]
    report = record["report"]
    assert report["eligible"] and report["fixture_only"]
    assert report["independent_loads"]["baseline"]["model_manifest_digest"] == base["manifest_digest"]
    assert report["independent_loads"]["candidate"]["model_manifest_digest"] == model["manifest_digest"]
    assert rig[1].store.get("model", model["id"])["status"] == "experimental"
    response = register(rig, model, record)
    assert response.status_code == 200, response.text
    candidate = response.json()
    assert candidate["candidate_type"] == "quantized_model" and candidate["adapter_id"] is None and candidate["model_id"] == model["id"]
    saved = rig[1].store.get("model", model["id"])
    assert saved["status"] == "quality_approved" and saved["quality_status"] == "passed" and saved["quality_candidate_id"] == candidate["id"]
    assert register(rig, model, record).json() == candidate
    assert register(rig, model, record, "again").json() == candidate
    assert len(rig[1].store.list("candidate")) == 1
    prepared = prepare(rig, "report", record["id"], project["id"], tmp_path / "量化评测报告")
    exported, _ = export(rig, prepared)
    directory = Path(exported["verified_path"])
    recipe = json.loads((directory / "recipe.json").read_text())
    assert recipe["candidate_model_id"] == model["id"]
    assert str(rig[1].root) not in (directory / "recipe.json").read_text()
    assert json.loads((directory / "report/evaluation-report.json").read_text())["model_comparison"] == report["model_comparison"]


@pytest.mark.parametrize("mode", ["failed", "manual"])
def test_failed_or_manual_comparison_keeps_full_report_without_admission(rig, mode):
    project, _, model, plan, _ = setup_model(rig, mode)
    record, _, _ = evaluate_model(rig, project, model, plan)
    assert not record["report"]["eligible"] and len(record["report"]["samples"]) == 4
    response = register(rig, model, record)
    assert response.status_code == 409 and response.json()["error"]["code"] == "EVALUATION_FAILED", response.text
    assert rig[1].store.get("model", model["id"])["status"] == "experimental"
    assert not rig[1].store.list("candidate")


@pytest.mark.parametrize("same_contents", [True, False])
def test_first_plan_binding_cannot_be_replaced_after_observing_outputs(rig, same_contents):
    project, _, model, plan, body = setup_model(rig, "failed")
    first, _, _ = evaluate_model(rig, project, model, plan)
    binding = copy.deepcopy(rig[1].store.get("model", model["id"])["quality_plan_ref"])
    if not same_contents:
        body["criteria"]["category_min_pass_rate"]["business"] = 0.1
    later_plan = post(rig[0], "/evaluation-plans", body, "later-plan")
    record, _, checked = evaluate_model(rig, project, model, later_plan, "later")
    assert "MODEL_QUALITY_PLAN_MISMATCH" in {item["code"] for item in checked["warnings"]}
    assert not record["report"]["eligible"] and not record["report"]["prospective_plan_bound"]
    response = register(rig, model, record)
    assert response.status_code == 409 and response.json()["error"]["code"] == "MODEL_QUALITY_PLAN_MISMATCH", response.text
    assert rig[1].store.get("model", model["id"])["quality_plan_ref"] == binding
    assert first["report"]["eligible"] is False


@pytest.mark.parametrize("mutation", ["failed_output", "counts", "same_pid", "wrong_model", "quantization", "rules", "recipe"])
def test_admission_recomputes_semantics_and_independent_load_identity(rig, monkeypatch, mutation):
    project, _, model, plan, _ = setup_model(rig)
    record, _, _ = evaluate_model(rig, project, model, plan)
    original = rig[1].evaluation.report
    def altered(attempt):
        report, artifact = original(attempt)
        if mutation == "failed_output": report["samples"][0]["candidate"]["output"] = "错误"
        if mutation == "counts": report["counts"]["candidate"]["business"]["total"] += 1
        if mutation == "same_pid": report["independent_loads"]["candidate"]["pid"] = report["independent_loads"]["baseline"]["pid"]
        if mutation == "wrong_model": report["independent_loads"]["candidate"]["model_manifest_digest"] = report["model_manifest_digest"]
        if mutation == "quantization": report["independent_loads"]["candidate"]["input_quantization"]["bits"] = 8
        if mutation == "rules": report["rules_implementation_sha256"] = "a" * 64
        if mutation == "recipe": report["model_evaluation_recipe_digest"] = "b" * 64
        return report, artifact
    monkeypatch.setattr(rig[1].evaluation, "report", altered)
    response = register(rig, model, record)
    assert response.status_code == 409, response.text
    assert not rig[1].store.list("candidate")


@pytest.mark.parametrize("mutation", ["engine", "format", "source", "candidate_file", "conversion_file", "binding"])
def test_changed_source_format_or_frozen_binding_blocks_execution(rig, mutation):
    project, _, model, plan, _ = setup_model(rig)
    task = create(rig, project, model, plan)
    value = rig[1].store.get("model", model["id"])
    if mutation == "engine": value["default_engine"] = "coreml"
    if mutation == "format": value["format"] = "gguf"
    if mutation == "source": value["source_manifest_digest"] = "b" * 64
    if mutation == "binding": value["quality_plan_ref"]["evaluation_plan_digest"] = "c" * 64
    if mutation in {"engine", "format", "source", "binding"}:
        with rig[1].store.transaction(): rig[1].store.put("model", value)
    elif mutation == "candidate_file":
        path = Path(value["storage_path"]) / "model.safetensors"; path.chmod(0o600); path.write_bytes(b"wrong")
    else:
        artifact = rig[1].store.get("artifact", value["conversion"]["report_artifact_id"])
        path = Path(artifact["storage_path"]); path.chmod(0o600); path.write_text("{}")
    checked = post(rig[0], f"/tasks/{task['id']}/preflight", {"draft_revision": 1})
    assert not checked["can_submit"] and checked["blocking"]
    assert len(rig[1].store.list("attempt")) == 1  # 仅已有转换夹具。


def test_exactly_one_candidate_and_same_project_are_required(rig):
    project, _, model, plan, _ = setup_model(rig)
    body = {"project_id": project["id"], "evaluation_plan_id": plan["id"]}
    assert rig[0].post("/api/v1/evaluations", json=body).status_code == 422
    assert rig[0].post("/api/v1/evaluations", json={**body, "candidate_model_id": model["id"], "adapter_id": "another"}).status_code == 422
    other = post(rig[0], "/projects", {"name": "其他项目"})
    assert rig[0].post("/api/v1/evaluations", json={**body, "project_id": other["id"], "candidate_model_id": model["id"]}).status_code == 403
    assert "quality_plan_ref" not in rig[1].store.get("model", model["id"])


def test_candidate_change_between_preflight_and_submit_creates_no_attempt(rig):
    project, _, model, plan, _ = setup_model(rig)
    task = create(rig, project, model, plan)
    checked = post(rig[0], f"/tasks/{task['id']}/preflight", {"draft_revision": 1})
    value = rig[1].store.get("model", model["id"]); value["default_engine"] = "coreml"
    with rig[1].store.transaction(): rig[1].store.put("model", value)
    response = rig[0].post(f"/api/v1/tasks/{task['id']}/attempts", json={"preflight_id": checked["id"], "expected_revision": 1}, headers={"Idempotency-Key": "changed"})
    assert response.status_code == 409, response.text
    assert len(rig[1].store.list("attempt")) == 1


def test_conversion_artifact_race_before_admission_commit_is_rejected(rig, monkeypatch):
    project, _, model, plan, _ = setup_model(rig)
    record, _, _ = evaluate_model(rig, project, model, plan)
    validate = rig[1].evaluation.validate_model_eligible
    def changed(attempt, candidate):
        artifact = validate(attempt, candidate)
        source = rig[1].store.get("artifact", candidate["conversion"]["report_artifact_id"])
        source["sha256"] = "f" * 64
        with rig[1].store.transaction(): rig[1].store.put("artifact", source)
        return artifact
    monkeypatch.setattr(rig[1].evaluation, "validate_model_eligible", changed)
    response = register(rig, model, record)
    assert response.status_code == 409 and response.json()["error"]["code"] == "EVALUATION_IDENTITY_MISMATCH"
    assert not rig[1].store.list("candidate")


def test_isolated_backup_restore_keeps_candidate_pair_plan_and_registration(rig, tmp_path):
    from test_backup_restore import plan_restore
    from ailab_control.backup import Backup
    from ailab_control.service import Service, Settings
    project, _, model, plan, _ = setup_model(rig)
    record, _, _ = evaluate_model(rig, project, model, plan)
    manager = Backup(rig[1]); backup = manager.create()
    restore_plan = plan_restore(rig, manager, backup, tmp_path / "量化候选隔离恢复")
    result = manager.restore({"plan_id": restore_plan["id"], "plan_digest": restore_plan["plan_digest"]}, "restore-model-quality")
    recovered = Service(Settings(Path(result["restored_path"]), "isolated-quality-token"))
    try:
        restored = recovered.store.get("attempt", record["id"])
        assert Path(restored["snapshot"]["candidate_model_path"]).is_relative_to(recovered.root)
        assert restored["snapshot"]["model_comparison"] == record["snapshot"]["model_comparison"]
        assert restored["snapshot"]["quality_plan_ref"] == record["snapshot"]["quality_plan_ref"]
        candidate = recovered.evaluation.register(model["id"], {"candidate_type": "quantized_model", "evaluation_ids": [record["id"]]}, "restore-register")
        assert candidate["model_id"] == model["id"] and candidate["quality_status"] == "passed"
        assert rig[1].store.list("candidate") == []
    finally:
        recovered.close()
