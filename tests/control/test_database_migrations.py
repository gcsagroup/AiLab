"""使用真实旧版 SQLite、WAL 和故障注入验证升级及回滚。"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/control"))
from ailab_control import migrations
from ailab_control.service import Service, Settings
from ailab_control.storage import Fault, Store

# 固定旧版结构，不能由新版初始化函数替代历史输入。
V1_SQL = """
CREATE TABLE schema_version(version INTEGER PRIMARY KEY);
INSERT INTO schema_version VALUES(1);
CREATE TABLE projects(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE resources(id TEXT PRIMARY KEY,kind TEXT NOT NULL,project_id TEXT NOT NULL REFERENCES projects(id),body TEXT NOT NULL);
CREATE INDEX resources_project_kind ON resources(project_id,kind);
CREATE TABLE events(attempt_id TEXT NOT NULL REFERENCES resources(id),sequence INTEGER NOT NULL,body TEXT NOT NULL,PRIMARY KEY(attempt_id,sequence));
CREATE TABLE commands(scope TEXT NOT NULL,key TEXT NOT NULL,request_digest TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(scope,key));
CREATE TABLE app_settings(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
"""


def legacy(path, wal=False):
    path.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(path, isolation_level=None)
    db.executescript(V1_SQL)
    if wal:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("INSERT INTO projects VALUES(?,?)", ("project-old", '{ "id": "project-old", "name": "旧库中文", "revision": 1 }'))
    for identity, kind, body in [
        ("task-z", "task", '{ "id": "task-z", "project_id":"project-old", "name":"早创建" }'),
        ("task-a", "task", '{ "id": "task-a", "project_id":"project-old", "name":"后创建" }'),
        ("attempt-old", "attempt", '{ "id": "attempt-old", "project_id":"project-old", "state":"succeeded" }'),
    ]:
        db.execute("INSERT INTO resources VALUES(?,?,?,?)", (identity, kind, "project-old", body))
    db.execute("INSERT INTO events VALUES(?,?,?)", ("attempt-old", 1, '{ "sequence": 1, "payload": "原事件字节" }'))
    db.execute("INSERT INTO commands VALUES(?,?,?,?)", ("old", "key", "digest", '{ "id": "attempt-old" }'))
    db.execute("INSERT INTO app_settings VALUES(1,?)", ('{ "revision": 7, "worker_python": null }',))
    for directory, name in [("assets", "原模型.bin"), ("runs", "原快照.json")]:
        (path.parent / directory).mkdir(exist_ok=True)
        (path.parent / directory / name).write_bytes(b"\x00historical-bytes\xff\n")
    return db


def rows(db):
    return {table: [tuple(row) for row in db.execute(f"SELECT rowid,* FROM {table} ORDER BY rowid")]
            for table in ("projects", "resources", "events", "commands", "app_settings")}


def files(root):
    return {str(path.relative_to(root)): path.read_bytes() for name in ("assets", "runs") for path in (root / name).rglob("*") if path.is_file()}


def receipt(path, before=1):
    target, = path.parent.glob(f"migrations/v{before}-to-v{before + 1}-*/receipt.json")
    return target, json.loads(target.read_text())


def test_new_database_is_v4_without_migration(tmp_path):
    store = Store(tmp_path / "control.sqlite3")
    assert migrations.version(store.db) == 4
    assert not (tmp_path / "migrations").exists()
    migrations.validate(store.db, 4, integrity=True)
    store.db.close()


@pytest.mark.parametrize("wal", [False, True])
def test_v3_upgrade_preserves_raw_evidence_and_verified_v3_copy(tmp_path, wal):
    path = tmp_path / "control.sqlite3"
    old = legacy(path, wal)
    migrations.migrate_v1_to_v2(old)
    migrations.migrate_v2_to_v3(old)
    before, content = rows(old), files(tmp_path)
    store = Store(path)
    assert migrations.version(store.db) == 4
    assert rows(store.db) == before and files(tmp_path) == content
    location, record = receipt(path, 3)
    saved_path = location.parent / record["backup"]["path"]
    assert record["status"] == "succeeded" and record["committed"] is True
    assert hashlib.sha256(saved_path.read_bytes()).hexdigest() == record["backup"]["sha256"]
    with sqlite3.connect(saved_path) as saved:
        assert migrations.version(saved) == 3 and rows(saved) == before
        migrations.validate(saved, 3, integrity=True)
    store.db.close(); old.close()
    reopened = Store(path)
    assert rows(reopened.db) == before and migrations.version(reopened.db) == 4
    assert len(list(tmp_path.glob("migrations/v3-to-v4-*"))) == 1
    reopened.db.close()


def test_v4_migration_failure_keeps_v3_and_retry_preserves_records(tmp_path, monkeypatch):
    path = tmp_path / "control.sqlite3"
    old = legacy(path, wal=True)
    migrations.migrate_v1_to_v2(old)
    migrations.migrate_v2_to_v3(old)
    before = rows(old)
    original = migrations.migrate_v3_to_v4
    def fail_after_version(db):
        original(db)
        db.execute("DELETE FROM commands")
        raise OSError("模拟v4迁移中断")
    monkeypatch.setattr(migrations, "migrate_v3_to_v4", fail_after_version)
    with pytest.raises(Fault) as captured:
        Store(path)
    assert captured.value.code == "DATABASE_MIGRATION_FAILED"
    assert migrations.version(old) == 3 and rows(old) == before
    location, record = receipt(path, 3)
    assert record["status"] == "failed_rolled_back" and record["committed"] is False
    with sqlite3.connect(location.parent / "control.sqlite3") as saved:
        assert migrations.version(saved) == 3 and rows(saved) == before
    monkeypatch.setattr(migrations, "migrate_v3_to_v4", original)
    restarted = Store(path)
    assert migrations.version(restarted.db) == 4 and rows(restarted.db) == before
    restarted.db.close(); old.close()


@pytest.mark.parametrize("wal", [False, True])
def test_upgrade_preserves_old_rows_files_order_and_consistent_v1_backup(tmp_path, wal):
    path = tmp_path / "control.sqlite3"
    old = legacy(path, wal)
    before, content = rows(old), files(tmp_path)
    if wal:
        assert path.with_name(path.name + "-wal").stat().st_size > 0
    store = Store(path)
    assert rows(store.db) == before
    assert files(tmp_path) == content
    assert [item["id"] for item in store.list("task")] == ["task-z", "task-a"]
    location, record = receipt(path)
    assert record["status"] == "succeeded" and record["committed"] is True
    second_location, second_record = receipt(path, 2)
    assert second_record["status"] == "succeeded" and second_record["committed"] is True
    with sqlite3.connect(second_location.parent / "control.sqlite3") as second_saved:
        assert migrations.version(second_saved) == 2 and rows(second_saved) == before
    backup = location.parent / record["backup"]["path"]
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == record["backup"]["sha256"]
    with sqlite3.connect(backup) as saved:
        assert migrations.version(saved) == 1
        assert rows(saved) == before
    assert not backup.with_name(backup.name + "-wal").exists()
    old.close(); store.db.close()
    restarted = Store(path)
    assert rows(restarted.db) == before
    assert len(list(tmp_path.glob("migrations/v1-to-v2-*"))) == 1
    restarted.db.close()
    # 旧版副本能恢复到独立目录并再次升级，不覆盖源库或原副本。
    restored = tmp_path / "isolated"; restored.mkdir()
    shutil.copy2(backup, restored / "control.sqlite3")
    recovered = Store(restored / "control.sqlite3")
    assert rows(recovered.db) == before
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == record["backup"]["sha256"]
    recovered.db.close()


def test_failure_after_ddl_rolls_back_every_change_and_allows_retry(tmp_path, monkeypatch):
    path = tmp_path / "control.sqlite3"; old = legacy(path)
    before, content = rows(old), files(tmp_path)
    original = migrations.migrate_v1_to_v2
    def fail_after_changes(db):
        original(db)
        db.execute("UPDATE projects SET body='篡改必须回滚'")
        raise sqlite3.OperationalError("模拟迁移写入失败")
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", fail_after_changes)
    with pytest.raises(Fault, match="迁移") as captured:
        Store(path)
    assert captured.value.code == "DATABASE_MIGRATION_FAILED"
    assert migrations.version(old) == 1 and rows(old) == before and files(tmp_path) == content
    assert old.execute("SELECT name FROM sqlite_master WHERE name='resources_kind'").fetchone() is None
    location, record = receipt(path)
    assert record["status"] == "failed_rolled_back" and record["committed"] is False
    with sqlite3.connect(location.parent / "control.sqlite3") as saved:
        assert rows(saved) == before and migrations.version(saved) == 1
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", original)
    restarted = Store(path)
    assert rows(restarted.db) == before and migrations.version(restarted.db) == 4
    restarted.db.close(); old.close()


def test_v2_attempt_index_failure_preserves_v2_and_retry_reaches_v4(tmp_path, monkeypatch):
    path = tmp_path / "control.sqlite3"; old = legacy(path, wal=True)
    migrations.migrate_v1_to_v2(old)
    before = rows(old)
    original = migrations.migrate_v2_to_v3
    def fail_after_index(db):
        original(db)
        db.execute("DELETE FROM events")
        raise OSError("模拟v3索引迁移中断")
    monkeypatch.setattr(migrations, "migrate_v2_to_v3", fail_after_index)
    with pytest.raises(Fault):
        Store(path)
    assert migrations.version(old) == 2 and rows(old) == before
    assert old.execute("SELECT name FROM sqlite_master WHERE name='resources_attempt_task'").fetchone() is None
    location, record = receipt(path, 2)
    assert record["status"] == "failed_rolled_back" and record["committed"] is False
    with sqlite3.connect(location.parent / "control.sqlite3") as saved:
        assert migrations.version(saved) == 2 and rows(saved) == before
    monkeypatch.setattr(migrations, "migrate_v2_to_v3", original)
    restarted = Store(path)
    assert migrations.version(restarted.db) == 4 and rows(restarted.db) == before
    restarted.db.close(); old.close()


def test_backup_failure_never_runs_migration(tmp_path, monkeypatch):
    path = tmp_path / "control.sqlite3"; old = legacy(path); before = rows(old)
    monkeypatch.setattr(migrations, "copy_database", lambda *_: (_ for _ in ()).throw(OSError("模拟磁盘已满")))
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", lambda *_: pytest.fail("备份失败后禁止执行迁移"))
    with pytest.raises(Fault):
        Store(path)
    assert migrations.version(old) == 1 and rows(old) == before
    assert receipt(path)[1]["status"] == "failed_rolled_back"
    old.close()


@pytest.mark.parametrize("versions", [(99,), (1, 99), ()])
def test_unsupported_versions_are_read_only_before_any_ddl(tmp_path, versions):
    path = tmp_path / "control.sqlite3"; old = legacy(path)
    old.execute("DELETE FROM schema_version")
    old.executemany("INSERT INTO schema_version VALUES(?)", [(value,) for value in versions])
    old.close(); original = path.read_bytes()
    with pytest.raises(Fault) as captured:
        Store(path)
    assert captured.value.code == "DATABASE_VERSION_UNSUPPORTED"
    assert path.read_bytes() == original
    assert not (tmp_path / "migrations").exists()


def test_service_rejects_migration_before_recovery_and_releases_lock(tmp_path, monkeypatch):
    path = tmp_path / "control.sqlite3"; old = legacy(path); old.close()
    original = migrations.migrate_v1_to_v2
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", lambda *_: (_ for _ in ()).throw(OSError("模拟升级中断")))
    monkeypatch.setattr(Service, "_recover", lambda *_: pytest.fail("迁移失败后禁止启动恢复或运行器"))
    with pytest.raises(Fault):
        Service(Settings(tmp_path, "fixture-token"))
    monkeypatch.setattr(migrations, "migrate_v1_to_v2", original)
    calls = []
    monkeypatch.setattr(Service, "_recover", lambda *_: calls.append("recovered"))
    service = Service(Settings(tmp_path, "fixture-token"))
    try:
        assert calls == ["recovered"] and migrations.version(service.store.db) == 4
    finally:
        service.close(); service.store.db.close()


def test_abrupt_exit_after_ddl_preserves_v1_and_verified_backup(tmp_path):
    path = tmp_path / "control.sqlite3"; old = legacy(path, wal=True); before = rows(old)
    code = """
import os,sys
from ailab_control import migrations
from ailab_control.storage import Store
original=migrations.migrate_v1_to_v2
def crash(db):
    original(db)
    db.execute("UPDATE projects SET body='未提交'")
    os._exit(73)
migrations.migrate_v1_to_v2=crash
Store(sys.argv[1])
"""
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "services/control")}
    result = subprocess.run([sys.executable, "-c", code, str(path)], env=environment, capture_output=True, timeout=20)
    assert result.returncode == 73, result.stderr
    assert migrations.version(old) == 1 and rows(old) == before
    location, record = receipt(path)
    assert record["status"] == "backup_verified" and record["committed"] is False
    with sqlite3.connect(location.parent / "control.sqlite3") as saved:
        assert migrations.version(saved) == 1 and rows(saved) == before
    old.close()
    restarted = Store(path)
    assert migrations.version(restarted.db) == 4 and rows(restarted.db) == before
    assert json.loads(location.read_text())["status"] == "interrupted_rolled_back"
    restarted.db.close()


def test_crash_before_first_receipt_does_not_permanently_block_old_database(tmp_path):
    path = tmp_path / "control.sqlite3"; old = legacy(path, wal=True); before = rows(old)
    code = """
import os,sys
from ailab_control import migrations
from ailab_control.storage import Store
migrations.write_receipt=lambda *_: os._exit(74)
Store(sys.argv[1])
"""
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "services/control")}
    result = subprocess.run([sys.executable, "-c", code, str(path)], env=environment, capture_output=True, timeout=20)
    assert result.returncode == 74, result.stderr
    assert migrations.version(old) == 1 and rows(old) == before
    temporary, = (tmp_path / "migrations").glob(".v1-to-v2-*")
    assert not (temporary / "receipt.json").exists()
    restarted = Store(path)
    assert migrations.version(restarted.db) == 4 and rows(restarted.db) == before
    assert temporary.exists() and receipt(path)[1]["status"] == "succeeded"
    restarted.db.close(); old.close()
