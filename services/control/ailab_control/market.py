"""受控 loopback 数据来源合同；审批来自提供方，下载不会自动修改训练草稿。"""

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from .assets import copy_asset, dataset_report, file_hash, regular_path, verify_manifest
from .media_assets import image_dataset_report
from .storage import Fault, digest, identifier, now

LABEL = '受控测试来源'
ACCESS = {'waiting', 'approved', 'denied', 'expired', 'revoked'}
TERMINAL = {'succeeded', 'failed', 'cancelled'}
SCHEMAS = {'sft': 'text', 'image_caption_v1': 'image'}
MAX_BYTES = 256 * 1024 * 1024


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        raise Fault('INVALID_MARKET_INPUT', '市场请求字段不完整或包含未支持字段。')


def text(value, maximum=2000, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise Fault('INVALID_MARKET_INPUT', '市场字段必须为长度有效的文本。')
    return value


def token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise Fault('INVALID_MARKET_INPUT', '来源、数据和版本编号只接受简短固定标识。')
    return value


def relative(value):
    if not isinstance(value, str) or len(value) > 240 or '\\' in value or not value or any(part in {'', '.', '..'} for part in value.split('/')) or Path(value).is_absolute():
        raise Fault('INVALID_MARKET_INPUT', '数据文件路径必须为来源目录内的规范相对路径。')
    return value


def directory(root, parts=()):
    """逐层检查后建目录，不能经现有符号链接在工作区外写入。"""
    regular_path(root)
    current = root
    for part in parts:
        current = current / part
        if current.exists() or current.is_symlink():
            regular_path(current)
            if not current.is_dir():
                raise Fault('PATH_NOT_ALLOWED', '下载位置已有非目录文件。', 409)
        else:
            current.mkdir(mode=0o700)
    return current


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Fault('MARKET_REDIRECT_FORBIDDEN', '受控来源不允许跳转到其他地址。', 409)


class LoopbackProvider:
    """只能由本地配置登记；请求负载没有提供方 URL 字段。"""

    def __init__(self, provider_id, origin):
        self.id = token(provider_id)
        try:
            parsed = urllib.parse.urlsplit(origin)
            valid = parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and not (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment) and parsed.port and origin == f'http://127.0.0.1:{parsed.port}'
        except (ValueError, AttributeError, TypeError):
            valid = False
        if not valid:
            raise Fault('MARKET_SOURCE_NOT_ALLOWED', '首期来源只允许已登记的固定 127.0.0.1 端口，不接受任意 URL。', 403)
        self.origin = origin
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def open(self, path, payload=None, headers=None):
        if not path.startswith('/v1/') or path.startswith('//'):
            raise Fault('MARKET_SOURCE_NOT_ALLOWED', '提供方协议路径不受支持。', 403)
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        request = urllib.request.Request(self.origin + path, data=body, headers={**({'Content-Type': 'application/json'} if body is not None else {}), **(headers or {})})
        try:
            return self.opener.open(request, timeout=10)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise Fault('MARKET_PROVIDER_UNAVAILABLE', '受控提供方请求未完成。', 503, reason=type(error).__name__) from None

    def json(self, path, payload=None):
        with self.open(path, payload) as response:
            body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise Fault('MARKET_PROVIDER_INVALID', '提供方元数据超过 2 MiB。', 409)
        try:
            def unique(pairs):
                result = {}
                for name, value in pairs:
                    if name in result:
                        raise ValueError('重复字段')
                    result[name] = value
                return result
            return json.loads(body, object_pairs_hook=unique, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (UnicodeError, ValueError, RecursionError):
            raise Fault('MARKET_PROVIDER_INVALID', '提供方未返回有效且字段唯一的 JSON。', 409) from None


class Market:
    def __init__(self, service, providers):
        self.service, self.store = service, service.store
        self.providers = {provider.id: provider for provider in providers}
        if len(self.providers) != len(providers):
            raise Fault('MARKET_SOURCE_NOT_ALLOWED', '提供方编号重复。')
        self.root = directory(service.root, ['market-downloads'])
        # 同一控制存储中的多个门面仍共享进程内下载互斥锁。
        with self.store.lock:
            if not hasattr(self.store, 'market_download_locks'):
                self.store.market_download_locks = {}
        with self.store.transaction():
            for record in self.store.list('market-download'):
                active_lock = self.store.market_download_locks.get(record['id'])
                if record['state'] in {'queued', 'downloading'} and not (active_lock and active_lock.locked()):
                    error = {'code': 'MARKET_DOWNLOAD_INTERRUPTED', 'message': '控制服务曾中断；原字节保留，请明确选择继续下载。'}
                    record['history'].append({'finished_at': now(), 'state': 'failed', 'received_bytes': record['received_bytes'], 'error': error})
                    record.update(state='failed', complete=False, cancel_requested=False, active_execution_key=None, error=error, updated_at=now())
                    self.store.put('market-download', record)

    def _provider(self, provider_id):
        if provider_id not in self.providers:
            raise Fault('MARKET_SOURCE_NOT_ALLOWED', '此来源没有在本次本地配置中登记。', 403)
        return self.providers[provider_id]

    def sources(self):
        return [{'provider_id': item.id, 'origin': item.origin, 'source_label': LABEL, 'schemas': list(SCHEMAS), 'operations': ['browse', 'request_access', 'refresh_access', 'download', 'resume_download']} for item in self.providers.values()]

    def activity(self, version_id):
        version = self._version(version_id)
        project = version['project_id']
        return {'access_requests': [item for item in self.store.list('market-access', project) if item['version_id'] == version_id],
                'downloads': [item for item in self.store.list('market-download', project) if item['version_id'] == version_id],
                'datasets': [self.service.public(item) for item in self.store.list('dataset', project) if item.get('market_provenance', {}).get('market_version_id') == version_id]}

    def _version(self, version_id):
        version = self.store.get('market-version', version_id)
        if digest(version['metadata']) != version['version_digest']:
            raise Fault('MARKET_VERSION_CHANGED', '本地数据版本记录与原摘要不符。', 409)
        if self._provider(version['provider_id']).origin != version['provider_origin']:
            raise Fault('MARKET_SOURCE_CHANGED', '来源地址与已冻结的数据版本不同。', 409)
        return version

    def _entry(self, value):
        fields(value, ('dataset_key', 'version', 'name', 'description', 'modality', 'schema', 'sample_count', 'total_bytes', 'format', 'provider_text', 'source_url', 'updated_at', 'access', 'license', 'files'))
        for name in ('dataset_key', 'version'):
            token(value[name])
        for name in ('name', 'description', 'format', 'provider_text'):
            text(value[name], 20000, empty=name in {'description', 'provider_text'})
        for name in ('source_url', 'updated_at'):
            if value[name] is not None:
                text(value[name], 2000)
        if not isinstance(value['schema'], str) or value['schema'] not in SCHEMAS or SCHEMAS[value['schema']] != value['modality'] or value['access'] not in ('open', 'restricted'):
            raise Fault('MARKET_SCHEMA_UNSUPPORTED', '当前来源仅支持文本 SFT 与图片描述数据。')
        if value['sample_count'] is not None and (type(value['sample_count']) is not int or value['sample_count'] < 1):
            raise Fault('INVALID_MARKET_INPUT', '未知样本数应留空，已知样本数必须为正整数。')
        if value['license'] is not None:
            fields(value['license'], ('reference', 'provider_text'))
            for item in value['license'].values():
                if item is not None:
                    text(item, 20000, empty=True)
        files = value['files']
        if not isinstance(files, list) or not 1 <= len(files) <= 1000:
            raise Fault('INVALID_MARKET_INPUT', '数据版本需要 1 至 1000 个文件。')
        for item in files:
            fields(item, ('path', 'size', 'sha256'))
            relative(item['path'])
            if type(item['size']) is not int or not 1 <= item['size'] <= MAX_BYTES or not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
                raise Fault('INVALID_MARKET_INPUT', '文件大小或 SHA256 无效。')
        if files != sorted(files, key=lambda item: item['path']) or len({item['path'] for item in files}) != len(files) or type(value['total_bytes']) is not int or value['total_bytes'] != sum(item['size'] for item in files) or value['total_bytes'] > MAX_BYTES:
            raise Fault('INVALID_MARKET_INPUT', '文件清单需唯一排序，总大小必须准确且不超过 256 MiB。')
        if value['schema'] == 'sft' and (len(files) != 1 or not files[0]['path'].endswith('.jsonl') or '/' in files[0]['path']):
            raise Fault('MARKET_SCHEMA_UNSUPPORTED', '文本版本需要单个 JSONL 文件。')
        return copy.deepcopy(value)

    def browse(self, project_id, provider_id):
        self.store.get('project', project_id)
        provider = self._provider(provider_id)
        catalog = provider.json('/v1/catalog')
        fields(catalog, ('schema_version', 'provider_id', 'catalog_version', 'versions'))
        if catalog['schema_version'] != 'market-catalog-v1' or catalog['provider_id'] != provider.id or not isinstance(catalog['versions'], list) or len(catalog['versions']) > 100:
            raise Fault('MARKET_PROVIDER_INVALID', '目录协议、提供方身份或版本数不符。', 409)
        token(catalog['catalog_version'])
        entries = [self._entry(value) for value in catalog['versions']]
        if len({(item['dataset_key'], item['version']) for item in entries}) != len(entries):
            raise Fault('MARKET_PROVIDER_INVALID', '目录包含重复的数据版本。', 409)
        with self.store.transaction():
            existing = self.store.list('market-version')
            result = []
            for entry in entries:
                identities = [item for item in existing if (item['provider_id'], item['metadata']['dataset_key'], item['metadata']['version']) == (provider_id, entry['dataset_key'], entry['version'])]
                if any(item['version_digest'] != digest(entry) or item['provider_origin'] != provider.origin for item in identities):
                    raise Fault('MARKET_VERSION_CHANGED', '提供方改写了已有版本，请使用新的版本编号。', 409)
                previous = next((item for item in identities if item['project_id'] == project_id), None)
                if previous:
                    result.append(previous)
                else:
                    version = self.service.resource('market-version', project_id, provider_id=provider_id, provider_origin=provider.origin, source_label=LABEL, metadata=entry, version_digest=digest(entry), catalog_version=catalog['catalog_version'], catalog_digest=digest(catalog), legal_assessment=None)
                    self.store.put('market-version', version)
                    result.append(version)
            catalogs = [item for item in self.store.list('market-catalog') if item['provider_id'] == provider_id and item['catalog_version'] == catalog['catalog_version']]
            if any(item['catalog_digest'] != digest(catalog) or item['provider_origin'] != provider.origin for item in catalogs):
                raise Fault('MARKET_CATALOG_CHANGED', '提供方改写了同一目录版本。', 409)
            previous_catalog = next((item for item in catalogs if item['project_id'] == project_id), None)
            if not previous_catalog:
                frozen_catalog = self.service.resource('market-catalog', project_id, provider_id=provider_id, provider_origin=provider.origin, catalog_version=catalog['catalog_version'], catalog_digest=digest(catalog), raw_catalog=catalog, source_label=LABEL)
                self.store.put('market-catalog', frozen_catalog)
            return {'source_label': LABEL, 'provider_id': provider_id, 'catalog_version': catalog['catalog_version'], 'catalog_digest': digest(catalog), 'versions': result}

    def _access_response(self, version, response, request_id=None):
        fields(response, ('provider_id', 'dataset_key', 'version', 'version_digest', 'request_id', 'status', 'provider_text', 'updated_at', 'expires_at', 'revision'))
        expected = {'provider_id': version['provider_id'], 'dataset_key': version['metadata']['dataset_key'], 'version': version['metadata']['version'], 'version_digest': version['version_digest']}
        if any(response[name] != value for name, value in expected.items()) or not isinstance(response['status'], str) or response['status'] not in ACCESS or (request_id and response['request_id'] != request_id):
            raise Fault('MARKET_ACCESS_MISMATCH', '提供方审批不属于此申请或数据版本。', 409)
        token(response['request_id'])
        if type(response['revision']) is not int or response['revision'] < 1:
            raise Fault('MARKET_PROVIDER_INVALID', '提供方审批缺少有效的单调版本号。', 409)
        text(response['provider_text'], 20000, empty=True)
        text(response['updated_at'])
        if response['expires_at'] is not None:
            try:
                expires = datetime.fromisoformat(response['expires_at'])
                if expires.tzinfo is None:
                    raise ValueError('缺少时区')
            except (TypeError, ValueError):
                raise Fault('MARKET_PROVIDER_INVALID', '审批有效期必须包含时区。', 409) from None
        return copy.deepcopy(response)

    def request_access(self, version_id, payload, key):
        fields(payload, ('purpose', 'user_statement'))
        for value in payload.values():
            text(value)
        scope = 'market-access:' + version_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            version = self._version(version_id)
            if version['metadata']['access'] != 'restricted':
                raise Fault('MARKET_ACCESS_NOT_REQUIRED', '此版本开放下载，不需要申请。')
        sent = {'provider_id': version['provider_id'], 'dataset_key': version['metadata']['dataset_key'], 'version': version['metadata']['version'], 'version_digest': version['version_digest'], **payload, 'request_key': digest({'project_id': version['project_id'], 'version_id': version_id, 'key': key})}
        response = self._access_response(version, self._provider(version['provider_id']).json('/v1/access', sent))
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            result = self.service.resource('market-access', version['project_id'], version_id=version_id, sent=sent, provider_response=response, response_history=[{'received_at': now(), 'response': response}], source_label=LABEL, legal_assessment=None)
            self.store.put('market-access', result)
            self.store.remember(scope, key, payload, result)
            return result

    def refresh_access(self, access_id):
        access = self.store.get('market-access', access_id)
        version = self._version(access['version_id'])
        provider_id = access['provider_response']['request_id']
        response = self._access_response(version, self._provider(version['provider_id']).json('/v1/access/' + provider_id), provider_id)
        with self.store.transaction():
            current = self.store.get('market-access', access_id)
            old = current['provider_response']
            if response['revision'] < old['revision'] or (response['revision'] == old['revision'] and response != old):
                raise Fault('MARKET_ACCESS_STALE', '提供方返回了旧审批或改写了同一审批版本。', 409)
            if response != current['provider_response']:
                current['response_history'].append({'received_at': now(), 'response': response})
                current.update(provider_response=response, updated_at=now())
                self.store.put('market-access', current)
            return current

    def _allowed(self, version, access_id):
        if version['metadata']['access'] == 'open':
            if access_id:
                raise Fault('MARKET_ACCESS_MISMATCH', '开放下载不接受额外审批编号。')
            return None
        if not access_id:
            raise Fault('MARKET_ACCESS_REQUIRED', '此版本需要提供方批准后下载。', 409)
        access = self.store.get('market-access', access_id)
        if access['version_id'] != version['id']:
            raise Fault('MARKET_ACCESS_MISMATCH', '审批属于其他数据版本。', 409)
        access = self.refresh_access(access_id)
        response = access['provider_response']
        expired = response['expires_at'] and datetime.fromisoformat(response['expires_at']) <= datetime.now(timezone.utc)
        if response['status'] != 'approved' or expired:
            raise Fault('MARKET_ACCESS_NOT_GRANTED', '提供方尚未批准，或访问已到期／撤销。', 409, provider_status=response['status'], expires_at=response['expires_at'])
        return copy.deepcopy(response)

    def start_download(self, version_id, payload, key):
        fields(payload, ('user_statement',), ('access_id',))
        text(payload['user_statement'])
        scope = 'market-download:' + version_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.service.closed.is_set():
                raise Fault('SERVICE_STOPPING', '控制服务正在关闭，未开始下载。', 503)
            version = self._version(version_id)
        self._allowed(version, payload.get('access_id'))
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.service.closed.is_set():
                raise Fault('SERVICE_STOPPING', '访问检查期间控制服务开始关闭，未创建下载。', 503)
            result = self.service.resource('market-download', version['project_id'], version_id=version_id, version_digest=version['version_digest'], access_id=payload.get('access_id'), user_statement=payload['user_statement'], state='queued', received_bytes=0, complete=False, cancel_requested=False, dataset_id=None, history=[], source_label=LABEL)
            self.store.put('market-download', result)
            self.store.remember(scope, key, payload, result)
            return result

    def cancel_download(self, download_id, key):
        scope, payload = 'market-cancel:' + download_id, {}
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            result = self.store.get('market-download', download_id)
            if result['state'] == 'completed':
                raise Fault('MARKET_DOWNLOAD_COMPLETE', '已完成下载无需取消。', 409)
            result.update(cancel_requested=True, state='cancelled' if result['state'] != 'downloading' else 'downloading', updated_at=now())
            self.store.put('market-download', result)
            self.store.remember(scope, key, payload, result)
            return result

    def execute_download(self, download_id, key, preserve_cancellation=False):
        """可在后台线程执行；同一下载只运行一次，取消与失败保留字节。"""
        scope, payload = 'market-execute:' + download_id, {}
        with self.store.lock:
            lock = self.store.market_download_locks.setdefault(download_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise Fault('MARKET_DOWNLOAD_BUSY', '此下载仍在运行。', 409)
        try:
            with self.store.transaction():
                if previous := self.store.replay(scope, key, payload):
                    return previous
                record = self.store.get('market-download', download_id)
                if record['state'] == 'completed':
                    raise Fault('MARKET_DOWNLOAD_COMPLETE', '下载已完成，请直接登记数据。', 409)
                if self.service.closed.is_set() or (preserve_cancellation and record['cancel_requested']):
                    record.update(state='cancelled', complete=False, error={'code': 'MARKET_DOWNLOAD_CANCELLED', 'message': '下载开始前已取消或控制服务正在关闭，原字节保留。'}, updated_at=now())
                    self.store.put('market-download', record)
                    self.store.remember(scope, key, payload, record)
                    return record
                version = self._version(record['version_id'])
                record.update(state='downloading', cancel_requested=False, complete=False, error=None, updated_at=now())
                self.store.put('market-download', record)
            files_root = self.root / download_id / 'files'
            provider_access, provider_finish = None, None
            try:
                directory(self.root, [download_id, 'files'])
                catalog = self.browse(version['project_id'], version['provider_id'])
                if not any(item['id'] == version['id'] for item in catalog['versions']):
                    raise Fault('MARKET_VERSION_UNAVAILABLE', '提供方当前目录已不再提供此版本。', 409)
                provider_access = self._allowed(version, record['access_id'])
                provider = self._provider(version['provider_id'])
                for item in version['metadata']['files']:
                    path = files_root / item['path']
                    directory(files_root, Path(item['path']).parts[:-1])
                    if path.exists() or path.is_symlink():
                        regular_path(path)
                    offset = path.stat().st_size if path.exists() else 0
                    if offset == item['size'] and file_hash(path) == item['sha256']:
                        continue
                    if offset >= item['size']:
                        raise Fault('MARKET_HASH_MISMATCH', '部分文件摘要错误；保留原字节，请创建新下载。', 409)
                    endpoint = '/v1/files/' + '/'.join(urllib.parse.quote(part, safe='') for part in (version['metadata']['dataset_key'], version['metadata']['version'], *item['path'].split('/')))
                    if provider_access:
                        endpoint += '?access_id=' + urllib.parse.quote(provider_access['request_id'], safe='')
                    with provider.open(endpoint, headers={'Range': f'bytes={offset}-'}) as response:
                        expected_range = f'bytes {offset}-{item["size"] - 1}/{item["size"]}'
                        if response.status != 206 or response.headers.get('Content-Range') != expected_range or response.headers.get('Content-Length') != str(item['size'] - offset):
                            raise Fault('MARKET_RANGE_MISMATCH', '提供方未按已冻结大小返回精确续传范围。', 409)
                        with path.open('ab') as stream:
                            while True:
                                if self.service.closed.is_set() or self.store.get('market-download', download_id)['cancel_requested']:
                                    raise Fault('MARKET_DOWNLOAD_CANCELLED', '下载已取消，部分字节已保留。', 409)
                                chunk = response.read1(min(65536, item['size'] - stream.tell() + 1))
                                if not chunk:
                                    break
                                if stream.tell() + len(chunk) > item['size']:
                                    raise Fault('MARKET_RANGE_MISMATCH', '提供方发送的字节超过冻结大小。', 409)
                                stream.write(chunk)
                                stream.flush()
                                self._progress(download_id, files_root)
                            os.fsync(stream.fileno())
                    if path.stat().st_size != item['size'] or file_hash(path) != item['sha256']:
                        raise Fault('MARKET_HASH_MISMATCH', '下载字节不完整或 SHA256 不符，未登记数据。', 409)
                provider_finish = self._allowed(version, record['access_id'])
                verify_manifest(files_root, version['metadata']['files'])
                self._progress(download_id, files_root)
                outcome, error = 'completed', None
            except Exception as failure:
                outcome = 'cancelled' if isinstance(failure, Fault) and failure.code == 'MARKET_DOWNLOAD_CANCELLED' else 'failed'
                error = {'code': failure.code if isinstance(failure, Fault) else 'MARKET_TRANSFER_FAILED', 'message': str(failure)[:1000]}
            with self.store.transaction():
                record = self.store.get('market-download', download_id)
                if self.service.closed.is_set() or record['cancel_requested']:
                    outcome, error = 'cancelled', {'code': 'MARKET_DOWNLOAD_CANCELLED', 'message': '下载已取消，部分字节已保留。'}
                record['history'].append({'finished_at': now(), 'state': outcome, 'received_bytes': record['received_bytes'], 'error': error, 'provider_response_at_start': provider_access, 'provider_response_at_finish': provider_finish})
                record.update(state=outcome, complete=outcome == 'completed', error=error, updated_at=now())
                self.store.put('market-download', record)
                self.store.remember(scope, key, payload, record)
                return record
        finally:
            lock.release()

    def _progress(self, download_id, directory):
        received = sum(path.stat().st_size for path in directory.rglob('*') if path.is_file())
        with self.store.transaction():
            value = self.store.get('market-download', download_id)
            value.update(received_bytes=received, updated_at=now())
            self.store.put('market-download', value)

    def register_new_dataset(self, download_id, key):
        scope, payload = 'market-register:' + download_id, {}
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            download = self.store.get('market-download', download_id)
            if not download['complete'] or download['state'] != 'completed':
                raise Fault('MARKET_DOWNLOAD_INCOMPLETE', '只有完整且哈希通过的下载可登记。', 409)
            if download['dataset_id']:
                return self.store.get('dataset', download['dataset_id'])
            version = self._version(download['version_id'])
        metadata = version['metadata']
        source = self.root / download_id / 'files'
        verify_manifest(source, metadata['files'])
        if metadata['schema'] == 'image_caption_v1':
            report = image_dataset_report(source)
        else:
            report = dataset_report(source / metadata['files'][0]['path'], 'sft')
            report.update(manifest=metadata['files'], manifest_digest=digest(metadata['files']), entrypoint=metadata['files'][0]['path'])
        if not report['can_import'] or report['manifest'] != metadata['files'] or (metadata['sample_count'] is not None and metadata['sample_count'] != report['sample_count']):
            raise Fault('DATA_SCHEMA_MISMATCH', '下载字节通过，但数据结构、文件集合或样本数不符合版本声明。', 409, report=report)
        destination = copy_asset(source, self.service.root / 'assets', report['manifest'], report['manifest_digest'])
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            download = self.store.get('market-download', download_id)
            if download['dataset_id']:
                result = self.store.get('dataset', download['dataset_id'])
            else:
                verify_manifest(destination, report['manifest'])
                result = self.service.resource('dataset', version['project_id'], name=metadata['name'], revision=1, version_id=identifier('version'), status='ready', manifest=report['manifest'], manifest_digest=report['manifest_digest'], total_bytes=report['total_bytes'], storage_path=str(destination), schema=report['schema'], sample_count=report['sample_count'], sha256=report['sha256'], checks=report['checks'], entrypoint=report.get('entrypoint', 'dataset.json'), market_provenance={'source_label': LABEL, 'provider_id': version['provider_id'], 'market_version_id': version['id'], 'version_digest': version['version_digest'], 'download_id': download_id, 'access_id': download['access_id'], 'metadata': metadata, 'user_statement': download['user_statement'], 'legal_assessment': None})
                self.store.put('dataset', result)
                download['dataset_id'] = result['id']
                self.store.put('market-download', download)
            self.store.remember(scope, key, payload, result)
            return result

    def enter(self, task_id, payload, key):
        fields(payload, ('expected_revision', 'step'))
        if payload['step'] != 'data':
            raise Fault('INVALID_MARKET_INPUT', '当前市场入口来自训练数据步骤。')
        scope = 'market-context:' + task_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            task = self.store.get('task', task_id)
            self._task(task, payload['expected_revision'])
            context = self.service.resource('market-context', task['project_id'], task_id=task_id, kind=task['kind'], step='data', draft_revision=task['draft_revision'], draft_snapshot=copy.deepcopy(task['draft']), task_name=task['name'])
            self.store.put('market-context', context)
            self.store.remember(scope, key, payload, context)
            return context

    def _task(self, task, revision):
        if task['operation'] != 'train' or task['kind'] not in {'text', 'image'} or task.get('immutable_draft') or task['draft'].get('checkpoint_id'):
            raise Fault('MARKET_TASK_UNSUPPORTED', '市场数据只能带回可编辑的文本或图片训练任务。', 409)
        if type(revision) is not int or task['draft_revision'] != revision:
            raise Fault('REVISION_CONFLICT', '原任务草稿已变化，数据已保留，请重新从原任务进入。', 409)
        if any(item.get('task_id') == task['id'] and (item.get('state') not in TERMINAL or item.get('recovery_required')) for item in self.store.list('attempt', task['project_id'])):
            raise Fault('MARKET_TASK_BUSY', '原任务仍在执行、暂停或等待进程恢复，草稿未改动。', 409)

    def use_for_task(self, context_id, payload, key):
        fields(payload, ('dataset_id',))
        scope = 'market-use:' + context_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            context = self.store.get('market-context', context_id)
            task = self.store.get('task', context['task_id'])
            self._task(task, context['draft_revision'])
            if task['draft'] != context['draft_snapshot']:
                raise Fault('REVISION_CONFLICT', '原任务输入与市场入口快照不符，草稿未改动。', 409)
            dataset = self.store.get('dataset', payload['dataset_id'])
            if dataset['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '下载数据不属于原任务项目。', 403)
            if dataset.get('schema') != ('sft' if task['kind'] == 'text' else 'image_caption_v1') or dataset.get('status') != 'ready' or not dataset.get('market_provenance'):
                raise Fault('DATA_SCHEMA_MISMATCH', '此市场数据格式不适合原训练任务。', 409)
            verify_manifest(Path(dataset['storage_path']), dataset['manifest'])
            task['draft']['dataset_id'] = dataset['id']
            task.update(draft_revision=task['draft_revision'] + 1, updated_at=now())
            self.store.put('task', task)
            result = {'task': task, 'return_to': {'project_id': task['project_id'], 'task_id': task['id'], 'kind': task['kind'], 'step': context['step'], 'highlight_dataset_id': dataset['id']}, 'previous_checks_invalidated': True}
            self.store.remember(scope, key, payload, result)
            return result
