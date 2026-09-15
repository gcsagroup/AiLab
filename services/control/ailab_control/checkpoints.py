"""训练安全点控制；所有权重摘要检查在数据库事务之外完成。"""

import json
import math
import os
from pathlib import Path
import re

from .assets import check_safetensors, file_hash, regular_path, verify_manifest
from .storage import Fault, digest, encode, identifier, now

TERMINAL = {"succeeded", "failed", "cancelled"}
HEX = re.compile(r"[0-9a-f]{64}")


def compatibility(snapshot, environment=None):
    environment = environment or snapshot.get("environment", {})
    facts = environment.get("versions", {})
    sources = facts.get("sources", environment.get("identity", {}).get("adapter_sources", {}))
    versions = facts.get("dependencies", {})
    result = {name: snapshot.get(name) for name in ("model_manifest_digest", "dataset_manifest_digest", "tokenization_recipe_digest", "evaluation_plan_digest")}
    result.update(runtime=snapshot["runtime"], versions={name: versions.get(name) for name in ("mlx", "mlx-lm")}, device="apple-gpu")
    for field, basename, alias in (("worker_source_sha256", "mlx_worker.py", "worker"), ("checkpoint_source_sha256", "checkpoint.py", "checkpoint"), ("recipe_source_sha256", "recipe.py", "recipe")):
        values = {value for name, value in sources.items() if Path(name).name == basename or name == alias}
        if len(values) != 1 or not HEX.fullmatch(next(iter(values), "")):
            raise Fault("CHECKPOINT_NOT_SUPPORTED", "本次执行器缺少可核验的检查点协议来源，不能安全暂停。", 409)
        result[field] = values.pop()
    if not all(isinstance(value, str) and value for value in result["versions"].values()):
        raise Fault("CHECKPOINT_NOT_SUPPORTED", "本次执行器缺少固定 MLX 版本，不能安全暂停。", 409)
    return result


