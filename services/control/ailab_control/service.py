"""业务合同、不可变快照与真实进程调度。"""

import json
import fcntl
import os
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .assets import authorized_path, copy_asset, dataset_report, file_hash, model_manifest, regular_path, verify_manifest
from .launcher import SOURCE as LAUNCHER_SOURCE
from .probe_observations import ProbeFailure, ProbeObservations
from .model_profiles import model_profile
from .storage import Fault, Store, digest, encode, identifier, now
from .ui_context import UIContextPatch, empty_context, validate_context

TERMINAL = {"succeeded", "failed", "cancelled"}
INLINE_TEXT_LIMIT = 16000
DEFAULT_RUNTIME = {"engine": "mlx", "device_id": "apple-gpu", "max_tokens": 128, "temperature": 0.0, "top_p": 1.0, "seed": 0}
TRAIN_RUNTIME = {"engine": "mlx", "device_id": "apple-gpu", "seed": 0, "training_type": "sft", "update_method": "lora", "recipe_id": "qwen25-assistant-only-v1", "steps": 4, "learning_rate": 0.0001, "max_seq_length": 512, "lora_rank": 4, "lora_alpha": 8.0, "num_layers": 2, "batch_size": 1, "gradient_accumulation": 1, "optimizer": "adamw", "weight_decay": 0.0, "lora_dropout": 0.0}


