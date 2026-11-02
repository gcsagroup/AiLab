"""Validate the current Studio documentation and checked-in screenshot links."""
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

DOCUMENTS = ('README.md', 'CHANGELOG.md', 'docs/README.md', 'docs/USER_GUIDE.md')


def check(root):
    root = Path(root).resolve()
    errors = []
    for name in DOCUMENTS:
        file = root / name
        if not file.is_file():
            errors.append(f'Missing document: {name}')
            continue
        body = file.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)', body):
            url = urlsplit(target)
            if url.scheme: continue
            if not url.path: continue
            dest = (file.parent / unquote(url.path)).resolve()
            if not dest.is_relative_to(root):
                errors.append(f'Link escapes repository: {name}: {target}')
            elif dest.is_relative_to(root / 'backup'):
                errors.append(f'Public document links local backup: {name}: {target}')
            elif not dest.is_file():
                errors.append(f'Missing link target: {name}: {target}')
    return errors


if __name__ == '__main__':
    problems = check(Path(__file__).resolve().parents[1])
    print(json.dumps({'passed': not problems, 'documents': len(DOCUMENTS), 'errors': problems}, ensure_ascii=False, indent=2))
    raise SystemExit(bool(problems))