class Checkpoints:
    def __init__(self, service):
        self.service, self.store, self.root = service, service.store, service.root

    def supported(self, attempt):
        if attempt.get("snapshot", {}).get("operation") != "train":
            return False
        try:
            compatibility(attempt["snapshot"])
            return True
        except Fault:
            return False

    def verify_lineage(self, source, expected_digest):
        from .backup import remap_reference_paths
        current, current_digest = source["snapshot"], source.get("snapshot_digest")
        if current_digest != digest(current):
            raise ValueError("当前来源快照摘要不符")
        restoration = source.get("restoration")
        current_root = self.root
        for _ in range(32):
            if current_digest == expected_digest:
                return
            if not isinstance(restoration, dict) or restoration.get("historical_artifacts_unchanged") is not True or not HEX.fullmatch(restoration.get("backup_manifest_digest", "")):
                raise ValueError("检查点缺少完整恢复来源")
            original, mapping = restoration.get("original_snapshot"), restoration.get("path_mapping")
            original_digest = restoration.get("original_snapshot_digest")
            if not isinstance(original, dict) or digest(original) != original_digest or not isinstance(mapping, dict) or len(mapping) != 1:
                raise ValueError("原快照或路径映射摘要不符")
            old_value, new_value = next(iter(mapping.items()))
            old_root, new_root = Path(old_value), Path(new_value)
            if not old_root.is_absolute() or not new_root.is_absolute() or ".." in old_root.parts or ".." in new_root.parts or old_root == new_root or new_root != current_root:
                raise ValueError("恢复目录映射与本库不符")
            if remap_reference_paths(original, old_root, new_root) != current:
                raise ValueError("恢复快照包含路径迁移以外的变化")
            current, current_digest, current_root = original, original_digest, old_root
            restoration = restoration.get("previous_restoration")
        raise ValueError("恢复来源链过长")

    def verify(self, source, path, expected_digest):
        run_dir = self.root / "runs" / source["id"]
        path = regular_path(path)
        relative = path.relative_to(run_dir) if path.is_relative_to(run_dir) else Path("invalid")
        if len(relative.parts) != 3 or relative.parts[0] != "checkpoints" or relative.name != "manifest.json" or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise Fault("CHECKPOINT_CORRUPT", "检查点清单路径或大小不符合本次运行范围。", 409)
        try:
            manifest = json.loads(path.read_text())
            if not isinstance(manifest, dict):
                raise ValueError("清单类型错误")
            actual = digest({key: value for key, value in manifest.items() if key != "digest"})
            if manifest.get("schema_version") != "mlx-training-checkpoint-v1" or manifest.get("complete") is not True or not HEX.fullmatch(expected_digest or "") or manifest.get("digest") != expected_digest or actual != expected_digest:
                raise ValueError("清单未闭合")
            if manifest.get("source_attempt_id") != source["id"]:
                raise ValueError("来源运行快照不符")
            self.verify_lineage(source, manifest.get("source_snapshot_digest"))
            if manifest.get("compatibility") != compatibility(source["snapshot"]):
                raise ValueError("模型、数据、配方、参数或执行器版本不符")
            step, total, count = manifest.get("step"), manifest.get("total_steps"), manifest.get("sample_count")
            if type(step) is not int or type(total) is not int or not 0 <= step <= total <= 200 or total != source["snapshot"]["runtime"]["steps"] or type(count) is not int or count < 1 or type(manifest.get("next_sample_index")) is not int or manifest["next_sample_index"] != step % count or not isinstance(manifest.get("losses"), list) or len(manifest["losses"]) != step or any(type(value) not in (int, float) or not math.isfinite(value) for value in manifest["losses"]) or not isinstance(manifest.get("tree"), dict):
                raise ValueError("安全步、数据位置或完整状态不符")
            files = manifest.get("files")
            if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict) or files[0].get("path") != "state.safetensors" or type(files[0].get("size")) is not int or not 0 < files[0]["size"] <= 256 * 1024 * 1024 or not HEX.fullmatch(files[0].get("sha256", "")):
                raise ValueError("完整状态文件清单不符")
            verify_manifest(path.parent, files + [{"path": path.name, "size": path.stat().st_size, "sha256": file_hash(path)}])
            check_safetensors(path.parent / "state.safetensors")
            if set(item.name for item in path.parent.iterdir()) != {"manifest.json", "state.safetensors"}:
                raise ValueError("检查点包含未声明文件")
        except (ValueError, TypeError, KeyError, OSError) as error:
            raise Fault("CHECKPOINT_CORRUPT", "检查点完整性或来源检查失败。", 409) from error
        return manifest

    def command(self, attempt_id, payload, key, action):
        scope = f"{action}:{attempt_id}"
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if payload["expected_state_version"] != attempt["state_version"]:
                raise Fault("REVISION_CONFLICT", "运行状态已更新，请刷新后重试。", 409, current_state_version=attempt["state_version"])
            if not self.supported(attempt) or attempt.get("recovery_required") or attempt_id not in self.service.processes:
                raise Fault("CONTROL_NOT_SUPPORTED", "此运行没有可归属的训练检查点协议。", 409)
            required = "running" if action == "pause" else "paused"
            if attempt["state"] != required:
                raise Fault("CONTROL_NOT_SUPPORTED", "当前状态不支持此检查点控制。", 409)
            checkpoint = self.store.get("checkpoint", attempt["checkpoint_id"]) if action == "resume" and attempt.get("checkpoint_id") else None
            if action == "resume" and checkpoint is None:
                raise Fault("CHECKPOINT_NOT_READY", "尚无完整核验的检查点，不能继续。", 409)
            captured = attempt
        if checkpoint:
            self.verify(captured, Path(checkpoint["storage_path"]), checkpoint["manifest_digest"])
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if attempt["state_version"] != captured["state_version"] or attempt["state"] != required:
                raise Fault("REVISION_CONFLICT", "检查期间运行状态已更新。", 409)
            sequence = attempt.get("training_control_sequence", 0) + 1
            command = self.service.resource("training-control", attempt["project_id"], attempt_id=attempt_id, action=action, sequence=sequence, result="accepted")
            command["id"] = identifier("command")
            command["command_id"] = command["id"]
            if checkpoint:
                command["checkpoint_digest"] = checkpoint["manifest_digest"]
            attempt.update(training_control_sequence=sequence, last_control=command)
            self.store.put("training-control", command)
            self.service.transition(attempt, "pausing" if action == "pause" else "resuming", "正在等待训练安全点确认。")
            self.store.event(attempt, "control_result", command)
            response = {**self.service.public(attempt), **{name: command[name] for name in ("command_id", "action", "result", "sequence")}}
            self.store.remember(scope, key, payload, response)
        try:
            directory = self.root / "runs" / attempt_id / "control" / "commands"
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            regular_path(directory)
            body = {name: command[name] for name in ("command_id", "sequence", "attempt_id", "action")}
            if checkpoint:
                body["checkpoint_digest"] = checkpoint["manifest_digest"]
            temporary = directory / (command["id"] + ".tmp")
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(encode(body))
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temporary, directory / (command["id"] + ".json"))
        except (OSError, Fault):
            self.handle_event(attempt_id, {"type": "control_result", "command_id": command["id"], "action": action, "result": "failed", "continuing": action == "pause", "code": "CONTROL_WRITE_FAILED", "message": "训练控制文件未能发布。"})
        return response

    def handle_event(self, attempt_id, event):
        with self.store.lock:
            captured = self.store.get("attempt", attempt_id)
            pending = captured.get("last_control", {})
            try:
                issued = self.store.get("training-control", event.get("command_id"))
            except Fault:
                issued = {}
            known = issued.get("attempt_id") == attempt_id and issued.get("action") == event.get("action") and issued.get("result") == "accepted"
            matches = known and event.get("command_id") == pending.get("command_id") and event.get("action") == pending.get("action") and pending.get("result") == "accepted" and captured["state"] == ("pausing" if event.get("action") == "pause" else "resuming")
        checkpoint = None
        verification_error = None
        if known and event.get("action") == "pause" and event.get("result") == "confirmed":
            try:
                evidence = event["checkpoint"]
                relative = Path(evidence["relative_path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise Fault("CHECKPOINT_CORRUPT", "检查点回执路径越界。", 409)
                path = self.root / "runs" / attempt_id / relative
                manifest = self.verify(captured, path, evidence["manifest_digest"])
                if evidence.get("step") != manifest["step"] or evidence.get("total_steps") != manifest["total_steps"]:
                    raise Fault("CHECKPOINT_CORRUPT", "检查点回执与清单的步数不一致。", 409)
                checkpoint = self.service.resource("checkpoint", captured["project_id"], source_attempt_id=attempt_id, source_snapshot_digest=captured["snapshot_digest"], storage_path=str(path), manifest_digest=manifest["digest"], manifest=manifest, step=manifest["step"], total_steps=manifest["total_steps"], status="verified")
                checkpoint["id"] = "checkpoint-" + digest({"attempt_id": attempt_id, "manifest_digest": manifest["digest"]})[:32]
            except (Fault, KeyError, TypeError, ValueError) as error:
                verification_error = error
        with self.store.transaction():
            attempt = self.store.get("attempt", attempt_id)
            if not matches or attempt["state_version"] != captured["state_version"] or attempt.get("last_control", {}).get("command_id") != event.get("command_id"):
                if checkpoint and attempt["snapshot_digest"] == captured["snapshot_digest"] and attempt["snapshot"] == captured["snapshot"]:
                    self.store.put("checkpoint", checkpoint)
                    issued.update(result="confirmed", checkpoint_id=checkpoint["id"], checkpoint_digest=checkpoint["manifest_digest"], completed_at=now(), late=True)
                    self.store.put("training-control", issued)
                    self.store.event(attempt, "checkpoint_ready", {"checkpoint_id": checkpoint["id"], "step": checkpoint["step"], "manifest_digest": checkpoint["manifest_digest"], "late": True, "message": "已登记迟到但完整的检查点；运行状态保持原样。"})
                else:
                    self.store.event(attempt, "warning", {"code": "CHECKPOINT_CORRUPT" if verification_error else "STALE_CONTROL_RESULT", "message": "迟到检查点未通过核验。" if verification_error else "收到过期的训练控制回执，运行状态未回退。", "command_id": event.get("command_id")})
                return
            command = attempt["last_control"]
            action = command["action"]
            if verification_error:
                command.update(result="failed", code="CHECKPOINT_CORRUPT", message="执行器已报告暂停，但检查点未通过完整核验；可取消本次运行。")
                attempt["phase"] = "pause_verification_failed"
            elif action == "pause" and event.get("result") == "confirmed" and checkpoint:
                self.store.put("checkpoint", checkpoint)
                attempt["checkpoint_id"] = checkpoint["id"]
                command.update(result="confirmed", checkpoint_id=checkpoint["id"], checkpoint_digest=checkpoint["manifest_digest"])
                self.service.transition(attempt, "paused", "完整检查点已核验，训练停在安全步。")
            elif action == "resume" and event.get("result") == "confirmed" and event.get("checkpoint_digest") == command.get("checkpoint_digest"):
                command["result"] = "confirmed"
                self.service.transition(attempt, "running", "执行器已重新加载完整状态并继续训练。")
            elif event.get("result") == "failed":
                command.update(result="failed", code=str(event.get("code", "CONTROL_FAILED"))[:100], message=str(event.get("message", "训练控制未完成。"))[:1000])
                if action == "resume" or event.get("continuing") is True:
                    self.service.transition(attempt, "paused" if action == "resume" else "running", command["message"])
            else:
                command.update(result="failed", code="INVALID_CONTROL_RESULT", message="训练控制回执不完整，未确认状态变化。")
            command["completed_at"] = now()
            attempt["last_control"] = command
            self.store.put("training-control", command)
            self.store.event(attempt, "control_result", command)

    def fields(self, task, environment):
        checkpoint = self.store.get("checkpoint", task["draft"]["checkpoint_id"])
        if checkpoint["project_id"] != task["project_id"]:
            raise Fault("PROJECT_MISMATCH", "检查点属于其它项目。", 403)
        source = self.store.get("attempt", checkpoint["source_attempt_id"])
        manifest = self.verify(source, Path(checkpoint["storage_path"]), checkpoint["manifest_digest"])
        original = source["snapshot"]
        if task["operation"] != "train" or any(task["draft"].get(name) != original.get(name) for name in ("model_id", "dataset_id", "evaluation_plan_id", "runtime", "input")) or task["draft"].get("adapter_id"):
            raise Fault("CHECKPOINT_CONFIG_CHANGED", "从检查点恢复必须保持原模型、数据、评测计划和训练参数。", 409)
        if source["state"] not in TERMINAL or source["id"] in self.service.processes:
            raise Fault("CHECKPOINT_SOURCE_ACTIVE", "原运行仍未确认退出，请在原运行继续或先取消并确认停止。", 409)
        if manifest["compatibility"] != compatibility(original, environment):
            raise Fault("CHECKPOINT_ENVIRONMENT_CHANGED", "当前执行器或依赖与检查点不兼容。", 409)
        fields = {"checkpoint_id": checkpoint["id"], "checkpoint_ref": {"path": checkpoint["storage_path"], "manifest_digest": checkpoint["manifest_digest"], "source_attempt_id": source["id"]}}
        if original.get('dataset_split_ref'):
            from .dataset_splits import portable_split_ref
            original_ref = portable_split_ref(original['dataset_split_ref'])
            dataset = self.store.get('dataset', original['dataset_id'])
            model = self.store.get('model', original['model_id'])
            current = self.service.dataset_splits.training_fields(task, dataset, model).get('dataset_split_ref')
            if original_ref != current:
                raise Fault('CHECKPOINT_CONFIG_CHANGED', '来源组划分证明已变化，不能恢复此检查点。', 409)
            fields['dataset_split_ref'] = original_ref
        return fields

    def new_task(self, checkpoint_id, payload, key):
        checkpoint = self.store.get("checkpoint", checkpoint_id)
        source = self.store.get("attempt", checkpoint["source_attempt_id"])
        original = source["snapshot"]
        draft = {name: original.get(name) for name in ("kind", "operation", "model_id", "dataset_id", "adapter_id", "evaluation_plan_id", "runtime", "input")}
        draft["checkpoint_id"] = checkpoint_id
        task = self.service.resource("task", checkpoint["project_id"], name=payload.get("name") or f"从第 {checkpoint['step']} 步恢复", kind="text", operation="train", draft_revision=1, draft=draft)
        scope = f"resume-task:{checkpoint_id}"
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
        self.fields(task, self.service.environment(refresh=True))
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.store.get("attempt", source["id"]) != source or self.store.get("checkpoint", checkpoint_id) != checkpoint:
                raise Fault("REVISION_CONFLICT", "恢复检查期间来源状态已变化。", 409)
            self.store.put("task", task)
            self.store.remember(scope, key, payload, task)
        return task
