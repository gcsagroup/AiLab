"""按已固定的公开来源和 SHA 获取构建依赖，支持本地完整缓存。"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen

HOSTS = {"files.pythonhosted.org", "download.pytorch.org", "download-r2.pytorch.org"}


def file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def fetch(manifest, destination):
    data = json.loads(manifest.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("files"), list):
        raise ValueError("依赖来源清单格式不符")
    destination.mkdir(parents=True, exist_ok=True)
    names = set()
    downloaded = 0
    for item in data["files"]:
        name, expected, source = item["filename"], item["sha256"], item["source"]
        url = urlparse(source)
        if not isinstance(name, str) or Path(name).name != name or name in names or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("依赖文件名或摘要无效")
        if url.scheme != "https" or url.hostname not in HOSTS or url.username or url.password or url.port not in {None, 443}:
            raise ValueError("依赖来源不是已声明的官方 HTTPS 下载地址")
        names.add(name)
        target = destination / name
        if target.exists():
            if target.is_symlink() or file_hash(target) != expected:
                raise ValueError("已有依赖文件与冻结 SHA 不符：" + name)
            continue
        temporary = None
        try:
            with urlopen(source, timeout=60) as response, tempfile.NamedTemporaryFile(dir=destination, delete=False) as stream:
                temporary = Path(stream.name)
                final = urlparse(response.url)
                if final.scheme != "https" or final.hostname not in HOSTS:
                    raise ValueError("依赖下载跳转到未声明来源")
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 1024 ** 3:
                        raise ValueError("单个运行时依赖超过 1 GiB 限制")
                    stream.write(chunk)
            if file_hash(temporary) != expected:
                raise ValueError("下载依赖 SHA 与冻结来源不符：" + name)
            temporary.replace(target)
            temporary = None
            downloaded += 1
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    print(json.dumps({"profile": data.get("profile"), "verified_files": len(names), "downloaded_files": downloaded, "destination": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    fetch(args.manifest.resolve(), args.destination.resolve())
