"""用实际解析器、无模型源码夹具和真实 PYZ 读写器核对静态索引接入。"""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PyInstaller import HOMEPATH
from PyInstaller.archive.writers import CArchiveWriter, ZlibArchiveWriter
from PyInstaller.building.build_main import Analysis
from PyInstaller.depend.analysis import PyiModuleGraph
from PyInstaller.loader.pyimod01_archive import ZlibArchiveReader


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("index_packaging", ROOT / "scripts/desktop/package_media.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)
index = packaging.transformers_index
PROFILE = "diffusers" if sys.version_info[:2] == (3, 13) else "kokoro"
CURRENT = ROOT / f"apps/desktop/src-tauri/resources/{PROFILE}/_internal/transformers"
LOADER = ROOT / "scripts/desktop/transformers_index_runtime.py"
MODEL_LIBRARIES = {"torch", "transformers", "kokoro", "diffusers", "misaki"}


class IndexBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="导入索引夹具 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "venv/transformers"
        for name in index.SOURCE_SHA256:
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((CURRENT / name).read_bytes())
        for name, content in {
            "models/albert/configuration_albert.py": '__all__ = ["AlbertConfig", "Shared"]\n',
            "models/albert/modeling_albert.py": '__all__ = ["AlbertModel"]\n',
            "models/albert/modeling_tf_albert.py": '__all__ = ["TFAlbertModel"]\n',
            "models/zeta/configuration_zeta.py": '__all__ = ["ZetaConfig", "Shared"]\n',
            "models/zeta/tokenization_zeta_fast.py": '__all__ = ["ZetaTokenizerFast"]\n',
            "utils/retained.json": '{"retained":true}\n',
        }.items():
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        # 只有小型模型源码集合使用夹具指纹；三份已核算法/入口仍是实际原字节。
        self.patch = patch.object(index, "MODELS_SHA256", index.fingerprint(index.source_files(self.source / "models")))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.overlay = self.root / "overlay/transformers"
        self.before = index.source_files(self.source)
        self.imported = {name for name in sys.modules if name.split(".")[0] in MODEL_LIBRARIES}

    def tearDown(self):
        self.assertEqual({name for name in sys.modules if name.split(".")[0] in MODEL_LIBRARIES}, self.imported)

    def prepare(self):
        return index.prepare_overlay(self.source, self.overlay, LOADER, "4.57.6")

    def test_overlay_changes_only_top_call_and_preserves_albert_and_source(self):
        provenance = self.prepare()
        self.assertEqual(index.source_files(self.source), self.before)
        patched = (self.overlay / "__init__.py").read_text()
        self.assertEqual(patched.replace(index.INDEX_CALL, index.ORIGINAL_CALL), (self.source / "__init__.py").read_text())
        self.assertIn('import_structure[frozenset({})].update(_import_structure)', patched)
        self.assertEqual((self.overlay / "models/albert/__init__.py").read_bytes(), (self.source / "models/albert/__init__.py").read_bytes())
        self.assertEqual(provenance["source_tree_sha256"], index.fingerprint(self.before))
        self.assertEqual(provenance["index_sha256"], index.verify_final_index(self.overlay)["index_sha256"])

    def test_version_and_algorithm_changes_are_rejected_before_copy(self):
        for version in [None, "4.57.5", "4.58.0"]:
            with self.subTest(version=version), self.assertRaises(ValueError):
                index.prepare_overlay(self.source, self.overlay, LOADER, version)
        algorithm = self.source / "utils/import_utils.py"
        algorithm.write_bytes(algorithm.read_bytes() + b"\n# changed\n")
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.overlay.exists())

    def test_model_file_changes_are_rejected_before_copy(self):
        (self.source / "models/zeta/configuration_zeta.py").write_text('__all__ = ["Different"]\n')
        with self.assertRaisesRegex(ValueError, "模型源码集合变化"):
            self.prepare()
        self.assertFalse(self.overlay.exists())

    def test_packaging_copies_loader_from_frozen_application_source(self):
        frozen = self.root / "frozen"
        loader = frozen / "application/scripts/desktop/transformers_index_runtime.py"
        loader.parent.mkdir(parents=True)
        loader.write_bytes(LOADER.read_bytes() + b"\n# frozen fixture source\n")
        destination = self.root / "packaging"
        destination.mkdir()
        distribution = SimpleNamespace(locate_file=lambda name: self.source)
        with patch.object(packaging.importlib.metadata, "distribution", return_value=distribution):
            overlay, provenance = packaging.prepare_overlay(destination, {"transformers": "4.57.6"}, frozen)
        self.assertEqual((overlay / index.LOADER_NAME).read_bytes(), loader.read_bytes())
        self.assertEqual(provenance["loader_sha256"], index.sha(loader.read_bytes()))
        self.assertNotEqual(provenance["loader_sha256"], index.sha(LOADER.read_bytes()))

    def test_existing_overlay_and_source_links_are_rejected(self):
        self.overlay.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            self.prepare()
        (self.source / "external").symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "链接"):
            self.prepare()

    def test_final_directory_order_is_recomputed_and_wrong_order_is_not_repaired_by_verify(self):
        provenance = self.prepare()
        before = (self.overlay / index.INDEX_NAME).read_bytes()
        final = self.root / "final/transformers"
        shutil.copytree(self.overlay, final)
        original_listdir = os.listdir
        def reversed_models(path):
            values = original_listdir(path)
            return list(reversed(values)) if Path(path) == final / "models" else values
        with patch.object(index.os, "listdir", side_effect=reversed_models):
            with self.assertRaisesRegex(ValueError, "顺序不一致"):
                index.verify_final_index(final)
            self.assertEqual((final / index.INDEX_NAME).read_bytes(), before)
            result = index.finalize_index(final, provenance)
            self.assertNotEqual((final / index.INDEX_NAME).read_bytes(), before)
            self.assertEqual(result["index_sha256"], index.verify_final_index(final)["index_sha256"])
        self.assertEqual(index.source_files(self.source), self.before)

    def test_final_complete_tree_change_is_rejected(self):
        provenance = self.prepare()
        (self.overlay / "utils/retained.json").write_text('{"retained":false}')
        with self.assertRaisesRegex(ValueError, "完整源码集合变化"):
            index.finalize_index(self.overlay, provenance)

    def test_readonly_verifier_does_not_create_bytecode_with_default_python(self):
        self.prepare()
        child = '''
from pathlib import Path
import hashlib,json,sys,types
assert sys.dont_write_bytecode is False
assert sys.pycache_prefix is None
generator,package,model_fingerprint=map(str,sys.argv[1:])
module=types.ModuleType("fixture_generator")
module.__file__=generator
exec(compile(Path(generator).read_bytes(),generator,"exec"),module.__dict__)
module.MODELS_SHA256=model_fingerprint
package=Path(package)
def complete_tree():
    records={}
    for path in [package,*sorted(package.rglob("*"))]:
        record=path.lstat()
        records[str(path.relative_to(package))]={"mode":record.st_mode,"inode":record.st_ino,
            "size":record.st_size,"mtime_ns":record.st_mtime_ns,"ctime_ns":record.st_ctime_ns,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}
    return records
before=complete_tree()
module.verify_final_index(package)
after=complete_tree()
added=sorted(set(after)-set(before))
changed=sorted(name for name in set(before)&set(after) if before[name]!=after[name])
print(json.dumps({"bytecode_allowed":not sys.dont_write_bytecode,"added":added,"changed":changed,"all_objects_unchanged":before==after}))
raise SystemExit(0 if before==after else 1)
'''
        environment = os.environ.copy()
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        done = subprocess.run([sys.executable, "-s", "-c", child, str(ROOT / "scripts/desktop/transformers_index.py"),
                               str(self.overlay), index.MODELS_SHA256], env=environment, capture_output=True, text=True)
        print(done.stdout.strip())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(json.loads(done.stdout)["bytecode_allowed"])
        self.assertTrue(json.loads(done.stdout)["all_objects_unchanged"])

    def test_overlay_datas_replaces_old_sources_without_duplicate_target(self):
        self.prepare()
        other = self.root / "other.json"
        other.write_text("{}")
        actual = index.overlay_datas([(str(self.source / "__init__.py"), "transformers"), (str(other), ".")], self.overlay)
        targets = [str(Path(destination) / Path(source).name) for source, destination in actual]
        self.assertEqual(len(targets), len(set(targets)))
        self.assertIn((str(other), "."), actual)
        self.assertEqual(next(source for source, destination in actual if str(Path(destination) / Path(source).name) == "transformers/__init__.py"), str(self.overlay / "__init__.py"))
        self.assertIn("transformers/" + index.LOADER_NAME, targets)
        self.assertIn("transformers/" + index.INDEX_NAME, targets)
        self.assertIn("transformers/utils/retained.json", targets)

    def test_dynamic_merge_preserves_complete_mapping_and_missing_backend_flags(self):
        self.prepare()
        scanned = index.original_mapping(self.overlay)
        restored = index.runtime_module(self.overlay).load_models_index(self.overlay / "__init__.py")
        dynamic = {"models.albert.configuration_albert": {"DynamicConfig", "Shared"}, "dynamic": {"Shared", "OnlyDynamic"}}
        for value in [scanned, restored]:
            value[frozenset()].update(dynamic)
        self.assertEqual(scanned, restored)
        self.assertEqual(index.ordered(scanned), index.ordered(restored))
        # 对每个对象核后写来源和缺失标签；不把所有后端伪装成可用。
        def ownership(value, available):
            return {name: (module, tags - available) for tags, modules in value.items() for module, names in modules.items() for name in names}
        for available in [frozenset(), frozenset({"torch", "tokenizers"})]:
            self.assertEqual(ownership(scanned, available), ownership(restored, available))
        self.assertEqual(ownership(restored, frozenset())["Shared"][0], "dynamic")
        self.assertEqual(ownership(restored, frozenset())["AlbertModel"][1], frozenset({"torch"}))

    def test_actual_pyinstaller_overlay_priority_reaches_pyz_code(self):
        # 两份同名无依赖夹具不能被真正执行；只让已安装 PyInstaller 分析和写 PYZ。
        fake_source = self.root / "fake-venv/transformers"
        fake_overlay = self.root / "fake-overlay/transformers"
        for base, marker in [(fake_source, "OLD_SOURCE"), (fake_overlay, "OVERLAY_SOURCE")]:
            for relative in ["__init__.py", index.LOADER_NAME, "models/albert/__init__.py"]:
                path = base / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f'MARKER = "{marker}"\nraise RuntimeError("fixture must not execute")\n')
        (fake_overlay / "models/__init__.py").write_text("")
        script = self.root / "entry.py"
        script.write_text("import transformers\nimport transformers._ailab_import_index\nimport transformers.models.albert\n")
        graph = PyiModuleGraph(HOMEPATH, path=[str(fake_source.parent), *sys.path])
        pathex = Analysis._extend_pathex(None, [str(fake_overlay.parent)], [str(script)])
        graph.path = pathex + graph.path
        graph.add_script(str(script))
        names = {"transformers": "__init__.py", "transformers._ailab_import_index": index.LOADER_NAME,
                 "transformers.models.albert": "models/albert/__init__.py"}
        entries = []
        for name, relative in names.items():
            self.assertEqual(Path(graph.find_node(name).filename), fake_overlay / relative)
            entries.append((name, str(fake_overlay / relative), "PYMODULE"))
        archive = self.root / "fixture.pyz"
        ZlibArchiveWriter(str(archive), entries, code_dict=graph.get_code_objects())
        reader = ZlibArchiveReader(str(archive))
        self.assertEqual(index.verify_pyz_sources(reader, fake_overlay), names)
        envelope = self.root / "fixture-carchive.bin"
        CArchiveWriter(str(envelope), [("PYZ.pyz", str(archive), False, "z")], "fixture-python.dylib")
        self.assertEqual(index.verify_executable_sources(envelope, fake_overlay), names)
        with self.assertRaisesRegex(ValueError, "实际 PYZ"):
            index.verify_pyz_sources(reader, fake_source)

    def test_build_selects_overlay_and_seals_each_final_tree_without_real_build(self):
        provenance = self.prepare()
        source = self.root / "frozen"
        for name in ["entry/runtime-diffusers.lock.txt", "entry/runtime-diffusers.sources.json", "entry/media_entry.py",
                     "adapters/media/prepare_tiny_sd.py", "adapters/media/prepare_svd.py", "adapters/media/image_cli.py"]:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")
        (self.root / ".artifacts/desktop").mkdir(parents=True)
        captured = []
        def fixture_build(options):
            captured.extend(options)
            internal = self.root / ".artifacts/desktop/diffusers-dist/ailab-diffusers/_internal"
            internal.mkdir(parents=True)
            for i, value in enumerate(options):
                if value == "--add-data":
                    origin, target = options[i + 1].rsplit(":", 1)
                    destination = internal / target / Path(origin).name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, destination)
            (internal.parent / "ailab-diffusers").write_bytes(b"not an executable")
        with patch.object(packaging.platform, "python_version", return_value="3.13.9"), \
                patch.object(packaging, "dependencies", return_value={"transformers": "4.57.6"}), \
                patch.object(packaging, "prepare_overlay", return_value=(self.overlay, provenance)) as prepare, \
                patch.object(packaging, "collect_all", return_value=([], [], [])), \
                patch.object(packaging, "copy_metadata", return_value=[]), \
                patch.object(packaging, "dependency_data", return_value=[]), \
                patch.object(packaging, "licenses"), \
                patch.object(packaging.PyInstaller.__main__, "run", side_effect=fixture_build), \
                patch.object(index, "verify_executable_sources") as verify_executable:
            packaging.build(self.root, source, "diffusers")
        paths = [captured[i + 1] for i, value in enumerate(captured) if value == "--paths"]
        self.assertEqual(paths[0], str(self.overlay.parent))
        self.assertIn("transformers._ailab_import_index", captured)
        prepare.assert_called_once_with(self.root / ".artifacts/desktop/diffusers-packaging-data", {"transformers": "4.57.6"}, source)
        verify_executable.assert_called_once()
        for base in [self.root / ".artifacts/desktop/diffusers-dist/ailab-diffusers", self.root / "apps/desktop/src-tauri/resources/diffusers"]:
            manifest = json.loads((base / "runtime-manifest.json").read_text())
            actual = {str(path.relative_to(base)): index.sha(path.read_bytes()) for path in base.rglob("*")
                      if path.is_file() and path != base / "runtime-manifest.json"}
            self.assertEqual(manifest["files"], actual)
            saved = json.loads((base / "_internal/source-manifest.json").read_text())["transformers_index"]
            self.assertEqual(saved["index_sha256"], index.verify_final_index(base / "_internal/transformers")["index_sha256"])


