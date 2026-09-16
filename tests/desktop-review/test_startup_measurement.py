"""测量器使用真实短进程夹具；这些结果不是 App 启动性能证据。"""

from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/desktop"))
SPEC = importlib.util.spec_from_file_location("startup_measurement", ROOT / "scripts/desktop/verify_startup.py")
measurement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measurement)
VERSION = {"version": "2.0.0", "build": 7}


def valid_receipt(**changes):
    return {"schema_version": "ailab-first-frame-v1", "app_version": "2.0.0", "app_build": 7,
            "pid": 123, "control_pid": 124, "view": "project_home", "host_to_first_frame_ms": 201.5,
            "reported_at_unix_ms": 1_000_010, **changes}


@pytest.mark.parametrize("change", [
    {"pid": 122}, {"pid": True}, {"app_build": 6}, {"app_version": "0.1.0"},
    {"reported_at_unix_ms": 999_999}, {"reported_at_unix_ms": 1_000_051},
    {"host_to_first_frame_ms": float("nan")}, {"host_to_first_frame_ms": -1},
    {"view": "hidden"}, {"control_pid": 123}, {"control_pid": 0}, {"control_pid": True},
])
def test_stale_wrong_identity_hidden_and_invalid_timing_never_count(tmp_path, change):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(valid_receipt(**change)))
    assert measurement.read_receipt(path, 123, VERSION, 1_000_000, 1_000_050) is None


def test_atomic_valid_receipt_and_unreadable_content(tmp_path):
    path = tmp_path / "receipt.json"
    for content in ("{", "null", "[]"):
        path.write_text(content)
        assert measurement.read_receipt(path, 123, VERSION, 1_000_000, 1_000_050) is None
    path.write_text(json.dumps(valid_receipt()))
    assert measurement.read_receipt(path, 123, VERSION, 1_000_000, 1_000_050) == valid_receipt()


def test_readiness_statistic_requires_twenty_complete_launches_without_claiming_initial_visibility():
    rounds = [{"status": "completed", "launch_to_receipt_observed_ms": 1000 + i} for i in range(20)]
    assert measurement.summarize(rounds, 20)["twenty_full_readiness_under_3000_ms"]
    assert not measurement.summarize(rounds[:19], 20)["twenty_full_readiness_under_3000_ms"]
    assert not measurement.summarize(rounds[:1], 1)["twenty_full_readiness_under_3000_ms"]
    for samples, requested in ((rounds, 20), (rounds[:19], 20), (rounds[:1], 1), ([], 20)):
        summary = measurement.summarize(samples, requested)
        assert summary["measurement_kind"] == "full_readiness_receipt_observed"
        assert summary["initial_visibility_target_passed"] is None
        assert summary["initial_visibility_evidence"] == "not_measured"
        assert "twenty_launch_target_passed" not in summary
    rounds[-1]["launch_to_receipt_observed_ms"] = 3000.01
    summary = measurement.summarize(rounds, 20)
    assert summary["p95_ms"] == 1018 and summary["over_3000_ms"] == 1
    assert not summary["twenty_full_readiness_under_3000_ms"]
    assert summary["initial_visibility_target_passed"] is None


def test_failed_slow_round_remains_incomplete_and_does_not_pass_readiness_statistic():
    rounds = [{"status": "completed", "launch_to_receipt_observed_ms": 1200} for _ in range(19)]
    rounds.append({"status": "failed", "launch_to_receipt_observed_ms": 5000, "error": "App 未正常退出"})
    original = json.dumps(rounds)
    summary = measurement.summarize(rounds, 20)
    assert summary["completed"] == 19 and not summary["measurement_complete"]
    assert not summary["twenty_full_readiness_under_3000_ms"]
    assert summary["initial_visibility_target_passed"] is None
    assert json.dumps(rounds) == original


def test_selected_library_nonterminal_attempt_prevents_repeated_launches(tmp_path):
    library = tmp_path / "恢复库"
    library.mkdir()
    database = library / "control.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE projects(id TEXT)")
        connection.execute("CREATE TABLE resources(kind TEXT, body TEXT)")
        connection.execute("INSERT INTO resources VALUES('attempt', ?)", (json.dumps({"state": "unknown"}),))
    (tmp_path / "selected-library.json").write_text(json.dumps({"data_dir": str(library)}))
    before = database.read_bytes()
    with pytest.raises(RuntimeError, match="非终态"):
        measurement.assert_idle(tmp_path)
    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE resources SET body=?", (json.dumps({"state": "succeeded", "snapshot": {"operation": "evaluation"}}),))
    assert measurement.assert_idle(tmp_path) == {"projects": 0, "attempts": 1, "active_attempts": 0}


