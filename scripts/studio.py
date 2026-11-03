"""Start the portable backend from a source checkout on Windows, macOS or Linux."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'control'))
from ailab_studio.__main__ import main

if __name__ == '__main__':
    if '--data-dir' not in sys.argv: sys.argv += ['--data-dir', str(ROOT / '.artifacts' / 'studio')]
    if '--token-file' not in sys.argv: sys.argv += ['--token-file', str(ROOT / '.artifacts' / 'dev' / 'control-connection.json')]
    if '--environment-dir' not in sys.argv: sys.argv += ['--environment-dir', str(ROOT / 'environment')]
    main()
