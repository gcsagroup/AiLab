"""只读收口已有量化实测，不重新生成答案或覆盖首次失败记录。"""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "services/control"))
from adapters.mlx_text.evaluation import load_plan, summarize
from ailab_control.assets import file_hash, model_manifest, verify_manifest
from ailab_control.storage import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    root, plan_root = args.evidence.resolve(), args.plan.resolve()
    report = json.loads((root / "report.json").read_text())
    record = json.loads((root / "evaluation-record.json").read_text())
    frozen = json.loads((plan_root / "frozen-plan.json").read_text())
    assert file_hash(plan_root / "frozen-plan.json") == report["frozen_plan_sha256"]
    assert all(file_hash(plan_root / entry["path"]) == entry["sha256"] for entry in frozen["files"])
    assert all(file_hash(ROOT / path) == checksum for path, checksum in report["source_sha256"].items())
    db = sqlite3.connect((root / "data/control.sqlite3").as_uri() + "?mode=ro", uri=True)
    def resource(resource_id): return json.loads(db.execute("SELECT body FROM resources WHERE id=?", (resource_id,)).fetchone()[0])
    try:
        attempt = resource(record["id"]); candidate = resource(report["candidate_model_id"]); baseline = resource(report["base_model_id"])
        assert attempt["state"] == attempt["compute_outcome"] == attempt["collection_state"] == "succeeded"
        assert attempt["snapshot_digest"] == digest(attempt["snapshot"])
        for model in (baseline, candidate): verify_manifest(Path(model["storage_path"]), model["manifest"])
        external = model_manifest(ROOT / frozen["model_source"])
        assert external["manifest"] == baseline["manifest"] and external["manifest_digest"] == frozen["fixed_model_manifest_digest"]
        source = Path(candidate["storage_path"])
        assert model_manifest(source)["manifest_digest"] == candidate["manifest_digest"]
        output = root / "data/runs" / attempt["id"] / "output"
        sealed = attempt["output_manifest_ref"]
        assert digest({key: value for key, value in sealed.items() if key != "digest"}) == sealed["digest"]
        for entry in sealed["artifacts"]: assert file_hash(output / entry["path"]) == entry["sha256"]
        quality = json.loads((output / "evaluation-report.json").read_text())
        assert quality == record["report"]
        snapshot = attempt["snapshot"]
        rows, criteria, _ = load_plan(snapshot)
        predictions = {side: json.loads((output / side / "predictions.json").read_text()) for side in ("baseline", "candidate")}
        assert len({attempt["process"]["pid"], *[value["identity"]["pid"] for value in predictions.values()]}) == 3
        assert predictions["baseline"]["identity"]["model_manifest_digest"] == baseline["manifest_digest"]
        assert predictions["candidate"]["identity"]["model_manifest_digest"] == candidate["manifest_digest"]
        rescored = summarize(rows, criteria, predictions["baseline"]["outputs"], predictions["candidate"]["outputs"], True)
        for key in ("status", "eligible", "counts", "samples", "blocking", "regression_pass_rate_delta"): assert quality[key] == rescored[key]
        assert not quality["eligible"] and quality["status"] == "failed" and report["admission"]["http_status"] == 409
        assert report["admission"]["response"]["error"]["code"] == "EVALUATION_FAILED"
        assert db.execute("SELECT COUNT(*) FROM resources WHERE kind='candidate'").fetchone()[0] == 0
        exported = {}
        for key in ("report_export", "model_export"):
            directory = Path(report[key]["record"]["verified_path"])
            manifest = json.loads((directory / "manifest.json").read_text())
            assert manifest["complete"] is True
            for entry in manifest["files"]: assert file_hash(directory / entry["path"]) == entry["sha256"]
            exported[key] = {"directory": str(directory), "file_count": len(manifest["files"]), "all_hashes_match": True}
        report_directory = Path(exported["report_export"]["directory"])
        assert json.loads((report_directory / "report/evaluation-report.json").read_text()) == quality
        assert model_manifest(Path(exported["model_export"]["directory"]) / "model")["manifest_digest"] == candidate["manifest_digest"]
        recipe = json.loads((report_directory / "recipe.json").read_text())
        assert recipe["model_comparison"] == snapshot["model_comparison"] and "candidate_model_path" not in recipe
        initial_error = report.get("error")
        assert report["status"] == "passed" or initial_error == "Fault('已登记资产文件集合发生变化，请重新导入。')"
        completion = {"status": "passed", "scope": "真实量化与独立质量比较、失败门禁、完整报告及模型导出回读", "quality_status": quality["status"], "quality_eligible": quality["eligible"], "original_run_report_sha256": file_hash(root / "report.json"), "original_run_report_status": report["status"],
                      "original_harness_error": initial_error, "harness_error_resolution": "末尾将外部HF缓存目录误作已登记完整资产目录；本次按原导入策略重算9文件模型清单并核对全部已登记原权重/量化资产。未重跑GPU，原失败报告保留。" if initial_error else None,
                      "frozen_plan_unchanged": True, "source_code_unchanged": True, "source_model_unchanged": True, "sealed_artifact_count": len(sealed["artifacts"]), "independent_loads": quality["independent_loads"], "counts": quality["counts"], "blocking": quality["blocking"], "exports": exported, "candidate_registry_count": 0, "candidate_status": candidate["status"], "evaluation_attempt_id": attempt["id"], "evaluation_task_id": attempt["task_id"], "candidate_model_id": candidate["id"], "project_id": attempt["project_id"]}
        destination = root / "completion.json"
        destination.write_text(json.dumps(completion, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": completion["status"], "quality_status": quality["status"], "quality_eligible": quality["eligible"], "output": str(destination)}, ensure_ascii=False))
    finally: db.close()


if __name__ == "__main__": main()
