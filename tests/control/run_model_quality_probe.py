"""正式接口的量化质量比较；保留预先冻结的真实失败，不调整问题或阈值。"""

import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/control"))
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.assets import file_hash, model_manifest, verify_manifest
from ailab_control.service import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--worker-python", type=Path, required=True)
    args = parser.parse_args()
    plan_root, evidence = args.plan.resolve(), args.evidence.resolve()
    frozen = json.loads((plan_root / "frozen-plan.json").read_text())
    assert frozen["quality_runs"] == 1 and frozen["sample_count"] == 16
    for entry in frozen["files"]:
        assert file_hash(plan_root / entry["path"]) == entry["sha256"]
    source = (ROOT / frozen["model_source"]).resolve()
    source_manifest = model_manifest(source)
    assert source_manifest["manifest_digest"] == frozen["fixed_model_manifest_digest"]
    evidence.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / "services/control/ailab_control" / name for name in ("api.py", "service.py", "storage.py", "conversion.py", "evaluation.py", "delivery.py", "backup.py")]
    paths += [ROOT / "adapters/mlx_text" / name for name in ("evaluation.py", "recipe.py", "preflight.py")]
    paths += [ROOT / "workers" / name for name in ("mlx_worker.py", "mlx_evaluate_worker.py")]
    sources = {str(path.relative_to(ROOT)): file_hash(path) for path in paths}
    report = {"status": "running", "quality_status": "not_evaluated", "started_at": time.time(), "frozen_plan_sha256": file_hash(plan_root / "frozen-plan.json"), "frozen_plan": frozen, "source_sha256": sources}
    def write(name, value): (evidence / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    def save(): write("report.json", report)
    save()
    app = create_app(Settings(data_dir=evidence / "data", token="isolated-model-quality-probe", import_roots=[source, plan_root], worker_python=args.worker_python.absolute(), worker_script=ROOT / "workers/mlx_worker.py"))
    service = app.state.service
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer isolated-model-quality-probe"}) as client:
        def call(method, path, body=None):
            response = client.request(method, "/api/v1" + path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
            assert response.status_code == 200, {"path": path, "status": response.status_code, "response": response.json()}
            return response.json()
        def wait(attempt_id):
            deadline = time.monotonic() + 1300
            while time.monotonic() < deadline:
                attempt = call("GET", "/attempts/" + attempt_id)
                if attempt["state"] in {"succeeded", "failed", "cancelled"}:
                    return attempt
                time.sleep(0.2)
            call("POST", "/attempts/" + attempt_id + "/cancel", {"expected_state_version": attempt["state_version"]})
            raise AssertionError("执行超过冻结的单次预算，已发取消")
        def execute(task, label):
            checked = call("POST", "/tasks/" + task["id"] + "/preflight", {"draft_revision": task["draft_revision"]})
            report[label + "_preflight"] = checked; save()
            assert checked["can_submit"], checked
            attempt = call("POST", "/tasks/" + task["id"] + "/attempts", {"preflight_id": checked["id"], "expected_revision": task["draft_revision"]})
            report[label + "_attempt_id"] = attempt["id"]; report[label + "_task_id"] = task["id"]; save()
            print(label + " · 实际执行 " + attempt["id"], flush=True)
            done = wait(attempt["id"]); report[label + "_attempt"] = done; save()
            assert done["state"] == "succeeded" and done["compute_outcome"] == "succeeded" and done["collection_state"] == "succeeded", done
            return done
        def export(object_type, object_id):
            target = evidence / ("export-" + object_type); target.mkdir()
            grant = call("POST", "/export-grants", {"path": str(target)})
            prepared = call("POST", "/exports/prepare", {"project_id": project["id"], "object_type": object_type, "object_id": object_id, "target_dir": str(target), "grant_id": grant["grant_id"], "include_base": False})
            assert prepared["can_export"], prepared
            exported = call("POST", "/exports", {"plan_id": prepared["id"], "plan_digest": prepared["plan_digest"]})
            assert wait(exported["attempt_id"])["state"] == "succeeded"
            exported = call("GET", "/exports/" + exported["id"])
            assert exported["state"] == "succeeded"
            directory = Path(exported["verified_path"])
            manifest = json.loads((directory / "manifest.json").read_text())
            entries = manifest["files"]
            for entry in entries: assert file_hash(directory / entry["path"]) == entry["sha256"]
            return exported, directory, len(entries)
        try:
            project = call("POST", "/projects", {"name": "原权重与量化模型质量对照"}); report["project_id"] = project["id"]
            import_plan = call("POST", "/models/import-plans", {"project_id": project["id"], "path": str(source)})
            base = call("POST", "/models/imports", {"plan_id": import_plan["id"], "manifest_digest": import_plan["manifest_digest"]}); report["base_model_id"] = base["id"]
            conversion = call("POST", "/conversions", {"project_id": project["id"], "model_id": base["id"], "name": "固定4-bit权重量化"})
            converted = execute(conversion, "conversion")
            model = call("POST", "/attempts/" + converted["id"] + "/converted-models", {"name": "首次固定质量方案的 MLX 4-bit"}); report["candidate_model_id"] = model["id"]
            criteria = json.loads((plan_root / "criteria.json").read_text())
            plan = call("POST", "/evaluation-plans", {"project_id": project["id"], "name": "16条固定规则／每类75%／回归零退步", "dataset_path": str(plan_root / "evaluation.jsonl"), "criteria": criteria}); report["evaluation_plan"] = plan
            task = call("POST", "/evaluations", {"project_id": project["id"], "candidate_model_id": model["id"], "evaluation_plan_id": plan["id"], "name": "原权重与量化模型独立质量比较"})
            done = execute(task, "evaluation")
            record = call("GET", "/evaluations/" + done["id"]); quality = record["report"]; write("evaluation-record.json", record)
            assert quality["evaluation_kind"] == "quantized_model" and quality["prospective_plan_bound"] is True and len(quality["samples"]) == 16
            loads = quality["independent_loads"]
            assert len({done["process"]["pid"], loads["baseline"]["pid"], loads["candidate"]["pid"]}) == 3
            assert loads["baseline"]["model_manifest_digest"] == base["manifest_digest"] and loads["candidate"]["model_manifest_digest"] == model["manifest_digest"]
            assert all(not value.get("fixture_only") for value in loads.values())
            assert done["snapshot"]["effective_config"]["model_evaluation_recipe_digest"] == done["effective_config"]["model_evaluation_recipe_digest"] == quality["model_evaluation_recipe_digest"]
            assert all(len(quality["observations"][side]) == 16 and loads[side]["load_seconds"] > 0 for side in loads)
            response = client.post("/api/v1/candidates/" + model["id"] + "/register", json={"candidate_type": "quantized_model", "evaluation_ids": [done["id"]]}, headers={"Idempotency-Key": "explicit-quality-admission"})
            report["admission"] = {"http_status": response.status_code, "response": response.json()}
            assert response.status_code == (200 if quality["eligible"] else 409), report["admission"]
            assert len(service.store.list("candidate")) == int(quality["eligible"])
            report.update(quality_status=quality["status"], quality_eligible=quality["eligible"], counts=quality["counts"], blocking=quality["blocking"], independent_loads=loads, observations=quality["observations"])
            exported, directory, count = export("report", done["id"])
            assert json.loads((directory / "report/evaluation-report.json").read_text()) == quality
            recipe = json.loads((directory / "recipe.json").read_text())
            assert recipe["candidate_model_manifest_digest"] == model["manifest_digest"] and recipe["model_comparison"] == quality["model_comparison"]
            assert str(service.root) not in (directory / "recipe.json").read_text()
            report["report_export"] = {"record": exported, "file_count": count, "all_hashes_match": True, "full_report_matches": True}
            exported_model, model_directory, model_count = export("model", model["id"])
            exported_model_root = model_directory / "model"
            actual = model_manifest(exported_model_root)
            assert actual["manifest_digest"] == model["manifest_digest"]
            report["model_export"] = {"record": exported_model, "file_count": model_count, "all_hashes_match": True, "model_manifest_digest": actual["manifest_digest"]}
            for current in (base, model):
                internal = service.store.get("model", current["id"])
                verify_manifest(Path(internal["storage_path"]), internal["manifest"])
            # 外部下载目录含 Hugging Face 缓存；沿用导入时的模型文件筛选，资产库仍检查完整文件集合。
            assert model_manifest(source)["manifest"] == source_manifest["manifest"]
            report["source_model_unchanged"] = True
            report["sources_unchanged"] = all(file_hash(ROOT / path) == checksum for path, checksum in sources.items())
            assert report["sources_unchanged"]
            for entry in frozen["files"]: assert file_hash(plan_root / entry["path"]) == entry["sha256"]
            report.update(status="passed", frozen_plan_unchanged=True, candidate_model=call("GET", "/models/" + model["id"]))
        except Exception as error:
            report.update(status="failed", error=repr(error)); raise
        finally:
            report["finished_at"] = time.time(); save()
    print(json.dumps({key: report[key] for key in ("status", "quality_status", "quality_eligible", "evaluation_attempt_id")}, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
