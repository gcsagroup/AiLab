"""只下载官方 SVD 的固定 fp16 文件集，保留许可与逐文件校验。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess
from pathlib import Path

from prepare_tiny_sd import sha256

REPO = "stabilityai/stable-video-diffusion-img2vid"
REVISION = "9cf024d5bfa8f56622af86c884f26a52f6676f2e"
WEIGHTS = {
    "image_encoder/model.fp16.safetensors": "ae616c24393dd1854372b0639e5541666f7521cbe219669255e865cb7f89466a",
    "unet/diffusion_pytorch_model.fp16.safetensors": "cb552818963e736506c6693ffc279d59df423d63aced38902ea4373ab1fd2932",
    "vae/diffusion_pytorch_model.fp16.safetensors": "af602cd0eb4ad6086ec94fbf1438dfb1be5ec9ac03fd0215640854e90d6463a3",
}
FILES = ["LICENSE.md", "README.md", "model_index.json", "feature_extractor/preprocessor_config.json",
         "image_encoder/config.json", "scheduler/scheduler_config.json", "unet/config.json", "vae/config.json", *WEIGHTS]


def prepare(root, api_path, download_workers=8):
    if not 1 <= download_workers <= 16:
        raise ValueError("每个大文件的下载并发必须在 1—16 内")
    root = Path(root).resolve()
    api = json.loads(Path(api_path).read_text())
    if (api["id"], api["sha"], api["gated"]) != (REPO, REVISION, False):
        raise ValueError("SVD 官方元数据与冻结源不符")
    entries = {item["rfilename"]: item for item in api["siblings"]}
    total = sum(entries[name]["size"] for name in FILES)
    if total > 4_520_000_000:
        raise ValueError("SVD 文件集超过预算")
    def fetch(name):
        item = entries[name]
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
            if name in WEIGHTS:
                from download_parts import download_parts
                download_parts(url, target, item["size"], WEIGHTS[name], workers=download_workers)
            else:
                temporary = target.with_name(target.name + ".partial")
                subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
                                "--connect-timeout", "30", "--max-time", "60", "--continue-at", "-", url, "--output", str(temporary)], check=True)
                temporary.replace(target)
        digest = sha256(target)
        if target.stat().st_size != item["size"]:
            raise ValueError(f"SVD 文件大小不符：{name}")
        if name in WEIGHTS:
            if digest != WEIGHTS[name] or digest != item["lfs"]["sha256"]:
                raise ValueError(f"SVD 官方权重摘要不符：{name}")
        else:
            data = target.read_bytes()
            if hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != item["blobId"]:
                raise ValueError(f"SVD 元数据摘要不符：{name}")
        print(json.dumps({"下载并核验": name, "bytes": item["size"]}, ensure_ascii=False), flush=True)
        return {"path": name, "bytes": item["size"], "sha256": digest}
    with ThreadPoolExecutor(max_workers=3) as executor:
        records = list(executor.map(fetch, FILES))
    manifest = {"repo": REPO, "revision": REVISION, "gated": False, "format": "safetensors", "variant": "fp16",
                "license": "Stable Video Diffusion Community License; 商业注册与收入条款须在发布前独立核验",
                "download_bytes": total, "files": records}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"完成": str(root / "manifest.json"), "download_bytes": total}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--api", required=True)
    parser.add_argument("--download-workers", type=int, default=8)
    args = parser.parse_args()
    prepare(args.root, args.api, args.download_workers)
