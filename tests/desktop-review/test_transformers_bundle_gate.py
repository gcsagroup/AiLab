"""最终 App 索引闸的纯文件夹具；不签名、不启动探测或导入模型库。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
with patch.object(sys, "path", [str(ROOT / "scripts/desktop"), *sys.path]):
    SPEC = importlib.util.spec_from_file_location("bundle_index_gate", ROOT / "scripts/desktop/verify_bundle.py")
    verifier = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(verifier)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class TransformersBundleGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="最终索引闸 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.resources = self.root / "resources"
        self.loader = b"# frozen private loader; must not execute in this fixture\n"
        self.source_files = {
            "application/scripts/desktop/transformers_index.py": sha(Path(verifier.transformers_index.__file__).read_bytes()),
            "application/scripts/desktop/transformers_index_runtime.py": sha(self.loader),
        }
        for profile in ("diffusers", "kokoro"):
            package = self.package(profile)
            package.mkdir(parents=True)
            (package / verifier.transformers_index.LOADER_NAME).write_bytes(self.loader)
            (package / "__init__.py").write_bytes(b"# patched top-level source\n")
            (package / verifier.transformers_index.INDEX_NAME).write_text(json.dumps({"schema_version": 1, "transformers_version": "4.57.6", "prefix": "models", "groups": []}))
            self.save_manifest(profile, {"profile": profile, "required_dependencies": {"transformers": "4.57.6"},
                "transformers_index": {"transformers_version": "4.57.6", "generator_sha256": self.source_files["application/scripts/desktop/transformers_index.py"],
                    "loader_sha256": sha(self.loader), "patched_init_sha256": sha((package / "__init__.py").read_bytes()),
                    "index_sha256": sha((package / verifier.transformers_index.INDEX_NAME).read_bytes())}})
        self.imported_models = {name for name in sys.modules if name.split(".")[0] in {"torch", "transformers", "kokoro", "diffusers", "misaki"}}

    def tearDown(self):
        self.assertEqual({name for name in sys.modules if name.split(".")[0] in {"torch", "transformers", "kokoro", "diffusers", "misaki"}}, self.imported_models)

    def package(self, profile):
        return self.resources / profile / "_internal/transformers"

    def manifest(self, profile="diffusers"):
        return json.loads((self.package(profile).parent / "source-manifest.json").read_text())

    def save_manifest(self, profile, value):
        (self.package(profile).parent / "source-manifest.json").write_text(json.dumps(value))

    def mapped_result(self, package):
        self.assertIn(package, [self.package("diffusers"), self.package("kokoro")])
        return {"index_sha256": sha((package / verifier.transformers_index.INDEX_NAME).read_bytes()),
                "backend_groups": 18, "module_entries": 1390, "object_entries": 3586}

    def tree(self):
        return {str(path.relative_to(self.resources)): (path.stat().st_mode, path.stat().st_ino,
                path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ctime_ns,
                sha(path.read_bytes()) if path.is_file() else None)
                for path in [self.resources, *sorted(self.resources.rglob("*"))]}

    def test_both_actual_final_paths_and_source_bindings_are_checked_without_writes(self):
        before = self.tree()
        with patch.object(verifier.transformers_index, "verify_final_index", side_effect=self.mapped_result) as check:
            result = verifier.verify_transformers_indices(self.resources, self.source_files)
        self.assertEqual([call.args[0] for call in check.call_args_list], [self.package("diffusers"), self.package("kokoro")])
        for profile in ("diffusers", "kokoro"):
            self.assertEqual(result[profile]["index_sha256"], self.manifest(profile)["transformers_index"]["index_sha256"])
            self.assertEqual(result[profile]["loader_sha256"], self.source_files["application/scripts/desktop/transformers_index_runtime.py"])
            self.assertEqual(result[profile]["generator_sha256"], self.source_files["application/scripts/desktop/transformers_index.py"])
        self.assertEqual(self.tree(), before)

    def test_missing_index_or_source_file_fails_before_mapping(self):
        package = self.package("diffusers")
        for path in [package / verifier.transformers_index.INDEX_NAME, package / verifier.transformers_index.LOADER_NAME,
                     package / "__init__.py", package.parent / "source-manifest.json"]:
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                path.unlink()
                with patch.object(verifier.transformers_index, "verify_final_index") as check, self.assertRaises(AssertionError):
                    verifier.verify_transformers_indices(self.resources, self.source_files)
                check.assert_not_called()
                path.write_bytes(raw)

    def test_wrong_runtime_version_or_missing_provenance_fails(self):
        original = self.manifest()
        for field, value in [("profile", "kokoro"), ("required_dependencies", {"transformers": "4.57.5"}), ("transformers_index", None)]:
            with self.subTest(field=field):
                self.save_manifest("diffusers", {**original, field: value})
                with patch.object(verifier.transformers_index, "verify_final_index") as check, self.assertRaises(AssertionError):
                    verifier.verify_transformers_indices(self.resources, self.source_files)
                check.assert_not_called()
        self.save_manifest("diffusers", original)

    def test_frozen_generator_or_loader_missing_or_changed_is_rejected(self):
        for key in self.source_files:
            for value in [None, "0" * 64]:
                with self.subTest(key=key, value=value):
                    altered = {**self.source_files, key: value}
                    with patch.object(verifier.transformers_index, "verify_final_index") as check, self.assertRaises(AssertionError):
                        verifier.verify_transformers_indices(self.resources, altered)
                    check.assert_not_called()

    def test_each_provenance_binding_mismatch_is_rejected(self):
        original = self.manifest()
        for field in ["transformers_version", "generator_sha256", "loader_sha256", "patched_init_sha256", "index_sha256"]:
            with self.subTest(field=field):
                changed = {**original, "transformers_index": {**original["transformers_index"], field: "wrong"}}
                self.save_manifest("diffusers", changed)
                with patch.object(verifier.transformers_index, "verify_final_index") as check, self.assertRaises(AssertionError):
                    verifier.verify_transformers_indices(self.resources, self.source_files)
                check.assert_not_called()
        self.save_manifest("diffusers", original)

    def test_private_loader_replacement_cannot_authorize_itself(self):
        package = self.package("diffusers")
        replacement = b"raise RuntimeError('replacement must not execute')\n"
        (package / verifier.transformers_index.LOADER_NAME).write_bytes(replacement)
        changed = self.manifest()
        changed["transformers_index"]["loader_sha256"] = sha(replacement)
        self.save_manifest("diffusers", changed)
        with patch.object(verifier.transformers_index, "verify_final_index") as check, self.assertRaisesRegex(AssertionError, "冻结来源"):
            verifier.verify_transformers_indices(self.resources, self.source_files)
        check.assert_not_called()

    def test_changed_actual_top_or_index_bytes_are_rejected(self):
        for name in ["__init__.py", verifier.transformers_index.INDEX_NAME]:
            with self.subTest(name=name):
                path = self.package("diffusers") / name
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                with patch.object(verifier.transformers_index, "verify_final_index") as check, self.assertRaises(AssertionError):
                    verifier.verify_transformers_indices(self.resources, self.source_files)
                check.assert_not_called()
                path.write_bytes(original)

    def test_non_equivalent_final_order_propagates_failure_without_retry_or_repair(self):
        before = self.tree()
        with patch.object(verifier.transformers_index, "verify_final_index", side_effect=ValueError("最终目录映射顺序不一致")) as check:
            with self.assertRaisesRegex(ValueError, "顺序不一致"):
                verifier.verify_transformers_indices(self.resources, self.source_files)
        check.assert_called_once_with(self.package("diffusers"))
        self.assertEqual(self.tree(), before)

    def test_verifier_result_must_match_current_index_bytes(self):
        with patch.object(verifier.transformers_index, "verify_final_index", return_value={"index_sha256": "0" * 64}):
            with self.assertRaisesRegex(AssertionError, "核验结果"):
                verifier.verify_transformers_indices(self.resources, self.source_files)

    def test_bundle_gate_failure_stops_before_any_executable_contract_or_probe(self):
        app = self.root / "Fixture.app"
        resources = app / "Contents/Resources/resources"
        shutil.copytree(self.resources, resources)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "org.gcsa.ailab", "CFBundleShortVersionString": "2.4.0", "LSMinimumSystemVersion": "26.0"}))
        required = ["control/ailab-control", "control/_internal/certifi/cacert.pem", "workers/mlx_worker.py",
            "adapters/mlx_text/preflight.py", "adapters/mlx_text/recipe.py", "mlx/ailab-mlx", "mlx/runtime-manifest.json", "mlx/licenses/index.json",
            "diffusers/ailab-diffusers", "kokoro/ailab-kokoro", "diffusers/runtime-manifest.json", "kokoro/runtime-manifest.json",
            "diffusers/licenses/index.json", "kokoro/licenses/index.json", "media-tools/bin/ffmpeg", "media-tools/bin/ffprobe",
            "media-tools/runtime-manifest.json", "media-tools/licenses/index.json"]
        for name in required:
            path = resources / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        (resources / "control/build-manifest.json").write_text(json.dumps({"files": self.source_files,
            "source_digest": sha(json.dumps(self.source_files, sort_keys=True).encode())}))
        authority = "Authority=Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)"
        def command(*args):
            for value in args:
                if value.startswith("--extract-certificates="):
                    Path(value.split("=", 1)[1] + "0").write_bytes(b"fixture certificate")
            return "minos 26.0" if args[0] == "/usr/bin/vtool" else authority
        certificate = SimpleNamespace(hexdigest=lambda: "7C33B517942161311A087CE893D2F1CE9B204B44")
        with patch.object(verifier, "command", side_effect=command), patch.object(verifier.hashlib, "sha1", return_value=certificate), \
                patch.object(verifier, "bundle_version", return_value={"fixture": True}), \
                patch.object(verifier, "verify_transformers_indices", side_effect=ValueError("final index rejected")) as gate, \
                patch.object(verifier.subprocess, "run", side_effect=AssertionError("must not launch")) as launch:
            with self.assertRaisesRegex(ValueError, "final index rejected"):
                verifier.verify(app)
        gate.assert_called_once_with(resources.resolve(), self.source_files)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
