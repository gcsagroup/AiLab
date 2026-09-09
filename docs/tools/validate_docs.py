#!/usr/bin/env python3
"""检查当前文档结构、追踪关系和阶段依赖；不把文档通过当作产品验收。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit


DOCS_ROOT = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"\b(PRD|WP|AC|AUD|E|TV|GAP)-(\d{1,3})([a-z]?)(?!\w)")
RANGE_RE = re.compile(r"\s*[—–~～至]\s*(?:(PRD|WP|AC|AUD|E|TV|GAP)-)?(\d{1,3})([a-z]?)(?!\w)")
WIDTH = {"PRD": 3}


def identifier(kind: str, number: int, suffix: str = "") -> str:
    return f"{kind}-{number:0{WIDTH.get(kind, 2)}d}{suffix}"


def ids(text: str, kind: str | None = None) -> set[str]:
    """展开 WP-05—WP-08、AC-06／08 和 WP-28a/b 等已有文档写法。"""
    found: set[str] = set()
    for match in ID_RE.finditer(text):
        prefix, number, suffix = match.groups()
        if kind and prefix != kind:
            continue
        start = int(number)
        found.add(identifier(prefix, start, suffix))
        tail = text[match.end():]
        endpoint = RANGE_RE.match(tail)
        if endpoint and (endpoint[1] is None or endpoint[1] == prefix):
            end, end_suffix = int(endpoint[2]), endpoint[3]
            if not suffix and not end_suffix and start <= end:
                found.update(identifier(prefix, n) for n in range(start, end + 1))
        short = re.match(r"((?:\s*[/／]\s*(?:\d{1,3}[a-z]?|[a-z]))+)", tail)
        if short:
            for item in re.split(r"\s*[/／]\s*", short[1])[1:]:
                if item.isalpha():
                    found.add(identifier(prefix, start, item))
                else:
                    part = re.fullmatch(r"(\d+)([a-z]?)", item)
                    if part:
                        found.add(identifier(prefix, int(part[1]), part[2]))
    found.update(re.findall(r"\bGATE-M[1-6]\b", text) if kind in (None, "GATE") else [])
    return found


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def error(self, code: str, where: str, detail: str) -> None:
        self.errors.append(f"{code} {where}：{detail}")

    def count(self, name: str, amount: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + amount


@dataclass
class Table:
    path: Path
    headers: list[str]
    rows: list[tuple[int, list[str]]]

    def records(self) -> list[tuple[int, dict[str, str]]]:
        return [(line, dict(zip(self.headers, cells))) for line, cells in self.rows]


def cells(line: str) -> list[str]:
    return [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def parse_markdown(path: Path, text: str, report: Result) -> tuple[str, list[Table]]:
    """保留行号，将代码块与表格正文分开检查。"""
    visible: list[str] = []
    fence = ""
    language = ""
    block: list[str] = []
    opening = 0
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if not fence and marker:
            fence, language, opening = marker[1], marker[2].strip(), number
            block = []
            visible.append("")
        elif fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                if language == "json":
                    try:
                        json.loads("\n".join(block), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                    except (ValueError, json.JSONDecodeError) as exc:
                        report.error("JSON", f"{path.name}:{opening}", str(exc))
                    report.count("JSON 示例")
                fence = ""
            else:
                block.append(line)
            visible.append("")
        else:
            visible.append(line)
    if fence:
        report.error("FENCE", f"{path.name}:{opening}", "代码块未闭合")
    if sum(bool(re.match(r"^#\s+", line)) for line in visible) != 1:
        report.error("TITLE", path.name, "必须有且只有一个一级标题")
    tables: list[Table] = []
    pos = 0
    while pos + 1 < len(visible):
        if visible[pos].lstrip().startswith("|") and re.fullmatch(r"[\s|:\-]+", visible[pos + 1]) and "-" in visible[pos + 1]:
            headers = cells(visible[pos])
            if len(headers) != len(cells(visible[pos + 1])):
                report.error("TABLE", f"{path.name}:{pos + 2}", "表头与分隔行列数不一致")
            table = Table(path, headers, [])
            pos += 2
            while pos < len(visible) and visible[pos].lstrip().startswith("|"):
                row = cells(visible[pos])
                if len(row) != len(headers):
                    report.error("TABLE", f"{path.name}:{pos + 1}", f"应有 {len(headers)} 列，实际 {len(row)} 列")
                table.rows.append((pos + 1, row))
                pos += 1
            tables.append(table)
            report.count("表格")
        else:
            pos += 1
    return "\n".join(visible), tables


def check_links(path: Path, visible: str, report: Result) -> None:
    for match in re.finditer(r"\[[^\]]*\]\((<[^>]+>|[^\n)]*)\)", visible):
        target = match[1].strip()
        target = target[1:-1] if target.startswith("<") and target.endswith(">") else re.split(r'\s+"', target, maxsplit=1)[0]
        if not target or target.startswith("#") or urlsplit(target).scheme:
            continue
        raw_path = unquote(target.split("#", 1)[0])
        line_ref = re.search(r":(\d+)$", raw_path)
        line_number = int(line_ref[1]) if line_ref else None
        if line_ref:
            raw_path = raw_path[:line_ref.start()]
        linked = Path(raw_path)
        linked = linked if linked.is_absolute() else path.parent / linked
        where = f"{path.name}:{visible.count(chr(10), 0, match.start()) + 1}"
        report.count("本地链接")
        if not linked.exists():
            report.error("LINK", where, f"目标不存在：{target}")
        elif line_number is not None:
            try:
                if not 1 <= line_number <= len(linked.read_text(encoding="utf-8").splitlines()):
                    report.error("LINK_LINE", where, f"目标行号越界：{target}")
            except (OSError, UnicodeError):
                report.error("LINK_LINE", where, f"目标不能作为文本读取：{target}")


def records(tables: list[Table], required: set[str]) -> list[tuple[str, dict[str, str]]]:
    return [(f"{table.path.name}:{line}", row) for table in tables if required <= set(table.headers) for line, row in table.records()]


def unique_rows(rows: list[tuple[str, dict[str, str]]], column: str, kind: str, report: Result) -> dict[str, tuple[str, dict[str, str]]]:
    found = {}
    for where, row in rows:
        candidates = ids(row.get(column, ""), kind)
        if len(candidates) != 1:
            report.error("DEFINITION", where, f"{column} 必须定义一个 {kind} 编号")
            continue
        key = next(iter(candidates))
        if key in found:
            report.error("DUPLICATE", where, f"{key} 重复定义")
        found[key] = (where, row)
    return found


def expected_ids(actual: set[str], kind: str, end: int, where: str, report: Result) -> None:
    missing = {identifier(kind, number) for number in range(1, end + 1)} - actual
    if missing:
        report.error("COVERAGE", where, f"缺少 {','.join(sorted(missing))}")


def same_set(actual: set[str], expected: set[str], code: str, where: str, label: str, report: Result) -> None:
    if actual != expected:
        report.error(code, where, f"{label}关系不一致；缺少 {sorted(expected - actual)}；多出 {sorted(actual - expected)}")


def check_schedule(text: str, tables: list[Table], report: Result) -> None:
    phase_rows = records(tables, {"阶段", "主要目标", "进入条件", "退出条件"})
    phase_totals: dict[str, tuple[int, int]] = {}
    for where, row in phase_rows:
        phase = re.match(r"M[0-6]\b", row["阶段"])
        duration = next((value for label, value in row.items() if "周期" in label), "")
        interval = re.fullmatch(r"(\d+)\s*[—–~～-]\s*(\d+)\s*周", duration)
        if not phase or not interval:
            report.error("SCHEDULE", where, "阶段或周期格式不明确，应为 M0—M6 及最短—最长周数")
            continue
        low, high = map(int, interval.groups())
        if phase[0] in phase_totals or low <= 0 or high < low:
            report.error("SCHEDULE", where, "阶段重复或周期区间无效")
        phase_totals[phase[0]] = (low, high)
    same_set(set(phase_totals), {f"M{i}" for i in range(7)}, "SCHEDULE", "09", "阶段", report)
    summary_lines = "\n".join(line for line in text.splitlines() if "顺序累计" in line)
    declared = re.search(r"(\d+)\s*[—–~～-]\s*(\d+)\s*周", summary_lines)
    if not declared:
        report.error("SCHEDULE_TOTAL", "09", "缺少可核对的顺序累计最短—最长周数")
    elif phase_totals:
        actual = (sum(item[0] for item in phase_totals.values()), sum(item[1] for item in phase_totals.values()))
        if tuple(map(int, declared.groups())) != actual:
            report.error("SCHEDULE_TOTAL", "09", f"阶段逐行相加为 {actual[0]}—{actual[1]} 周，与正文累计不一致")


def check_dependencies(work: dict, subwork: dict, report: Result) -> None:
    """复合工作包须引用显式子交付，不给任何工作包永久豁免。"""
    graph: dict[str, set[str]] = {}
    phases: dict[str, int] = {}
    nodes = {**work, **subwork}
    for key, (where, _) in subwork.items():
        parent = re.sub(r"[a-z]$", "", key)
        if key == parent or parent not in work:
            report.error("DEPENDENCY_PARENT", where, f"{key} 没有对应顶层工作包")
    for key, (where, row) in nodes.items():
        stage = row.get("阶段", "")
        stage_ids = {int(number) for number in re.findall(r"\bM([0-6])\b", stage)}
        child_ids = {child for child in subwork if re.sub(r"[a-z]$", "", child) == key}
        if child_ids:
            # 父行只是阶段汇总；由有明确阶段的子行承载依赖边。
            if not row.get("依赖", "").startswith("见 ") or ids(row["依赖"], "WP") != child_ids:
                report.error("DEPENDENCY_SUMMARY", where, f"{key} 的汇总依赖必须明确列出全部自身子项，实际依赖写在子项行")
            child_phases = set().union(*({int(n) for n in re.findall(r"\bM([0-6])\b", subwork[child][1]["阶段"])} for child in child_ids))
            same_set({str(n) for n in child_phases}, {str(n) for n in stage_ids}, "DEPENDENCY_SUMMARY", where, key + " 的父子阶段", report)
            child_acceptance = set().union(*(ids(subwork[child][1].get("最终 AC", ""), "AC") for child in child_ids))
            same_set(child_acceptance, ids(row.get("最终 AC", ""), "AC"), "DEPENDENCY_SUMMARY", where, key + " 的父子最终验收", report)
            continue
        if len(stage_ids) != 1:
            report.error("DEPENDENCY_STAGE", where, f"{key} 跨阶段交付需显式子交付行")
            continue
        phases[key] = next(iter(stage_ids))
        dependencies = ids(row.get("依赖", ""), "WP")
        all_targets = "全部目标工作包" in row.get("依赖", "")
        if all_targets:
            dependencies = set(work) - {key}
        graph[key] = set()
        for dependency in dependencies:
            if dependency not in nodes:
                report.error("DEPENDENCY_UNKNOWN", where, f"{key} 引用不存在的 {dependency}")
                continue
            dependency_children = {child for child in subwork if re.sub(r"[a-z]$", "", child) == dependency}
            if dependency_children and not all_targets:
                report.error("DEPENDENCY_AMBIGUOUS", where, f"{key} 依赖跨阶段 {dependency}，须引用具体子项")
            graph[key].update(dependency_children or {dependency})
    for key, dependencies in graph.items():
        for dependency in dependencies:
            if dependency in phases and phases[dependency] > phases[key]:
                report.error("DEPENDENCY_STAGE", nodes[key][0], f"{key} 的 M{phases[key]} 依赖后期 {dependency} 的 M{phases[dependency]}")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            report.error("DEPENDENCY_CYCLE", "10", "依赖成环：" + " → ".join(trail + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in sorted(graph.get(node, set())):
            visit(dependency, trail + [node])
        visiting.remove(node)
        visited.add(node)
    for key in sorted(graph):
        visit(key, [])


def check_archive(root: Path, report: Result) -> None:
    for manifest in sorted((root / "archive").glob("*/manifest.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if "sha256" in data:
                entries = [{"path": name, "sha256": digest} for name, digest in data["sha256"].items()]
            else:
                entries = data.get("files", [])
                entries = [{"path": path, **value} for path, value in entries.items()] if isinstance(entries, dict) else entries
            if not entries:
                report.error("ARCHIVE", str(manifest.relative_to(root)), "清单没有可核对的文件")
            for item in entries:
                name = item.get("path", item.get("name", ""))
                file = manifest.parent / name
                if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != item["sha256"]:
                    report.error("ARCHIVE", str(manifest.relative_to(root)), f"历史文件摘要不符：{name}")
                report.count("历史摘要")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report.error("ARCHIVE", str(manifest.relative_to(root)), f"清单无法核对：{exc}")


def validate_docs(root: Path = DOCS_ROOT, archive: bool = False) -> Result:
    root = root.resolve()
    report = Result()
    texts: dict[str, str] = {}
    visible: dict[str, str] = {}
    tables: dict[str, list[Table]] = {}
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        texts[path.name] = text
        visible[path.name], tables[path.name] = parse_markdown(path, text, report)
        check_links(path, visible[path.name], report)
        report.count("当前 Markdown")
    files = {"prd": "01-product-requirements.md", "roadmap": "09-development-roadmap.md", "work": "10-work-breakdown.md", "acceptance": "11-testing-and-acceptance.md", "tracking": "16-audit-remediation-plan.md"}
    missing = set(files.values()) - set(texts)
    if missing:
        report.error("DOCUMENT", str(root), f"缺少规范文件：{sorted(missing)}")
        return report
    prd = unique_rows(records(tables[files["prd"]], {"编号", "功能", "详细要求"}), "编号", "PRD", report)
    wp_rows = records(tables[files["work"]], {"工作包", "阶段", "责任角色／规模", "需求", "交付物", "依赖", "阶段验证", "最终 AC"})
    work = unique_rows(wp_rows, "工作包", "WP", report)
    subwork = unique_rows(records(tables[files["work"]], {"子项", "阶段", "依赖"}), "子项", "WP", report)
    ac_blocks = re.split(r"(?m)^###\s+(?=AC-\d+)", texts[files["acceptance"]])[1:]
    acceptance: dict[str, set[str]] = {}
    for block in ac_blocks:
        heading = re.match(r"AC-(\d+)\b", block)
        if heading:
            key = identifier("AC", int(heading[1]))
            if key in acceptance:
                report.error("DUPLICATE", files["acceptance"], f"{key} 重复定义")
            coverage = re.search(r"覆盖\s+(PRD-[^。\n]+)", block)
            acceptance[key] = ids(coverage[1], "PRD") if coverage else set()
            if not acceptance[key]:
                report.error("AC_COVERAGE", files["acceptance"], f"{key} 缺少明确的覆盖 PRD 列表")
    tracking_tables = tables[files["tracking"]]
    # 审计表也含同名列，独立表使用恰好三列以免误认。
    tracing = unique_rows(records([t for t in tracking_tables if t.headers == ["需求", "实施工作包", "最终验收"]], {"需求"}), "需求", "PRD", report)
    audit = unique_rows(records(tracking_tables, {"编号", "规范位置", "需求", "实施工作包", "最终验收", "文档处理", "实现状态"}), "编号", "AUD", report)
    enhancements = unique_rows(records(tracking_tables, {"编号", "决策", "规范位置", "实施工作包", "最终验收", "实现状态"}), "编号", "E", report)
    expected_ids(set(prd), "PRD", 20, files["prd"], report)
    expected_ids(set(work), "WP", 30, files["work"], report)
    expected_ids(set(acceptance), "AC", 27, files["acceptance"], report)
    expected_ids(set(audit), "AUD", 14, files["tracking"], report)
    expected_ids(set(enhancements), "E", 5, files["tracking"], report)
    same_set(set(tracing), set(prd), "TRACE_COVERAGE", "16", "需求追踪行", report)
    for key, (where, row) in tracing.items():
        expected_wp = {wp for wp, (_, task) in work.items() if key in ids(task["需求"], "PRD") and wp != "WP-30"}
        expected_ac = {ac for ac, requirements in acceptance.items() if key in requirements}
        same_set(ids(row["实施工作包"], "WP"), expected_wp, "TRACE_WP", where, key + " → 工作包", report)
        same_set(ids(row["最终验收"], "AC"), expected_ac, "TRACE_AC", where, key + " → 验收", report)
        handled_ac = set().union(*(ids(work[wp][1]["最终 AC"], "AC") for wp in expected_wp)) if expected_wp else set()
        if expected_ac - handled_ac:
            report.error("TRACE_OWNER", where, f"{key} 的验收没有实施工作包承接：{sorted(expected_ac - handled_ac)}")
    for wp, (where, row) in work.items():
        requirements = ids(row["需求"], "PRD")
        final_ac = ids(row["最终 AC"], "AC")
        for ac in final_ac:
            if ac in acceptance and not requirements & acceptance[ac]:
                report.error("WP_AC", where, f"{wp} 的 {ac} 不覆盖该工作包任何需求")
        if not requirements or not final_ac:
            report.error("WP_FIELDS", where, f"{wp} 缺少需求或最终验收")
    # 从需求的对象枚举读取导出范围，再检查实施表的交付物；诊断包不能顶替用户产物。
    export_requirement = prd.get("PRD-019")
    if export_requirement:
        object_phrase = re.search(r"选择([^，。；]+)[，。；]", export_requirement[1]["详细要求"])
        if not object_phrase:
            report.error("EXPORT_SCOPE", export_requirement[0], "PRD-019 缺少可核对的导出对象枚举")
        else:
            objects = set(re.split(r"[、或和与／/]", object_phrase[1]))
            export_deliverables = "\n".join(task["交付物"] for wp, (_, task) in work.items()
                                            if wp != "WP-30" and "PRD-019" in ids(task["需求"], "PRD")
                                            and "导出" in task["交付物"])
            missing_objects = {obj for obj in objects if obj not in export_deliverables}
            if missing_objects:
                report.error("EXPORT_DELIVERABLE", "10", f"PRD-019 的普通导出对象未写入实施交付物：{sorted(missing_objects)}")
    all_acceptance_tables = tables[files["acceptance"]]
    definitions = set(prd) | set(work) | set(subwork) | set(acceptance) | set(audit) | set(enhancements)
    for table in all_acceptance_tables:
        for _, row in table.rows:
            if row:
                definitions.update(ids(row[0], "TV"))
                definitions.update(ids(row[0], "GATE"))
    definitions.update(ids("\n".join(re.findall(r"(?m)^#{2,4}\s+.*$", texts[files["acceptance"]])), "TV"))
    definitions.update(ids("\n".join(re.findall(r"(?m)^#{2,4}\s+.*$", texts[files["acceptance"]])), "GATE"))
    for table in tables.get("14-prototype-traceability.md", []):
        for _, row in table.rows:
            if row:
                definitions.update(ids(row[0], "GAP"))
    expected_ids(definitions, "TV", 3, "11", report)
    same_set({key for key in definitions if key.startswith("GATE-")}, {f"GATE-M{i}" for i in range(1, 7)}, "GATE_COVERAGE", "11", "阶段门槛", report)
    for filename, text in visible.items():
        for reference in sorted(ids(text) - definitions):
            report.error("REFERENCE", filename, f"引用未定义编号 {reference}")
    for wp, (where, row) in {**work, **subwork}.items():
        stage_validation = row.get("阶段验证", "")
        stage_numbers = {int(number) for number in re.findall(r"\bM([0-6])\b", row["阶段"])}
        if 0 in stage_numbers:
            if not ids(stage_validation, "TV") or ids(stage_validation, "AC") or ids(stage_validation, "GATE"):
                report.error("M0_GATE", where, f"{wp} 的 M0 阶段验证必须为独立 TV，不能使用最终 AC")
        else:
            for stage in stage_numbers:
                if f"GATE-M{stage}" not in ids(stage_validation, "GATE"):
                    report.error("WP_GATE", where, f"{wp} 缺少 GATE-M{stage} 阶段验证")
    for key, (where, row) in {**audit, **enhancements}.items():
        for column in ("规范位置", "实施工作包", "最终验收", "实现状态"):
            if not row.get(column, "").strip() or row[column].strip() in ("—", "无", "待定"):
                report.error("AUDIT_MAPPING", where, f"{key} 的 {column} 未落实")
        if not ids(row.get("实施工作包", ""), "WP"):
            report.error("AUDIT_MAPPING", where, f"{key} 没有实施工作包")
        if not (ids(row.get("最终验收", ""), "AC") or ids(row.get("最终验收", ""), "TV")):
            report.error("AUDIT_MAPPING", where, f"{key} 没有验收编号")
        assigned = ids(row.get("实施工作包", ""), "WP")
        assigned_tasks = [work[wp][1] for wp in assigned if wp in work]
        handled_requirements = set().union(*(ids(task["需求"], "PRD") for task in assigned_tasks)) if assigned_tasks else set()
        handled_acceptance = set().union(*(ids(task["最终 AC"], "AC") | ids(task["阶段验证"], "TV") for task in assigned_tasks)) if assigned_tasks else set()
        if ids(row.get("需求", ""), "PRD") - handled_requirements:
            report.error("AUDIT_RELATION", where, f"{key} 的需求没有被列出的实施工作包覆盖")
        if (ids(row.get("最终验收", ""), "AC") | ids(row.get("最终验收", ""), "TV")) - handled_acceptance:
            report.error("AUDIT_RELATION", where, f"{key} 的验收没有被列出的实施工作包承接")
        state = row.get("实现状态", "")
        if re.search(r"(?:Demo|原型|产品|真实实现).{0,12}(?:已修复|已完成|已通过)", state, re.IGNORECASE) or state.strip() in {"已修复", "已完成", "完成", "通过"}:
            report.error("IMPLEMENTATION_CLAIM", where, f"{key} 不得把本轮文档修订写成 Demo 或产品实现完成")
    check_schedule(texts[files["roadmap"]], tables[files["roadmap"]], report)
    check_dependencies(work, subwork, report)
    if archive:
        check_archive(root, report)
    for name, count in (("需求", len(prd)), ("工作包", len(work)), ("子交付", len(subwork)), ("最终验收", len(acceptance)), ("审计映射", len(audit)), ("增强决策", len(enhancements))):
        report.count(name, count)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=DOCS_ROOT, help="当前 docs 路径，默认脚本上级 docs 目录")
    parser.add_argument("--check-archive", action="store_true", help="额外核对历史归档摘要；不要求旧编号符合当前规范")
    parser.add_argument("--json", action="store_true", help="输出可保存的 JSON 验证结果")
    args = parser.parse_args()
    report = validate_docs(args.docs, archive=args.check_archive)
    if args.json:
        print(json.dumps({"通过": not report.errors, "统计": report.counts, "错误": report.errors, "边界": "文档静态验证，不代表 Demo 缺陷已修或产品实机验收通过"}, ensure_ascii=False, indent=2))
    else:
        print("文档验证" + ("失败" if report.errors else "通过"))
        print("；".join(f"{key} {value}" for key, value in report.counts.items()))
        for error in report.errors:
            print(error)
        print("验证边界：文档静态检查，不代表 Demo 缺陷已修或产品实机验收通过。")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
