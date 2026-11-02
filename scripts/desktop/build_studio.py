"""Build the native desktop for the current OS, with only a lightweight control runtime."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control-only', action='store_true', help='Package the control service without building Tauri')
    args, tauri_args = parser.parse_known_args()
    if importlib.util.find_spec('PyInstaller') is None:
        parser.error('Install services/control/requirements.studio-build.txt in the control virtualenv first.')
    subprocess.run([sys.executable, str(ROOT / 'scripts/desktop/package_studio.py')], cwd=ROOT, check=True)
    if args.control_only:
        return
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not npm or not shutil.which('cargo'):
        parser.error('Node.js/npm and the Rust/Tauri build prerequisites are required on the build machine.')
    subprocess.run([npm, 'run', 'build'], cwd=ROOT, check=True)
    cli = ROOT / 'node_modules' / '@tauri-apps' / 'cli' / 'tauri.js'
    node = shutil.which('node')
    if not node:
        parser.error('Node.js is required.')
    subprocess.run([node, str(cli), 'build', *tauri_args], cwd=ROOT / 'apps/desktop', check=True)


if __name__ == '__main__':
    main()