def publish_run_record(path, value):
    """完整写入并同步后才公开就绪文件，且不覆盖已有授权或证据。"""
    temporary = path.with_name(path.name + ".tmp")
    owned = False
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            owned = True
            stream.write(encode(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if owned:
            temporary.unlink(missing_ok=True)


@dataclass
class Settings:
    data_dir: Path
    token: str
    import_roots: list[Path] = field(default_factory=list)
    worker_python: Path | None = None
    worker_script: Path | None = None
    allowed_origins: list[str] = field(default_factory=list)
    parent_pid: int | None = None
    preflight_script: Path | None = None
    bundled_worker: Path | None = None
    export_roots: list[Path] = field(default_factory=list)
    host_token: str | None = None
    media_python: Path | None = None
    audio_python: Path | None = None
    media_worker_script: Path | None = None
    media_preflight_script: Path | None = None
    audio_worker_script: Path | None = None
    audio_preflight_script: Path | None = None
    bundled_media_worker: Path | None = None
    bundled_audio_worker: Path | None = None
    market_providers: list[tuple[str, str]] = field(default_factory=list)


class Service:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        descriptor = os.open(self.root / "control.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.instance_lock = os.fdopen(descriptor, "w")
        try:
            fcntl.flock(self.instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.instance_lock.close()
            raise Fault("DATA_DIRECTORY_BUSY", "此数据目录已有控制服务运行，请使用现有实例。", 409) from None
        self.shutdown_complete = False
        self._close_lock = threading.Lock()
        self._shutdown_ready = False
        for name in ("assets", "runs", "backups"):
            (self.root / name).mkdir(exist_ok=True, mode=0o700)
        try:
            self.store = Store(self.root / "control.sqlite3")
        except BaseException:
            self.instance_lock.close()
            raise
        self.active_writes = 0
        self.activation_pending = False
        self.activation_deadline = 0
        self.maintenance_pending = False
        saved = self.store.db.execute("SELECT body FROM app_settings WHERE id=1").fetchone()
        self.user_settings = json.loads(saved[0]) if saved else {"revision": 1, "worker_python": None}
        if not settings.worker_python and self.user_settings["worker_python"]:
            settings.worker_python = Path(self.user_settings["worker_python"])
        if not settings.preflight_script and settings.worker_script:
            settings.preflight_script = settings.worker_script.parent.parent / "adapters" / "mlx_text" / "preflight.py"
        for prefix in ('media', 'audio'):
            name = prefix + '_python'
            if not getattr(settings, name) and self.user_settings.get(name):
                setattr(settings, name, Path(self.user_settings[name]))
        if settings.worker_script:
            source_root = settings.worker_script.parent.parent
            defaults = {'media_worker_script': source_root / 'workers/media_worker.py', 'media_preflight_script': source_root / 'adapters/media/preflight.py', 'audio_worker_script': source_root / 'workers/tts_worker.py', 'audio_preflight_script': source_root / 'workers/tts_worker.py'}
            for name, path in defaults.items():
                if not getattr(settings, name):
                    setattr(settings, name, path)
        self.grants = {}
        self.processes = {}
        self.threads = set()
        self.closed = threading.Event()
        self.environment_cache = None
        self.environment_lock = threading.Lock()
        self.probe_observations = ProbeObservations()
        self._recover()
        from .delivery import Delivery
        self.delivery = Delivery(self)
        from .evaluation import Evaluation
        self.evaluation = Evaluation(self)
        from .backup import Backup
        self.backup_manager = Backup(self)
        from .conversion import Conversion
        self.conversion = Conversion(self)
        from .model_lab import ModelLab
        self.model_lab = ModelLab(self)
        from .format_conversions import FormatConversions
        self.format_conversions = FormatConversions(self)
        from .checkpoints import Checkpoints
        self.checkpoints = Checkpoints(self)
        from .cleanup import Cleanup
        self.cleanup = Cleanup(self)
        from .media import Media
        self.media = Media(self)
        from .workflows import Workflows
        self.workflows = Workflows(self)
        from .work_revisions import WorkRevisions
        self.work_revisions = WorkRevisions(self)
        from .work_recipes import WorkRecipes
        self.work_recipes = WorkRecipes(self)
        from .ai_assistance import AIAssistance
        self.ai = AIAssistance(self)
        from .market import Market, LoopbackProvider
        self.market = Market(self, [LoopbackProvider(provider, origin) for provider, origin in settings.market_providers])
        from .model_downloads import ModelDownloads
        self.model_downloads = ModelDownloads(self)
        from .diagnostics import Diagnostics
        self.diagnostics = Diagnostics(self)
        from .execution_targets import ExecutionTargets
        self.execution_targets = ExecutionTargets(self)
        from .remote_execution import RemoteExecution
        self.remote_execution = RemoteExecution(self)
        from .dataset_splits import DatasetSplits
        self.dataset_splits = DatasetSplits(self)

    def _recover(self):
        with self.store.transaction():
            pending_collections = {}
            for collection in self.store.list("collection"):
                if collection["state"] == "collecting":
                    pending_collections.setdefault(collection["attempt_id"], []).append(collection)
            for attempt in self.store.list("attempt"):
                if attempt["state"] not in TERMINAL:
                    attempt["connection_state"] = "disconnected"
                    attempt["stop_status"] = "unknown"
                    attempt["state_version"] += 1
                    attempt["recovery_required"] = True
                    if attempt.get("executor_type") == "remote":
                        attempt["last_connection_error"] = "CONTROL_INTERRUPTED"
                    self.store.event(attempt, "warning", {"code": "CONTROL_RESULT_UNKNOWN", "message": "控制服务曾中断，原执行未重新启动；停止结果待核实。"})
                elif (attempt["state"] in {"failed", "cancelled"}
                      and attempt.get("compute_outcome") == "succeeded"
                      and attempt.get("collection_state") == "collecting"
                      and attempt.get("output_manifest_ref")):
                    # 已取得资料目录独占锁，旧控制进程的本地补收不可能继续。
                    # 补收引用已终结的计算；只释放收集状态，不改写原终态或重新执行。
                    pending = pending_collections.get(attempt["id"], [])
                    if (len(pending) == 1 and pending[0]["project_id"] == attempt["project_id"]
                            and pending[0]["manifest_digest"] == attempt["output_manifest_ref"]["digest"]):
                        collection = pending[0]
                        error = {"code": "COLLECTION_INTERRUPTED", "message": "控制服务在产物补收期间中断，计算结果保留，可重新补收。"}
                        collection.update(state="failed", error=error, finished_at=now())
                        self.store.put("collection", collection)
                        attempt.update(collection_state="failed", collection_version=attempt["collection_version"] + 1)
                        self.store.event(attempt, "collection_changed", {"collection_id": collection["id"], "state": "failed", "error": error})

    def close(self):
        # 串行处理生命周期退出和显式关闭；后台收尾不取此锁，避免 join 互相等待。
        with self._close_lock:
            with self.store.lock:
                if self.shutdown_complete:
                    return
                self._shutdown_ready = False
                self.closed.set()
            if hasattr(self, 'dataset_splits'):
                self.dataset_splits.close()
            with self.store.lock:
                processes = list(self.processes.items())
            for attempt_id, process in processes:
                with self.store.transaction():
                    attempt = self.store.get("attempt", attempt_id)
                    if attempt["state"] not in TERMINAL:
                        attempt["stop_status"] = "pending"
                        self.transition(attempt, "cancelling", "宿主退出，正在停止本次运行。")
                self._signal(process, signal.SIGTERM)
            deadline = time.monotonic() + 5
            for _, process in processes:
                try:
                    process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    self._signal(process, signal.SIGKILL)
                    process.wait(timeout=2)
                while self.group_present(process.pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
                if self.group_present(process.pid):
                    self._signal(process, signal.SIGKILL)
            for thread in list(self.threads):
                if thread.ident is not None:
                    thread.join(timeout=3)
            with self.store.lock:
                # 主体失败时保持 False，末个后台线程不能越过未完成的关闭流程。
                self._shutdown_ready = True
                self._release_if_idle()

    def _release_if_idle(self):
        with self.store.lock:
            if not self.closed.is_set() or not self._shutdown_ready or self.shutdown_complete:
                return
            alive_groups = any(process.poll() is None or self.group_present(process.pid) for process in self.processes.values())
            split_alive = hasattr(self, 'dataset_splits') and self.dataset_splits.has_live_processes()
            if not self.threads and not alive_groups and not split_alive:
                # 保持实例锁直到数据库成功关闭，让 WAL 有机会完成正常清理。
                self.store.close()
                self.instance_lock.close()
                self.shutdown_complete = True

    def public(self, value):
        if value.get('resource_type') in {'dataset-split', 'dataset-split-plan'}:
            return self.dataset_splits.public(value)
        result = {key: item for key, item in value.items() if key not in {"storage_path", "manifest", "source_path", "grant_id", "source_files", "final_path", "evaluation_dataset_path", "evaluation_criteria_path"}}
        if value.get('resource_type') == 'work':
            result['favorite'] = value.get('favorite', False)
        if value.get("resource_type") == "artifact":
            permitted = value.get("relative_path") == "result.txt" and value.get("media_type") == "text/plain"
            result["text"] = value.get("text", "")[:INLINE_TEXT_LIMIT] if permitted and isinstance(value.get("text"), str) else None
            if permitted and isinstance(value.get("text"), str):
                result["text_truncated"] = value.get("text_truncated", False) or len(value["text"]) > INLINE_TEXT_LIMIT
        elif isinstance(value.get("text"), str):
            result["text"] = value["text"][:INLINE_TEXT_LIMIT]
            result["text_truncated"] = value.get("text_truncated", False) or len(value["text"]) > INLINE_TEXT_LIMIT
        if value.get("resource_type") == "attempt":
            permitted = value.get("snapshot", {}).get("operation") == "generate"
            original_text = value.get("output_text", "") if permitted else ""
            result["output_text"] = original_text[:INLINE_TEXT_LIMIT]
            result["output_text_truncated"] = value.get("output_text_truncated", False) or len(original_text) > INLINE_TEXT_LIMIT
            result["allowed_actions"] = self.actions(value)
            result["artifacts"] = [self.public(item) for item in self.store.list("artifact", value["project_id"]) if item["attempt_id"] == value["id"]]
            # 从持久登记恢复保存状态；不能依赖前端分页列表或上次页面内存。
            artifact_ids = {item["id"] for item in result["artifacts"]}
            result["saved_work_artifact_ids"] = sorted({item["artifact_id"] for item in self.store.list("work", value["project_id"])
                                                       if item.get("attempt_id") == value["id"] and item.get("artifact_id") in artifact_ids})
        return result

    def actions(self, attempt):
        if attempt.get('executor_type') == 'remote':
            if attempt['state'] in TERMINAL:
                return ['collect'] if attempt['compute_outcome'] == 'succeeded' and attempt['collection_state'] != 'succeeded' and attempt.get('output_manifest_ref') else []
            return ['reconcile', 'cancel'] if attempt.get('recovery_required') else ['reconcile'] if attempt['state'] == 'cancelling' else ['cancel']
        if attempt["state"] in TERMINAL:
            return ["collect"] if attempt["compute_outcome"] == "succeeded" and attempt["collection_state"] != "succeeded" and attempt.get("output_manifest_ref") else []
        if attempt.get("recovery_required"):
            return ["reconcile"]
        if attempt.get("executor_type") == "export" and not any(thread.name == f"export-{attempt['export_id']}" for thread in self.threads):
            return ["reconcile"]
        if attempt["state"] == "cancelling":
            return ["force-stop"] if attempt["id"] in self.processes else []
        if self.checkpoints.supported(attempt):
            if attempt["state"] == "running":
                return ["pause", "cancel"]
            if attempt["state"] == "paused" and attempt.get("checkpoint_id"):
                return ["resume", "cancel"]
        return ["cancel"]

    def resource(self, resource_type, project_id, **fields):
        self.store.get("project", project_id)
        return {"id": identifier(resource_type), "resource_type": resource_type, "project_id": project_id, "created_at": now(), **fields}

    def project(self, payload):
        with self.store.transaction():
            result = {"id": identifier("project"), "name": payload["name"], "revision": 1, "created_at": now(), "archived_at": None}
            self.store.put("project", result)
            return result

    def execution_default(self, project_id, payload=None):
        with self.store.transaction():
            project = self.store.get('project', project_id)
            if payload is not None:
                if project['revision'] != payload['expected_revision']:
                    raise Fault('REVISION_CONFLICT', '项目已更新，请刷新后再保存默认位置。', 409, current_revision=project['revision'])
                if payload['execution_target_id']:
                    target = self.store.get('execution-target', payload['execution_target_id'])
                    if target['project_id'] != project_id:
                        raise Fault('PROJECT_MISMATCH', '默认执行目标必须属于当前项目。', 403)
                project.update(default_execution_target_id=payload['execution_target_id'], revision=project['revision'] + 1, updated_at=now())
                self.store.put('project', project)
            return {'project_id': project_id, 'execution_target_id': project.get('default_execution_target_id'), 'revision': project['revision']}

    def grant(self, path):
        selected = regular_path(path)
        if not (selected.is_file() or selected.is_dir()):
            raise Fault("PATH_NOT_ALLOWED", "请选择常规文件或目录。")
        grant_id = identifier("grant")
        self.grants[grant_id] = selected
        return {"grant_id": grant_id, "path": str(selected), "expires": "session"}

    def import_plan(self, kind, payload):
        self.store.get("project", payload["project_id"])
        roots = [regular_path(p) for p in self.settings.import_roots]
        if payload.get("grant_id"):
            grant = self.grants.get(payload["grant_id"])
            if grant is None:
                raise Fault("IMPORT_GRANT_EXPIRED", "文件选择已失效，请重新选择。", 403)
            roots.append(grant)
        source = authorized_path(payload["path"], roots)
        if kind == "model":
            from .media_assets import media_model_manifest
            report = media_model_manifest(source) or model_manifest(source)
            report.update(can_import=True, issues=[])
        elif kind == 'material':
            from .media_assets import material_report
            report = material_report(source)
            report['material_kind'] = report.pop('kind')
        elif payload.get('schema') == 'image_caption_v1':
            from .media_assets import image_dataset_report
            report = image_dataset_report(source)
        else:
            report = dataset_report(source, payload.get("schema", "sft"))
            report["manifest"] = [{"path": source.name, "size": report["total_bytes"], "sha256": report["sha256"]}]
            report["manifest_digest"] = digest(report["manifest"])
        with self.store.transaction():
            result = self.resource("import-plan", payload["project_id"], kind=kind,
                                   name=payload.get("name") or source.name, path=str(source),
                                   source_path=str(source), grant_id=payload.get("grant_id"), **report)
            self.store.put("import-plan", result)
        return self.public(result)

    def import_asset(self, kind, payload, key):
        scope = f"import:{kind}"
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            plan = self.store.get("import-plan", payload["plan_id"])
            if plan["kind"] != kind or plan["manifest_digest"] != payload["manifest_digest"]:
                raise Fault("IMPORT_PLAN_CHANGED", "导入计划与当前请求不一致，请重新分析。", 409)
            if not plan["can_import"]:
                raise Fault("DATA_SCHEMA_MISMATCH", "导入计划存在失败样本，请修正数据后重新分析。")
        roots = [regular_path(p) for p in self.settings.import_roots]
        if plan.get("grant_id") in self.grants:
            roots.append(self.grants[plan["grant_id"]])
        source = authorized_path(plan["source_path"], roots)
        from .media_assets import image_dataset_report, material_report, media_model_manifest
        actual = (media_model_manifest(source) or model_manifest(source)) if kind == 'model' else material_report(source) if kind == 'material' else image_dataset_report(source) if plan['schema'] == 'image_caption_v1' else dataset_report(source, plan['schema'])
        actual_digest = actual.get('manifest_digest') or digest([{'path': source.name, 'size': actual['total_bytes'], 'sha256': actual['sha256']}])
        if actual_digest != plan["manifest_digest"]:
            raise Fault("SOURCE_CHANGED", "所选文件已发生变化，请重新分析。", 409)
        destination = copy_asset(source, self.root / "assets", plan["manifest"], plan["manifest_digest"])
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            result = self.resource(kind, plan["project_id"], name=plan["name"], revision=1,
                                   version_id=identifier("version"), status="ready", manifest=plan["manifest"],
                                   manifest_digest=plan["manifest_digest"], total_bytes=plan["total_bytes"], storage_path=str(destination))
            if kind == "model":
                result.update(format=plan.get('detected_format', 'safetensors'), family=plan["family"], model_config=plan["model_config"], modality=plan.get('modality', 'text'), load_policy_ref=plan["id"],
                              loader=plan["loader"], trust_class=plan["trust_class"], execution_scope=plan["execution_scope"],
                              execution_boundary=actual["execution_boundary"])
                for name in ('default_engine', 'metadata_manifest_digest', 'license'):
                    if name in plan:
                        result[name] = plan[name]
            elif kind == 'material':
                result.update(kind=plan['material_kind'], **{name: plan[name] for name in ('media_type', 'width', 'height', 'entrypoint', 'checks')})
            else:
                result.update(schema=plan["schema"], sample_count=plan["sample_count"], sha256=plan["sha256"], checks=plan["checks"])
                result['entrypoint'] = plan.get('entrypoint', plan['manifest'][0]['path'])
            self.store.put(kind, result)
            response = self.public(result)
            self.store.remember(scope, key, payload, response)
            return response

    def new_task(self, payload):
        from .media import DEFAULTS
        draft = {"kind": payload["kind"], "operation": payload["operation"], "model_id": None, "dataset_id": None, "adapter_id": None, "evaluation_plan_id": None, "checkpoint_id": None,
                 "input": {"prompt": ""}, "runtime": dict(TRAIN_RUNTIME if payload["operation"] == "train" else DEFAULT_RUNTIME)}
        if payload['kind'] != 'text':
            draft['runtime'] = dict(DEFAULTS.get((payload['kind'], payload['operation']), DEFAULTS.get((payload['kind'], 'generate'), {})))
            if payload['kind'] == 'image':
                draft['input'] = {'prompt': '', 'negative_prompt': ''}
            elif payload['kind'] == 'video':
                draft['input'] = {'material_id': None}
        with self.store.transaction():
            project = self.store.get('project', payload['project_id'])
            if payload['kind'] == 'text' and payload['operation'] in {'generate', 'train'} and project.get('default_execution_target_id'):
                target = self.store.get('execution-target', project['default_execution_target_id'])
                if target['project_id'] != payload['project_id']:
                    raise Fault('PROJECT_MISMATCH', '默认执行目标与当前项目不一致。', 403)
                draft['execution_target_id'] = target['id']
                draft['runtime'].update(engine='transformers', device_id='cuda:0', precision='bfloat16')
            result = self.resource("task", payload["project_id"], name=payload["name"], kind=payload["kind"], operation=payload["operation"], draft_revision=1, draft=draft)
            self.store.put("task", result)
            return result

    def save_draft(self, task_id, payload):
        with self.store.transaction():
            task = self.store.get("task", task_id)
            if task["operation"] in {"export", "evaluate", "quantize"} or task["draft"].get("checkpoint_id") or task.get('immutable_draft'):
                raise Fault("CONTROL_NOT_SUPPORTED", "此任务使用固定计划或检查点，不能修改草稿；需要其他输入时新建任务。", 409)
            if task["draft_revision"] != payload["expected_revision"]:
                raise Fault("REVISION_CONFLICT", "草稿已更新，请刷新后再保存。", 409, current_revision=task["draft_revision"])
            draft = payload["draft"]
            if draft["kind"] != task["kind"] or draft["operation"] != task["operation"]:
                raise Fault("INVALID_CONFIG", "草稿类别和操作必须与任务一致。")
            for field_name, kind in (("model_id", "model"), ("dataset_id", "dataset"), ("adapter_id", "adapter"), ("evaluation_plan_id", "evaluation-plan"), ("checkpoint_id", "checkpoint"), ('execution_target_id', 'execution-target')):
                if draft.get(field_name):
                    item = self.store.get(kind, draft[field_name])
                    if item["project_id"] != task["project_id"]:
                        raise Fault("PROJECT_MISMATCH", "资源属于其他项目，请在当前项目导入。", 403, field=field_name)
            task.update(draft=draft, draft_revision=task["draft_revision"] + 1, updated_at=now())
            self.store.put("task", task)
            return task

    def environment(self, refresh=False, *, origin='environment'):
        with self.probe_observations.environment('mlx', 'text', origin, refresh) as observation:
            with self.environment_lock:
                observation['lock_acquired_monotonic_ns'] = time.monotonic_ns()
                result = self._environment(refresh, observation)
                observation['ready'] = result.get('ready')
                return result

    def _environment(self, refresh, observation):
        python, script = self.settings.worker_python, self.settings.worker_script
        result = {"engine": "mlx", "device_id": "apple-gpu", "ready": False, "reason": "尚未配置独立 MLX Python 环境与执行脚本。"}
        preflight_script = self.settings.preflight_script
        bundled = not python and self.settings.bundled_worker
        if bundled:
            prepared = self.settings.bundled_worker.is_absolute() and self.settings.bundled_worker.is_file()
        else:
            prepared = bool(python and script and preflight_script and python.is_absolute() and script.is_absolute() and preflight_script.is_absolute() and python.is_file() and script.is_file() and preflight_script.is_file())
        if not prepared:
            result["digest"] = digest(result)
            return result
        with self.probe_observations.identity(observation):
            identity = self.execution_identity()
            cache_key = digest(identity)
        if not refresh and self.environment_cache and self.environment_cache[0] == cache_key:
            observation['cache_outcome'] = 'hit'
            return self.environment_cache[1]
        observation['cache_outcome'] = 'refresh' if refresh else 'miss'
        try:
            command = [str(self.settings.bundled_worker), "--mode", "probe"] if bundled else [str(python), "-c", "import json,importlib.metadata,platform,mlx.core as mx,mlx_lm;print(json.dumps({'python':platform.python_version(),'dependencies':{name:importlib.metadata.version(name) for name in ['mlx','mlx-lm','transformers','tokenizers','numpy','safetensors','huggingface-hub']},'metal':mx.metal.is_available()}))"]
            facts, ready = self.probe_observations.run("mlx", "bundled" if bundled else "external_python", command,
                                   timeout=90 if bundled else 20, env=self.worker_environment(),
                                   is_ready=lambda facts: bool(facts.get("metal")) and (not bundled or bool(facts.get("sources") and facts.get("runtime_manifest_sha256"))))
            result.update(ready=ready, execution_backend="bundled" if bundled else "external_python", versions=facts, reason="" if ready else "MLX 依赖、运行身份或 Metal 设备不可用，请检查已选择环境。")
        except ProbeFailure as error:
            result["reason"] = str(error)
        result["identity"] = identity
        result["digest"] = digest(result)
        self.environment_cache = (cache_key, result)
        return result

    def execution_identity(self):
        python, worker, preflight = self.settings.worker_python, self.settings.worker_script, self.settings.preflight_script
        if not python and self.settings.bundled_worker:
            binary = self.settings.bundled_worker
            return {"bundled_worker": str(binary), "binary_sha256": file_hash(binary), "binary_size": binary.stat().st_size}
        sources = {str(path): file_hash(path) for path in sorted(preflight.parent.glob("*.py")) if path.is_file()}
        sources.update({str(path): file_hash(path) for path in sorted(worker.parent.glob("*.py")) if path.is_file()})
        lock_file = preflight.parent / "requirements.lock.txt"
        return {"python": str(python), "python_size": python.stat().st_size, "python_mtime_ns": python.stat().st_mtime_ns,
                "adapter_sources": sources, "launcher_sha256": digest(LAUNCHER_SOURCE), "dependencies_lock_sha256": file_hash(lock_file) if lock_file.is_file() else None}

    def preflight_command(self, snapshot, output):
        if not self.settings.worker_python and self.settings.bundled_worker:
            return [str(self.settings.bundled_worker), "--mode", "preflight", "--snapshot", str(snapshot), "--output-dir", str(output)]
        return [str(self.settings.worker_python), str(self.settings.preflight_script), "--snapshot", str(snapshot), "--output-dir", str(output)]

    def worker_environment(self):
        environment = {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT") if key in os.environ}
        environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1", TOKENIZERS_PARALLELISM="false", PYTHONUNBUFFERED="1", AILAB_CONTROL_PID=str(os.getpid()))
        return environment

    def inspect_task(self, task):
        if self.format_conversions.handles(task):
            return self.format_conversions.inspect(task)
        if task['draft']['kind'] != 'text':
            return self.media.inspect(task)
        draft, blocking = task["draft"], []
        model_evaluation = draft.get("operation") == "evaluate" and draft.get("evaluation_kind") == "quantized_model"
        model_evaluation_fields = {}
        if (draft.get("candidate_model_id") or draft.get("evaluation_kind")) and not model_evaluation:
            blocking.append({"code": "MODEL_COMPARISON_UNSUPPORTED", "message": "量化模型对照字段只能用于专用质量评测任务。", "field": "candidate_model_id"})
        if draft['operation'] == 'generate':
            # 历史或直接写入的草稿也走正式合同；不把缺省字段回写到用户草稿。
            from .api import Runtime
            try:
                requested = Runtime.model_validate(draft['runtime'])
                if requested.max_tokens >= requested.context_limit:
                    blocking.append({'code': 'CONTEXT_TOO_LONG', 'message': '最大输出必须为输入和聊天模板留出上下文空间；请增加总预算或减少最大输出。', 'field': 'runtime.context_limit'})
            except (TypeError, ValueError):
                blocking.append({'code': 'UNSUPPORTED_PARAMETER', 'message': '生成参数不符合当前本机组合，请检查上下文、停止序列、流式和其他字段。', 'field': 'runtime'})
        if draft.get("runtime", {}).get("kv_precision") == "q4":
            blocking.append({"code": "KV_PRECISION_NOT_APPROVED", "message": "4-bit 缓存未通过质量对照，请改为模型精度后重新检查。", "field": "kv_precision"})
        environment = self.environment(refresh=True)
        model = None
        dataset = None
        adapter = None
        plan = None
        plan_fields = {}
        if draft["kind"] != "text":
            blocking.append({"code": "UNSUPPORTED_COMBINATION", "message": "当前只开放本机 MLX 文本生成与 SFT LoRA；媒体适配器尚未接入。", "field": "operation"})
        if draft["runtime"]["engine"] != "mlx" or draft["runtime"]["device_id"] != "apple-gpu":
            blocking.append({"code": "UNSUPPORTED_COMBINATION", "message": "当前只支持 MLX 与本机 Apple GPU 组合。", "field": "runtime"})
        if not environment["ready"]:
            blocking.append({"code": "ENVIRONMENT_NOT_READY", "message": environment["reason"], "field": "runtime.engine"})
        if draft["operation"] == "generate" and not draft["input"]["prompt"].strip():
            blocking.append({"code": "INVALID_CONFIG", "message": "请输入生成内容。", "field": "input.prompt"})
        if not draft.get("model_id"):
            blocking.append({"code": "MODEL_NOT_READY", "message": "请先导入并选择模型。", "field": "model_id"})
        else:
            model = self.store.get("model", draft["model_id"])
            if model["project_id"] != task["project_id"]:
                raise Fault("PROJECT_MISMATCH", "模型不属于当前项目。", 403)
            if model.get("format") in {"coreml", "onnx", "torchscript"}:
                blocking.append({"code": "CONVERTED_ENGINE_MISMATCH", "message": "转换模型需要从模型库使用其对应格式引擎试用。", "field": "model_id"})
            config = model["model_config"]
            quantization = config.get("quantization") or config.get("quantization_config")
            try:
                profile = model_profile(config)
            except ValueError as error:
                profile = None
                blocking.append({"code": "MODEL_UNVERIFIED", "message": str(error), "field": "model_id"})
            if profile and draft["operation"] in {"train", "distill"} and draft["runtime"].get("num_layers", 2) > profile["num_hidden_layers"]:
                blocking.append({"code": "INVALID_CONFIG", "message": "训练层数超过所选基座的总层数。", "field": "runtime.num_layers"})
            if profile and profile["name"] == "qwen25-7b" and (quantization or draft["operation"] == "quantize" or model_evaluation):
                blocking.append({"code": "MODEL_UNVERIFIED", "message": "7B 当前只接受未量化基座；权重量化尚未通过独立验证。", "field": "model_id"})
            elif profile and quantization:
                expected_quantization = {"bits": 4, "group_size": 64, "mode": "affine"}
                if quantization != expected_quantization or config.get("quantization") not in (None, expected_quantization) or config.get("quantization_config") not in (None, expected_quantization) or draft["operation"] != "generate" or draft.get("adapter_id"):
                    blocking.append({"code": "MODEL_UNVERIFIED", "message": "当前量化组合仅开放 MLX 4-bit／64／affine 独立生成；训练、适配器、评测和再次量化均未开放。", "field": "model_id"})
            try:
                verify_manifest(Path(model["storage_path"]), model["manifest"])
            except Fault as error:
                blocking.append({"code": error.code, "message": error.message, "field": "model_id"})
        if draft.get("dataset_id"):
            dataset = self.store.get("dataset", draft["dataset_id"])
            if dataset["project_id"] != task["project_id"]:
                raise Fault("PROJECT_MISMATCH", "数据不属于当前项目。", 403)
            if draft["operation"] not in {"train", "distill"}:
                blocking.append({"code": "UNSUPPORTED_COMBINATION", "message": "当前操作不读取训练数据，请清空数据集选择。", "field": "dataset_id"})
            elif dataset["schema"] != "sft" or dataset["total_bytes"] > 64 * 1024 * 1024:
                blocking.append({"code": "DATA_SCHEMA_MISMATCH", "message": "首期训练需要不超过 64 MiB 的 SFT 对话数据。", "field": "dataset_id"})
            else:
                try:
                    verify_manifest(Path(dataset["storage_path"]), dataset["manifest"])
                except Fault as error:
                    blocking.append({"code": error.code, "message": error.message, "field": "dataset_id"})
        elif draft["operation"] in {"train", "distill"}:
            blocking.append({"code": "DATASET_NOT_READY", "message": "请先导入并选择 SFT 数据。", "field": "dataset_id"})
        dataset_split_fields = {}
        if dataset and draft['operation'] in {'train', 'distill'}:
            try:
                dataset_split_fields = self.dataset_splits.training_fields(task, dataset, model)
            except Fault as error:
                blocking.append({'code': error.code, 'message': error.message, 'field': 'dataset_id'})
        if draft.get("adapter_id"):
            adapter = self.store.get("adapter", draft["adapter_id"])
            if adapter["project_id"] != task["project_id"]:
                raise Fault("PROJECT_MISMATCH", "适配器不属于当前项目。", 403)
            if draft["operation"] not in {"generate", "evaluate", "merge"} or not model or adapter["base_model_id"] != model["id"] or adapter["base_manifest_digest"] != model["manifest_digest"]:
                blocking.append({"code": "ADAPTER_BASE_MISMATCH", "message": "适配器仅可在其固定基座上进行显式试用或评测。", "field": "adapter_id"})
            try:
                verify_manifest(Path(adapter["storage_path"]), adapter["manifest"])
            except Fault as error:
                blocking.append({"code": error.code, "message": error.message, "field": "adapter_id"})
        elif draft["operation"] == "evaluate" and not model_evaluation:
            blocking.append({"code": "ADAPTER_NOT_READY", "message": "独立评测必须选择已保存的实验适配器。", "field": "adapter_id"})
        if model_evaluation:
            try:
                model_evaluation_fields = self.evaluation.model_fields(task)
            except Fault as error:
                blocking.append({"code": error.code, "message": error.message, "field": "candidate_model_id"})
        if draft.get("evaluation_plan_id"):
            plan = self.store.get("evaluation-plan", draft["evaluation_plan_id"])
            if plan["project_id"] != task["project_id"]:
                raise Fault("PROJECT_MISMATCH", "评测计划不属于当前项目。", 403)
            try:
                if draft["operation"] not in {"train", "evaluate"}:
                    raise Fault("UNSUPPORTED_COMBINATION", "生成任务不绑定训练评测计划。")
                plan_fields = self.evaluation.plan_fields(plan)
                if draft["operation"] == "train" and dataset and not blocking:
                    self.evaluation.no_overlap(plan, dataset)
            except Fault as error:
                blocking.append({"code": error.code, "message": error.message, "field": "evaluation_plan_id"})
        elif draft["operation"] == "evaluate":
            blocking.append({"code": "EVALUATION_PLAN_REQUIRED", "message": "请先选择冻结评测计划。", "field": "evaluation_plan_id"})
        if model_evaluation_fields and plan:
            model_evaluation_fields["evaluation_plan_created_at"] = plan["created_at"]
        lab_fields = {}
        try:
            lab_fields = self.model_lab.fields(task)
        except (Fault, ValueError) as error:
            blocking.append({"code": getattr(error, "code", "MODEL_LAB_INVALID"), "message": str(error), "field": "teacher_model_id"})
        checkpoint_fields = {}
        if draft.get("checkpoint_id"):
            try:
                checkpoint_fields = self.checkpoints.fields(task, environment)
            except Fault as error:
                blocking.append({"code": error.code, "message": error.message, "field": "checkpoint_id"})
        result = {"blocking": blocking, "environment": environment, "model": model, "dataset": dataset, "adapter": adapter, "evaluation_plan": plan, "evaluation_fields": plan_fields, "checkpoint_fields": checkpoint_fields, "model_evaluation_fields": model_evaluation_fields, "dataset_split_fields": dataset_split_fields, "lab_fields": lab_fields}
        if not blocking:
            snapshot = {"operation": draft["operation"], "model_path": model["storage_path"], "model_manifest": model["manifest"], "model_manifest_digest": model["manifest_digest"], "input": draft["input"], "runtime": draft["runtime"]}
            if dataset:
                snapshot["dataset_path"] = str(Path(dataset["storage_path"]) / dataset["manifest"][0]["path"])
                snapshot.update(dataset_manifest=dataset["manifest"], dataset_manifest_digest=dataset["manifest_digest"])
            if adapter:
                snapshot.update(adapter_path=adapter["storage_path"], adapter_manifest=adapter["manifest"], adapter_manifest_digest=adapter["manifest_digest"], adapter_training_recipe_digest=adapter["training_recipe_digest"])
            snapshot.update(lab_fields)
            snapshot.update(plan_fields)
            snapshot.update(model_evaluation_fields)
            snapshot.update(checkpoint_fields)
            with tempfile.TemporaryDirectory(prefix="preflight-", dir=self.root) as directory:
                path = Path(directory)
                (path / "snapshot.json").write_text(encode(snapshot), encoding="utf-8")
                try:
                    checked = subprocess.run(self.preflight_command(path / "snapshot.json", path / "output"), capture_output=True, text=True, timeout=60, env=self.worker_environment())
                    report = json.loads(checked.stdout)
                    if not isinstance(report, dict) or type(report.get("can_submit")) is not bool or not isinstance(report.get("blocking"), list) or checked.returncode not in (0, 1):
                        raise ValueError("检查器结果结构错误")
                    if not report["can_submit"] and not report["blocking"]:
                        raise ValueError("阻断结果缺少原因")
                    if report["can_submit"] and (checked.returncode != 0 or report["blocking"] or not isinstance(report.get("effective_config"), dict) or not isinstance(report.get("recipe"), dict) or not isinstance(report.get("check_report"), dict) or not isinstance(report.get("tokenization_recipe_digest"), str) or not re.fullmatch(r"[0-9a-f]{64}", report["tokenization_recipe_digest"])):
                        raise ValueError("成功检查缺少完整身份或退出码错误")
                    if any(not isinstance(item, dict) or not isinstance(item.get("code"), str) or not isinstance(item.get("message"), str) for item in report["blocking"]):
                        raise ValueError("阻断字段无效")
                    result["check"] = report
                    blocking.extend(report["blocking"])
                    if dataset_split_fields and report.get('can_submit') and report.get('source_dataset_tokenization_recipe_digest', report.get('tokenization_recipe_digest')) != dataset_split_fields['dataset_split_ref']['tokenization_recipe_digest']:
                        blocking.append({'code': 'DATASET_SPLIT_CHECK_EXPIRED', 'message': '当前分词配方与来源组检查不同，请重新准备划分。', 'field': 'dataset_id'})
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    blocking.append({"code": "PREFLIGHT_FAILED", "message": "分词与监督检查未完成，请检查已选环境。"})
        return result

    def preflight(self, task_id, revision):
        task = self.store.get("task", task_id)
        if (task.get('draft') or {}).get('execution_target_id'):
            return self.remote_execution.preflight(task_id, revision)
        if task["operation"] == "export":
            raise Fault("CONTROL_NOT_SUPPORTED", "导出任务必须通过固定导出计划提交。", 409)
        settings_revision = self.user_settings["revision"]
        if revision != task["draft_revision"]:
            raise Fault("REVISION_CONFLICT", "草稿已更新，请重新检查。", 409, current_revision=task["draft_revision"])
        with self.store.lock:
            workflow_fields = self.workflows.submission_fields(task)
        inspected = self.inspect_task(task)
        with self.store.transaction():
            latest = self.store.get("task", task_id)
            if latest["draft_revision"] != revision:
                raise Fault("REVISION_CONFLICT", "检查期间草稿已更新，请重新检查。", 409, current_revision=latest["draft_revision"])
            if self.user_settings["revision"] != settings_revision:
                raise Fault("ENVIRONMENT_CHANGED", "检查期间环境设置已更新，请重新检查。", 409)
            if self.workflows.submission_fields(latest) != workflow_fields:
                raise Fault('WORKFLOW_IDENTITY_MISMATCH', '检查期间工作流输入来源已变化，请打开当前步骤重新检查。', 409)
            result = self.resource("preflight", task["project_id"], task_id=task_id, draft_revision=revision,
                                   can_submit=not inspected["blocking"], blocking=inspected["blocking"], warnings=[], changes=[],
                                   effective_config=task["draft"]["runtime"], environment=inspected["environment"],
                                   config_digest=digest(task["draft"]), model_digest=inspected["model"]["manifest_digest"] if inspected["model"] else None,
                                   expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())
            checked = inspected.get("check", {})
            result.update(effective_config=checked.get("effective_config", task["draft"]["runtime"]), tokenization_recipe_digest=checked.get("tokenization_recipe_digest"), tokenization_recipe=checked.get("recipe"), check_report=checked.get("check_report"), dataset_digest=inspected["dataset"]["manifest_digest"] if inspected["dataset"] else None)
            result["lab_inputs_digest"] = digest(inspected.get("lab_fields", {}))
            result["adapter_digest"] = inspected["adapter"]["manifest_digest"] if inspected["adapter"] else None
            result["evaluation_plan_digest"] = inspected["evaluation_fields"].get("evaluation_plan_digest")
            result["evaluation_plan_id"] = inspected["evaluation_fields"].get("evaluation_plan_id")
            model_evaluation_fields = inspected.get("model_evaluation_fields", {})
            result["model_evaluation_inputs_digest"] = digest(model_evaluation_fields) if model_evaluation_fields else None
            result["checkpoint_digest"] = inspected["checkpoint_fields"].get("checkpoint_ref", {}).get("manifest_digest")
            result['media_recipe_digest'] = checked.get('media_recipe_digest')
            result['material_digest'] = inspected.get('media_fields', {}).get('input_image_manifest_digest')
            result['workflow_ref'] = workflow_fields.get('workflow_ref')
            result['workflow_digest'] = digest(result['workflow_ref']) if result['workflow_ref'] else None
            if inspected.get('dataset_split_fields'):
                result.update(inspected['dataset_split_fields'])
            if inspected["adapter"]:
                result["warnings"].append({"code": "EXPERIMENTAL_ADAPTER", "message": "此适配器为实验产物，尚未通过独立质量评测。"})
            if inspected["model"] and inspected["model"].get("status") == "experimental":
                result["warnings"].append({"code": "EXPERIMENTAL_MODEL", "message": "此模型为转换实验产物，尚未通过独立质量评测。"})
            if task["kind"] == 'text' and task["operation"] == "train" and not inspected["evaluation_plan"]:
                result["warnings"].append({"code": "EVALUATION_PLAN_NOT_BOUND", "message": "本次训练未绑定冻结评测计划，产物仅能保存为实验适配器，事后评测不能准入。"})
            if task["operation"] == "evaluate" and inspected["adapter"] and inspected["adapter"]["config"].get("evaluation_plan_digest") != result["evaluation_plan_digest"]:
                result["warnings"].append({"code": "POSTHOC_EVALUATION", "message": "来源训练未绑定此计划；允许查看事后对照，但不能登记候选。"})
            if model_evaluation_fields and any(model_evaluation_fields["quality_plan_ref"][key] != result[key] for key in ("evaluation_plan_id", "evaluation_plan_digest")):
                result["warnings"].append({"code": "MODEL_QUALITY_PLAN_MISMATCH", "message": "本次不是该量化模型首次固定的准入方案；可生成完整对照报告，但不能据此登记。"})
            result["preflight_id"] = result["id"]
            self.store.put("preflight", result)
            return self.public(result)

    def submit(self, task_id, payload, key):
        if (self.store.get('task', task_id).get('draft') or {}).get('execution_target_id'):
            return self.remote_execution.submit(task_id, payload, key)
        settings_revision = self.user_settings["revision"]
        with self.store.transaction():
            scope = f"submit:{task_id}"
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.closed.is_set():
                raise Fault("SERVICE_STOPPING", "服务正在关闭，请稍后重试。", 503)
            task = self.store.get("task", task_id)
            if task["operation"] == "export":
                raise Fault("CONTROL_NOT_SUPPORTED", "导出任务不能作为模型计算重复提交。", 409)
            check = self.store.get("preflight", payload["preflight_id"])
            if payload["expected_revision"] != task["draft_revision"] or check["draft_revision"] != task["draft_revision"]:
                raise Fault("REVISION_CONFLICT", "草稿已更新，请重新检查。", 409, current_revision=task["draft_revision"])
            if check["task_id"] != task_id or check["config_digest"] != digest(task["draft"]) or datetime.fromisoformat(check["expires_at"]) <= datetime.now(timezone.utc):
                raise Fault("PREFLIGHT_EXPIRED", "检查已过期或不属于当前任务，请重新检查。", 409)
            workflow_ref = self.workflows.submission_fields(task).get('workflow_ref')
            if check.get('workflow_ref') != workflow_ref or check.get('workflow_digest') != (digest(workflow_ref) if workflow_ref else None):
                raise Fault('WORKFLOW_IDENTITY_MISMATCH', '工作流检查没有绑定当前输入来源，请重新检查。', 409)
        inspected = self.inspect_task(task)
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            latest = self.store.get("task", task_id)
            if latest["draft_revision"] != task["draft_revision"]:
                raise Fault("REVISION_CONFLICT", "提交检查期间草稿已更新，请重新检查。", 409, current_revision=latest["draft_revision"])
            current_workflow_ref = self.workflows.submission_fields(latest).get('workflow_ref')
            if current_workflow_ref != workflow_ref:
                raise Fault('WORKFLOW_IDENTITY_MISMATCH', '提交期间工作流输入来源已变化，请打开当前步骤。', 409)
            if self.user_settings["revision"] != settings_revision or self.closed.is_set():
                raise Fault("ENVIRONMENT_CHANGED", "提交检查期间环境或服务状态已更新。", 409)
            if datetime.fromisoformat(check["expires_at"]) <= datetime.now(timezone.utc):
                raise Fault("PREFLIGHT_EXPIRED", "检查已过期，请重新检查。", 409)
            if not check["can_submit"] or inspected["blocking"]:
                raise Fault("PREFLIGHT_BLOCKED", "存在阻断项，尚不能提交。", 409, blocking=inspected["blocking"])
            if check["environment"]["digest"] != inspected["environment"]["digest"] or check["model_digest"] != inspected["model"]["manifest_digest"]:
                raise Fault("ENVIRONMENT_CHANGED", "环境或模型已变化，请重新检查。", 409)
            if check.get("tokenization_recipe_digest") != inspected.get("check", {}).get("tokenization_recipe_digest") or check.get("dataset_digest") != (inspected["dataset"]["manifest_digest"] if inspected["dataset"] else None):
                raise Fault("ENVIRONMENT_CHANGED", "分词配方或数据版本已变化，请重新检查。", 409)
            if check.get('dataset_split_ref') != inspected.get('dataset_split_fields', {}).get('dataset_split_ref'):
                raise Fault('DATASET_SPLIT_CHANGED', '来源组划分身份已变化，请重新检查。', 409)
            if check.get("lab_inputs_digest", digest({})) != digest(inspected.get("lab_fields", {})):
                raise Fault("MODEL_LAB_SOURCE_CHANGED", "教师版本或实验输入变化，请重新检查。", 409)
            if check.get("adapter_digest") != (inspected["adapter"]["manifest_digest"] if inspected["adapter"] else None):
                raise Fault("ENVIRONMENT_CHANGED", "适配器版本已变化，请重新检查。", 409)
            if check.get("evaluation_plan_digest") != inspected["evaluation_fields"].get("evaluation_plan_digest"):
                raise Fault("EVALUATION_PLAN_CHANGED", "评测计划已变化，请重新检查。", 409)
            model_evaluation_fields = inspected.get("model_evaluation_fields", {})
            if check.get("model_evaluation_inputs_digest") != (digest(model_evaluation_fields) if model_evaluation_fields else None) or check.get("effective_config", {}).get("model_evaluation_recipe_digest") != inspected.get("check", {}).get("effective_config", {}).get("model_evaluation_recipe_digest"):
                raise Fault("MODEL_COMPARISON_CHANGED", "原权重、量化候选、准入方案或评测代码已变化，请重新检查。", 409)
            if check.get("checkpoint_digest") != inspected["checkpoint_fields"].get("checkpoint_ref", {}).get("manifest_digest"):
                raise Fault("CHECKPOINT_CHANGED", "检查点已变化，请重新检查。", 409)
            if check.get('media_recipe_digest') != inspected.get('check', {}).get('media_recipe_digest') or check.get('material_digest') != inspected.get('media_fields', {}).get('input_image_manifest_digest'):
                raise Fault('MEDIA_RECIPE_CHANGED', '媒体配方或输入素材已变化，请重新检查。', 409)
            if check.get('effective_config', {}).get('inference_recipe_digest') != inspected.get('check', {}).get('effective_config', {}).get('inference_recipe_digest'):
                raise Fault('INFERENCE_RECIPE_CHANGED', '推理配方或缓存配置已变化，请重新检查。', 409)
            active = [item for item in self.store.list("attempt") if (item["state"] not in TERMINAL or item.get('recovery_required')) and item.get("executor_type") not in {'export', 'remote'}]
            if active:
                raise Fault("DEVICE_BUSY", "本机已有任务或待核实的运行，请先处理后提交。", 409, attempt_id=active[0]["id"])
            attempt = self.resource("attempt", task["project_id"], task_id=task_id, state="queued", state_version=1,
                                    connection_state="connected", stop_status="not_requested", compute_outcome="pending",
                                    collection_state="not_started", collection_version=0, output_manifest_ref=None,
                                    last_event_sequence=0, phase="queued", progress=None, output_text="", terminal_reason=None)
            model = inspected["model"]
            snapshot = {"schema_version": "1.1", "attempt_id": attempt["id"], "task_id": task_id, "project_id": task["project_id"],
                        "draft_revision": task["draft_revision"], "kind": task["kind"], "operation": task["operation"],
                        "model_id": model["id"], "model_version_id": model["version_id"], "model_manifest_digest": model["manifest_digest"],
                        "model_path": model["storage_path"], "model_manifest": model["manifest"], "load_policy_ref": model["load_policy_ref"],
                        "input": task["draft"]["input"], "runtime": task["draft"]["runtime"], "requested_config": task["draft"]["runtime"], "effective_config": check["effective_config"],
                        "environment": inspected["environment"], "preflight_id": check["id"], "submitted_at": now(), "idempotency_key": key,
                        "tokenization_recipe_digest": check["tokenization_recipe_digest"], "tokenization_recipe": check["tokenization_recipe"], "tokenization_check_ref": check["id"]}
            if inspected["dataset"]:
                dataset = inspected["dataset"]
                snapshot.update(dataset_id=dataset["id"], dataset_version_id=dataset["version_id"], dataset_path=str(Path(dataset["storage_path"]) / dataset.get('entrypoint', dataset["manifest"][0]["path"])), dataset_manifest=dataset["manifest"], dataset_manifest_digest=dataset["manifest_digest"])
            if inspected["adapter"]:
                adapter = inspected["adapter"]
                snapshot.update(adapter_id=adapter["id"], adapter_version_id=adapter["version_id"], adapter_path=adapter["storage_path"], adapter_manifest=adapter["manifest"], adapter_manifest_digest=adapter["manifest_digest"], adapter_training_recipe_digest=adapter["training_recipe_digest"])
            snapshot.update(inspected.get("lab_fields", {}))
            snapshot.update(inspected["evaluation_fields"])
            snapshot.update(model_evaluation_fields)
            snapshot.update(inspected["checkpoint_fields"])
            snapshot.update(inspected.get('dataset_split_fields', {}))
            if task['kind'] != 'text':
                snapshot.update(inspected['media_fields'])
                snapshot['media_recipe_digest'] = check['media_recipe_digest']
            attempt["snapshot"] = snapshot
            self.workflows.bind_attempt(task, attempt)
            attempt["snapshot_digest"] = digest(snapshot)
            self.store.put("attempt", attempt)
            self.store.event(attempt, "state_changed", {"state": "queued", "state_version": 1})
            response = self.public(attempt)
            self.store.remember(scope, key, payload, response)
            thread = threading.Thread(target=self.run, args=(attempt["id"],), daemon=True, name=f"runner-{attempt['id']}")
            self.threads.add(thread)
        thread.start()
        return response

    def transition(self, attempt, state, message):
        if attempt["state"] in TERMINAL:
            return
        attempt.update(state=state, state_version=attempt["state_version"] + 1)
        if state in TERMINAL:
            attempt["finished_at"] = now()
        self.store.event(attempt, "terminal" if state in TERMINAL else "state_changed", {"state": state, "state_version": attempt["state_version"], "message": message})

    @staticmethod
    def process_identity(pid):
        try:
            result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            return {"status": "unknown"}
        if result.returncode == 1 and not result.stdout.strip():
            return {"status": "absent"}
        if result.returncode != 0 or not result.stdout.strip():
            return {"status": "unknown"}
        return {"status": "present", "identity_digest": digest({"pid": pid, "started": result.stdout.strip()}), "pid": pid}

    @staticmethod
    def group_present(pgid):
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def matching_launch_processes(snapshot_path):
        try:
            result = subprocess.run(["/bin/ps", "-ww", "-axo", "pid=,command="], capture_output=True, text=True, timeout=3)
            if result.returncode != 0:
                return None
            return [int(line.strip().split(None, 1)[0]) for line in result.stdout.splitlines() if str(snapshot_path) in line]
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    def reconcile(self, attempt_id, payload, key):
        initial = self.store.get("attempt", attempt_id)
        if initial.get('executor_type') == 'remote':
            return self.remote_execution.reconcile(attempt_id, payload, key)
        if initial.get("executor_type") == "export":
            if initial["state"] in TERMINAL:
                return self.public(initial)
            if not initial.get("recovery_required") and any(thread.name == f"export-{initial['export_id']}" for thread in self.threads):
                raise Fault("CONTROL_NOT_SUPPORTED", "当前导出仍由本服务管理，无需崩溃核实。", 409)
            return self.delivery.reconcile_export(attempt_id, payload, key)
        with self.store.transaction():
            scope = f"reconcile:{attempt_id}"
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if attempt["state_version"] != payload["expected_state_version"]:
                raise Fault("REVISION_CONFLICT", "运行状态已更新，请刷新。", 409, current_state_version=attempt["state_version"])
            if attempt["state"] in TERMINAL:
                return self.public(attempt)
            if not attempt.get("recovery_required"):
                raise Fault("CONTROL_NOT_SUPPORTED", "当前运行仍由本服务管理，无需崩溃核实。", 409)
        run_dir = self.root / "runs" / attempt_id
        process = attempt.get("process")
        if not process and (run_dir / "process.json").is_file():
            try:
                process = json.loads((run_dir / "process.json").read_text())
            except (OSError, ValueError):
                pass
        evidence = {"checked_at": now(), "status": "unknown"}
        if not process and not (run_dir / "launch-intent.json").exists() and not (run_dir / "start-authorized.json").exists() and attempt["state"] == "queued":
            evidence.update(status="confirmed_exited", reason="never_launched")
        elif process and type(process.get("pid")) is int and process["pid"] > 1:
            identity = self.process_identity(process["pid"])
            evidence.update(pid=process["pid"], observed=identity)
            if identity["status"] == "absent" and not self.group_present(process["pid"]):
                evidence.update(status="confirmed_exited", reason="process_and_group_absent")
            elif identity["status"] == "present" and process.get("identity", {}).get("status") == "present" and identity["identity_digest"] != process["identity"]["identity_digest"]:
                evidence.update(status="confirmed_exited", reason="pid_reused_with_different_start_identity")
            else:
                evidence["reason"] = "owned_process_or_group_still_present_or_unconfirmed"
        else:
            evidence["reason"] = "launch_record_unavailable"
            intent_file = run_dir / "launch-intent.json"
            if intent_file.is_file() and not (run_dir / "start-authorized.json").exists():
                try:
                    intent = json.loads(intent_file.read_text())
                    if intent.get("launch_protocol") == 1 and intent.get("attempt_id") == attempt_id and type(intent.get("controller_pid")) is int:
                        old_controller = self.process_identity(intent["controller_pid"])
                        old_identity = intent.get("controller_identity", {})
                        controller_exited = old_controller["status"] == "absent" or (old_controller["status"] == "present" and old_identity.get("status") == "present" and old_controller["identity_digest"] != old_identity.get("identity_digest"))
                        matches = self.matching_launch_processes(run_dir / "snapshot.json") if controller_exited else None
                        if controller_exited and matches == []:
                            evidence.update(status="confirmed_exited", reason="controller_exited_and_launch_never_authorized", controller=old_controller, matching_launch_pids=[])
                except (OSError, ValueError, TypeError):
                    pass
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if attempt["state_version"] != payload["expected_state_version"]:
                raise Fault("REVISION_CONFLICT", "核实期间运行状态已更新，请刷新。", 409, current_state_version=attempt["state_version"])
            attempt["recovery_evidence"] = evidence
            if evidence["status"] == "confirmed_exited":
                if not attempt.get("output_manifest_ref") and (run_dir / "completed.json").is_file():
                    try:
                        attempt["output_manifest_ref"] = self.seal_manifest(json.loads((run_dir / "completed.json").read_text()))
                        attempt["compute_outcome"] = "succeeded"
                    except (Fault, OSError, ValueError):
                        pass
                attempt.update(recovery_required=False, connection_state="connected", stop_status="confirmed", terminal_reason="CONTROL_INTERRUPTED")
                self.processes.pop(attempt_id, None)
                if attempt["compute_outcome"] == "succeeded":
                    attempt["collection_state"] = "failed"
                    attempt["collection_version"] += 1
                else:
                    attempt["compute_outcome"] = "failed"
                self.transition(attempt, "failed", "已核实原执行进程退出；保留中断事实，可创建新的运行。")
            else:
                attempt["state_version"] += 1
                self.store.event(attempt, "warning", {"code": "CONTROL_RESULT_UNKNOWN", "message": "原进程或其进程组仍存在，或缺少核实证据；未重新执行。", "evidence": evidence})
            response = self.public(attempt)
            self.store.remember(scope, key, payload, response)
            return response

    @staticmethod
    def _signal(process, signum):
        if process.poll() is None or (Service.process_identity(process.pid)["status"] == "absent" and Service.group_present(process.pid)):
            try:
                os.killpg(process.pid, signum)
                return True
            except ProcessLookupError:
                pass
        return False

    def control(self, attempt_id, payload, key, force=False):
        if self.store.get('attempt', attempt_id).get('executor_type') == 'remote':
            return self.remote_execution.control(attempt_id, payload, key, force)
        with self.store.transaction():
            scope = f"{'force-stop' if force else 'cancel'}:{attempt_id}"
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get("attempt", attempt_id)
            if payload["expected_state_version"] != attempt["state_version"]:
                raise Fault("REVISION_CONFLICT", "运行状态已更新，请刷新后重试。", 409, current_state=attempt["state"], current_state_version=attempt["state_version"], allowed_actions=self.actions(attempt))
            if attempt.get("recovery_required"):
                raise Fault("CONTROL_RESULT_UNKNOWN", "原执行归属尚未核实，不能向未知进程发送信号。", 409)
            if force and (attempt["state"] == "finalizing" or attempt_id not in self.processes):
                raise Fault("CONTROL_NOT_SUPPORTED", "当前没有可强制停止的已归属计算进程。", 409)
            command = {"command_id": identifier("command"), "action": "force-stop" if force else "cancel", "result": "not_applicable" if attempt["state"] in TERMINAL else "accepted"}
            if attempt["state"] not in TERMINAL:
                attempt["stop_status"] = "pending"
                attempt["last_control"] = command
                self.transition(attempt, "cancelling", "正在等待本次执行实际停止。")
                process = self.processes.get(attempt_id)
                if process:
                    try:
                        self._signal(process, signal.SIGKILL if force else signal.SIGTERM)
                    except OSError:
                        # 信号被拒绝不是停止确认；保留取消意图和设备占用，允许再核实或重试。
                        attempt["stop_status"] = "unknown"
                        command.update(result="failed", code="CONTROL_SIGNAL_FAILED", message="停止信号未能发送，尚未确认执行进程停止。")
                elif attempt["compute_outcome"] == "pending" and attempt.get("executor_type") != "export":
                    attempt.update(stop_status="confirmed", compute_outcome="cancelled", terminal_reason="CANCELLED_BEFORE_START")
                    command["result"] = "confirmed"
                    self.transition(attempt, "cancelled", "已确认任务尚未启动。")
            self.store.event(attempt, "control_result", command)
            response = {**self.public(attempt), **command}
            self.store.remember(scope, key, payload, response)
            return response

    def run(self, attempt_id):
        process, completed, worker_error = None, None, None
        run_dir = self.root / "runs" / attempt_id
        try:
            with self.store.transaction():
                attempt = self.store.get("attempt", attempt_id)
                if attempt["state"] in TERMINAL:
                    return
                if self.closed.is_set():
                    attempt.update(stop_status="confirmed", compute_outcome="cancelled", terminal_reason="SERVICE_STOPPING")
                    self.transition(attempt, "cancelled", "服务关闭前任务尚未启动。")
                    return
                self.transition(attempt, "preparing", "正在准备独立执行进程。")
                run_dir.mkdir(mode=0o700)
                output = run_dir / "output"
                output.mkdir(mode=0o700)
                snapshot_path = run_dir / "snapshot.json"
                snapshot_path.write_text(encode(attempt["snapshot"]), encoding="utf-8")
                snapshot_path.chmod(0o400)
                intent = {"controller_pid": os.getpid(), "controller_identity": self.process_identity(os.getpid()), "attempt_id": attempt_id, "snapshot_sha256": file_hash(snapshot_path), "launch_protocol": 1}
                publish_run_record(run_dir / "launch-intent.json", intent)
                (run_dir / "launcher.py").write_text(LAUNCHER_SOURCE, encoding="utf-8")
                stderr = (run_dir / "worker.stderr.log").open("wb")
                try:
                    if attempt['snapshot']['kind'] != 'text' or attempt['snapshot']['runtime']['engine'] in {'coreml', 'onnx', 'torchscript'}:
                        binary = self.media.bundled(attempt['snapshot']['kind'])
                        if binary:
                            command = [str(binary), '--mode', 'launch', '--snapshot', str(snapshot_path), '--output-dir', str(output), '--controller-pid', str(os.getpid())]
                        else:
                            python, worker, _ = self.media.execution(attempt['snapshot']['kind'])
                            command = [str(python), '-B', str(run_dir / 'launcher.py'), '--worker-script', str(worker), '--snapshot', str(snapshot_path), '--output-dir', str(output), '--controller-pid', str(os.getpid())]
                    else:
                        command = [str(self.settings.bundled_worker), "--mode", "launch", "--snapshot", str(snapshot_path), "--output-dir", str(output), "--controller-pid", str(os.getpid())] if not self.settings.worker_python and self.settings.bundled_worker else [str(self.settings.worker_python), str(run_dir / "launcher.py"), "--worker-script", str(self.settings.worker_script), "--snapshot", str(snapshot_path), "--output-dir", str(output), "--controller-pid", str(os.getpid())]
                    process = subprocess.Popen(command,
                                               stdout=subprocess.PIPE, stderr=stderr, start_new_session=True, env=self.worker_environment())
                finally:
                    stderr.close()
                self.processes[attempt_id] = process
                attempt["process"] = {"pid": process.pid, "started_at": now(), "owned": True, "controller_pid": os.getpid(), "identity": {"status": "unknown"}, "launch_protocol": 1}
                self.store.put("attempt", attempt)
            deadline = time.monotonic() + 5
            while not (run_dir / "process.json").is_file() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            with self.store.transaction():
                attempt = self.store.get("attempt", attempt_id)
                if attempt["state"] != "cancelling" and process.poll() is None:
                    if not (run_dir / "process.json").is_file():
                        raise Fault("LAUNCH_HANDSHAKE_FAILED", "执行器未完成归属登记，未授权模型执行。")
                    record = json.loads((run_dir / "process.json").read_text())
                    if record.get("pid") != process.pid or record.get("snapshot_sha256") != intent["snapshot_sha256"] or record.get("controller_pid") != os.getpid():
                        raise Fault("LAUNCH_HANDSHAKE_FAILED", "执行器启动身份不匹配，未授权模型执行。")
                    attempt["process"] = {**record, "started_at": attempt["process"]["started_at"]}
                    self.transition(attempt, "running", "执行器归属已登记，等待模型加载。")
                    authorize = True
                else:
                    authorize = False
            if authorize:
                publish_run_record(run_dir / "start-authorized.json", {"pid": process.pid, "snapshot_sha256": intent["snapshot_sha256"]})
            while raw := process.stdout.readline(2 * 1024 * 1024 + 1):
                if len(raw) > 2 * 1024 * 1024:
                    raise Fault("INVALID_WORKER_EVENT", "执行器事件超过大小限制。")
                try:
                    event = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise Fault("INVALID_WORKER_EVENT", "执行器返回了无法解析的事件。") from None
                if not isinstance(event, dict) or event.get("type") not in {"phase", "token", "metric", "completed", "error", "control_result"}:
                    raise Fault("INVALID_WORKER_EVENT", "执行器事件类型不受支持。")
                if event["type"] == "control_result":
                    self.checkpoints.handle_event(attempt_id, event)
                    continue
                if event["type"] == "completed":
                    if completed:
                        raise Fault("INVALID_WORKER_EVENT", "执行器重复报告计算完成。")
                    completed = event
                    self.seal_manifest(event)
                    publish_run_record(run_dir / "completed.json", event)
                elif event["type"] == "error":
                    worker_error = event
                with self.store.transaction():
                    attempt = self.store.get("attempt", attempt_id)
                    if event["type"] == "token":
                        token = event.get("text", "")
                        if attempt["snapshot"]["operation"] != "generate" or not isinstance(token, str) or len(attempt["output_text"]) + len(token) > 8 * 1024 * 1024:
                            raise Fault("INVALID_WORKER_EVENT", "输出内容超过大小限制。")
                        attempt["output_text"] += token
                        self.store.event(attempt, "token", {"text": token})
                    elif event["type"] == "phase":
                        attempt["phase"] = str(event.get("phase", event.get("name", "unknown")))[:120]
                        self.store.event(attempt, "phase_changed", event)
                    elif event["type"] == "metric":
                        self.store.event(attempt, "metric", event)
                    elif event["type"] == "error":
                        self.store.event(attempt, "warning", {"code": str(event.get("code", "WORKER_FAILED"))[:100], "message": str(event.get("message", "执行失败。"))[:1000]})
            returncode = process.wait()
            with self.store.transaction():
                attempt = self.store.get("attempt", attempt_id)
                attempt["process"]["returncode"] = returncode
                attempt["process"]["exited_at"] = now()
                if attempt["state"] == "cancelling":
                    if self.group_present(process.pid):
                        attempt.update(stop_status="unknown", recovery_required=True)
                        self.store.event(attempt, "warning", {"code": "CONTROL_RESULT_UNKNOWN", "message": "执行进程已退出，但进程组仍待核实。"})
                        return
                    if returncode == 0 and completed:
                        attempt["compute_outcome"] = "succeeded"
                        attempt["output_manifest_ref"] = self.seal_manifest(completed)
                    else:
                        attempt["compute_outcome"] = "cancelled" if returncode in (0, -signal.SIGTERM, -signal.SIGKILL, 130, 143) else "failed"
                    attempt.update(stop_status="confirmed", terminal_reason="USER_CANCELLED", collection_state="cancelled")
                    self.transition(attempt, "cancelled" if attempt["compute_outcome"] != "failed" else "failed", "已确认本次执行进程退出。")
                    return
                if returncode != 0 or worker_error or not completed:
                    raise Fault(str((worker_error or {}).get("code", "WORKER_FAILED"))[:100], str((worker_error or {}).get("message", "执行进程未提供完整计算结果。"))[:1000])
                attempt["compute_outcome"] = "succeeded"
                attempt["output_manifest_ref"] = self.seal_manifest(completed)
                attempt["effective_config"] = completed.get("effective_config", {})
                if self.group_present(process.pid):
                    attempt.update(stop_status="unknown", recovery_required=True)
                    self.store.event(attempt, "warning", {"code": "CONTROL_RESULT_UNKNOWN", "message": "主执行进程报告完成，但仍有同组进程存活；尚未收集产物或释放设备。"})
                    return
                command = attempt.get("last_control", {})
                if command.get("action") in {"pause", "resume"} and command.get("result") == "accepted":
                    # 计算已抢先完成，原暂停／恢复接收回执不能永久显示为仍待执行。
                    issued = self.store.get("training-control", command["command_id"])
                    if issued.get("attempt_id") == attempt_id and issued.get("result") == "accepted":
                        command.update(result="not_applicable", code="COMPUTE_COMPLETED", message="计算已完成，本次检查点控制未执行。", completed_at=now())
                        self.store.put("training-control", command)
                        self.store.event(attempt, "control_result", command)
                self.transition(attempt, "finalizing", "计算完成，正在校验与保存产物。")
            self.collect(attempt_id)
        except BaseException as error:
            if process and process.poll() is None:
                self._signal(process, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._signal(process, signal.SIGKILL)
                    process.wait(timeout=2)
            if process and self.group_present(process.pid):
                self._signal(process, signal.SIGTERM)
                deadline = time.monotonic() + 1
                while self.group_present(process.pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
                if self.group_present(process.pid):
                    self._signal(process, signal.SIGKILL)
            with self.store.transaction():
                attempt = self.store.get("attempt", attempt_id)
                if attempt["state"] not in TERMINAL:
                    # 前面的失败事务可能回滚退出字段；重新持久化实际观察到的退出证据。
                    if process and process.poll() is not None and attempt.get("process", {}).get("pid") == process.pid:
                        attempt["process"].update(returncode=process.returncode, exited_at=now())
                    fault = error if isinstance(error, Fault) else Fault("EXECUTION_FAILED", "执行或产物登记失败，请查看本次运行记录。", 500)
                    if process and self.group_present(process.pid):
                        attempt.update(stop_status="unknown", recovery_required=True)
                        self.store.event(attempt, "warning", {"code": "CONTROL_RESULT_UNKNOWN", "message": "执行异常，但仍有进程组成员待核实；设备占用尚未释放。", "original_error": fault.code})
                        return
                    if attempt["compute_outcome"] != "succeeded":
                        attempt["compute_outcome"] = "failed"
                    attempt["terminal_reason"] = fault.code
                    if attempt["compute_outcome"] == "succeeded":
                        attempt["collection_state"] = "failed"
                    self.store.event(attempt, "warning", {"code": fault.code, "message": fault.message})
                    self.transition(attempt, "failed", fault.message)
        finally:
            with self.store.lock:
                if not process or not self.group_present(process.pid):
                    self.processes.pop(attempt_id, None)
            if process and process.stdout:
                process.stdout.close()
            with self.store.lock:
                self.threads.discard(threading.current_thread())
            self._release_if_idle()

    def seal_manifest(self, completed):
        entries = completed.get("artifacts")
        if not isinstance(entries, list) or not entries or len(entries) > 100:
            raise Fault("MANIFEST_UNAVAILABLE", "执行器未提供完整产物清单。")
        paths = set()
        for item in entries:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise Fault("MANIFEST_UNAVAILABLE", "产物清单字段不完整。")
            path = Path(item["path"])
            if path.is_absolute() or ".." in path.parts or path.as_posix() in paths or not path.parts:
                raise Fault("ARTIFACT_CORRUPT", "产物路径越界或重复。")
            if not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
                raise Fault("MANIFEST_UNAVAILABLE", "产物摘要无效。")
            paths.add(path.as_posix())
        result = {"artifacts": entries, "complete": True, "effective_config": completed.get("effective_config", {})}
        result["digest"] = digest(result)
        return result

    def collect(self, attempt_id, payload=None, key=None, _remote_ready=False):
        if not _remote_ready and self.store.get('attempt', attempt_id).get('executor_type') == 'remote':
            return self.remote_execution.collect(attempt_id, payload, key)
        with self.store.transaction():
            attempt = self.store.get("attempt", attempt_id)
            scope = f"collect:{attempt_id}"
            if payload is not None:
                if previous := self.store.replay(scope, key, payload):
                    return previous
                if payload["expected_collection_version"] != attempt["collection_version"]:
                    raise Fault("COLLECTION_CONFLICT", "产物收集状态已更新，请刷新。", 409, current_collection_version=attempt["collection_version"])
                if attempt["state"] not in {"failed", "cancelled"}:
                    raise Fault("COLLECTION_CONFLICT", "当前尝试无需补收或仍在执行。", 409)
            manifest = attempt["output_manifest_ref"]
            if attempt["compute_outcome"] != "succeeded" or not manifest:
                raise Fault("MANIFEST_UNAVAILABLE", "没有可补收的已完成计算与完整清单。", 409)
            if payload and payload["manifest_digest"] != manifest["digest"]:
                raise Fault("COLLECTION_CONFLICT", "清单摘要不匹配，不能改收其他产物。", 409)
            if attempt["collection_state"] in {"collecting", "succeeded"}:
                raise Fault("COLLECTION_CONFLICT", "产物正在收集或已完整登记。", 409)
            collection = self.resource("collection", attempt["project_id"], attempt_id=attempt_id, state="collecting", manifest_digest=manifest["digest"], error=None, registered_artifact_ids=[])
            self.store.put("collection", collection)
            attempt.update(collection_state="collecting", collection_version=attempt["collection_version"] + 1)
            collection_version = attempt["collection_version"]
            self.store.event(attempt, "collection_changed", {"collection_id": collection["id"], "state": "collecting"})
        output_dir = self.root / "runs" / attempt_id / "output"
        registered = []
        failure = None
        try:
            total_bytes = 0
            for item in manifest["artifacts"]:
                source = regular_path(output_dir / item["path"])
                if not source.is_relative_to(output_dir) or not source.is_file():
                    raise Fault("ARTIFACT_CORRUPT", "产物文件越出本次输出目录或不是常规文件。")
                model_output = attempt['snapshot']['operation'] in {'merge', 'distill', 'convert'} and Path(item['path']).parts[0] == 'model'
                limit = 8 * 1024**3 if model_output else 256 * 1024**2
                total_bytes += source.stat().st_size
                if source.stat().st_size > limit or total_bytes > 32 * 1024**3:
                    raise Fault("ARTIFACT_CORRUPT", "产物超过本次收集限额：模型文件 8 GiB，其他文件 256 MiB，总计 32 GiB。")
                record = {"path": source.name, "size": source.stat().st_size, "sha256": item["sha256"]}
                destination = copy_asset(source, self.root / "assets", [record], digest(record))
                artifact_id = "artifact-" + digest({"attempt_id": attempt_id, "manifest": manifest["digest"], "path": item["path"]})[:32]
                media_type = item.get("media_type", "application/octet-stream")
                text = None
                truncated = False
                if attempt["snapshot"]["operation"] == "generate" and item["path"] == "result.txt" and media_type == "text/plain":
                    with (destination / source.name).open(encoding="utf-8") as stream:
                        preview = stream.read(INLINE_TEXT_LIMIT + 1)
                    text, truncated = preview[:INLINE_TEXT_LIMIT], len(preview) > INLINE_TEXT_LIMIT
                registered.append({"id": artifact_id, "resource_type": "artifact", "project_id": attempt["project_id"], "created_at": now(),
                                   "attempt_id": attempt_id, "name": source.name, "relative_path": item["path"], "storage_path": str(destination / source.name),
                                   "size": record["size"], "sha256": item["sha256"], "media_type": media_type, "text": text, "text_truncated": truncated})
        except (Fault, OSError, UnicodeError) as error:
            failure = error if isinstance(error, Fault) else Fault("COLLECTION_FAILED", "文件保存失败，计算结果保留，可修复存储后补收。", 500)
        try:
            with self.store.transaction():
                attempt = self.store.get("attempt", attempt_id)
                cancelled = attempt["state"] == "cancelling"
                collection["state"] = "failed" if failure else "cancelled" if cancelled else "succeeded"
                collection["error"] = {"code": failure.code, "message": failure.message} if failure else None
                collection["finished_at"] = now()
                if not failure and not cancelled:
                    for artifact in registered:
                        self.store.put("artifact", artifact)
                    collection["registered_artifact_ids"] = [artifact["id"] for artifact in registered]
                    texts = [artifact for artifact in registered if artifact["relative_path"] == "result.txt" and artifact["media_type"] == "text/plain" and artifact["text"] is not None]
                    if texts:
                        attempt["output_text"] = texts[0]["text"]
                        attempt["output_text_truncated"] = texts[0]["text_truncated"]
                    elif attempt["snapshot"]["operation"] != "generate":
                        attempt["output_text"] = ""
                self.store.put("collection", collection)
                attempt.update(collection_state=collection["state"], collection_version=attempt["collection_version"] + 1)
                self.store.event(attempt, "collection_changed", {"collection_id": collection["id"], "state": collection["state"], "error": collection["error"]})
                if attempt["state"] not in TERMINAL:
                    if cancelled:
                        attempt.update(stop_status="confirmed", terminal_reason="COLLECTION_CANCELLED")
                        self.transition(attempt, "cancelled", "计算已完成，产物收集已取消。")
                    elif failure:
                        attempt["terminal_reason"] = failure.code
                        self.transition(attempt, "failed", failure.message)
                    else:
                        attempt["terminal_reason"] = "COMPLETED"
                        self.transition(attempt, "succeeded", "产物已校验并完整保存。")
                if payload is not None:
                    self.store.remember(scope, key, payload, collection)
                return collection
        except Exception as error:
            # 登记事务已回滚；人工补收没有 run 的外层收尾，必须释放本次收集状态。
            # 使用版本确认归属，避免异常收尾覆盖后来已经完成的收集。
            try:
                with self.store.transaction():
                    current = self.store.get("attempt", attempt_id)
                    pending = self.store.get("collection", collection["id"])
                    if (pending["state"] == "collecting" and current["collection_state"] == "collecting"
                            and current["collection_version"] == collection_version):
                        fault = error if isinstance(error, Fault) else Fault("COLLECTION_FAILED", "产物登记失败，计算结果保留，可修复存储后补收。", 500)
                        pending.update(state="failed", error={"code": fault.code, "message": fault.message}, finished_at=now())
                        self.store.put("collection", pending)
                        current.update(collection_state="failed", collection_version=collection_version + 1)
                        self.store.event(current, "collection_changed", {"collection_id": pending["id"], "state": "failed", "error": pending["error"]})
                        if current["state"] == "cancelling":
                            current.update(stop_status="confirmed", terminal_reason="COLLECTION_CANCELLED")
                            self.transition(current, "cancelled", "计算已完成，产物登记失败，本次收集已取消。")
                        elif current["state"] not in TERMINAL:
                            current["terminal_reason"] = fault.code
                            self.transition(current, "failed", fault.message)
            finally:
                # 即使故障持续导致收尾写入也失败，仍向调用者保留原登记异常。
                raise error

    def save_work(self, payload, key):
        if self.store.get('attempt', payload['attempt_id'])['snapshot'].get('kind', 'text') != 'text':
            return self.media.save_work(payload, key)
        with self.store.transaction():
            if previous := self.store.replay("save-work", key, payload):
                return previous
            attempt = self.store.get("attempt", payload["attempt_id"])
            if attempt["snapshot"]["operation"] != "generate" or attempt["compute_outcome"] != "succeeded" or attempt["collection_state"] != "succeeded":
                raise Fault("ARTIFACT_NOT_READY", "文本作品需要已完整保存的生成正文。", 409)
        artifact = self.delivery.artifact_for_path(attempt, "result.txt")
        entries = [item for item in attempt["output_manifest_ref"]["artifacts"] if item.get("path") == "result.txt"]
        if artifact.get("media_type") != "text/plain" or entries[0].get("media_type") != "text/plain" or payload.get("artifact_id") not in (None, artifact["id"]):
            raise Fault("ARTIFACT_NOT_READY", "只有原执行清单中明确的 result.txt 生成正文可保存为文本作品。", 409)
        with Path(artifact["storage_path"]).open(encoding="utf-8") as stream:
            preview = stream.read(INLINE_TEXT_LIMIT + 1)
        if file_hash(Path(artifact["storage_path"])) != artifact["sha256"]:
            raise Fault("ARTIFACT_CORRUPT", "读取正文期间产物已变化。", 409)
        with self.store.transaction():
            if previous := self.store.replay("save-work", key, payload):
                return previous
            if self.store.get("attempt", attempt["id"]) != attempt or self.store.get("artifact", artifact["id"]) != artifact:
                raise Fault("REVISION_CONFLICT", "保存作品检查期间来源记录已变化。", 409)
            existing = [item for item in self.store.list("work", attempt["project_id"]) if item["artifact_id"] == artifact["id"]]
            result = existing[0] if existing else self.resource("work", attempt["project_id"], name=payload.get("name") or "文本结果", artifact_id=artifact["id"], attempt_id=attempt["id"], source_attempt=attempt["id"], revision=1, favorite=False, recipe=attempt["snapshot"])
            result.update(text=preview[:INLINE_TEXT_LIMIT], text_truncated=len(preview) > INLINE_TEXT_LIMIT)
            self.store.put("work", result)
            response = self.public(result)
            self.store.remember("save-work", key, payload, response)
            return response

    def backup(self, key=None):
        return self.backup_manager.create(key)

    def get_settings(self):
        bundled = bool(self.settings.bundled_worker and self.settings.bundled_worker.is_file())
        result = {**{key: value for key, value in self.user_settings.items() if key != "ui_context"}, "worker_python": str(self.settings.worker_python) if self.settings.worker_python else None,
                'media_python': str(self.settings.media_python) if self.settings.media_python else None,
                'audio_python': str(self.settings.audio_python) if self.settings.audio_python else None,
                "bundled_worker_available": bundled, "execution_backend": "external_python" if self.settings.worker_python else "bundled" if bundled else "not_prepared"}
        for prefix in ('media', 'audio'):
            binary = getattr(self.settings, 'bundled_' + prefix + '_worker')
            available = bool(binary and binary.is_file() and os.access(binary, os.X_OK))
            result['bundled_' + prefix + '_worker_available'] = available
            result[prefix + '_execution_backend'] = 'external_python' if getattr(self.settings, prefix + '_python') else 'bundled' if available else 'not_prepared'
        return result

    def get_ui_context(self):
        with self.store.lock:
            value = self.user_settings.get("ui_context", empty_context())
            return validate_context(value, self.store.get, allow_missing=True)

    def update_ui_context(self, payload):
        payload = UIContextPatch.model_validate(payload).model_dump(exclude_unset=True)
        with self.store.lock:
            with self.store.transaction():
                current = self.user_settings.get("ui_context", empty_context())
                validate_context(current, self.store.get, allow_missing=True)
                # 只核实本次新增的选择，不把其他项目的陈旧引用归一化写回。
                validate_context({"project_id": payload["project_id"], "projects": {
                    payload["project_id"]: payload["context"],
                }}, self.store.get)
                selected = {"project_id": payload["project_id"], "projects": {
                    **current["projects"], payload["project_id"]: payload["context"],
                }}
                # 取同一把锁内的最新环境设置；界面写入不改变环境版本或缓存。
                value = {**self.user_settings, "ui_context": selected}
                self.store.db.execute("INSERT INTO app_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (encode(value),))
            # 提交失败时保留原内存；提交成功后仍持锁，避免覆盖交错的环境写入。
            self.user_settings = value
            return self.get_ui_context()

    def update_settings(self, payload):
        paths = {name: Path(payload[name]) if payload[name] is not None else None for name in ('worker_python', 'media_python', 'audio_python') if name in payload}
        if not paths:
            raise Fault('INVALID_ENVIRONMENT', '至少选择一个需要更新的执行环境。')
        for name, path in paths.items():
            if name == 'worker_python' and path is None and not (self.settings.bundled_worker and self.settings.bundled_worker.is_file() and os.access(self.settings.bundled_worker, os.X_OK)):
                raise Fault("INVALID_ENVIRONMENT", "当前安装未包含可用的内置执行器，不能清空外部环境。")
            if path is not None and (not path.is_absolute() or not path.is_file() or not path.name.startswith("python") or not os.access(path, os.X_OK)):
                raise Fault("INVALID_ENVIRONMENT", "请选择已准备环境中可执行的 Python 绝对路径。")
        with self.store.transaction():
            if payload["expected_revision"] != self.user_settings["revision"]:
                raise Fault("REVISION_CONFLICT", "环境设置已更新，请刷新。", 409, current_revision=self.user_settings["revision"])
            if any(item["state"] not in TERMINAL for item in self.store.list("attempt")):
                raise Fault("DEVICE_BUSY", "运行期间不能替换执行环境。", 409)
            value = {**self.user_settings, "revision": self.user_settings["revision"] + 1, **{name: str(path) if path else None for name, path in paths.items()}}
            self.store.db.execute("INSERT INTO app_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (encode(value),))
            self.user_settings = value
            for name, path in paths.items():
                setattr(self.settings, name, path)
            self.environment_cache = None
            self.media.cache.clear()
            return self.get_settings()
