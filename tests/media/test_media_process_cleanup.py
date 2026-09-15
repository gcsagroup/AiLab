"""真实子进程取消、退出清理与回执边界；不加载模型、不代表模型能力。"""

import atexit
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers import media_worker as worker


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n")


def gone(pid, group=False):
    try:
        (os.killpg if group else os.kill)(pid, 0)
    except ProcessLookupError:
        return True
    return False


def fixture_cli(mode, output):
    tracker_pid = None
    if mode == "slow-cancel":
        sys.path.insert(0, str(ROOT / "adapters/media"))
        from adapters.media.image_cli import install_cancellation
        import multiprocessing
        from multiprocessing import resource_tracker
        install_cancellation()
        global TEST_LOCK
        TEST_LOCK = multiprocessing.get_context("spawn").Lock()
        tracker_pid = resource_tracker._resource_tracker._pid

        def slow_cleanup():
            (output / "cleanup-started").touch()
            time.sleep(3)
            (output / "cleanup-completed").touch()

        # 后注册的钩子先执行，保证三秒清理完成后才注销真实信号量。
        atexit.register(slow_cleanup)
    else:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    write_json(output / "cli-ready.json", {"pid": os.getpid(), "parent_pid": os.getppid(),
                                         "pgid": os.getpgrp(), "tracker_pid": tracker_pid})
    if mode == "invalid-output":
        print("x" * (worker.MAX_EVENT_BYTES + 1), flush=True)
    while True:
        time.sleep(0.05)


def fixture_bridge(mode, output):
    signal.signal(signal.SIGTERM, worker.common.cancel_handler)
    signal.signal(signal.SIGINT, worker.common.cancel_handler)
    try:
        worker.run_command([sys.executable, "-B", str(Path(__file__).resolve()),
                            "--fixture-cli", mode, str(output)], output)
    except worker.common.WorkerError as error:
        write_json(output / "bridge-error.json", {"code": error.code})
        return 130 if error.code == "CANCELLED" else 1
    return 0


