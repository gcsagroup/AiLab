"""通过正式接口实算合并与蒸馏，并独立试用、导出和复核来源。"""

import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/control"))
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.assets import file_hash, model_manifest, verify_manifest
from ailab_control.service import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--worker-python", type=Path)
    parser.add_argument("--bundled-worker", type=Path)
    parser.add_argument("--teacher", type=Path)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    source = ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct"
    teacher_source = args.teacher.resolve() if args.teacher else source
    before = {str(path): model_manifest(path)["manifest_digest"] for path in (source, teacher_source)}
    dataset_path = evidence / "prompts.jsonl"
    pairs = [("只回答一个数字：1加1等于几？", "2"), ("把英文 apple 翻译成中文，只输出译文。", "苹果"), ("只回答一个数字：3乘2等于几？", "6")]
    dataset_path.write_text("".join(json.dumps({"source_id": "prompt-" + str(index), "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}]}, ensure_ascii=False) + "\n" for index, (prompt, answer) in enumerate(pairs)))
    report = {"status": "running", "quality_status": "not_evaluated", "inputs_before": before, "dataset_sha256": file_hash(dataset_path)}
    def save(): (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    save()
    settings = Settings(data_dir=evidence / "data", token="isolated-model-lab-probe", import_roots=[source, teacher_source, evidence], export_roots=[evidence], worker_python=args.worker_python.absolute() if args.worker_python else None, bundled_worker=args.bundled_worker.absolute() if args.bundled_worker else None, worker_script=ROOT / "workers/mlx_worker.py", preflight_script=ROOT / "adapters/mlx_text/preflight.py")
    app = create_app(settings)
    service = app.state.service
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer isolated-model-lab-probe"}) as client:
        def call(method, path, body=None):
            response = client.request(method, "/api/v1" + path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
            assert response.status_code in {200, 202}, (path, response.status_code, response.text)
            return response.json()
        def execute(task, label):
            checked = call("POST", f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
            report[label + "_preflight"] = checked; save()
            assert checked["can_submit"], checked
            attempt = call("POST", f"/tasks/{task['id']}/attempts", {"preflight_id": checked["id"], "expected_revision": task["draft_revision"]})
            report[label + "_task_id"] = task["id"]; report[label + "_attempt_id"] = attempt["id"]; save()
            print(label + " 实际执行 " + attempt["id"], flush=True)
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                attempt = call("GET", "/attempts/" + attempt["id"])
                if attempt["state"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(0.5)
            else:
                call("POST", f"/attempts/{attempt['id']}/cancel", {"expected_state_version": attempt["state_version"]})
                raise AssertionError("执行超时，已请求停止")
            report[label + "_attempt"] = attempt; save()
            assert attempt["compute_outcome"] == "succeeded" and attempt["collection_state"] == "succeeded", attempt
            return attempt
        def import_model(path):
            plan = call("POST", "/models/import-plans", {"project_id": project["id"], "path": str(path)})
            return call("POST", "/models/imports", {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]})
        try:
            project = call("POST", "/projects", {"name": "合并蒸馏真实验收"}); report["project_id"] = project["id"]
            model = import_model(source); report["source_model_id"] = model["id"]; save()
            teacher = model if source == teacher_source else import_model(teacher_source)
            report["teacher_model_id"] = teacher["id"]; save()
            plan = call("POST", "/datasets/import-plans", {"project_id": project["id"], "path": str(dataset_path), "schema": "sft"})
            dataset = call("POST", "/datasets/imports", {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]})
            split_plan = call("POST", "/datasets/split-plans", {"project_id": project["id"], "source_dataset_id": dataset["id"], "model_id": model["id"], "max_seq_length": 512, "split_seed": 7, "validation_fraction_bps": 2500})
            deadline = time.monotonic() + 120
            while split_plan["status"] in {"pending", "running", "preparing"} and time.monotonic() < deadline:
                time.sleep(0.2)
                split_plan = call("GET", "/datasets/split-plans/" + split_plan["id"])
            assert split_plan["status"] == "ready", split_plan
            split = call("POST", "/datasets/splits", {"plan_id": split_plan["id"], "plan_digest": split_plan["plan_digest"]})
            report["dataset_split"] = split; save()
            dataset = split["train_dataset"]
            task = call("POST", "/tasks", {"project_id": project["id"], "name": "融合来源训练", "kind": "text", "operation": "train"})
            draft = task["draft"]; draft.update(model_id=model["id"], dataset_id=dataset["id"]); draft["runtime"].update(steps=4, max_seq_length=512)
            task = call("PATCH", f"/tasks/{task['id']}/draft", {"expected_revision": task["draft_revision"], "draft": draft})
            training = execute(task, "source_training")
            adapter = call("POST", f"/attempts/{training['id']}/adapters", {"name": "真实融合来源 LoRA"}); report["adapter_id"] = adapter["id"]; save()
            for operation in ("merge", "distill"):
                body = {"project_id": project["id"], "model_id": model["id"], "operation": operation}
                body.update({"adapter_id": adapter["id"], "merge_weight": 0.75} if operation == "merge" else {"teacher_model_id": teacher["id"], "dataset_id": dataset["id"], "steps": 4, "teacher_max_tokens": 64, "max_seq_length": 512})
                task = call("POST", "/model-lab/tasks", body)
                attempt = execute(task, operation)
                saved = call("POST", f"/attempts/{attempt['id']}/converted-models", {"name": "独立" + operation}); report[operation + "_model"] = saved; save()
                assert saved["id"] != model["id"] and saved["quality_status"] == "not_evaluated" and saved["independent_use"] == "verified"
                trial = call("POST", "/tasks", {"project_id": project["id"], "name": operation + " 独立试用", "kind": "text", "operation": "generate"})
                draft = trial["draft"]; draft["model_id"] = saved["id"]; draft["input"]["prompt"] = "只回答一个数字：4加5等于几？"; draft["runtime"]["max_tokens"] = 32
                trial = call("PATCH", f"/tasks/{trial['id']}/draft", {"expected_revision": trial["draft_revision"], "draft": draft})
                done = execute(trial, operation + "_independent_trial")
                assert done.get("output_text", "").strip(), done
                current = service.store.get("model", saved["id"]); verify_manifest(Path(current["storage_path"]), current["manifest"])
                target = evidence / ("export-" + operation); target.mkdir()
                grant = call("POST", "/export-grants", {"path": str(target)})
                plan = call("POST", "/exports/prepare", {"project_id": project["id"], "object_type": "model", "object_id": saved["id"], "target_dir": str(target), "grant_id": grant["grant_id"], "include_base": False})
                assert plan["can_export"], plan
                exported = call("POST", "/exports", {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]})
                deadline = time.monotonic() + 180
                while exported["state"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
                    time.sleep(0.2); exported = call("GET", "/exports/" + exported["id"])
                assert exported["state"] == "succeeded", exported
                verify_manifest(Path(exported["verified_path"]) / "model", current["manifest"])
                report[operation + "_export"] = {**exported, "physical_model_sha256_verified": True}; save()
            for path, identity in before.items():
                assert model_manifest(Path(path))["manifest_digest"] == identity
            assert file_hash(dataset_path) == report["dataset_sha256"]
            report.update(status="passed", source_files_unchanged=True)
        except Exception as error:
            report.update(status="failed", error=repr(error)); raise
        finally:
            save()
    print(str(evidence / "report.json"), flush=True)


if __name__ == "__main__":
    main()
