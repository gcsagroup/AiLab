"""Owned local media library, with bounded uploads and content chunks for the IPC bridge."""
import base64
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from .storage import uid

LIMIT = 2 * 1024**3


def media_type(path):
    with path.open('rb') as stream: header = stream.read(32)
    if header.startswith(b'\x89PNG\r\n\x1a\n'): return 'image', 'image/png', '.png'
    if header.startswith(b'\xff\xd8\xff'): return 'image', 'image/jpeg', '.jpg'
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP': return 'image', 'image/webp', '.webp'
    if header[4:8] == b'ftyp': return 'video', 'video/mp4', '.mp4'
    if header.startswith(b'\x1a\x45\xdf\xa3'): return 'video', 'video/webm', '.webm'
    raise ValueError('仅支持 PNG、JPEG、WebP 图像及 MP4、WebM 视频')


class Materials:
    def __init__(self, studio):
        self.studio = studio
        self.root = studio.root / 'materials'; self.root.mkdir(exist_ok=True)
        self.staging = self.root / '.uploads'; self.staging.mkdir(exist_ok=True)
        self.thumbnails = self.root / '.thumbnails'; self.thumbnails.mkdir(exist_ok=True)
        self.thumbnail_lock = threading.Lock()

    def thumbnail(self, key):
        from .runtimes import interpreter
        item = self.get(key)
        target = self.thumbnails / (item['id'] + '.jpg')
        with self.thumbnail_lock:
            if not target.is_file():
                profiles = ('diffusers',) if item['kind'] == 'video' else ('diffusers', 'llama', 'ablation', 'vllm')
                runtime = None
                for profile in profiles:
                    try: runtime = self.studio.runtimes.resolve(profile); break
                    except ValueError: continue
                if runtime is None: raise ValueError('预览需要已安装的图像环境；视频缩略图需要 Diffusers 环境')
                worker = Path(__file__).parent / 'workers' / 'thumbnail.py'
                result = subprocess.run([str(interpreter(runtime['path'])), str(worker), item['path'], str(target), item['kind']],
                                        capture_output=True, timeout=25,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if result.returncode or not target.is_file(): raise ValueError('无法生成缩略图，请点击素材查看原文件')
        return {'data_url': 'data:image/jpeg;base64,' + base64.b64encode(target.read_bytes()).decode()}

    def add(self, file, source, name='', parameters=None, job_id=None):
        file = Path(file).resolve()
        if not file.is_file() or file.stat().st_size > LIMIT: raise ValueError('素材不存在或超过 2 GiB')
        kind, mime, extension = media_type(file)
        key = uid(); destination = self.root / (key + extension)
        shutil.copyfile(file, destination)
        digest = hashlib.sha256()
        with destination.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024**2), b''): digest.update(chunk)
        return self.studio.store.put('material', {'id': key, 'name': name or file.name, 'kind': kind, 'source': source,
            'mime': mime, 'path': str(destination), 'size': destination.stat().st_size, 'sha256': digest.hexdigest(),
            'created_at': time.time(), 'parameters': parameters or {}, 'job_id': job_id})

    def get(self, key):
        item = self.studio.store.get('material', key); file = Path(item['path']).resolve()
        if not file.is_relative_to(self.root.resolve()) or not file.is_file(): raise ValueError('素材文件不存在')
        return item

    def content(self, key, offset, length):
        item = self.get(key)
        with Path(item['path']).open('rb') as stream:
            stream.seek(offset); data = stream.read(length)
        return {'mime': item['mime'], 'size': item['size'], 'offset': offset, 'data': base64.b64encode(data).decode()}

    def delete(self, key):
        with self.studio.mutex, self.thumbnail_lock:
            item = self.studio.store.get('material', key)
            path = Path(item['path']).resolve()
            if path.parent != self.root.resolve() or path.stem != item['id']:
                raise ValueError('素材路径无效，拒绝删除')
            for job in self.studio.store.list('job', 100000):
                config = job.get('config', {})
                if job['state'] in ('queued', 'running', 'paused', 'cancelling') and (config.get('material_id') == key or config.get('image_path') == str(path)):
                    raise ValueError('素材正被任务使用，请先结束对应任务')
            path.unlink(missing_ok=True)
            (self.thumbnails / (item['id'] + '.jpg')).unlink(missing_ok=True)
            self.studio.store.delete('material', key)
        return {'id': key}

    def begin(self, name, size):
        if not name or not 0 < size <= LIMIT: raise ValueError('文件名或大小无效，最大 2 GiB')
        if shutil.disk_usage(self.root).free < size * 2 + 100 * 1024**2: raise ValueError('素材库磁盘空间不足')
        key = uid(); (self.staging / key).touch()
        return self.studio.store.put('upload', {'id': key, 'name': name, 'size': size, 'offset': 0})

    def append(self, key, offset, data):
        try: chunk = base64.b64decode(data, validate=True)
        except ValueError as exc: raise ValueError('文件编码无效') from exc
        if not chunk or len(chunk) > 1024**2: raise ValueError('上传分片大小无效')
        with self.studio.mutex:
            item = self.studio.store.get('upload', key)
            if offset != item['offset'] or offset + len(chunk) > item['size']: raise ValueError('上传分片位置不匹配')
            with (self.staging / key).open('r+b') as stream:
                stream.seek(offset); stream.write(chunk); stream.truncate()
            item['offset'] += len(chunk)
            return self.studio.store.put('upload', item)

    def complete(self, key):
        with self.studio.mutex:
            item = self.studio.store.get('upload', key)
            if item['offset'] != item['size']: raise ValueError('素材尚未上传完毕')
            result = self.add(self.staging / key, 'imported', item['name'])
            (self.staging / key).unlink(); self.studio.store.delete('upload', key)
            return result
