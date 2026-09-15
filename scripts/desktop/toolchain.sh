#!/bin/bash
set -euo pipefail

# 只为当前构建选择独立工具链，不更改系统 Homebrew 或用户默认配置。
if [[ -x "$HOME/.rustup/toolchains/1.95.0-aarch64-apple-darwin/bin/rustc" ]]; then
  export PATH="$HOME/.rustup/toolchains/1.95.0-aarch64-apple-darwin/bin:$PATH"
fi
rustc --version
cargo --version
