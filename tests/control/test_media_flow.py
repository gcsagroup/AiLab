"""真实 PNG/WAV 小文件验证媒体 API 闭包；不把这些字节当模型生成证据。"""

from pathlib import Path
import io
import struct
import wave

import pytest

from test_control import rig, post
from test_media_assets import png
from test_delivery import prepare, export
from ailab_control.assets import file_hash
from ailab_control.storage import digest
import ailab_control.media as media_module


def media_attempt(rig, kind="image", primary_bytes=None):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "媒体合同隔离夹具"})
    task = post(client, "/tasks", {"project_id": project["id"], "name": "字节结构验证", "kind": kind, "operation": "generate"})
    snapshot = {"kind": kind, "operation": "generate", "input": {"prompt": "只验证文件与接口，不是质量证明"}, "runtime": task["draft"]["runtime"]}
    attempt = service.resource("attempt", project["id"], task_id=task["id"], state="finalizing", state_version=1,
                               snapshot=snapshot, snapshot_digest=digest(snapshot), compute_outcome="succeeded", collection_state="not_started",
                               collection_version=0, output_manifest_ref=None, last_event_sequence=0, terminal_reason=None)
    output = service.root / "runs" / attempt["id"] / "output"
    output.mkdir(parents=True)
    relative, mime = media_module.PRIMARY[kind]
    primary = output / relative; primary.parent.mkdir()
    if primary_bytes is not None:
        primary.write_bytes(primary_bytes)
    elif kind == "image":
        png(primary, width=8, height=8)
    else:
        with wave.open(str(primary), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000); stream.writeframes(b"\0\0" * 240)
    metadata = output / "generation.json"; metadata.write_text('{"fixture_only":true}')
    entries = [{"path": relative, "sha256": file_hash(primary), "media_type": mime},
               {"path": "generation.json", "sha256": file_hash(metadata), "media_type": "application/json"}]
    attempt["output_manifest_ref"] = service.seal_manifest({"artifacts": entries})
    with service.store.transaction(): service.store.put("attempt", attempt)
    collected = service.collect(attempt["id"])
    assert collected["state"] == "succeeded"
    artifact = next(item for item in service.store.list("artifact") if item["attempt_id"] == attempt["id"] and item["relative_path"] == relative)
    return project, service.store.get("attempt", attempt["id"]), artifact, primary.read_bytes()


@pytest.mark.parametrize("kind", ["image", "audio"])
def test_authenticated_content_and_saved_work_export_keep_original_media(rig, tmp_path, kind):
    client, service, *_ = rig
    project, attempt, artifact, original = media_attempt(rig, kind)
    response = client.get(f"/api/v1/artifacts/{artifact['id']}/content")
    assert response.status_code == 200 and response.content == original
    assert response.headers["content-type"] == media_module.PRIMARY[kind][1]
    assert response.headers["cache-control"] == "no-store" and response.headers["x-content-type-options"] == "nosniff"
    work = post(client, "/works", {"attempt_id": attempt["id"], "name": "保存主媒体"}, "save-media")
    assert work["kind"] == kind and work["media_type"] == artifact["media_type"]
    assert work["artifact_id"] == artifact["id"] and work["recipe"] == attempt["snapshot"]
    assert work["quality_status"] == "not_evaluated" and work["text"] is None
    plan = prepare(rig, "work", work["id"], project["id"], tmp_path / "媒体导出")
    exported, _ = export(rig, plan)
    assert exported["state"] == "succeeded"
    target = Path(exported["verified_path"])
    assert (target / "work" / artifact["name"]).read_bytes() == original


def test_saved_image_becomes_material_with_frozen_source_and_idempotency(rig):
    client, service, *_ = rig
    _, attempt, artifact, original = media_attempt(rig)
    work = post(client, "/works", {"attempt_id": attempt["id"]}, "save-image")
    material = post(client, f"/works/{work['id']}/materials", {}, "image-material")
    assert material["kind"] == "image" and material["media_type"] == "image/png"
    assert material["source_work_id"] == work["id"] and material["source_attempt_id"] == attempt["id"]
    assert post(client, f"/works/{work['id']}/materials", {}, "image-material") == material
    stored = service.store.get("material", material["id"])
    assert (Path(stored["storage_path"]) / stored["entrypoint"]).read_bytes() == original
    assert file_hash(Path(artifact["storage_path"])) == artifact["sha256"]


