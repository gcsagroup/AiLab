"""准备固定官方 Kokoro 文件；下载与推理分开，已有文件按完整摘要复核。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.request

REPOSITORY = "hexgrad/Kokoro-82M"
REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
FILES = {
    "config.json": {"size": 2351, "git_blob_sha1": "14a726edd3718279eac426630879ff743955b16a"},
    "kokoro-v1_0.pth": {"size": 327212226, "sha256": "496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4"},
    "voices/zf_xiaobei.pt": {"size": 523435, "sha256": "9b76be63dab4f4f96962030acc0126a9aee9728608fbbe115e2b58a2bd504df6"},
}


def file_hash(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            checksum.update(block)
    return checksum.hexdigest()


def verify(path, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected["size"]:
        raise ValueError("文件大小、类型或路径不符合固定官方清单：" + str(path))
    sha256 = file_hash(path)
    if expected.get("sha256") and sha256 != expected["sha256"]:
        raise ValueError("文件 SHA256 不符合固定官方清单：" + str(path))
    if expected.get("git_blob_sha1"):
        blob = b"blob " + str(path.stat().st_size).encode() + b"\0" + path.read_bytes()
        if hashlib.sha1(blob).hexdigest() != expected["git_blob_sha1"]:
            raise ValueError("配置与官方固定 Git 对象身份不符")
    return sha256


def download(directory, name, expected):
    destination = directory / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return verify(destination, expected)
    partial = destination.with_name(destination.name + ".partial")
    url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
    if expected["size"] > 32 * 1024 * 1024:
        parallel_download(url, partial, expected["size"])
    for attempt in range(6):
        position = partial.stat().st_size if partial.exists() else 0
        if position == expected["size"]:
            break
        if position > expected["size"]:
            raise ValueError("部分下载超过预定大小，保留文件供检查")
        request = urllib.request.Request(url, headers={"User-Agent": "GCSA-AiLab-local-preparation/0.1", **({"Range": f"bytes={position}-"} if position else {})})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                if position and response.status != 206:
                    position = 0
                with partial.open("ab" if position else "wb") as stream:
                    while block := response.read(1024 * 1024):
                        position += len(block)
                        if position > expected["size"]:
                            raise ValueError("下载内容超过官方固定文件大小")
                        stream.write(block)
                    stream.flush()
                    os.fsync(stream.fileno())
            if position == expected["size"]:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if attempt == 5:
                raise
            time.sleep(1)
    checksum = verify(partial, expected)
    partial.chmod(0o400)
    os.rename(partial, destination)
    return checksum


def parallel_download(url, partial, size, chunk_size=8 * 1024 * 1024):
    """官方服务器支持范围请求时并行取固定分片，总大小始终受清单约束。"""
    if partial.exists() and partial.stat().st_size == size:
        return
    parts = partial.with_name(partial.name + ".parts")
    parts.mkdir(exist_ok=True)
    plan_path = parts / "ranges.json"
    if plan_path.exists():
        ranges = json.loads(plan_path.read_text())
    else:
        start = partial.stat().st_size if partial.exists() else 0
        ranges = [{"start": 0, "end": start - 1}] if start else []
        if start:
            os.rename(partial, parts / "0")
        for position in range(start, size, chunk_size):
            ranges.append({"start": position, "end": min(size, position + chunk_size) - 1})
        plan_path.write_text(json.dumps(ranges))

    def one(index):
        part, interval = parts / str(index), ranges[index]
        expected = interval["end"] - interval["start"] + 1
        for attempt in range(6):
            completed = part.stat().st_size if part.exists() else 0
            if completed == expected:
                return
            if completed > expected:
                raise ValueError("分片超过预定范围")
            start = interval["start"] + completed
            request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{interval['end']}"})
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{interval['end']}/{size}":
                        raise ValueError("官方服务器未按请求返回固定分片，未接受其内容")
                    with part.open("ab") as stream:
                        while block := response.read(1024 * 1024):
                            completed += len(block)
                            if completed > expected:
                                raise ValueError("分片下载超过固定大小")
                            stream.write(block)
                        stream.flush()
                        os.fsync(stream.fileno())
                if completed == expected:
                    return
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                if attempt == 5:
                    raise
                time.sleep(1)
        raise ValueError("分片未完成")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(one, range(len(ranges))))
    with partial.open("wb") as output:
        for index in range(len(ranges)):
            with (parts / str(index)).open("rb") as source:
                shutil.copyfileobj(source, output, 4 * 1024 * 1024)
        output.flush()
        os.fsync(output.fileno())
    # 只清理由本下载器生成且已经完整合并的分片；最终发布仍需全文件摘要。
    shutil.rmtree(parts)


def prepare(directory):
    directory = directory.absolute()
    if any(path.is_symlink() for path in [directory, *directory.parents]):
        raise ValueError("准备目录不能经过符号链接")
    directory.mkdir(parents=True, exist_ok=True)
    if any(path.is_symlink() for path in directory.rglob("*")):
        raise ValueError("准备目录中的已有文件不能经过符号链接")
    files = []
    for name, expected in FILES.items():
        print(json.dumps({"phase": "download", "file": name, "bytes": expected["size"]}, ensure_ascii=False), flush=True)
        checksum = download(directory, name, expected)
        files.append({"path": name, "size": expected["size"], "sha256": checksum})
    manifest = {"schema_version": "kokoro-zh-v1", "repository": REPOSITORY, "revision": REVISION, "license": "Apache-2.0", "license_source": f"https://huggingface.co/{REPOSITORY}/blob/{REVISION}/README.md", "source_api": f"https://huggingface.co/api/models/{REPOSITORY}/revision/{REVISION}?blobs=true", "files": files, "total_bytes": sum(item["size"] for item in files), "load_policy": "fixed_official_files_torch_weights_only_cpu", "voice": "zf_xiaobei", "sample_rate": 24000}
    target = directory / "manifest.json"
    if target.exists():
        if json.loads(target.read_text()) != manifest:
            raise ValueError("已准备清单不同，未覆盖")
    else:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        target.chmod(0o400)
    print(json.dumps({"phase": "prepared", "manifest": str(target), "total_bytes": manifest["total_bytes"]}, ensure_ascii=False), flush=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="下载固定官方 Kokoro 模型与一个中文音色")
    parser.add_argument("--model-dir", required=True, type=Path)
    args = parser.parse_args()
    prepare(args.model_dir)
