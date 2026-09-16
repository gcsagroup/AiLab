"""逐轮测量固定候选的完整就绪回执；初次可见目标仍须独立界面证据。"""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import sqlite3
import statistics
import subprocess
import time

from app_version import APP_PATH, ROOT, atomic_write, check_app, json_text, read_version


DATA_ROOT = Path.home() / "Library/Application Support/org.gcsa.ailab"
TERMINAL = {"succeeded", "failed", "cancelled"}


def read_receipt(path, pid, version, launched_ms, observed_ms):
    """旧回执、未完整写入和其他进程不计入本轮。"""
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            return None
        if (value.get("schema_version") != "ailab-first-frame-v1"
                or type(value.get("pid")) is not int or value["pid"] != pid
                or value.get("app_version") != version["version"]
                or type(value.get("app_build")) is not int or value["app_build"] != version["build"]
                or value.get("view") not in {"empty_library", "project_home"}
                or type(value.get("control_pid")) is not int
                or value["control_pid"] <= 0 or value["control_pid"] == pid):
            return None
        stamp, elapsed = value.get("reported_at_unix_ms"), value.get("host_to_first_frame_ms")
        if (type(stamp) is not int or not launched_ms <= stamp <= observed_ms
                or type(elapsed) not in {int, float} or not math.isfinite(elapsed) or elapsed < 0):
            return None
        return value
    except (OSError, ValueError, TypeError):
        return None


def assert_idle(data_root):
    selection = data_root / "selected-library.json"
    selected = Path(json.loads(selection.read_text())["data_dir"]) if selection.exists() else data_root
    database = selected / "control.sqlite3"
    if not database.exists():
        return {"projects": 0, "attempts": 0, "active_attempts": 0}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        projects = connection.execute("SELECT count(*) FROM projects").fetchone()[0]
        attempts = [json.loads(row[0]) for row in connection.execute("SELECT body FROM resources WHERE kind='attempt'")]
        downloads = [json.loads(row[0]) for row in connection.execute("SELECT body FROM resources WHERE kind IN ('model-download','market-download')")]
    active = sum(value.get("state") not in TERMINAL or bool(value.get("recovery_required")) for value in attempts)
    if active:
        raise RuntimeError(f"当前库仍有 {active} 次非终态尝试，请先在 App 处理后再测启动")
    if any(value.get("state") in {"queued", "downloading", "verifying"} for value in downloads):
        raise RuntimeError("当前库仍有模型或市场下载，请先完成或停止后再测启动")
    return {"projects": projects, "attempts": len(attempts), "active_attempts": active}


def assert_not_running(executable):
    result = subprocess.run(["/usr/bin/pgrep", "-x", executable.name], capture_output=True, text=True)
    if result.returncode == 0:
        raise RuntimeError("同名 App 进程仍在运行，请先正常退出")
    if result.returncode != 1:
        raise RuntimeError("无法核对 App 是否已退出")


def process_rows():
    """只读取进程身份，不收集参数或凭据；路径内空格必须完整保留。"""
    observed = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,lstart=,comm="],
                              capture_output=True, text=True, check=True, timeout=5,
                              env={**os.environ, "LC_ALL": "C"})
    rows = {}
    for line in observed.stdout.splitlines():
        fields = line.strip().split(None, 7)
        if len(fields) != 8 or not fields[0].isdigit() or not fields[1].isdigit():
            raise RuntimeError("无法解析进程身份，停止本轮测量")
        pid = int(fields[0])
        if pid in rows:
            raise RuntimeError("进程身份重复，停止本轮测量")
        rows[pid] = {"pid": pid, "ppid": int(fields[1]), "started_at": " ".join(fields[2:7]),
                     "executable": fields[7]}
    return rows


def matching_app(rows, executable):
    matches = [row for row in rows.values() if row["executable"] == str(executable)]
    if len(matches) > 1:
        raise RuntimeError("存在多个固定 App 进程，拒绝混用回执")
    return matches[0] if matches else None


