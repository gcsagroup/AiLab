"""自包含备份与新目录隔离恢复；原运行证据保持原字节。"""

import hashlib
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
import threading
import time

from .assets import authorized_path, file_hash, regular_path, verify_manifest
from .migrations import SUPPORTED_VERSIONS
from .storage import Fault, digest, encode, identifier, now
from .ui_context import validate_context

VERSION = "ailab-portable-backup-v1"
MAX_DATABASE_BYTES = 1024**3
MAX_BACKUP_BYTES = 32 * 1024**3
TERMINAL = {"succeeded", "failed", "cancelled"}
PATH_FIELDS = {"storage_path", "model_path", "candidate_model_path", "dataset_path", "adapter_path", "evaluation_dataset_path",
               "evaluation_criteria_path", "input_image_path", "dataset_root_path", "source_path", "target_dir", "verified_path", "final_path", "partial_path"}
TABLE_COLUMNS = {
    "schema_version": ["version"], "projects": ["id", "body"],
    "resources": ["id", "kind", "project_id", "body"], "events": ["attempt_id", "sequence", "body"],
    "commands": ["scope", "key", "request_digest", "response"], "app_settings": ["id", "body"],
}


def remap_reference_paths(value, source_root: Path, target_root: Path, key=None):
    """仅迁移业务文件引用；原检查点清单内的来源摘要保持不变。"""
    if isinstance(value, dict) and value.get("resource_type") in {"source-check", "capability-review"}:
        # 外部原文和人工记录是不可变证据，其中的同名路径字段不属于工作库引用。
        return value
    if isinstance(value, list):
        return [remap_reference_paths(item, source_root, target_root) for item in value]
    if isinstance(value, dict):
        return {name: remap_reference_paths(item, source_root, target_root,
                                           "storage_path" if key in {"checkpoint_ref", "teacher"} and name == "path" else name)
                for name, item in value.items()}
    if key in PATH_FIELDS and isinstance(value, str) and Path(value).is_absolute() and Path(value).is_relative_to(source_root):
        return str(target_root / Path(value).relative_to(source_root))
    return value


def fail(message, code="BACKUP_INVALID"):
    raise Fault(code, message, 409)


def relative_path(value):
    if not isinstance(value, str):
        fail("备份清单路径必须为字符串。")
    path = Path(value)
    if path.is_absolute() or not path.parts or any(part in {".", ".."} for part in value.split("/")) or path.as_posix() != value:
        fail("备份清单包含越界或非规范路径。")
    return path


def read_json(path):
    if path.stat().st_size > 16 * 1024 * 1024:
        fail("备份清单超过 16 MiB。")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                fail("备份清单包含重复字段。")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: fail("备份清单不能包含非有限数。"))


def regular_file(path):
    resolved = regular_path(path)
    if not stat.S_ISREG(resolved.stat().st_mode):
        fail("备份只接受普通文件，不能包含链接或设备文件。")
    return resolved


class DatabaseResources:
    """冻结备份库的可重复只读查询，避免百万条 JSON 同时驻留内存。"""

    def __init__(self, path):
        self.path = path

    def select(self, *kinds):
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            db.execute("PRAGMA trusted_schema=OFF")
            clause = " WHERE kind IN (" + ",".join("?" for _ in kinds) + ")" if kinds else ""
            for kind, body in db.execute("SELECT kind,body FROM resources" + clause, kinds):
                yield kind, json.loads(body)
        finally:
            db.close()

    def __iter__(self):
        return self.select()


def selected_resources(resources, *kinds):
    if isinstance(resources, DatabaseResources):
        return resources.select(*kinds)
    return ((kind, body) for kind, body in resources if kind in kinds)


def database(path, with_version=False):
    if path.stat().st_size > MAX_DATABASE_BYTES:
        fail("当前恢复支持不超过 1 GiB 的元数据数据库。")
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        db.execute("PRAGMA trusted_schema=OFF")
        entries = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if any(kind not in {"table", "index"} for kind, _ in entries) or {name for kind, name in entries if kind == "table"} != set(TABLE_COLUMNS):
            fail("备份数据库结构不受支持。")
        for table, columns in TABLE_COLUMNS.items():
            if [row[1] for row in db.execute(f'PRAGMA table_info("{table}")')] != columns:
                fail("备份数据库字段不受支持。")
        versions = db.execute("SELECT version FROM schema_version").fetchall()
        if len(versions) != 1 or type(versions[0][0]) is not int or versions[0][0] not in SUPPORTED_VERSIONS:
            fail("备份数据库版本不受支持。")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            fail("备份数据库完整性检查失败。")
        if db.execute("SELECT 1 FROM resources WHERE CASE WHEN json_valid(body) THEN json_type(body)!='object' ELSE 1 END LIMIT 1").fetchone():
            fail("备份数据库包含无效的资源正文。")
        saved = db.execute("SELECT body FROM app_settings WHERE id=1").fetchone()
        if saved:
            settings = json.loads(saved[0])
            # 旧备份没有界面字段时沿用原合同；新字段只包含枚举和本库对象编号。
            if isinstance(settings, dict) and "ui_context" in settings:
                def resolve(kind, resource_id):
                    if kind == "project":
                        row = db.execute("SELECT body FROM projects WHERE id=?", (resource_id,)).fetchone()
                    else:
                        row = db.execute("SELECT body FROM resources WHERE kind=? AND id=?", (kind, resource_id)).fetchone()
                    if not row:
                        raise Fault("RESOURCE_NOT_FOUND", "界面引用的记录不存在。", 404)
                    return json.loads(row[0])
                validate_context(settings["ui_context"], resolve)
        resources = DatabaseResources(path)
        if any(body.get("state") not in TERMINAL or body.get("recovery_required") for _, body in resources.select("attempt")):
            fail("备份包含状态未确认的执行，不能恢复为已完成。")
        if versions[0][0] < 4 and any(True for _ in resources.select("dataset-split", "dataset-split-plan")):
            fail("来源组划分资源需要资料库 v4，不能按旧版语义恢复。")
        return (resources, versions[0][0]) if with_version else resources
    finally:
        db.close()


