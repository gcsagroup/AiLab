"""Package Windows inference components separately from the desktop application."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[2]
runtime = root / 'apps/windows-ui/runtime'
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=root.parent / 'release' / 'runtime-components')
parser.add_argument('--component', action='append', choices=['base', 'image-video', 'audio', 'text-cuda', 'image-video-cuda', 'audio-cuda'])
args = parser.parse_args()

required = {
    'base': ['text/ailab-gguf.exe', 'text/plm-worker.exe', 'text/llama.dll', 'text/llama-server.exe',
             'text/llama-server-impl.dll', 'text/mtmd.dll', 'diffusion/ffmpeg.exe'],
    'image-video': ['diffusion/ailab-image.exe', 'diffusion/sd-cli.exe', 'diffusion/0d71f96/sd-cli.exe',
                    'diffusion/stable-diffusion.dll', 'diffusion/0d71f96/vulkan/ggml-vulkan.dll'],
    'audio': ['audio/audiocpp_cli.exe', 'audio/vulkan/audiocpp_cli.exe', 'audio/v0.9.6/vulkan/audiocpp_cli.exe',
              'audio/f5/audiocpp_cli.exe', 'audio/v0.9.6/audiocpp_cli.exe', 'audio/audiocpp_gguf.exe',
              'audio/model_specs/mira_tts.json', 'audio/sea_g2p_rs.dll', 'audio/sea_g2p.bin', 'audio/soxr.dll'],
    'text-cuda': ['text/cuda/ailab-gguf.exe', 'text/cuda/plm-worker.exe', 'text/cuda/llama-server.exe', 'text/cuda/ggml-cuda.dll',
                  'text/native-kernels/cuda/ailab-gguf.exe', 'text/native-kernels/cuda/ggml-cuda.dll'],
    'image-video-cuda': ['diffusion/cuda/ailab-image.exe', 'diffusion/cuda/sd-cli.exe',
                         'diffusion/0d71f96/cuda/sd-cli.exe', 'diffusion/0d71f96/cuda/ggml-cuda.dll'],
    'audio-cuda': ['audio/cuda/audiocpp_cli.exe', 'audio/v0.9.6/cuda/audiocpp_cli.exe',
                   'audio/cuda/ggml-cuda.dll', 'audio/v0.9.6/cuda/ggml-cuda.dll', 'audio/cuda-runtime/cufft64_11.dll'],
}
for engine, group in [('text', 'text-cuda'), ('diffusion', 'image-video-cuda'), ('audio', 'audio-cuda')]:
    required[group] += [f'{engine}/cuda-runtime/{name}' for name in ('cudart64_12.dll', 'cublas64_12.dll', 'cublasLt64_12.dll')]
if args.component:
    required = {group: required[group] for group in dict.fromkeys(args.component)}
for group, files in required.items():
    missing = [name for name in files if not (runtime / name).is_file()]
    if missing:
        raise SystemExit(f'Missing {group} components: {", ".join(missing)}. Run prepare-gguf.py first.')

def category(relative):
    parts = relative.parts
    engine = parts[0]
    cuda = 'cuda' in parts or 'cuda-runtime' in parts or 'native-kernels' in parts
    if engine == 'text': return 'text-cuda' if cuda else 'base'
    if engine == 'audio': return 'audio-cuda' if cuda else 'audio'
    if engine == 'diffusion':
        if parts[-1] == 'ffmpeg.exe' or parts[-1].startswith(('ffmpeg-', 'LICENSE.ffmpeg')): return 'base'
        return 'image-video-cuda' if cuda else 'image-video'
    raise ValueError(f'Unexpected runtime path: {relative}')

files = {group: [] for group in required}
for file in runtime.rglob('*'):
    if file.is_symlink(): raise SystemExit(f'Unexpected runtime symlink: {file}')
    if file.is_file():
        group = category(file.relative_to(runtime))
        if group in files: files[group].append(file)
args.output.mkdir(parents=True, exist_ok=True)
manifest = {}
for group, members in files.items():
    target = args.output / f'GCSA-AiLab-runtime-{group}-20261127-x64.zip'
    if target.exists(): raise SystemExit(f'Output already exists: {target}')
    print(f'Packaging {group} ({len(members)} files)...', flush=True)
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for file in sorted(members): archive.write(file, file.relative_to(runtime).as_posix())
    with target.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest[group] = {'filename': target.name, 'size_bytes': target.stat().st_size, 'sha256': digest}
    if target.stat().st_size >= 2_000_000_000: raise SystemExit(f'Component exceeds GitHub release asset limit: {target}')
    print(f'  {target.stat().st_size} bytes · {digest}', flush=True)
(args.output / 'runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
