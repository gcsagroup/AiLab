#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# App 开发与验收共用已构建的固定入口；网页热更新另用 npm run dev。
exec "$TASK_ROOT/scripts/desktop/run.sh" "$@"
