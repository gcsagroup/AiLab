"""固定官方 Tiny-SD 源版本；受限转换，绝不回退到任意 pickle 执行。"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

REPO = "segmind/tiny-sd"
REVISION = "cad0bd7495fa6c4bcca01b19a723dc91627fe84f"
WEIGHTS = {
    "text_encoder/pytorch_model.bin": ("f99d8915149c782551f7d14aae5ca0b6e76a6e94d30e5dc86a349b228fbf92ad", "text_encoder/model.safetensors"),
    "unet/diffusion_pytorch_model.bin": ("c9b63e57cb1479c946c73bf5484bc1a823dbe565158ea0ee40015a18844d9f29", "unet/diffusion_pytorch_model.safetensors"),
    "vae/diffusion_pytorch_model.bin": ("279228e5296858f5d330db506ff6a51fdcad0d69f87634b5e9133406110af9bf", "vae/diffusion_pytorch_model.safetensors"),
}
FILES = ["README.md", "model_index.json", "scheduler/scheduler_config.json",
         "text_encoder/config.json", "tokenizer/merges.txt", "tokenizer/special_tokens_map.json",
         "tokenizer/tokenizer_config.json", "tokenizer/vocab.json", "unet/config.json", "vae/config.json", *WEIGHTS]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(root, api_path):
    root = Path(root).resolve()
    api = json.loads(Path(api_path).read_text())
    if api["id"] != REPO or api["sha"] != REVISION or api["gated"] is not False:
        raise ValueError("官方元信息与冻结源版本不一致")
    entries = {item["rfilename"]: item for item in api["siblings"]}
    total = sum(entries[name]["size"] for name in FILES)
    if total > 1_100_000_000:
        raise ValueError("模型下载超过本组合预算")
    records = []
    for name in FILES:
        item = entries[name]
        target = root / "official" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
            if name in WEIGHTS:
                from download_parts import download_parts
                download_parts(url, target, item["size"], WEIGHTS[name][0], workers=8)
            else:
                temporary = target.with_name(target.name + ".partial")
                subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2",
                                "--connect-timeout", "30", "--max-time", "60", url, "--output", str(temporary)], check=True)
                temporary.replace(target)
        content_sha = sha256(target)
        if target.stat().st_size != item["size"]:
            raise ValueError(f"文件大小不符：{name}")
        if name in WEIGHTS:
            expected = WEIGHTS[name][0]
            if content_sha != expected or item["lfs"]["sha256"] != expected:
                raise ValueError(f"官方权重摘要不符：{name}")
        else:
            data = target.read_bytes()
            blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            if blob != item["blobId"]:
                raise ValueError(f"元数据 Git 对象摘要不符：{name}")
        records.append({"path": name, "bytes": item["size"], "sha256": content_sha})
        print(json.dumps({"下载并核验": name, "bytes": item["size"]}, ensure_ascii=False), flush=True)
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if existing.get("repo") != REPO or existing.get("revision") != REVISION or existing.get("source_files") != records:
            raise ValueError("已有转换清单与官方基座不一致，不覆盖旧模型")
        expected_paths = {WEIGHTS[name][1] if name in WEIGHTS else name for name in FILES}
        if {item["path"] for item in existing.get("converted_files", [])} != expected_paths:
            raise ValueError("已有转换文件集合不完整，不覆盖旧模型")
        for item in existing["converted_files"]:
            path = root / "safetensors" / item["path"]
            if not path.is_file() or sha256(path) != item["sha256"]:
                raise ValueError("已有转换文件摘要不符，不覆盖旧模型")
        print(json.dumps({"复用已核验模型": str(manifest_path), "download_bytes": 0}, ensure_ascii=False), flush=True)
        return
    # 转换严格发生在 CPU；模型仓库不提供可执行代码，不使用远程代码信任选项。
    import torch
    from safetensors.torch import save_file
    converted = []
    for name in FILES:
        source = root / "official" / name
        destination = root / "safetensors" / (WEIGHTS[name][1] if name in WEIGHTS else name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if name in WEIGHTS:
            state = torch.load(source, map_location="cpu", weights_only=True)
            if not isinstance(state, dict) or not state or not all(isinstance(k, str) and isinstance(v, torch.Tensor) for k, v in state.items()):
                raise ValueError("受限加载结果不是纯张量 state_dict")
            save_file({k: v.contiguous() for k, v in state.items()}, destination, metadata={"format": "pt", "source_revision": REVISION})
            del state
        else:
            destination.write_bytes(source.read_bytes())
        converted.append({"path": str(destination.relative_to(root / "safetensors")), "bytes": destination.stat().st_size, "sha256": sha256(destination)})
    manifest = {"repo": REPO, "revision": REVISION, "gated": False, "license": "creativeml-openrail-m",
                "download_bytes": total, "source_files": records, "converted_files": converted,
                "loader": "torch.load(weights_only=True, map_location='cpu')", "runtime_format": "safetensors"}
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"完成": str(root / "manifest.json"), "download_bytes": total}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--api", required=True)
    args = parser.parse_args()
    prepare(args.root, args.api)
