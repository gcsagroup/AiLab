"""Prepare pinned native GGUF backends and build AiLab's Windows worker (WSL MinGW)."""

import argparse
import concurrent.futures
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from urllib.request import urlopen, Request
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".artifacts" / "ggml-sdk"
DEST = ROOT / "apps" / "windows-ui" / "runtime"
LLAMA = "https://github.com/ggml-org/llama.cpp/releases/download/b11669/llama-b11669-bin-win-vulkan-x64.zip"
SD = "https://github.com/leejet/stable-diffusion.cpp/releases/download/master-1106-532d2c1/sd-master-532d2c1-bin-win-vulkan-x64.zip"
AUDIO = "https://github.com/0xShug0/audio.cpp/releases/download/v0.9.5/audio-v0.9.5-bin-windows-x64-cpu-portable.zip"
SOURCE = "https://codeload.github.com/ggml-org/llama.cpp/tar.gz/refs/tags/b11669"


def fetch(url, name, checksum):
    dest = CACHE / name
    if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != checksum:
        temp = dest.with_suffix(".partial")
        with (
            urlopen(
                Request(url, headers={"User-Agent": "AiLab-build"}), timeout=120
            ) as resp,
            temp.open("wb") as out,
        ):
            shutil.copyfileobj(resp, out)
        if hashlib.sha256(temp.read_bytes()).hexdigest() != checksum:
            raise RuntimeError("Checksum mismatch: " + name)
        os.replace(temp, dest)
    return dest


