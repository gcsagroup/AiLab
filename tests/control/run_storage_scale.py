"""隔离目录生成 1 万任务与 100 万条元信息，测量真实 SQLite/HTTP 分页。"""

import argparse
import json
import math
from pathlib import Path
import platform
import resource
import sys
import time
import tracemalloc

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/control"))
from ailab_control.api import create_app
from ailab_control.service import Settings
from ailab_control.storage import Store, encode


def percentile(values, quantile):
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)]


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    data = output / "data"; data.mkdir()
    store = Store(data / "control.sqlite3")
    started = time.monotonic()
    with store.transaction():
        store.put("project", {"id": "project-scale", "name": "规模夹具", "revision": 1})
        for kind, count in (("task", 10000), ("dataset", 1000000)):
            for offset in range(0, count, 1000):
                batch = []
                for index in range(offset, min(offset + 1000, count)):
                    item = {"id": f"{kind}-{index:06d}", "resource_type": kind, "project_id": "project-scale",
                            "name": f"规模元信息 {index}", "fixture_only": True, "created_at": "2026-09-10T00:00:00+00:00"}
                    batch.append((item["id"], kind, item["project_id"], encode(item)))
                store.db.executemany("INSERT INTO resources VALUES(?,?,?,?)", batch)
    insertion_seconds = time.monotonic() - started
    assert store.db.execute("SELECT COUNT(*) FROM resources WHERE kind='task'").fetchone()[0] == 10000
    assert store.db.execute("SELECT COUNT(*) FROM resources WHERE kind='dataset'").fetchone()[0] == 1000000
    store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    query_plans = {
        "global": [row[3] for row in store.db.execute("EXPLAIN QUERY PLAN SELECT id,body FROM resources WHERE kind=? AND rowid>? ORDER BY rowid LIMIT ?", ("dataset", 500000, 101))],
        "project": [row[3] for row in store.db.execute("EXPLAIN QUERY PLAN SELECT id,body FROM resources WHERE kind=? AND project_id=? AND rowid>? ORDER BY rowid LIMIT ?", ("dataset", "project-scale", 500000, 101))],
    }
    for details in query_plans.values():
        assert "rowid>?" in " ".join(details) and "SCAN" not in " ".join(details) and "TEMP B-TREE" not in " ".join(details)
    app = create_app(Settings(data, "storage-scale-local-token"))
    measurements = []
    with TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer storage-scale-local-token"}) as client:
        for kind, route, total in (("task", "tasks", 10000), ("dataset", "datasets", 1000000)):
            for position, offset in (("first", 0), ("middle", total // 2), ("last", total - 100)):
                descending = kind == "task"
                cursor = (("desc:" + f"{kind}-{total - offset:06d}") if descending else f"{kind}-{offset - 1:06d}") if offset else None
                expected = [f"{kind}-{index:06d}" for index in (range(total - offset - 1, total - offset - 101, -1) if descending else range(offset, offset + 100))]
                parameters = {"project_id": "project-scale", "limit": 100, **({"cursor": cursor} if cursor else {})}
                for transport in ("sqlite", "http"):
                    durations, sizes = [], []
                    tracemalloc.start()
                    for _ in range(30):
                        before = time.perf_counter()
                        if transport == "sqlite":
                            page = store.page(kind, "project-scale", cursor, 100, descending=descending)
                        else:
                            response = client.get("/api/v1/" + route, params=parameters)
                            assert response.status_code == 200, response.text
                            page = response.json(); sizes.append(len(response.content))
                        durations.append((time.perf_counter() - before) * 1000)
                        assert [item["id"] for item in page["items"]] == expected
                        assert page["next_cursor"] == ((("desc:" if descending else "") + expected[-1]) if offset + 100 < total else None)
                    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
                    measurements.append({"kind": kind, "transport": transport, "position": position, "descending": descending, "samples": len(durations),
                                         "median_ms": percentile(durations, 0.5), "p95_ms": percentile(durations, 0.95),
                                         "max_ms": max(durations), "peak_traced_bytes": peak,
                                         "response_bytes": max(sizes) if sizes else None, "passed": percentile(durations, 0.95) <= 300 and peak < 16 * 1024 * 1024})
    app.state.service.store.db.close()
    store.db.close()
    report = {"schema_version": "ailab-storage-scale-v1", "fixture_only": True, "scope": "真实本地 SQLite 和 HTTP 分页；元信息夹具不代表已导入的训练数据文件",
              "tasks": 10000, "data_metadata": 1000000, "platform": platform.platform(), "python": platform.python_version(),
              "insertion_seconds": insertion_seconds, "database_bytes": (data / "control.sqlite3").stat().st_size,
              "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "query_plans": query_plans, "measurements": measurements, "passed": all(item["passed"] for item in measurements)}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(output / "report.json"), "passed": report["passed"], "database_bytes": report["database_bytes"],
                      "worst_p95_ms": max(item["p95_ms"] for item in measurements), "max_traced_bytes": max(item["peak_traced_bytes"] for item in measurements)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    raise SystemExit(run(parser.parse_args().output.resolve()))
