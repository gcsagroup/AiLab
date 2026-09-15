"""版本化 SQLite 迁移；先保存一致副本，再以单次事务升级。"""

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid
from datetime import datetime, timezone

from .storage import Fault

CURRENT_VERSION = 4
SUPPORTED_VERSIONS = {1, 2, 3, 4}
ATTEMPT_TASK_INDEX = "CREATE INDEX resources_attempt_task ON resources(json_extract(body,'$.task_id')) WHERE kind='attempt'"
TABLE_COLUMNS = {
    "schema_version": ["version"], "projects": ["id", "body"],
    "resources": ["id", "kind", "project_id", "body"],
    "events": ["attempt_id", "sequence", "body"],
    "commands": ["scope", "key", "request_digest", "response"],
    "app_settings": ["id", "body"],
}
CREATE_V1 = (
    "CREATE TABLE schema_version(version INTEGER PRIMARY KEY)",
    "CREATE TABLE projects(id TEXT PRIMARY KEY, body TEXT NOT NULL)",
    "CREATE TABLE resources(id TEXT PRIMARY KEY, kind TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id), body TEXT NOT NULL)",
    "CREATE INDEX resources_project_kind ON resources(project_id,kind)",
    "CREATE TABLE events(attempt_id TEXT NOT NULL REFERENCES resources(id), sequence INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(attempt_id,sequence))",
    "CREATE TABLE commands(scope TEXT NOT NULL, key TEXT NOT NULL, request_digest TEXT NOT NULL, response TEXT NOT NULL, PRIMARY KEY(scope,key))",
    "CREATE TABLE app_settings(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)",
)


def version(db):
    try:
        rows = db.execute("SELECT version FROM schema_version").fetchall()
    except sqlite3.Error as error:
        raise Fault("DATABASE_VERSION_UNSUPPORTED", "数据库缺少受支持的版本信息，未改写数据库。", 503) from error
    if len(rows) != 1 or type(rows[0][0]) is not int or rows[0][0] not in SUPPORTED_VERSIONS:
        raise Fault("DATABASE_VERSION_UNSUPPORTED", "数据库版本不兼容，未改写数据库。", 503)
    return rows[0][0]


def validate(db, expected, integrity=False):
    if version(db) != expected:
        raise Fault("DATABASE_VERSION_UNSUPPORTED", "数据库版本在打开期间变化，未继续启动。", 503)
    entries = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    if any(kind not in {"table", "index"} for kind, _ in entries) or {name for kind, name in entries if kind == "table"} != set(TABLE_COLUMNS):
        raise Fault("DATABASE_SCHEMA_INVALID", "数据库结构不符合当前版本，未继续启动。", 503)
    for table, columns in TABLE_COLUMNS.items():
        if [row[1] for row in db.execute(f'PRAGMA table_info("{table}")')] != columns:
            raise Fault("DATABASE_SCHEMA_INVALID", "数据库字段不符合当前版本，未继续启动。", 503)
    indexes = {"resources_project_kind": ["project_id", "kind"]}
    if expected >= 2:
        indexes["resources_kind"] = ["kind"]
    if expected >= 3:
        indexes["resources_attempt_task"] = [None]
    for name, columns in indexes.items():
        if [row[2] for row in db.execute(f'PRAGMA index_info("{name}")')] != columns:
            raise Fault("DATABASE_SCHEMA_INVALID", "数据库索引不符合当前版本，未继续启动。", 503)
    if expected >= 3 and db.execute("SELECT sql FROM sqlite_master WHERE name='resources_attempt_task'").fetchone()[0] != ATTEMPT_TASK_INDEX:
        raise Fault("DATABASE_SCHEMA_INVALID", "执行历史索引不符合当前版本，未继续启动。", 503)
    if integrity and (db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall()):
        raise Fault("DATABASE_INTEGRITY_FAILED", "数据库完整性检查失败，未继续启动。", 503)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_receipt(directory, value):
    temporary = directory / (".receipt-" + uuid.uuid4().hex)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, sort_keys=True, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, directory / "receipt.json")
        sync_directory(directory)
    finally:
        temporary.unlink(missing_ok=True)


def copy_database(path, directory, expected):
    target = directory / "control.sqlite3"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    # 主连接持有写保留锁；独立读连接取得包括已提交 WAL 的一致视图。
    source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, isolation_level=None)
    backup = sqlite3.connect(target, isolation_level=None)
    try:
        source.backup(backup)
        backup.execute("PRAGMA journal_mode=DELETE")
        validate(backup, expected, integrity=True)
    finally:
        source.close()
        backup.close()
    with target.open("rb") as stream:
        os.fsync(stream.fileno())
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    sync_directory(directory)
    return {"path": "control.sqlite3", "size": target.stat().st_size, "sha256": checksum}


def migrate_v1_to_v2(db):
    # SQLite 索引隐含 rowid，保留原插入顺序供游标分页读取。
    db.execute("CREATE INDEX resources_kind ON resources(kind)")
    db.execute("UPDATE schema_version SET version=2 WHERE version=1")


def migrate_v2_to_v3(db):
    db.execute(ATTEMPT_TASK_INDEX)
    db.execute("UPDATE schema_version SET version=3 WHERE version=2")


