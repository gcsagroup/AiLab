"""固定 MLX 量化任务与实验模型登记，不把格式转换当作质量验收。"""

from pathlib import Path

from .assets import copy_asset, model_manifest, regular_path, safe_json, verify_manifest
from .storage import Fault, digest, identifier

QUANTIZATION = {"bits": 4, "group_size": 64, "mode": "affine"}


class Conversion:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def quality_source(self, candidate):
        """重新核对实际转换来源；独立导入的量化文件不伪装为本产品转换候选。"""
        if candidate.get("format") != "mlx-safetensors" or candidate.get("default_engine") != "mlx" or candidate.get("modality") != "text" or not candidate.get("source_model_id") or not candidate.get("source_attempt_id"):
            raise Fault("MODEL_COMPARISON_UNSUPPORTED", "质量比较需要本产品保存的 MLX 量化模型及明确来源。", 409)
        base = self.store.get("model", candidate["source_model_id"])
        source = self.store.get("attempt", candidate["source_attempt_id"])
        if any(item["project_id"] != candidate["project_id"] for item in (base, source)):
            raise Fault("PROJECT_MISMATCH", "量化模型、原权重和转换来源必须属于同一项目。", 403)
        snapshot = source["snapshot"]
        if source.get("snapshot_digest") != digest(snapshot) or snapshot.get("operation") != "quantize" or source.get("compute_outcome") != "succeeded" or source.get("collection_state") != "succeeded":
            raise Fault("CONVERSION_SOURCE_CHANGED", "量化来源没有完整的实际转换及收集记录。", 409)
        expected = {"model_id": base["id"], "model_version_id": base["version_id"], "model_manifest_digest": base["manifest_digest"]}
        if candidate["id"] == base["id"] or any(snapshot.get(key) != value for key, value in expected.items()) or candidate.get("source_model_version_id") != base["version_id"] or candidate.get("source_manifest_digest") != base["manifest_digest"]:
            raise Fault("CONVERSION_SOURCE_CHANGED", "量化候选与原权重版本或转换来源不一致。", 409)
        for model in (base, candidate):
            if digest(model["manifest"]) != model["manifest_digest"]:
                raise Fault("CONVERSION_SOURCE_CHANGED", "模型清单自身摘要不一致。", 409)
            verify_manifest(Path(model["storage_path"]), model["manifest"])
            actual = model_manifest(Path(model["storage_path"]))
            if actual["model_config"] != model["model_config"] or actual["manifest_digest"] != model["manifest_digest"]:
                raise Fault("CONVERSION_SOURCE_CHANGED", "模型格式或文件与已保存记录不一致。", 409)
        base_config, candidate_config = base["model_config"], candidate["model_config"]
        if base_config.get("quantization") or base_config.get("quantization_config") or candidate_config.get("quantization") != QUANTIZATION or candidate_config.get("quantization_config") not in (None, QUANTIZATION):
            raise Fault("MODEL_COMPARISON_UNSUPPORTED", "当前仅比较未量化原权重与 MLX 4-bit／64／affine 候选。", 409)
        tokenizer_files = {"tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja", "generation_config.json"}
        if {item["path"]: item for item in base["manifest"] if item["path"] in tokenizer_files} != {item["path"]: item for item in candidate["manifest"] if item["path"] in tokenizer_files}:
            raise Fault("TOKENIZATION_IDENTITY_MISMATCH", "权重量化对照必须使用相同分词器、模板和生成配置。", 409)
        report_artifact = self.service.delivery.artifact_for_path(source, "conversion.json")
        report = safe_json(Path(report_artifact["storage_path"]))
        actual = source.get("effective_config", {})
        if actual != source["output_manifest_ref"].get("effective_config") or candidate.get("conversion", {}).get("report_artifact_id") != report_artifact["id"] or report.get("operation") != "quantize" or report.get("quantization") != QUANTIZATION or not actual.get("model_manifest_sha256") or report.get("source_model_manifest_sha256") != actual.get("model_manifest_sha256") or report.get("output_model_manifest") != candidate["manifest"] or report.get("output_model_manifest_digest") != candidate["manifest_digest"] or actual.get("model_output_manifest_digest") != candidate["manifest_digest"]:
            raise Fault("CONVERSION_SOURCE_CHANGED", "量化候选与原转换报告、实际参数或封存清单不一致。", 409)
        if any(report.get(field) != sum(item["size"] for item in model["manifest"] if item["path"].endswith(".safetensors")) for field, model in (("source_weight_bytes", base), ("output_weight_bytes", candidate))):
            raise Fault("CONVERSION_REPORT_INVALID", "转换体积证据与实际两份权重不一致。", 409)
        artifacts = [report_artifact]
        for entry in candidate["manifest"]:
            artifact = self.service.delivery.artifact_for_path(source, "model/" + entry["path"])
            if (artifact["sha256"], artifact["size"]) != (entry["sha256"], entry["size"]):
                raise Fault("CONVERSION_OUTPUT_CHANGED", "量化文件不属于原转换已收集的完整产物。", 409)
            artifacts.append(artifact)
        comparison = {"kind": "quantized_model", "baseline_model_id": base["id"], "baseline_model_version_id": base["version_id"], "baseline_model_manifest_digest": base["manifest_digest"],
                      "candidate_model_id": candidate["id"], "candidate_model_version_id": candidate["version_id"], "candidate_model_manifest_digest": candidate["manifest_digest"],
                      "conversion_attempt_id": source["id"], "conversion_manifest_digest": source["output_manifest_ref"]["digest"], "conversion_report_sha256": report_artifact["sha256"],
                      "candidate_format": candidate["format"], "candidate_default_engine": candidate["default_engine"], "quantization": QUANTIZATION}
        return base, source, comparison, artifacts

    def new_task(self, payload, key=None):
        with self.store.transaction():
            if key and (previous := self.store.replay("conversion-task", key, payload)):
                return previous
            model = self.store.get("model", payload["model_id"])
            if model["project_id"] != payload["project_id"]:
                raise Fault("PROJECT_MISMATCH", "源模型须属于当前项目。", 403)
            config = model["model_config"]
            if config.get("model_type") != "qwen2" or config.get("hidden_size") != 896 or config.get("num_hidden_layers") != 24 or config.get("quantization") or config.get("quantization_config"):
                raise Fault("MODEL_UNVERIFIED", "当前量化仅开放未量化 Qwen2.5-0.5B-Instruct。", 409)
            draft = {"kind": "text", "operation": "quantize", "model_id": model["id"], "dataset_id": None, "adapter_id": None, "evaluation_plan_id": None,
                     "input": {"prompt": ""}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", "seed": 0, **QUANTIZATION}}
            task = self.service.resource("task", payload["project_id"], name=payload.get("name") or "MLX 4-bit 量化", kind="text", operation="quantize", draft_revision=1, draft=draft)
            self.store.put("task", task)
            if key:
                self.store.remember("conversion-task", key, payload, task)
            return task

    def save_model(self, attempt_id, payload, key):
        if self.store.get("attempt", attempt_id)["snapshot"]["operation"] in {"merge", "distill", "convert"}:
            return self.service.model_lab.save_model(attempt_id, payload, key)
        scope = f"save-converted-model:{attempt_id}"
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if attempt["snapshot"]["operation"] != "quantize" or attempt["compute_outcome"] != "succeeded" or attempt["collection_state"] != "succeeded":
                raise Fault("CONVERSION_NOT_READY", "请先完成量化计算与产物收集。", 409)
            existing = [item for item in self.store.list("model", attempt["project_id"]) if item.get("source_attempt_id") == attempt_id]
            if existing:
                response = self.service.public(existing[0]); self.store.remember(scope, key, payload, response)
                return response
            source = self.store.get("model", attempt["snapshot"]["model_id"])
        snapshot = attempt["snapshot"]
        if digest(snapshot) != attempt["snapshot_digest"] or source["project_id"] != attempt["project_id"] or snapshot["model_version_id"] != source["version_id"] or snapshot["model_manifest_digest"] != source["manifest_digest"]:
            raise Fault("CONVERSION_SOURCE_CHANGED", "量化记录与来源模型身份不一致。", 409)
        verify_manifest(Path(source["storage_path"]), source["manifest"])
        metadata_artifact = self.service.delivery.artifact_for_path(attempt, "conversion.json")
        metadata = safe_json(Path(metadata_artifact["storage_path"]))
        actual = attempt.get("effective_config", {})
        if actual != attempt["output_manifest_ref"].get("effective_config"):
            raise Fault("CONVERSION_SOURCE_CHANGED", "量化实际参数与原执行清单不一致。", 409)
        if metadata.get("operation") != "quantize" or metadata.get("quantization") != QUANTIZATION or not actual.get("model_manifest_sha256") or metadata.get("source_model_manifest_sha256") != actual["model_manifest_sha256"]:
            raise Fault("CONVERSION_SOURCE_CHANGED", "转换报告缺少与实际执行一致的模型及格式身份。", 409)
        directory = regular_path(self.service.root / "runs" / attempt_id / "output" / "model")
        inspected = model_manifest(directory)
        config = inspected["model_config"]
        if config.get("model_type") != "qwen2" or config.get("hidden_size") != 896 or config.get("num_hidden_layers") != 24 or config.get("quantization") != QUANTIZATION or config.get("quantization_config") not in (None, QUANTIZATION):
            raise Fault("CONVERSION_FORMAT_MISMATCH", "转换输出不属于已验证的 MLX 4-bit／64／affine 格式。", 409)
        if metadata.get("output_model_manifest") != inspected["manifest"] or metadata.get("output_model_manifest_digest") != inspected["manifest_digest"] or actual.get("model_output_manifest_digest") != inspected["manifest_digest"]:
            raise Fault("CONVERSION_OUTPUT_CHANGED", "转换输出文件与原执行清单不一致。", 409)
        # 每个模型文件都必须已由原尝试收集，不能只信任一个可修改的转换报告。
        artifacts = [metadata_artifact]
        for entry in inspected["manifest"]:
            artifact = self.service.delivery.artifact_for_path(attempt, "model/" + entry["path"])
            if (artifact["size"], artifact["sha256"]) != (entry["size"], entry["sha256"]):
                raise Fault("CONVERSION_OUTPUT_CHANGED", "模型文件与已收集产物身份不一致。", 409)
            artifacts.append(artifact)
        source_bytes = sum(item["size"] for item in source["manifest"] if item["path"].endswith(".safetensors"))
        output_bytes = sum(item["size"] for item in inspected["manifest"] if item["path"].endswith(".safetensors"))
        if metadata.get("source_weight_bytes") != source_bytes or metadata.get("output_weight_bytes") != output_bytes:
            raise Fault("CONVERSION_REPORT_INVALID", "转换体积报告与实际文件不一致。", 409)
        destination = copy_asset(directory, self.service.root / "assets", inspected["manifest"], inspected["manifest_digest"])
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.store.get("attempt", attempt_id) != attempt or self.store.get("model", source["id"]) != source or any(self.store.get("artifact", item["id"]) != item for item in artifacts):
                raise Fault("CONVERSION_SOURCE_CHANGED", "保存检查期间来源记录发生变化，请重试。", 409)
            existing = [item for item in self.store.list("model", attempt["project_id"]) if item.get("source_attempt_id") == attempt_id]
            if existing:
                result = existing[0]
            else:
                policy = self.service.resource("load-policy", attempt["project_id"], source_attempt_id=attempt_id, manifest_digest=inspected["manifest_digest"], loader=inspected["loader"], trust_class=inspected["trust_class"], execution_scope=inspected["execution_scope"])
                self.store.put("load-policy", policy)
                result = self.service.resource("model", attempt["project_id"], name=payload.get("name") or f"{source['name']} · MLX 4-bit", revision=1,
                    version_id=identifier("version"), status="experimental", quality_status="not_evaluated", format="mlx-safetensors", modality="text", default_engine="mlx",
                    family=inspected["family"], model_config=config, manifest=inspected["manifest"], manifest_digest=inspected["manifest_digest"], total_bytes=inspected["total_bytes"], storage_path=str(destination),
                    load_policy_ref=policy["id"], loader=inspected["loader"], trust_class=inspected["trust_class"], execution_scope=inspected["execution_scope"],
                    source_attempt_id=attempt_id, source_model_id=source["id"], source_model_version_id=source["version_id"], source_manifest_digest=source["manifest_digest"],
                    conversion={"quantization": QUANTIZATION, "source_weight_bytes": source_bytes, "output_weight_bytes": output_bytes, "report_artifact_id": metadata_artifact["id"], "independent_use": "not_verified"},
                    message="量化文件已保存为实验模型；试用需要 MLX 引擎，质量尚未通过独立验收。")
                self.store.put("model", result)
            response = self.service.public(result)
            self.store.remember(scope, key, payload, response)
            return response
