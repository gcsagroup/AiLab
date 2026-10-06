"""检查公开文档的语言覆盖、摘要、链接及发布范围，不依赖本地内部资料。"""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

LANGUAGES = {'zh-CN', 'zh-TW', 'en', 'ja', 'ko', 'fr', 'pt'}
KINDS = {'readme', 'guide', 'changelog'}


def check(root, tracked=None):
    root = Path(root).resolve()
    errors = []
    manifest = json.loads((root / 'i18n/manifest.json').read_text())
    if manifest.get('schema_version') != 2 or set(manifest.get('languages', [])) != LANGUAGES:
        errors.append('公开文档必须列出七种语言')
    documents = manifest['documents']
    pairs = [(item['language'], item['kind']) for item in documents]
    if len(pairs) != 21 or set(pairs) != {(lang, kind) for lang in LANGUAGES for kind in KINDS}:
        errors.append('每种语言必须各有项目介绍、操作手册及更新记录')
    allowed = {item['path'] for item in documents} | set(manifest['indexes'])
    if len(allowed) != 23:
        errors.append('公开文档路径重复或索引缺失')
    if tracked is None:
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    tracked = set(tracked)
    for path in tracked:
        if path.endswith('.md') and path not in allowed:
            errors.append(f'内部文档仍被跟踪：{path}')
        if path.startswith(('docs/', 'i18n/', 'prototype/')) and path not in allowed | {'i18n/manifest.json'}:
            errors.append(f'内部资料仍被跟踪：{path}')
    for path in sorted(allowed):
        file = root / path
        if path not in tracked or not file.is_file():
            errors.append(f'公开文档缺失或未跟踪：{path}')
            continue
        body = file.read_text()
        if re.search(r'/Users/|\.artifacts/|docs/implementation/|E\d{2,}\b', body):
            errors.append(f'公开文档含内部路径或验收编号：{path}')
        for target in re.findall(r'\]\(([^)]+)\)', body):
            url = urlsplit(target)
            if url.scheme:
                if url.scheme != 'https':
                    errors.append(f'非 HTTPS 链接：{path}: {target}')
                continue
            dest = (file.parent / unquote(url.path)).resolve()
            try:
                rel = dest.relative_to(root).as_posix()
            except ValueError:
                errors.append(f'链接超出仓库：{path}: {target}')
                continue
            if rel not in allowed or not dest.is_file():
                errors.append(f'链接不是公开文档：{path}: {target}')
    for item in documents:
        file = root / item['path']
        if file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() != item['sha256']:
            errors.append(f'文档摘要未同步：{item["path"]}')
    return errors


if __name__ == '__main__':
    problems = check(Path(__file__).resolve().parents[1])
    print(json.dumps({'passed': not problems, 'languages': 7, 'documents': 21, 'indexes': 2, 'errors': problems}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(problems))
