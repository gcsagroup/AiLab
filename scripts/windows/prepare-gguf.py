"""Prepare pinned native GGUF backends and build AiLab's Windows worker (WSL MinGW)."""

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
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
LLAMA = "https://github.com/ggml-org/llama.cpp/releases/download/b12648/llama-b12648-bin-win-vulkan-x64.zip"
SD = "https://github.com/leejet/stable-diffusion.cpp/releases/download/master-1106-532d2c1/sd-master-532d2c1-bin-win-vulkan-x64.zip"
AUDIO = "https://github.com/0xShug0/audio.cpp/releases/download/v0.9.5/audio-v0.9.5-bin-windows-x64-cpu-portable.zip"
AUDIO_096 = "https://github.com/0xShug0/audio.cpp/releases/download/v0.9.6/audio-v0.9.6-bin-windows-x64-cpu-portable.zip"
SD_CONTROL = "https://github.com/leejet/stable-diffusion.cpp/releases/download/master-1117-0d71f96/sd-master-0d71f96-bin-win-cpu-x64.zip"
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
                    "llama-server.exe",
                    "llama-server-impl.dll",
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
                    "audiocpp_gguf.exe",
                    "LICENSE",
                    "kokoro_tts.json",
                    "mira_tts.json",
                    "zonos2.json",
                    "zonos3.json",
                    "minimax_h3.json",
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


def prepare_recipe_runtime(url, digest, folder, executable):
    archive = fetch(url, url.rsplit("/", 1)[1], digest)
    target = DEST / folder
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            name = Path(member.filename)
            if name.parent != Path(".") or not (name.name in (executable, "LICENSE") or name.suffix in (".dll", ".txt")):
                continue
            with bundle.open(member) as src, (target / name).open("wb") as dst:
                shutil.copyfileobj(src, dst)


def prepare_phonemizer():
    wheel = fetch(
        "https://files.pythonhosted.org/packages/9d/ed/a3d872fbad4f3a3f3db0e8c31768ab14e77cd77306de16b8b20b1e1df7ea/espeakng_loader-0.2.4-py3-none-win_amd64.whl",
        "espeakng_loader-0.2.4-win_amd64.whl",
        "41f1e08ac9deda2efd1ea9de0b81dab9f5ae3c4b24284f76533d0a7b1dd7abd7",
    )
    dest = DEST / "audio" / "espeak"
    dest.mkdir(parents=True, exist_ok=True)
    license_file = fetch(
        "https://raw.githubusercontent.com/espeak-ng/espeak-ng/1.52.0/COPYING",
        "espeak-ng-COPYING.txt",
        "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
    )
    shutil.copyfile(license_file, dest / "COPYING.txt")
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            name = member.filename.removeprefix("espeakng_loader/")
            if member.is_dir():
                continue
            if name != "espeak-ng.dll" and not name.startswith("espeak-ng-data/"):
                if ".dist-info/licenses/" not in name and not name.lower().endswith("/license"):
                    continue
                name = "licenses/" + Path(name).name
            target = dest / name
            if not target.resolve().is_relative_to(dest.resolve()):
                raise ValueError(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def prepare_sea_g2p():
    release = "https://github.com/pnnbao97/sea-g2p/releases/download/v0.10.0/"
    assets = [
        ("sea_g2p.bin", release + "sea_g2p.bin", "4346e690d0711ebc5231e7a42c5c88aaf6e40377e894b4617c018fd81c6f4096"),
        ("sea_g2p_rs.dll", release + "sea_g2p_rs-windows-x86_64.dll", "1daff10cf65304daa56d90814f4f6a54cf6269bf22a684b940a3d7c0bbea25c3"),
        ("LICENSE.sea-g2p.txt", "https://raw.githubusercontent.com/pnnbao97/sea-g2p/v0.10.0/LICENSE", "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"),
    ]
    for filename, url, checksum in assets:
        shutil.copyfile(fetch(url, filename, checksum), DEST / "audio" / filename)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["text", "diffusion", "audio"])
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    entries = [
        (
            "text",
            LLAMA,
            "35670c463d67d33b26058d2ac867346007a44ef19eaf0c0bfd6de08faa535b47",
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
    if args.only in (None, "audio"):
        prepare_recipe_runtime(AUDIO_096, "5d2e7fe24dbec0f8267db00ab2c6ccdd24799d916cb7beef3168eb66a53a4077",
                               "audio/v0.9.6", "audiocpp_cli.exe")
    if args.only in (None, "diffusion"):
        prepare_recipe_runtime(SD_CONTROL, "ba3e524523297902c9db1ec0e43e0bcbaf4067b4e053bd899b30c138ff1edda2",
                               "diffusion/0d71f96", "sd-cli.exe")
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
    if args.only in (None, "audio"):
        prepare_phonemizer()
        prepare_sea_g2p()
        for script in ("build-f5.py", "build-soxr.py"):
            command = ["python3", "scripts/windows/" + script]
            subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", *command] if os.name == "nt" else command,
                           cwd=ROOT, check=True)
    if args.only == "audio":
        return
    if args.only in (None, "diffusion"):
        prepare_image_sdk()
    if args.only in (None, "text"):
        prepare_text_sdk()
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
        "-I.artifacts/ggml-sdk/llama.cpp-b12648/include",
        "-I.artifacts/ggml-sdk/llama.cpp-b12648/tools/mtmd",
        "-I.artifacts/ggml-sdk/llama.cpp-b12648/ggml/include",
        "-I.artifacts/ggml-sdk/llama.cpp-b12648/vendor",
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
    build_plm = ["python3", "scripts/windows/build-plm.py"]
    subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", *build_plm] if os.name == "nt" else build_plm,
                   cwd=ROOT, check=True)