def launch_system_app(executable, log):
    app = executable.parents[2]
    if app.suffix != ".app" or executable.parent != app / "Contents/MacOS":
        raise RuntimeError("启动目标不是 App 包内固定可执行文件")
    streams = []
    for channel in ("stdout", "stderr"):
        path = Path(log.name).with_name(Path(log.name).name + ".app-" + channel)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        streams.extend(["--" + channel, str(path)])
    return subprocess.Popen(["/usr/bin/open", "-W", "-n", str(app), *streams], stdout=log, stderr=log)


def confirm_native_quit(pid):
    # LaunchServices 不提供 App 退出码；不能把 open 的 0 冒充 App 正常退出。
    try:
        return input(f"App {pid} 和控制服务已停止。确认已通过原生退出菜单及确认框退出后，输入“已确认退出”：").strip() == "已确认退出"
    except EOFError:
        return False


def measure_one(executable, receipt_path, version, log, timeout, quit_timeout):
    if matching_app(process_rows(), executable) is not None:
        raise RuntimeError("固定 App 已运行，拒绝复用已有进程")
    started_wall_ms = time.time_ns() // 1_000_000
    started = time.perf_counter()
    process = None
    result = {"launched_at_unix_ms": started_wall_ms, "status": "waiting_first_frame",
              "launch_method": "macos_launchservices_foreground", "app_exit_code": None,
              "native_quit_confirmed": False}
    try:
        process = launch_system_app(executable, log)
        result["launcher_pid"] = process.pid
        identity = None
        while time.perf_counter() - started < timeout:
            rows = process_rows()
            current = matching_app(rows, executable)
            if identity is None and current is not None:
                identity = current
                result.update(pid=identity["pid"], app_identity=identity)
            elif identity is not None and current != identity:
                raise RuntimeError("App 在有效首屏回执前退出或进程身份变化")
            receipt = read_receipt(receipt_path, identity["pid"], version, started_wall_ms, time.time_ns() // 1_000_000) if identity else None
            if receipt is not None:
                control = rows.get(receipt["control_pid"])
                if (control is None or control["ppid"] != identity["pid"]
                        or control["executable"] != str(executable.parents[1] / "Resources/resources/control/ailab-control")):
                    raise RuntimeError("首屏回执的控制进程不属于本轮 App")
                result.update(status="first_frame", receipt=receipt,
                              control_identity=control,
                              launch_to_receipt_observed_ms=(time.perf_counter() - started) * 1000)
                break
            if process.poll() is not None:
                raise RuntimeError("系统启动器在有效首屏回执前退出")
            time.sleep(0.1)
        else:
            raise RuntimeError("等待可见首屏超时；App 保留供界面排查")
        print(json_text({"event": "first_frame", **result}).strip(), flush=True)
        # 操作者通过真实 App 的退出菜单确认退出；脚本没有退出后门或强制停止。
        code = process.wait(timeout=quit_timeout)
        result["launcher_exit_code"] = code
        if code != 0:
            raise RuntimeError("系统启动器未正常结束")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            rows = process_rows()
            if matching_app(rows, executable) is not None or identity["pid"] in rows:
                raise RuntimeError("系统启动器结束后 App 仍在或身份被复用")
            if receipt["control_pid"] not in rows:
                result.update(app_exit_observed=True, control_exit_observed=True)
                break
            time.sleep(.1)
        else:
            raise RuntimeError("App 退出后控制进程仍存在")
        if not confirm_native_quit(identity["pid"]):
            raise RuntimeError("未确认原生正常退出；保留本轮，不计为完成")
        result.update(native_quit_confirmed=True, status="completed")
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        result.update(status="failed", error=str(error))
    finally:
        if process is not None:
            result["launcher_exit_code"] = process.poll()
            result["launcher_running"] = result["launcher_exit_code"] is None
    return result


def summarize(rounds, requested):
    values = [value["launch_to_receipt_observed_ms"] for value in rounds if value.get("status") == "completed"]
    summary = {"requested": requested, "completed": len(values), "measurement_complete": len(values) == requested,
               "measurement_kind": "full_readiness_receipt_observed",
               "initial_visibility_target_passed": None,
               "initial_visibility_evidence": "not_measured"}
    if values:
        ordered = sorted(values)
        summary.update(median_ms=statistics.median(values), p95_ms=ordered[math.ceil(len(values) * .95) - 1],
                       maximum_ms=max(values), over_3000_ms=sum(value > 3000 for value in values))
    # 继续保留原 20 轮／3000ms 统计，但完整就绪迟于初显，不能据此判初显失败。
    # 本脚本也未采集初显帧；快样本不代替冻结需求要求的独立界面验收。
    summary["twenty_full_readiness_under_3000_ms"] = requested >= 20 and len(values) == requested and max(values, default=math.inf) <= 3000
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--quit-timeout", type=float, default=300)
    arguments = parser.parse_args()
    if not 1 <= arguments.rounds <= 100 or not 0 < arguments.timeout <= 300 or not 0 < arguments.quit_timeout <= 1800:
        parser.error("轮数须为 1—100，首屏等待为 0—300 秒，退出等待为 0—1800 秒")
    output = arguments.output.resolve()
    if output.exists():
        parser.error("输出目录已存在，请使用新的验收批次，保留旧结果")
    app = ROOT / APP_PATH
    version = check_app(ROOT, app, read_version(ROOT))
    metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if metadata.get("CFBundleIdentifier") != "org.gcsa.ailab":
        raise RuntimeError("App 标识不匹配")
    executable = app / "Contents/MacOS" / metadata["CFBundleExecutable"]
    assert_not_running(executable)
    for args in (("--verify", "--deep", "--strict"), ("-dvvv",)):
        check = subprocess.run(["/usr/bin/codesign", *args, str(app)], capture_output=True, text=True, timeout=60)
        if check.returncode or (args == ("-dvvv",) and "Authority=Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)" not in check.stderr):
            raise RuntimeError("候选 App 签名或组织校验失败")
    report = {"schema_version": 3, "started_at": datetime.now(timezone.utc).isoformat(), "version": version,
              "app_path": str(app), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "library_before": assert_idle(DATA_ROOT), "rounds": [], "status": "running",
              "scope": "同一已安装候选由 macOS open 正常前台启动；保留系统文件缓存，不是系统重启或干净安装。外部计时从启动 open 前至完整就绪回执读回，包含系统启动、进程检查、文件写入及约100ms轮询等待；不测主窗口初次可见，不判定其三秒目标。App退出码未知；启动器成功结束、App及控制进程消失，并由操作者确认原生正常退出后，才开始下一轮。"}
    output.mkdir(parents=True, mode=0o700)
    try:
        for index in range(arguments.rounds):
            assert_not_running(executable)
            assert_idle(DATA_ROOT)
            log_path = output / f"round-{index + 1:02d}.private.log"
            with log_path.open("x") as log:
                os.chmod(log_path, 0o600)
                value = measure_one(executable, DATA_ROOT / "startup-latest.json", version, log, arguments.timeout, arguments.quit_timeout)
            report["rounds"].append({"round": index + 1, **value})
            report["summary"] = summarize(report["rounds"], arguments.rounds)
            atomic_write(output / "report.json", json_text(report))
            if value["status"] != "completed":
                raise RuntimeError(value.get("error", "本轮未完成"))
        report.update(status="completed", library_after=assert_idle(DATA_ROOT))
    except Exception as error:
        report.update(status="failed", error=str(error))
    finally:
        report["summary"] = summarize(report["rounds"], arguments.rounds)
        atomic_write(output / "report.json", json_text(report))
    print(json_text({"status": report["status"], "summary": report["summary"], "report": str(output / "report.json")}), flush=True)
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