def split_referenced_files(resources, source_root, files_root, add):
    """从冻结资源核验划分关系；ready 计划的暂存也必须完整随备份保存。"""
    splits = {body['id']: body for _, body in selected_resources(resources, 'dataset-split')}
    plans = {body['id']: body for _, body in selected_resources(resources, 'dataset-split-plan')}
    # 普通旧库不增加模型/数据全量索引；有派生声明而关系丢失时仍须拒绝。
    declared = [body for _, body in selected_resources(resources, 'dataset')
                if 'dataset_split_id' in body or 'dataset_split_role' in body]
    if not splits and not plans and not declared:
        return {}
    from .dataset_splits import verify_ready_plan, verify_split_record
    datasets = {body['id']: body for _, body in selected_resources(resources, 'dataset')}
    models = {body['id']: body for _, body in selected_resources(resources, 'model')}
    references = {}

    def resolve(value):
        path = Path(value)
        if not path.is_absolute() or not path.is_relative_to(source_root):
            fail('来源组资产引用超出原资料库。')
        relative = relative_path(path.relative_to(source_root).as_posix())
        if relative.parts[0] != 'assets':
            fail('来源组资产必须位于本库 assets 目录。')
        return files_root / relative

    for child in declared:
        split = splits.get(child.get('dataset_split_id'))
        role = child.get('dataset_split_role')
        if not split or role not in {'train', 'validation'} or split.get(role + '_dataset_id') != child['id']:
            fail('派生数据缺少完整的训练／验证关系。', 'BACKUP_REFERENCE_MISSING')
    for split in splits.values():
        try:
            references[split['id']] = verify_split_record(split, datasets.__getitem__, resolve)
            model = models[split['model_id']]
            plan = plans[split['plan_id']]
            if (model['project_id'] != split['project_id'] or model['manifest_digest'] != split['model_manifest_digest']
                    or plan['status'] != 'applied' or plan['applied_split_id'] != split['id']):
                fail('来源组划分缺少固定模型或已应用计划。', 'BACKUP_REFERENCE_MISSING')
        except (Fault, KeyError, TypeError, ValueError, OSError) as error:
            raise Fault('BACKUP_REFERENCE_MISSING', '来源组数据或证据不完整，不能生成完整备份。', 409) from error
        for entry in split['manifest']:
            add(Path(split['storage_path']) / relative_path(entry['path']), entry['size'], entry['sha256'])
    for plan in plans.values():
        status = plan.get('status')
        if status in {'preparing', 'cancelling', 'recovery_required'}:
            fail('来源组检查仍在进行或上次状态待核实，请先取消并确认结束。', 'BACKUP_BUSY')
        if status == 'applied':
            split = splits.get(plan.get('applied_split_id'))
            fields = ('project_id', 'plan_digest', 'source_dataset_id', 'source_version_id', 'source_manifest_digest',
                      'model_id', 'model_manifest_digest', 'train_dataset_id', 'validation_dataset_id')
            if not split or split['plan_id'] != plan['id'] or any(split[name] != plan.get(name) for name in fields):
                fail('已应用计划缺少原划分结果。', 'BACKUP_REFERENCE_MISSING')
            continue
        if status == 'cancelled':
            if plan.get('storage_path'):
                fail('已取消计划仍有未确认的暂存引用。', 'BACKUP_BUSY')
            continue
        if status not in {'ready', 'blocked', 'failed'}:
            fail('来源组计划状态不受支持。')
        if not plan.get('storage_path'):
            if status == 'ready':
                fail('待应用计划缺少暂存证据。', 'BACKUP_REFERENCE_MISSING')
            continue
        stage = plan.get('staged_manifest')
        if not isinstance(stage, list) or not stage:
            fail('尚有未整理的划分暂存，请取消计划后重试备份。', 'BACKUP_BUSY')
        directory = resolve(plan['storage_path'])
        if directory.name != '.split-' + plan['id']:
            fail('划分暂存目录不属于该计划。')
        source, model = datasets.get(plan['source_dataset_id']), models.get(plan['model_id'])
        if not source or not model or any(item['project_id'] != plan['project_id'] for item in (source, model)):
            fail('待应用计划缺少同项目原件或模型。', 'BACKUP_REFERENCE_MISSING')
        verify_manifest(directory, stage)
        if status == 'ready':
            try:
                verify_ready_plan(plan, datasets.__getitem__, models.__getitem__, resolve)
            except (Fault, KeyError, TypeError, ValueError, OSError) as error:
                raise Fault('BACKUP_REFERENCE_MISSING', '待应用划分的原件、模型或完整证据不一致。', 409) from error
        for entry in stage:
            add(Path(plan['storage_path']) / relative_path(entry['path']), entry['size'], entry['sha256'])
    return references


