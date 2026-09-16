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


def system_launch_fixture(tmp_path, monkeypatch, *, receipt_enabled=True, confirm=True):
    """真实父子进程和回执；仅替代系统启动器及 Python 夹具的可执行路径标识。"""
    receipt = tmp_path / "receipt.json"
    identities = tmp_path / "identities.json"
    executable = tmp_path / "带空格 Fixture.app/Contents/MacOS/fixture"
    app = tmp_path / "app.py"
    app.write_text("import os,json,subprocess,sys,time\nfrom pathlib import Path\n"
        "control=subprocess.Popen([sys.executable,'-c','import time;time.sleep(3)'])\n"
        f"identities=Path({str(identities)!r})\n"
        "temporary=identities.with_suffix('.tmp')\n"
        "temporary.write_text(json.dumps({'app':os.getpid(),'control':control.pid}))\n"
        "temporary.replace(identities)\n"
        f"value={valid_receipt()!r}\n"
        "value.update(pid=os.getpid(),control_pid=control.pid,reported_at_unix_ms=time.time_ns()//1_000_000)\n"
        + (f"Path({str(receipt)!r}).write_text(json.dumps(value))\n" if receipt_enabled else "")
        + "time.sleep(.7)\ncontrol.terminate();control.wait(timeout=2)\n")
    launcher = tmp_path / "open.py"
    launcher.write_text(f"import subprocess,sys\np=subprocess.Popen([sys.executable,{str(app)!r}])\np.wait(timeout=5)\n")
    actual_rows = measurement.process_rows
    launched = []

    def launch(_executable, log):
        assert _executable == executable
        process = subprocess.Popen([sys.executable, str(launcher)], stdout=log, stderr=log)
        launched.append(process)
        return process

    def fixture_rows():
        rows = actual_rows()
        if identities.exists():
            ids = json.loads(identities.read_text())
            for key, path in (("app", executable), ("control", executable.parents[1] / "Resources/resources/control/ailab-control")):
                if ids[key] in rows:
                    rows[ids[key]] = {**rows[ids[key]], "executable": str(path)}
        return rows

    monkeypatch.setattr(measurement, 'launch_system_app', launch)
    monkeypatch.setattr(measurement, 'process_rows', fixture_rows)
    monkeypatch.setattr(measurement, 'confirm_native_quit', lambda pid: confirm)
    with (tmp_path / 'log').open('w') as log:
        result = measurement.measure_one(executable, receipt, VERSION, log, 5, 5)
    for process in launched:
        process.wait(timeout=5)
    return result


def test_real_system_launcher_fixture_receipt_and_both_processes_exit(tmp_path, monkeypatch):
    result = system_launch_fixture(tmp_path, monkeypatch)
    assert result["status"] == "completed" and result["launcher_exit_code"] == 0
    assert result["app_exit_code"] is None and result["native_quit_confirmed"]
    assert result["control_exit_observed"] and result["app_exit_observed"]
    assert result["pid"] != result["launcher_pid"]
    assert result["receipt"]["pid"] == result["pid"] and result["launch_to_receipt_observed_ms"] > 0


def test_real_fixture_exit_before_first_frame_keeps_failed_round(tmp_path, monkeypatch):
    result = system_launch_fixture(tmp_path, monkeypatch, receipt_enabled=False)
    assert result["status"] == "failed" and "首屏回执前退出" in result["error"]
    assert not measurement.summarize([result], 1)["measurement_complete"]


def test_system_launcher_success_cannot_replace_native_quit_confirmation(tmp_path, monkeypatch):
    result = system_launch_fixture(tmp_path, monkeypatch, confirm=False)
    assert result["launcher_exit_code"] == 0 and result["app_exit_code"] is None
    assert result["status"] == "failed" and not result["native_quit_confirmed"]
    assert "未确认原生正常退出" in result["error"]


def test_process_parser_preserves_full_paths_and_start_identity(monkeypatch):
    content = " 12 1 Wed Sep 16 17:00:00 2026 /带空格/Example App.app/Contents/MacOS/app\n"
    def run(argv, **kwargs):
        assert argv == ["/bin/ps", "-axo", "pid=,ppid=,lstart=,comm="]
        assert kwargs['env']['LC_ALL'] == 'C' and kwargs['check']
        return subprocess.CompletedProcess(argv, 0, content, '')
    monkeypatch.setattr(measurement.subprocess, 'run', run)
    rows = measurement.process_rows()
    assert rows[12] == {'pid': 12, 'ppid': 1, 'started_at': 'Wed Sep 16 17:00:00 2026', 'executable': '/带空格/Example App.app/Contents/MacOS/app'}
    assert measurement.matching_app(rows, Path(rows[12]['executable'])) == rows[12]
    assert measurement.matching_app(rows, Path('/other/app')) is None
    with pytest.raises(RuntimeError, match='多个'):
        measurement.matching_app({**rows, 13: {**rows[12], 'pid': 13}}, Path(rows[12]['executable']))


@pytest.mark.parametrize('content', ['invalid\n', '12 1 Wed Sep 16 17:00:00 2026 /app\n12 1 Wed Sep 16 17:00:00 2026 /app\n'])
def test_ambiguous_process_table_is_rejected(monkeypatch, content):
    monkeypatch.setattr(measurement.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0, content, ''))
    with pytest.raises(RuntimeError): measurement.process_rows()


