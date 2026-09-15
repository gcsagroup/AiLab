"""手动执行真实 MLX 控制闭环，不属于常规夹具测试。"""

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "control"))
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.assets import file_hash
from ailab_control.service import Service, Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    args.data_dir = args.data_dir.resolve()
    model_source = ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct"
    input_dir = args.data_dir.parent / "real-input"
    input_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = input_dir / "sft.jsonl"
    dataset_path.write_text("\n".join(json.dumps({"messages": [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]}, ensure_ascii=False) for question, answer in [("什么是版本？", "版本是固定内容的记录。"), ("为什么保存摘要？", "摘要用于检查内容是否发生变化。")]) + "\n")
    token = secrets.token_urlsafe(32)
    settings = Settings(args.data_dir, token, [model_source, input_dir], ROOT / "adapters/mlx_text/.venv/bin/python", ROOT / "workers/mlx_worker.py", preflight_script=ROOT / "adapters/mlx_text/preflight.py")
    app = create_app(settings)
    report = {"scope": "真实控制服务至本机MLX，不代表质量或跨设备验收", "started_at": time.time(), "checks": {}}
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer " + token}) as client:
        def post(path, body, key=None):
            result = client.post("/api/v1" + path, json=body, headers={"Idempotency-Key": key} if key else {})
            assert result.status_code == 200, result.text
            return result.json()

        def execute(task):
            checked = post(f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
            assert checked["can_submit"], checked
            submitted = post(f"/tasks/{task['id']}/attempts", {"preflight_id": checked["id"], "expected_revision": task["draft_revision"]}, task["id"])
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                attempt = client.get(f"/api/v1/attempts/{submitted['id']}").json()
                if attempt["state"] in {"succeeded", "failed", "cancelled"}:
                    break
                time.sleep(0.1)
            assert attempt["state"] == "succeeded", attempt
            assert attempt["compute_outcome"] == attempt["collection_state"] == "succeeded"
            return checked, attempt

        project = post("/projects", {"name": "真实MLX控制验收"})
        plan = post("/models/import-plans", {"project_id": project["id"], "path": str(model_source), "name": "Qwen2.5-0.5B-Instruct 官方固定版本"})
        model = post("/models/imports", {"plan_id": plan["id"], "manifest_digest": plan["manifest_digest"]}, "import-model")
        data_plan = post("/datasets/import-plans", {"project_id": project["id"], "path": str(dataset_path), "schema": "sft"})
        dataset = post("/datasets/imports", {"plan_id": data_plan["id"], "manifest_digest": data_plan["manifest_digest"]}, "import-dataset")
        report.update(project=project, model=model, dataset=dataset)
        generate = post("/tasks", {"project_id": project["id"], "kind": "text", "operation": "generate", "name": "真实文本生成"})
        generate["draft"].update(model_id=model["id"], input={"prompt": "请用一句话说明为什么需要保存数据版本。"})
        generate["draft"]["runtime"]["max_tokens"] = 32
        saved = client.patch(f"/api/v1/tasks/{generate['id']}/draft", json={"expected_revision": 1, "draft": generate["draft"]})
        assert saved.status_code == 200, saved.text
        generate = saved.json()
        check, attempt = execute(generate)
        assert attempt["output_text"].strip()
        report["generate"] = {"preflight": check, "attempt": attempt}
        work = post("/works", {"attempt_id": attempt["id"], "name": "真实结果"}, "save-real-work")
        report["work"] = work
        training = post("/tasks", {"project_id": project["id"], "kind": "text", "operation": "train", "name": "真实一步SFT LoRA"})
        training["draft"].update(model_id=model["id"], dataset_id=dataset["id"])
        training["draft"]["runtime"].update(steps=1, max_seq_length=128)
        saved = client.patch(f"/api/v1/tasks/{training['id']}/draft", json={"expected_revision": 1, "draft": training["draft"]})
        assert saved.status_code == 200, saved.text
        checked, trained = execute(saved.json())
        assert checked["tokenization_recipe_digest"] == trained["snapshot"]["tokenization_recipe_digest"]
        assert any(item["name"] == "adapters.safetensors" for item in trained["artifacts"])
        report["train"] = {"preflight": checked, "attempt": trained}
        report["checks"].update(real_generation=True, real_sft_lora=True, files_registered=True, fixed_tokenization_identity=True)
    reopened = Service(settings)
    try:
        assert reopened.store.get("work", work["id"])["text"] == attempt["output_text"]
        assert reopened.store.get("attempt", trained["id"])["state"] == "succeeded"
        report["checks"]["reopen_persistence"] = True
    finally:
        reopened.close()
    report["finished_at"] = time.time()
    destination = args.data_dir.parent / "real-smoke-report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "passed", "checks": report["checks"], "report": str(destination), "project_id": project["id"], "generate_attempt_id": attempt["id"], "train_attempt_id": trained["id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
