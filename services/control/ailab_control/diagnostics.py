"""诊断只导出固定白名单摘要；不读取服务日志，不启动依赖探测或模型。"""

from collections import Counter
import errno
import hashlib
import io
import json
import os
import platform
import re
import shutil
import zipfile

from . import __version__, __build__, __version_label__
from .assets import regular_path
from .storage import Fault, digest, encode, identifier, now

SCHEMA = 'ailab-diagnostics-v1'
RECORD_SCOPE = 'diagnostic-preview-record'
MAX_BYTES = 256 * 1024
KINDS = ('task', 'attempt', 'model', 'dataset', 'adapter', 'material', 'work', 'work-revision', 'ai-request', 'ai-proposal', 'workflow', 'workflow-run')
STATES = {'queued', 'preparing', 'running', 'pausing', 'paused', 'resuming', 'cancelling', 'finalizing', 'succeeded', 'failed', 'cancelled'}
OUTCOMES = {'pending', 'succeeded', 'failed', 'cancelled', 'not_started', 'running', 'collecting'}
ERROR_CODES = frozenset('''ADAPTER_BASE_MISMATCH ADAPTER_PROVENANCE_MISMATCH ARTIFACT_CORRUPT BACKUP_FAILED CHECKPOINT_CHANGED
CHECKPOINT_CONFIG_CHANGED CHECKPOINT_CORRUPT CHECKPOINT_ENVIRONMENT_CHANGED CHECKPOINT_NOT_READY CHECKPOINT_SOURCE_ACTIVE
CLEANUP_IO_ERROR COLLECTION_CANCELLED COLLECTION_FAILED CONTROL_INTERRUPTED CONTROL_RESULT_UNKNOWN CONVERSION_OUTPUT_CHANGED
CONVERSION_SOURCE_CHANGED DATA_SCHEMA_MISMATCH DATA_DIRECTORY_BUSY DEVICE_BUSY DISK_FULL ENVIRONMENT_CHANGED EVALUATION_FAILED
EVALUATION_IDENTITY_MISMATCH EXECUTION_FAILED EXPORT_CANCELLED EXPORT_INCOMPLETE EXPORT_REGISTRATION_PENDING EXPORT_SOURCE_CHANGED
EXPORT_TARGET_EXISTS INFERENCE_IDENTITY_CHANGED INFERENCE_IDENTITY_REQUIRED INVALID_CONFIG INVALID_DATASET INVALID_PROMPT
INVALID_WORKER_EVENT LAUNCH_HANDSHAKE_FAILED MODEL_LOAD_FAILED MODEL_UNVERIFIED NO_TRAINABLE_DATA OUTPUT_EXISTS OUTPUT_SYMLINK
PREFLIGHT_FAILED RECIPE_CHANGED RESTORE_FAILED SERVICE_STOPPING SOURCE_CHANGED SOURCE_MODEL_CHANGED SOURCE_NOT_FOUND
TOKENIZATION_IDENTITY_CHANGED TOKENIZATION_IDENTITY_REQUIRED UNSUPPORTED_DEVICE UNSUPPORTED_PARAMETER WORKER_FAILED
CACHE_CONFIG_MISMATCH CACHE_NOT_EMPTY CACHE_NOT_POPULATED CONTEXT_TOO_LONG AI_RESPONSE_NOT_STRUCTURED AI_PROPOSAL_INVALID
AI_FIELD_NOT_ALLOWED AI_RESPONSE_SOURCE_MISMATCH MEDIA_EXECUTION_FAILED MEDIA_PREFLIGHT_FAILED MEDIA_IDENTITY_CHANGED
MEDIA_SOURCE_CHANGED TTS_FAILED PROCESS_IDENTITY_MISMATCH LAUNCH_AUTHORIZATION_FAILED'''.split())
PACKAGES = ('mlx', 'mlx-lm', 'transformers', 'tokenizers', 'numpy', 'safetensors', 'huggingface-hub', 'torch', 'diffusers',
            'accelerate', 'Pillow', 'peft', 'kokoro', 'misaki', 'soundfile', 'fastapi', 'uvicorn')