def prepare_text_sdk():
    revision = "44d50873b56b568c28ef2ad8d6445069feaa9fbd"
    files = json.loads(Path(__file__).with_name("llama-sdk.json").read_text())
    for name, checksum in files.items():
        relative = "llama.cpp-b12648/" + name
        (CACHE / relative).parent.mkdir(parents=True, exist_ok=True)
        source = fetch(
            f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{revision}/{name}",
            relative,
            checksum,
        )
        if name == "LICENSE":
            shutil.copyfile(source, DEST / "text" / "LICENSE.llama.cpp.txt")

    # Every name must have exactly the role provided by the matching native source.
    src = CACHE / "llama.cpp-b12648" / "src"
    table = (
        (src / "llama-arch.cpp")
        .read_text(encoding="utf-8")
        .split("LLM_ARCH_NAMES = {", 1)[1]
        .split("};", 1)[0]
    )
    mapping = (
        (src / "llama-model.cpp")
        .read_text(encoding="utf-8")
        .split("static llama_model * llama_model_mapping", 1)[1]
        .split("default:", 1)[0]
    )
    names = dict(re.findall(r'\{\s*(LLM_ARCH_\w+),\s*"([^"]+)"', table))
    constructors = set(re.findall(r"case (LLM_ARCH_\w+):", mapping))
    catalog = json.loads(
        (ROOT / "apps/windows-ui/hf/llama-architectures.json").read_text()
    )
    expected = {
        name for enum, name in names.items() if enum in constructors and name != "clip"
    }
    missing = {
        name
        for enum, name in names.items()
        if enum not in constructors and name != "(unknown)"
    }
    if (
        catalog["revision"] != revision
        or set(catalog["models"]) != expected
        or catalog["projectors"] != ["clip"]
        or set(catalog["no_constructor"]) != missing
    ):
        raise ValueError("llama.cpp architecture registry and packaged routes disagree")


def prepare_image_sdk():
    archive = fetch(
        SOURCE,
        "llama.tar.gz",
        "e06ba4fa263e30fdb9f0e65f00a8965202ddaa0c51f548a67e1f9b2164d04efc",
    )
    with tarfile.open(archive) as tar:
        for member in tar:
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


if __name__ == "__main__":
    main()
