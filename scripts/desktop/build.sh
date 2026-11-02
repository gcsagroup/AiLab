#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_PYTHON="${AILAB_CONTROL_PYTHON:-$TASK_ROOT/.venv/bin/python}"
if [[ ! -x "$TASK_PYTHON" ]]; then
  echo "Install the lightweight control/build requirements in .venv, or set AILAB_CONTROL_PYTHON." >&2
  exit 1
fi
exec "$TASK_PYTHON" "$TASK_ROOT/scripts/desktop/build_studio.py" "$@"