INCLUDED = ['应用与本机系统版本（不含主机名）', '项目范围内的资源数量、运行状态与已知错误代码计数',
            '最多 20 次指定运行的状态摘要', '已保存的依赖版本摘要；不重新探测环境',
            '本次控制服务会话最近 32 次环境探测的固定结果、耗时、退出码和完成时间',
            '最近 64 次环境调用的进程编号、锁等待与身份计算时刻、缓存结果；不含用户内容']
EXCLUDED = ['模型、数据集、图片、音频、视频与缓存内容', '提示词、生成结果、AI 问题、任务名称与项目名称',
            '个人文件路径、主机名、令牌、环境变量、授权信息', '服务日志、执行原始日志、错误正文与未知扩展字段']


def enum(value, choices):
    return value if type(value) is str and value in choices else 'unknown'


def version(value):
    # 只接受数字版本及明确的预发布后缀，不接受本地构建标签或自由文本。
    return value if type(value) is str and re.fullmatch(r'\d{1,4}(?:\.\d{1,4}){0,3}(?:(?:a|b|rc|\.post|\.dev)\d{1,4})?', value) else None


def dependency_summary(environment):
    if not isinstance(environment, dict):
        return None
    facts = environment.get('versions')
    if not isinstance(facts, dict):
        return None
    dependencies = facts.get('dependencies')
    if not isinstance(dependencies, dict):
        return None
    versions = {name: parsed for name in PACKAGES if (parsed := version(dependencies.get(name))) is not None}
    python = version(facts.get('python'))
    if not versions and python is None:
        return None
    result = {'engine': enum(environment.get('engine'), {'mlx', 'diffusers', 'kokoro'}),
              'device': enum(environment.get('device_id'), {'apple-gpu', 'cpu'}),
              'backend': enum(environment.get('execution_backend'), {'bundled', 'external_python'}),
              'ready': environment.get('ready') if type(environment.get('ready')) is bool else None,
              'python': python, 'packages': versions}
    return {**result, 'summary_sha256': digest(result)}


