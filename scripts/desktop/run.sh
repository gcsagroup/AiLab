#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_APP="$TASK_ROOT/apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app"
"$TASK_ROOT/services/control/.venv/bin/python" "$TASK_ROOT/scripts/desktop/app_version.py" check --app "$TASK_APP"
exec /usr/bin/open "$TASK_APP" --args "$@"
