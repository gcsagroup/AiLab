#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_ARTIFACTS="$TASK_ROOT/.artifacts/desktop"
TASK_MLX_VENV="$TASK_ARTIFACTS/mlx-package-venv"
if [[ ! -x "$TASK_MLX_VENV/bin/python" ]]; then
  "$TASK_ROOT/adapters/mlx_text/.venv/bin/python" -m venv "$TASK_MLX_VENV"
fi
"$TASK_MLX_VENV/bin/python" -m pip install --requirement "$TASK_ROOT/adapters/mlx_text/requirements.lock.txt" --requirement "$TASK_ROOT/scripts/desktop/packaging.lock.txt"
TASK_SOURCE="${1:-$(mktemp -d "$TASK_ARTIFACTS/mlx-source-XXXXXXXX")}"
if [[ ! -f "$TASK_SOURCE/build-manifest.json" ]]; then
  "$TASK_MLX_VENV/bin/python" "$TASK_ROOT/scripts/desktop/stage_control.py" "$TASK_ROOT" "$TASK_SOURCE"
fi
"$TASK_MLX_VENV/bin/python" "$TASK_ROOT/scripts/desktop/package_mlx.py" "$TASK_ROOT" "$TASK_SOURCE"
