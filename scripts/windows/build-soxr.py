"""Build the shared Windows resampler used by audio.cpp's MuLaCover chord frontend."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

from native_build_tools import resolve_tool

DIGEST = "b111c15fdc8c029989330ff559184198c161100a59312f5dc19ddeb9b5a15889"
URL = "https://deb.debian.org/debian/pool/main/libs/libsoxr/libsoxr_0.1.3.orig.tar.xz"
destination = Path(__file__).resolve().parents[2] / "apps/windows-ui/runtime/audio"
parser = argparse.ArgumentParser()
parser.add_argument("--archive", type=Path)
parser.add_argument("--cmake", default="cmake")
parser.add_argument("--ninja", default="ninja")
args = parser.parse_args()
work = Path.home() / ".cache/ailab-soxr-0.1.3"
work.mkdir(parents=True, exist_ok=True)
archive = args.archive or work / "soxr-0.1.3.tar.xz"
if not archive.is_file():
    with urllib.request.urlopen(URL, timeout=40) as response:
        archive.write_bytes(response.read())
if hashlib.sha256(archive.read_bytes()).hexdigest() != DIGEST:
    raise ValueError("Unexpected SoX Resampler source archive")
with tarfile.open(archive) as source_archive:
    source_archive.extractall(work, filter="data")
source = work / "soxr-0.1.3-Source"
build = work / "windows-x64"
cmake = resolve_tool("cmake", args.cmake, work)
ninja = resolve_tool("ninja", args.ninja, work)
subprocess.run([cmake, "-S", str(source), "-B", str(build), "-G", "Ninja",
                "-DCMAKE_MAKE_PROGRAM=" + ninja, "-DCMAKE_SYSTEM_NAME=Windows",
                "-DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc-posix",
                "-DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++-posix",
                "-DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres",
                "-DCMAKE_SHARED_LINKER_FLAGS=-static-libgcc", "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_POLICY_VERSION_MINIMUM=3.5", "-DBUILD_SHARED_LIBS=ON",
                "-DBUILD_TESTS=OFF", "-DWITH_OPENMP=OFF", "-DWITH_LSR_BINDINGS=OFF"], check=True)
subprocess.run([cmake, "--build", str(build), "--target", "soxr", "-j", "2"], check=True)
library, = build.rglob("*soxr*.dll")
shutil.copy2(library, destination / "soxr.dll")
for notice in ("LICENCE", "COPYING.LGPL"):
    shutil.copy2(source / notice, destination / ("soxr-" + notice + ".txt"))