@pytest.mark.parametrize("kind,body", [
    ("attempt", {"state": "failed", "recovery_required": True, "stop_status": "unknown"}),
    ("model-download", {"state": "queued"}), ("market-download", {"state": "downloading"}),
    ("model-download", {"state": "verifying"}),
])
def test_real_store_recovery_and_downloading_states_are_not_idle(tmp_path, kind, body):
    with sqlite3.connect(tmp_path / "control.sqlite3") as connection:
        connection.execute("CREATE TABLE projects(id TEXT)")
        connection.execute("CREATE TABLE resources(kind TEXT, body TEXT)")
        connection.execute("INSERT INTO resources VALUES(?, ?)", (kind, json.dumps(body)))
    with pytest.raises(RuntimeError, match="尝试|下载"):
        measurement.assert_idle(tmp_path)


@pytest.mark.parametrize("body,error_type", [
    (json.dumps({"state": "succeeded"}), None),
    ("{", json.JSONDecodeError),
    (json.dumps({"state": "unknown"}), RuntimeError),
], ids=["success", "invalid_json", "nonterminal_attempt"])
def test_idle_reader_closes_live_wal_connection_and_preserves_data(tmp_path, monkeypatch, body, error_type):
    database = tmp_path / "control.sqlite3"
    connect = sqlite3.connect
    readers = []

    class TrackingConnection(sqlite3.Connection):
        close_calls = 0

        def close(self):
            self.close_calls += 1
            return super().close()

    def track_readonly(database_uri, **kwargs):
        assert database_uri == database.resolve().as_uri() + "?mode=ro" and kwargs == {"uri": True}
        connection = connect(database_uri, **kwargs, factory=TrackingConnection)
        readers.append(connection)  # 保留强引用，避免垃圾回收掩盖遗漏 close。
        return connection

    with closing(connect(database)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE projects(id TEXT)")
        writer.execute("CREATE TABLE resources(kind TEXT, body TEXT)")
        writer.commit()
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        writer.execute("INSERT INTO projects VALUES('保留项目')")
        writer.execute("INSERT INTO resources VALUES('attempt', ?)", (body,))
        writer.commit()
        before = list(writer.iterdump())
        assert database.with_name("control.sqlite3-wal").stat().st_size > 32
        # 最新已提交数据仅在 WAL，活库读取必须看到它，不能改成 immutable。
        with closing(connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as checkpointed:
            assert checkpointed.execute("SELECT count(*) FROM projects").fetchone() == (0,)
        try:
            with monkeypatch.context() as scoped:
                scoped.setattr(measurement.sqlite3, "connect", track_readonly)
                if error_type is None:
                    assert measurement.assert_idle(tmp_path) == {"projects": 1, "attempts": 1, "active_attempts": 0}
                else:
                    with pytest.raises(error_type):
                        measurement.assert_idle(tmp_path)
            assert len(readers) == 1 and readers[0].close_calls == 1
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                readers[0].execute("SELECT 1")
            assert list(writer.iterdump()) == before
        finally:
            for connection in readers:
                if not connection.close_calls:
                    connection.close()
    assert not database.with_name("control.sqlite3-wal").exists()
    assert not database.with_name("control.sqlite3-shm").exists()
    with closing(connect(database.as_uri() + "?mode=ro", uri=True)) as reopened:
        assert list(reopened.iterdump()) == before


def test_real_fixture_process_receipt_then_normal_exit(tmp_path):
    receipt = tmp_path / "receipt.json"
    # 先取得确已退出的测试 PID，代表正常释放的侧进程。
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=5)
    executable = tmp_path / "fixture"
    executable.write_text(f"#!{Path(sys.executable).resolve()}\nimport json,os,time\nfrom pathlib import Path\n"
                          f"value={valid_receipt(control_pid=child.pid)!r}\n"
                          "value['pid']=os.getpid()\nvalue['reported_at_unix_ms']=time.time_ns()//1_000_000\n"
                          f"Path({str(receipt)!r}).write_text(json.dumps(value))\ntime.sleep(.1)\n")
    executable.chmod(0o700)
    with (tmp_path / "log").open("w") as log:
        result = measurement.measure_one(executable, receipt, VERSION, log, 5, 5)
    assert result["status"] == "completed" and result["exit_code"] == 0 and result["control_exit_observed"]
    assert result["receipt"]["pid"] == result["pid"] and result["launch_to_receipt_observed_ms"] > 0


def test_real_fixture_exit_before_first_frame_keeps_failed_round(tmp_path):
    executable = tmp_path / "fixture"
    executable.write_text(f"#!{Path(sys.executable).resolve()}\nraise SystemExit(0)\n")
    executable.chmod(0o700)
    with (tmp_path / "log").open("w") as log:
        result = measurement.measure_one(executable, tmp_path / "missing", VERSION, log, 5, 5)
    assert result["status"] == "failed" and "首屏回执前退出" in result["error"]
    assert not measurement.summarize([result], 1)["measurement_complete"]


def test_real_cli_rejects_invalid_round_count_without_starting_app(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/desktop/verify_startup.py"), "--rounds", "0",
                             "--output", str(tmp_path / "output")], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and "轮数" in result.stderr and not (tmp_path / "output").exists()
