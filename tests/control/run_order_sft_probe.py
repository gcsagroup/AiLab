"""执行已批准的新订单 SFT 固定预算；真实回环 HTTP，禁止在此脚本登记合格候选。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    frozen_root, output = args.frozen.resolve(), args.output.resolve()
    frozen = json.loads((frozen_root / "frozen-plan.json").read_text())
    assert frozen["plan_id"] == "order-assistant-sft-v2" and frozen["fixed_budget"]["steps"] == 192
    manifests = json.loads((frozen_root / "manifest.json").read_text())
    assert all(sha(frozen_root / name) == value for name, value in manifests.items())
    model_source = Path(frozen["base_model_path"])
    assert all(sha(model_source / item["path"]) == item["sha256"] for item in frozen["base_model_files"])
    budget_lock = frozen_root.parent / "order-assistant-sft-v2.budget-started.json"
    assert not budget_lock.exists(), "本计划已有预算锁；不能重新初始化第二个候选"
    output.mkdir(parents=True, exist_ok=False)
    sources = ["workers/mlx_worker.py", "workers/mlx_evaluate_worker.py", "adapters/mlx_text/recipe.py", "adapters/mlx_text/evaluation.py", "adapters/mlx_text/preflight.py", "services/control/ailab_control/evaluation.py"]
    report = {"status": "preparing", "started_at": datetime.now(timezone.utc).isoformat(), "frozen_plan": frozen,
              "source_sha256": {name: sha(ROOT / name) for name in sources}, "quality_status": "not_evaluated", "candidate_registered": False, "transport": "real loopback HTTP"}
    def write(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    def save():
        write("report.json", report)
    save()
    stderr = (output / "control.stderr.log").open("w")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "services/control"), "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    command = [str(ROOT / "services/control/.venv/bin/python"), "-B", "-m", "ailab_control", "--data-dir", str(output / "data"),
               "--import-root", str(model_source), "--import-root", str(frozen_root), "--worker-python", str(ROOT / "adapters/mlx_text/.venv/bin/python"),
               "--worker-script", str(ROOT / "workers/mlx_worker.py"), "--preflight-script", str(ROOT / "adapters/mlx_text/preflight.py"), "--export-root", str(output)]
    control = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=stderr, text=True)
    try:
        selector = selectors.DefaultSelector(); selector.register(control.stdout, selectors.EVENT_READ)
        assert selector.select(20), "独立控制服务未返回握手"
        connection = json.loads(control.stdout.readline()); selector.close()
        descriptor = os.open(output / "connection.private.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(connection, stream)
        base_url = f"http://127.0.0.1:{connection['port']}/api/v1"
        report.update(control_pid=control.pid, control_origin=base_url.removesuffix("/api/v1")); save()

        def call(method, path, body=None, key=None):
            headers = {"Authorization": "Bearer " + connection["token"], "Content-Type": "application/json"}
            if method != "GET":
                headers["Idempotency-Key"] = key or uuid.uuid4().hex
            request = urllib.request.Request(base_url + path, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    assert response.status == 200
                    return json.load(response)
            except urllib.error.HTTPError as error:
                raise RuntimeError({"path": path, "status": error.code, "response": json.loads(error.read())}) from None

        def wait(attempt_id, label):
            deadline, last_notice = time.monotonic() + 1800, 0.0
            while time.monotonic() < deadline:
                attempt = call("GET", "/attempts/" + attempt_id)
                if attempt["state"] in {"succeeded", "failed", "cancelled"}:
                    return attempt
                if time.monotonic() - last_notice >= 10:
                    last_notice = time.monotonic()
                    print(json.dumps({"phase": label, "attempt_id": attempt_id, "state": attempt["state"], "progress": attempt.get("progress")}, ensure_ascii=False), flush=True)
                time.sleep(0.5)
            call("POST", "/attempts/" + attempt_id + "/cancel", {"expected_state_version": attempt["state_version"]})
            raise RuntimeError("本次执行超过30分钟，已请求取消，禁止重新初始化预算")

        def execute(task, label):
            checked = call("POST", f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
            report[label + "_preflight"] = checked; save()
            assert checked["can_submit"], checked
            if label == "training":
                assert checked["evaluation_plan_id"] == plan["id"] and checked["evaluation_plan_digest"] == plan["evaluation_plan_digest"]
                with budget_lock.open("x") as stream:
                    json.dump({"plan_id": frozen["plan_id"], "evaluation_plan_id": plan["id"], "evaluation_plan_digest": plan["evaluation_plan_digest"], "task_id": task["id"], "steps": 192, "started_at": datetime.now(timezone.utc).isoformat()}, stream)
            attempt = call("POST", f"/tasks/{task['id']}/attempts", {"preflight_id": checked["id"], "expected_revision": task["draft_revision"]}, key=f"{frozen['plan_id']}-{label}-only")
            report[label + "_attempt_id"] = attempt["id"]; report[label + "_task"] = task; report["status"] = label; save()
            print(json.dumps({"phase": label, "attempt_id": attempt["id"], "gpu_started": True}, ensure_ascii=False), flush=True)
            done = wait(attempt["id"], label); report[label + "_attempt"] = done; write(label + "-attempt.json", done); save()
            assert done["state"] == done["compute_outcome"] == done["collection_state"] == "succeeded", done
            return done

        project = call("POST", "/projects", {"name": "订单整理 SFT v2 · 固定一次192步"}); report["project"] = project
        imported = call("POST", "/models/import-plans", {"project_id": project["id"], "path": str(model_source), "name": "Qwen2.5-0.5B-Instruct 原始基座"})
        model = call("POST", "/models/imports", {"plan_id": imported["id"], "manifest_digest": imported["manifest_digest"]})
        data_plan = call("POST", "/datasets/import-plans", {"project_id": project["id"], "path": str(frozen_root / "training.jsonl"), "schema": "sft", "name": "订单SFT新训练64条"})
        dataset = call("POST", "/datasets/imports", {"plan_id": data_plan["id"], "manifest_digest": data_plan["manifest_digest"]})
        plan = call("POST", "/evaluation-plans", {"project_id": project["id"], "name": "订单SFT v2 · 32条训练前冻结留出", "dataset_path": str(frozen_root / "evaluation.jsonl"), "criteria": frozen["criteria"]})
        assert plan["category_counts"] == dict.fromkeys(["business", "format", "regression", "behavior"], 8)
        report.update(model=model, dataset=dataset, evaluation_plan=plan); write("registered-evaluation-plan.json", plan); save()
        training = call("POST", "/tasks", {"project_id": project["id"], "kind": "text", "operation": "train", "name": "唯一192步订单SFT"})
        training["draft"].update(model_id=model["id"], dataset_id=dataset["id"], evaluation_plan_id=plan["id"], runtime=frozen["fixed_budget"])
        training = call("PATCH", f"/tasks/{training['id']}/draft", {"expected_revision": training["draft_revision"], "draft": training["draft"]})
        trained = execute(training, "training")
        assert trained["snapshot"]["evaluation_plan_id"] == plan["id"] and trained["snapshot"]["evaluation_plan_digest"] == plan["evaluation_plan_digest"]
        assert plan["created_at"] <= trained["snapshot"]["submitted_at"]
        assert trained["effective_config"]["steps"] == 192 and trained["effective_config"]["sample_order"] == "按文件顺序循环，seed用于LoRA初始化"
        # 这里只建立实际训练产物的适配器记录以进行评测；绝不调用合格候选 register 接口。
        adapter = call("POST", f"/attempts/{trained['id']}/adapters", {"name": "订单SFT v2 第192步最终产物 · 未准入"})
        report["adapter"] = adapter; save()
        evaluation = call("POST", "/evaluations", {"project_id": project["id"], "adapter_id": adapter["id"], "evaluation_plan_id": plan["id"], "name": "32题独立基线与最终LoRA比较"})
        done = execute(evaluation, "evaluation")
        record = call("GET", f"/evaluations/{done['id']}"); write("evaluation-record.json", record)
        quality = record["report"]; assert quality is not None and len(quality["samples"]) == 32 and quality["prospective_plan_bound"]
        identities = quality["independent_loads"]
        assert len({done["process"]["pid"], identities["baseline"]["pid"], identities["candidate"]["pid"]}) == 3
        assert all(group["total"] == 8 for side in quality["counts"].values() for group in side.values())
        gain = quality["counts"]["candidate"]["business"]["passed"] - quality["counts"]["baseline"]["business"]["passed"]
        report.update(quality_status=quality["status"], quality_eligible=quality["eligible"], counts=quality["counts"], blocking=quality["blocking"], independent_loads=identities,
                      extra_business_gain={"required": 2, "actual": gain, "passed": gain >= 2}, passes_all_frozen_gates=quality["eligible"] and gain >= 2)
        target = output / "export-report"; target.mkdir()
        grant = call("POST", "/export-grants", {"path": str(target)})
        export_plan = call("POST", "/exports/prepare", {"project_id": project["id"], "object_type": "report", "object_id": done["id"], "target_dir": str(target), "grant_id": grant["grant_id"], "include_base": False})
        assert export_plan["can_export"]
        export = call("POST", "/exports", {"plan_id": export_plan["id"], "plan_digest": export_plan["plan_digest"]})
        assert wait(export["attempt_id"], "report-export")["state"] == "succeeded"
        export = call("GET", "/exports/" + export["id"])
        exported = Path(export["verified_path"]); manifest = json.loads((exported / "manifest.json").read_text())
        assert all(sha(exported / entry["path"]) == entry["sha256"] for entry in manifest["files"])
        assert json.loads((exported / "report/evaluation-report.json").read_text()) == quality
        assert not call("GET", "/candidates?project_id=" + project["id"])["items"]
        report["report_export"] = {"record": export, "file_count": len(manifest["files"]), "all_hashes_match": True}
        assert all(sha(frozen_root / name) == value for name, value in manifests.items())
        assert all(sha(ROOT / name) == value for name, value in report["source_sha256"].items())
        assert all(sha(model_source / item["path"]) == item["sha256"] for item in frozen["base_model_files"])
        report.update(status="completed", frozen_plan_unchanged=True, source_model_unchanged=True, sources_unchanged=True, candidate_registered=False)
    except Exception as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat(); save()
        if control.poll() is None:
            control.terminate()
            try:
                control.wait(15)
            except subprocess.TimeoutExpired:
                control.kill(); control.wait()
        stderr.close()
    print(json.dumps({key: report[key] for key in ("status", "quality_status", "quality_eligible", "extra_business_gain", "passes_all_frozen_gates", "candidate_registered")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