def migrate_v3_to_v4(db):
    # 新增来源组划分资源语义；旧应用必须拒绝，避免备份遗漏成对数据和证据。
    # 表结构与原业务正文不变，仍先由 upgrade 保存一致的 v3 副本。
    db.execute("UPDATE schema_version SET version=4 WHERE version=3")


def recover_receipts(path, current):
    parent = path.parent / "migrations"
    if not parent.exists():
        return
    if parent.is_symlink() or not parent.is_dir():
        raise Fault("DATABASE_MIGRATION_FAILED", "迁移回执目录无效，未继续启动。", 503)
    for directory in parent.glob("v*-to-v*-*"):
        match = re.fullmatch(r"v([123])-to-v([234])-[0-9a-f]{32}", directory.name)
        if not match or int(match[2]) != int(match[1]) + 1:
            raise Fault("DATABASE_MIGRATION_FAILED", "迁移回执目录编号无效，未继续启动。", 503)
        target = directory / "receipt.json"
        if directory.is_symlink() or target.is_symlink() or not target.is_file() or target.stat().st_size > 65536:
            raise Fault("DATABASE_MIGRATION_FAILED", "迁移回执缺失或无效，未继续启动。", 503)
        record = json.loads(target.read_text(encoding="utf-8"))
        if record.get("database_path") != str(path):
            continue
        before, after = int(match[1]), int(match[2])
        if record.get("schema_version") != "ailab-database-migration-v1" or record.get("from_version") != before or record.get("to_version") != after or current < before:
            raise Fault("DATABASE_MIGRATION_FAILED", "迁移回执版本无效，未继续启动。", 503)
        if record.get("status") in {"backing_up", "backup_verified"}:
            record.update(status="interrupted_rolled_back" if current == before else "succeeded_recovered_receipt",
                          committed=current >= after, recovered_at=timestamp())
            write_receipt(directory, record)


def upgrade(db, path, expected):
    directory, receipt, committed = None, None, False
    try:
        db.execute("BEGIN IMMEDIATE")
        current = version(db)
        if current > expected:
            db.execute("COMMIT")
            return
        validate(db, expected, integrity=True)
        parent = path.parent / "migrations"
        parent.mkdir(mode=0o700, exist_ok=True)
        if parent.is_symlink() or not stat.S_ISDIR(parent.stat().st_mode):
            raise OSError("迁移备份目录必须是普通目录。")
        final = parent / (f"v{expected}-to-v{expected + 1}-" + uuid.uuid4().hex)
        directory = parent / ("." + final.name)
        directory.mkdir(mode=0o700)
        sync_directory(parent)
        receipt = {"schema_version": "ailab-database-migration-v1", "from_version": expected, "to_version": expected + 1,
                   "database_path": str(path), "started_at": timestamp(), "status": "backing_up",
                   "scope": "database_only_assets_unchanged", "committed": False}
        write_receipt(directory, receipt)
        # 首条回执持久化后才公布正式目录；此前崩溃的临时目录保留但不阻塞重试。
        os.rename(directory, final)
        directory = final
        sync_directory(parent)
        receipt["backup"] = copy_database(path, directory, expected)
        receipt["status"] = "backup_verified"
        write_receipt(directory, receipt)
        {1: migrate_v1_to_v2, 2: migrate_v2_to_v3, 3: migrate_v3_to_v4}[expected](db)
        validate(db, expected + 1, integrity=True)
        db.execute("COMMIT")
        committed = True
        receipt.update(status="succeeded", committed=True, completed_at=timestamp())
        write_receipt(directory, receipt)
    except BaseException as error:
        if db.in_transaction:
            db.execute("ROLLBACK")
        if receipt is not None:
            receipt.update(status="receipt_failed_after_commit" if committed else "failed_rolled_back",
                           committed=committed, completed_at=timestamp(), error_type=type(error).__name__)
            try:
                write_receipt(directory, receipt)
            except OSError:
                pass
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise Fault("DATABASE_MIGRATION_FAILED", "数据库迁移未完成验收，运行器未启动；请检查保留的备份与迁移回执。" if directory else "数据库迁移无法开始，运行器未启动，未执行版本变更。", 503,
                    migration_path=str(directory) if directory else None, committed=committed) from error


def connect(path):
    path = Path(path).absolute()
    existed = path.exists()
    if path.is_symlink() or (existed and not stat.S_ISREG(path.stat().st_mode)):
        raise Fault("DATABASE_PATH_INVALID", "数据库必须是普通文件，不能使用链接或设备。", 503)
    current = None
    if existed and path.stat().st_size:
        readonly = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            current = version(readonly)
            validate(readonly, current)
        finally:
            readonly.close()
        recover_receipts(path, current)
    db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    try:
        if current is None:
            db.execute("BEGIN IMMEDIATE")
            for statement in CREATE_V1:
                db.execute(statement)
            db.execute("INSERT INTO schema_version VALUES(4)")
            db.execute("CREATE INDEX resources_kind ON resources(kind)")
            db.execute(ATTEMPT_TASK_INDEX)
            db.execute("COMMIT")
        else:
            while current < CURRENT_VERSION:
                upgrade(db, path, current)
                current = version(db)
            validate(db, CURRENT_VERSION)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        return db
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        db.close()
        raise
