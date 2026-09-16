"""首用固定官方模型下载；显式网络请求、可续传字节和独立登记。"""

import os
from pathlib import Path
import re
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request

from .assets import copy_asset, file_hash, model_manifest, regular_path, restricted_execution_boundary, verify_manifest
from .model_catalog import CATALOG_ID, FILES, MODEL_NAME, REPO, REVISION
from .storage import Fault, digest, identifier, now

ACTIVE = {'queued', 'downloading', 'verifying'}
SEGMENT_BYTES = 8 * 1024 * 1024


def https_source(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ''
        valid = parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None, 443) and (host == 'huggingface.co' or host.endswith('.huggingface.co') or host.endswith('.hf.co'))
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise Fault('MODEL_DOWNLOAD_SOURCE_REJECTED', '模型下载仅接受固定官方来源及其 HTTPS 文件分发地址。', 403)
    return url


class ModelRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        https_source(newurl)
        return super().redirect_request(request, response, code, message, headers, newurl)


class OfficialSource:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), ModelRedirect())

    def open(self, name, offset, end):
        if name not in {item['path'] for item in FILES}:
            raise Fault('MODEL_DOWNLOAD_SOURCE_REJECTED', '文件不在固定模型清单中。', 403)
        url = https_source(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}')
        request = urllib.request.Request(url, headers={'User-Agent': 'GCSA-AiLab/0.1.0', 'Range': f'bytes={offset}-{end}', 'Accept-Encoding': 'identity'})
        return self.opener.open(request, timeout=30)


def child_directory(root, *parts):
    root = regular_path(root)
    for part in parts:
        target = root / part
        if target.is_symlink():
            raise Fault('MODEL_DOWNLOAD_PATH_CHANGED', '下载路径发生变化，原文件保留。', 409)
        target.mkdir(exist_ok=True, mode=0o700)
        root = regular_path(target)
        if not root.is_dir():
            raise Fault('MODEL_DOWNLOAD_PATH_CHANGED', '下载路径不是目录。', 409)
    return root