class MediaProcessCleanupTests(unittest.TestCase):
    def tearDown(self):
        worker.common.CANCELLED = False

    def run_group(self, mode):
        # 显式提供证据目录时保留所有原始文件；普通测试使用临时目录。
        evidence_root = os.environ.get("AILAB_CLEANUP_TEST_OUTPUT")
        if evidence_root:
            output = Path(evidence_root) / mode
            output.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            output = Path(temporary.name)
        command = [sys.executable, "-B", str(Path(__file__).resolve()),
                   "--fixture-bridge", mode, str(output)]
        started = time.monotonic()
        process, ready = None, None
        try:
            with (output / "bridge.stdout.log").open("wb") as stdout, (output / "bridge.stderr.log").open("wb") as stderr:
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
                deadline = started + 20
                while not (output / "cli-ready.json").exists():
                    self.assertIsNone(process.poll(), "CLI ready 前桥已退出")
                    self.assertLess(time.monotonic(), deadline - 13, "CLI ready 超时")
                    time.sleep(0.02)
                ready = json.loads((output / "cli-ready.json").read_text())
                self.assertEqual(ready["parent_pid"], process.pid)
                self.assertEqual(ready["pgid"], process.pid)
                if mode != "invalid-output":
                    os.killpg(process.pid, signal.SIGTERM)
                returncode = process.wait(timeout=max(0.1, deadline - time.monotonic() - 1))
                while not gone(process.pid, group=True) and time.monotonic() < deadline - 1:
                    time.sleep(0.02)
            receipt = json.loads((output / "executor-process.json").read_text())
            summary = {"command": command, "actual_bridge_returncode": returncode,
                       "elapsed_seconds": time.monotonic() - started, "receipt": receipt,
                       "bridge_gone": gone(process.pid), "group_gone": gone(process.pid, group=True),
                       "cli_gone": gone(ready["pid"]),
                       "tracker_gone": gone(ready["tracker_pid"]) if ready["tracker_pid"] else None}
            write_json(output / "test-observation.json", summary)
            self.assertTrue(summary["bridge_gone"])
            self.assertTrue(summary["group_gone"])
            self.assertTrue(summary["cli_gone"])
            self.assertEqual(receipt["executor_pid"], ready["pid"])
            if ready["tracker_pid"]:
                self.assertTrue(summary["tracker_gone"])
            return output, returncode, receipt
        finally:
            if process is not None and not gone(process.pid, group=True):
                # 仅清理该用例刚创建的独立进程组，不影响测试运行器和其它任务。
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)

    def test_cancel_allows_real_three_second_semaphore_cleanup(self):
        output, returncode, receipt = self.run_group("slow-cancel")
        self.assertEqual(returncode, 130)
        self.assertEqual(receipt["returncode"], 130)
        self.assertTrue(receipt["cancelled"])
        self.assertTrue(receipt["group_terminate_sent"])
        self.assertTrue(receipt["terminate_sent"])
        self.assertFalse(receipt["kill_sent"])
        self.assertEqual(receipt["cleanup_grace_seconds"], 10)
        self.assertGreater(receipt["cleanup_wait_seconds"], 2.5)
        self.assertLess(receipt["cleanup_wait_seconds"], 9)
        self.assertTrue((output / "cleanup-started").exists())
        self.assertTrue((output / "cleanup-completed").exists())
        self.assertEqual(json.loads((output / "bridge-error.json").read_text())["code"], "CANCELLED")
        self.assertNotIn("resource_tracker:", (output / "executor.stderr.log").read_text())

    def test_cancel_still_kills_unresponsive_child_after_ten_seconds(self):
        output, returncode, receipt = self.run_group("ignore-cancel")
        self.assertEqual(returncode, 130)
        self.assertEqual(receipt["returncode"], -signal.SIGKILL)
        self.assertTrue(receipt["cancelled"])
        self.assertTrue(receipt["group_terminate_sent"])
        self.assertTrue(receipt["terminate_sent"])
        self.assertTrue(receipt["kill_sent"])
        self.assertEqual(receipt["cleanup_grace_seconds"], 10)
        self.assertGreaterEqual(receipt["cleanup_wait_seconds"], 9.9)
        self.assertLess(receipt["cleanup_wait_seconds"], 13)
        self.assertEqual(json.loads((output / "bridge-error.json").read_text())["code"], "CANCELLED")

    def test_non_cancel_error_retains_two_second_cleanup(self):
        output, returncode, receipt = self.run_group("invalid-output")
        self.assertEqual(returncode, 1)
        self.assertEqual(receipt["returncode"], -signal.SIGKILL)
        self.assertFalse(receipt["cancelled"])
        self.assertFalse(receipt["group_terminate_sent"])
        self.assertTrue(receipt["terminate_sent"])
        self.assertTrue(receipt["kill_sent"])
        self.assertEqual(receipt["cleanup_grace_seconds"], 2)
        self.assertGreaterEqual(receipt["cleanup_wait_seconds"], 1.9)
        self.assertLess(receipt["cleanup_wait_seconds"], 5)
        self.assertEqual(json.loads((output / "bridge-error.json").read_text())["code"], "MEDIA_EVENT_TOO_LARGE")

    def test_success_and_failure_receipts_keep_actual_exit_code(self):
        for exit_code in [0, 7]:
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
                output = Path(directory)
                command = [sys.executable, "-c", f"raise SystemExit({exit_code})"]
                if exit_code:
                    with self.assertRaises(worker.common.WorkerError) as error:
                        worker.run_command(command, output)
                    self.assertEqual(error.exception.code, "MEDIA_EXECUTION_FAILED")
                else:
                    self.assertEqual(worker.run_command(command, output)["returncode"], 0)
                receipt = json.loads((output / "executor-process.json").read_text())
                self.assertIsInstance(receipt["executor_pid"], int)
                self.assertEqual(receipt["returncode"], exit_code)
                self.assertFalse(receipt["cancelled"])
                for key in ["group_terminate_sent", "terminate_sent", "kill_sent"]:
                    self.assertFalse(receipt[key])
                self.assertIsNone(receipt["cleanup_grace_seconds"])
                self.assertIsNone(receipt["cleanup_wait_seconds"])

    def test_start_failure_receipt_does_not_invent_pid_or_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with self.assertRaises(FileNotFoundError):
                worker.run_command([str(output / "missing-executor")], output)
            receipt = json.loads((output / "executor-process.json").read_text())
            self.assertIsNone(receipt["executor_pid"])
            self.assertIsNone(receipt["returncode"])
            self.assertFalse(receipt["cancelled"])
            self.assertFalse(receipt["group_terminate_sent"])
            self.assertFalse(receipt["terminate_sent"])
            self.assertFalse(receipt["kill_sent"])
            self.assertIsNone(receipt["cleanup_grace_seconds"])
            self.assertIsNone(receipt["cleanup_wait_seconds"])


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] in {"--fixture-cli", "--fixture-bridge"}:
        # 子夹具使用导入守卫，禁止意外加载模型库或访问网络。
        def no_models_or_network(event, arguments):
            if event == "import" and arguments[0].split(".")[0] in {"torch", "mlx", "mlx_lm", "diffusers", "transformers"}:
                raise RuntimeError("无模型夹具禁止加载模型库")
            if event in {"socket.connect", "socket.getaddrinfo"}:
                raise RuntimeError("无模型夹具禁止网络访问")
        sys.addaudithook(no_models_or_network)
        action = fixture_cli if sys.argv[1] == "--fixture-cli" else fixture_bridge
        raise SystemExit(action(sys.argv[2], Path(sys.argv[3])))
    unittest.main()
