"""SVD 首期参数与模型身份的负例。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters" / "media"))
from video_cli import validate_video_config, verify_svd
from prepare_svd import REPO, REVISION
from prepare_tiny_sd import sha256


class VideoContractTests(unittest.TestCase):
    def test_frozen_parameters_and_rejections(self):
        validate_video_config(14, 7, 25)
        for args in [(25, 7, 25), (14, 8, 25), (14, 7, 0), (14, 7, 51), (14, 7, True)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                validate_video_config(*args)

    def test_model_checksum_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            item = root / "fixture.safetensors"
            item.write_bytes(b"checksum fixture")
            manifest = {"repo": REPO, "revision": REVISION, "variant": "fp16", "files": [{"path": item.name, "sha256": sha256(item)}]}
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            self.assertEqual(verify_svd(root), sha256(path))
            item.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "摘要"):
                verify_svd(root)
            manifest["variant"] = "fp32"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "格式"):
                verify_svd(root)


if __name__ == "__main__":
    unittest.main()