def test_no_auth_nonprimary_json_and_mismatched_artifact_are_rejected(rig):
    client, service, *_ = rig
    _, attempt, artifact, _ = media_attempt(rig)
    private = client.get(f"/api/v1/artifacts/{artifact['id']}/content", headers={"Authorization": ""})
    assert private.status_code == 401 and private.headers["content-type"].startswith("application/json")
    metadata = next(item for item in service.store.list("artifact") if item["relative_path"] == "generation.json")
    metadata["media_type"] = "image/png"
    with service.store.transaction(): service.store.put("artifact", metadata)
    rejected = client.get(f"/api/v1/artifacts/{metadata['id']}/content")
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "MEDIA_NOT_PREVIEWABLE"
    rejected = client.post("/api/v1/works", json={"attempt_id": attempt["id"], "artifact_id": metadata["id"]}, headers={"Idempotency-Key": "wrong-primary"})
    assert rejected.status_code == 409 and not service.store.list("work")


@pytest.mark.parametrize("damage", ["bytes", "mime", "project", "manifest", "not_collected"])
def test_tampered_media_identity_or_unclosed_result_cannot_be_previewed_or_saved(rig, damage):
    client, service, *_ = rig
    _, attempt, artifact, _ = media_attempt(rig)
    if damage == "bytes":
        source = Path(artifact["storage_path"]); source.chmod(0o600); source.write_bytes(b"changed")
    elif damage == "mime": artifact["media_type"] = "text/html"
    elif damage == "project": artifact["project_id"] = post(client, "/projects", {"name": "另一个项目"})["id"]
    elif damage == "manifest": attempt["output_manifest_ref"]["artifacts"][0]["sha256"] = "0" * 64
    else: attempt["collection_state"] = "failed"
    with service.store.transaction():
        service.store.put("artifact", artifact); service.store.put("attempt", attempt)
    for response in [client.get(f"/api/v1/artifacts/{artifact['id']}/content"), client.post("/api/v1/works", json={"attempt_id": attempt["id"]}, headers={"Idempotency-Key": "damaged"})]:
        assert response.status_code in (403, 409), response.text
    assert not service.store.list("work")


def test_content_size_limit_is_enforced_without_returning_bytes(rig, monkeypatch):
    client = rig[0]
    _, _, artifact, original = media_attempt(rig)
    assert media_module.MAX_CONTENT == 64 * 1024 * 1024
    monkeypatch.setattr(media_module, "MAX_CONTENT", len(original) - 1)
    response = client.get(f"/api/v1/artifacts/{artifact['id']}/content")
    assert response.status_code == 413 and response.json()["error"]["code"] == "MEDIA_TOO_LARGE"


@pytest.mark.parametrize("invalid", ["png_json", "wav_truncated", "mp4_missing_ftyp", "mp4_missing_moov", "mp4_missing_mdat", "mp4_truncated_box"])
def test_primary_extension_and_self_consistent_hash_do_not_substitute_for_media_structure(rig, invalid):
    def box(name, body=b""):
        return struct.pack(">I", len(body) + 8) + name + body
    if invalid == "png_json":
        kind, raw = "image", b'{"not_a_png":true}'
    elif invalid == "wav_truncated":
        kind = "audio"; output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000); stream.writeframes(b"\0\0" * 240)
        raw = output.getvalue()[:-1]
    else:
        kind = "video"
        boxes = {"ftyp": box(b"ftyp", b"isom\0\0\0\0isomiso2"), "moov": box(b"moov"), "mdat": box(b"mdat", b"fixture")}
        if invalid == "mp4_truncated_box": raw = struct.pack(">I", 1000) + b"ftypisom"
        else: raw = b"".join(value for name, value in boxes.items() if name != invalid.removeprefix("mp4_missing_"))
    _, attempt, artifact, _ = media_attempt(rig, kind, raw)
    responses = [rig[0].get(f"/api/v1/artifacts/{artifact['id']}/content"), rig[0].post("/api/v1/works", json={"attempt_id": attempt["id"]}, headers={"Idempotency-Key": "invalid-encoded-primary"})]
    for response in responses:
        assert response.status_code in (400, 409), response.text
    assert not rig[1].store.list("work")


def test_audio_work_and_cross_project_work_cannot_become_image_material(rig):
    client, service, *_ = rig
    _, audio, _, _ = media_attempt(rig, "audio")
    work = post(client, "/works", {"attempt_id": audio["id"]}, "save-audio")
    assert client.post(f"/api/v1/works/{work['id']}/materials", json={}, headers={"Idempotency-Key": "audio-material"}).status_code == 409
    _, image, _, _ = media_attempt(rig)
    work = post(client, "/works", {"attempt_id": image["id"]}, "save-image")
    stored = service.store.get("work", work["id"]); stored["project_id"] = audio["project_id"]
    with service.store.transaction(): service.store.put("work", stored)
    assert client.post(f"/api/v1/works/{work['id']}/materials", json={}, headers={"Idempotency-Key": "cross-material"}).status_code == 409
    assert not service.store.list("material")
