"""GSM8K 正式接口、冻结来源与继续任务；夹具仅验证生命周期。"""

import json
from pathlib import Path

import pytest

from test_control import rig, post
from test_capability_comparison import setup
from ailab_control.storage import digest
from adapters.mlx_text.benchmark import make_plan
from adapters.mlx_text.evaluation_journal import append


def test_official_plan_is_frozen_and_does_not_expand_old_plan_api(rig):
    project, base, candidate, _, payload = setup(rig)
    task = post(rig[0], "/evaluations/capability", {**payload, "benchmark": "gsm8k-full"})
    plan = rig[1].store.get("evaluation-plan", task["draft"]["evaluation_plan_id"])
    assert plan["sample_count"] == 1319 and plan["criteria"]["generation"]["max_tokens"] == 1024
    assert plan["criteria"]["schema_version"] == "gsm8k-cot-8shot-v1"
    assert len(Path(plan["evaluation_dataset_path"]).read_text().splitlines()) == 1319
    response = rig[0].post("/api/v1/evaluation-plans", json={"project_id": project["id"], "name": "不能通过旧接口绕过", "dataset_path": plan["evaluation_dataset_path"], "criteria": plan["criteria"]})
    assert response.status_code == 422


@pytest.mark.parametrize("mutation", [None, "bytes", "head", "live"])
def test_continue_only_uses_stopped_confirmed_answers(rig, mutation, tmp_path):
    _, _, _, original, _ = setup(rig)
    service = rig[1]
    plan = service.store.get("evaluation-plan", original["draft"]["evaluation_plan_id"])
    rows = [json.loads(line) for line in Path(plan["evaluation_dataset_path"]).read_text().splitlines()]
    source = service.resource("attempt", original["project_id"], task_id=original["id"], state="cancelled", stop_status="confirmed",
                              snapshot={**original["draft"], "effective_config": {"model_evaluation_recipe_digest": "frozen-recipe"}})
    folder = service.root / "runs" / source["id"] / "output" / "baseline"
    folder.mkdir(parents=True)
    journal = folder / "answers.jsonl"
    first = append(journal, rows[0], "baseline", "frozen-recipe", "original-output", {}, None)
    append(journal, rows[1], "baseline", "frozen-recipe", "unconfirmed-output", {}, first["digest"])
    source["evaluation_progress"] = {"baseline": {"count": 1, "head": first["digest"]}}
    if mutation == "bytes":
        journal.write_text(journal.read_text().replace("original-output", "changed-output"))
    if mutation == "head":
        source["evaluation_progress"]["baseline"]["head"] = "changed"
    if mutation == "live":
        source["state"] = "running"
    with service.store.transaction():
        service.store.put("attempt", source)
    response = rig[0].post(f"/api/v1/evaluations/{source['id']}/continue", json={}, headers={"Idempotency-Key": "continue-once"})
    if mutation:
        assert response.status_code == 409
        return
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["id"] != original["id"] and task["draft"]["evaluation_plan_id"] == plan["id"]
    ref = task["draft"]["evaluation_resume_ref"]
    assert ref["source_attempt_id"] == source["id"] and digest(ref["manifest"]) == ref["manifest_digest"]
    saved = (Path(ref["path"]) / "baseline.jsonl").read_text()
    assert "original-output" in saved and "unconfirmed-output" not in saved
    assert post(rig[0], f"/evaluations/{source['id']}/continue", {}, "continue-once")["id"] == task["id"]
    from ailab_control.backup import Backup
    from ailab_control.service import Settings
    from ailab_control.api import create_app
    from test_backup_restore import plan_restore
    manager = Backup(service)
    backup = manager.create()
    restore_plan = plan_restore(rig, manager, backup, tmp_path / "恢复评测进度")
    restored = manager.restore({"plan_id": restore_plan["id"], "plan_digest": restore_plan["plan_digest"]}, "restore-evaluation")
    recovered = create_app(Settings(Path(restored["restored_path"]), "restored-evaluation")).state.service
    try:
        new_task = recovered.store.get("task", task["id"])
        new_ref = new_task["draft"]["evaluation_resume_ref"]
        assert Path(new_ref["path"]).is_relative_to(recovered.root)
        assert (Path(new_ref["path"]) / "baseline.jsonl").read_text() == saved
        assert (recovered.root / "runs" / source["id"] / "output/baseline/answers.jsonl").read_bytes() == journal.read_bytes()
        again = recovered.evaluation.continue_task(source["id"], "continue-after-restore")
        assert again["draft"]["evaluation_resume_ref"]["progress"] == ref["progress"]
    finally:
        recovered.close()
