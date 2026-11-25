"""Build AiLab's corrected language graphs against the pinned ggml ABI."""
from pathlib import Path
from urllib.request import urlopen
import argparse
import hashlib
import re
import shutil
import subprocess
import tarfile
from native_build_tools import resolve_tool

REV = "44d50873b56b568c28ef2ad8d6445069feaa9fbd"
ARCHIVE_HASH = "cd9225f12dc66ab662f53e629f1fb2d487a593fcfbd289eca86d8f6211b6b1a9"
ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--archive", type=Path)
parser.add_argument("--cmake", default="cmake")
parser.add_argument("--ninja", default="ninja")
parser.add_argument("--jobs", default="3")
args = parser.parse_args()
work = Path.home() / ".cache" / ("ailab-windows-plm-" + REV[:10])
work.mkdir(parents=True, exist_ok=True)

args.cmake = resolve_tool("cmake", args.cmake, work)
args.ninja = resolve_tool("ninja", args.ninja, work)
archive = args.archive or work / "llama.tgz"
if not archive.exists():
    with urlopen("https://codeload.github.com/ggml-org/llama.cpp/tar.gz/" + REV[:12], timeout=120) as src, archive.open("wb") as dst:
        shutil.copyfileobj(src, dst)
with archive.open("rb") as src:
    if hashlib.sha256(src.read()).hexdigest() != ARCHIVE_HASH:
        raise ValueError("Unexpected llama.cpp source archive")
with tarfile.open(archive) as tar:
    prefix = tar.getmembers()[0].name.split("/")[0]
    for member in tar.getmembers():
        if member.isfile() and any(member.name.startswith(prefix + "/" + path) for path in ("ggml/include/", "src/", "include/", "vendor/")):
            dest = (work / member.name).resolve()
            if work.resolve() not in dest.parents:
                raise ValueError(member.name)
            if not dest.exists() or member.name.endswith("/src/models/qwen4exp.cpp"):
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as output:
                    shutil.copyfileobj(tar.extractfile(member), output)
src = work / prefix
# The vendor ggml DLL and MinGW can use different Windows CRTs. Keep the FILE*
# used by MinGW's fseek/_fileno in the same CRT while preserving UTF-8 filenames.
io_source = src / "src/llama-mmap.cpp"
code = io_source.read_text()
if "ggml_fopen(fname.c_str(), mode)" in code:
    io_source.write_text("#include <filesystem>\n" + code.replace("ggml_fopen(fname.c_str(), mode)",
        "_wfopen(std::filesystem::u8path(fname).c_str(), std::filesystem::u8path(mode).c_str())"))
plm = src / "src/models/plm.cpp"
code = plm.read_text()
# b12648's KV cache expects [value_width, head, token]. The original projection
# already has that shape. Flattening it makes ggml_set_rows reject the first prefill.
start = code.find("            v_states = ggml_view_2d")
if start >= 0:
    end = code.index("            q = build_rope", start)
    plm.write_text(code[:start] + code[end:])
step = src / "src/models/step35.cpp"
code = step.read_text()
pattern = "ml.get_arr(LLM_KV_ATTENTION_SLIDING_WINDOW_PATTERN, hparams.is_swa_impl);"
if "if (!hparams.is_swa_any())" not in code:
    if pattern not in code:
        raise ValueError("Unrecognized Step35 attention metadata loader")
    code=code.replace(pattern, pattern + "\n    if (!hparams.is_swa_any()) hparams.swa_type = LLAMA_SWA_TYPE_NONE;")
if 'auto * full_attn' not in code:
    # The regular and interleaved-SWA caches have different concrete types.
    code,inputs=re.subn(r'auto\s+\* inp_attn\s*= build_attn_inp_kv_iswa\(\);',
        'auto * full_attn = hparams.is_swa_any() ? nullptr : build_attn_inp_kv();\n'
        '    auto * swa_attn = hparams.is_swa_any() ? build_attn_inp_kv_iswa() : nullptr;',code)
    code,calls=re.subn(r'build_attn\(inp_attn,(\s+nullptr, nullptr, nullptr,\s+Qcur, Kcur, Vcur, nullptr, nullptr, nullptr, kq_scale, il)\)',
        r'swa_attn ? build_attn(swa_attn,\1) : build_attn(full_attn,\1)',code)
    if inputs!=2 or calls!=2:raise ValueError("Unrecognized Step35 attention graph")
