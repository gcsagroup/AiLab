#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$TASK_ROOT/scripts/desktop/toolchain.sh"
cd "$TASK_ROOT"
TASK_VERSION_PYTHON="$TASK_ROOT/services/control/.venv/bin/python"
TASK_APP="$TASK_ROOT/apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app"
mkdir -p "$TASK_ROOT/.artifacts/desktop"
TASK_BUILD_LOCK="$TASK_ROOT/.artifacts/desktop/candidate-build.lock"
if ! mkdir "$TASK_BUILD_LOCK"; then
  echo "已有完整候选构建占用固定输出路径；请先确认并结束该构建。" >&2
  exit 1
fi
TASK_VERSION_STARTED=0
TASK_VERSION_FINISHED=0
function finish_candidate() {
  TASK_BUILD_EXIT=$?
  if [[ "$TASK_VERSION_STARTED" == 1 && "$TASK_VERSION_FINISHED" == 0 ]]; then
    "$TASK_VERSION_PYTHON" "$TASK_ROOT/scripts/desktop/app_version.py" finish --status failed || true
  fi
  rmdir "$TASK_BUILD_LOCK"
  exit "$TASK_BUILD_EXIT"
}
trap finish_candidate EXIT
"$TASK_VERSION_PYTHON" "$TASK_ROOT/scripts/desktop/app_version.py" begin
TASK_VERSION_STARTED=1
TASK_SOURCE="$(mktemp -d "$TASK_ROOT/.artifacts/desktop/source-XXXXXXXX")"
"$TASK_ROOT/scripts/desktop/package_control.sh" "$TASK_SOURCE"
"$TASK_ROOT/.artifacts/desktop/package-venv/bin/python" "$TASK_ROOT/scripts/desktop/stage_control.py" "$TASK_ROOT" "$TASK_SOURCE" --verify-application
"$TASK_ROOT/scripts/desktop/package_mlx.sh" "$TASK_SOURCE"
"$TASK_ROOT/.artifacts/desktop/package-venv/bin/python" "$TASK_ROOT/scripts/desktop/package_media_tools.py" "$TASK_ROOT"
"$TASK_ROOT/scripts/desktop/package_media.sh" "$TASK_SOURCE" diffusers
"$TASK_ROOT/scripts/desktop/package_media.sh" "$TASK_SOURCE" kokoro
npm run build
cd "$TASK_ROOT/apps/desktop"
"$TASK_ROOT/node_modules/.bin/tauri" build --bundles app "$@"
"$TASK_ROOT/.artifacts/desktop/package-venv/bin/python" "$TASK_ROOT/scripts/desktop/seal_runtime.py" "$TASK_APP" "$TASK_ROOT/apps/desktop/src-tauri/Entitlements.plist"
codesign --verify --deep --strict --verbose=2 "$TASK_APP"
codesign -dvvv "$TASK_APP" 2>&1
shasum -a 256 "$TASK_APP/Contents/MacOS/gcsa-ailab"
"$TASK_ROOT/.artifacts/desktop/package-venv/bin/python" "$TASK_ROOT/scripts/desktop/verify_bundle.py" "$TASK_APP" --output "$TASK_ROOT/.artifacts/desktop/bundle-verification.json"
"$TASK_ROOT/.artifacts/desktop/package-venv/bin/python" "$TASK_ROOT/scripts/desktop/stage_control.py" "$TASK_ROOT" "$TASK_SOURCE" --verify-application
"$TASK_VERSION_PYTHON" "$TASK_ROOT/scripts/desktop/app_version.py" check --app "$TASK_APP"
"$TASK_VERSION_PYTHON" "$TASK_ROOT/scripts/desktop/app_version.py" finish --status succeeded
TASK_VERSION_FINISHED=1
