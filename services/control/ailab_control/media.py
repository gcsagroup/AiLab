"""本机媒体运行与原始产物入口；复用控制器的冻结、进程和收集合同。"""

import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import wave

from .assets import check_safetensors, copy_asset, file_hash, regular_path, verify_manifest
from .media_assets import material_report, media_model_manifest
from .probe_observations import ProbeFailure
from .storage import Fault, digest, encode, identifier

DEFAULTS = {
    ('image', 'generate'): {'engine': 'diffusers', 'device_id': 'apple-gpu', 'seed': 0, 'size': 512, 'steps': 20, 'cfg': 7.5},
    ('image', 'train'): {'engine': 'diffusers', 'device_id': 'apple-gpu', 'seed': 0, 'size': 512, 'steps': 12, 'learning_rate': 0.0001, 'lora_rank': 4},
    ('video', 'generate'): {'engine': 'diffusers', 'device_id': 'apple-gpu', 'seed': 0, 'steps': 25, 'frames': 14, 'fps': 7},
    ('audio', 'generate'): {'engine': 'kokoro', 'device_id': 'cpu', 'seed': 0, 'voice': 'zf_xiaobei', 'speed': 1.0, 'sample_rate': 24000},
}
PRIMARY = {'image': ('result/image.png', 'image/png'), 'video': ('result/video.mp4', 'video/mp4'), 'audio': ('result/speech.wav', 'audio/wav')}
MAX_CONTENT = 64 * 1024 * 1024


def verify_mp4(raw):
    """验证普通 MP4 外层容器边界；视频解码由固定执行器独立完成。"""
    cursor, kinds = 0, []
    while cursor < len(raw):
        if cursor + 8 > len(raw):
            raise ValueError('MP4 数据块头不完整')
        length = int.from_bytes(raw[cursor:cursor + 4], 'big')
        kind = raw[cursor + 4:cursor + 8]
        header = 8
        if length == 1:
            if cursor + 16 > len(raw):
                raise ValueError('MP4 扩展数据块头不完整')
            length, header = int.from_bytes(raw[cursor + 8:cursor + 16], 'big'), 16
        elif length == 0:
            length = len(raw) - cursor
        if length < header or cursor + length > len(raw) or not re.fullmatch(rb'[a-zA-Z0-9 ]{4}', kind):
            raise ValueError('MP4 数据块边界无效')
        body = raw[cursor + header:cursor + length]
        if kind == b'ftyp' and (cursor or len(body) < 8 or body[:4] not in {b'isom', b'iso2', b'mp41', b'mp42', b'avc1', b'qt  '}):
            raise ValueError('MP4 格式标识无效')
        if kind in {b'moov', b'mdat'} and not body:
            raise ValueError('MP4 媒体或索引为空')
        kinds.append(kind)
        cursor += length
    if not kinds or kinds[0] != b'ftyp' or kinds.count(b'ftyp') != 1 or kinds.count(b'moov') != 1 or b'mdat' not in kinds:
        raise ValueError('MP4 缺少格式、索引或媒体数据')


