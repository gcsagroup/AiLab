#!/bin/bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK_ARTIFACTS="$TASK_ROOT/.artifacts/desktop"
TASK_PACKAGE_VENV="$TASK_ARTIFACTS/package-venv"
TASK_SIGN_IDENTITY="Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)"
mkdir -p "$TASK_ARTIFACTS"
if [[ ! -x "$TASK_PACKAGE_VENV/bin/python" ]]; then
  "$TASK_ROOT/services/control/.venv/bin/python" -m venv "$TASK_PACKAGE_VENV"
fi
"$TASK_PACKAGE_VENV/bin/python" -m pip install --requirement "$TASK_ROOT/scripts/desktop/packaging.lock.txt"
# 固定本次依赖中的 CA 字节；构建后必须仍是同一份，不回退系统证书库。
TASK_CA_SHA256="$("$TASK_PACKAGE_VENV/bin/python" -c 'import certifi, hashlib; from pathlib import Path; print(hashlib.sha256(Path(certifi.where()).read_bytes()).hexdigest())')"
TASK_SOURCE="${1:-$(mktemp -d "$TASK_ARTIFACTS/source-XXXXXXXX")}"
if [[ ! -f "$TASK_SOURCE/build-manifest.json" ]]; then
  "$TASK_PACKAGE_VENV/bin/python" "$TASK_ROOT/scripts/desktop/stage_control.py" "$TASK_ROOT" "$TASK_SOURCE"
fi
"$TASK_PACKAGE_VENV/bin/python" -m PyInstaller \
  --noconfirm --onedir --name ailab-control \
  --distpath "$TASK_ARTIFACTS/sidecar-dist" \
  --workpath "$TASK_ARTIFACTS/sidecar-build" \
  --specpath "$TASK_ARTIFACTS" \
  --paths "$TASK_SOURCE/control" \
  --paths "$TASK_SOURCE" \
  --hidden-import adapters.nvidia_text.adapter \
  --add-data "$TASK_SOURCE/adapters:adapters" \
  --add-data "$TASK_SOURCE/workers:workers" \
  --exclude-module torch --exclude-module transformers --exclude-module peft \
  --exclude-module accelerate --exclude-module safetensors --exclude-module numpy \
  --exclude-module mlx --exclude-module mlx_lm \
  --collect-submodules uvicorn \
  --collect-data certifi \
  --codesign-identity "$TASK_SIGN_IDENTITY" \
  "$TASK_SOURCE/entry/control_entry.py"
"$TASK_PACKAGE_VENV/bin/python" - "$TASK_ARTIFACTS/sidecar-dist/ailab-control/_internal/certifi/cacert.pem" "$TASK_CA_SHA256" <<'PY'
import hashlib
from pathlib import Path
import sys

path = Path(sys.argv[1])
if hashlib.sha256(path.read_bytes()).hexdigest() != sys.argv[2]:
    raise RuntimeError("内置控制层 CA 与本次固定依赖字节不一致")
PY
TASK_RESOURCE="$TASK_ROOT/apps/desktop/src-tauri/resources/control"
mkdir -p "$TASK_RESOURCE"
# 此目录只保存本脚本生成的控制层资源，不含用户数据。
rsync -a --delete "$TASK_ARTIFACTS/sidecar-dist/ailab-control/" "$TASK_RESOURCE/"
cp "$TASK_SOURCE/build-manifest.json" "$TASK_RESOURCE/build-manifest.json"
mkdir -p "$TASK_ROOT/apps/desktop/src-tauri/resources/workers" "$TASK_ROOT/apps/desktop/src-tauri/resources/adapters" "$TASK_ROOT/apps/desktop/src-tauri/resources/services"
rsync -a --delete "$TASK_SOURCE/workers/" "$TASK_ROOT/apps/desktop/src-tauri/resources/workers/"
rsync -a --delete "$TASK_SOURCE/adapters/" "$TASK_ROOT/apps/desktop/src-tauri/resources/adapters/"
rsync -a --delete "$TASK_SOURCE/services/" "$TASK_ROOT/apps/desktop/src-tauri/resources/services/"
codesign --verify --strict "$TASK_RESOURCE/ailab-control"
"$TASK_RESOURCE/ailab-control" --help
