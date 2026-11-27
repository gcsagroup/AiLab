"""Create deterministic downloads for AiLab's custom Windows workers and their notices."""
import argparse
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

root = Path(__file__).resolve().parents[2]
runtime = root / "apps/windows-ui/runtime"
groups = {
    "base": ["text/ailab-gguf.exe", "text/plm-worker.exe", "text/LICENSE.llama.cpp.txt",
             "diffusion/LICENSE.ffmpeg-GPLv3.txt"],
    "image-video": ["diffusion/ailab-image.exe", "diffusion/LICENSE.stb.txt", "diffusion/LICENSE.stable-diffusion.txt"],
    "audio": ["audio/f5/*", "audio/soxr.dll", "audio/soxr-*.txt", "audio/espeak/COPYING.txt", "audio/LICENSE.sea-g2p.txt"],
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
for group, patterns in groups.items():
    target = args.output / f"ailab-workers-{group}-20261127-x64.zip"
    with ZipFile(target, "w") as archive:
        for pattern in patterns:
            files = sorted(runtime.glob(pattern))
            if not files:
                raise FileNotFoundError(pattern)
            for file in files:
                member = ZipInfo(file.relative_to(runtime).as_posix())
                member.compress_type = ZIP_DEFLATED
                archive.writestr(member, file.read_bytes())
    with target.open("rb") as stream:
        print(target.name, hashlib.file_digest(stream, "sha256").hexdigest())
