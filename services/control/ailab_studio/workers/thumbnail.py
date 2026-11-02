"""Bounded CPU-only thumbnail generation in an installed media-capable environment."""
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageOps

source, target, kind = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
Image.MAX_IMAGE_PIXELS = 40_000_000
temporary = target.with_suffix('.tmp.jpg')
try:
    if kind == 'video':
        import imageio_ffmpeg
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error', '-threads', '1',
                        '-i', str(source), '-frames:v', '1', '-vf', 'scale=480:320:force_original_aspect_ratio=decrease',
                        '-threads', '1', '-y', str(temporary)], check=True, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    else:
        with Image.open(source) as original:
            original.thumbnail((480, 320))
            picture = ImageOps.exif_transpose(original).convert('RGBA')
            background = Image.new('RGB', picture.size, '#edf1ef')
            background.paste(picture, mask=picture.getchannel('A'))
            background.save(temporary, format='JPEG', quality=82)
    os.replace(temporary, target)
finally:
    temporary.unlink(missing_ok=True)
