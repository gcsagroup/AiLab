"""为百万元信息补实际共享资产，并实跑完整备份与新目录恢复。"""

import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/control"))
from ailab_control.assets import copy_asset, dataset_report, file_hash, verify_manifest
from ailab_control.backup import Backup, MAX_BACKUP_BYTES, MAX_DATABASE_BYTES, remap_reference_paths
from ailab_control.service import Service, Settings
from ailab_control.storage import digest, encode


def row_digest(db, source=None, target=None):
    checksum = hashlib.sha256()
    for rowid, identity, kind, project, body in db.execute("SELECT rowid,id,kind,project_id,body FROM resources ORDER BY rowid"):
        if source is not None:
            body = encode(remap_reference_paths(json.loads(body), source, target))
        checksum.update(encode([rowid, identity, kind, project, body]).encode() + b"\n")
    return checksum.hexdigest()


def run(source, output):
    output.mkdir(parents=True, exist_ok=False)
    data = output / "d"; data.mkdir()
    source_before = file_hash(source)
    shutil.copy2(source, data / "control.sqlite3")
    inputs = output / "input"; inputs.mkdir()
    sample = inputs / "rows.jsonl"
    sample.write_text('{"messages":[{"role":"user","content":"2+2=?"},{"role":"assistant","content":"4"}]}\n', encoding="utf-8")
    report = dataset_report(sample, "sft")
    assert report["can_import"]
    manifest = [{"path": sample.name, "size": sample.stat().st_size, "sha256": file_hash(sample)}]
    (data / "assets").mkdir()
    asset = copy_asset(sample, data / "assets", manifest, digest(manifest))
    service = Service(Settings(data, "backup-scale-token"))
    try:
        db = service.store.db
        count, after = 0, 0
        started = time.monotonic()
        with service.store.transaction():
            while True:
                rows = db.execute("SELECT rowid,id,body FROM resources WHERE kind='dataset' AND rowid>? ORDER BY rowid LIMIT 1000", (after,)).fetchall()
                if not rows:
                    break
                for _, identity, body in rows:
                    value = json.loads(body)
                    value.update(manifest=manifest, manifest_digest=digest(manifest), storage_path=str(asset),
                                 version_id="scale-version-" + identity.removeprefix("dataset-"), total_bytes=sample.stat().st_size,
                                 status="ready", schema="sft", sample_count=1)
                    db.execute("UPDATE resources SET body=? WHERE id=?", (encode(value), identity))
                after = rows[-1][0]; count += len(rows)
        assert count == 1000000
        db.execute("VACUUM")
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        database = data / "control.sqlite3"
        size = database.stat().st_size
        assert 128 * 1024**2 < size <= MAX_DATABASE_BYTES, size
        before_rows, before_db, before_asset = row_digest(db), file_hash(database), file_hash(asset / sample.name)
        print(json.dumps({"stage": "fixture_ready", "database_bytes": size, "seconds": time.monotonic() - started}), flush=True)
        manager = Backup(service)
        timings = {}
        started = time.monotonic(); backup = manager.create("scale-backup")
        timings["backup_seconds"] = time.monotonic() - started
        directory = Path(backup["backup_path"])
        print(json.dumps({"stage": "backup_completed", **timings}), flush=True)
        started = time.monotonic(); package = manager.verify(directory)
        timings["verify_seconds"] = time.monotonic() - started
        assert len(package["files"]) == 2 and package["reference_file_count"] == 1
        assert next(item for item in package["files"] if item["path"] != "control.sqlite3")["sha256"] == before_asset
        target = output / "restores"; target.mkdir()
        service.settings.export_roots = [target]
        started = time.monotonic(); plan = manager.plan({"backup_path": str(directory), "target_dir": str(target)})
        timings["restore_preflight_seconds"] = time.monotonic() - started
        started = time.monotonic(); restored = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "scale-restore")
        timings["restore_seconds"] = time.monotonic() - started
        recovered = Path(restored["restored_path"])
        print(json.dumps({"stage": "restore_completed", **timings}), flush=True)
        destination = Service(Settings(recovered, "backup-scale-restored-token"))
        try:
            original_count = dict(db.execute("SELECT kind,COUNT(*) FROM resources GROUP BY kind"))
            restored_count = dict(destination.store.db.execute("SELECT kind,COUNT(*) FROM resources GROUP BY kind"))
            assert original_count == restored_count == {"dataset": 1000000, "task": 10000}
            assert row_digest(destination.store.db, recovered, data) == before_rows
            for cursor in (None, "dataset-499999", "dataset-999899"):
                page = destination.store.page("dataset", "project-scale", cursor, 100)
                assert len(page["items"]) == 100
                for record in page["items"]:
                    assert Path(record["storage_path"]).is_relative_to(recovered)
                    verify_manifest(Path(record["storage_path"]), record["manifest"])
            asset_relative = (asset / sample.name).relative_to(data)
            assert file_hash(recovered / asset_relative) == before_asset
        finally:
            destination.close(); destination.store.db.close()
        assert row_digest(db) == before_rows and file_hash(database) == before_db and file_hash(asset / sample.name) == before_asset
        assert file_hash(source) == source_before
        result = {"schema_version": "ailab-backup-scale-v1", "passed": True, "fixture_only": True,
                  "scope": "1万任务与100万元信息；全部dataset引用一份通过真实SFT结构检查的共享JSONL，实际复制和校验闭包",
                  "database_bytes": size, "restored_database_bytes": (recovered / "control.sqlite3").stat().st_size,
                  "max_database_bytes": MAX_DATABASE_BYTES, "max_total_backup_bytes": MAX_BACKUP_BYTES,
                  "source_database_sha256": before_db, "source_rows_sha256": before_rows, "asset_sha256": before_asset,
                  "source_unchanged": True, "restored_rows_equal_after_path_normalization": True,
                  "resource_counts": original_count, "backup_files": package["files"], "backup_path": str(directory),
                  "restored_path": str(recovered), "timings": timings, "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        (output / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"report": str(output / "report.json"), "passed": True, "database_bytes": size, **timings}), flush=True)
    finally:
        service.close(); service.store.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    run(arguments.source.resolve(), arguments.output.resolve())
