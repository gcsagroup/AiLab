"""模型实验的输入绑定与独立模型登记，复用正式任务和产物收集。"""

from pathlib import Path

from .assets import copy_asset, model_manifest, safe_json, verify_manifest
from .model_profiles import model_profile
from .storage import Fault, digest, identifier


class ModelLab:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def new_task(self, payload, key):
        from .service import TRAIN_RUNTIME
        with self.store.transaction():
            if key and (previous := self.store.replay("model-lab-task", key, payload)):
                return previous
            operation = payload["operation"]
            model = self.store.get("model", payload["model_id"])
            if model["project_id"] != payload["project_id"]:
                raise Fault("PROJECT_MISMATCH", "模型必须属于当前项目。", 403)
            try:
                profile = model_profile(model["model_config"])
            except ValueError as error:
                raise Fault("MODEL_UNVERIFIED", str(error), 409) from None
            if profile["name"] != "qwen25-0.5b":
                raise Fault("MODEL_UNVERIFIED", "本轮合并和蒸馏学生仅开放已验收的 Qwen2.5-0.5B；教师可选 7B。", 409)
            if model["model_config"].get("quantization") or model["model_config"].get("quantization_config"):
                raise Fault("MODEL_UNVERIFIED", "合并和蒸馏需要未量化基座。", 409)
            runtime = {"engine": "mlx", "device_id": "apple-gpu", "seed": 0}
            if operation == "merge":
                if not payload.get("adapter_id") or payload.get("teacher_model_id") or payload.get("dataset_id"):
                    raise Fault("INVALID_CONFIG", "合并须选择适配器，不能绑定教师或训练数据。")
                runtime["merge_weight"] = payload["merge_weight"]
            else:
                if not payload.get("teacher_model_id") or not payload.get("dataset_id") or payload.get("adapter_id"):
                    raise Fault("INVALID_CONFIG", "蒸馏须选择教师与数据，学生从未量化基座开始。")
                runtime.update(TRAIN_RUNTIME, steps=payload["steps"], max_seq_length=payload["max_seq_length"], teacher_max_tokens=payload["teacher_max_tokens"])
            draft = {"kind": "text", "operation": operation, "model_id": model["id"], "adapter_id": payload.get("adapter_id"), "teacher_model_id": payload.get("teacher_model_id"), "dataset_id": payload.get("dataset_id"), "evaluation_plan_id": None, "input": {"prompt": ""}, "runtime": runtime}
            task = self.service.resource("task", payload["project_id"], name=payload.get("name") or {"merge": "LoRA 权重合并", "distill": "本地离线蒸馏"}[operation], kind="text", operation=operation, draft_revision=1, draft=draft, immutable_draft=True)
            self.fields(task)
            if operation == "merge":
                adapter = self.store.get("adapter", draft["adapter_id"])
                if adapter["project_id"] != task["project_id"] or adapter["base_model_id"] != model["id"] or adapter["base_model_version_id"] != model["version_id"] or adapter["base_manifest_digest"] != model["manifest_digest"]:
                    raise Fault("ADAPTER_BASE_MISMATCH", "适配器与基座的版本及文件身份不一致。", 409)
            self.store.put("task", task)
            if key:
                self.store.remember("model-lab-task", key, payload, task)
            return task

    def fields(self, task):
        if task["operation"] != "distill":
            return {}
        teacher = self.store.get("model", task["draft"]["teacher_model_id"])
        dataset = self.store.get("dataset", task["draft"]["dataset_id"])
        if any(item["project_id"] != task["project_id"] for item in (teacher, dataset)):
            raise Fault("PROJECT_MISMATCH", "教师、学生与数据必须属于同一项目。", 403)
        try:
            model_profile(teacher["model_config"])
        except ValueError as error:
            raise Fault("TEACHER_UNSUPPORTED", str(error), 409) from None
        if teacher["model_config"].get("quantization") or teacher["model_config"].get("quantization_config"):
            raise Fault("TEACHER_UNSUPPORTED", "当前教师必须为未量化 Qwen2.5 模型。", 409)
        verify_manifest(Path(teacher["storage_path"]), teacher["manifest"])
        return {"teacher": {"model_id": teacher["id"], "version_id": teacher["version_id"], "path": teacher["storage_path"], "manifest": teacher["manifest"], "manifest_digest": teacher["manifest_digest"]}}

    def save_model(self, attempt_id, payload, key):
        scope = f"save-lab-model:{attempt_id}"
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            snapshot = attempt["snapshot"]
            if snapshot["operation"] not in {"merge", "distill", "convert"} or attempt["compute_outcome"] != "succeeded" or attempt["collection_state"] != "succeeded" or digest(snapshot) != attempt["snapshot_digest"]:
                raise Fault("MODEL_LAB_NOT_READY", "实验尚未成功完成计算和收集。", 409)
            source = self.store.get("model", snapshot["model_id"])
        if source["project_id"] != attempt["project_id"] or source["manifest_digest"] != snapshot["model_manifest_digest"] or source["version_id"] != snapshot["model_version_id"]:
            raise Fault("MODEL_LAB_SOURCE_CHANGED", "实验来源与模型版本不一致。", 409)
        verify_manifest(Path(source["storage_path"]), source["manifest"])
        report_artifact = self.service.delivery.artifact_for_path(attempt, "conversion.json")
        report = safe_json(Path(report_artifact["storage_path"]))
        directory = self.service.root / "runs" / attempt_id / "output" / "model"
        if snapshot["operation"] == "convert":
            from .format_assets import format_manifest
            inspected = {**format_manifest(directory), "model_config": source["model_config"], "family": source["family"], "loader": "internal_conversion." + snapshot["runtime"]["engine"], "trust_class": "verified_internal_conversion", "execution_scope": {"network": False, "custom_code": False, "credentials": False}}
            if inspected["metadata"]["format"] != snapshot["runtime"]["engine"]:
                raise Fault("CONVERTED_ENGINE_MISMATCH", "产物格式与任务目标不一致。", 409)
        else:
            inspected = model_manifest(directory)
        effective = attempt.get("effective_config", {})
        if effective != attempt["output_manifest_ref"].get("effective_config") or report.get("operation") != snapshot["operation"] or report.get("source_model_manifest_digest") != source["manifest_digest"] or report.get("source_model_manifest_sha256") != effective.get("model_manifest_sha256") or report.get("output_model_manifest") != inspected["manifest"] or report.get("output_model_manifest_digest") != inspected["manifest_digest"] or effective.get("model_output_manifest_digest") != inspected["manifest_digest"] or report.get("verification", {}).get("passed") is not True or effective.get("independent_use") != "verified":
            raise Fault("MODEL_LAB_OUTPUT_CHANGED", "实验报告、独立加载记录或输出清单不一致。", 409)
        if inspected["model_config"] != source["model_config"]:
            raise Fault("MODEL_LAB_FORMAT_CHANGED", "融合模型结构必须与学生或基座一致。", 409)
        artifacts = [report_artifact]
        for entry in inspected["manifest"]:
            artifact = self.service.delivery.artifact_for_path(attempt, "model/" + entry["path"])
            if (artifact["size"], artifact["sha256"]) != (entry["size"], entry["sha256"]):
                raise Fault("MODEL_LAB_OUTPUT_CHANGED", "输出与原收集产物不一致。", 409)
            artifacts.append(artifact)
        destination = copy_asset(directory, self.service.root / "assets", inspected["manifest"], inspected["manifest_digest"])
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.store.get("attempt", attempt_id) != attempt or self.store.get("model", source["id"]) != source or any(self.store.get("artifact", artifact["id"]) != artifact for artifact in artifacts):
                raise Fault("MODEL_LAB_SOURCE_CHANGED", "保存检查期间来源发生变化。", 409)
            existing = next((model for model in self.store.list("model", attempt["project_id"]) if model.get("source_attempt_id") == attempt_id), None)
            if not existing:
                policy = self.service.resource("load-policy", attempt["project_id"], source_attempt_id=attempt_id, manifest_digest=inspected["manifest_digest"], loader=inspected["loader"], trust_class=inspected["trust_class"], execution_scope=inspected["execution_scope"])
                self.store.put("load-policy", policy)
                existing = self.service.resource("model", attempt["project_id"], name=payload.get("name") or source["name"] + {"merge": " · 合并", "distill": " · 蒸馏学生", "convert": " · " + snapshot["runtime"]["engine"]}[snapshot["operation"]], revision=1, version_id=identifier("version"), status="experimental", quality_status="not_evaluated", format=snapshot["runtime"]["engine"] if snapshot["operation"] == "convert" else "safetensors", modality="text", default_engine=snapshot["runtime"]["engine"] if snapshot["operation"] == "convert" else "mlx", family=inspected["family"], model_config=inspected["model_config"], manifest=inspected["manifest"], manifest_digest=inspected["manifest_digest"], total_bytes=inspected["total_bytes"], storage_path=str(destination), load_policy_ref=policy["id"], loader=inspected["loader"], trust_class=inspected["trust_class"], execution_scope=inspected["execution_scope"], source_attempt_id=attempt_id, source_model_id=source["id"], source_model_version_id=source["version_id"], source_manifest_digest=source["manifest_digest"], lab_operation=snapshot["operation"], lab_report_artifact_id=report_artifact["id"], format_details=inspected.get("metadata"), independent_use="verified", message="已独立加载；固定样例通过不等于模型质量通过。")
                self.store.put("model", existing)
            response = self.service.public(existing)
            self.store.remember(scope, key, payload, response)
            return response
