#!/usr/bin/env python3
"""准备固定公开试验模型；默认下载到项目产物目录，不改用户模型缓存。"""

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
WEIGHTS_SHA256 = "fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe"
FILES = ["config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json", "model.safetensors", "vocab.json", "merges.txt", "README.md", "LICENSE"]


def main():
    parser = argparse.ArgumentParser(description="下载并核对固定官方 Qwen2.5-0.5B-Instruct")
    parser.add_argument("--model-dir", type=Path, default=ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
        from huggingface_hub import snapshot_download
        snapshot_download(REPO, revision=REVISION, local_dir=args.model_dir, allow_patterns=FILES, max_workers=2)
    manifest = []
    for name in FILES:
        path = args.model_dir / name
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        manifest.append({"path": name, "size": path.stat().st_size, "sha256": digest.hexdigest()})
    weights = next(item for item in manifest if item["path"] == "model.safetensors")
    if weights["sha256"] != WEIGHTS_SHA256 or weights["size"] != 988097824:
        raise ValueError("权重与固定官方 revision 的摘要或大小不一致")
    print(json.dumps({"repo_id": REPO, "revision": REVISION, "license": "Apache-2.0", "files": manifest, "verified": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
