"""使用真实 PyInstaller 展开器验证媒体头文件过滤，不启动打包或模型。"""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if importlib.util.find_spec("PyInstaller") is None:
    raise unittest.SkipTest("本文件须在两个固定打包 Python 环境下执行；当前环境缺少 PyInstaller。")

from PyInstaller.building.utils import format_binaries_and_datas
from PyInstaller.exceptions import InvalidSrcDestTupleError


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("media_packaging_data", ROOT / "scripts/desktop/package_media.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class MediaPackagingDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="媒体打包数据 ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.imported_torch = sys.modules.get("torch")

    def source(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
        return path

    def expanded_result(self, datas):
        result = packaging.media_runtime_data(datas)
        self.assertTrue(all(Path(source).is_file() for source, _ in result))
        self.assertIs(sys.modules.get("torch"), self.imported_torch)
        return format_binaries_and_datas(result)

    def test_single_files_and_normalized_destinations(self):
        header = self.source("direct/tensor.h")
        kernel = self.source("direct/kernel.cuh")
        config = self.source("direct/config.json")
        result = self.expanded_result([
            (str(header), "torch/./include/ATen"),
            (str(kernel), "unused/../torch/include"),
            (str(config), "torch/../runtime"),
        ])
        self.assertEqual(result, {("runtime/config.json", str(config))})

    def test_parent_directory_expands_before_filtering(self):
        for name in ["torch/include/ATen/a.h", "torch/include/torch/b.hpp", "torch/include/cuda/c.cuh"]:
            self.source("tree/" + name)
        kept = ["torch/_C.so", "torch/lib/libtorch_cpu.dylib", "torch/bin/torch_shm_manager",
                "torch/__init__.py", "torch/include/config.json", "torch/include/LICENSE",
                "torch-2.14.0.dist-info/METADATA"]
        expected = {(name, str(self.source("tree/" + name))) for name in kept}
        self.assertEqual(self.expanded_result([(str(self.root / "tree"), ".")]), expected)

    def test_file_glob_filters_headers_and_keeps_data(self):
        self.source("files/ops.hpp")
        self.source("files/ops.cuh")
        data = self.source("files/ops.json")
        result = self.expanded_result([(str(self.root / "files/*"), "torch/include/ATen")])
        self.assertEqual(result, {("torch/include/ATen/ops.json", str(data))})

    def test_directory_glob_keeps_its_directory_names(self):
        self.source("packages/torch/include/ops.h")
        runtime = self.source("packages/torch/lib/runtime.dylib")
        other = self.source("packages/torch_extra/include/ops.h")
        result = self.expanded_result([(str(self.root / "packages/*"), ".")])
        self.assertEqual(result, {("torch/lib/runtime.dylib", str(runtime)),
                                  ("torch_extra/include/ops.h", str(other))})

    def test_late_cuh_entry_cannot_reintroduce_filtered_header(self):
        kernel = self.source("collected/include/kernel.cuh")
        runtime = self.source("collected/lib/runtime.dylib")
        datas = [(str(self.root / "collected"), "torch")]
        datas.append((str(kernel), "torch/include"))
        self.assertEqual(self.expanded_result(datas), {("torch/lib/runtime.dylib", str(runtime))})

    def test_similar_directories_and_other_suffixes_are_preserved(self):
        kept = ["torch/include_extra/a.h", "torchvision/include/a.h", "vendor/torch/include/a.h",
                "torch/include/a.cpp", "torch/include/a.hi", "torch/include/uppercase.H",
                "torch/include/README", "licenses/torch/LICENSE", "torch-2.14.0.dist-info/RECORD"]
        expected = {(name, str(self.source("lookalikes/" + name))) for name in kept}
        # 用独立源文件表达大写目标，避免本机文件系统将 Torch 和 torch 合并。
        uppercase_target = self.source("case-target/directory.h")
        expected.add(("Torch/include/directory.h", str(uppercase_target)))
        datas = [(str(self.root / "lookalikes"), "."), (str(uppercase_target), "Torch/include")]
        self.assertEqual(self.expanded_result(datas), expected)

    def test_distinct_sources_for_one_target_are_not_lost(self):
        first = self.source("first/config.json")
        second = self.source("second/config.json")
        result = self.expanded_result([(str(first), "runtime"), (str(second), "runtime")])
        self.assertEqual(result, {("runtime/config.json", str(first)), ("runtime/config.json", str(second))})

    def test_invalid_sources_are_rejected_even_under_filtered_target(self):
        for source in ["", str(self.root / "missing.h"), str(self.root / "missing/*.cuh")]:
            with self.subTest(source=source), self.assertRaises(SystemExit):
                packaging.media_runtime_data([(source, "torch/include")])

    def test_empty_absolute_and_escaping_destinations_remain_rejected(self):
        header = self.source("invalid/header.h")
        for destination in ["", str(self.root / "absolute"), "../escape", "torch/include/../../../escape"]:
            with self.subTest(destination=destination), self.assertRaises(InvalidSrcDestTupleError):
                packaging.media_runtime_data([(str(header), destination)])

    def test_build_filters_after_all_data_sources_without_changing_binaries(self):
        source = self.root / "frozen"
        for name in ["prepare_tiny_sd", "prepare_svd", "image_cli"]:
            self.source("frozen/adapters/media/" + name + ".py")
        self.source("frozen/entry/runtime-diffusers.lock.txt")
        (self.root / ".artifacts/desktop").mkdir(parents=True)
        self.source("collected/include/header.h")
        runtime = self.source("collected/lib/runtime.dylib")
        late_kernel = self.source("late/kernel.cuh")
        metadata = self.source("fixture.dist-info/METADATA")
        binary = self.source("native/runtime.so")
        overlay_init = self.source("overlay/transformers/__init__.py")
        captured = []

        class BuildNotStarted(Exception):
            pass

        def stop_before_build(options):
            captured.extend(options)
            raise BuildNotStarted

        with patch.object(packaging.platform, "python_version", return_value="3.13.9"), \
                patch.object(packaging, "dependencies", return_value={"fixture": "1"}), \
                patch.object(packaging, "prepare_overlay", return_value=(overlay_init.parent, {})), \
                patch.object(packaging, "collect_all", return_value=(
                    [(str(self.root / "collected"), "torch")], [(str(binary), "native")], ["fixture.runtime"])), \
                patch.object(packaging, "copy_metadata", return_value=[(str(metadata.parent), "fixture.dist-info")]), \
                patch.object(packaging, "dependency_data", return_value=[(str(late_kernel), "torch/include")]), \
                patch.object(packaging.PyInstaller.__main__, "run", side_effect=stop_before_build), \
                self.assertRaises(BuildNotStarted):
            packaging.build(self.root, source, "diffusers")

        datas = [captured[i + 1].rsplit(":", 1) for i, value in enumerate(captured) if value == "--add-data"]
        actual = format_binaries_and_datas(datas)
        self.assertIn(("torch/lib/runtime.dylib", str(runtime)), actual)
        self.assertIn(("fixture.dist-info/METADATA", str(metadata)), actual)
        self.assertNotIn(("torch/include/header.h", str(self.root / "collected/include/header.h")), actual)
        self.assertNotIn(("torch/include/kernel.cuh", str(late_kernel)), actual)
        binaries = [captured[i + 1] for i, value in enumerate(captured) if value == "--add-binary"]
        self.assertEqual(binaries, [f"{binary}:native"] * len(packaging.PROFILES["diffusers"]["packages"]))
        self.assertIn("fixture.runtime", captured)
        self.assertIs(sys.modules.get("torch"), self.imported_torch)


if __name__ == "__main__":
    unittest.main()
