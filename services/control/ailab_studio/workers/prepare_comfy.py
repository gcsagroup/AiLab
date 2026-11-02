"""Install a pinned native engine source; never touch model weights."""
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = 'v0.43.0'


def prepare(root, cache):
    root, cache = Path(root), Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f'comfyui-{VERSION}.zip'
    if not archive.is_file():
        partial = archive.with_suffix('.partial')
        urllib.request.urlretrieve(f'https://api.github.com/repos/Comfy-Org/ComfyUI/zipball/{VERSION}', partial)
        partial.replace(archive)
    destination = root / 'comfyui'
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            relative = Path(*Path(item.filename).parts[1:])
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError('Invalid source archive path')
            if item.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(item) as incoming, target.open('wb') as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
    requirements = (destination / 'requirements.txt').read_text(encoding='utf-8')
    # No web frontend, templates or documentation bundle is needed by this worker.
    requirements = '\n'.join(line for line in requirements.splitlines() if not line.startswith(('comfyui-frontend-', 'comfyui-workflow-', 'comfyui-embedded-')))
    (root / 'requirements.comfy.txt').write_text(requirements, encoding='utf-8')
    (destination / 'AILAB_VERSION').write_text(VERSION, encoding='utf-8')


if __name__ == '__main__': prepare(*sys.argv[1:])