class Media:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.cache = {}
        self.environment_locks = {'media': threading.Lock(), 'audio': threading.Lock()}

    def execution(self, kind):
        settings = self.service.settings
        prefix = 'audio' if kind == 'audio' else 'media'
        return (getattr(settings, prefix + '_python'), getattr(settings, prefix + '_worker_script'), getattr(settings, prefix + '_preflight_script'))

    def bundled(self, kind):
        prefix = 'audio' if kind == 'audio' else 'media'
        return getattr(self.service.settings, 'bundled_' + prefix + '_worker') if not getattr(self.service.settings, prefix + '_python') else None

    def bundled_environment(self, kind, binary, result, refresh, observation):
        if not binary.is_absolute() or not binary.is_file() or not os.access(binary, os.X_OK):
            result['reason'] = '内置媒体执行器缺失或不可执行，请重新安装应用。'
            return {**result, 'digest': digest(result)}
        with self.service.probe_observations.identity(observation):
            identity = {'bundled_worker': str(binary), 'binary_sha256': file_hash(binary), 'binary_size': binary.stat().st_size}
            cache_key = digest(identity)
        if not refresh and cache_key in self.cache:
            observation['cache_outcome'] = 'hit'
            return self.cache[cache_key]
        observation['cache_outcome'] = 'refresh' if refresh else 'miss'
        def is_ready(facts):
            sources = facts.get('sources')
            complete = isinstance(sources, dict) and bool(sources) and all(isinstance(name, str) and isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) for name, value in sources.items()) and isinstance(facts.get('runtime_manifest_sha256'), str) and re.fullmatch('[0-9a-f]{64}', facts['runtime_manifest_sha256'])
            return bool(complete and facts.get('device_ready') is True and facts['dependencies'])
        try:
            facts, ready = self.service.probe_observations.run(result['engine'], 'bundled', [str(binary), '--mode', 'probe'],
                                  timeout=90, env=self.service.worker_environment(), is_ready=is_ready)
            result.update(ready=ready, execution_backend='bundled', versions=facts, identity=identity, reason='' if ready else '内置媒体环境缺少设备、依赖或完整来源身份。')
        except ProbeFailure as error:
            result.update(identity=identity, execution_backend='bundled', reason=str(error))
        result['digest'] = digest(result)
        self.cache[cache_key] = result
        return result

    def environment(self, kind, refresh=False, *, origin='environment'):
        with self.service.probe_observations.environment('kokoro' if kind == 'audio' else 'diffusers', kind, origin, refresh) as observation:
            with self.environment_locks['audio' if kind == 'audio' else 'media']:
                observation['lock_acquired_monotonic_ns'] = time.monotonic_ns()
                result = self._environment(kind, refresh, observation)
                observation['ready'] = result.get('ready')
                return result

    def _environment(self, kind, refresh, observation):
        python, worker, preflight = self.execution(kind)
        audio = kind == 'audio'
        result = {'engine': 'kokoro' if audio else 'diffusers', 'device_id': 'cpu' if audio else 'apple-gpu', 'ready': False, 'reason': '请在设置中选择已准备的配音 Python 环境。' if audio else '请在设置中选择已准备的图片与视频 Python 环境。'}
        if binary := self.bundled(kind):
            return self.bundled_environment(kind, binary, result, refresh, observation)
        if not all(path and path.is_absolute() and path.is_file() for path in (python, worker, preflight)):
            return {**result, 'digest': digest(result)}
        root = worker.parent.parent
        names = ['adapters/media/tts_cli.py', 'adapters/media/tts_prepare.py'] if audio else ['adapters/media/image_cli.py', 'adapters/media/video_cli.py', 'adapters/media/prepare_tiny_sd.py', 'adapters/media/prepare_svd.py', 'adapters/media/requirements.lock.txt', 'workers/mlx_worker.py']
        names.extend('services/control/ailab_control/' + name for name in ('assets.py', 'storage.py', 'media_assets.py', 'media_model_cards.py'))
        paths = list(dict.fromkeys([worker, preflight, *[root / name for name in names]]))
        if not all(path.is_file() for path in paths):
            result['reason'] = '媒体执行器来源文件不完整，请重新安装本机应用。'
            return {**result, 'digest': digest(result)}
        with self.service.probe_observations.identity(observation):
            sources = {str(path): file_hash(path) for path in paths}
            identity = {'python': str(python), 'python_size': python.stat().st_size, 'python_mtime_ns': python.stat().st_mtime_ns, 'sources': sources}
            cache_key = digest(identity)
        if not refresh and cache_key in self.cache:
            observation['cache_outcome'] = 'hit'
            return self.cache[cache_key]
        observation['cache_outcome'] = 'refresh' if refresh else 'miss'
        packages = ['kokoro', 'misaki', 'torch', 'transformers', 'soundfile'] if audio else ['torch', 'diffusers', 'transformers', 'accelerate', 'safetensors', 'Pillow', 'peft']
        program = "import json,platform,importlib.metadata as m;import torch;print(json.dumps({'python':platform.python_version(),'dependencies':{n:m.version(n) for n in " + repr(packages) + "},'device_ready':" + ('True' if audio else 'torch.backends.mps.is_available()') + '}))'
        try:
            facts, ready = self.service.probe_observations.run(result['engine'], 'external_python', [str(python), '-B', '-c', program],
                                  timeout=30, env=self.service.worker_environment(), is_ready=lambda facts: bool(facts.get('device_ready')))
            result.update(ready=ready, versions=facts, identity=identity, execution_backend='external_python')
            result['reason'] = '' if result['ready'] else '媒体依赖或实际设备未准备完成。'
        except ProbeFailure as error:
            result['reason'] = str(error)
        result['digest'] = digest(result)
        self.cache[cache_key] = result
        return result

    def command(self, snapshot, output, kind, preflight=False):
        if binary := self.bundled(kind):
            return [str(binary), '--mode', 'preflight' if preflight else 'run', '--snapshot', str(snapshot), '--output-dir', str(output)]
        python, worker, checker = self.execution(kind)
        command = [str(python), '-B', str(checker if preflight else worker), '--snapshot', str(snapshot), '--output-dir', str(output)]
        if preflight and kind == 'audio':
            command.append('--preflight')
        return command

    def inspect(self, task):
        draft = task['draft']
        kind, operation = draft['kind'], draft['operation']
        blocking = []
        environment = self.environment(kind, refresh=True)
        result = {'blocking': blocking, 'environment': environment, 'model': None, 'dataset': None, 'adapter': None, 'evaluation_plan': None, 'evaluation_fields': {}, 'checkpoint_fields': {}, 'media_fields': {}}
        if (kind, operation) not in DEFAULTS:
            blocking.append({'code': 'UNSUPPORTED_COMBINATION', 'message': '当前媒体组合尚未接入真实执行。'})
        if not environment['ready']:
            blocking.append({'code': 'ENVIRONMENT_NOT_READY', 'message': environment['reason']})
        if draft.get('evaluation_plan_id') or draft.get('checkpoint_id'):
            blocking.append({'code': 'UNSUPPORTED_COMBINATION', 'message': '媒体任务尚未接入训练检查点或质量准入计划。'})
        model = self.store.get('model', draft['model_id']) if draft.get('model_id') else None
        result['model'] = model
        if not model:
            blocking.append({'code': 'MODEL_NOT_READY', 'message': '请先导入并选择当前类型的固定模型。', 'field': 'model_id'})
        else:
            if model['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '模型不属于当前项目。', 403)
            try:
                report = media_model_manifest(Path(model['storage_path']))
                if not report or report['manifest_digest'] != model['manifest_digest'] or report['modality'] != kind or draft['runtime'].get('engine') != report['default_engine']:
                    raise Fault('UNSUPPORTED_COMBINATION', '模型类型、固定清单或执行引擎不匹配。')
                result['media_fields']['prepared_model_manifest_digest'] = report['metadata_manifest_digest']
            except Fault as error:
                blocking.append({'code': error.code, 'message': error.message, 'field': 'model_id'})
        if operation == 'train':
            dataset = self.store.get('dataset', draft['dataset_id']) if draft.get('dataset_id') else None
            result['dataset'] = dataset
            if not dataset or dataset.get('schema') != 'image_caption_v1':
                blocking.append({'code': 'DATA_SCHEMA_MISMATCH', 'message': '图片训练需要已导入的图片与描述数据集。', 'field': 'dataset_id'})
            elif dataset['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '数据集不属于当前项目。', 403)
            else:
                try:
                    verify_manifest(Path(dataset['storage_path']), dataset['manifest'])
                    result['media_fields']['dataset_root_path'] = dataset['storage_path']
                except Fault as error:
                    blocking.append({'code': error.code, 'message': error.message, 'field': 'dataset_id'})
        elif draft.get('dataset_id'):
            blocking.append({'code': 'UNSUPPORTED_COMBINATION', 'message': '媒体生成不接受训练数据集。'})
        if draft.get('adapter_id'):
            adapter = self.store.get('adapter', draft['adapter_id'])
            result['adapter'] = adapter
            if adapter['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '适配器不属于当前项目。', 403)
            if kind != 'image' or operation != 'generate' or adapter.get('modality') != 'image' or not model or adapter['base_model_id'] != model['id'] or adapter['base_manifest_digest'] != model['manifest_digest']:
                blocking.append({'code': 'ADAPTER_BASE_MISMATCH', 'message': '图片适配器只可在来源固定基座上显式试用。', 'field': 'adapter_id'})
            else:
                try:
                    verify_manifest(Path(adapter['storage_path']), adapter['manifest'])
                except Fault as error:
                    blocking.append({'code': error.code, 'message': error.message, 'field': 'adapter_id'})
        if kind == 'video':
            material_id = draft['input'].get('material_id')
            material = self.store.get('material', material_id) if material_id else None
            if not material:
                blocking.append({'code': 'MATERIAL_REQUIRED', 'message': '图生视频需要先选择已导入的 PNG 图片。', 'field': 'input.material_id'})
            elif material['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '输入素材不属于当前项目。', 403)
            else:
                try:
                    verify_manifest(Path(material['storage_path']), material['manifest'])
                    entrypoint = material['entrypoint']
                    report = material_report(Path(material['storage_path']) / entrypoint)
                    if report['manifest_digest'] != material['manifest_digest']:
                        raise Fault('ARTIFACT_CORRUPT', '输入素材与已导入版本不符。', 409)
                    result['media_fields'].update(material_id=material['id'], material_version_id=material['version_id'], input_image_path=str(Path(material['storage_path']) / entrypoint), input_image_manifest=material['manifest'], input_image_manifest_digest=material['manifest_digest'])
                except Fault as error:
                    blocking.append({'code': error.code, 'message': error.message, 'field': 'input.material_id'})
        if blocking:
            return result
        snapshot = {'kind': kind, 'operation': operation, 'model_path': model['storage_path'], 'model_manifest': model['manifest'], 'model_manifest_digest': model['manifest_digest'], 'input': draft['input'], 'runtime': draft['runtime'], **result['media_fields']}
        if result['dataset']:
            dataset = result['dataset']
            snapshot.update(dataset_path=str(Path(dataset['storage_path']) / dataset['entrypoint']), dataset_manifest=dataset['manifest'], dataset_manifest_digest=dataset['manifest_digest'])
        if result['adapter']:
            adapter = result['adapter']
            snapshot.update(adapter_path=adapter['storage_path'], adapter_manifest=adapter['manifest'], adapter_manifest_digest=adapter['manifest_digest'])
        with tempfile.TemporaryDirectory(prefix='media-check-', dir=self.service.root) as directory:
            path = Path(directory)
            (path / 'snapshot.json').write_text(encode(snapshot))
            try:
                checked = subprocess.run(self.command(path / 'snapshot.json', path / 'output', kind, preflight=True), capture_output=True, text=True, timeout=180, env=self.service.worker_environment())
                report = json.loads(checked.stdout)
                if not isinstance(report, dict) or type(report.get('can_submit')) is not bool or not isinstance(report.get('blocking'), list) or checked.returncode not in (0, 1):
                    raise ValueError('媒体检查结构错误')
                if report['can_submit'] and (checked.returncode or report['blocking'] or not isinstance(report.get('effective_config'), dict) or not re.fullmatch('[0-9a-f]{64}', report.get('media_recipe_digest', '')) or not isinstance(report.get('check_report'), dict)):
                    raise ValueError('媒体检查缺少完整身份')
                if not report['can_submit'] and not report['blocking']:
                    raise ValueError('媒体阻断缺少原因')
                if any(not isinstance(item, dict) or not isinstance(item.get('code'), str) or not isinstance(item.get('message'), str) for item in report['blocking']):
                    raise ValueError('媒体阻断字段无效')
                result['check'] = report
                blocking.extend(report['blocking'])
            except (OSError, ValueError, subprocess.TimeoutExpired):
                blocking.append({'code': 'PREFLIGHT_FAILED', 'message': '媒体实际检查未完成，请检查环境与模型。'})
        return result

    def primary(self, attempt):
        kind = attempt['snapshot']['kind']
        if kind not in PRIMARY or attempt['snapshot']['operation'] != 'generate' or attempt['compute_outcome'] != 'succeeded' or attempt['collection_state'] != 'succeeded':
            raise Fault('ARTIFACT_NOT_READY', '只有完整保存的媒体生成主产物可预览和保存为作品。', 409)
        relative, mime = PRIMARY[kind]
        artifact = self.service.delivery.artifact_for_path(attempt, relative)
        entries = [item for item in attempt['output_manifest_ref']['artifacts'] if item.get('path') == relative]
        if artifact.get('relative_path') != relative or artifact.get('media_type') != mime or entries[0].get('media_type') != mime:
            raise Fault('ARTIFACT_CORRUPT', '媒体类型与原执行主产物清单不符。', 409)
        if artifact['size'] > MAX_CONTENT:
            raise Fault('MEDIA_TOO_LARGE', '此媒体超过当前 64 MiB 作品与预览限制。', 413)
        try:
            if kind == 'image':
                report = material_report(Path(artifact['storage_path']))
                if report['sha256'] != artifact['sha256'] or report['total_bytes'] != artifact['size']:
                    raise ValueError('图片结构检查期间内容已变化')
            else:
                with regular_path(artifact['storage_path']).open('rb') as stream:
                    raw = stream.read(MAX_CONTENT + 1)
                if len(raw) != artifact['size'] or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
                    raise ValueError('媒体结构检查期间内容已变化')
                if kind == 'audio':
                    with wave.open(io.BytesIO(raw), 'rb') as reader:
                        frames = reader.getnframes()
                        if reader.getframerate() != 24000 or reader.getnchannels() != 1 or reader.getsampwidth() != 2 or not 0 < frames <= 24000 * 180 or len(reader.readframes(frames)) != frames * 2:
                            raise ValueError('音频采样格式、长度或完整性不符')
                else:
                    verify_mp4(raw)
        except (Fault, ValueError, OSError, EOFError, wave.Error) as error:
            raise Fault('MEDIA_CORRUPT', '主媒体无法按声明格式完整读取。', 409) from error
        return artifact

    def content(self, artifact_id):
        initial = self.store.get('artifact', artifact_id)
        attempt = self.store.get('attempt', initial['attempt_id'])
        artifact = self.primary(attempt)
        if artifact['id'] != artifact_id:
            raise Fault('MEDIA_NOT_PREVIEWABLE', '此产物不是本次生成的主媒体。', 409)
        if artifact['size'] > MAX_CONTENT:
            raise Fault('MEDIA_TOO_LARGE', '此媒体超过 64 MiB 预览限制，请使用导出。', 413)
        with regular_path(artifact['storage_path']).open('rb') as stream:
            raw = stream.read(MAX_CONTENT + 1)
        if len(raw) != artifact['size'] or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
            raise Fault('ARTIFACT_CORRUPT', '媒体读取期间源文件已变化。', 409)
        return raw, artifact['media_type']

    def save_work(self, payload, key):
        with self.store.transaction():
            if previous := self.store.replay('save-work', key, payload):
                return previous
            attempt = self.store.get('attempt', payload['attempt_id'])
        artifact = self.primary(attempt)
        if payload.get('artifact_id') not in (None, artifact['id']):
            raise Fault('ARTIFACT_NOT_READY', '所选产物不是该媒体生成的主结果。', 409)
        with self.store.transaction():
            if previous := self.store.replay('save-work', key, payload):
                return previous
            if self.store.get('attempt', attempt['id']) != attempt or self.store.get('artifact', artifact['id']) != artifact:
                raise Fault('REVISION_CONFLICT', '保存作品期间来源已变化。', 409)
            existing = [item for item in self.store.list('work', attempt['project_id']) if item['artifact_id'] == artifact['id']]
            kind = attempt['snapshot']['kind']
            result = existing[0] if existing else self.service.resource('work', attempt['project_id'], name=payload.get('name') or {'image': '图片结果', 'video': '视频结果', 'audio': '配音结果'}[kind], kind=kind, media_type=artifact['media_type'], artifact_id=artifact['id'], attempt_id=attempt['id'], source_attempt=attempt['id'], revision=1, favorite=False, recipe=attempt['snapshot'], text=None, quality_status='not_evaluated')
            self.store.put('work', result)
            response = self.service.public(result)
            self.store.remember('save-work', key, payload, response)
            return response

    def save_adapter(self, attempt_id, payload, key):
        scope = 'save-adapter:' + attempt_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            attempt = self.store.get('attempt', attempt_id)
            snapshot = attempt['snapshot']
            if snapshot['kind'] != 'image' or snapshot['operation'] != 'train' or attempt['compute_outcome'] != 'succeeded' or attempt['collection_state'] != 'succeeded':
                raise Fault('ADAPTER_NOT_READY', '图片适配器需要完整保存的真实训练产物。', 409)
            existing = [item for item in self.store.list('adapter', attempt['project_id']) if item['source_attempt_id'] == attempt_id]
            if existing:
                response = self.service.public(existing[0])
                self.store.remember(scope, key, payload, response)
                return response
        weights = self.service.delivery.artifact_for_path(attempt, 'result/pytorch_lora_weights.safetensors')
        training = self.service.delivery.artifact_for_path(attempt, 'result/training.json')
        if training['size'] > 8 * 1024 * 1024:
            raise Fault('ADAPTER_PROVENANCE_MISMATCH', '图片训练报告超过允许大小。', 409)
        with regular_path(training['storage_path']).open('rb') as stream:
            report_bytes = stream.read(8 * 1024 * 1024 + 1)
        if len(report_bytes) != training['size'] or hashlib.sha256(report_bytes).hexdigest() != training['sha256']:
            raise Fault('ARTIFACT_CORRUPT', '图片训练报告读取期间已变化。', 409)
        try:
            report = json.loads(report_bytes)
            if not isinstance(report, dict):
                raise ValueError('报告须为对象')
        except (ValueError, UnicodeError) as error:
            raise Fault('ADAPTER_PROVENANCE_MISMATCH', '图片训练报告无法解析。', 409) from error
        effective = attempt['output_manifest_ref'].get('effective_config', {})
        model_manifest_sha = next((item['sha256'] for item in snapshot['model_manifest'] if item['path'] == 'manifest.json'), None)
        dataset_sha = next((item['sha256'] for item in snapshot['dataset_manifest'] if item['path'] == 'dataset.json'), None)
        losses = report.get('losses')
        if not model_manifest_sha or not dataset_sha or report.get('model_manifest_sha256') != model_manifest_sha or report.get('dataset_sha256') != dataset_sha or report.get('adapter_sha256') != weights['sha256'] or effective.get('media_recipe_digest') != snapshot.get('media_recipe_digest') or not effective.get('source_model_unchanged'):
            raise Fault('ADAPTER_PROVENANCE_MISMATCH', '图片适配器的基座、数据、配方或权重来源与原执行不符。', 409)
        frozen = report.get('frozen_parameter_sha256_before')
        runtime = snapshot['runtime']
        expected = {'size': 512, 'steps': runtime['steps'], 'seed': runtime['seed'], 'rank': 4, 'alpha': 4, 'learning_rate': 0.0001}
        if any(report.get(name) != value for name, value in expected.items()) or not isinstance(frozen, str) or not re.fullmatch('[0-9a-f]{64}', frozen) or frozen != report.get('frozen_parameter_sha256_after') or not isinstance(losses, list) or len(losses) != runtime['steps'] or any(not isinstance(item, dict) or item.get('step') != index or type(item.get('loss')) not in (float, int) or not math.isfinite(item['loss']) for index, item in enumerate(losses, 1)):
            raise Fault('ADAPTER_PROVENANCE_MISMATCH', '图片训练参数、真实逐步损失或冻结基座证据不完整。', 409)
        check_safetensors(Path(weights['storage_path']))
        manifest = [{'path': name, 'size': artifact['size'], 'sha256': artifact['sha256']} for name, artifact in [('pytorch_lora_weights.safetensors', weights), ('training.json', training)]]
        identity = digest(manifest)
        # 两个已收集来源在独立目录，不重新解释执行目录中的其它文件。
        with tempfile.TemporaryDirectory(prefix='.image-adapter-', dir=self.service.root / 'assets') as temporary:
            import shutil
            for name, artifact in [('pytorch_lora_weights.safetensors', weights), ('training.json', training)]:
                shutil.copyfile(artifact['storage_path'], Path(temporary) / name)
            destination = copy_asset(Path(temporary), self.service.root / 'assets', manifest, identity)
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.store.get('attempt', attempt_id) != attempt or self.store.get('artifact', weights['id']) != weights or self.store.get('artifact', training['id']) != training:
                raise Fault('REVISION_CONFLICT', '保存适配器期间原执行记录已变化。', 409)
            result = self.service.resource('adapter', attempt['project_id'], name=payload.get('name') or '图片实验 LoRA', modality='image', status='experimental', quality_status='not_evaluated', version_id=identifier('adapter-version'), revision=1, source_attempt_id=attempt_id, base_model_id=snapshot['model_id'], base_model_version_id=snapshot['model_version_id'], base_manifest_digest=snapshot['model_manifest_digest'], training_recipe_digest=snapshot['media_recipe_digest'], manifest=manifest, manifest_digest=identity, total_bytes=sum(item['size'] for item in manifest), storage_path=str(destination), config=report, message='图片实验适配器；需要固定基座，尚未通过独立质量准入。')
            self.store.put('adapter', result)
            response = self.service.public(result)
            self.store.remember(scope, key, payload, response)
            return response

    def material_from_work(self, work_id, key):
        payload, scope = {'work_id': work_id}, 'material-from-work:' + work_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            work = self.store.get('work', work_id)
            attempt = self.store.get('attempt', work['source_attempt'])
        artifact = self.primary(attempt)
        if attempt['snapshot']['kind'] != 'image' or artifact['id'] != work['artifact_id'] or work['project_id'] != attempt['project_id']:
            raise Fault('MATERIAL_UNSUPPORTED', '只有已保存的图片作品可转为视频输入素材。', 409)
        report = material_report(Path(artifact['storage_path']))
        if report['sha256'] != artifact['sha256'] or report['total_bytes'] != artifact['size']:
            raise Fault('ARTIFACT_CORRUPT', '转换素材期间图片作品已变化。', 409)
        destination = copy_asset(Path(artifact['storage_path']), self.service.root / 'assets', report['manifest'], report['manifest_digest'])
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if self.store.get('work', work_id) != work or self.store.get('attempt', attempt['id']) != attempt:
                raise Fault('REVISION_CONFLICT', '转换素材期间作品来源已变化。', 409)
            existing = [item for item in self.store.list('material', work['project_id']) if item.get('source_work_id') == work_id]
            fields = {key: report[key] for key in ('kind', 'media_type', 'manifest', 'manifest_digest', 'entrypoint', 'total_bytes', 'width', 'height', 'checks')}
            result = existing[0] if existing else self.service.resource('material', work['project_id'], name=work['name'], version_id=identifier('version'), revision=1, status='ready', storage_path=str(destination), source_work_id=work_id, source_attempt_id=attempt['id'], **fields)
            self.store.put('material', result)
            response = self.service.public(result)
            self.store.remember(scope, key, payload, response)
            return response
