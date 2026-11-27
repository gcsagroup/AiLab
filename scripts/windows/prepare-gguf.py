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
import tempfile
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
AUDIO_VULKAN = AUDIO.replace("-cpu-portable", "-vulkan-portable")
AUDIO_096_VULKAN = AUDIO_096.replace("-cpu-portable", "-vulkan-portable")
SD_CONTROL_VULKAN = SD_CONTROL.replace("-cpu-x64", "-vulkan-x64")
SOURCE = "https://codeload.github.com/ggml-org/llama.cpp/tar.gz/refs/tags/b11669"


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(url, name, checksum):
    dest = CACHE / name
    if not dest.exists() or file_sha256(dest) != checksum:
        temp = dest.with_suffix(".partial")
        with (
            urlopen(
                Request(url, headers={"User-Agent": "AiLab-build"}), timeout=120
            ) as resp,
            temp.open("wb") as out,
        ):
            shutil.copyfileobj(resp, out)
        if file_sha256(temp) != checksum:
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


def build_text_worker(sdk, runtime):
    # Only the AiLab host adapter is built here. CUDA kernels come from the distribution.
    sdk = sdk.relative_to(ROOT).as_posix()
    runtime = runtime.relative_to(ROOT).as_posix()
    cmd = [
        "x86_64-w64-mingw32-g++", "-std=c++17", "-O2", "-static", "-s",
        f"-I{sdk}/include", f"-I{sdk}/tools/mtmd", f"-I{sdk}/ggml/include",
        "-I.artifacts/ggml-sdk/llama.cpp-b12648/vendor", "workers/gguf-trial.cpp",
        *[f"{runtime}/{dll}.dll" for dll in ("mtmd", "llama", "ggml", "ggml-base")],
        "-o", f"{runtime}/ailab-gguf.exe",
    ]
    subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", *cmd] if os.name == "nt" else cmd,
                   cwd=ROOT, check=True)


def install_runtime_file(src, target):
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
        partial = Path(temp.name)
    try:
        with partial.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)

def extract_cuda(url, digest, folder, include):
    archive = fetch(url, url.rsplit("/", 1)[1], digest)
    target = DEST / folder
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            name = Path(member.filename)
            if name.parent == Path(".") and not member.is_dir() and include(name):
                with bundle.open(member) as src:
                    install_runtime_file(src, target / name)

def text_cuda_file(name):
    return name.name.startswith(("LICENSE", "ggml-cpu-")) or name.name in {
        "ggml.dll", "ggml-base.dll", "ggml-cuda.dll", "llama.dll", "mtmd.dll", "libomp.dll",
        "llama-server.exe", "llama-server-impl.dll", "llama-common.dll"}

def prepare_native_text():
    tag = "b12649-mix-c7059d6"
    base = f"https://github.com/unslothai/llama.cpp/releases/download/{tag}/"
    folder = "text/native-kernels/cuda"
    extract_cuda(base + f"app-{tag}-windows-x64-cuda12-older.zip",
            "1bde79ab7182c27f9f7976847011ce7ef7dc9f0ea4ddede7c0ddf5360b070b7e", folder,
            lambda name: text_cuda_file(name) or name.name in {"BUILD_INFO.txt", "THIRD_PARTY_LICENSES.txt", "UNSLOTH_PREBUILT_INFO.json"})
    archive = f"llama.cpp-source-commit-189f431bf58f433d376d718c7788b1bf4467fa72.tar.gz"
    source = fetch(base + archive, archive, "26ff4fc470df2aa935a8e66b0584c0d32a843c0f6f6fad6860bc9cc6ca9ca857")
    prefix = f"llama.cpp-{tag}/"
    with tarfile.open(source) as tar:
        for member in tar:
            name = member.name.removeprefix(prefix)
            if member.isfile() and member.name.startswith(prefix) and (
                name == "LICENSE" or (name.endswith(".h") and name.startswith(("include/", "ggml/include/", "tools/mtmd/")))
            ):
                tar.extract(member, CACHE, filter="data")
    sdk = CACHE / prefix
    shutil.copy2(sdk / "LICENSE", DEST / folder / "LICENSE.llama.cpp.txt")
    build_text_worker(sdk, DEST / folder)