def referenced_files(resources, source_root, files_root=None):
    """从数据库冻结记录取得所有必须存在的资产和已声明运行输出。"""
    expected = {}
    files_root = files_root or source_root
    attempts = {body["id"] for _, body in selected_resources(resources, "attempt")}
    checkpoints = {body["id"]: body for _, body in selected_resources(resources, "checkpoint")}
    def add(path, size, checksum):
        path = Path(path)
        if not path.is_absolute() or not path.is_relative_to(source_root):
            fail("数据库引用了工作目录之外的资产。")
        relative = str(path.relative_to(source_root))
        part = relative_path(relative)
        if size is None:
            size = regular_file(files_root / relative).stat().st_size
        if part.parts[0] not in {"assets", "runs", "model-downloads", "market-downloads"} or type(size) is not int or size < 0 or not isinstance(checksum, str) or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            fail("数据库资产引用无效。")
        record = {"path": relative, "size": size, "sha256": checksum}
        if relative in expected and expected[relative] != record:
            fail("同一文件存在不一致的资产声明。")
        expected[relative] = record
    split_references = split_referenced_files(resources, source_root, files_root, add)
    split_records = {body['id']: body for _, body in selected_resources(resources, 'dataset-split')}
    versions = {body['id']: body for _, body in selected_resources(resources, 'market-version')}
    for kind, body in selected_resources(resources, 'model-download', 'market-download'):
        if not re.fullmatch(kind + r'-[0-9a-f]{32}', body['id']) or body['state'] not in {'failed', 'cancelled', 'completed'}:
            fail('下载记录无效或尚未静止，不能完整备份。', 'BACKUP_BUSY')
        if kind == 'model-download':
            manifest = body['manifest']
            if digest(manifest) != body['manifest_digest']:
                fail('模型下载清单摘要不符。')
        else:
            version = versions.get(body['version_id'])
            if not version or digest(version['metadata']) != version['version_digest'] or version['version_digest'] != body['version_digest']:
                fail('市场下载缺少完整的来源版本。')
            manifest = version['metadata']['files']
        declared = {}
        for entry in manifest:
            name = relative_path(entry['path']).as_posix()
            if name in declared or type(entry['size']) is not int or entry['size'] < 0 or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
                fail('下载文件声明无效。')
            declared[name] = entry
        relative = Path(kind + 's') / body['id']
        directory = files_root / relative
        present, received = set(), 0
        if directory.exists() or directory.is_symlink():
            regular_path(directory)
            if not directory.is_dir() or any(path.name != 'files' for path in directory.iterdir()):
                fail('下载缓存目录出现清单外内容。')
            cache = directory / 'files'
            if cache.exists() or cache.is_symlink():
                regular_path(cache)
                if not cache.is_dir():
                    fail('下载缓存的 files 路径不是目录。')
                for path in cache.rglob('*'):
                    if path.is_symlink() or not (path.is_file() or path.is_dir()):
                        fail('下载缓存包含链接或非常规文件。')
                    if path.is_dir():
                        prefix = path.relative_to(cache).as_posix() + '/'
                        if not any(name.startswith(prefix) for name in declared):
                            fail('下载缓存包含清单外目录。')
                        continue
                    name = path.relative_to(cache).as_posix()
                    size = path.stat().st_size
                    if name not in declared or size > declared[name]['size']:
                        fail('下载缓存包含清单外文件或超出声明大小。')
                    checksum = file_hash(path)
                    if body['state'] == 'completed' and (size != declared[name]['size'] or checksum != declared[name]['sha256']):
                        fail('已完成下载的文件已变化。', 'BACKUP_SOURCE_CHANGED')
                    add(source_root / relative / 'files' / name, size, checksum)
                    present.add(name); received += size
        if received < body['received_bytes'] or body['state'] == 'completed' and present != set(declared):
            fail('备份缺少下载记录声明的已收字节。', 'BACKUP_REFERENCE_MISSING')
    for kind, body in resources:
        if kind in {"attempt", "task"}:
            configuration = body.get("snapshot" if kind == "attempt" else "draft", {})
            # 导出任务固定保存 draft:null；它没有训练配置或检查点引用。
            if configuration is None and kind == "task" and body.get("kind") == body.get("operation") == "export":
                configuration = {}
            if not isinstance(configuration, dict):
                fail("任务草稿或运行快照结构无效，无法确认备份资产引用。")
            if 'dataset_split_ref' in configuration:
                reference = configuration['dataset_split_ref']
                if (not isinstance(reference, dict) or split_references.get(reference.get('id')) != reference
                        or split_records[reference['id']]['project_id'] != body['project_id']):
                    fail('任务或运行快照缺少完整且一致的来源组证明。', 'BACKUP_REFERENCE_MISSING')
                split = split_records[reference['id']]
                training_identity = {'dataset_version_id': reference['train_version_id'], 'dataset_manifest_digest': reference['train_manifest_digest'],
                                     'model_manifest_digest': split['model_manifest_digest']}
                recipe_identity = configuration.get('tokenization_recipe_digest')
                if configuration.get('operation') == 'distill' and recipe_identity:
                    recipe = configuration.get('tokenization_recipe', {})
                    if hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest() != recipe_identity or recipe.get('recipe_id') != 'qwen25-offline-distillation-v1':
                        fail('蒸馏执行配方身份不完整。', 'BACKUP_REFERENCE_MISSING')
                    recipe_identity = recipe.get('source_dataset_tokenization_recipe_digest')
                    if not recipe_identity:
                        fail('蒸馏缺少原训练子集的分词配方身份。', 'BACKUP_REFERENCE_MISSING')
                if (configuration.get('dataset_id') != reference['train_dataset_id']
                        or any(name in configuration and configuration[name] != value for name, value in training_identity.items())
                        or recipe_identity is not None and recipe_identity != reference['tokenization_recipe_digest']
                        or 'dataset_manifest' in configuration and digest(configuration['dataset_manifest']) != reference['train_manifest_digest']
                        or 'runtime' in configuration and (not isinstance(configuration['runtime'], dict)
                                                           or configuration['runtime'].get('max_seq_length') != reference['max_seq_length'])):
                    fail('训练配置与其来源组证明不是同一训练子集或检查身份。', 'BACKUP_REFERENCE_MISSING')
            reference = configuration.get("checkpoint_ref")
            checkpoint_id = configuration.get("checkpoint_id")
            if checkpoint_id and checkpoint_id not in checkpoints:
                fail("数据库恢复任务缺少来源检查点。")
            if reference and not any(reference == {"path": item["storage_path"], "manifest_digest": item["manifest_digest"], "source_attempt_id": item["source_attempt_id"]} for item in checkpoints.values()):
                fail("运行快照的检查点引用没有完整来源记录。")
        if kind in {"model", "dataset", "adapter", "material"}:
            for entry in body["manifest"]:
                add(Path(body["storage_path"]) / relative_path(entry["path"]), entry["size"], entry["sha256"])
        elif kind == "artifact":
            add(body["storage_path"], body["size"], body["sha256"])
        elif kind == "evaluation-plan":
            for name in ("dataset", "criteria"):
                for entry in body[f"evaluation_{name}_manifest"]:
                    path = Path(body[f"evaluation_{name}_path"])
                    add(path.parent / relative_path(entry["path"]), entry["size"], entry["sha256"])
        elif kind == "checkpoint":
            path = Path(body["storage_path"])
            if body["source_attempt_id"] not in attempts:
                fail("检查点缺少来源运行记录。")
            run = source_root / "runs" / relative_path(body["source_attempt_id"])
            relative = path.relative_to(run) if path.is_relative_to(run) else Path("invalid")
            if len(relative.parts) != 3 or relative.parts[0] != "checkpoints" or relative.name != "manifest.json":
                fail("检查点引用不在来源运行的完整检查点目录。")
            physical = regular_file(files_root / path.relative_to(source_root))
            manifest = read_json(physical)
            if manifest != body["manifest"] or manifest.get("schema_version") != "mlx-training-checkpoint-v1" or manifest.get("complete") is not True or manifest.get("digest") != body["manifest_digest"] or digest({key: value for key, value in manifest.items() if key != "digest"}) != body["manifest_digest"] or manifest.get("source_attempt_id") != body["source_attempt_id"] or manifest.get("source_snapshot_digest") != body["source_snapshot_digest"]:
                fail("检查点原始清单与数据库来源声明不一致。")
            if len(manifest["files"]) != 1 or manifest["files"][0]["path"] != "state.safetensors":
                fail("检查点未声明完整优化状态。")
            add(path, physical.stat().st_size, file_hash(physical))
            for entry in manifest["files"]:
                add(path.parent / relative_path(entry["path"]), entry["size"], entry["sha256"])
        elif kind == "attempt" and body.get("output_manifest_ref"):
            attempt_id = body["id"]
            if relative_path(attempt_id).name != attempt_id:
                fail("执行编号不是单层路径。")
            for entry in body["output_manifest_ref"]["artifacts"]:
                add(source_root / "runs" / attempt_id / "output" / relative_path(entry["path"]), entry.get("size"), entry["sha256"])
    return expected


