"""备份元数据按需读取，体积限制同时覆盖数据库和资产。"""

import json
from pathlib import Path

import pytest

from test_control import rig, post
from test_backup_restore import ready_backup
import ailab_control.backup as backup_module
from ailab_control.backup import Backup, DatabaseResources
from ailab_control.storage import Fault


def test_database_returns_repeatable_filtered_rows_without_decoding_whole_collection(rig, monkeypatch):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "流式资源"})
    with service.store.transaction():
        for index in range(1000):
            service.store.put("task", {"id": f"task-{index}", "resource_type": "task", "project_id": project["id"], "name": f"记录{index}"})
    backup = Backup(service).create("streaming-resources")
    original, calls = json.loads, []
    def loads(value, *args, **kwargs):
        calls.append(value)
        return original(value, *args, **kwargs)
    monkeypatch.setattr(backup_module.json, "loads", loads)
    records = backup_module.database(Path(backup["backup_path"]) / "control.sqlite3")
    assert isinstance(records, DatabaseResources) and not calls
    assert list(records.select("attempt")) == [] and not calls
    selected = iter(records)
    assert next(selected)[1]["id"] == "task-0" and len(calls) == 1
    selected.close()
    assert sum(1 for _ in records.select("task")) == 1000
    assert sum(1 for _ in records.select("task")) == 1000


def test_total_size_limit_includes_real_database_bytes(rig, monkeypatch):
    manager, backup, *_ = ready_backup(rig)
    manifest = manager.verify(Path(backup["backup_path"]))
    database_size = next(item["size"] for item in manifest["files"] if item["path"] == "control.sqlite3")
    asset_size = sum(item["size"] for item in manifest["files"] if item["path"] != "control.sqlite3")
    assert database_size > 0 and asset_size > 0
    monkeypatch.setattr(backup_module, "MAX_BACKUP_BYTES", database_size + asset_size - 1)
    with pytest.raises(Fault):
        manager.verify(Path(backup["backup_path"]))
    with pytest.raises(Fault):
        manager.create("total-limit")
    assert not any(path.name.startswith(".backup-") for path in (rig[1].root / "backups").iterdir())


def test_database_size_limit_rejects_actual_sqlite_before_resource_read(rig, monkeypatch):
    manager, backup, *_ = ready_backup(rig)
    path = Path(backup["backup_path"]) / "control.sqlite3"
    monkeypatch.setattr(backup_module, "MAX_DATABASE_BYTES", path.stat().st_size - 1)
    with pytest.raises(Fault, match="元数据"):
        backup_module.database(path)
