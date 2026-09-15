"""量化登记的文件与来源合同；小文件仅用于合同，不代表真实模型效果。"""

import copy
import json
from pathlib import Path
import shutil

import pytest

from test_control import rig, post, setup_task
from ailab_control.assets import file_hash, model_manifest, verify_manifest
from ailab_control.conversion import Conversion, QUANTIZATION
from ailab_control.storage import Fault, digest


def converted_fixture(rig):
    _, service, _, _ = rig
    project, model, _ = setup_task(rig)
    conversion = Conversion(service)
    task = conversion.new_task({"project_id": project["id"], "model_id": model["id"]}, "fixed-task")
    base = service.store.get("model", model["id"])
    snapshot = {"operation": "quantize", "model_id": base["id"], "model_version_id": base["version_id"], "model_manifest_digest": base["manifest_digest"]}
    attempt = service.resource("attempt", project["id"], task_id=task["id"], state="succeeded", state_version=4, compute_outcome="succeeded", collection_state="succeeded", snapshot=snapshot, snapshot_digest=digest(snapshot))
    output = service.root / "runs" / attempt["id"] / "output"
    directory = output / "model"
    shutil.copytree(base["storage_path"], directory)
    config_path = directory / "config.json"; config_path.chmod(0o600)
    config = json.loads(config_path.read_text()); config["quantization"] = QUANTIZATION; config_path.write_text(json.dumps(config))
    inspected = model_manifest(directory)
    size = sum(item["size"] for item in inspected["manifest"] if item["path"].endswith(".safetensors"))
    metadata = {"operation": "quantize", "quantization": QUANTIZATION, "source_model_manifest_sha256": "a" * 64, "output_model_manifest": inspected["manifest"], "output_model_manifest_digest": inspected["manifest_digest"], "source_weight_bytes": size, "output_weight_bytes": size}
    (output / "conversion.json").write_text(json.dumps(metadata))
    attempt["effective_config"] = {"model_manifest_sha256": "a" * 64, "model_output_manifest_digest": inspected["manifest_digest"]}
    sealed = {"complete": True, "effective_config": copy.deepcopy(attempt["effective_config"]), "artifacts": [{"path": path.relative_to(output).as_posix(), "sha256": file_hash(path), "media_type": "application/octet-stream"} for path in sorted(output.rglob("*")) if path.is_file()]}
    attempt["output_manifest_ref"] = {**sealed, "digest": digest(sealed)}
    with service.store.transaction():
        service.store.put("attempt", attempt)
        for path in output.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(output).as_posix()
            artifact = service.resource("artifact", project["id"], attempt_id=attempt["id"], storage_path=str(path), name=path.name, size=path.stat().st_size, sha256=file_hash(path))
            artifact["id"] = "artifact-" + digest({"attempt_id": attempt["id"], "manifest": attempt["output_manifest_ref"]["digest"], "path": relative})[:32]
            service.store.put("artifact", artifact)
    return conversion, project, base, task, attempt, output


def test_create_fixed_conversion_does_not_launch_or_accept_foreign_model(rig):
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    manager = Conversion(service)
    body = {"project_id": project["id"], "model_id": model["id"], "name": "固定量化"}
    task = manager.new_task(body, "once")
    assert manager.new_task(body, "once")["id"] == task["id"]
    assert task["operation"] == "quantize" and task["draft"]["runtime"] == {"engine": "mlx", "device_id": "apple-gpu", "seed": 0, **QUANTIZATION}
    assert service.store.list("attempt") == []
    other = post(client, "/projects", {"name": "其他项目"})
    with pytest.raises(Fault) as error:
        manager.new_task({**body, "project_id": other["id"]})
    assert error.value.code == "PROJECT_MISMATCH"


def test_saves_independent_experimental_model_idempotently(rig):
    manager, project, base, _, attempt, _ = converted_fixture(rig)
    service = rig[1]
    model = manager.save_model(attempt["id"], {"name": "小文件量化合同"}, "save")
    assert model["id"] != base["id"] and model["status"] == "experimental"
    assert model["quality_status"] == "not_evaluated" and model["default_engine"] == "mlx"
    assert model["source_model_version_id"] == base["version_id"] and model["source_attempt_id"] == attempt["id"]
    assert manager.save_model(attempt["id"], {"name": "小文件量化合同"}, "save") == model
    assert manager.save_model(attempt["id"], {}, "another")["id"] == model["id"]
    assert len(service.store.list("model", project["id"])) == 2
    assert service.store.list("candidate", project["id"]) == []
    verify_manifest(Path(base["storage_path"]), base["manifest"])
    stored = service.store.get("model", model["id"])
    verify_manifest(Path(stored["storage_path"]), stored["manifest"])


