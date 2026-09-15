"""图片试验配置、身份与覆写拒绝的代表性负例。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "media"))
from image_cli import checked_output, config_snapshot, validate_numbers, verify_model
from prepare_tiny_sd import REPO, REVISION, sha256


class ImageContractTests(unittest.TestCase):
    def test_scheduler_unbounded_default_is_explicit_json(self):
        snapshot = config_snapshot({"lambda_min_clipped": float("-inf"), "_use_default_values": {"a"}, "beta_start": 0.00085})
        self.assertEqual(snapshot["lambda_min_clipped"], {"non_finite_float": "-inf"})
        self.assertEqual(snapshot["beta_start"], 0.00085)
        json.dumps(snapshot, allow_nan=False)

    def test_allowed_parameters(self):
        for size in (256, 384, 512):
            validate_numbers(size, 12, 7.5, 0.0001, 4)

    def test_reject_unresolved_or_invalid_parameters(self):
        cases = [(513, 12, 7.5, None, 4), (512, 0, 7.5, None, 4),
                 (512, 51, 7.5, None, 4), (512, True, 7.5, None, 4),
                 (512, 2.5, 7.5, None, 4), (512, 12, float("nan"), None, 4),
                 (512, 12, 7.5, float("inf"), 4), (512, 12, 7.5, 0, 4),
                 (512, 12, 7.5, 0.0001, 3)]
        for parameters in cases:
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                validate_numbers(*parameters)

    def test_manifest_missing_changed_wrong_base_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "safetensors").mkdir()
            weight = root / "safetensors" / "fixture.safetensors"
            weight.write_bytes("哈希测试夹具，不用于模型运行".encode())
            manifest = {"repo": REPO, "revision": REVISION, "runtime_format": "safetensors",
                        "converted_files": [{"path": weight.name, "sha256": sha256(weight)}]}
            def persist():
                (root / "manifest.json").write_text(json.dumps(manifest))
            persist()
            self.assertEqual(verify_model(root)[0], root / "safetensors")
            weight.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "摘要"):
                verify_model(root)
            weight.unlink()
            with self.assertRaisesRegex(ValueError, "缺失"):
                verify_model(root)
            manifest["revision"] = "different-base"
            persist()
            with self.assertRaisesRegex(ValueError, "身份"):
                verify_model(root)
            manifest["revision"] = REVISION
            manifest["converted_files"][0]["path"] = "../manifest.json"
            persist()
            with self.assertRaisesRegex(ValueError, "越界"):
                verify_model(root)

    def test_output_never_overwrites_previous_result(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "结果"
            checked_output(output)
            marker = output / "image.png"
            marker.write_bytes(b"previous")
            with self.assertRaisesRegex(ValueError, "已存在"):
                checked_output(output)
            self.assertEqual(marker.read_bytes(), b"previous")


if __name__ == "__main__":
    unittest.main()
