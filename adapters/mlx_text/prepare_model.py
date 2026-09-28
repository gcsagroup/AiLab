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

VARIANTS = {
    "0.5b": {"repo": REPO, "revision": REVISION, "files": FILES, "weights": {"model.safetensors": {"size": 988097824, "sha256": WEIGHTS_SHA256}}},
    "7b": {
        "repo": "Qwen/Qwen2.5-7B-Instruct",
        "revision": "a09a35458c702b33eeacc393d103063234e8bc28",
        "files": [
            "LICENSE",
            "README.md",
            "config.json",
            "generation_config.json",
            "merges.txt",
            "model-00001-of-00004.safetensors",
            "model-00002-of-00004.safetensors",
            "model-00003-of-00004.safetensors",
            "model-00004-of-00004.safetensors",
            "model.safetensors.index.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json"
        ],
        "weights": {
            "model-00001-of-00004.safetensors": {
                "size": 3945441440,
                "sha256": "a1333e6293854747c481288ea83b348226af178dd565c49b6f9495ba1966aba7"
            },
            "model-00002-of-00004.safetensors": {
                "size": 3864726352,
                "sha256": "f5d25a2772cb825164a2a2c0fb6d51a87e282abf21e4dd75bc5cfb3cd0ea6185"
            },
            "model-00003-of-00004.safetensors": {
                "size": 3864726424,
                "sha256": "8efdec4c1bc12317ae1a38dc42b595ce777738a64deea3fcb8a0a91381bcdfd5"
            },
            "model-00004-of-00004.safetensors": {
                "size": 3556377672,
                "sha256": "1a72d403cdf0c1ec3cb7f289f17b394a01e64394c2e9b3c0f94dbce3faf879bd"
            }
        }
    },
}


def main():
    parser = argparse.ArgumentParser(description="下载并核对固定官方 Qwen2.5 文本基座")
    parser.add_argument("--variant", choices=VARIANTS, default="0.5b")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    selected = VARIANTS[args.variant]
    if args.model_dir is None:
        args.model_dir = ROOT / ".artifacts/models" / selected["repo"].split("/")[-1]
    if not args.verify_only:
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
        from huggingface_hub import snapshot_download
        snapshot_download(selected["repo"], revision=selected["revision"], local_dir=args.model_dir, allow_patterns=selected["files"], max_workers=2)
    manifest = []
    for name in selected["files"]:
        path = args.model_dir / name
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        manifest.append({"path": name, "size": path.stat().st_size, "sha256": digest.hexdigest()})
    for name, expected in selected["weights"].items():
        weights = next(item for item in manifest if item["path"] == name)
        if weights["sha256"] != expected["sha256"] or weights["size"] != expected["size"]:
            raise ValueError("权重与固定官方 revision 的摘要或大小不一致：" + name)
    print(json.dumps({"repo_id": selected["repo"], "revision": selected["revision"], "license": "Apache-2.0", "files": manifest, "verified": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