def backend(kind, url, sha):
    archive = fetch(url, url.rsplit("/", 1)[1], sha)
    dest = DEST / kind
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if info.is_dir():
                continue
            if kind == "text":
                take = name in (
                    "ggml.dll",
                    "ggml-base.dll",
                    "ggml-vulkan.dll",
                    "llama.dll",
                    "mtmd.dll",
                    "llama-common.dll",
                    "libomp.dll",
                ) or name.startswith(("ggml-cpu-", "LICENSE"))
            elif kind == "diffusion":
                take = (
                    name.endswith(".dll")
                    or name.startswith("LICENSE")
                    or name == "sd-cli.exe"
                )
            else:
                take = name.endswith(".dll") or name in (
                    "audiocpp_cli.exe",
                    "LICENSE",
                    "kokoro_tts.json",
                )
            if take:
                # Audio ships phonemizer dictionaries alongside the executable.
                target = dest / (info.filename if kind == "audio" else name)
                if not target.resolve().is_relative_to(dest.resolve()):
                    raise ValueError(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if (
                    target.is_file()
                    and target.stat().st_size == info.file_size
                    and zlib.crc32(target.read_bytes()) == info.CRC
                ):
                    continue
                with z.open(info) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)
    return kind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["text", "diffusion", "audio"])
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    entries = [
        (
            "text",
            LLAMA,
            "2c07574e7bde71321cb785282b20cc821e951132149eeceeea32ddebdbf0598e",
        ),
        (
            "diffusion",
            SD,
            "3e66222c87ca27074e1fd8ce79706eef17a8aaf39949906aa1bee7e060f22ecc",
        ),
        (
            "audio",
            AUDIO,
            "9f470c3b254205d044e91e84d609424f528734cd06b74968ab0e4868a30b839a",
        ),
    ]
    with concurrent.futures.ThreadPoolExecutor() as pool:
        list(
            pool.map(
                lambda entry: backend(*entry),
                [x for x in entries if args.only in (None, x[0])],
            )
        )
    if args.only in (None, "diffusion"):
        for url, name, digest in [
            (
                "https://raw.githubusercontent.com/leejet/stable-diffusion.cpp/532d2c1/LICENSE",
                "LICENSE.stable-diffusion.txt",
                "b53fa08f515cb5a6fff7b9fd8fcd0961a4b80df29d74372d25e1f9171aa042ee",
            ),
            (
                "https://raw.githubusercontent.com/FFmpeg/FFmpeg/n7.1/COPYING.GPLv3",
                "LICENSE.ffmpeg-GPLv3.txt",
                "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
            ),
        ]:
            shutil.copyfile(fetch(url, name, digest), DEST / "diffusion" / name)
        wheel = fetch(
            "https://files.pythonhosted.org/packages/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl",
            "imageio-ffmpeg.whl",
            "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a",
        )
        with zipfile.ZipFile(wheel) as z:
            exe = next(i for i in z.namelist() if i.lower().endswith(".exe"))
            (DEST / "diffusion" / "ffmpeg.exe").write_bytes(z.read(exe))
            for name in z.namelist():
                if "license" in name.lower() and not name.endswith("/"):
                    (DEST / "diffusion" / ("ffmpeg-" + Path(name).name)).write_bytes(
                        z.read(name)
                    )
    if args.only == "audio":
        return
    archive = fetch(
        SOURCE,
        "llama.tar.gz",
        "e06ba4fa263e30fdb9f0e65f00a8965202ddaa0c51f548a67e1f9b2164d04efc",
    )
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.name == "llama.cpp-b11669/LICENSE":
                if args.only in (None, "text"):
                    (DEST / "text" / "LICENSE.llama.cpp.txt").write_bytes(
                        tar.extractfile(member).read()
                    )
            if member.isfile() and member.name.startswith(
                (
                    "llama.cpp-b11669/include/",
                    "llama.cpp-b11669/ggml/include/",
                    "llama.cpp-b11669/vendor/nlohmann/",
                    "llama.cpp-b11669/tools/mtmd/mtmd.h",
                    "llama.cpp-b11669/tools/mtmd/mtmd-helper.h",
                )
            ):
                tar.extract(member, CACHE, filter="data")
    if args.only in (None, "diffusion"):
        base = "https://raw.githubusercontent.com/leejet/stable-diffusion.cpp/532d2c1/"
        fetch(
            base + "include/stable-diffusion.h",
            "stable-diffusion.h",
            "3b0d0f479905ee59afeeb6511cf3c0a7baefbe23b829d673f3ce507296b54743",
        )
        header = fetch(
            base + "thirdparty/stb_image_write.h",
            "stb_image_write.h",
            "683e15c6dfdc2d57b06b9e166ba27665328e0854a9c1130c2ba9958afaf2f8da",
        )
        license_text = header.read_text().split("ALTERNATIVE A - MIT License", 1)[-1]
        (DEST / "diffusion" / "LICENSE.stb.txt").write_text(
            "ALTERNATIVE A - MIT License" + license_text, encoding="utf-8"
        )
        image_cmd = [
            "x86_64-w64-mingw32-g++",
            "-std=c++17",
            "-O2",
            "-static",
            "-s",
            "-I.artifacts/ggml-sdk",
            "-I.artifacts/ggml-sdk/llama.cpp-b11669/vendor",
            "workers/gguf-image.cpp",
            "apps/windows-ui/runtime/diffusion/stable-diffusion.dll",
            "-o",
            "apps/windows-ui/runtime/diffusion/ailab-image.exe",
        ]
        subprocess.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--", *image_cmd]
            if os.name == "nt"
            else image_cmd,
            cwd=ROOT,
            check=True,
        )
    if args.only == "diffusion":
        return
    cmd = [
        "x86_64-w64-mingw32-g++",
        "-std=c++17",
        "-O2",
        "-static",
        "-s",
        "-I.artifacts/ggml-sdk/llama.cpp-b11669/include",
        "-I.artifacts/ggml-sdk/llama.cpp-b11669/tools/mtmd",
        "-I.artifacts/ggml-sdk/llama.cpp-b11669/ggml/include",
        "-I.artifacts/ggml-sdk/llama.cpp-b11669/vendor",
        "workers/gguf-trial.cpp",
        "apps/windows-ui/runtime/text/mtmd.dll",
        "apps/windows-ui/runtime/text/llama.dll",
        "apps/windows-ui/runtime/text/ggml.dll",
        "apps/windows-ui/runtime/text/ggml-base.dll",
        "-o",
        "apps/windows-ui/runtime/text/ailab-gguf.exe",
    ]
    subprocess.run(
        ["wsl.exe", "-d", "Ubuntu-24.04", "--", *cmd] if os.name == "nt" else cmd,
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
