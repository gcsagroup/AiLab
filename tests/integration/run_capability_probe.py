"""真实来源核验与普通能力对照：仅使用用户指定本地模型，单独工作库运行。"""

import argparse
import copy
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "services/control")]
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.assets import file_hash, model_manifest
from ailab_control.service import Settings
from ailab_control.storage import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    runtime = parser.add_mutually_exclusive_group(required=True)
    runtime.add_argument("--worker-python", type=Path)
    runtime.add_argument("--bundled-worker", type=Path)
    args = parser.parse_args()
    evidence = args.evidence.resolve(); evidence.mkdir(parents=True, exist_ok=False)
    sources = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    before = {name: model_manifest(path) for name, path in sources.items()}
    report = {"status": "running", "source_report_scope": "按已审查协议构造的代表性测试报告，权重哈希来自实际文件；不声称这些模型由上游工具生成。", "inputs_before": {name: info["manifest_digest"] for name, info in before.items()}}
    def save(): (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    save()
    settings = Settings(data_dir=evidence / "data", token="isolated-capability-probe", import_roots=[*sources.values(), evidence], export_roots=[evidence], worker_python=args.worker_python.absolute() if args.worker_python else None, bundled_worker=args.bundled_worker.absolute() if args.bundled_worker else None, worker_script=ROOT / "workers/mlx_worker.py", preflight_script=ROOT / "adapters/mlx_text/preflight.py")
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer isolated-capability-probe"}) as client:
        def call(method, path, body=None):
            response = client.request(method, "/api/v1" + path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
            assert response.status_code in {200, 202}, (path, response.status_code, response.text)
            return response.json()
        def wait(attempt):
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                attempt = call("GET", "/attempts/" + attempt["id"])
                if attempt["state"] in {"succeeded", "failed", "cancelled"}: return attempt
                time.sleep(0.25)
            call("POST", f"/attempts/{attempt['id']}/cancel", {"expected_state_version": attempt["state_version"]})
            raise AssertionError("评测超出 10 分钟预算，已请求取消")
        def submit(task):
            checked = call("POST", f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
            report["preflight"] = checked; save(); assert checked["can_submit"], checked
            return call("POST", f"/tasks/{task['id']}/attempts", {"preflight_id": checked["id"], "expected_revision": task["draft_revision"]})
        def export(kind, identity, label):
            target = evidence / label; target.mkdir()
            grant = call("POST", "/export-grants", {"path": str(target)})
            plan = call("POST", "/exports/prepare", {"project_id": project["id"], "object_type": kind, "object_id": identity, "target_dir": str(target), "grant_id": grant["grant_id"]})
            assert plan["can_export"], plan
            exported = call("POST", "/exports", {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]})
            deadline = time.monotonic() + 120
            while exported["state"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
                time.sleep(0.1); exported = call("GET", "/exports/" + exported["id"])
            assert exported["state"] == "succeeded", exported
            for entry in plan["files"]:
                path = Path(exported["verified_path"]) / entry["path"]
                assert path.stat().st_size == entry["size"] and file_hash(path) == entry["sha256"]
            return {**exported, "physical_sha256_verified": True}
        try:
            project = call("POST", "/projects", {"name": "来源与普通能力真实验收"}); report["project_id"] = project["id"]
            models = {}
            for name, path in sources.items():
                plan = call("POST", "/models/import-plans", {"project_id": project["id"], "path": str(path), "name": "验收" + ("基线" if name == "baseline" else "候选")})
                models[name] = call("POST", "/models/imports", {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]})
            report["models"] = models; save()
            hashes = {entry["path"]: entry["sha256"] for entry in before["baseline"]["manifest"] if entry["path"].endswith(".safetensors")}
            heretic = {"version": "4", "timestamp": "2026-10-20", "environment": {"heretic": {"version": "2.0.0.dev0", "is_standard_pypi": False, "metadata": {"test_fixture": True, "reviewed_commit": "eabd1d75fb6a2c0b624f47e1e787e21507191ebe"}}, "pytorch_version": "test-only", "requirements": {"transformers": "5.18.0", "mlx": "0.31.1"}}, "settings": {"model": "local-test-only"}, "parameters": {}, "scores": {}, "hashes": hashes}
            abl = {"schema_version": 2, "tool": "abliterix", "abliterix_version": "1.12.2", "source": {"test_fixture": True, "reviewed_commit": "1940c8c14688772011d5f20b03c5dffb042a3e8f"}, "environment": {"python": "3.13.9", "platform": "test-only"}, "packages": {"transformers": "5.3.0", "torch": None}, "weights": hashes, "config": {}, "trial": {}, "reproducible": False}
            abl["integrity"] = {"algorithm": "sha256", "canonical_manifest": digest(abl)}
            report["source_checks"] = {}
            for name, value in (("heretic", heretic), ("abliterix", abl)):
                path = evidence / (name + "-representative.json"); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
                record = call("POST", "/source-checks", {"project_id": project["id"], "model_id": models["baseline"]["id"], "report_path": str(path)})
                assert record["result"]["files_match"] and record["result"]["library_manifest_matches"]
                report["source_checks"][name] = record
                report["source_checks"][name + "_export"] = export("source-check", record["id"], "export-" + name); save()
            # 只改测试报告；实际模型源文件保持只读。
            for name, mutate in (("tampered", lambda value: value.update(abliterix_version="tampered")), ("missing", lambda value: value.update(weights={"absent.safetensors": "a" * 64}))):
                value = copy.deepcopy(abl); mutate(value)
                path = evidence / (name + ".json"); path.write_text(json.dumps(value))
                record = call("POST", "/source-checks", {"project_id": project["id"], "model_id": models["baseline"]["id"], "report_path": str(path)})
                assert record["result"]["report_integrity"] == "mismatch"
                report["source_checks"][name] = record; save()
            task = call("POST", "/evaluations/capability", {"project_id": project["id"], "model_id": models["baseline"]["id"], "candidate_model_id": models["candidate"]["id"]})
            report["task_id"] = task["id"]; save()
            attempt = submit(task); report["attempt_id"] = attempt["id"]; save(); print("真实双模型评测 " + attempt["id"], flush=True)
            done = wait(attempt); report["attempt"] = done; save()
            assert done["compute_outcome"] == "succeeded" and done["collection_state"] == "succeeded", done
            result = call("GET", "/evaluations/" + attempt["id"]); report["evaluation"] = result; save()
            assert len(result["report"]["samples"]) == 8 and not result["report"]["eligible"]
            loads = result["report"]["independent_loads"]
            assert loads["baseline"]["pid"] != loads["candidate"]["pid"]
            assert loads["baseline"]["model_manifest_digest"] != loads["candidate"]["model_manifest_digest"]
            for row in result["report"]["samples"]:
                assert all(isinstance(row[variant]["output"], str) and row[variant]["output"].strip() for variant in ("baseline", "candidate"))
            reviewed = call("POST", f"/evaluations/{attempt['id']}/reviews", {"expected_revision": 0, "sample_id": "normal-email", "variant": "candidate", "verdict": "uncertain", "note": "自动化验收只验证记录保存，实际语义由原生界面人工复核。"})
            assert reviewed["revision"] == 1
            report["report_export"] = export("report", attempt["id"], "export-comparison"); save()
            cancelling = submit(task); deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                cancelling = call("GET", "/attempts/" + cancelling["id"])
                if cancelling["state"] == "running": break
                assert cancelling["state"] not in {"failed", "succeeded", "cancelled"}, cancelling
                time.sleep(0.1)
            assert cancelling["state"] == "running"
            cancelling = call("POST", f"/attempts/{cancelling['id']}/cancel", {"expected_state_version": cancelling["state_version"]})
            cancelled = wait(cancelling); report["cancelled"] = cancelled; save()
            assert cancelled["state"] == "cancelled" and cancelled["compute_outcome"] == "cancelled"
            assert all(model_manifest(path)["manifest_digest"] == before[name]["manifest_digest"] for name, path in sources.items())
            report.update(status="passed", source_files_unchanged=True)
        except Exception as error:
            report.update(status="failed", error=repr(error)); raise
        finally: save()
    # 关闭服务后，以同一库重开正式接口，核对原始报告和独立人工记录。
    app = create_app(settings)
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer isolated-capability-probe"}) as client:
        restored = client.get("/api/v1/evaluations/" + report["attempt_id"]).json()
        assert restored["report"] == report["evaluation"]["report"] and restored["reviews"]["revision"] == 1
        assert len(client.get("/api/v1/source-checks", params={"project_id": report["project_id"]}).json()["items"]) == 4
        report["cold_reopen_verified"] = True; save()
    print(str(evidence / "report.json"), flush=True)


if __name__ == "__main__":
    main()