class CurrentSourceTests(unittest.TestCase):
    def test_actual_1958_file_input_and_complete_roundtrip_without_model_import(self):
        before = {name for name in sys.modules if name.split(".")[0] in MODEL_LIBRARIES}
        original = index.original_mapping(CURRENT)
        specification = importlib.util.spec_from_file_location("fixture_index_runtime", LOADER)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        raw = json.dumps({"schema_version": 1, "transformers_version": "4.57.6", "prefix": "models", "groups": index.ordered(original)}).encode()
        restored = module.decode_models_index(raw)
        self.assertEqual(original, restored)
        self.assertEqual(index.ordered(original), index.ordered(restored))
        self.assertEqual(len(original), 18)
        self.assertEqual(sum(len(v) for v in original.values()), 1390)
        self.assertEqual(sum(len(names) for rows in original.values() for names in rows.values()), 3586)
        # 代表性输入还走完整准备入口：真实源码完整复制到新临时目录，不写现有运行时。
        source_before = index.source_files(CURRENT)
        with tempfile.TemporaryDirectory(prefix="实际源码索引准备 ") as temporary:
            overlay = Path(temporary) / "transformers"
            provenance = index.prepare_overlay(CURRENT, overlay, LOADER, "4.57.6")
            self.assertEqual(provenance["source_tree_sha256"], index.fingerprint(source_before))
            self.assertEqual(provenance["index_sha256"], index.verify_final_index(overlay)["index_sha256"])
            self.assertEqual(index.source_files(CURRENT), source_before)
        self.assertEqual({name for name in sys.modules if name.split(".")[0] in MODEL_LIBRARIES}, before)


if __name__ == "__main__":
    unittest.main()
