#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_SOURCE="${1:?需指定本次固定源码目录}"
TASK_PROFILE="${2:?需指定 diffusers 或 kokoro}"
case "$TASK_PROFILE" in
  diffusers) TASK_BASE_PYTHON="${AILAB_DIFFUSERS_BUILD_PYTHON:-/opt/homebrew/opt/python@3.13/bin/python3.13}" ;;
  kokoro) TASK_BASE_PYTHON="${AILAB_KOKORO_BUILD_PYTHON:-/opt/homebrew/opt/python@3.10/bin/python3.10}" ;;
  *) echo "未知媒体 profile" >&2; exit 2 ;;
esac
TASK_ARTIFACTS="$TASK_ROOT/.artifacts/desktop"
TASK_ENV="$TASK_ARTIFACTS/$TASK_PROFILE-package-venv"
TASK_WHEELS="$TASK_ARTIFACTS/media-wheels/$TASK_PROFILE"
if [[ ! -x "$TASK_ENV/bin/python" ]]; then
  "$TASK_BASE_PYTHON" -m venv "$TASK_ENV"
fi
"$TASK_ENV/bin/python" "$TASK_ROOT/scripts/desktop/fetch_media_dependencies.py" "$TASK_SOURCE/entry/runtime-$TASK_PROFILE.sources.json" "$TASK_WHEELS"
"$TASK_ENV/bin/python" "$TASK_ROOT/scripts/desktop/fetch_media_dependencies.py" "$TASK_SOURCE/entry/media-packaging.sources.json" "$TASK_ARTIFACTS/media-wheels/build"
"$TASK_ENV/bin/python" - "$TASK_SOURCE/entry/runtime-$TASK_PROFILE.lock.txt" "$TASK_ARTIFACTS/$TASK_PROFILE-build-foundation.lock.txt" <<'PY'
from pathlib import Path
import sys
lines = [line for line in Path(sys.argv[1]).read_text().splitlines() if line.startswith(('setuptools==', 'wheel==', 'packaging=='))]
Path(sys.argv[2]).write_text('\n'.join(lines) + '\n')
PY
"$TASK_ENV/bin/python" -m pip install --no-index --no-deps --require-hashes --find-links "$TASK_WHEELS" --requirement "$TASK_ARTIFACTS/$TASK_PROFILE-build-foundation.lock.txt"
"$TASK_ENV/bin/python" -m pip install --no-index --no-deps --no-build-isolation --require-hashes --find-links "$TASK_WHEELS" --requirement "$TASK_SOURCE/entry/runtime-$TASK_PROFILE.lock.txt"
"$TASK_ENV/bin/python" -m pip install --no-index --no-deps --require-hashes --find-links "$TASK_ARTIFACTS/media-wheels/build" --requirement "$TASK_SOURCE/entry/media-packaging.lock.txt"
"$TASK_ENV/bin/python" -m pip check
"$TASK_ENV/bin/python" "$TASK_ROOT/scripts/desktop/package_media.py" "$TASK_ROOT" "$TASK_SOURCE" "$TASK_PROFILE"