@pytest.mark.parametrize("change,expected", [("operation", "CONVERSION_NOT_READY"), ("collection", "CONVERSION_NOT_READY"), ("snapshot", "CONVERSION_SOURCE_CHANGED"), ("metadata", "ARTIFACT_CORRUPT"), ("extra", "CONVERSION_OUTPUT_CHANGED"), ("weight", "CONVERSION_OUTPUT_CHANGED")])
def test_rejects_missing_collection_and_changed_evidence(rig, change, expected):
    manager, project, base, _, attempt, output = converted_fixture(rig)
    service = rig[1]
    if change in {"operation", "collection", "snapshot"}:
        if change == "operation":
            attempt["snapshot"]["operation"] = "train"
        elif change == "collection":
            attempt["collection_state"] = "failed"
        else:
            attempt["snapshot"]["model_manifest_digest"] = "f" * 64
        with service.store.transaction():
            service.store.put("attempt", attempt)
    elif change == "metadata":
        (output / "conversion.json").write_text("{}")
    elif change == "extra":
        (output / "model/extra.txt").write_text("新增但未登记")
    else:
        path = output / "model/model.safetensors"; path.chmod(0o600)
        data = path.read_bytes(); path.write_bytes(data[:-4] + b"\0\0\0\0")
    with pytest.raises(Fault) as error:
        manager.save_model(attempt["id"], {}, "bad")
    assert error.value.code == expected
    assert len(service.store.list("model", project["id"])) == 1


def test_converted_model_cannot_be_used_as_conversion_source(rig):
    manager, project, _, _, attempt, _ = converted_fixture(rig)
    model = manager.save_model(attempt["id"], {}, "saved")
    with pytest.raises(Fault) as error:
        manager.new_task({"project_id": project["id"], "model_id": model["id"]})
    assert error.value.code == "MODEL_UNVERIFIED"


def test_http_conversion_task_is_immutable_and_requires_explicit_submit(rig):
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    body = {"project_id": project["id"], "model_id": model["id"], "name": "量化HTTP合同"}
    task = post(client, "/conversions", body, "create-conversion")
    checked = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": task["draft_revision"]})
    assert checked["can_submit"] and service.store.list("attempt") == []
    changed = copy.deepcopy(task["draft"]); changed["runtime"]["bits"] = 8
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": 1, "draft": changed})
    assert response.status_code in {409, 422}
    assert service.store.get("task", task["id"])["draft"] == task["draft"]


@pytest.mark.parametrize("operation,engine,with_adapter", [("train", "mlx", False), ("evaluate", "mlx", False), ("quantize", "mlx", False), ("generate", "coreml", False), ("generate", "mlx", True)])
def test_converted_format_rejects_unverified_engine_and_operation(rig, operation, engine, with_adapter):
    manager, project, base, _, attempt, _ = converted_fixture(rig)
    client, service, _, _ = rig
    model = manager.save_model(attempt["id"], {}, "save")
    task = post(client, "/tasks", {"project_id": project["id"], "name": "转换模型检查", "kind": "text", "operation": "generate"})
    task["draft"].update(model_id=model["id"], operation=operation, input={"prompt": "试用"})
    task["draft"]["runtime"]["engine"] = engine
    if with_adapter:
        adapter = service.resource("adapter", project["id"], base_model_id=base["id"], base_manifest_digest=base["manifest_digest"], manifest=base["manifest"], storage_path=base["storage_path"])
        service.store.put("adapter", adapter)
        task["draft"]["adapter_id"] = adapter["id"]
    result = service.inspect_task(task)
    assert result["blocking"]


def test_exact_converted_format_can_be_checked_for_mlx_inference(rig):
    manager, project, _, _, attempt, _ = converted_fixture(rig)
    client, service, _, _ = rig
    model = manager.save_model(attempt["id"], {}, "save")
    task = post(client, "/tasks", {"project_id": project["id"], "name": "转换模型试用", "kind": "text", "operation": "generate"})
    task["draft"].update(model_id=model["id"], input={"prompt": "试用"})
    assert not service.inspect_task(task)["blocking"]


def test_file_and_artifact_rewrite_cannot_replace_original_execution_evidence(rig):
    manager, project, _, _, attempt, output = converted_fixture(rig)
    service = rig[1]
    artifact = service.delivery.artifact_for_path(attempt, "conversion.json")
    path = output / "conversion.json"
    value = json.loads(path.read_text()); value["unsealed_note"] = "产物记录也被替换"; path.write_text(json.dumps(value))
    artifact.update(size=path.stat().st_size, sha256=file_hash(path))
    with service.store.transaction():
        service.store.put("artifact", artifact)
    with pytest.raises(Fault) as error:
        manager.save_model(attempt["id"], {}, "rewritten")
    assert error.value.code == "ARTIFACT_CORRUPT"
    assert len(service.store.list("model", project["id"])) == 1