def prepare_cuda(kind):
    # Each engine uses its own upstream CUDA redistribution and GGML plugin.
    # Versioned recipes share only their engine's compatible NVIDIA libraries.
    def worker(source, folder):
        file = DEST / source
        with file.open("rb") as src:
            install_runtime_file(src, DEST / folder / file.name)

    def runtime_files(name):
        return name.suffix in (".dll", ".txt") or name.name.startswith("LICENSE")

    if kind in (None, "text"):
        cudart = LLAMA.rsplit("/", 1)[0] + "/cudart-llama-bin-win-cuda-12.4-x64.zip"
        extract_cuda(cudart, "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
                "text/cuda-runtime", runtime_files)
        extract_cuda(LLAMA.replace("vulkan", "cuda-12.4"), "26b82a04c99449d19641e3db392ef2c5a2977ad087bb64c8d74e538b490b9649",
                "text/cuda", text_cuda_file)
        prepare_native_text()
        for name in ("ailab-gguf.exe", "plm-worker.exe"):
            worker("text/" + name, "text/cuda")
    if kind in (None, "diffusion"):
        cudart = SD.rsplit("/", 1)[0] + "/cudart-sd-bin-win-cu12-x64.zip"
        extract_cuda(cudart, "fe20366827d357c00797eebb58244dddab7fd9a348d70090c3871004c320f38d",
                "diffusion/cuda-runtime", runtime_files)
        for url, digest, folder in [
            (SD.replace("vulkan", "cuda12"), "b087219145a382cc1b1e826318289e1f672b9bb6965977734ef0deb85fe2d03a", "diffusion/cuda"),
            (SD_CONTROL.replace("-cpu-", "-cuda12-"), "b2db431b50e5c5b87c25b6b52006627eae866193634112f68c57daf7c1c8cb0d", "diffusion/0d71f96/cuda"),
        ]:
            extract_cuda(url, digest, folder, lambda name: runtime_files(name) or name.name == "sd-cli.exe")
        worker("diffusion/ailab-image.exe", "diffusion/cuda")
    if kind in (None, "audio"):
        cudart = AUDIO_096.replace("-bin-windows-x64-cpu-portable", "-cudart-windows-x64-cuda12.4")
        extract_cuda(cudart, "283fbf6927021b8e73cd22e6c3c300c2d12adb66361bc1d392401e1ca2759297",
                "audio/cuda-runtime", runtime_files)
        for url, digest, folder in [
            (AUDIO, "81f38a0a62935bdf4b2605541a21d50223b2e12b661887031705dd8a369f844b", "audio/cuda"),
            (AUDIO_096, "ff7783e29b02e9006fa4304b9cdeffa030cd5a184998090f769f0a1d221b2698", "audio/v0.9.6/cuda"),
        ]:
            extract_cuda(url.replace("cpu-portable", "cuda12.4"), digest, folder,
                    lambda name: runtime_files(name) or name.name == "audiocpp_cli.exe")
            worker("audio/soxr.dll", folder)


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
        prepare_recipe_runtime(AUDIO_VULKAN, "6c304c9a1e0cfc18b2d3b208b03d40365fec71d094ee4da4f695b2d9e7de29e8",
                               "audio/vulkan", "audiocpp_cli.exe")
        prepare_recipe_runtime(AUDIO_096_VULKAN, "8cfbd5a3a3c655dbb752972e548424d761cbd598ad7ea0903b77dbba0f202c3e",
                               "audio/v0.9.6/vulkan", "audiocpp_cli.exe")
        prepare_recipe_runtime(AUDIO_096, "5d2e7fe24dbec0f8267db00ab2c6ccdd24799d916cb7beef3168eb66a53a4077",
                               "audio/v0.9.6", "audiocpp_cli.exe")
    if args.only in (None, "diffusion"):
        prepare_recipe_runtime(SD_CONTROL_VULKAN, "0c11ec33b9c1a636f9f72e2bc537384b6c88cf88cd72c97d53f3d834980f27e8",
                               "diffusion/0d71f96/vulkan", "sd-cli.exe")
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
        for directory in (DEST / "audio/vulkan", DEST / "audio/v0.9.6/vulkan"):
            shutil.copy2(DEST / "audio/soxr.dll", directory / "soxr.dll")
    if args.only == "audio":
        prepare_cuda("audio")
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
        prepare_cuda("diffusion")
        return
    build_text_worker(CACHE / "llama.cpp-b12648", DEST / "text")
    build_plm = ["python3", "scripts/windows/build-plm.py"]
    subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", *build_plm] if os.name == "nt" else build_plm,
                   cwd=ROOT, check=True)
    prepare_cuda(args.only)


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
