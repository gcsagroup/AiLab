"""Package only the portable control service; invoke with the control virtualenv."""
from pathlib import Path
import shutil
import subprocess
import sys
import uv

ROOT = Path(__file__).resolve().parents[2]
artifacts = ROOT / '.artifacts' / 'studio-build'
source = ROOT / 'services' / 'control' / 'ailab_studio'
command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--name', 'ailab-control',
    '--distpath', str(artifacts / 'dist'), '--workpath', str(artifacts / 'build'), '--specpath', str(artifacts),
    '--paths', str(ROOT / 'services' / 'control'), '--collect-all', 'uv', '--collect-submodules', 'uvicorn',
    '--hidden-import', 'ailab_studio.workers.supervisor',
    '--add-binary', f'{uv.find_uv_bin()}:bin',
    '--add-data', f'{source / "workers"}:ailab_studio/workers', '--add-data', f'{source / "templates"}:ailab_studio/templates',
    str(ROOT / 'scripts' / 'desktop' / 'studio_entry.py')]
if __name__ == '__main__':
    artifacts.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, cwd=ROOT, check=True)
    target = ROOT / 'apps' / 'desktop' / 'src-tauri' / 'resources' / 'control'
    if target.exists():
        # Preserve any old generated runtime instead of silently mixing it with the new bundle.
        previous = artifacts / ('previous-control-' + str(__import__('time').time_ns()))
        assert target.resolve().is_relative_to(ROOT.resolve()) and previous.resolve().is_relative_to(ROOT.resolve())
        shutil.move(str(target), str(previous))
    shutil.copytree(artifacts / 'dist' / 'ailab-control', target)
    print('Portable control runtime packaged:', target)