class Diagnostics:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def record(self, preview_id):
        if not isinstance(preview_id, str) or not re.fullmatch(r'diagnostic-preview-[0-9a-f]{32}', preview_id):
            raise Fault('DIAGNOSTICS_NOT_FOUND', '诊断预览不存在。', 404)
        with self.store.lock:
            row = self.store.db.execute('SELECT response FROM commands WHERE scope=? AND key=?', (RECORD_SCOPE, preview_id)).fetchone()
        if row is None:
            raise Fault('DIAGNOSTICS_NOT_FOUND', '诊断预览不存在。', 404)
        return json.loads(row[0])

    def put(self, record):
        self.store.db.execute('UPDATE commands SET response=? WHERE scope=? AND key=?', (encode(record), RECORD_SCOPE, record['id']))

    def public(self, record):
        result = {name: record[name] for name in ('id', 'status', 'created_at', 'scope', 'included', 'excluded', 'files', 'total_bytes', 'archive_bytes', 'archive_sha256', 'preview_digest')}
        result['preview_id'] = record['id']
        result['diagnostics'] = record['diagnostics']
        result['can_export'] = record['status'] == 'ready'
        result['can_cancel'] = record['status'] in {'ready', 'writing'}
        for name in ('export_id', 'finished_at', 'error', 'file_name'):
            if name in record:
                result[name] = record[name]
        if record['status'] in {'succeeded', 'registration_pending'}:
            result['saved_path'] = record['final_path']
        return result

    def summary(self, project_id, attempt_ids):
        where, args = (' AND project_id=?', [project_id]) if project_id else ('', [])
        counts = {name: 0 for name in KINDS}
        for kind, count in self.store.db.execute('SELECT kind,count(*) FROM resources WHERE 1=1' + where + ' GROUP BY kind', args):
            if kind in counts:
                counts[kind] = count
        states, errors = Counter(), Counter()
        unknown_errors = 0
        for state, code, count in self.store.db.execute("SELECT json_extract(body,'$.state'),json_extract(body,'$.terminal_reason'),count(*) FROM resources WHERE kind='attempt'" + where + " GROUP BY json_extract(body,'$.state'),json_extract(body,'$.terminal_reason')", args):
            states[enum(state, STATES)] += count
            if state == 'failed':
                if type(code) is str and code in ERROR_CODES:
                    errors[code] += count
                else:
                    unknown_errors += count
        selected = []
        for index, attempt_id in enumerate(attempt_ids, 1):
            row = self.store.db.execute("SELECT project_id,json_extract(body,'$.state'),json_extract(body,'$.snapshot.kind'),json_extract(body,'$.snapshot.operation'),json_extract(body,'$.compute_outcome'),json_extract(body,'$.collection_state'),json_extract(body,'$.terminal_reason') FROM resources WHERE kind='attempt' AND id=?", (attempt_id,)).fetchone()
            if row is None:
                raise Fault('RESOURCE_NOT_FOUND', '所选运行不存在。', 404)
            if project_id and row[0] != project_id:
                raise Fault('PROJECT_MISMATCH', '所选运行属于其他项目。', 403)
            selected.append({'selection_index': index, 'state': enum(row[1], STATES), 'kind': enum(row[2], {'text', 'image', 'video', 'audio', 'export'}),
                             'operation': enum(row[3], {'generate', 'train', 'evaluate', 'quantize', 'export'}),
                             'compute_outcome': enum(row[4], OUTCOMES), 'collection_state': enum(row[5], OUTCOMES),
                             'error_code': row[6] if row[1] == 'failed' and type(row[6]) is str and row[6] in ERROR_CODES else None})
        observations = []
        cache = self.service.environment_cache
        if isinstance(cache, tuple) and len(cache) == 2:
            observations.append(cache[1])
        observations.extend(list(self.service.media.cache.values()))
        query = "SELECT json_object('engine',json_extract(body,'$.snapshot.environment.engine'),'device_id',json_extract(body,'$.snapshot.environment.device_id'),'execution_backend',json_extract(body,'$.snapshot.environment.execution_backend'),'ready',json_extract(body,'$.snapshot.environment.ready'),'versions',json_extract(body,'$.snapshot.environment.versions')) FROM resources WHERE kind='attempt'" + where + ' ORDER BY rowid DESC LIMIT 20'
        observations.extend(json.loads(row[0]) for row in self.store.db.execute(query, args))
        dependencies = {}
        for observation in observations:
            item = dependency_summary(observation)
            if item:
                dependencies[item['summary_sha256']] = item
        system = enum(platform.system(), {'Darwin', 'Linux', 'Windows'})
        release = platform.mac_ver()[0] if system == 'Darwin' else platform.release()
        probes, probes_omitted = self.service.probe_observations.snapshot()
        environments, environments_omitted = self.service.probe_observations.environment_snapshot()
        return {'schema_version': SCHEMA, 'captured_at': now(), 'application': {'name': 'GCSA AI Lab', 'version': version(__version__), 'build': __build__, 'version_label': __version_label__,
                'control_python': version(platform.python_version()), 'system': system, 'system_version': version(release),
                'architecture': enum(platform.machine(), {'arm64', 'aarch64', 'x86_64', 'AMD64', 'x86'})},
                'scope': {'project_count': 1 if project_id else self.store.db.execute('SELECT count(*) FROM projects').fetchone()[0], 'selected_attempt_count': len(attempt_ids)},
                'resource_counts': counts, 'attempt_state_counts': dict(sorted(states.items())), 'known_error_code_counts': dict(sorted(errors.items())),
                'unknown_error_code_count': unknown_errors, 'selected_attempts': selected,
                'dependency_observations': [dependencies[key] for key in sorted(dependencies)][:32],
                'dependency_observations_omitted': max(0, len(dependencies) - 32),
                'dependency_scope': '仅已有缓存和本范围最近 20 次运行保存的版本；可能过时，本次未重新探测。',
                'probe_observations': probes, 'probe_observations_omitted': probes_omitted,
                'environment_observations': environments, 'environment_observations_omitted': environments_omitted,
                'environment_scope': '整个控制服务当前会话最近 64 次环境调用；按完成顺序排列，包含缓存命中和未配置环境。monotonic_ns 为同一 control_pid 内的纳秒时刻；可按 engine 和覆盖时间段关联 probe_observations，不能与宿主或前端时钟直接相减。completed_at 仅用于有误差的壁钟关联。空 identity 时刻表示未进入身份计算；ready 为本次返回结果，不代表稍后设备状态。预览与导出不启动检查；服务重启清空。',
                'probe_scope': '整个控制服务当前会话最近 32 次实际环境探测；按完成顺序排列，可能包含旧配置。缓存命中、未配置环境和本次诊断不启动探测、不新增记录；服务重启清空，不代表当前设备就绪。'}

    def contents(self, record):
        diagnostics = (encode(record['diagnostics']) + '\n').encode()
        if hashlib.sha256(diagnostics).hexdigest() != record['data_sha256']:
            raise Fault('DIAGNOSTICS_CHANGED', '诊断预览内容已变化，请重新预览。', 409)
        manifest = {'schema_version': record['diagnostics']['schema_version'], 'preview_id': record['id'], 'captured_at': record['created_at'],
                    'complete': True, 'included': record['included'], 'excluded': record['excluded'],
                    'files': [{'path': 'diagnostics.json', 'size': len(diagnostics), 'sha256': record['data_sha256']}]}
        return {'diagnostics.json': diagnostics, 'manifest.json': (encode(manifest) + '\n').encode()}

    def archive(self, record):
        parts = self.contents(record)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, body in parts.items():
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.external_attr = 0o600 << 16
                archive.writestr(info, body)
        data = output.getvalue()
        if len(data) > MAX_BYTES:
            raise Fault('DIAGNOSTICS_TOO_LARGE', '诊断摘要超过当前 256 KiB 上限，请缩小范围。', 409)
        return parts, data

    def preview(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'project_id', 'attempt_ids'}:
            raise Fault('DIAGNOSTICS_INVALID', '诊断预览包含未支持字段。')
        project_id, attempt_ids = payload.get('project_id'), payload.get('attempt_ids', [])
        if project_id is not None and (not isinstance(project_id, str) or not project_id):
            raise Fault('DIAGNOSTICS_INVALID', '项目范围无效。')
        if type(attempt_ids) is not list or len(attempt_ids) > 20 or any(not isinstance(value, str) or not value or len(value) > 100 for value in attempt_ids) or len(set(attempt_ids)) != len(attempt_ids):
            raise Fault('DIAGNOSTICS_INVALID', '最多选择 20 次不同的运行。')
        with self.store.transaction():
            if project_id:
                self.store.get('project', project_id)
            data = self.summary(project_id, attempt_ids)
            record = {'id': identifier('diagnostic-preview'), 'status': 'ready', 'created_at': data['captured_at'],
                      'scope': {'project_id': project_id, 'attempt_ids': attempt_ids}, 'included': INCLUDED, 'excluded': EXCLUDED,
                      'diagnostics': data, 'data_sha256': hashlib.sha256((encode(data) + '\n').encode()).hexdigest()}
            parts, archive = self.archive(record)
            record.update(files=[{'path': name, 'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()} for name, body in parts.items()],
                          total_bytes=sum(len(body) for body in parts.values()), archive_bytes=len(archive), archive_sha256=hashlib.sha256(archive).hexdigest())
            record['preview_digest'] = digest({name: record[name] for name in ('id', 'scope', 'files', 'archive_sha256')})
            # 此记录与项目无外键关系，空资料库也可诊断；沿用现有命令表，避免改变备份数据库结构。
            self.store.remember(RECORD_SCOPE, record['id'], payload, record)
            return self.public(record)

    def get(self, preview_id):
        return self.public(self.record(preview_id))

    def check_cancel(self, preview_id):
        record = self.record(preview_id)
        if record['status'] == 'cancelled' or self.service.closed.is_set():
            raise Fault('DIAGNOSTICS_CANCELLED', '诊断导出已取消，未发布完整文件。', 409)
        return record

    def cancel(self, preview_id, key):
        payload = {'preview_id': preview_id}
        with self.store.transaction():
            if previous := self.store.replay('diagnostic-cancel', key, payload):
                return previous
            record = self.record(preview_id)
            if record['status'] in {'succeeded', 'registration_pending'}:
                raise Fault('DIAGNOSTICS_ALREADY_PUBLISHED', '诊断文件已经发布，取消不会删除已保存文件。', 409)
            if record['status'] == 'writing' and os.path.lexists(record['final_path']):
                # 服务可能在文件发布后、状态提交前中断；已有目标文件不能谎报为已取消。
                record.update(status='registration_pending', finished_at=now(), error={'code': 'DIAGNOSTICS_REGISTRATION_PENDING', 'message': '目标文件已经存在，当前不能确认停止在发布之前；请核对原文件。'})
                self.put(record)
                response = self.public(record)
                self.store.remember('diagnostic-cancel', key, payload, response)
                return response
            if record['status'] not in {'ready', 'writing', 'cancelled'}:
                raise Fault('DIAGNOSTICS_STATE_CONFLICT', '此诊断导出已经结束。', 409)
            record.update(status='cancelled', finished_at=now())
            self.put(record)
            response = self.public(record)
            self.store.remember('diagnostic-cancel', key, payload, response)
            return response

    def verify(self, raw, record):
        if len(raw) != record['archive_bytes'] or hashlib.sha256(raw).hexdigest() != record['archive_sha256']:
            raise Fault('DIAGNOSTICS_INCOMPLETE', '诊断文件大小或完整摘要不一致。', 409)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.namelist() != [item['path'] for item in record['files']] or archive.testzip() is not None:
                raise Fault('DIAGNOSTICS_INCOMPLETE', '诊断 ZIP 文件集合或校验不完整。', 409)
            for entry in record['files']:
                body = archive.read(entry['path'])
                if len(body) != entry['size'] or hashlib.sha256(body).hexdigest() != entry['sha256']:
                    raise Fault('DIAGNOSTICS_INCOMPLETE', '诊断内部文件摘要不一致。', 409)

    def export(self, payload, key):
        if not isinstance(payload, dict) or set(payload) - {'preview_id', 'target_dir', 'grant_id'} or not {'preview_id', 'target_dir'} <= set(payload):
            raise Fault('DIAGNOSTICS_INVALID', '诊断导出需要预览与已授权的本机目录。')
        if not isinstance(payload['target_dir'], str) or not payload['target_dir'] or len(payload['target_dir']) > 4096 or (payload.get('grant_id') is not None and not isinstance(payload['grant_id'], str)):
            raise Fault('DIAGNOSTICS_INVALID', '诊断导出目录或授权格式无效。')
        with self.store.transaction():
            if previous := self.store.replay('diagnostic-export', key, payload):
                record = self.record(previous['preview_id'])
                if record['status'] == 'succeeded':
                    try:
                        with regular_path(record['final_path']).open('rb') as stream:
                            raw = stream.read(MAX_BYTES + 1)
                        self.verify(raw, record)
                    except (OSError, Fault, zipfile.BadZipFile):
                        raise Fault('DIAGNOSTICS_EXPORT_CHANGED', '原诊断文件已移动、删除或变化；此命令不会重建文件。', 409) from None
                return self.public(record)
            record = self.check_cancel(payload['preview_id'])
            if record['status'] != 'ready':
                raise Fault('DIAGNOSTICS_STATE_CONFLICT', '此预览已经用于导出，请读取原回执或重新预览。', 409)
            target = self.service.delivery.target(payload['target_dir'], payload.get('grant_id'))
            record.update(status='writing', export_id=identifier('diagnostic-export'), file_name=record['id'] + '.zip',
                          final_path=str(target / (record['id'] + '.zip')))
            self.put(record)
            self.store.remember('diagnostic-export', key, payload, {'preview_id': record['id'], 'export_id': record['export_id']})
        descriptor, temporary, published, temporary_stat = None, '.diagnostic-' + record['export_id'] + '.tmp', False, None
        try:
            self.check_cancel(record['id'])
            if shutil.disk_usage(target).free < record['archive_bytes'] + 1024 * 1024:
                raise Fault('DISK_FULL', '目标目录空间不足，未发布诊断文件。', 409)
            _, raw = self.archive(record)
            self.verify(raw, record)
            descriptor = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            directory_stat = os.fstat(descriptor)
            stream_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
            with os.fdopen(stream_fd, 'wb') as stream:
                temporary_stat = os.fstat(stream.fileno())
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self.check_cancel(record['id'])
            stream_fd = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
            with os.fdopen(stream_fd, 'rb') as stream:
                self.verify(stream.read(MAX_BYTES + 1), record)
            # 发布事务回滚时也先保存“文件已出现”的回执，再允许取消线程进入。
            with self.store.lock:
                try:
                    with self.store.transaction():
                        self.check_cancel(record['id'])
                        checked_target = self.service.delivery.target(payload['target_dir'], payload.get('grant_id'))
                        current_stat = checked_target.stat()
                        if checked_target != target or (current_stat.st_dev, current_stat.st_ino) != (directory_stat.st_dev, directory_stat.st_ino):
                            raise Fault('DIAGNOSTICS_TARGET_CHANGED', '导出目录在写入期间变化，未发布诊断文件。', 409)
                        # 同目录硬链接以完整文件原子发布，已存在的同名文件绝不会被覆盖。
                        os.link(temporary, record['file_name'], src_dir_fd=descriptor, dst_dir_fd=descriptor, follow_symlinks=False)
                        published = True
                        os.fsync(descriptor)
                        stream_fd = os.open(record['file_name'], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
                        with os.fdopen(stream_fd, 'rb') as stream:
                            self.verify(stream.read(MAX_BYTES + 1), record)
                        record.update(status='succeeded', finished_at=now(), error=None)
                        self.put(record)
                except Exception:
                    if published:
                        with self.store.transaction():
                            pending = self.record(record['id'])
                            pending.update(status='registration_pending', finished_at=now(), error={'code': 'DIAGNOSTICS_REGISTRATION_PENDING', 'message': '目标文件已出现，但完整性或登记尚未确认；请核对原文件，不会重新生成。'})
                            self.put(pending)
                    raise
        except Exception as error:
            with self.store.transaction():
                current = self.record(record['id'])
                if published and current['status'] != 'registration_pending':
                    current.update(status='registration_pending', finished_at=now(), error={'code': 'DIAGNOSTICS_REGISTRATION_PENDING', 'message': '目标文件已出现，但完整性或登记尚未确认；请核对原文件，不会重新生成。'})
                elif current['status'] == 'registration_pending':
                    pass
                elif current['status'] == 'cancelled' or self.service.closed.is_set():
                    current.update(status='cancelled', finished_at=now(), error={'code': 'DIAGNOSTICS_CANCELLED', 'message': '诊断导出已取消，未发布完整文件。'})
                else:
                    code = error.code if isinstance(error, Fault) else 'DISK_FULL' if isinstance(error, OSError) and error.errno == errno.ENOSPC else 'DIAGNOSTICS_IO_ERROR'
                    current.update(status='failed', finished_at=now(), error={'code': code, 'message': '诊断文件未完整发布，请检查目标目录后重新预览。'})
                self.put(current)
                record = current
        finally:
            if descriptor is not None:
                try:
                    current_stat = os.stat(temporary, dir_fd=descriptor, follow_symlinks=False) if temporary_stat else None
                    if current_stat and (current_stat.st_dev, current_stat.st_ino) == (temporary_stat.st_dev, temporary_stat.st_ino):
                        os.unlink(temporary, dir_fd=descriptor)
                except FileNotFoundError:
                    pass
                except OSError:
                    with self.store.transaction():
                        record = self.record(record['id'])
                        record.update(status='registration_pending' if published else 'failed', finished_at=now(),
                                      error={'code': 'DIAGNOSTICS_CLEANUP_PENDING', 'message': '临时文件清理未完成；本次未登记为成功，请检查导出目录。'})
                        self.put(record)
                finally:
                    os.close(descriptor)
        return self.public(record)
