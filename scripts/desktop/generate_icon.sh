#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_ICONS="$TASK_ROOT/.artifacts/desktop/generated-icons"
mkdir -p "$TASK_ICONS"
swift "$TASK_ROOT/scripts/desktop/generate_icon.swift" "$TASK_ICONS/source.png"
"$TASK_ROOT/node_modules/.bin/tauri" icon "$TASK_ICONS/source.png" --output "$TASK_ICONS"
cp "$TASK_ICONS/icon.icns" "$TASK_ROOT/apps/desktop/src-tauri/icons/icon.icns"
cp "$TASK_ICONS/icon.png" "$TASK_ROOT/apps/desktop/src-tauri/icons/icon.png"
