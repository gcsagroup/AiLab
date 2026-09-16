"""实验适配器与本机产物导出；不替代独立评测准入。"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import threading

from .assets import authorized_path, check_safetensors, file_hash, regular_path, safe_json, verify_manifest
from .storage import Fault, digest, encode, identifier, now


class ExportCancelled(Exception):
    pass


def portable_recipe(snapshot):
    allowed = {"schema_version", "attempt_id", "task_id", "project_id", "draft_revision", "kind", "operation", "model_id", "model_version_id", "model_manifest_digest", "model_manifest", "adapter_id", "adapter_version_id", "adapter_manifest_digest", "adapter_training_recipe_digest", "dataset_id", "dataset_version_id", "dataset_manifest_digest", "dataset_manifest", "tokenization_recipe_digest", "tokenization_recipe", "input", "runtime", "requested_config", "effective_config", "submitted_at", "preflight_id", "evaluation_plan_id", "evaluation_plan_digest", "evaluation_dataset_manifest", "evaluation_dataset_manifest_digest", "evaluation_criteria_manifest", "evaluation_criteria_manifest_digest", "evaluation_kind", "candidate_model_id", "candidate_model_version_id", "candidate_model_manifest", "candidate_model_manifest_digest", "model_comparison", "model_comparison_digest", "quality_plan_ref", "evaluation_plan_created_at"}
    result = {key: value for key, value in snapshot.items() if key in allowed}
    for key in ('media_recipe_digest', 'prepared_model_manifest_digest', 'material_id', 'material_version_id', 'input_image_manifest', 'input_image_manifest_digest'):
        if key in snapshot:
            result[key] = snapshot[key]
    environment = snapshot.get("environment", {})
    result["environment"] = {key: environment[key] for key in ("engine", "device_id", "digest", "versions") if key in environment}
    if 'dataset_split_ref' in snapshot:
        from .dataset_splits import portable_split_ref
        result['dataset_split_ref'] = portable_split_ref(snapshot['dataset_split_ref'])
    return result


class Delivery:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.export_grants = {}

    def artifact_for_path(self, attempt, relative_path):
        manifest = attempt.get("output_manifest_ref")
        if not isinstance(manifest, dict) or manifest.get("complete") is not True or manifest.get("digest") != digest({key: value for key, value in manifest.items() if key != "digest"}):
            raise Fault("ARTIFACT_CORRUPT", "原执行产物清单不完整或摘要不一致。", 409)
        entries = [item for item in manifest.get("artifacts", []) if isinstance(item, dict) and item.get("path") == relative_path]
        if len(entries) != 1:
            raise Fault("ARTIFACT_CORRUPT", "原执行清单未唯一声明此产物。", 409)
        artifact_id = "artifact-" + digest({"attempt_id": attempt["id"], "manifest": manifest["digest"], "path": relative_path})[:32]
        artifact = self.store.get("artifact", artifact_id)
        if artifact["project_id"] != attempt["project_id"] or artifact["attempt_id"] != attempt["id"]:
            raise Fault("PROJECT_MISMATCH", "产物来源与项目不符。", 403)
        if artifact["sha256"] != entries[0].get("sha256"):
            raise Fault("ARTIFACT_CORRUPT", "产物内容已偏离原执行清单。", 409)
        source = regular_path(artifact["storage_path"])
        if source.stat().st_size != artifact["size"] or file_hash(source) != artifact["sha256"]:
            raise Fault("ARTIFACT_CORRUPT", "已保存产物缺失或摘要不符。", 409)
        return artifact

    def save_adapter(self, attempt_id, payload, key):
        if self.store.get('attempt', attempt_id)['snapshot'].get('kind', 'text') != 'text':
            return self.service.media.save_adapter(attempt_id, payload, key)
        scope = f"save-adapter:{attempt_id}"
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if attempt["snapshot"]["operation"] != "train" or attempt["compute_outcome"] != "succeeded" or attempt["collection_state"] != "succeeded":
                raise Fault("ADAPTER_NOT_READY", "仅可保存已完成计算和产物收集的真实训练适配器。", 409)
            existing = [item for item in self.store.list("adapter", attempt["project_id"]) if item["source_attempt_id"] == attempt_id]
            if existing:
                response = self.service.public(existing[0])
                self.store.remember(scope, key, payload, response)
                return response
        prefix = 'mlx-adapter' if attempt.get('executor_type') == 'remote' else 'adapter'
        weights = self.artifact_for_path(attempt, prefix + '/adapters.safetensors')
        configuration = self.artifact_for_path(attempt, prefix + '/adapter_config.json')
        config = safe_json(Path(configuration["storage_path"]))
        snapshot = attempt["snapshot"]
        if config.get("base_input_manifest_digest") != snapshot["model_manifest_digest"] or config.get("training_recipe_digest") != snapshot["tokenization_recipe_digest"] or config.get("evaluation_plan_digest") != snapshot.get("evaluation_plan_digest"):
            raise Fault("ADAPTER_PROVENANCE_MISMATCH", "适配器缺少与本次基座及训练配方一致的来源记录。", 409)
        check_safetensors(Path(weights["storage_path"]))
        files = [("adapter_config.json", configuration), ("adapters.safetensors", weights)]
        manifest = [{"path": name, "size": item["size"], "sha256": item["sha256"]} for name, item in files]
        identity = digest(manifest)
        destination = self.service.root / "assets" / identity
        if destination.exists():
            verify_manifest(destination, manifest)
        else:
            temporary = Path(tempfile.mkdtemp(prefix=".adapter-", dir=self.service.root / "assets"))
            try:
                for name, artifact in files:
                    shutil.copyfile(artifact["storage_path"], temporary / name)
                    with (temporary / name).open("rb") as stream:
                        os.fsync(stream.fileno())
                    (temporary / name).chmod(0o400)
                verify_manifest(temporary, manifest)
                try:
                    os.rename(temporary, destination)
                except OSError:
                    if not destination.is_dir():
                        raise
                    verify_manifest(destination, manifest)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            existing = [item for item in self.store.list("adapter", attempt["project_id"]) if item["source_attempt_id"] == attempt_id]
            adapter = existing[0] if existing else self.service.resource("adapter", attempt["project_id"],
                name=payload.get("name") or "实验 LoRA 适配器", status="experimental", quality_status="not_evaluated",
                version_id=identifier("adapter-version"), revision=1, source_attempt_id=attempt_id,
                base_model_id=snapshot["model_id"], base_model_version_id=snapshot["model_version_id"], base_manifest_digest=snapshot["model_manifest_digest"],
                training_recipe_digest=snapshot["tokenization_recipe_digest"], manifest=manifest, manifest_digest=identity,
                total_bytes=sum(item["size"] for item in manifest), storage_path=str(destination), config=config,
                message="仅保存实验产物；尚未通过独立质量评测，不是可独立运行的完整模型。")
            self.store.put("adapter", adapter)
            response = self.service.public(adapter)
            self.store.remember(scope, key, payload, response)
            return response

    def export_grant(self, value):
        path = regular_path(value)
        if not path.is_dir():
            raise Fault("EXPORT_TARGET_INVALID", "请选择已有目录作为导出位置。")
        grant_id = identifier("export-grant")
        self.export_grants[grant_id] = path
        return {"path": str(path), "grant_id": grant_id, "expires": "session", "scope": "export_write"}

    def target(self, value, grant_id=None):
        roots = [regular_path(path) for path in self.service.settings.export_roots]
        if grant_id in self.export_grants:
            roots.append(self.export_grants[grant_id])
        target = authorized_path(value, roots)
        if not target.is_dir() or target == self.service.root or target.is_relative_to(self.service.root):
            raise Fault("EXPORT_TARGET_INVALID", "导出位置须为工作数据目录之外的已有目录。")
        return target

    def export_sources(self, project_id, object_type, object_id, include_base, work_revision_id=None):
        files, dependencies = [], []

        def add_file(path, source, sha256, size):
            files.append({"path": path, "source": str(source), "sha256": sha256, "size": size})

        def add_json(path, body):
            contents = encode(body) + "\n"
            files.append({"path": path, "contents": contents, "sha256": hashlib.sha256(contents.encode()).hexdigest(), "size": len(contents.encode())})

        def add_model(model, prefix="model"):
            for item in model["manifest"]:
                add_file(f"{prefix}/{item['path']}", Path(model["storage_path"]) / item["path"], item["sha256"], item["size"])

        def add_split_dependency(snapshot):
            if 'dataset_split_ref' not in snapshot:
                return None
            from .dataset_splits import portable_split_ref
            reference = portable_split_ref(snapshot['dataset_split_ref'])
            dependencies.append({"type": "dataset_split", "id": reference['id'],
                                 "split_digest": reference['split_digest'], "included": False,
                                 "description": "此报告或适配器只保留来源组身份；完整原件、两份子集与逐行证据需另行导出划分数据包。"})
            return reference

        item = self.store.get("attempt" if object_type == "report" else object_type, object_id)
        if item["project_id"] != project_id:
            raise Fault("PROJECT_MISMATCH", "导出对象属于其他项目。", 403)
        if object_type == "dataset-split":
            from .dataset_splits import verify_split_record
            reference = verify_split_record(item, lambda identity: self.store.get("dataset", identity))
            for role in ("source", "train", "validation"):
                dataset = self.store.get("dataset", item[f"{role}_dataset_id"])
                for part in dataset["manifest"]:
                    add_file(f"data/{role}/{part['path']}", Path(dataset["storage_path"]) / part["path"], part["sha256"], part["size"])
            for part in item["manifest"]:
                add_file("evidence/" + part["path"], Path(item["storage_path"]) / part["path"], part["sha256"], part["size"])
            metadata = {"id": item["id"], "name": item.get("name", "来源组划分数据包"),
                        "dataset_split_ref": reference, "counts": item["counts"],
                        "source_identifiers_included": True,
                        "scope": "原件、训练子集、留出验证子集与逐行划分证据；不包含模型或分词器。",
                        "validation_loss": "not_run", "semantic_near_duplicates": "not_checked"}
            dependencies.append({"type": "tokenizer_model", "id": item["model_id"],
                                 "manifest_digest": item["model_manifest_digest"], "included": False,
                                 "description": "重做分词检查需要原模型的固定分词器和配方；本包只包含数据及已保存检查证据。"})
        elif object_type == "model":
            add_model(item)
            metadata = {key: item[key] for key in ("id", "name", "version_id", "format", "model_config", "manifest_digest")}
            metadata.update({key: item[key] for key in ("status", "quality_status", "quality_candidate_id", "quality_scope", "quality_plan_ref", "source_model_id", "source_model_version_id", "source_manifest_digest", "source_attempt_id", "default_engine") if key in item})
        elif object_type == "adapter":
            for part in item["manifest"]:
                add_file("adapter/" + part["path"], Path(item["storage_path"]) / part["path"], part["sha256"], part["size"])
            base = self.store.get("model", item["base_model_id"])
            if base["project_id"] != project_id or base["manifest_digest"] != item["base_manifest_digest"]:
                raise Fault("ADAPTER_BASE_MISMATCH", "适配器的固定基座依赖不匹配。", 409)
            dependencies.append({"type": "base_model", "id": base["id"], "version_id": base["version_id"], "manifest_digest": base["manifest_digest"],
                                 "included": include_base, "description": "使用此适配器需要精确匹配的基座与" + ('Diffusers' if item.get('modality') == 'image' else 'MLX') + "环境。", "name": base["name"], "manifest": base["manifest"]})
            if include_base:
                add_model(base, "base_model")
            metadata = {key: item[key] for key in ("id", "name", "version_id", "status", "quality_status", "source_attempt_id", "base_model_id", "base_model_version_id", "base_manifest_digest", "training_recipe_digest", "manifest_digest", "config")}
            source_attempt = self.store.get('attempt', item['source_attempt_id'])
            reference = add_split_dependency(source_attempt['snapshot'])
            if reference is not None:
                metadata['dataset_split_ref'] = reference
        elif object_type == "work":
            selected = self.service.work_revisions.export_selection(object_id, work_revision_id, project_id)
            item, metadata = selected['work'], selected['metadata']
            files.extend(selected['files'])
            add_json('recipe.json', portable_recipe(selected['recipe']))
        else:
            if item["collection_state"] != "succeeded" or not item.get("output_manifest_ref"):
                raise Fault("REPORT_NOT_READY", "本次执行尚无已完整保存的报告产物。", 409)
            for part in item["output_manifest_ref"]["artifacts"]:
                if part.get("media_type") == "application/json":
                    artifact = self.artifact_for_path(item, part["path"])
                    add_file("report/" + part["path"], artifact["storage_path"], artifact["sha256"], artifact["size"])
            if not files:
                raise Fault("REPORT_NOT_READY", "本次执行没有可导出的JSON报告。", 409)
            add_json("recipe.json", portable_recipe(item["snapshot"]))
            add_split_dependency(item['snapshot'])
            if item["snapshot"].get("evaluation_plan_id"):
                evaluation_plan = self.store.get("evaluation-plan", item["snapshot"]["evaluation_plan_id"])
                self.service.evaluation.plan_fields(evaluation_plan)
                for kind in ("dataset", "criteria"):
                    source = Path(evaluation_plan[f"evaluation_{kind}_path"])
                    part = evaluation_plan[f"evaluation_{kind}_manifest"][0]
                    add_file("evaluation-plan/" + source.name, source, part["sha256"], part["size"])
            metadata = {"id": item["id"], "task_id": item["task_id"], "state": item["state"], "report_scope": "independent_text_evaluation" if item["snapshot"]["operation"] == "evaluate" else "execution_evidence", "quality_acceptance": "以冻结评测报告的逐项结果与准入阻断为准；成功导出不代表质量通过"}
        add_json("object.json", metadata)
        return item, files, dependencies

    def prepare_export(self, payload):
        self.store.get("project", payload["project_id"])
        target = self.target(payload["target_dir"], payload.get("grant_id"))
        item, files, dependencies = self.export_sources(payload["project_id"], payload["object_type"], payload["object_id"], payload.get("include_base", False), payload.get('work_revision_id'))
        blocking = []
        for entry in files:
            if "source" in entry:
                try:
                    source = regular_path(entry["source"])
                    if not source.is_file() or source.stat().st_size != entry["size"] or file_hash(source) != entry["sha256"]:
                        raise Fault("EXPORT_SOURCE_CHANGED", "导出源文件缺失或摘要不符。", 409)
                except (Fault, OSError):
                    blocking.append({"code": "EXPORT_SOURCE_CHANGED", "message": "源文件缺失或摘要不符。", "path": entry["path"]})
        total = sum(entry["size"] for entry in files)
        if shutil.disk_usage(target).free < total + 16 * 1024 * 1024:
            blocking.append({"code": "DISK_FULL", "message": "目标目录可用空间不足；请释放空间或选择其他位置。"})
        if total > 32 * 1024 * 1024 * 1024:
            blocking.append({"code": "EXPORT_TOO_LARGE", "message": "首期单次导出最多32 GiB。"})
        manifest = [{key: entry[key] for key in ("path", "size", "sha256")} for entry in files]
        with self.store.transaction():
            plan = self.service.resource("export-plan", payload["project_id"], object_type=payload["object_type"], object_id=payload["object_id"],
                object_name=item.get("name", "执行报告"), target_dir=str(target), grant_id=payload.get("grant_id"), include_base=payload.get("include_base", False),
                work_revision_id=payload.get('work_revision_id'),
                object_version_id=item.get("version_id", item.get("revision", item["id"])), files=manifest, source_files=files,
                dependencies=dependencies, total_bytes=total, file_count=len(files), can_export=not blocking, blocking=blocking)
            plan["plan_digest"] = digest({key: plan[key] for key in ("project_id", "object_type", "object_id", "object_version_id", "target_dir", "include_base", "files", "dependencies")})
            if payload["object_type"] == "dataset-split":
                plan["object_name"] = item.get("name", "来源组划分数据包")
                plan["disclosures"] = ["包含原始样本、来源标识、训练与验证子集及逐行划分证据；请确认接收方适合查看这些内容。"]
                plan["plan_digest"] = digest({key: plan[key] for key in ("project_id", "object_type", "object_id", "object_version_id", "target_dir", "include_base", "files", "dependencies", "disclosures")})
            self.store.put("export-plan", plan)
            return self.service.public(plan)

    def export_work_selection(self, record):
        """从冻结清单投影历史选择；不跟随当前修订，也不改写旧记录。"""
        unknown = {"selection_warning": "无法核实这条历史导出选择的作品版本，请返回作品重新选择后导出。"}
        try:
            plan = self.store.get("export-plan", record["plan_id"])
            fields = ("project_id", "object_type", "object_id", "object_version_id", "target_dir", "include_base", "files", "dependencies")
            if (plan["id"] != record["plan_id"] or any(plan[name] != record[name] for name in ("project_id", "object_type", "object_id"))
                    or plan["plan_digest"] != record["plan_digest"] or digest({name: plan[name] for name in fields}) != record["plan_digest"]):
                return unknown
            entries = [entry for entry in plan["files"] if entry["path"] == "object.json"]
            sources = [entry for entry in plan["source_files"] if entry["path"] == "object.json"]
            if len(entries) != 1 or len(sources) != 1:
                return unknown
            entry, source = entries[0], sources[0]
            contents = source["contents"]
            if (not isinstance(contents, str) or "source" in source or type(entry["size"]) is not int
                    or {name: source[name] for name in ("path", "size", "sha256")} != entry
                    or len(contents.encode()) != entry["size"] or hashlib.sha256(contents.encode()).hexdigest() != entry["sha256"]):
                return unknown
            metadata = json.loads(contents)
            # 只接受原导出器写入的规范 JSON，重复键等歧义不能变成版本身份。
            if encode(metadata) + "\n" != contents or metadata["id"] != record["object_id"]:
                return unknown
            selected = metadata["selected_version"]
            if (set(selected) != {"type", "id", "revision_id"} or not isinstance(selected["id"], str)
                    or not selected["id"] or selected["id"] != plan["object_version_id"]):
                return unknown
            revision_id = selected["revision_id"]
            if "work_revision_id" in plan and plan["work_revision_id"] != revision_id:
                return unknown
            if selected["type"] == "original":
                if revision_id is not None or metadata["revision"] is not None or selected["id"] != metadata["artifact_id"]:
                    return unknown
            elif selected["type"] == "revision":
                revision = metadata["revision"]
                if (not isinstance(revision_id, str) or not revision_id or selected["id"] != revision_id
                        or revision["id"] != revision_id or revision["work_id"] != record["object_id"]
                        or revision["project_id"] != record["project_id"] or revision["source_artifact_id"] != metadata["artifact_id"]
                        or revision["source_attempt_id"] != metadata["source_attempt"]):
                    return unknown
            else:
                return unknown
            return {"work_revision_id": revision_id}
        except (Fault, KeyError, TypeError, ValueError, UnicodeError):
            return unknown

    def export_record(self, record):
        attempt = self.store.get("attempt", record["attempt_id"])
        result = self.service.public(record)
        result.update(state=attempt["state"], state_version=attempt["state_version"], progress=attempt["progress"], allowed_actions=self.service.actions(attempt))
        if record["object_type"] == "work":
            result.pop("work_revision_id", None)
            result.pop("selection_warning", None)
            result.update(self.export_work_selection(record))
        return result

    def start_export(self, payload, key):
        with self.store.transaction():
            if previous := self.store.replay("export", key, payload):
                return self.export_record(self.store.get("export", previous["id"]))
            plan = self.store.get("export-plan", payload["plan_id"])
            if payload["plan_digest"] != plan["plan_digest"]:
                raise Fault("EXPORT_PLAN_CHANGED", "导出计划不匹配，请重新检查。", 409)
            if not plan["can_export"]:
                raise Fault("EXPORT_BLOCKED", "导出计划存在阻断项，请重新检查。", 409, blocking=plan["blocking"])
            if self.service.closed.is_set():
                raise Fault("SERVICE_STOPPING", "服务正在关闭。", 503)
            target = self.target(plan["target_dir"], plan.get("grant_id"))
            export_id = identifier("export")
            task = self.service.resource("task", plan["project_id"], name="导出 " + plan["object_name"], kind="export", operation="export", export_id=export_id, draft_revision=1, draft=None)
            attempt = self.service.resource("attempt", plan["project_id"], task_id=task["id"], export_id=export_id, executor_type="export",
                state="queued", state_version=1, connection_state="connected", stop_status="not_requested", compute_outcome="pending", collection_state="not_started", collection_version=0,
                output_manifest_ref=None, last_event_sequence=0, phase="queued", progress=0, output_text="", terminal_reason=None,
                snapshot={"schema_version": "1.1", "operation": "export", "plan_id": plan["id"], "plan_digest": plan["plan_digest"], "object_id": plan["object_id"], "object_type": plan["object_type"], "files": plan["files"], "submitted_at": now()})
            attempt["snapshot_digest"] = digest(attempt["snapshot"])
            record = {"id": export_id, "resource_type": "export", "project_id": plan["project_id"], "created_at": now(), "plan_id": plan["id"], "plan_digest": plan["plan_digest"],
                "task_id": task["id"], "attempt_id": attempt["id"], "object_type": plan["object_type"], "object_id": plan["object_id"], "object_name": plan["object_name"],
                "total_bytes": plan["total_bytes"], "file_count": plan["file_count"], "target_dir": str(target), "verified_path": None, "error": None,
                "final_path": str(target / f"ailab-{plan['object_type']}-{export_id}"), "partial_path": str(target / f".ailab-{export_id}.partial"), "independent_use": "not_verified"}
            self.store.put("task", task)
            self.store.put("attempt", attempt)
            self.store.put("export", record)
            self.store.event(attempt, "state_changed", {"state": "queued", "state_version": 1})
            response = self.export_record(record)
            self.store.remember("export", key, payload, response)
            thread = threading.Thread(target=self.run_export, args=(record["id"],), daemon=True, name=f"export-{record['id']}")
            self.service.threads.add(thread)
        thread.start()
        return response

    def check_cancel(self, attempt_id):
        attempt = self.store.get("attempt", attempt_id)
        if self.service.closed.is_set() or attempt["state"] in {"cancelling", "cancelled"}:
            raise ExportCancelled()

    @staticmethod
    def export_manifest(record, plan):
        return {"schema_version": "1.1", "export_id": record["id"], "plan_digest": plan["plan_digest"],
                "object_type": plan["object_type"], "object_id": plan["object_id"],
                "object_version_id": plan["object_version_id"], "files": plan["files"],
                "dependencies": plan["dependencies"], "complete": True, "independent_use": "not_verified"}

    def run_export(self, export_id):
        record = self.store.get("export", export_id)
        plan = self.store.get("export-plan", record["plan_id"])
        attempt_id = record["attempt_id"]
        temporary, final = Path(record["partial_path"]), Path(record["final_path"])
        try:
            self.check_cancel(attempt_id)
            with self.store.transaction():
                self.check_cancel(attempt_id)
                attempt = self.store.get("attempt", attempt_id)
                self.service.transition(attempt, "preparing", "正在复核导出来源、目标和空间。")
            target = self.target(plan["target_dir"], plan.get("grant_id"))
            if shutil.disk_usage(target).free < plan["total_bytes"] + 16 * 1024 * 1024:
                raise Fault("DISK_FULL", "导出空间不足，请选择其他位置。", 409)
            if temporary.exists() or final.exists():
                raise Fault("EXPORT_TARGET_EXISTS", "本次导出位置已存在，未覆盖任何文件。", 409)
            temporary.mkdir(mode=0o700)
            with self.store.transaction():
                self.check_cancel(attempt_id)
                attempt = self.store.get("attempt", attempt_id)
                self.service.transition(attempt, "running", "正在复制已选择的固定版本。")
            copied = 0
            for entry in plan["source_files"]:
                self.check_cancel(attempt_id)
                output = temporary / entry["path"]
                output.parent.mkdir(parents=True, exist_ok=True)
                checksum = hashlib.sha256()
                count = 0
                with output.open("xb") as destination:
                    if "contents" in entry:
                        block = entry["contents"].encode()
                        destination.write(block)
                        checksum.update(block)
                        count += len(block)
                    else:
                        source = regular_path(entry["source"])
                        if not source.is_file():
                            raise Fault("EXPORT_SOURCE_CHANGED", "源文件不再是常规文件。", 409)
                        with source.open("rb") as stream:
                            while block := stream.read(4 * 1024 * 1024):
                                self.check_cancel(attempt_id)
                                destination.write(block)
                                checksum.update(block)
                                count += len(block)
                    destination.flush()
                    os.fsync(destination.fileno())
                if count != entry["size"] or checksum.hexdigest() != entry["sha256"]:
                    raise Fault("EXPORT_SOURCE_CHANGED", "导出期间源文件内容发生变化，未发布完整包。", 409)
                copied += count
                with self.store.transaction():
                    attempt = self.store.get("attempt", attempt_id)
                    attempt["progress"] = copied / max(1, plan["total_bytes"])
                    self.store.event(attempt, "progress", {"copied_bytes": copied, "total_bytes": plan["total_bytes"], "progress": attempt["progress"]})
            self.check_cancel(attempt_id)
            manifest = self.export_manifest(record, plan)
            with (temporary / "manifest.json").open("x", encoding="utf-8") as stream:
                stream.write(encode(manifest) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.verify_export(temporary, record, plan)
            with self.store.transaction():
                self.check_cancel(attempt_id)
                if final.exists():
                    raise Fault("EXPORT_TARGET_EXISTS", "完整导出位置已存在，未覆盖。", 409)
                attempt = self.store.get("attempt", attempt_id)
                self.service.transition(attempt, "finalizing", "文件完整性已通过，正在发布本机导出目录。")
                os.rename(temporary, final)
                record.update(verified_path=str(final), finished_at=now(), error=None, manifest_digest=digest(manifest))
                self.store.put("export", record)
                attempt.update(compute_outcome="succeeded", collection_state="succeeded", progress=1, terminal_reason="EXPORT_COMPLETED")
                self.service.transition(attempt, "succeeded", "本机导出包已完整保存；独立加载或播放尚待验证。")
        except Exception as error:
            with self.store.transaction():
                attempt = self.store.get("attempt", attempt_id)
                if final.is_dir():
                    record.update(verified_path=None, error={"code": "EXPORT_REGISTRATION_PENDING", "message": "导出结果尚未确认，请核实原导出；不会重新运行模型。"})
                    self.store.put("export", record)
                    attempt.update(recovery_required=True, stop_status="unknown")
                    self.store.event(attempt, "warning", record["error"])
                    return
                cancelled = isinstance(error, ExportCancelled) or attempt["state"] == "cancelling" or self.service.closed.is_set()
                fault = error if isinstance(error, Fault) else Fault("EXPORT_CANCELLED" if cancelled else "EXPORT_INCOMPLETE", "导出已取消，未发布完整包。" if cancelled else "导出未完成，请检查存储后重新准备。", 409)
                record["error"] = {"code": fault.code, "message": fault.message}
                record["finished_at"] = now()
                self.store.put("export", record)
                attempt.update(compute_outcome="cancelled" if cancelled else "failed", collection_state="cancelled" if cancelled else "failed", terminal_reason=fault.code)
                if cancelled:
                    attempt["stop_status"] = "confirmed"
                self.service.transition(attempt, "cancelled" if cancelled else "failed", fault.message)
        finally:
            with self.store.lock:
                self.service.threads.discard(threading.current_thread())
            self.service._release_if_idle()

    def verify_export(self, directory, record, plan):
        regular_path(directory)
        expected = {entry["path"] for entry in plan["files"]} | {"manifest.json"}
        actual = set()
        pending = [directory]
        # 先核对全部目录项，再读取清单；不能遗漏目录链接、断链或特殊文件。
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    mode = entry.stat(follow_symlinks=False).st_mode
                    path = Path(entry.path)
                    if stat.S_ISDIR(mode):
                        pending.append(path)
                    elif stat.S_ISREG(mode):
                        actual.add(path.relative_to(directory).as_posix())
                    else:
                        raise Fault("EXPORT_INCOMPLETE", "导出包包含符号链接或非常规文件。", 409)
        if expected != actual:
            raise Fault("EXPORT_INCOMPLETE", "导出文件集合不完整或出现额外文件。", 409)
        manifest = safe_json(directory / "manifest.json")
        # 文件摘要不证明物件身份；逐项绑定冻结清单，并区分 JSON 布尔值与数字。
        try:
            matches_plan = encode(manifest) == encode(self.export_manifest(record, plan))
        except ValueError:
            matches_plan = False
        if not matches_plan:
            raise Fault("EXPORT_INCOMPLETE", "导出清单与冻结计划不一致。", 409)
        for entry in plan["files"]:
            path = regular_path(directory / entry["path"])
            if path.stat().st_size != entry["size"] or file_hash(path) != entry["sha256"]:
                raise Fault("EXPORT_INCOMPLETE", "导出文件摘要或大小不匹配。", 409)
        return manifest

    def reconcile_export(self, attempt_id, payload, key):
        with self.store.transaction():
            if previous := self.store.replay(f"reconcile:{attempt_id}", key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if attempt["state_version"] != payload["expected_state_version"]:
                raise Fault("REVISION_CONFLICT", "导出状态已更新。", 409, current_state_version=attempt["state_version"])
            record = self.store.get("export", attempt["export_id"])
            plan = self.store.get("export-plan", record["plan_id"])
        final = Path(record["final_path"])
        completed = False
        if final.is_dir() and attempt["state"] != "cancelling":
            try:
                self.verify_export(final, record, plan)
                completed = True
            except (Fault, OSError):
                pass
        with self.store.transaction():
            latest = self.store.get("attempt", attempt_id)
            if latest["state_version"] != payload["expected_state_version"]:
                raise Fault("REVISION_CONFLICT", "核实期间导出状态已更新。", 409, current_state_version=latest["state_version"])
            latest.update(recovery_required=False, connection_state="connected", stop_status="confirmed", compute_outcome="succeeded" if completed else "failed", collection_state="succeeded" if completed else "failed", terminal_reason="EXPORT_RECOVERED" if completed else "EXPORT_INTERRUPTED")
            if completed:
                record.update(verified_path=str(final), error=None, finished_at=now())
            else:
                record["error"] = {"code": "EXPORT_INTERRUPTED", "message": "导出曾中断且没有通过校验的完整包，可重新准备导出；未重新运行模型。"}
            self.store.put("export", record)
            self.service.transition(latest, "succeeded" if completed else "failed", "已核实原导出文件，未重新运行模型。")
            response = self.service.public(latest)
            self.store.remember(f"reconcile:{attempt_id}", key, payload, response)
            return response
