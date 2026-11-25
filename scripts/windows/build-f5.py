"""Build AiLab's F5-TTS and AuK Windows CPU worker from pinned audio.cpp."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
from native_build_tools import resolve_tool

REVISION = "61c7838baf1f7f34769b5b7bd369c0d78edf9535"
ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path)
parser.add_argument("--cmake", default="cmake")
parser.add_argument("--ninja", default="ninja")
parser.add_argument("--jobs", type=int, default=3)
args = parser.parse_args()
work = Path.home() / ".cache" / ("ailab-f5-" + REVISION[:8])
work.mkdir(parents=True, exist_ok=True)
args.cmake = resolve_tool("cmake", args.cmake, work)
args.ninja = resolve_tool("ninja", args.ninja, work)
source = args.source or work / "audio.cpp"
if not source.exists():
    subprocess.run(["git", "-c", "http.version=HTTP/1.1", "clone", "--depth=1", "--branch", "v0.9.5",
                    "https://github.com/0xShug0/audio.cpp", str(source)], check=True)
actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
if actual != REVISION:
    raise ValueError("Unexpected audio.cpp source revision " + actual)
header = source / "src/community_models/f5_tts/cpu_graph_compute.h"
original = subprocess.check_output(["git", "-C", str(source), "show", "HEAD:" + header.relative_to(source).as_posix()])
if hashlib.sha1(b"blob " + str(len(original)).encode() + b"\0" + original).hexdigest() != "a4ceaec19bbac92e5df0ef8b0d409355f049512c":
    raise ValueError("Unexpected F5 CPU implementation")
modified = original.decode().replace('#include "ggml.h"', '#include "ggml.h"\n#if defined(_WIN32)\n#include "ggml-cpu.h"\n#endif')
modified = modified.replace("#if defined(__GNUC__)", "#if defined(__GNUC__) && !defined(_WIN32)", 1)
anchor = "inline F5CpuGraphComputeFn f5_cpu_graph_compute_fn() {"
modified = modified.replace(anchor + "\n#if defined(__GNUC__)", anchor + "\n#if defined(_WIN32)\n    return &::ggml_graph_compute_with_ctx;\n#elif defined(__GNUC__)")
if header.read_bytes() not in (original, modified.encode()):
    raise ValueError("F5 CPU header contains unrelated edits")
if header.read_bytes() != modified.encode():
    header.write_bytes(modified.encode())
# All three AuK graphs select CPU kernels through the execution context. Its
# seeded Philox sampler also has a host implementation when cuda_fast_path is false.
auk = source / "src/community_models/auk/session.cpp"
auk_path = auk.relative_to(source).as_posix()
if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD:" + auk_path], text=True).strip() != "137f502e8015d89ae74aac11455d3b343f9abfbf":
    raise ValueError("Unexpected AuK source")
upstream = subprocess.check_output(["git", "-C", str(source), "show", "HEAD:" + auk_path])
guard = (b"    if (execution_context().backend_type() == core::BackendType::Cpu) {\n"
         b'        throw std::runtime_error("AuK native session does not support the CPU backend");\n'
         b"    }\n")
if upstream.count(guard) != 1:
    raise ValueError("Missing AuK CPU backend selection")
ported = upstream.replace(guard, b"    mem_saver_ = execution_context().backend_type() == core::BackendType::Cpu || mem_saver_;\n")
if auk.read_bytes() not in (upstream, ported):
    raise ValueError("AuK source contains unrelated edits")
if auk.read_bytes() != ported:
    auk.write_bytes(ported)
# MinGW headers predating the thread throttling structure still expose SetThreadInformation.
cpu = source / "external/ggml/src/ggml-cpu/ggml-cpu.c"
original_cpu = cpu.read_bytes()
eol = b"\r\n" if b"\r\n" in original_cpu else b"\n"
old_guard = b"#if _WIN32_WINNT >= 0x0602" + eol + b"        THREAD_POWER_THROTTLING_STATE"
new_guard = old_guard.replace(b"0x0602", b"0x0602 && defined(THREAD_POWER_THROTTLING_CURRENT_VERSION)")
cpu_source = original_cpu.replace(new_guard, old_guard)
if hashlib.sha1(b"blob " + str(len(cpu_source)).encode() + b"\0" + cpu_source).hexdigest() != "8bcfe3d26baf2124a2d0e4dad120b049adddeb97":
    raise ValueError("Unexpected ggml CPU source")
if cpu_source.count(old_guard) != 1:
    raise ValueError("Missing Windows scheduler capability check")
if new_guard not in original_cpu:
    cpu.write_bytes(cpu_source.replace(old_guard, new_guard))
build = work / "build"
architecture = work / "windows-x64.cmake"
architecture.write_text('set(CMAKE_SYSTEM_PROCESSOR "x86_64")\n')
subprocess.run([args.cmake, "-S", str(source), "-B", str(build), "-G", "Ninja",
                "-DCMAKE_MAKE_PROGRAM=" + args.ninja, "-DCMAKE_SYSTEM_NAME=Windows", "-DCMAKE_SYSTEM_PROCESSOR=x86_64",
                "-DCMAKE_PROJECT_INCLUDE=" + str(architecture), "-DGGML_OPENMP=OFF",
                "-DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc-posix",
                "-DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++-posix",
                "-DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres",
                "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXE_LINKER_FLAGS=-static",
                "-DAUDIOCPP_VERSION=0.9.5-ailab-f5", "-DAUDIOCPP_MODEL_SET=custom",
                "-DAUDIOCPP_MODELS=f5_tts,auk", "-DAUDIOCPP_DEPLOYMENT_BUILD=ON",
                "-DAUDIOCPP_BUILD_NATIVE_MODEL_MANAGER=OFF", "-DENGINE_ENABLE_OPENMP=OFF",
                "-DENGINE_ENABLE_CUDA=OFF", "-DENGINE_ENABLE_NATIVE_CPU=OFF",
                "-DENGINE_ENABLE_CPU_ALL_VARIANTS=OFF", "-DENGINE_ENABLE_LLAMAFILE=OFF"], check=True)
subprocess.run([args.cmake, "--build", str(build), "--target", "audiocpp_cli", "-j", str(args.jobs)], check=True)
dst = ROOT / "apps/windows-ui/runtime/audio/f5"
dst.mkdir(exist_ok=True)
shutil.copy2(build / "bin/audiocpp_cli.exe", dst / "audiocpp_cli.exe")
shutil.copy2(source / "LICENSE", dst / "LICENSE")
for notice in ("ggml/LICENSE", "sentencepiece/LICENSE", "cJSON/LICENSE", "libyaml/License", "utf8proc/LICENSE.md"):
    name = notice.split("/", 1)[0]
    shutil.copy2(source / "external" / notice, dst / ("LICENSE." + name + ".txt"))
