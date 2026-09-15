"""媒体快照身份、固定参数及真实子进程边界；夹具不代表模型能力。"""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.media import preflight
from workers import media_worker as worker


class MediaBridgeTests(unittest.TestCase):
    def tearDown(self):
        worker.common.CANCELLED = False

    def test_only_measured_runtime_combinations(self):
        for kind, operation in [("image", "generate"), ("image", "train"), ("video", "generate")]:
            value = preflight.runtime_config({"kind": kind, "operation": operation, "runtime": {"seed": 17}})
            self.assertEqual(value["engine"], "diffusers")
            self.assertEqual(value["seed"], 17)
        invalid = [{"seed": True}, {"seed": 1.5}, {"seed": -1}, {"seed": 2**32}, {"cfg": float("nan")},
                   {"cfg": True}, {"size": 256}, {"steps": 19}, {"engine": "mlx"}, {"device_id": "cpu"}, {"temperature": 0}]
        for runtime in invalid:
            with self.subTest(runtime=runtime), self.assertRaises(worker.common.WorkerError):
                preflight.runtime_config({"kind": "image", "operation": "generate", "runtime": runtime})
        with self.assertRaisesRegex(worker.common.WorkerError, "只开放"):
            preflight.runtime_config({"kind": "video", "operation": "train"})

    def test_full_manifest_rejects_extra_cache_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original = root / "a.bin"
            original.write_bytes(b"identity fixture; not a model")
            entries = [{"path": original.name, "size": original.stat().st_size, "sha256": worker.common.sha256(original)}]
            snapshot = {"model_manifest": entries, "model_manifest_digest": worker.common.canonical_digest(entries)}
            self.assertEqual(preflight.verify_bound(root, snapshot, "model"), root)
            cache = root / ".gitattributes"
            cache.write_text("extra")
            with self.assertRaisesRegex(worker.common.WorkerError, "集合"):
                preflight.verify_bound(root, snapshot, "model")
            cache.unlink()
            cache.symlink_to(original)
            with self.assertRaisesRegex(worker.common.WorkerError, "符号链接"):
                preflight.verify_bound(root, snapshot, "model")
            cache.unlink()
            original.write_bytes(b"changed")
            with self.assertRaisesRegex(worker.common.WorkerError, "摘要"):
                preflight.verify_bound(root, snapshot, "model")

    def test_output_overlap_and_existing_result_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            model = root / "model"
            model.mkdir()
            with self.assertRaisesRegex(worker.common.WorkerError, "重叠"):
                preflight.check_output(model / "output", [model])
            output = root / "output"
            output.mkdir()
            marker = output / "image.png"
            marker.write_bytes(b"previous")
            with self.assertRaisesRegex(worker.common.WorkerError, "不能覆盖"):
                preflight.check_output(output, [model])
            self.assertEqual(marker.read_bytes(), b"previous")

    def test_cli_command_carries_all_effective_arguments(self):
        snapshot = {"kind": "image", "operation": "generate", "model_path": "/fixed/model", "adapter_path": "/fixed/lora"}
        effective = {"steps": 20, "seed": 17, "size": 512, "prompt": "蓝色杯子", "negative_prompt": "", "cfg": 7.5}
        command = worker.command_for(snapshot, effective, Path("/new/output"))
        self.assertEqual(command[command.index("--prompt") + 1], "蓝色杯子")
        self.assertEqual(command[command.index("--negative-prompt") + 1], "")
        self.assertEqual(command[command.index("--adapter") + 1], "/fixed/lora")
        self.assertEqual(command[command.index("--seed") + 1], "17")

    def test_frozen_worker_uses_only_fixed_internal_commands(self):
        snapshot = {"kind": "image", "operation": "generate", "model_path": "/fixed/model"}
        effective = {"steps": 20, "seed": 17, "size": 512, "prompt": "蓝色杯子", "negative_prompt": "", "cfg": 7.5}
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", "/moved runtime/ailab-diffusers"):
            command = worker.command_for(snapshot, effective, Path("/new/output"))
            self.assertEqual(command[:4], [sys.executable, "--mode", "image-cli", "generate"])
            self.assertNotIn("-u", command)
            self.assertFalse(any(value.endswith(".py") for value in command))
            snapshot.update(kind="video", input_image_path="/fixed/input.png")
            effective.update(steps=25, frames=14, fps=7)
            command = worker.command_for(snapshot, effective, Path("/new/video"))
            self.assertEqual(command[:3], [sys.executable, "--mode", "video-cli"])
            self.assertEqual(command[command.index("--input") + 1], "/fixed/input.png")
            self.assertEqual(command[command.index("--frames") + 1], "14")

    def test_real_child_progress_and_failure_boundaries(self):
        line = {"step": 1, "sample_index": 0, "timestep": 10, "loss": 0.2, "grad_norm": 0.1}
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as stream:
            root = Path(directory).resolve()
            code = "import json;print(json.dumps(" + repr(line) + "))"
            result = worker.run_command([sys.executable, "-c", code], root, train_steps=1)
            self.assertEqual(result["returncode"], 0)
            events = [json.loads(raw) for raw in stream.getvalue().splitlines()]
            self.assertEqual([event["completed_steps"] for event in events if event["type"] == "metric"], [1])
        for code, expected in [("print('x' * 65537)", "MEDIA_EVENT_TOO_LARGE"), ("raise SystemExit(7)", "MEDIA_EXECUTION_FAILED")]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(worker.common.WorkerError) as error:
                    worker.run_command([sys.executable, "-c", code], Path(directory).resolve())
                self.assertEqual(error.exception.code, expected)

    def test_cancel_reaps_actual_child_before_returning(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory).resolve()
            pid_file = root / "child-pid"
            code = "import os,time;from pathlib import Path;Path(" + repr(str(pid_file)) + ").write_text(str(os.getpid()));time.sleep(30)"
            def cancel_when_started():
                deadline = time.monotonic() + 5
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                worker.common.cancel_handler()
            thread = threading.Thread(target=cancel_when_started)
            thread.start()
            # 函数单测只停止创建的子进程；完整独立组由产品生命周期测试验证。
            with patch.object(worker.os, "getpgrp", return_value=-1), self.assertRaises(worker.common.WorkerError) as error:
                worker.run_command([sys.executable, "-c", code], root)
            thread.join(timeout=5)
            self.assertEqual(error.exception.code, "CANCELLED")
            child_pid = int(pid_file.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)


if __name__ == "__main__":
    unittest.main()
