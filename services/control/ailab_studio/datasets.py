"""Durable dataset catalog and single download queue, independent of GPU jobs."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time

from .dataset_sources import Sources, relative, RangeUnavailable
from .storage import uid

TERMINAL = {'completed', 'failed', 'paused', 'cancelled', 'interrupted'}
FORMATS = {'.jsonl', '.json', '.parquet', '.csv', '.txt', '.zip'}
TRAINING = {'.jsonl', '.json', '.parquet'}


def file_hash(file):
    result = hashlib.sha256()
    with file.open('rb') as stream:
        while chunk := stream.read(1024 * 1024): result.update(chunk)
    return result.hexdigest()


def safe_path(root, name):
    relative(name)
    root = Path(root).absolute()
    target = root / name
    # Reject symlinks/junctions before resolving, including substituted parents.
    for part in [root, *root.parents, target, *target.parents]:
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()): raise ValueError('数据目录不能经过符号链接或目录联接')
    if not target.resolve().is_relative_to(root.resolve()): raise ValueError('数据路径超出目录')
    return target


def preview(file):
    if file.suffix.lower() not in {'.jsonl', '.json', '.csv', '.txt', '.md'}:
        return {'text': '', 'note': '此格式仅展示文件信息，请用对应工具查看内容', 'truncated': False}
    with file.open('rb') as stream: data = stream.read(32769)
    return {'text': data[:32768].decode('utf-8-sig', errors='replace'), 'truncated': len(data) > 32768, 'note': '最多预览前 32 KiB，不执行文件内容'}


class Datasets:
    def __init__(self, studio):
        self.studio, self.store = studio, studio.store
        self.sources = Sources()
        self.lock = threading.RLock()
        self.wake = threading.Event(); self.stop = threading.Event()
        for item in self.store.list('dataset-download', 100000):
            if item['state'] in {'queued', 'downloading', 'pausing', 'cancelling'}:
                item.update(state='interrupted', error='服务曾中断，已保留部分文件，可继续下载')
                self.store.put('dataset-download', item)
        self.thread = threading.Thread(target=self._loop, name='dataset-downloads', daemon=True)
        self.thread.start()

    def detail(self, provider, dataset, revision):
        info = self.sources.detail(provider, dataset, revision)
        if len(info['files']) > 5000: raise ValueError('此数据集文件超过 5000 个，请选择更小的数据集')
        selection = {'id': uid(), **info, 'created_at': time.time()}
        self.store.put('dataset-selection', selection)
        # Retain only a bounded browsing cache; active downloads contain their own snapshot.
        for old in self.store.list('dataset-selection', 100000)[100:]: self.store.delete('dataset-selection', old['id'])
        return selection

    def remote_preview(self, selection_id, path):
        info = self.store.get('dataset-selection', selection_id)
        if info['provider'] != 'huggingface': raise ValueError('Kaggle 请先下载 ZIP，解压导入后预览')
        if path not in {x['path'] for x in info['files']}: raise ValueError('文件不属于所选版本')
        if Path(path).suffix.lower() not in {'.md', '.jsonl', '.json', '.csv', '.txt'}: raise ValueError('此格式不支持文本预览')
        with self.sources.open(info['provider'], self.sources.file_url(info, path), {'Range': 'bytes=0-32768'}) as response:
            raw = response.read(32769)
        return {'text': raw[:32768].decode('utf-8-sig', errors='replace'), 'truncated': len(raw) > 32768, 'note': '来源文件前 32 KiB，不执行内容'}

    def start(self, selection_id, files, category, purpose):
        if not re.fullmatch(r'[\w\-\u4e00-\u9fff]{1,40}', category): raise ValueError('分类只接受 1 至 40 位文字、数字、下划线或短横线')
        info = self.store.get('dataset-selection', selection_id)
        available = {f['path']: f for f in info['files']}
        if not files or len(files) > 500 or len(set(files)) != len(files) or any(f not in available for f in files): raise ValueError('请选择该版本中 1 至 500 个不同文件')
        for name in files:
            relative(name)
            if name.endswith('.ailab-part'): raise ValueError('来源文件名与下载临时文件后缀冲突')
        if len({os.path.normcase(f) for f in files}) != len(files): raise ValueError('所选文件名在本机大小写规则下重复')
        with self.lock:
            if self.stop.is_set(): raise ValueError('服务正在退出')
            if sum(x['state'] in {'queued', 'downloading'} for x in self.downloads()) >= 100: raise ValueError('下载队列已满')
            for old in self.downloads():
                if old['state'] in {'queued', 'downloading'} and old['selection']['provider'] == info['provider'] and old['selection']['dataset'] == info['dataset'] and old['selection']['revision'] == info['revision'] and [f['path'] for f in old['files']] == files:
                    return old
            root = Path(self.studio.paths()['datasets']).resolve()
            key = uid(); directory = safe_path(root, f'market/{category}/{key}')
            if os.name == 'nt' and any(len(str(directory / (f + '.ailab-part'))) >= 260 for f in files): raise ValueError('下载文件路径过长，请在设置中选择更短的数据根目录')
            if shutil.disk_usage(root).free < sum((available[f]['size'] or 0) for f in files) + 64 * 1024 * 1024: raise ValueError('磁盘剩余空间不足')
            directory.mkdir(parents=True, exist_ok=False)
            item = {'id': key, 'state': 'queued', 'selection': {k: info[k] for k in ('provider', 'dataset', 'title', 'revision', 'license', 'source_url')},
                    'files': [{**available[f], 'received': 0, 'sha256': None, 'complete': False} for f in files], 'directory': str(directory),
                    'download_root': str(root), 'category': category, 'purpose': purpose, 'created_at': time.time(), 'updated_at': time.time(),
                    'error': None, 'attempts': 0, 'received_bytes': 0, 'total_bytes': sum(available[f]['size'] or 0 for f in files) or None}
            self.store.put('dataset-download', item)
        self.wake.set()
        return item

    def downloads(self): return self.store.list('dataset-download', 100000)

    def control(self, key, action):
        with self.lock:
            item = self.store.get('dataset-download', key)
            if action == 'resume':
                if item['state'] not in {'failed', 'paused', 'cancelled', 'interrupted'}: raise ValueError('此任务当前不能继续')
                item.update(state='queued', error=None)
            elif action in {'pause', 'cancel'}:
                if item['state'] not in {'queued', 'downloading'}: raise ValueError('此任务当前不能暂停或取消')
                item['state'] = ('pausing' if action == 'pause' else 'cancelling') if item['state'] == 'downloading' else ('paused' if action == 'pause' else 'cancelled')
            else: raise ValueError('下载操作不支持')
            self.store.put('dataset-download', item)
        self.wake.set()
        return item

    def _checkpoint(self, key):
        item = self.store.get('dataset-download', key)
        if self.stop.is_set() or item['state'] in {'pausing', 'cancelling'}: raise InterruptedError()

    def _save(self, item):
        with self.lock:
            current = self.store.get('dataset-download', item['id'])
            item['state'] = current['state']
            item['received_bytes'] = sum(f['received'] for f in item['files']); item['updated_at'] = time.time()
            item['total_bytes'] = sum(f['size'] for f in item['files']) if all(f['size'] is not None for f in item['files']) else None
            self.store.put('dataset-download', item)

    def _transfer(self, item, file):
        key = item['id']; destination = safe_path(Path(item['directory']), file['path'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = safe_path(Path(item['directory']), file['path'] + '.ailab-part')
        if file['complete'] and destination.is_file() and file_hash(destination) == file['sha256']: return
        # An unexpected existing final file must not be overwritten on retry.
        if destination.exists(): raise ValueError('目标文件已被修改，请保留现有文件并重新创建下载任务')
        start = partial.stat().st_size if partial.exists() else 0
        if start and not (file.get('etag') or file.get('expected_sha256')): start = 0
        if file['size'] is not None and start > file['size']: raise ValueError('部分文件超过来源大小，请清理该下载后重试')
        if start and file['size'] is not None and start == file['size']:
            # Only a source checksum proves a previously complete partial file.
            if file.get('expected_sha256') and file_hash(partial) == file['expected_sha256']:
                partial.replace(destination); file.update(received=start, sha256=file_hash(destination), complete=True); self._save(item); return
            start = 0
        headers = {'Range': f'bytes={start}-'} if start else {}
        if start and file.get('etag'): headers['If-Range'] = file['etag']
        url = self.sources.file_url(item['selection'], file['path'])
        try: response = self.sources.open(item['selection']['provider'], url, headers)
        except RangeUnavailable:
            if not start: raise
            start = 0
            response = self.sources.open(item['selection']['provider'], url, {})
        with response:
            status = response.status
            content_range = response.headers.get('Content-Range', '')
            if status == 206:
                match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', content_range)
                if not match or int(match[1]) != start: raise ValueError('来源断点响应无效，未追加任何字节')
                total = int(match[3])
                if file['size'] is not None and file['size'] != total: raise ValueError('来源文件大小已变化')
                if start and file.get('etag') and response.headers.get('ETag') != file['etag']: raise ValueError('来源文件标识已变化，不能追加旧文件')
            elif status == 200:
                start = 0  # Server ignored Range or If-Range: safely restart this file.
                total = int(response.headers['Content-Length']) if response.headers.get('Content-Length') else file['size']
            else: raise ValueError('来源未返回可下载文件')
            if file['size'] is not None and total is not None and file['size'] != total: raise ValueError('来源大小与固定版本清单不符')
            if response.headers.get_content_type() in {'text/html', 'application/xhtml+xml'} and destination.suffix.lower() not in {'.html', '.htm'}: raise ValueError('来源返回登录页面，请检查凭据与访问权限')
            file['etag'] = response.headers.get('ETag'); file['received'] = start
            file['size'] = total
            self._save(item)
            if total is not None and shutil.disk_usage(destination.parent).free < max(0, total - start) + 64 * 1024 * 1024: raise ValueError('磁盘剩余空间不足')
            saved = time.monotonic()
            with partial.open('ab' if start else 'wb') as stream:
                while True:
                    self._checkpoint(key)
                    chunk = response.read(256 * 1024)
                    if not chunk: break
                    if total is not None and file['received'] + len(chunk) > total: raise ValueError('来源传输了超出声明大小的数据')
                    if shutil.disk_usage(destination.parent).free < len(chunk) + 16 * 1024 * 1024: raise ValueError('磁盘剩余空间不足')
                    stream.write(chunk); file['received'] += len(chunk)
                    if time.monotonic() - saved > .3: self._save(item); saved = time.monotonic()
        if total is not None and file['received'] != total: raise ValueError('连接提前结束，已保留部分文件，可继续下载')
        self._checkpoint(key)
        checksum = file_hash(partial)
        if file.get('expected_sha256') and checksum != file['expected_sha256']:
            partial.unlink(); file['received'] = 0
            raise ValueError('来源 SHA256 校验失败，错误部分文件已清除，可重试')
        if destination.suffix.lower() == '.zip':
            import zipfile
            if not zipfile.is_zipfile(partial): raise ValueError('下载内容不是有效 ZIP，请检查来源访问权限')
        partial.replace(destination); file.update(size=file['received'], sha256=checksum, complete=True)
        self._save(item)

    def _loop(self):
        while not self.stop.is_set() and not self.studio.stopping:
            with self.lock:
                queued = sorted((x for x in self.downloads() if x['state'] == 'queued'), key=lambda x: x['created_at'])
                item = queued[0] if queued else None
                if item:
                    item.update(state='downloading', attempts=item['attempts'] + 1, error=None)
                    self.store.put('dataset-download', item)
            if not item: self.wake.wait(.3); self.wake.clear(); continue
            try:
                for file in item['files']:
                    for attempt in range(3):
                        self._checkpoint(item['id'])
                        try: self._transfer(item, file); break
                        except InterruptedError: raise
                        except (ValueError, OSError):
                            if attempt == 2: raise
                            self.stop.wait(.5 * (attempt + 1))
                with self.lock:
                    self._checkpoint(item['id'])
                    item.update(state='completed', error=None)
                    self.store.put('dataset-download', item)
                    self.store.put('dataset', {'id': item['id'], 'name': item['selection']['title'], 'path': item['directory'],
                        'source': item['selection']['provider'], 'provenance': item['selection'], 'files': [{k: f.get(k) for k in ('path', 'size', 'sha256')} for f in item['files']],
                        'category': item['category'], 'purpose': item['purpose'], 'created_at': time.time(), 'managed': True,
                        'download_root': item['download_root'], 'size': sum(f['received'] for f in item['files'])})
            except Exception as exc:
                with self.lock:
                    current = self.store.get('dataset-download', item['id'])
                    state = 'cancelled' if current['state'] == 'cancelling' else 'paused' if isinstance(exc, InterruptedError) else 'failed'
                    item.update(state=state, error=None if isinstance(exc, InterruptedError) else str(exc)[:600])
                    item['received_bytes'] = sum(f['received'] for f in item['files'])
                    self.store.put('dataset-download', item)

    def import_local(self, raw, category, purpose):
        path = Path(raw).expanduser()
        if not path.is_absolute(): raise ValueError('请选择本机绝对路径')
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()): raise ValueError('不导入符号链接或目录联接')
        path = path.resolve()
        if not path.exists(): raise ValueError('本地数据路径不存在')
        files = []
        candidates = [path] if path.is_file() else path.rglob('*')
        for count, file in enumerate(candidates):
            if count > 20000: raise ValueError('目录过大，请选择更具体的数据目录')
            if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(path if path.is_dir() else path.parent): continue
            if file.suffix.lower() not in FORMATS: continue
            relative_name = file.name if path.is_file() else file.relative_to(path).as_posix()
            files.append({'path': relative_name, 'size': file.stat().st_size, 'sha256': file_hash(file)})
            if len(files) > 5000: raise ValueError('导入文件过多，请选择更具体的数据目录')
        if not files: raise ValueError('未找到 JSON、JSONL、Parquet、CSV、TXT 或 ZIP 文件')
        item = {'id': uid(), 'name': path.name, 'path': str(path), 'source': 'local', 'provenance': None, 'files': files,
                'category': category, 'purpose': purpose, 'created_at': time.time(), 'managed': False, 'size': sum(f['size'] for f in files)}
        return self.store.put('dataset', item)

    def local_file(self, key, name):
        item = self.store.get('dataset', key)
        if name not in {f['path'] for f in item['files']}: raise ValueError('文件未登记')
        original = Path(item['path']); root = original.parent if original.is_file() else original
        file = safe_path(root, name)
        if not file.is_file(): raise ValueError('本地文件已移走或删除')
        return file

    def assets(self):
        result = []
        for item in self.store.list('dataset', 100000):
            for f in item['files']:
                if Path(f['path']).suffix.lower() not in TRAINING: continue
                try: file = self.local_file(item['id'], f['path'])
                except ValueError: continue
                result.append({'path': str(file), 'name': item['name'] + ' / ' + f['path'], 'format': file.suffix[1:]})
        return result

    def training_reference(self, path):
        """Freeze the selected file's observed content and provenance into the SFT job."""
        selected = Path(path).resolve()
        if not selected.is_file(): return None
        for item in self.store.list('dataset', 100000):
            for entry in item['files']:
                try: candidate = self.local_file(item['id'], entry['path'])
                except ValueError: continue
                if candidate.resolve() != selected: continue
                observed = file_hash(candidate)
                if entry['sha256'] and observed != entry['sha256']: raise ValueError('已登记下载文件发生变化，请作为本地数据重新导入后训练')
                return {'dataset_id': item['id'], 'source': item['source'], 'provenance': item['provenance'],
                        'file': entry['path'], 'sha256': observed, 'bytes': candidate.stat().st_size, 'purpose': item['purpose']}
        return None

    def remove(self, key, delete_files=False):
        with self.lock:
            item = self.store.get('dataset', key)
            if delete_files:
                if not item['managed']: raise ValueError('本地导入仅移除索引，不删除源文件')
                self._delete_directory(item)
            self.store.delete('dataset', key)
            return {'removed': True, 'files_deleted': delete_files}

    def cleanup(self, key):
        with self.lock:
            item = self.store.get('dataset-download', key)
            if item['state'] not in TERMINAL: raise ValueError('请先暂停或取消下载')
            self._delete_directory(item)
            self.store.delete('dataset', key); self.store.delete('dataset-download', key)
            return {'removed': True}

    def _delete_directory(self, item):
        root = Path(item['download_root']); directory = Path(item.get('directory') or item['path'])
        expected = safe_path(root, 'market/' + item['category'] + '/' + item['id'])
        if directory.absolute() != expected.absolute(): raise ValueError('下载目录身份不匹配，不能清理')
        for job in self.studio.store.list('job', 100000):
            raw = job.get('config', {}).get('dataset')
            if raw and job['state'] not in {'succeeded', 'failed', 'cancelled', 'interrupted'}:
                used = Path(raw).resolve()
                if used.is_relative_to(directory.resolve()) or directory.resolve().is_relative_to(used): raise ValueError('数据仍被任务使用，请先结束任务')
        if directory.exists(): shutil.rmtree(directory)

    def close(self):
        self.stop.set(); self.wake.set(); self.thread.join(timeout=20)
        if self.thread.is_alive(): raise ValueError('下载仍在结束，请稍后退出')
