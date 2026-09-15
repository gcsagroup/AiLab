"""官方大文件的有界 Range 下载；每段核验区间，完整摘要通过后才发布。"""

from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import subprocess
from pathlib import Path

from prepare_tiny_sd import sha256


def download_parts(url, destination, size, expected_sha256, workers=8, chunk_size=8 * 1024 * 1024):
    destination = Path(destination)
    if destination.is_file():
        if destination.stat().st_size != size or sha256(destination) != expected_sha256:
            raise ValueError("已有下载文件与固定摘要不一致")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = destination.with_name(destination.name + ".partial")
    prefix_size = prefix.stat().st_size if prefix.exists() else 0
    if prefix_size > size:
        raise ValueError("旧部分文件超过官方文件大小")
    parts = destination.with_name(destination.name + ".parts")
    parts.mkdir(exist_ok=True)
    ranges = [(offset, min(offset + chunk_size, size) - 1) for offset in range(prefix_size, size, chunk_size)]
    def fetch(interval, attempt=0):
        start, end = interval
        part = parts / f"{start:012d}-{end:012d}"
        if part.exists() and part.stat().st_size == end - start + 1:
            return part
        headers = part.with_suffix(".headers")
        temporary = part.with_suffix(".partial")
        received = temporary.stat().st_size if temporary.exists() else 0
        tail = part.with_suffix(".tail")
        # 进程被终止时也保留已落盘的响应前缀，不能依赖异常处理一定运行。
        interrupted_range = f"content-range: bytes {start + received}-{end}/{size}"
        if tail.exists() and headers.exists() and interrupted_range in headers.read_text().lower() and tail.stat().st_size <= end - start + 1 - received:
            with temporary.open("ab") as output, tail.open("rb") as source:
                shutil.copyfileobj(source, output)
            tail.unlink()
            received = temporary.stat().st_size
        remaining = end - start + 1 - received
        if remaining < 0:
            raise ValueError("部分下载段超过请求区间")
        if remaining == 0:
            temporary.replace(part)
            return part
        if headers.exists():
            headers.unlink()
        response = subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--connect-timeout", "20",
                                   "--max-time", "240", "--max-filesize", str(remaining), "--range", f"{start + received}-{end}",
                                   "--dump-header", str(headers), url, "--output", str(tail)])
        expected_range = f"content-range: bytes {start + received}-{end}/{size}"
        if not headers.exists() or expected_range not in headers.read_text().lower() or not tail.exists() or tail.stat().st_size > remaining:
            if response.returncode and attempt < 2:
                return fetch(interval, attempt + 1)
            raise ValueError("官方 Range 响应与请求区间不一致")
        # 截断响应只补入已收到的连续前缀；下次从缺失位置继续，最终仍须完整 SHA256。
        with temporary.open("ab") as output, tail.open("rb") as source:
            shutil.copyfileobj(source, output)
        tail.unlink()
        if response.returncode and attempt < 2:
            return fetch(interval, attempt + 1)
        response.check_returncode()
        if temporary.stat().st_size != end - start + 1:
            raise ValueError("下载段尚未完整")
        temporary.replace(part)
        print(json.dumps({"分段完成": destination.name, "start": start, "end": end}, ensure_ascii=False), flush=True)
        return part
    with ThreadPoolExecutor(max_workers=workers) as executor:
        completed = list(executor.map(fetch, ranges))
    assembled = destination.with_name(destination.name + ".assembled")
    with assembled.open("wb") as output:
        for part in ([prefix] if prefix.exists() else []) + completed:
            with part.open("rb") as stream:
                shutil.copyfileobj(stream, output, 8 * 1024 * 1024)
    if assembled.stat().st_size != size or sha256(assembled) != expected_sha256:
        raise ValueError("完整官方文件摘要不符；保留部分文件供定位")
    assembled.replace(destination)
    # 只清理本函数创建的可重建分段缓存，原始模型与证据保留。
    if prefix.exists():
        prefix.unlink()
    shutil.rmtree(parts)