def checked_copy(source, destination, record):
    source = regular_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    checksum, count = hashlib.sha256(), 0
    with source.open("rb") as original, destination.open("xb") as target:
        while block := original.read(4 * 1024 * 1024):
            target.write(block)
            checksum.update(block)
            count += len(block)
        target.flush()
        os.fsync(target.fileno())
    if count != record["size"] or checksum.hexdigest() != record["sha256"]:
        fail("复制期间源文件缺失或发生变化，未完成备份或恢复。", "BACKUP_SOURCE_CHANGED")


def publish(temporary, final):
    # macOS 的 RENAME_EXCL 保证即使检查后目标被创建，也不会覆盖它。
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, "renamex_np", None)
    if rename is None:
        fail("当前完整备份与恢复仅在 macOS 上完成原子发布验证。", "RESTORE_PLATFORM_UNVERIFIED")
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(os.fsencode(temporary), os.fsencode(final), 0x00000004) != 0:
        raise OSError(ctypes.get_errno(), "备份或恢复目录无法无覆盖发布")


class Backup:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.plans = {}
        self.lock = threading.Lock()
        self.records = service.root / "backups" / ".commands"
        self.records.mkdir(exist_ok=True, mode=0o700)
        regular_path(self.records)

    def write_record(self, name, value):
        temporary = self.records / ("." + identifier("record"))
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(encode(value) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.records / name)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def backup_summary(manifest, path):
        return {"id": manifest["id"], "backup_path": str(path), "scope": manifest["scope"], "contains_asset_files": True,
                "created_at": manifest["created_at"], "asset_count": manifest["reference_file_count"],
                "file_count": len(manifest["files"]), "total_bytes": sum(item["size"] for item in manifest["files"]),
                "manifest_digest": manifest["manifest_digest"], "verification_required": True,
                "message": "数据库、引用资产和原运行证据已完整备份，可预检查后恢复到新目录。"}

    def list_backups(self):
        items = []
        for path in sorted((self.service.root / "backups").glob("backup-*")):
            try:
                manifest = read_json(regular_file(path / "manifest.json"))
                if manifest.get("schema_version") == VERSION and manifest.get("complete") is True:
                    items.append(self.backup_summary(manifest, path))
            except (Fault, OSError, ValueError, KeyError, TypeError):
                continue
        return {"items": items}

    def list_restores(self):
        items = []
        for path in sorted(self.records.glob("restore-*.json")):
            try:
                record = read_json(regular_file(path))
                if "response" in record:
                    items.append({**record["response"], "state": record["state"], "verification_required": True, "verified": False})
            except (Fault, OSError, ValueError, KeyError, TypeError):
                continue
        return {"items": items}

    def idle(self):
        if self.service.closed.is_set() or any(item["state"] not in TERMINAL or item.get("recovery_required") for item in self.store.list("attempt")) or any(thread.is_alive() for thread in self.service.threads) or any(process.poll() is None or self.service.group_present(process.pid) for process in self.service.processes.values()):
            fail("请在运行、收集、导出及状态核实全部完成后创建备份。", "BACKUP_BUSY")
        if any(item['state'] in {'queued', 'downloading', 'verifying'} for kind in ('model-download', 'market-download') for item in self.store.list(kind)):
            fail('请先停止下载或等待文件校验完成，再创建备份。', 'BACKUP_BUSY')

    def create(self, key=None):
        if key is not None and (not key or len(key) > 200 or any(ord(char) < 33 or ord(char) > 126 for char in key)):
            fail("备份需要有效的 Idempotency-Key。", "IDEMPOTENCY_KEY_REQUIRED")
        command_digest = digest(key) if key else None
        backup_id = "backup-" + command_digest[:32] if key else identifier("backup")
        root = self.service.root
        parent = regular_path(root / "backups")
        final = parent / backup_id
        with self.lock:
            if final.exists():
                manifest = self.verify(final)
                if manifest.get("command_key_digest") != command_digest:
                    fail("此备份命令与已保存记录不一致。", "IDEMPOTENCY_CONFLICT")
                return self.backup_summary(manifest, final)
            temporary = Path(tempfile.mkdtemp(prefix=".backup-", dir=parent))
            owns_maintenance = False
            try:
                # 缓存续传会原地写入，复制期间冻结写请求，列表读取仍可继续。
                with self.store.lock:
                    self.idle()
                    if self.service.maintenance_pending or self.service.active_writes > 1:
                        fail('还有写入请求正在完成，请稍后备份。', 'BACKUP_BUSY')
                    self.service.maintenance_pending = True
                    owns_maintenance = True
                    copied = sqlite3.connect(temporary / "control.sqlite3")
                    try:
                        self.store.db.backup(copied)
                        copied.execute("PRAGMA journal_mode=DELETE")
                    finally:
                        copied.close()
                resources, schema_version = database(temporary / "control.sqlite3", with_version=True)
                files = referenced_files(resources, root)
                referenced_count = len(files)
                # 运行日志和原始快照是历史证据，同步保留已登记执行的运行目录。
                for _, body in selected_resources(resources, "attempt"):
                    run = root / "runs" / relative_path(body["id"])
                    if run.exists():
                        regular_path(run)
                        for path in run.rglob("*"):
                            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                                fail("运行证据目录包含链接或非常规文件。")
                            if path.is_file():
                                relative = str(path.relative_to(root))
                                files.setdefault(relative, {"path": relative, "size": path.stat().st_size, "sha256": file_hash(path)})
                db_file = temporary / "control.sqlite3"
                if len(files) > 50000 or sum(item["size"] for item in files.values()) + db_file.stat().st_size > MAX_BACKUP_BYTES:
                    fail("首期完整备份最多 50000 个引用文件、总计 32 GiB，元数据库不超过 1 GiB。")
                for record in files.values():
                    checked_copy(root / record["path"], temporary / record["path"], record)
                files["control.sqlite3"] = {"path": "control.sqlite3", "size": db_file.stat().st_size, "sha256": file_hash(db_file)}
                manifest = {"schema_version": VERSION, "database_schema_version": schema_version, "id": backup_id, "created_at": now(),
                            "source_data_root": str(root), "scope": "database_and_referenced_assets_and_run_evidence",
                            "contains_asset_files": True, "complete": True, "reference_file_count": referenced_count,
                            "command_key_digest": command_digest,
                            "files": sorted(files.values(), key=lambda item: item["path"])}
                manifest["manifest_digest"] = digest(manifest)
                (temporary / "manifest.json").write_text(encode(manifest) + "\n", encoding="utf-8")
                self.verify(temporary)
                publish(temporary, final)
                return self.backup_summary(manifest, final)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                raise Fault("BACKUP_FAILED", "备份文件或数据库校验失败，未登记为完整备份。", 409) from error
            finally:
                if owns_maintenance:
                    with self.store.lock:
                        self.service.maintenance_pending = False
                if temporary.exists():
                    shutil.rmtree(temporary)

    def verify(self, directory):
        directory = regular_path(directory)
        manifest = read_json(regular_file(directory / "manifest.json"))
        identity = manifest.get("manifest_digest")
        if manifest.get("schema_version") != VERSION or type(manifest.get("database_schema_version")) is not int or manifest['database_schema_version'] not in SUPPORTED_VERSIONS or manifest.get("complete") is not True or manifest.get("contains_asset_files") is not True or identity != digest({key: value for key, value in manifest.items() if key != "manifest_digest"}):
            fail("备份版本、完整标记或清单摘要无效。")
        source_root = Path(manifest["source_data_root"])
        if not source_root.is_absolute() or ".." in source_root.parts:
            fail("备份原始数据目录身份无效。")
        records = manifest["files"]
        if not isinstance(records, list) or not 1 <= len(records) <= 50001:
            fail("备份文件清单无效。")
        files, total = {}, 0
        for record in records:
            relative = relative_path(record["path"])
            if set(record) != {"path", "size", "sha256"} or record["path"] in files or relative.parts[0] not in {"assets", "runs", "model-downloads", "market-downloads", "control.sqlite3"} or (relative.parts[0] == "control.sqlite3" and len(relative.parts) != 1) or type(record["size"]) is not int or record["size"] < 0:
                fail("备份包含不支持的文件记录。")
            path = regular_file(directory / relative)
            total += record["size"]
            if path.stat().st_size != record["size"] or file_hash(path) != record["sha256"]:
                fail("备份文件缺失或摘要不符。", "BACKUP_SOURCE_CHANGED")
            files[record["path"]] = record
        if total > MAX_BACKUP_BYTES:
            fail("备份超过当前恢复大小限制。")
        actual = set()
        for path in directory.rglob("*"):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                fail("备份包含链接或非常规文件。")
            if path.is_file():
                actual.add(str(path.relative_to(directory)))
        if actual != set(files) | {"manifest.json"} or "control.sqlite3" not in files:
            fail("备份文件集合与清单不一致。")
        resources, schema_version = database(directory / "control.sqlite3", with_version=True)
        if manifest['database_schema_version'] != schema_version:
            fail('备份声明的数据库版本与实际版本不一致。')
        referenced = referenced_files(resources, source_root, directory)
        if any(files.get(path) != record for path, record in referenced.items()):
            fail("备份未覆盖数据库引用的完整资产与运行产物。", "BACKUP_REFERENCE_MISSING")
        if any(path not in referenced for path in files if Path(path).parts[0] in {'model-downloads', 'market-downloads'}):
            fail('备份包含没有来源记录的下载缓存。')
        return manifest

    def source(self, payload):
        roots = [regular_path(path) for path in self.service.settings.import_roots]
        roots.append(regular_path(self.service.root / "backups"))
        if payload.get("backup_grant_id"):
            grant = self.service.grants.get(payload["backup_grant_id"])
            if grant is None:
                fail("备份目录读取授权已失效，请重新选择。", "IMPORT_GRANT_EXPIRED")
            roots.append(grant)
        return authorized_path(payload["backup_path"], roots)

    def plan(self, payload):
        try:
            source = self.source(payload)
            target = self.service.delivery.target(payload["target_dir"], payload.get("target_grant_id"))
            if target == source or target.is_relative_to(source):
                fail("恢复目标不能位于备份包内。", "RESTORE_TARGET_INVALID")
            manifest = self.verify(source)
            plan_id = identifier("restore-plan")
            final = target / ("ailab-restored-" + plan_id.removeprefix("restore-plan-"))
            total = sum(entry["size"] for entry in manifest["files"])
            if shutil.disk_usage(target).free < total + 16 * 1024**2:
                fail("恢复目标可用空间不足。", "DISK_FULL")
            result = {"id": plan_id, "backup_path": str(source), "target_dir": str(target), "restored_path": str(final),
                      "manifest_digest": manifest["manifest_digest"], "source_data_root": manifest["source_data_root"],
                      "file_count": len(manifest["files"]), "total_bytes": total, "can_restore": True, "blocking": [],
                      "path_mapping": {manifest["source_data_root"]: str(final)}, "changes_current_library": False,
                      "evidence_policy": "原始快照与产物文件按原字节保留；数据库运行引用迁移并保留原快照及摘要。"}
            result["plan_digest"] = digest(result)
            with self.lock:
                self.plans[plan_id] = {"result": result, "payload": dict(payload)}
                self.write_record(plan_id + ".json", self.plans[plan_id])
            return result
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            raise Fault("BACKUP_INVALID", "备份预检查失败，未创建恢复目录。", 409) from error

    def remap_database(self, path, source_root, target_root, backup_digest):
        db = sqlite3.connect(path)
        try:
            db.execute("PRAGMA trusted_schema=OFF")
            after = 0
            while True:
                rows = db.execute("SELECT rowid,id,kind,body FROM resources WHERE rowid>? ORDER BY rowid LIMIT 512", (after,)).fetchall()
                if not rows:
                    break
                for _, resource_id, kind, text in rows:
                    original = json.loads(text)
                    updated = remap_reference_paths(original, source_root, target_root)
                    if kind == "execution-target":
                        # 恢复的工作库必须重新授权连接，不继承原机器的钥匙串引用。
                        updated.update(credential_ref=None, credential_cleanup_refs=[], revision=int(original.get("revision", 0)) + 1,
                                       connection_state="unchecked", protocol_ready=False, network_remote_ready=False,
                                       nvidia_ready=False, nvidia_environment=None, adapters={}, checked_at=None, last_error=None)
                    if kind == "attempt" and original.get("snapshot"):
                        updated["restoration"] = {"backup_manifest_digest": backup_digest, "original_snapshot": original["snapshot"],
                                                  "original_snapshot_digest": original.get("snapshot_digest"),
                                                  "path_mapping": {str(source_root): str(target_root)},
                                                  "historical_artifacts_unchanged": True}
                        if original.get("restoration"):
                            updated["restoration"]["previous_restoration"] = original["restoration"]
                        updated["snapshot_digest"] = digest(updated["snapshot"])
                    db.execute("UPDATE resources SET body=? WHERE id=?", (encode(updated), resource_id))
                after = rows[-1][0]
            # 原机器执行器路径和幂等响应不能授权新环境或重放旧目录的写入。
            saved = db.execute("SELECT body FROM app_settings WHERE id=1").fetchone()
            if saved:
                settings = json.loads(saved[0]); settings["worker_python"] = None; settings["revision"] += 1
                for name in ("media_python", "audio_python"):
                    if name in settings:
                        settings[name] = None
                db.execute("UPDATE app_settings SET body=? WHERE id=1", (encode(settings),))
            db.execute("DELETE FROM commands")
            db.commit()
        finally:
            db.close()
        database(path)

    def get_restore(self, restore_id):
        if not restore_id.startswith("restore-") or len(restore_id) != 40 or any(char not in "0123456789abcdef" for char in restore_id[8:]):
            fail("恢复记录编号无效。", "RESTORE_NOT_FOUND")
        try:
            record = read_json(regular_file(self.records / (restore_id + ".json")))
            response, expected = record["response"], record["receipt"]
            final = regular_path(response["restored_path"])
            if final == self.service.root or final.is_relative_to(self.service.root):
                fail("恢复记录不能指向当前库。", "RESTORE_TARGET_INVALID")
            receipt = read_json(regular_file(final / "restoration.json"))
            if receipt != expected:
                fail("恢复回执与原命令不一致。", "RESTORE_INCOMPLETE")
            database_file = regular_file(final / "control.sqlite3")
            if file_hash(database_file) != receipt["restored_database_sha256"]:
                fail("恢复数据库已变化或尚未完整发布，请重新核实。", "RESTORE_INCOMPLETE")
            database(database_file)
            for entry in receipt["original_evidence_files"]:
                path = regular_file(final / relative_path(entry["path"]))
                if path.stat().st_size != entry["size"] or file_hash(path) != entry["sha256"]:
                    fail("恢复后的引用资产或原始证据不完整。", "RESTORE_INCOMPLETE")
            record["state"] = "succeeded"
            self.write_record(restore_id + ".json", record)
            return {**response, "verified": True, "verification_required": False}
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            raise Fault("RESTORE_INCOMPLETE", "恢复记录或文件未通过完整性核实。", 409) from error

    def activate(self, restore_id):
        with self.lock:
            result = self.get_restore(restore_id)
            with self.store.lock:
                self.idle()
                if self.service.active_writes != 1 or self.service.activation_pending:
                    fail("还有写入请求正在完成，请稍后再切换工作库。", "LIBRARY_BUSY")
                self.service.activation_pending = True
                self.service.activation_deadline = time.monotonic() + 30
            return {**result, "activation_ready": True}

    def cancel_activation(self):
        with self.store.lock:
            self.service.activation_pending = False
            self.service.activation_deadline = 0
        return {"activation_pending": False}

    def restore(self, payload, key):
        if not key or len(key) > 200 or any(ord(char) < 33 or ord(char) > 126 for char in key):
            fail("恢复需要有效的 Idempotency-Key。", "IDEMPOTENCY_KEY_REQUIRED")
        with self.lock:
            command_digest = digest(key)
            restore_id = "restore-" + command_digest[:32]
            command_file = self.records / (restore_id + ".json")
            if command_file.exists():
                command = read_json(regular_file(command_file))
                if command["request_digest"] != digest(payload) or command["command_key_digest"] != command_digest:
                    fail("此命令键已用于其他恢复计划。", "IDEMPOTENCY_CONFLICT")
                if "response" in command and Path(command["response"]["restored_path"]).exists():
                    return self.get_restore(restore_id)
            saved = self.plans.get(payload["plan_id"])
            if saved is None and relative_path(payload["plan_id"]).name == payload["plan_id"]:
                saved_path = self.records / (payload["plan_id"] + ".json")
                if saved_path.is_file():
                    saved = read_json(regular_file(saved_path))
            if saved is None:
                fail("恢复计划已失效，请重新预检查。", "RESTORE_PLAN_EXPIRED")
            plan, requested = saved["result"], saved["payload"]
            if payload["plan_digest"] != plan["plan_digest"]:
                fail("恢复计划摘要不一致。", "RESTORE_PLAN_CHANGED")
            source = self.source(requested)
            target = self.service.delivery.target(requested["target_dir"], requested.get("target_grant_id"))
            final = Path(plan["restored_path"])
            if final.exists() or final.is_symlink() or final.parent != target:
                fail("恢复目录已存在或目标已变化，未覆盖文件。", "RESTORE_TARGET_EXISTS")
            temporary = None
            try:
                manifest = self.verify(source)
                if manifest["manifest_digest"] != plan["manifest_digest"]:
                    fail("备份在预检查后发生变化，请重新检查。", "RESTORE_PLAN_CHANGED")
                if shutil.disk_usage(target).free < plan["total_bytes"] + 16 * 1024**2:
                    fail("恢复目标可用空间不足。", "DISK_FULL")
                temporary = Path(tempfile.mkdtemp(prefix=".ailab-restore-", dir=target))
                for record in manifest["files"]:
                    checked_copy(source / record["path"], temporary / record["path"], record)
                self.remap_database(temporary / "control.sqlite3", Path(plan["source_data_root"]), final, manifest["manifest_digest"])
                # 发布前再次按新库路径核验来源组；request.json 保留原字节，不用于执行。
                split_referenced_files(database(temporary / 'control.sqlite3'), final, temporary, lambda *_: None)
                (temporary / "backups").mkdir()
                (temporary / "assets").mkdir(exist_ok=True)
                (temporary / "runs").mkdir(exist_ok=True)
                receipt = {"schema_version": VERSION, "backup_manifest_digest": manifest["manifest_digest"],
                           "original_database_sha256": next(item["sha256"] for item in manifest["files"] if item["path"] == "control.sqlite3"),
                           "restored_database_sha256": file_hash(temporary / "control.sqlite3"), "path_mapping": plan["path_mapping"],
                           "original_evidence_files": [item for item in manifest["files"] if item["path"] != "control.sqlite3"],
                           "old_commands_replay_disabled": True, "external_worker_selection_cleared": True,
                           "restore_id": restore_id, "command_key_digest": command_digest,
                           "request_digest": digest(payload), "plan_digest": plan["plan_digest"]}
                (temporary / "restoration.json").write_text(encode(receipt) + "\n", encoding="utf-8")
                response = {"id": restore_id, "state": "succeeded", "restored_path": str(final),
                            "manifest_digest": manifest["manifest_digest"], "file_count": plan["file_count"],
                            "changes_current_library": False, "message": "已完整恢复到独立新目录；当前工作库未切换。"}
                command = {"request_digest": digest(payload), "command_key_digest": command_digest,
                           "state": "publishing", "response": response, "receipt": receipt}
                # 发布前写入命令与精确回执；崩溃后可用同一命令核实已发布目录。
                self.write_record(restore_id + ".json", command)
                if final.exists() or final.is_symlink():
                    fail("恢复目录已被其他操作创建，未覆盖。", "RESTORE_TARGET_EXISTS")
                regular_path(target)
                publish(temporary, final)
                return self.get_restore(restore_id)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
                raise Fault("RESTORE_FAILED", "恢复未完成，当前工作库未被覆盖。", 409) from error
            finally:
                if temporary is not None and temporary.exists():
                    shutil.rmtree(temporary)