def test_system_launch_uses_foreground_bundle_and_separate_private_logs(tmp_path, monkeypatch):
    executable = tmp_path / '固定 App.app/Contents/MacOS/app'
    calls = []
    monkeypatch.setattr(measurement.subprocess, 'Popen', lambda argv, **kwargs: calls.append(argv) or object())
    with (tmp_path/'launch.log').open('w') as log:
        measurement.launch_system_app(executable, log)
    assert calls[0][:4] == ['/usr/bin/open', '-W', '-n', str(executable.parents[2])]
    assert '-g' not in calls[0] and '-j' not in calls[0]
    assert calls[0][4::2] == ['--stdout', '--stderr']
    assert calls[0][5] != calls[0][7]
    for name in calls[0][5::2]: assert Path(name).stat().st_mode & 0o777 == 0o600
    with (tmp_path/'launch.log').open('a') as log:
        with pytest.raises(FileExistsError): measurement.launch_system_app(executable, log)
    assert len(calls) == 1


@pytest.mark.parametrize('response', ['已确认退出', 'no', ''])
def test_quit_acknowledgement_requires_explicit_phrase(monkeypatch, response):
    monkeypatch.setattr('builtins.input', lambda _: response)
    assert measurement.confirm_native_quit(12) is (response == '已确认退出')


def test_quit_acknowledgement_eof_is_not_success(monkeypatch):
    def eof(_): raise EOFError
    monkeypatch.setattr('builtins.input', eof)
    assert not measurement.confirm_native_quit(12)


@pytest.mark.parametrize('case,reason', [
    ('duplicate', '多个'), ('identity_changed', '身份变化'),
    ('wrong_parent', '不属于'), ('wrong_control_path', '不属于'),
    ('app_still_live', 'App 仍在'), ('control_still_live', '控制进程仍存在'),
    ('launcher_failed', '启动器未正常结束'), ('timeout', '超时'),
])
def test_system_launch_failures_never_restart_kill_or_count_as_complete(tmp_path, monkeypatch, case, reason):
    executable = tmp_path/'App.app/Contents/MacOS/app'
    app = {'pid': 123, 'ppid': 1, 'started_at': 'current', 'executable': str(executable)}
    control = {'pid': 124, 'ppid': 123, 'started_at': 'current', 'executable': str(executable.parents[1]/'Resources/resources/control/ailab-control')}
    calls = 0
    class Launcher:
        pid = 122
        code = None
        def poll(self): return self.code
        def wait(self, timeout):
            self.code = 2 if case == 'launcher_failed' else 0
            return self.code
    launcher = Launcher()
    def launch(*args):
        nonlocal calls
        calls += 1
        return launcher
    snapshots = 0
    def rows():
        nonlocal snapshots
        snapshots += 1
        if snapshots == 1: return {}
        if case == 'duplicate': return {123: app, 125: {**app, 'pid': 125}}
        if case == 'identity_changed' and snapshots > 2: return {123: {**app, 'started_at': 'replacement'}}
        if case == 'wrong_parent': return {123: app, 124: {**control, 'ppid': 999}}
        if case == 'wrong_control_path': return {123: app, 124: {**control, 'executable': '/other/control'}}
        if launcher.code is not None:
            return {123: app} if case == 'app_still_live' else {124: control} if case == 'control_still_live' else {}
        return {123: app, 124: control}
    monkeypatch.setattr(measurement, 'process_rows', rows)
    monkeypatch.setattr(measurement, 'launch_system_app', launch)
    monkeypatch.setattr(measurement, 'read_receipt', lambda *args: None if case in ('identity_changed', 'timeout') else valid_receipt())
    monkeypatch.setattr(measurement, 'confirm_native_quit', lambda _: pytest.fail('失败不能进入确认'))
    if case == 'control_still_live':
        clock = iter([0, 6])
        monkeypatch.setattr(measurement.time, 'monotonic', lambda: next(clock))
    with (tmp_path/'log').open('w') as log:
        result = measurement.measure_one(executable, tmp_path/'receipt', VERSION, log, .01 if case == 'timeout' else 5, 5)
    assert result['status'] == 'failed' and reason in result['error']
    assert not result['native_quit_confirmed'] and calls == 1
    assert not measurement.summarize([result], 1)['measurement_complete']
    if case == 'timeout': assert result['launcher_running'] and result['launcher_exit_code'] is None


def test_existing_fixed_app_blocks_system_launch(tmp_path, monkeypatch):
    executable = tmp_path/'App.app/Contents/MacOS/app'
    monkeypatch.setattr(measurement, 'process_rows', lambda: {1: {'pid': 1, 'executable': str(executable)}})
    monkeypatch.setattr(measurement, 'launch_system_app', lambda *args: pytest.fail('不应再次启动'))
    with (tmp_path/'log').open('w') as log, pytest.raises(RuntimeError, match='已运行'):
        measurement.measure_one(executable, tmp_path/'receipt', VERSION, log, 1, 1)


def test_real_cli_rejects_invalid_round_count_without_starting_app(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/desktop/verify_startup.py"), "--rounds", "0",
                             "--output", str(tmp_path / "output")], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and "轮数" in result.stderr and not (tmp_path / "output").exists()