step.write_text(code)
qwen = src / "src/models/qwen4exp.cpp"
code = qwen.read_text()
# The PLE projection consumes the concatenated n-gram heads. Their width
# need not equal the language model's hidden size, e.g. 16 vs 8 in Mini Qwen.
width = "int64_t(hparams.ple_head_dim) * hparams.ple_n_heads"
for projection, output in (("KEY", "hc_dim"), ("VALUE", "n_embd")):
    prefix = rf'(create_tensor\(tn\(LLM_TENSOR_PLE_{projection},\s+"weight", il\), \{{ )'
    suffix = rf'(, {output} \}})'
    if re.search(prefix + re.escape(width) + suffix, code):
        continue
    code, count = re.subn(prefix + "n_embd" + suffix, rf'\g<1>{width}\2', code)
    if count != 1:
        raise ValueError("Unrecognized Qwen4Exp PLE " + projection + " projection")
# A checkpoint can enable the indexer only in the MTP layer. Building the
# trunk's input object then tries to fill cache row tensors with no consumer.
trunk = "if (mctx_idx && hparams.indexer_kpool > 0)"
mtp = "if (mctx_hyb->get_idx() && hparams.indexer_kpool > 0)"
if code.count(trunk) != 1 or code.count(mtp) != 1:
    raise ValueError("Unrecognized Qwen4Exp indexer inputs")
code = code.replace(trunk, '''bool has_trunk_indexer = false;
    for (int il = 0; il < n_layer; ++il) {
        has_trunk_indexer |= !hparams.is_recr(il) && hparams.dsv4_compress_ratios[il] > 0;
    }
    if (mctx_idx && has_trunk_indexer)''')
code = code.replace(mtp, "if (mctx_hyb->get_idx() && hparams.dsv4_compress_ratios[il] > 0)")
qwen.write_text(code)
factory = src / "src/llama-model.cpp"
code = factory.read_text()
mapping = code.index("static llama_model * llama_model_mapping")
start = code.index("{",mapping) + 1
end = code.index("\n}",start)
graphs = ("plm", "step35", "qwen4exp")
constructors = "".join(f"\n    if (arch == LLM_ARCH_{name.upper()}) return new llama_model_{name}(params);" for name in graphs)
factory.write_text(code[:start] + constructors + '\n    throw std::runtime_error("Unsupported AiLab graph");' + code[end:])
cm = src / "src/CMakeLists.txt"
listing = 'set(LLAMA_MODELS_SOURCES models/plm.cpp models/step35.cpp models/qwen4exp.cpp models/delta-net-base.cpp)'
source_list = cm.read_text().replace('file(GLOB LLAMA_MODELS_SOURCES "models/*.cpp")', listing)
source_list, count = re.subn(r'set\(LLAMA_MODELS_SOURCES models/plm\.cpp[^)]*\)', listing, source_list)
if count != 1:
    raise ValueError("Unrecognized model source list")
cm.write_text(source_list)
runtime = ROOT / "apps/windows-ui/runtime/text"
project = work / "project"
project.mkdir(exist_ok=True)
(project / "CMakeLists.txt").write_text(f'''cmake_minimum_required(VERSION 3.18)
project(ailab_plm LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(BUILD_SHARED_LIBS OFF)
set(LLAMA_VERSION_BASE 0.0.0)
set(LLAMA_VERSION_MAJOR 0)
set(LLAMA_BUILD_NUMBER 12648)
set(LLAMA_BUILD_COMMIT "{REV}")
function(llama_add_compile_flags)
endfunction()
add_library(ggml INTERFACE)
target_include_directories(ggml INTERFACE "{src}/ggml/include" "{src}/vendor")
target_link_libraries(ggml INTERFACE "{runtime}/ggml.dll" "{runtime}/ggml-base.dll")
add_subdirectory("{src}/src" llama-code)
set_target_properties(llama PROPERTIES PREFIX "" OUTPUT_NAME ailab-plm)
add_executable(plm-worker "{ROOT}/workers/gguf-trial.cpp")
target_include_directories(plm-worker PRIVATE "{src}/vendor" "{ROOT}/.artifacts/ggml-sdk/llama.cpp-b12648/tools/mtmd")
target_link_libraries(plm-worker PRIVATE llama "{runtime}/mtmd.dll")
target_link_options(plm-worker PRIVATE -static -s)
''')
build = work / "build"
subprocess.run([args.cmake, "-S", project, "-B", build, "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM="+args.ninja,
    "-DCMAKE_SYSTEM_NAME=Windows", "-DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc", "-DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++",
    "-DCMAKE_BUILD_TYPE=Release"], check=True)
subprocess.run([args.cmake, "--build", build, "--target", "plm-worker", "-j", args.jobs], check=True)
shutil.copyfile(build / "plm-worker.exe", runtime / "plm-worker.exe")
