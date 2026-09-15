"""模型文件与生成正文分离，验证历史及新 HTTP 响应保持有限体积。"""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from test_control import rig, post, setup_task, submit, wait_attempt
from ailab_control.assets import file_hash


@pytest.mark.parametrize("operation", ["generate", "quantize", "evaluate", "train"])
def test_only_explicit_generation_result_is_inline_and_files_unchanged(rig, operation):
    client, service, *_ = rig
    project, _, task = setup_task(rig)
    attempt = service.resource("attempt", project["id"], task_id=task["id"], state="finalizing", state_version=1, compute_outcome="succeeded", collection_state="not_started", collection_version=0, snapshot={"operation": operation}, last_event_sequence=0, output_text="")
    output = service.root / "runs" / attempt["id"] / "output"
    (output / "model").mkdir(parents=True)
    (output / "model/tokenizer.json").write_text('{"tokens":"' + "字" * 700000 + '"}')
    (output / "model/merges.txt").write_text("模型合并规则\n" * 180000)
    (output / "result.txt").write_text("真实中文生成正文。")
    entries = [{"path": path.relative_to(output).as_posix(), "sha256": file_hash(path), "media_type": "application/json" if path.suffix == ".json" else "text/plain"} for path in output.rglob("*") if path.is_file()]
    attempt["output_manifest_ref"] = service.seal_manifest({"artifacts": entries})
    original = {item["path"]: item["sha256"] for item in entries}
    with service.store.transaction():
        service.store.put("attempt", attempt)
    service.collect(attempt["id"])
    response = client.get(f"/api/v1/attempts/{attempt['id']}")
    assert response.status_code == 200 and len(response.content) < 128 * 1024
    result = response.json()
    assert result["output_text"] == ("真实中文生成正文。" if operation == "generate" else "")
    for artifact in result["artifacts"]:
        assert artifact["text"] == ("真实中文生成正文。" if operation == "generate" and artifact["relative_path"] == "result.txt" else None)
    wrong = next(item for item in result["artifacts"] if item["relative_path"] == "model/merges.txt")
    rejected = client.post("/api/v1/works", json={"attempt_id": attempt["id"], "artifact_id": wrong["id"]}, headers={"Idempotency-Key": "wrong-work"})
    assert rejected.status_code == 409
    saved_work = client.post("/api/v1/works", json={"attempt_id": attempt["id"]}, headers={"Idempotency-Key": "correct-work"})
    assert saved_work.status_code == (200 if operation == "generate" else 409)
    if operation == "generate":
        assert saved_work.json()["text"] == "真实中文生成正文。" and saved_work.json()["text_truncated"] is False
    assert original == {relative: file_hash(output / relative) for relative in original}
    assert service.store.get("attempt", attempt["id"])["output_manifest_ref"] == attempt["output_manifest_ref"]
    # 重现旧版把 tokenizer 和 merges 内嵌进数据库的历史；public 必须直接收窄响应。
    with service.store.transaction():
        stored = service.store.get("attempt", attempt["id"])
        stored["output_text"] = "历史模型文件\n" * 400000
        service.store.put("attempt", stored)
        for artifact in service.store.list("artifact"):
            artifact["text"] = "历史模型文件\n" * 400000
            service.store.put("artifact", artifact)
    legacy = client.get(f"/api/v1/attempts/{attempt['id']}")
    assert len(legacy.content) < 128 * 1024
    assert all(item["text"] is None for item in legacy.json()["artifacts"] if item["relative_path"] != "result.txt")
    if operation != "generate":
        assert legacy.json()["output_text"] == ""


def test_long_generation_preview_marks_truncation_without_truncating_artifact(rig):
    client, service, *_ = rig
    project, _, task = setup_task(rig)
    attempt = service.resource("attempt", project["id"], task_id=task["id"], state="finalizing", state_version=1, compute_outcome="succeeded", collection_state="not_started", collection_version=0, snapshot={"operation": "generate"}, last_event_sequence=0, output_text="")
    output = service.root / "runs" / attempt["id"] / "output"
    output.mkdir(parents=True)
    full_text = "中文生成正文。" * 10000
    path = output / "result.txt"
    path.write_text(full_text)
    attempt["output_manifest_ref"] = service.seal_manifest({"artifacts": [{"path": "result.txt", "sha256": file_hash(path), "media_type": "text/plain"}]})
    with service.store.transaction(): service.store.put("attempt", attempt)
    service.collect(attempt["id"])
    response = client.get(f"/api/v1/attempts/{attempt['id']}")
    assert len(response.content) < 128 * 1024
    value = response.json()
    assert len(value["output_text"]) == 16000 and value["output_text_truncated"] is True
    assert value["artifacts"][0]["text_truncated"] is True
    work = post(client, "/works", {"attempt_id": attempt["id"]}, "long-work")
    assert len(work["text"]) == 16000 and work["text_truncated"] is True
    saved = service.store.get("artifact", value["artifacts"][0]["id"])
    assert Path(saved["storage_path"]).read_text() == full_text and path.read_text() == full_text


def test_work_verification_hash_does_not_hold_control_transaction(rig, monkeypatch):
    import ailab_control.delivery as delivery
    client, service, *_ = rig
    _, _, task = setup_task(rig)
    done = wait_attempt(client, submit(rig, task)[0]["id"])
    _, _, waiting_task = setup_task(rig, "__wait__")
    waiting = wait_attempt(client, submit(rig, waiting_task, "other-run")[0]["id"], lambda item: bool(item["output_text"]))
    entered, release = threading.Event(), threading.Event()
    original = delivery.file_hash

    def slow(path):
        entered.set()
        assert release.wait(3)
        return original(path)

    monkeypatch.setattr(delivery, "file_hash", slow)
    with ThreadPoolExecutor(max_workers=1) as executor:
        work = executor.submit(post, client, "/works", {"attempt_id": done["id"]}, "slow-work")
        assert entered.wait(2)
        before = time.monotonic()
        cancelled = post(client, f"/attempts/{waiting['id']}/cancel", {"expected_state_version": waiting["state_version"]}, "cancel-work-hash")
        assert time.monotonic() - before < 1 and cancelled["state"] == "cancelling"
        release.set()
        assert work.result(3)["text"] == done["output_text"]
    assert wait_attempt(client, waiting["id"])["state"] == "cancelled"
