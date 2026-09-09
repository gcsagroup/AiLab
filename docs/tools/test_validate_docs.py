#!/usr/bin/env python3
"""用当前规范的临时副本验证检查器；所有负例均不改动原文档。"""

from __future__ import annotations

import hashlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
from validate_docs import DOCS_ROOT, ids, validate_docs  # noqa: E402


class DocumentationValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline_temp = tempfile.TemporaryDirectory(prefix="ailab-docs-baseline-")
        cls.baseline = Path(cls.baseline_temp.name) / "docs"
        cls.original_hashes = cls.hashes(DOCS_ROOT)
        shutil.copytree(DOCS_ROOT, cls.baseline, ignore=shutil.ignore_patterns("__pycache__"))

    @staticmethod
    def hashes(root: Path) -> dict[str, str]:
        return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.baseline_temp.cleanup()
        if cls.hashes(DOCS_ROOT) != cls.original_hashes:
            raise AssertionError("测试期间原始文档发生变化；本轮结果不能作为稳定基线报告")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ailab-docs-case-")
        self.root = Path(self.temporary.name) / "docs"
        shutil.copytree(self.baseline, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def edit(self, filename: str, transform) -> None:
        path = self.root / filename
        before = path.read_text(encoding="utf-8")
        after = transform(before)
        self.assertNotEqual(before, after, "负例没有修改到目标，不能计为有效测试")
        path.write_text(after, encoding="utf-8")

    def edit_table_row(self, filename: str, first_cell: str, column: str, value: str) -> None:
        def transform(text: str) -> str:
            rows = text.splitlines()
            headers: list[str] = []
            changed = False
            for number, line in enumerate(rows):
                if not line.startswith("|"):
                    continue
                parsed = [cell.strip() for cell in line.strip("|").split("|")]
                if column in parsed:
                    headers = parsed
                if parsed[0].startswith(first_cell) and column in headers:
                    parsed[headers.index(column)] = value
                    rows[number] = "| " + " | ".join(parsed) + " |"
                    changed = True
                    break
            self.assertTrue(changed, f"没有找到 {first_cell} 的 {column} 列")
            return "\n".join(rows) + "\n"
        self.edit(filename, transform)

    def assert_rejected(self, code: str, archive: bool = False) -> None:
        report = validate_docs(self.root, archive=archive)
        self.assertTrue(any(error.startswith(code + " ") for error in report.errors),
                        f"应报告 {code}，实际：\n" + "\n".join(report.errors))

    def test_01_current_baseline(self) -> None:
        """真实当前文档、编号关系、阶段依赖和历史摘要全部通过。"""
        report = validate_docs(self.root, archive=True)
        self.assertEqual(report.errors, [], "\n".join(report.errors))
        self.assertEqual(report.counts["审计映射"], 14)
        self.assertEqual(report.counts["增强决策"], 5)
        self.assertGreater(report.counts["历史摘要"], 0)

    def test_02_wp14_semantic_mismatch(self) -> None:
        """编号仍存在，但把评测包改成 AI 建议关系必须拒绝。"""
        self.edit_table_row("10-work-breakdown.md", "WP-14 ", "需求", "PRD-017")
        self.edit_table_row("10-work-breakdown.md", "WP-14 ", "最终 AC", "AC-15")
        self.assert_rejected("TRACE_WP")

    def test_03_m1_duration_changes_total(self) -> None:
        """阶段表改长而正文累计不变，必须从数字求和发现。"""
        self.edit("09-development-roadmap.md", lambda text: re.sub(
            r"(\| M1[^|]+\|\s*)2—3 周", r"\g<1>8—9 周", text, count=1))
        self.assert_rejected("SCHEDULE_TOTAL")

    def test_04_missing_audit_mapping(self) -> None:
        self.edit("16-audit-remediation-plan.md", lambda text: re.sub(r"(?m)^\| AUD-09\s*\|[^\n]*\n", "", text, count=1))
        self.assert_rejected("COVERAGE")

    def test_05_m0_cannot_use_final_ac_as_exit(self) -> None:
        self.edit_table_row("10-work-breakdown.md", "WP-01 ", "阶段验证", "AC-12")
        self.assert_rejected("M0_GATE")

    def test_06_broken_local_link(self) -> None:
        self.edit("README.md", lambda text: text + "\n[缺失链接](never-created.md)\n")
        self.assert_rejected("LINK")

    def test_07_invalid_json(self) -> None:
        self.edit("05-data-model-and-assets.md", lambda text: text + '\n```json\n{"任务": }\n```\n')
        self.assert_rejected("JSON")

    def test_08_dependency_cycle(self) -> None:
        self.edit_table_row("10-work-breakdown.md", "WP-01 ", "依赖", "WP-02")
        self.edit_table_row("10-work-breakdown.md", "WP-02 ", "依赖", "WP-01")
        self.assert_rejected("DEPENDENCY_CYCLE")

    def test_09_dependency_on_later_subdelivery(self) -> None:
        self.edit_table_row("10-work-breakdown.md", "WP-03 ", "依赖", "WP-29c")
        self.assert_rejected("DEPENDENCY_STAGE")

    def test_10_unknown_dependency(self) -> None:
        self.edit_table_row("10-work-breakdown.md", "WP-03 ", "依赖", "WP-99")
        self.assert_rejected("DEPENDENCY_UNKNOWN")

    def test_11_known_ac_wrong_requirement_mapping(self) -> None:
        self.edit_table_row("16-audit-remediation-plan.md", "PRD-014", "最终验收", "AC-15")
        self.assert_rejected("TRACE_AC")

    def test_12_do_not_claim_demo_fixed(self) -> None:
        self.edit_table_row("16-audit-remediation-plan.md", "AUD-01", "实现状态", "Demo 已修复")
        self.assert_rejected("IMPLEMENTATION_CLAIM")

    def test_13_optional_line_link(self) -> None:
        self.edit("README.md", lambda text: text + "\n[有效行号](01-product-requirements.md:2)\n")
        self.assertEqual(validate_docs(self.root).errors, [])
        self.edit("README.md", lambda text: text + "\n[越界行号](01-product-requirements.md:99999)\n")
        self.assert_rejected("LINK_LINE")

    def test_14_history_is_not_current_numbering(self) -> None:
        history = self.root / "archive" / "historical-test.md"
        history.write_text("# 历史\n\nPRD-999；Demo 已修复。\n", encoding="utf-8")
        self.assertEqual(validate_docs(self.root).errors, [])

    def test_15_more_current_documents_are_allowed(self) -> None:
        (self.root / "additional-review.md").write_text("# 补充评审\n\n文档数量不作为永久门槛。\n", encoding="utf-8")
        self.assertEqual(validate_docs(self.root).errors, [])

    def test_16_range_and_short_reference_expansion(self) -> None:
        self.assertEqual(ids("PRD-001—PRD-003，WP-28a/b，AC-06／08"),
                         {"PRD-001", "PRD-002", "PRD-003", "WP-28a", "WP-28b", "AC-06", "AC-08"})

    def test_17_table_column_mismatch(self) -> None:
        self.edit("README.md", lambda text: text + "\n| 字段 | 值 |\n| --- | --- |\n| 错误 |\n")
        self.assert_rejected("TABLE")

    def test_18_unclosed_fence(self) -> None:
        self.edit("README.md", lambda text: text + "\n```text\n未闭合\n")
        self.assert_rejected("FENCE")

    def test_19_archive_digest_mismatch(self) -> None:
        self.edit("archive/v1.0-2026-09-09/README.md", lambda text: text + "\n归档错误改动。\n")
        self.assert_rejected("ARCHIVE", archive=True)

    def test_20_compound_dependency_must_name_deliverable(self) -> None:
        self.edit_table_row("10-work-breakdown.md", "WP-17 ", "依赖", "WP-16")
        self.assert_rejected("DEPENDENCY_AMBIGUOUS")

    def test_21_diagnostic_export_cannot_replace_user_artifacts(self) -> None:
        self.edit_table_row("10-work-breakdown.md", "WP-29 ", "交付物", "安装、签名、更新和诊断包导出")
        self.assert_rejected("EXPORT_DELIVERABLE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
