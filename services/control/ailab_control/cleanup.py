"""只把当前库无引用的不可变资产移入受管回收区；保留原位置并支持恢复。"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat

from .assets import file_hash, regular_path
from .backup import publish, read_json
from .storage import Fault, digest, encode, identifier, now

HEX = re.compile(r"[0-9a-f]{64}")
RECORD = re.compile(r"cleanup-[0-9a-f]{32}")
TERMINAL = {"succeeded", "failed", "cancelled"}


def fail(code, message):
    raise Fault(code, message, 409)


def fingerprint(path):
    value = path.lstat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_mode, value.st_nlink]


def tree(path):
    """摘要计算不持有数据库锁，且不接受链接、可写文件或硬链接。"""
    root = regular_path(path)
    if not root.is_dir():
        fail("CLEANUP_UNSAFE_ASSET", "资产不是普通目录，未纳入清理。")
    signatures = {".": fingerprint(root)}
    files = []
    entries = sorted(root.rglob("*"))
    if len(entries) > 10000:
        fail("CLEANUP_TOO_LARGE", "单个资产超过 10000 个目录项，未纳入本次清理。")
    for item in entries:
        before = fingerprint(item)
        mode = before[4]
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            fail("CLEANUP_UNSAFE_ASSET", "资产含链接或非常规文件，未纳入清理。")
        relative = item.relative_to(root).as_posix()
        signatures[relative] = before
        if stat.S_ISDIR(mode):
            continue
        if mode & 0o222 or before[5] != 1:
            fail("CLEANUP_UNSAFE_ASSET", "资产含可写文件或硬链接，未纳入清理。")
        checksum = file_hash(item)
        if fingerprint(item) != before:
            fail("CLEANUP_ASSET_CHANGED", "摘要检查期间资产发生变化，请重新检查。")
        files.append({"path": relative, "size": before[2], "sha256": checksum, "mode": stat.S_IMODE(mode)})
    if fingerprint(root) != signatures["."]:
        fail("CLEANUP_ASSET_CHANGED", "摘要检查期间资产目录发生变化。")
    return {"files": files, "signatures": signatures, "manifest_digest": digest(files),
            "total_bytes": sum(item["size"] for item in files), "file_count": len(files)}


def same_tree(path, expected):
    current = tree(path)
    if current["files"] != expected["files"] or current["signatures"] != expected["signatures"]:
        fail("CLEANUP_ASSET_CHANGED", "资产文件与已确认清单不一致，未移动文件。")
    return current


def unchanged(path, signatures):
    if set(signatures) != {"."} | {item.relative_to(path).as_posix() for item in path.rglob("*")}:
        return False
    return all(fingerprint(path if name == "." else path / name) == value for name, value in signatures.items())


class Cleanup:
    def __init__(self, service):
        self.service, self.store, self.root = service, service.store, service.root
        self.assets = regular_path(self.root / "assets")
        self.trash = self.root / "trash"
        for directory in (self.trash, self.trash / "plans", self.trash / "records", self.trash / "items"):
            directory.mkdir(exist_ok=True, mode=0o700)
            regular_path(directory)

    def write(self, directory, name, value):
        regular_path(directory)
        if directory == self.trash / "records":
            value = {key: item for key, item in value.items() if key != "record_digest"}
            value["record_digest"] = digest(value)
        temporary = directory / ("." + identifier("record"))
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(encode(value) + "\n")
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, directory / name)
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def read(path):
        try:
            return read_json(regular_path(path))
        except (OSError, ValueError, UnicodeError) as error:
            raise Fault("CLEANUP_INVALID", "清理计划或回收记录无法读取，未移动文件；请保留原记录并核实。", 409) from error

    def idle(self):
        if self.service.closed.is_set() or self.service.activation_pending or self.service.dataset_splits.unresolved() or any(item["state"] not in TERMINAL or item.get("recovery_required") for item in self.store.list("attempt")) or any(thread.is_alive() for thread in self.service.threads) or any(process.poll() is None or self.service.group_present(process.pid) for process in self.service.processes.values()):
            fail("CLEANUP_BUSY", "请先完成运行、状态核实与工作库切换，再管理回收区。")

    @contextmanager
    def guard(self, writing=False):
        lock = self.service.backup_manager.lock
        if not lock.acquire(blocking=False):
            fail("CLEANUP_BUSY", "备份、恢复或其他存储维护正在进行，请稍后重试。")
        gated = False
        try:
            with self.store.lock:
                self.idle()
                if getattr(self.service, "maintenance_pending", False) or self.service.active_writes > 1:
                    fail("CLEANUP_BUSY", "还有写入操作正在完成，请稍后重试。")
                if writing:
                    self.service.maintenance_pending = True
                    gated = True
            yield
        except OSError as error:
            raise Fault("CLEANUP_IO_ERROR", "本机文件操作未完成，已有文件和回收记录均保留；请核实原命令后重试。", 409) from error
        finally:
            if gated:
                with self.store.lock:
                    self.service.maintenance_pending = False
            lock.release()

    def rows(self):
        return {table: [tuple(row) for row in self.store.db.execute(query)] for table, query in {
            "resources": "SELECT id,body FROM resources ORDER BY id",
            "events": "SELECT attempt_id,sequence,body FROM events ORDER BY attempt_id,sequence",
            "commands": "SELECT scope,key,response FROM commands ORDER BY scope,key",
            "settings": "SELECT id,body FROM app_settings ORDER BY id",
        }.items()}

    def reference_files(self):
        paths = list((self.root / "backups").glob("backup-*/manifest.json"))
        paths.extend((self.root / "backups/.commands").glob("*.json"))
        if (self.root / "restoration.json").exists():
            paths.append(self.root / "restoration.json")
        return sorted(paths)

    def references(self):
        with self.store.lock:
            rows = self.rows()
        protected = set()
        def protect(value):
            if isinstance(value, dict):
                for item in value.values():
                    protect(item)
            elif isinstance(value, list):
                for item in value:
                    protect(item)
            elif isinstance(value, str) and value.startswith("/"):
                for candidate in (Path(value), Path(os.path.normpath(value))):
                    if candidate == self.assets:
                        protected.add("*")
                    elif candidate.is_relative_to(self.assets):
                        protected.add(candidate.relative_to(self.assets).parts[0])
        for entries in rows.values():
            for row in entries:
                protect(json.loads(row[-1]))
        documents, signatures = {}, {}
        for path in self.reference_files():
            regular_path(path)
            before = fingerprint(path)
            value = read_json(path)
            if not isinstance(value, dict):
                fail("CLEANUP_REFERENCE_INVALID", "备份或恢复记录无法完整核验，未生成清理计划。")
            if value.get("state") == "publishing":
                fail("CLEANUP_BUSY", "恢复结果仍待核实，请先核实恢复记录。")
            protect(value)
            for field in ("files", "original_evidence_files"):
                if field in value and (not isinstance(value[field], list) or any(not isinstance(item, dict) for item in value[field])):
                    fail("CLEANUP_REFERENCE_INVALID", "备份或恢复引用清单损坏，未生成清理计划。")
            if value.get("source_data_root") == str(self.root):
                for item in value.get("files", []):
                    if str(item.get("path", "")).startswith("assets/"):
                        protect(str(self.root / item["path"]))
            if path == self.root / "restoration.json":
                for item in value.get("original_evidence_files", []):
                    if str(item.get("path", "")).startswith("assets/"):
                        protect(str(self.root / item["path"]))
            if fingerprint(path) != before:
                fail("CLEANUP_REFERENCE_CHANGED", "引用记录在检查期间发生变化。")
            documents[str(path)] = value
            signatures[str(path)] = before
        return {"digest": digest({"rows": rows, "documents": documents}), "rows": rows,
                "protected": protected, "signatures": signatures}

    def cas(self, references):
        self.idle()
        if self.rows() != references["rows"] or [str(path) for path in self.reference_files()] != sorted(references["signatures"]) or any(fingerprint(Path(path)) != value for path, value in references["signatures"].items()):
            fail("CLEANUP_REFERENCE_CHANGED", "计划后新增或修改了引用，请重新检查清理范围。")

    @staticmethod
    def public_item(item):
        return {key: item[key] for key in ("asset_id", "source_path", "total_bytes", "file_count", "manifest_digest", "reason", "trash_path") if key in item}

    def public(self, value):
        result = {key: item for key, item in value.items() if key not in {"items", "reference_digest", "command_key_digest", "request_digest", "restore_command", "record_digest"}}
        result["items"] = [self.public_item(item) for item in value["items"]]
        result["can_restore"] = value.get("state") in {"moving", "trashed", "restoring", "needs_attention"}
        return result

    def plan(self, payload=None):
        if payload not in (None, {}):
            fail("CLEANUP_INVALID", "清理范围固定为当前库的无引用资产。")
        with self.guard():
            references = self.references()
            items, retained, skipped = [], 0, []
            for path in sorted(self.assets.iterdir()):
                if not HEX.fullmatch(path.name):
                    continue
                if "*" in references["protected"] or path.name in references["protected"]:
                    retained += 1
                    continue
                try:
                    details = tree(path)
                except Fault as error:
                    skipped.append({"path": str(path), "reason": error.message})
                    continue
                items.append({"asset_id": path.name, "source_path": str(path), **details,
                              "reason": "当前项目、运行、检查点、备份与恢复记录均未引用此资产。"})
                if len(items) > 100 or sum(item["file_count"] for item in items) > 10000 or sum(item["total_bytes"] for item in items) > 32 * 1024**3:
                    fail("CLEANUP_TOO_LARGE", "当前清理计划最多 100 个资产、10000 个文件、32 GiB。")
            with self.store.lock:
                self.cas(references)
            value = {"id": identifier("cleanup-plan"), "created_at": now(), "data_root": str(self.root), "items": items,
                     "reference_digest": references["digest"], "total_bytes": sum(item["total_bytes"] for item in items),
                     "asset_count": len(items), "file_count": sum(item["file_count"] for item in items),
                     "retained_asset_count": retained, "skipped": skipped, "can_execute": bool(items),
                     "permanent_delete": False, "destination": str(self.trash), "requires_confirmation": True}
            value["plan_digest"] = digest(value)
            self.write(self.trash / "plans", value["id"] + ".json", value)
            return self.public(value)

    def read_plan(self, plan_id):
        if not isinstance(plan_id, str) or not re.fullmatch(r"cleanup-plan-[0-9a-f]{32}", plan_id):
            fail("CLEANUP_PLAN_INVALID", "清理计划编号无效。")
        value = self.read(self.trash / "plans" / (plan_id + ".json"))
        if not isinstance(value, dict) or value.get("id") != plan_id or value.get("data_root") != str(self.root) or value.get("plan_digest") != digest({key: item for key, item in value.items() if key != "plan_digest"}):
            fail("CLEANUP_PLAN_CHANGED", "清理计划已变化，请重新检查。")
        items = value.get("items")
        if not isinstance(items, list) or len(items) > 100:
            fail("CLEANUP_PLAN_INVALID", "清理计划的资产清单损坏。")
        seen = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("asset_id"), str) or not HEX.fullmatch(item["asset_id"]) or item["asset_id"] in seen or item.get("source_path") != str(self.assets / item["asset_id"]):
                fail("CLEANUP_PLAN_INVALID", "清理计划包含无效或越界资产。")
            seen.add(item["asset_id"])
            files, signatures = item.get("files"), item.get("signatures")
            if not isinstance(files, list) or not isinstance(signatures, dict) or "." not in signatures or item.get("manifest_digest") != digest(files):
                fail("CLEANUP_PLAN_INVALID", "清理计划的文件摘要损坏。")
            for relative, signature in signatures.items():
                path = Path(relative)
                if (relative != "." and (path.is_absolute() or ".." in path.parts or path.as_posix() != relative)) or not isinstance(signature, list) or len(signature) != 6 or any(type(number) is not int for number in signature):
                    fail("CLEANUP_PLAN_INVALID", "清理计划的文件位置记录损坏。")
            if any(not isinstance(file, dict) or file.get("path") not in signatures for file in files):
                fail("CLEANUP_PLAN_INVALID", "清理计划文件与位置清单不一致。")
        return value

    def record(self, cleanup_id):
        if not isinstance(cleanup_id, str) or not RECORD.fullmatch(cleanup_id):
            fail("CLEANUP_NOT_FOUND", "清理记录编号无效。")
        value = self.read(self.trash / "records" / (cleanup_id + ".json"))
        if not isinstance(value, dict) or value.get("id") != cleanup_id or value.get("data_root") != str(self.root) or value.get("record_digest") != digest({key: item for key, item in value.items() if key != "record_digest"}):
            fail("CLEANUP_INVALID", "回收区记录与当前工作库不一致。")
        plan = self.read_plan(value.get("plan_id"))
        expected = [{**item, "trash_path": str(self.trash / "items" / cleanup_id / item["asset_id"])} for item in plan["items"]]
        if value.get("items") != expected or any(value.get(key) != plan.get(key) for key in ("plan_digest", "reference_digest", "total_bytes", "asset_count", "file_count")) or value.get("state") not in {"moving", "trashed", "restoring", "restored"}:
            fail("CLEANUP_INVALID", "回收区记录与原始清理计划不一致。")
        return value

    def get(self, cleanup_id):
        return self.public(self.record(cleanup_id))

    def list_items(self):
        items, unreadable = [], []
        for path in sorted((self.trash / "records").glob("cleanup-*.json")):
            try:
                items.append(self.get(path.stem))
            except (Fault, OSError, ValueError, TypeError, KeyError):
                unreadable.append(str(path))
        return {"items": list(reversed(items)), "unreadable_records": unreadable}

    @staticmethod
    def key(value):
        if not isinstance(value, str) or not value or len(value) > 200 or any(ord(char) < 33 or ord(char) > 126 for char in value):
            fail("IDEMPOTENCY_KEY_REQUIRED", "清理与恢复需要有效的 Idempotency-Key。")
        return digest(value)

    def execute(self, payload, key):
        if not isinstance(payload, dict) or set(payload) != {"plan_id", "plan_digest"}:
            fail("CLEANUP_PLAN_INVALID", "执行清理需要完整的已确认计划。")
        key_digest = self.key(key)
        cleanup_id = "cleanup-" + key_digest[:32]
        with self.guard(writing=True):
            path = self.trash / "records" / (cleanup_id + ".json")
            if path.exists():
                record = self.record(cleanup_id)
                if record["request_digest"] != digest(payload) or record["command_key_digest"] != key_digest:
                    fail("IDEMPOTENCY_CONFLICT", "此命令已用于另一份清理计划。")
                if record["state"] in {"trashed", "restored"}:
                    return self.public(record)
                if record["state"] == "restoring":
                    fail("CLEANUP_BUSY", "此清理记录正在恢复，请继续核实原恢复命令。")
            else:
                plan_id = payload.get("plan_id", "")
                plan = self.read_plan(plan_id)
                if plan["plan_digest"] != payload.get("plan_digest") or not plan["items"]:
                    fail("CLEANUP_PLAN_CHANGED", "清理计划为空或已变化，请重新检查。")
                record = {"id": cleanup_id, "data_root": str(self.root), "created_at": now(), "state": "moving", "permanent_delete": False,
                          "plan_id": plan_id, "plan_digest": plan["plan_digest"], "reference_digest": plan["reference_digest"],
                          "command_key_digest": key_digest, "request_digest": digest(payload),
                          "items": [{**item, "trash_path": str(self.trash / "items" / cleanup_id / item["asset_id"])} for item in plan["items"]],
                          "total_bytes": plan["total_bytes"], "asset_count": plan["asset_count"], "file_count": plan["file_count"], "moved_asset_ids": []}
            references = self.references()
            if references["digest"] != record["reference_digest"]:
                fail("CLEANUP_REFERENCE_CHANGED", "计划后引用已变化，未继续移动文件；已回收内容仍可恢复。")
            locations = self.locations(record, restoring=False)
            self.write(self.trash / "records", cleanup_id + ".json", record)
            destination = self.trash / "items" / cleanup_id
            destination.mkdir(exist_ok=True, mode=0o700); regular_path(destination)
            for item, source, already, scanned in locations:
                with self.store.lock:
                    self.cas(references)
                    if not unchanged(source, scanned["signatures"]):
                        fail("CLEANUP_ASSET_CHANGED", "移动前资产已变化，未继续移动文件。")
                    if not already:
                        publish(source, Path(item["trash_path"]))
                if item["asset_id"] not in record["moved_asset_ids"]:
                    record["moved_asset_ids"].append(item["asset_id"])
                self.write(self.trash / "records", cleanup_id + ".json", record)
            record.update(state="trashed", completed_at=now())
            self.write(self.trash / "records", cleanup_id + ".json", record)
            return self.public(record)

    def locations(self, record, restoring):
        result = []
        for item in record["items"]:
            original, trash = Path(item["source_path"]), Path(item["trash_path"])
            for parent in (original.parent, trash.parent):
                if parent.exists():
                    regular_path(parent)
            original_exists = original.exists() or original.is_symlink()
            trash_exists = trash.exists() or trash.is_symlink()
            if original_exists and trash_exists:
                fail("CLEANUP_TARGET_EXISTS", "原位置已有内容，未覆盖文件；回收副本仍保留。")
            if not original_exists and not trash_exists:
                fail("CLEANUP_ASSET_MISSING", "原位置和回收区均缺少此资产，请核实本机文件。")
            current = original if original_exists else trash
            scanned = same_tree(current, item)
            result.append((item, current, original_exists if restoring else trash_exists, scanned))
        return result

    def restore(self, cleanup_id, payload, key):
        key_digest = self.key(key)
        if payload not in (None, {}):
            fail("CLEANUP_INVALID", "恢复只允许使用原记录位置。")
        with self.guard(writing=True):
            record = self.record(cleanup_id)
            command = {"key_digest": key_digest, "request_digest": digest(payload or {})}
            if record.get("restore_command") not in (None, command):
                fail("IDEMPOTENCY_CONFLICT", "此回收记录已有另一条恢复命令。")
            if record["state"] == "restored":
                return self.public(record)
            locations = self.locations(record, restoring=True)
            references = self.references()
            record.update(state="restoring", restore_command=command)
            self.write(self.trash / "records", cleanup_id + ".json", record)
            for item, source, already, scanned in locations:
                with self.store.lock:
                    self.cas(references)
                    if not unchanged(source, scanned["signatures"]):
                        fail("CLEANUP_ASSET_CHANGED", "恢复前文件已变化，未继续移动。")
                    if not already:
                        publish(source, Path(item["source_path"]))
                self.write(self.trash / "records", cleanup_id + ".json", record)
            record.update(state="restored", restored_at=now())
            self.write(self.trash / "records", cleanup_id + ".json", record)
            return self.public(record)
