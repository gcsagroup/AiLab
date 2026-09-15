"""三語文件檢查器的代表性正反例。"""
from pathlib import Path
import subprocess
import tempfile
import unittest

import check_translations as checker


class TranslationChecks(unittest.TestCase):
    def test_preserves_code_and_links(self):
        source = "# 標題\n\n[指南](docs/guide.md#章節)\n\n\x60[勿改](docs/guide.md)\x60\n\n\x60\x60\x60sh\n[勿改](docs/guide.md)\n\x60\x60\x60\n"
        result = checker.rewrite_links("README.md", source, "en", {"README.md", "docs/guide.md"})
        self.assertIn("[指南](docs/guide.md#章節)", result)
        nested = checker.rewrite_links("docs/guide.md", "[源碼](../src/main.py)", "en", {"docs/guide.md"})
        self.assertEqual(nested, "[源碼](../../../src/main.py)")
        self.assertEqual(checker.rewrite_links("README.md", "[简体中文](README.md)", "en", {"README.md"}), "[简体中文](../../README.md)")
        self.assertEqual([m[0] for m in checker.FENCE.finditer(source)], [m[0] for m in checker.FENCE.finditer(result)])

    def test_quantity_conversion_and_wrong_number(self):
        self.assertEqual(checker.number_counts("1 万任务，100 万条"), checker.number_counts("10,000 tasks, 1,000,000 rows"))
        self.assertEqual(checker.number_counts("1 萬任務"), checker.number_counts("10,000 tasks"))
        self.assertEqual(checker.number_counts("9 月 14 日"), checker.number_counts("September 14"))
        self.assertIn("逐行數字不同", checker.invariants("# 原文\n\n20 次，128 tokens。\n", "# Translation\n\n21 runs, 128 tokens.\n"))
        self.assertIn("逐行數字不同", checker.invariants("# 原文\n\n20\n\n128\n", "# Translation\n\n128\n\n20\n"))

    def test_structural_negative_cases(self):
        source = "# 原文\n\n- §alpha§\n\n| 欄 | 值 |\n| --- | --- |\n| A | 20 |\n\n§§§sh\ntrue\n§§§\n".replace("§", chr(96))
        self.assertEqual(checker.invariants(source, source), [])
        self.assertIn("行內程式碼內容或順序不同", checker.invariants(source, source.replace("alpha", "beta")))
        self.assertIn("程式碼圍欄內容不同", checker.invariants(source, source.replace("true", "false")))
        self.assertIn("表格列數或順序不同", checker.invariants(source, source.replace("| A | 20 |", "| A | 20 | extra |")))
        self.assertIn("標題層級不同", checker.invariants(source, source.replace("# 原文", "## 原文")))

    def test_stable_original_anchors(self):
        text = "# 主頁\n\n## 章節：測試\n\n## 章節：測試\n"
        self.assertEqual(checker.source_anchors(text), ["主頁", "章節測試", "章節測試-1"])
        with_anchor = '<a id="主頁"></a>\n\n' + text
        self.assertEqual(checker.body(with_anchor), text)

    def test_real_manifest_and_missing_tampered_broken_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "README.md").write_text("# 原文\n\n20 次。\n")
            d = {"source": "README.md", "source_sha256": checker.digest(root / "README.md")}
            for lang in checker.LANGUAGES:
                path = root / "i18n" / lang / "README.md"
                path.parent.mkdir(parents=True)
                path.write_text('<a id="原文"></a>\n\n# Translation\n\n20 runs.\n')
                d[lang] = str(path.relative_to(root))
                d[lang + "_sha256"] = checker.digest(path)
            manifest = {"documents": [d]}
            self.assertTrue(checker.check(root, manifest)["passed"])
            target = root / d["en"]
            original = target.read_text()
            target.write_text(original.replace("20", "21"))
            report = checker.check(root, manifest)
            self.assertFalse(report["passed"])
            self.assertTrue(any("逐行數字不同" in e for e in report["errors"]))
            target.write_text(original + "\n[Missing](missing.md)\n")
            report = checker.check(root, manifest)
            self.assertTrue(any("連結目標不存在" in e for e in report["errors"]))
            target.unlink()
            self.assertTrue(any("缺少譯文" in e for e in checker.check(root, manifest)["errors"]))
            target.write_text(original)
            (root / "NEW.md").write_text("# 新文件\n")
            self.assertTrue(any("原文覆蓋不一致" in e for e in checker.check(root, manifest)["errors"]))


if __name__ == "__main__":
    unittest.main()