class ModelDownloads:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.root = child_directory(service.root, 'model-downloads')
        self.source = OfficialSource()
        with self.store.transaction():
            for record in self.store.list('model-download'):
                if record['state'] in ACTIVE:
                    record.update(state='failed', cancel_requested=False, error={'code': 'MODEL_DOWNLOAD_INTERRUPTED', 'message': '上次下载中断，已下载文件保留。请明确继续下载。'}, updated_at=now())
                    self.store.put('model-download', record)

    def catalog(self):
        return {'id': CATALOG_ID, 'name': MODEL_NAME, 'repo': REPO, 'revision': REVISION, 'source_url': f'https://huggingface.co/{REPO}/tree/{REVISION}',
                'license': 'Apache-2.0', 'files': FILES, 'manifest_digest': digest(FILES), 'total_bytes': sum(item['size'] for item in FILES),
                'loader': 'safetensors', 'execution_boundary': restricted_execution_boundary(), 'network_scope': '只向固定官方模型来源请求这 9 个公开文件，不发送项目名、提示词或本机路径。',
                'capability': '本机 Apple Silicon / MLX；文本生成与 SFT + LoRA。下载与文件完整不代表质量通过。'}

    def get(self, download_id):
        return self.store.get('model-download', download_id)

    def start(self, payload, key):
        scope = 'model-download-start'
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return self.get(previous['id'])
            self.store.get('project', payload['project_id'])
            if payload['catalog_id'] != CATALOG_ID or payload['manifest_digest'] != digest(FILES):
                raise Fault('MODEL_CATALOG_CHANGED', '模型来源或文件版本已变化，请重新查看清单。', 409)
            self._ready()
            total = sum(item['size'] for item in FILES)
            if shutil.disk_usage(self.root).free < total * 2 + 64 * 1024 * 1024:
                raise Fault('DISK_FULL', '模型下载和独立登记约需 2 GiB 空间，请先准备空间。', 409)
            active = [item for item in self.store.list('model-download') if item['state'] in ACTIVE]
            if active:
                raise Fault('MODEL_DOWNLOAD_BUSY', '已有模型正在下载，请从模型库查看进度。', 409, download_id=active[0]['id'])
            record = self.service.resource('model-download', payload['project_id'], name=MODEL_NAME, catalog_id=CATALOG_ID, manifest=FILES, manifest_digest=digest(FILES), repo=REPO, revision=REVISION,
                                           state='queued', received_bytes=0, total_bytes=total, current_file=None, cancel_requested=False, model_id=None, error=None)
            self.store.put('model-download', record)
            self.store.remember(scope, key, payload, record)
            self._schedule(record)
            return record

    def _ready(self):
        if self.service.closed.is_set():
            raise Fault('SERVICE_STOPPING', '控制服务正在关闭，未开始新的下载。', 503)

    def resume(self, download_id, key):
        scope, payload = 'model-download-resume:' + download_id, {}
        with self.store.transaction():
            if self.store.replay(scope, key, payload):
                return self.get(download_id)
            self._ready()
            record = self.get(download_id)
            if record['state'] not in {'failed', 'cancelled'} or any(item['state'] in ACTIVE for item in self.store.list('model-download')):
                raise Fault('MODEL_DOWNLOAD_BUSY', '当前下载尚未停止或已经完成，请刷新状态。', 409)
            if any(thread.name == 'model-download-' + download_id for thread in self.service.threads):
                raise Fault('MODEL_DOWNLOAD_BUSY', '原下载正在释放资源，请稍后继续。', 409)
            record.update(state='queued', cancel_requested=False, error=None, updated_at=now())
            self.store.put('model-download', record)
            self.store.remember(scope, key, payload, record)
            self._schedule(record)
            return record

    def _schedule(self, record):
        thread = threading.Thread(target=self._execute, args=(record['id'],), daemon=True, name='model-download-' + record['id'])
        self.service.threads.add(thread)
        try:
            thread.start()
        except Exception:
            self.service.threads.discard(thread)
            record.update(state='failed', error={'code': 'MODEL_DOWNLOAD_START_FAILED', 'message': '下载进程未启动，记录已保存，请明确继续下载。'}, updated_at=now())
            self.store.put('model-download', record)
            # 外层事务保存命令和失败记录；抛异常会同时回滚，使重试失去身份。

    def cancel(self, download_id, key):
        scope, payload = 'model-download-cancel:' + download_id, {}
        with self.store.transaction():
            if self.store.replay(scope, key, payload):
                return self.get(download_id)
            record = self.get(download_id)
            if record['state'] == 'completed':
                raise Fault('MODEL_DOWNLOAD_COMPLETE', '文件已完整下载，无需取消。', 409)
            record.update(cancel_requested=True, updated_at=now())
            if record['state'] not in ACTIVE:
                record['state'] = 'cancelled'
            self.store.put('model-download', record)
            self.store.remember(scope, key, payload, record)
            return record

    def _check_cancel(self, download_id):
        if self.service.closed.is_set() or self.get(download_id)['cancel_requested']:
            raise Fault('MODEL_DOWNLOAD_CANCELLED', '下载已停止，已下载部分保留，可稍后继续。', 409)

    def _progress(self, download_id, files_root, **fields):
        total = 0
        for item in FILES:
            path = files_root / item['path']
            if path.exists() or path.is_symlink():
                path = regular_path(path)
                if not path.is_file():
                    raise Fault('MODEL_DOWNLOAD_PATH_CHANGED', '下载文件路径无效。', 409)
                total += path.stat().st_size
        with self.store.transaction():
            record = self.get(download_id)
            record.update(received_bytes=total, updated_at=now(), **fields)
            self.store.put('model-download', record)

    def _execute(self, download_id):
        try:
            self._check_cancel(download_id)
            record = self.get(download_id)
            if record['manifest_digest'] != digest(FILES) or record['manifest'] != FILES:
                raise Fault('MODEL_CATALOG_CHANGED', '固定模型版本不符。', 409)
            files_root = child_directory(self.root, download_id, 'files')
            if any(path.name not in {item['path'] for item in FILES} for path in files_root.iterdir()):
                raise Fault('MODEL_DOWNLOAD_PATH_CHANGED', '下载目录出现清单外文件，未继续写入。', 409)
            self._progress(download_id, files_root, state='downloading')
            for item in FILES:
                self._check_cancel(download_id)
                path = files_root / item['path']
                offset = 0
                if path.exists() or path.is_symlink():
                    actual = regular_path(path)
                    if not actual.is_file():
                        raise Fault('MODEL_DOWNLOAD_PATH_CHANGED', '下载目标不是普通文件。', 409)
                    offset = actual.stat().st_size
                    if offset >= item['size']:
                        if offset == item['size'] and file_hash(actual) == item['sha256']:
                            continue
                        # 仅重置本次下载清单内不合格的临时文件；已登记资产另存。
                        with actual.open('wb'):
                            pass
                        offset = 0
                if shutil.disk_usage(files_root).free < item['size'] - offset + 32 * 1024 * 1024:
                    raise Fault('DISK_FULL', '模型下载空间不足，已下载部分保留。', 409)
                self._progress(download_id, files_root, current_file=item['path'])
                while offset < item['size']:
                    self._check_cancel(download_id)
                    end = min(offset + SEGMENT_BYTES, item['size']) - 1
                    with self.source.open(item['path'], offset, end) as response:
                        status = response.status
                        if response.headers.get('Content-Encoding', 'identity') != 'identity':
                            raise Fault('MODEL_DOWNLOAD_RANGE_INVALID', '下载响应编码不符。', 409)
                        if status == 206:
                            match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                            if not match or tuple(map(int, match.groups())) != (offset, end, item['size']):
                                raise Fault('MODEL_DOWNLOAD_RANGE_INVALID', '续传范围与固定文件不符，原字节保留。', 409)
                        elif status == 200:
                            # 提供方不支持 Range 时，先确认整文件长度再重置临时文件。
                            offset, end = 0, item['size'] - 1
                        else:
                            raise Fault('MODEL_DOWNLOAD_RESPONSE_INVALID', '官方来源未返回文件内容。', 409)
                        if response.headers.get('Content-Length') != str(end - offset + 1):
                            raise Fault('MODEL_DOWNLOAD_RANGE_INVALID', '下载长度与固定清单不符。', 409)
                        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if offset else os.O_TRUNC)
                        with os.fdopen(os.open(path, flags, 0o600), 'ab' if offset else 'wb') as stream:
                            received = offset
                            while True:
                                self._check_cancel(download_id)
                                block = response.read(min(1024 * 1024, end - received + 2))
                                if not block:
                                    break
                                if received + len(block) > end + 1:
                                    raise Fault('MODEL_DOWNLOAD_RESPONSE_INVALID', '下载响应超过本段固定大小。', 409)
                                stream.write(block); stream.flush(); received += len(block)
                                self._progress(download_id, files_root)
                            os.fsync(stream.fileno())
                        if received != end + 1:
                            raise Fault('MODEL_DOWNLOAD_RESPONSE_INVALID', '本段下载中断，已下载部分保留，请明确继续下载。', 409)
                        offset = received
                if path.stat().st_size != item['size'] or file_hash(path) != item['sha256']:
                    raise Fault('MODEL_DOWNLOAD_HASH_MISMATCH', '文件未完整或摘要不符，未登记模型；可明确重试。', 409)
            self._check_cancel(download_id)
            self._progress(download_id, files_root, state='verifying', current_file=None)
            verify_manifest(files_root, FILES)
            report = model_manifest(files_root)
            if report['manifest_digest'] != digest(FILES):
                raise Fault('MODEL_DOWNLOAD_HASH_MISMATCH', '模型结构与固定清单不符，未登记。', 409)
            self._check_cancel(download_id)
            with self.store.transaction():
                self._check_cancel(download_id)
                record = self.get(download_id)
                record.update(state='completed', received_bytes=record['total_bytes'], error=None, current_file=None, updated_at=now())
                self.store.put('model-download', record)
        except Exception as error:
            with self.store.transaction():
                record = self.get(download_id)
                cancelled = self.service.closed.is_set() or record['cancel_requested'] or isinstance(error, Fault) and error.code == 'MODEL_DOWNLOAD_CANCELLED'
                record.update(state='cancelled' if cancelled else 'failed', error={'code': 'MODEL_DOWNLOAD_CANCELLED' if cancelled else error.code if isinstance(error, Fault) else 'MODEL_SOURCE_UNAVAILABLE',
                    'message': '下载已停止，已下载部分保留。' if cancelled else error.message if isinstance(error, Fault) else '官方来源暂时不可用或连接中断，已下载部分保留，请稍后继续。'}, updated_at=now())
                self.store.put('model-download', record)
        finally:
            with self.store.lock:
                self.service.threads.discard(threading.current_thread())
            self.service._release_if_idle()

    def register(self, download_id, key):
        scope, payload = 'model-download-register:' + download_id, {}
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            record = self.get(download_id)
            if record.get('model_id'):
                result = self.service.public(self.store.get('model', record['model_id']))
                self.store.remember(scope, key, payload, result)
                return result
            if record['state'] != 'completed' or record['manifest_digest'] != digest(FILES):
                raise Fault('MODEL_DOWNLOAD_INCOMPLETE', '请先完成下载和文件校验，再登记模型。', 409)
        source = regular_path(self.root / download_id / 'files')
        verify_manifest(source, FILES)
        report = model_manifest(source)
        if report['manifest_digest'] != digest(FILES):
            raise Fault('MODEL_DOWNLOAD_HASH_MISMATCH', '下载文件已变化，未登记模型。', 409)
        destination = copy_asset(source, self.service.root / 'assets', FILES, digest(FILES))
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            current = self.get(download_id)
            if current.get('model_id'):
                result = self.service.public(self.store.get('model', current['model_id']))
                self.store.remember(scope, key, payload, result)
                return result
            if current != record:
                raise Fault('MODEL_DOWNLOAD_CHANGED', '下载记录已变化，请刷新后登记。', 409)
            plan = self.service.resource('import-plan', record['project_id'], kind='model', name=MODEL_NAME, path=str(source), source_path=str(source), grant_id=None, can_import=True, issues=[], **report)
            model = self.service.resource('model', record['project_id'], name=MODEL_NAME, revision=1, version_id=identifier('version'), status='ready', manifest=FILES, manifest_digest=digest(FILES), total_bytes=record['total_bytes'], storage_path=str(destination),
                format=report['detected_format'], family=report['family'], model_config=report['model_config'], modality='text', load_policy_ref=plan['id'], loader=report['loader'], trust_class=report['trust_class'], execution_scope=report['execution_scope'], execution_boundary=report['execution_boundary'],
                provenance={'source': 'official_download', 'repo': REPO, 'revision': REVISION, 'source_url': self.catalog()['source_url'], 'manifest_digest': digest(FILES)}, default_engine='mlx')
            self.store.put('import-plan', plan); self.store.put('model', model)
            current.update(model_id=model['id'], updated_at=now()); self.store.put('model-download', current)
            result = self.service.public(model)
            self.store.remember(scope, key, payload, result)
            return result
