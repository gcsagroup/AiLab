"""格式转换的任务、检查与来源约束，运行时复用已有本机 PyTorch 包。"""

import json
from pathlib import Path
import subprocess
import tempfile

from .assets import verify_manifest, safe_json
from .format_assets import FORMATS
from .storage import Fault, digest, encode


class FormatConversions:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def handles(self, task):
        return task.get('kind') == 'text' and task.get('draft', {}).get('runtime', {}).get('engine') in FORMATS

    def new_task(self, payload, key, *, trial=False):
        scope = 'converted-model-trial' if trial else 'format-conversion'
        with self.store.transaction():
            if key and (previous := self.store.replay(scope, key, payload)):
                return previous
            model = self.store.get('model', payload['model_id'])
            if model['project_id'] != payload['project_id']:
                raise Fault('PROJECT_MISMATCH', '模型必须属于当前项目。', 403)
            target = model.get('default_engine') if trial else payload['target_format']
            if target not in FORMATS:
                raise Fault('CONVERTED_ENGINE_MISMATCH', '当前仅支持 Core ML、ONNX 和 TorchScript。', 409)
            if trial:
                self.provenance(model, target)
            elif model.get('format') not in {'safetensors', 'mlx-safetensors'} or model['model_config'].get('quantization') or model['model_config'].get('quantization_config'):
                raise Fault('MODEL_UNVERIFIED', '格式转换需要未量化 Qwen2.5-0.5B 权重。', 409)
            runtime = {'engine': target, 'device_id': 'cpu', 'seed': 0}
            if trial:
                runtime['max_tokens'] = payload['max_tokens']
            operation = 'generate' if trial else 'convert'
            draft = {'kind': 'text', 'operation': operation, 'model_id': model['id'], 'dataset_id': None, 'adapter_id': None, 'evaluation_plan_id': None, 'input': {'prompt': payload['prompt'] if trial else ''}, 'runtime': runtime}
            task = self.service.resource('task', model['project_id'], name=model['name'] + (' · 格式试用' if trial else ' · ' + target + ' 转换'), kind='text', operation=operation, draft_revision=1, draft=draft, immutable_draft=True)
            self.store.put('task', task)
            if key:
                self.store.remember(scope, key, payload, task)
            return task

    def provenance(self, model, engine):
        if model.get('format') != engine or model.get('default_engine') != engine or model.get('lab_operation') != 'convert' or not model.get('source_attempt_id'):
            raise Fault('CONVERTED_ENGINE_MISMATCH', '格式产物只能使用匹配引擎，并须有本产品的完整转换记录。', 409)
        attempt = self.store.get('attempt', model['source_attempt_id'])
        if attempt['project_id'] != model['project_id'] or attempt['compute_outcome'] != 'succeeded' or attempt['collection_state'] != 'succeeded' or digest(attempt['snapshot']) != attempt['snapshot_digest'] or attempt['snapshot']['operation'] != 'convert' or attempt['snapshot']['runtime']['engine'] != engine:
            raise Fault('CONVERTED_SOURCE_CHANGED', '模型转换来源不完整或发生变化。', 409)
        artifact = self.service.delivery.artifact_for_path(attempt, 'conversion.json')
        report = safe_json(Path(artifact['storage_path']))
        if artifact['id'] != model.get('lab_report_artifact_id') or report.get('output_model_manifest') != model['manifest'] or report.get('output_model_manifest_digest') != model['manifest_digest'] or report.get('verification', {}).get('passed') is not True:
            raise Fault('CONVERTED_SOURCE_CHANGED', '模型与独立加载报告不一致。', 409)
        return {'source_attempt_id': attempt['id'], 'report_sha256': artifact['sha256'], 'manifest_digest': model['manifest_digest'], 'format': engine}

    def inspect(self, task):
        draft = task['draft']; blocking = []
        environment = self.service.media.environment('text', refresh=True)
        environment = {**environment, 'engine': draft['runtime']['engine'], 'device_id': 'cpu', 'runtime_container': 'bundled-media' if self.service.media.bundled('text') else 'external-media-python'}
        environment['digest'] = digest({key: value for key, value in environment.items() if key != 'digest'})
        result = {'blocking': blocking, 'environment': environment, 'model': None, 'dataset': None, 'adapter': None, 'evaluation_plan': None, 'evaluation_fields': {}, 'checkpoint_fields': {}, 'lab_fields': {}}
        try:
            if task['operation'] not in {'generate', 'convert'} or draft.get('dataset_id') or draft.get('adapter_id') or draft.get('checkpoint_id') or draft.get('evaluation_plan_id') or draft.get('execution_target_id'):
                raise Fault('UNSUPPORTED_COMBINATION', '当前格式组合只接受本机转换或独立推理。', 409)
            if not environment['ready']:
                raise Fault('ENVIRONMENT_NOT_READY', environment['reason'], 409)
            model = self.store.get('model', draft['model_id']); result['model'] = model
            if model['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '模型不属于当前项目。', 403)
            verify_manifest(Path(model['storage_path']), model['manifest'])
            if task['operation'] == 'generate':
                result['lab_fields'] = {'format_provenance': self.provenance(model, draft['runtime']['engine'])}
            elif model.get('format') in FORMATS:
                raise Fault('CONVERTED_ENGINE_MISMATCH', '不支持把转换产物再次当作原始权重转换。', 409)
            snapshot = {'kind': 'text', 'operation': task['operation'], 'runtime': draft['runtime'], 'input': draft['input'], 'model_path': model['storage_path'], 'model_manifest': model['manifest'], 'model_manifest_digest': model['manifest_digest'], **result['lab_fields']}
            with tempfile.TemporaryDirectory(prefix='format-check-', dir=self.service.root) as temporary:
                path = Path(temporary); (path / 'snapshot.json').write_text(encode(snapshot))
                checked = subprocess.run(self.service.media.command(path / 'snapshot.json', path / 'output', 'text', preflight=True), capture_output=True, text=True, timeout=90, env=self.service.worker_environment())
                report = json.loads(checked.stdout)
                if not isinstance(report, dict) or type(report.get('can_submit')) is not bool or not isinstance(report.get('blocking'), list):
                    raise ValueError('检查结果结构错误')
                if report['can_submit'] and (checked.returncode != 0 or report['blocking'] or not all(isinstance(report.get(name), dict) for name in ('recipe', 'effective_config', 'check_report')) or report.get('tokenization_recipe_digest') != digest(report['recipe'])):
                    raise ValueError('成功检查缺少完整身份')
                if not report['can_submit'] and not report['blocking']:
                    raise ValueError('阻断原因缺失')
                result['check'] = report; blocking.extend(report['blocking'])
        except Fault as error:
            blocking.append({'code': error.code, 'message': error.message})
        except (ValueError, OSError, subprocess.TimeoutExpired):
            blocking.append({'code': 'FORMAT_PREFLIGHT_FAILED', 'message': '格式执行环境未完成检查，请核对本机依赖。'})
        return result
