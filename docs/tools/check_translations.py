#!/usr/bin/env python3
"""核對三語文件覆蓋、原文身份、內容結構與鏡像連結；不執行模型。"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = ("zh-TW", "en")
FENCE = re.compile(r"^([ \t]*)(\x60{3,}|~{3,})[^\n]*\n.*?^\1\2[ \t]*$", re.M | re.S)
INLINE = re.compile(r"(\x60+)(.+?)\1")
LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\((<[^>\n]+>|[^)\n]+)\)")
META = re.compile(r"<!-- translation-navigation:start -->\n.*?<!-- translation-navigation:end -->\n\n", re.S)
ANCHOR = re.compile(r'<a id="([^"]+)"></a>\n\n')
NUMBER = re.compile(r"\d+(?:\.\d+)*")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body(text: str) -> str:
    return ANCHOR.sub("", META.sub("", text))


def without_code(text: str) -> str:
    return INLINE.sub("", FENCE.sub("", text))


def headings(text: str) -> list[tuple[int, str]]:
    return [(len(m[1]), m[2]) for m in re.finditer(r"^(#{1,6}) +(.+?)\s*#*\s*$", FENCE.sub("", text), re.M)]


def source_anchors(text: str) -> list[str]:
    """保留原文標題錨點，讓既有章節引用在兩種譯文仍可定位。"""
    seen: Counter[str] = Counter()
    result = []
    for _, title in headings(text):
        title = LINK.sub(lambda m: m[1], title)
        title = re.sub(r"<[^>]+>", "", title).replace("\x60", "").lower()
        slug = "".join(c for c in title if c in "_- " or unicodedata.category(c)[0] in "LMN")
        slug = slug.replace(" ", "-")
        count = seen[slug]
        seen[slug] += 1
        result.append(slug + ("-" + str(count) if count else ""))
    return result


def target_for(source: str, target: str, lang: str, sources: set[str]) -> str:
    wrapped = target.startswith("<") and target.endswith(">")
    raw = target[1:-1] if wrapped else target
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw) or raw.startswith(("mailto:", "data:")):
        return target
    path_part, sep, fragment = raw.partition("#")
    if not path_part:
        return target
    # 絕對本機路徑屬歷史證據，保留原值，不假造 GitHub 可下載資源。
    if path_part.startswith("/"):
        return target
    resolved = Path(os.path.normpath(str(Path(source).parent / unquote(path_part))))
    resolved_name = resolved.as_posix()
    # 明確語言切換目標保持所指語言；普通文檔引用跟隨當前語言。
    dest = Path("i18n") / lang / resolved if resolved_name in sources else resolved
    origin = Path("i18n") / lang / Path(source).parent
    rewritten = Path(os.path.relpath(dest, origin)).as_posix()
    if sep:
        rewritten += "#" + fragment
    return "<" + rewritten + ">" if wrapped else rewritten


def rewrite_links(source: str, text: str, lang: str, sources: set[str]) -> str:
    # 只改 Markdown 連結，程式碼圍欄和行內原值不得變動。
    def visible(part: str) -> str:
        def replace(match: re.Match) -> str:
            # 語言切換的簡體入口指回原文，不能誤導回當前譯文。
            mapped_sources = set() if match[1] in {"简体中文", "簡體中文", "繁體中文", "English"} else sources
            return "[" + match[1] + "](" + target_for(source, match[2], lang, mapped_sources) + ")"
        # 使用 span 保留行內程式碼原字節。
        out, start = [], 0
        for match in INLINE.finditer(part):
            out.append(LINK.sub(replace, part[start:match.start()]))
            out.append(match[0])
            start = match.end()
        out.append(LINK.sub(replace, part[start:]))
        return "".join(out)
    out, start = [], 0
    for match in FENCE.finditer(text):
        out.append(visible(text[start:match.start()]))
        out.append(match[0])
        start = match.end()
    out.append(visible(text[start:]))
    return "".join(out)


def number_counts(text: str) -> Counter[str]:
    # 日期月份與中文萬、英文千位逗號按同一數值比較。
    months = ("January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December")
    for number, month in enumerate(months, 1):
        text = re.sub(r"\b" + month + r"\b(?=\s+\d)", str(number), text)
    text = re.sub(r"(\d+)\s*[万萬]", lambda m: str(int(m[1]) * 10000), text)
    text = re.sub(r"(?<!\d)\d{1,3}(?:,\d{3})+(?!\d)", lambda m: m[0].replace(",", ""), text)
    return Counter(NUMBER.findall(text))


def invariants(source: str, translated: str) -> list[str]:
    errors = []
    if [m[0] for m in FENCE.finditer(source)] != [m[0] for m in FENCE.finditer(translated)]:
        errors.append("程式碼圍欄內容不同")
    a, b = FENCE.sub("", source), FENCE.sub("", translated)
    if [m[0] for m in INLINE.finditer(a)] != [m[0] for m in INLINE.finditer(b)]:
        errors.append("行內程式碼內容或順序不同")
    if [n for n, _ in headings(a)] != [n for n, _ in headings(b)]:
        errors.append("標題層級不同")
    a, b = INLINE.sub("", a), INLINE.sub("", b)
    if len(a.splitlines()) != len(b.splitlines()):
        errors.append("段落行數不同")
    if [not line.strip() for line in a.splitlines()] != [not line.strip() for line in b.splitlines()]:
        errors.append("空行結構不同")
    # Markdown 表格原有未跳脫的豎線也保留，因此以每行形狀核對。
    def table_shapes(text: str) -> list[int]:
        return [len(re.split(r"(?<!\\)\|", line)) for line in text.splitlines() if line.lstrip().startswith("|")]
    if table_shapes(a) != table_shapes(b):
        errors.append("表格列數或順序不同")
    def lists(text: str) -> list[str]:
        return [m[1] for m in re.finditer(r"^\s*([-*+]|\d+[.)])\s+", text, re.M)]
    if lists(a) != lists(b):
        errors.append("列表結構不同")
    a, b = LINK.sub(lambda m: m[1], a), LINK.sub(lambda m: m[1], b)
    if [number_counts(line) for line in a.splitlines()] != [number_counts(line) for line in b.splitlines()]:
        errors.append("逐行數字不同")
    return errors


def check(root: Path, manifest: dict, raw: bool = False) -> dict:
    root = root.resolve()
    documents = manifest["documents"]
    sources = {d["source"] for d in documents}
    errors, checked_links, external_evidence = [], 0, set()
    if len(sources) != len(documents):
        errors.append("清單有重複原文")
    if not raw and manifest.get("index"):
        index = root / manifest["index"]
        if not index.is_file() or digest(index) != manifest.get("index_sha256"):
            errors.append("三語目錄不存在或摘要變更")
        else:
            for match in LINK.finditer(without_code(index.read_text())):
                target = match[2].strip("<>")
                if not (index.parent / target).is_file():
                    errors.append("三語目錄連結不存在: " + target)
                checked_links += 1
    discover = set()
    # 只查版本控制候選檔案，排除依賴與本機證據資料夾。
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root, check=True, capture_output=True).stdout
    for name in tracked.decode().split("\0"):
        if name.endswith(".md") and not name.startswith("i18n/"):
            discover.add(name)
    if discover != sources:
        errors.append("原文覆蓋不一致: " + repr(sorted(discover ^ sources)))
    for d in documents:
        source_path = root / d["source"]
        if not source_path.is_file():
            errors.append(d["source"] + ": 缺少原文")
            continue
        if digest(source_path) != d["source_sha256"]:
            errors.append(d["source"] + ": 原文摘要變更")
        src = source_path.read_text()
        for lang in LANGUAGES:
            path = root / d[lang]
            label = d[lang]
            if not path.is_file():
                errors.append(label + ": 缺少譯文")
                continue
            text = path.read_text()
            if not raw and digest(path) != d.get(lang + "_sha256"):
                errors.append(label + ": 譯文摘要變更")
            expected = src if raw else rewrite_links(d["source"], src, lang, sources)
            clean = body(text)
            errors.extend(label + ": " + issue for issue in invariants(expected, clean))
            expected_links = [m[2] for m in LINK.finditer(without_code(expected))]
            actual_links = [m[2] for m in LINK.finditer(without_code(clean))]
            if expected_links != actual_links:
                errors.append(label + ": 連結目標不同")
            if not raw and ANCHOR.findall(text) != source_anchors(src):
                errors.append(label + ": 原文標題錨點不同")
            if "@@MISSING" in text or "@@CODE" in text:
                errors.append(label + ": 未完成翻譯佔位符")
            if not raw:
                for target in [m[2] for m in LINK.finditer(without_code(text))]:
                    value = target.strip("<>")
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value):
                        continue
                    location, _, fragment = value.partition("#")
                    location = re.sub(r":\d+$", "", unquote(location))
                    destination = (path.parent / location).resolve() if location else path
                    checked_links += 1
                    try:
                        relative = destination.relative_to(root)
                    except ValueError:
                        external_evidence.add(str(destination))
                        continue
                    if relative.parts and relative.parts[0] == ".artifacts":
                        external_evidence.add(str(relative))
                        continue
                    if not destination.exists():
                        errors.append(label + ": 連結目標不存在: " + target)
                    elif fragment and destination.suffix == ".md" and str(relative).startswith("i18n/"):
                        target_text = destination.read_text()
                        available = set(ANCHOR.findall(target_text)) | set(source_anchors(body(target_text)))
                        if unquote(fragment) not in available:
                            errors.append(label + ": 章節錨點不存在: " + target)
    return {"passed": not errors, "source_documents": len(documents), "translations": len(documents) * len(LANGUAGES),
            "checked_local_links": checked_links, "local_evidence_targets": len(external_evidence), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "i18n/manifest.json")
    parser.add_argument("--raw", action="store_true", help="連結重寫前的原始譯文核對")
    args = parser.parse_args()
    report = check(ROOT, json.loads(args.manifest.read_text()), args.raw)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
