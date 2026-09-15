"""正式任务账本中的独立执行：冻结上传范围、原编号同步与原清单补收。"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace

from .assets import verify_manifest
from .remote.protocol import ProtocolError, MAX_INPUTS, MAX_STORAGE, publish_directory, sync_directory, CONNECTION_ERRORS
from .storage import Fault, digest, identifier, now


TERMINAL = {'succeeded', 'failed', 'cancelled'}


class RemoteExecution:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.running = set()
        self.collecting = set()
        self.lock = threading.RLock()

    def target_fields(self, value):
        return {**{key: value[key] for key in ('id', 'name', 'origin', 'executor_id', 'revision', 'validation_scope')},
                'transport': value.get('transport', 'loopback_http')}

    def transfer_prepare(self, payload):
        target = self.store.get('execution-target', payload['execution_target_id'])
        client, target = self.service.execution_targets.client(target['id'], payload['project_id'])
        try:
            client.identity()
        except ProtocolError as error:
            raise Fault(error.code, error.message, error.status) from None
        asset = self.store.get(payload['asset_kind'], payload['asset_id'])
        if asset['project_id'] != payload['project_id']:
            raise Fault('PROJECT_MISMATCH', '传输输入不属于当前项目。', 403)
        verify_manifest(Path(asset['storage_path']), asset['manifest'])
        files = asset['manifest']
        if not 1 <= len(files) <= MAX_INPUTS or any(item['size'] > 64 * 1024**2 for item in files) or sum(item['size'] for item in files) > MAX_STORAGE:
            raise Fault('TRANSFER_INPUT_LIMIT', '传输验证最多 16 个文件，每个文件不超过 64 MiB。')
        fields = {**payload, 'target': self.target_fields(target), 'files': files, 'total_bytes': sum(item['size'] for item in files),
                  'asset_manifest_digest': asset['manifest_digest'], 'validation_scope': target['validation_scope'], 'transport': target.get('transport', 'loopback_http'), 'model_execution': False,
                  'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
        value = self.service.resource('remote-transfer-plan', payload['project_id'], **{key: value for key, value in fields.items() if key != 'project_id'})
        value['prepare_id'] = value['id']
        value['digest'] = digest(value)
        with self.store.transaction():
            if self.target_fields(self.store.get('execution-target', target['id'])) != fields['target']:
                raise Fault('EXECUTION_TARGET_CHANGED', '准备期间执行目标发生变化，请重新预览。', 409)
            self.store.put('remote-transfer-plan', value)
        return self.service.public(value)

    def transfer_submit(self, payload, key):
        with self.store.transaction():
            if previous := self.store.replay('remote-transfer:submit', key, payload):
                return self.service.public(self.store.get('attempt', previous['id']))
            plan = self.store.get('remote-transfer-plan', payload['prepare_id'])
            if payload['digest'] != plan['digest'] or digest({k: v for k, v in plan.items() if k != 'digest'}) != plan['digest']:
                raise Fault('TRANSFER_PLAN_CHANGED', '上传范围摘要不一致，请重新预览。', 409)
            if datetime.fromisoformat(plan['expires_at']) <= datetime.now(timezone.utc):
                raise Fault('TRANSFER_PLAN_EXPIRED', '上传范围预览已过期，请重新预览。', 409)
            asset = self.store.get(plan['asset_kind'], plan['asset_id'])
            _, target = self.service.execution_targets.client(plan['execution_target_id'], plan['project_id'])
            if self.target_fields(target) != plan['target'] or asset['manifest_digest'] != plan['asset_manifest_digest'] or asset['manifest'] != plan['files']:
                raise Fault('TRANSFER_PLAN_CHANGED', '输入或目标版本已变化，请重新预览上传范围。', 409)
        verify_manifest(Path(asset['storage_path']), asset['manifest'])
        with self.store.transaction():
            if previous := self.store.replay('remote-transfer:submit', key, payload):
                return self.service.public(self.store.get('attempt', previous['id']))
            if self.store.get(plan['asset_kind'], plan['asset_id']) != asset or self.target_fields(self.store.get('execution-target', target['id'])) != plan['target']:
                raise Fault('TRANSFER_PLAN_CHANGED', '提交检查期间输入或目标发生变化。', 409)
            if self.service.closed.is_set():
                raise Fault('SERVICE_STOPPING', '服务正在关闭，请稍后重试。', 503)
            task = self.service.resource('task', plan['project_id'], name='文件传输验证 · ' + asset['name'], kind='text', operation='transfer',
                                         immutable_draft=True, draft_revision=1, draft={'kind': 'text', 'operation': 'transfer', 'execution_target_id': target['id'], 'runtime': {}})
            self.store.put('task', task)
            snapshot = {'schema_version': '1.1', 'kind': 'text', 'operation': 'transfer', 'project_id': plan['project_id'], 'task_id': task['id'],
                        'execution_target_id': target['id'], 'execution_target_name': target['name'], 'execution_target': plan['target'],
                        'validation_scope': target['validation_scope'], 'transport': target.get('transport', 'loopback_http'), 'model_execution': False, 'input': {}, 'runtime': {},
                        'asset_kind': plan['asset_kind'], 'asset_id': plan['asset_id'], 'asset_manifest_digest': plan['asset_manifest_digest'],
                        'upload_summary': {'files': plan['files'], 'total_bytes': plan['total_bytes']}, 'submitted_at': now()}
            inputs = [{key: item[key] for key in ('path', 'size', 'sha256')} for item in plan['files']]
            remote = {'schema_version': 1, 'executor_id': target['executor_id'], 'transport': target.get('transport', 'loopback_http'), 'adapter_id': 'protocol-copy', 'operation': 'copy',
                      'inputs': inputs, 'runtime': {'steps': 50, 'step_delay_ms': 100}}
            # 相对名与本机路径分开保存，不向执行服务发送本机路径。
            sources = [{'source_path': str(Path(asset['storage_path']) / item['path']), 'root': asset['storage_path'], 'path': item['path'],
                        'size': item['size'], 'sha256': item['sha256']} for item in plan['files']]
            attempt = self.new_attempt(task, snapshot, remote, sources)
            self.store.remember('remote-transfer:submit', key, payload, {'id': attempt['id']})
        self.start(attempt['id'])
        return self.service.public(attempt)

    def new_attempt(self, task, snapshot, remote_snapshot, sources):
        attempt = self.service.resource('attempt', task['project_id'], task_id=task['id'], state='queued', state_version=1,
                                       executor_type='remote', execution_target_id=snapshot['execution_target_id'],
                                       connection_state='connected', stop_status='not_requested', compute_outcome='pending',
                                       collection_state='not_started', collection_version=0, output_manifest_ref=None,
                                       last_event_sequence=0, phase='uploading', progress=None, output_text='', terminal_reason=None,
                                       remote_event_cursor=0, remote_state_version=None, remote_submission_started=False,
                                       remote_submitted=False, remote_cancel_intent=False, remote_cancel_command=None, source_files=sources)
        snapshot = {**snapshot, 'attempt_id': attempt['id']}
        remote_snapshot = {**remote_snapshot, 'attempt_id': attempt['id']}
        attempt.update(snapshot=snapshot, snapshot_digest=digest(snapshot), remote_snapshot=remote_snapshot,
                       remote_snapshot_digest=digest(remote_snapshot), remote_submit_key='submit-' + attempt['id'])
        self.store.put('attempt', attempt)
        self.store.event(attempt, 'state_changed', {'state': 'queued', 'state_version': 1, 'message': '上传范围已冻结；正在按原文件摘要传输。'})
        return attempt

    def listing(self, project_id, cursor=None, limit=100, execution_target_id=None):
        if execution_target_id:
            target = self.store.get('execution-target', execution_target_id)
            if project_id and target['project_id'] != project_id:
                raise Fault('PROJECT_MISMATCH', '执行目标不属于当前项目。', 403)
        page = self.store.page('attempt', project_id, cursor, limit=limit, operation='transfer', descending=True, execution_target_id=execution_target_id)
        return {**page, 'items': [self.service.public(item) for item in page['items']]}

    def inspect(self, task):
        from adapters.nvidia_text.adapter import validate_snapshot, MODEL_DIGEST, source_identity
        from adapters.mlx_text.recipe import build_recipe, TEMPLATE_SHA256
        draft, blocking = task['draft'], []
        target = self.store.get('execution-target', draft['execution_target_id'])
        if target['project_id'] != task['project_id']:
            raise Fault('PROJECT_MISMATCH', '执行目标不属于当前项目。', 403)
        try:
            checked = self.service.execution_targets.check(target['id'])
            environment = checked.get('nvidia_environment') or {'ready': False, 'blocking': [checked.get('last_error') or {'code': 'NVIDIA_PROBE_REQUIRED', 'message': '此执行目标没有可用的 NVIDIA 探测结果。'}]}
        except Fault as error:
            environment = {'ready': False, 'blocking': [{'code': error.code, 'message': error.message}]}
        environment = {**environment, 'engine': 'transformers', 'device_id': 'cuda:0', 'execution_target_id': target['id']}
        if not environment.get('ready'):
            blocking.extend(environment.get('blocking') or [{'code': 'NVIDIA_NOT_READY', 'message': '目标 NVIDIA 环境尚未就绪。'}])
        environment['digest'] = digest(environment)
        if draft['kind'] != 'text' or draft['operation'] not in {'generate', 'train'}:
            blocking.append({'code': 'REMOTE_OPERATION_UNSUPPORTED', 'message': '此执行目标首期只支持文本生成与 SFT + LoRA。'})
        if draft.get('adapter_id') or draft.get('checkpoint_id'):
            blocking.append({'code': 'REMOTE_INPUT_UNSUPPORTED', 'message': 'NVIDIA 首期不接受推理适配器或本机检查点。'})
        resources, files, sources = {}, [], []
        for kind, field in (('model', 'model_id'), ('dataset', 'dataset_id')):
            if not draft.get(field):
                if kind == 'model' or draft['operation'] == 'train':
                    blocking.append({'code': kind.upper() + '_NOT_READY', 'message': '请先选择模型和本次训练需要的数据。', 'field': field})
                continue
            if kind == 'dataset' and draft['operation'] != 'train':
                blocking.append({'code': 'REMOTE_INPUT_UNSUPPORTED', 'message': '生成任务不上传训练数据。', 'field': field})
                continue
            asset = self.store.get(kind, draft[field])
            if asset['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '输入资源不属于当前项目。', 403)
            resources[kind] = asset
            try:
                verify_manifest(Path(asset['storage_path']), asset['manifest'])
                if digest(asset['manifest']) != asset['manifest_digest']:
                    raise Fault('ASSET_MANIFEST_CHANGED', '输入清单摘要与登记不一致。', 409)
                if kind == 'model' and asset['manifest_digest'] != MODEL_DIGEST:
                    raise Fault('MODEL_UNVERIFIED', 'NVIDIA 首期只支持固定 Qwen2.5-0.5B-Instruct 原权重；当前模型不匹配。', 409)
                if kind == 'dataset' and (len(asset['manifest']) != 1 or asset.get('schema', 'sft') != 'sft'):
                    raise Fault('DATASET_SCHEMA_UNSUPPORTED', 'NVIDIA SFT 只接受单个纯文本 SFT JSONL。', 409)
                for item in asset['manifest']:
                    name = 'model/' + item['path'] if kind == 'model' else 'data/train.jsonl'
                    files.append({**item, 'path': name})
                    sources.append({'source_path': str(Path(asset['storage_path']) / item['path']), 'root': asset['storage_path'],
                                    'path': name, 'size': item['size'], 'sha256': item['sha256']})
            except Fault as error:
                blocking.append({'code': error.code, 'message': error.message, 'field': field})
        runtime = dict(draft['runtime'])
        dataset_split_fields = {}
        if draft['operation'] == 'train' and resources.get('dataset'):
            try:
                dataset_split_fields = self.service.dataset_splits.training_fields(task, resources['dataset'], resources.get('model'))
            except Fault as error:
                blocking.append({'code': error.code, 'message': error.message, 'field': 'dataset_id'})
        from .api import NvidiaRuntime, NvidiaTrainingRuntime
        try:
            runtime = (NvidiaTrainingRuntime if draft['operation'] == 'train' else NvidiaRuntime).model_validate(runtime).model_dump()
        except (TypeError, ValueError):
            blocking.append({'code': 'UNSUPPORTED_PARAMETER', 'message': '参数不属于当前 NVIDIA 固定组合，尚未上传或执行。', 'field': 'runtime'})
        recipe, recipe_digest = None, None
        model = resources.get('model')
        if model and model['manifest_digest'] == MODEL_DIGEST:
            config = json.loads((Path(model['storage_path']) / 'tokenizer_config.json').read_text())
            template = config.get('chat_template')
            if not isinstance(template, str) or hashlib.sha256(template.encode()).hexdigest() != TEMPLATE_SHA256:
                blocking.append({'code': 'TOKENIZER_UNVERIFIED', 'message': '聊天模板与固定来源不一致。'})
            else:
                recipe, recipe_digest = build_recipe(Path(model['storage_path']), SimpleNamespace(chat_template=template), draft['operation'], runtime.get('max_seq_length'))
                if dataset_split_fields and recipe_digest != dataset_split_fields['dataset_split_ref']['tokenization_recipe_digest']:
                    blocking.append({'code': 'DATASET_SPLIT_CHECK_EXPIRED', 'message': '当前远端训练配方与来源组检查不同，请重新准备划分。', 'field': 'dataset_id'})
        inputs = {'model_manifest_digest': model['manifest_digest'] if model else None, 'source_code_digest': environment.get('source_code_digest') or source_identity()}
        if draft['operation'] == 'generate':
            inputs['prompt'] = draft['input'].get('prompt', '')
        elif draft['operation'] == 'train':
            allowed = {'engine', 'device_id', 'precision', 'seed', 'steps', 'batch_size', 'learning_rate', 'max_seq_length', 'lora_rank', 'lora_alpha', 'num_layers'}
            runtime = {key: value for key, value in runtime.items() if key in allowed}
            alpha = runtime.get('lora_alpha')
            if type(alpha) is float and alpha.is_integer():
                runtime['lora_alpha'] = int(alpha)
            inputs['dataset_manifest_digest'] = digest([{**item, 'path': 'train.jsonl'} for item in files if item['path'] == 'data/train.jsonl'])
        plan_fields = {}
        if draft.get('evaluation_plan_id'):
            plan = self.store.get('evaluation-plan', draft['evaluation_plan_id'])
            if plan['project_id'] != task['project_id']:
                raise Fault('PROJECT_MISMATCH', '评测计划不属于当前项目。', 403)
            resources['evaluation-plan'] = plan
            if draft['operation'] != 'train':
                blocking.append({'code': 'REMOTE_INPUT_UNSUPPORTED', 'message': '生成任务不绑定训练评测计划。'})
            else:
                try:
                    plan_fields = self.service.evaluation.plan_fields(plan)
                    if resources.get('dataset'):
                        self.service.evaluation.no_overlap(plan, resources['dataset'])
                    for kind in ('dataset', 'criteria'):
                        item = plan_fields[f'evaluation_{kind}_manifest'][0]
                        path = Path(plan_fields[f'evaluation_{kind}_path'])
                        name = 'evaluation/' + item['path']
                        files.append({**item, 'path': name})
                        sources.append({'source_path': str(path), 'root': str(path.parent), 'path': name, 'size': item['size'], 'sha256': item['sha256']})
                    inputs.update(evaluation_plan_digest=plan_fields['evaluation_plan_digest'], evaluation_plan_created_at=plan['created_at'], submitted_at=task.get('created_at') if task.get('created_at', '') >= plan['created_at'] else plan['created_at'])
                except Fault as error:
                    blocking.append({'code': error.code, 'message': error.message})
        remote = {'schema_version': 1, 'attempt_id': 'attempt-' + '0' * 32, 'executor_id': target['executor_id'], 'adapter_id': 'nvidia-text',
                  'operation': draft['operation'], 'inputs': files, 'input': inputs, 'runtime': runtime, 'transport': target.get('transport', 'loopback_http')}
        try:
            effective = validate_snapshot(remote)
        except ProtocolError as error:
            effective = runtime
            if not any(item['code'] == error.code for item in blocking):
                blocking.append({'code': error.code, 'message': error.message})
        result = {'target': self.target_fields(target), 'environment': environment, 'blocking': blocking, 'resources': resources,
                  'remote_snapshot': remote, 'source_files': sources, 'effective_config': effective, 'tokenization_recipe': recipe,
                  'tokenization_recipe_digest': recipe_digest, 'evaluation_fields': plan_fields,
                  'dataset_split_fields': dataset_split_fields,
                  'upload_summary': {'files': files, 'total_bytes': sum(item['size'] for item in files)}}
        result['identity_digest'] = digest({key: result[key] for key in ('target', 'environment', 'remote_snapshot', 'tokenization_recipe_digest', 'dataset_split_fields')})
        return result

    def preflight(self, task_id, revision):
        task = self.store.get('task', task_id)
        if task['draft_revision'] != revision:
            raise Fault('REVISION_CONFLICT', '草稿已更新，请重新检查。', 409)
        inspected = self.inspect(task)
        with self.store.transaction():
            if self.store.get('task', task_id)['draft_revision'] != revision or self.target_fields(self.store.get('execution-target', inspected['target']['id'])) != inspected['target']:
                raise Fault('REVISION_CONFLICT', '检查期间草稿或执行目标发生变化。', 409)
            check = self.service.resource('preflight', task['project_id'], task_id=task_id, draft_revision=revision,
                                          config_digest=digest(task['draft']), can_submit=not inspected['blocking'], blocking=inspected['blocking'],
                                          warnings=[{'code': 'REMOTE_TOKENIZATION_BEFORE_COMPUTE', 'message': '输入上传后，由执行器在分配模型之前完成真实分词、监督样本与上下文检查。'}], changes=[],
                                          environment=inspected['environment'], effective_config=inspected['effective_config'], execution_target=inspected['target'],
                                          upload_summary=inspected['upload_summary'], remote_identity_digest=inspected['identity_digest'],
                                          remote_snapshot_digest=digest(inspected['remote_snapshot']), tokenization_recipe=inspected['tokenization_recipe'],
                                          tokenization_recipe_digest=inspected['tokenization_recipe_digest'], check_report={'scope': 'manifest_and_recipe_verified', 'tokenization_check': 'on_executor_before_model_allocation'},
                                          expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())
            check['preflight_id'] = check['id']
            check.update(inspected['dataset_split_fields'])
            self.store.put('preflight', check)
        return self.service.public(check)

    def submit(self, task_id, payload, key):
        with self.store.transaction():
            if previous := self.store.replay('submit:' + task_id, key, payload):
                return self.service.public(self.store.get('attempt', previous['id']))
            task = self.store.get('task', task_id)
            check = self.store.get('preflight', payload['preflight_id'])
            if payload['expected_revision'] != task['draft_revision'] or check['draft_revision'] != task['draft_revision']:
                raise Fault('REVISION_CONFLICT', '草稿已更新，请重新检查。', 409)
            if check['task_id'] != task_id or check['config_digest'] != digest(task['draft']) or datetime.fromisoformat(check['expires_at']) <= datetime.now(timezone.utc):
                raise Fault('PREFLIGHT_EXPIRED', '检查已过期或不属于本次草稿。', 409)
        inspected = self.inspect(task)
        with self.store.transaction():
            if previous := self.store.replay('submit:' + task_id, key, payload):
                return self.service.public(self.store.get('attempt', previous['id']))
            if self.store.get('task', task_id)['draft_revision'] != task['draft_revision'] or self.target_fields(self.store.get('execution-target', inspected['target']['id'])) != inspected['target']:
                raise Fault('REVISION_CONFLICT', '提交检查期间草稿或目标发生变化。', 409)
            if not check['can_submit'] or inspected['blocking']:
                raise Fault('PREFLIGHT_BLOCKED', '远端环境或输入存在阻断项，尚未提交或上传。', 409, blocking=inspected['blocking'])
            if check['remote_identity_digest'] != inspected['identity_digest']:
                raise Fault('REMOTE_IDENTITY_CHANGED', '目标、代码、模型或数据身份已变化，请重新检查。', 409)
            if self.service.closed.is_set() or datetime.fromisoformat(check['expires_at']) <= datetime.now(timezone.utc):
                raise Fault('PREFLIGHT_EXPIRED', '检查过期或服务正在关闭。', 409)
            for kind, original in inspected['resources'].items():
                if self.store.get(kind, original['id']) != original:
                    raise Fault('REMOTE_INPUT_CHANGED', '提交期间输入资源发生变化。', 409)
            model = inspected['resources']['model']
            snapshot = {'schema_version': '1.1', 'project_id': task['project_id'], 'task_id': task_id, 'draft_revision': task['draft_revision'],
                        'kind': 'text', 'operation': task['operation'], 'execution_target_id': inspected['target']['id'], 'execution_target_name': inspected['target']['name'],
                        'execution_target': inspected['target'], 'validation_scope': inspected['target']['validation_scope'],
                        'transport': inspected['target']['transport'], 'model_execution': True,
                        'model_id': model['id'], 'model_version_id': model['version_id'], 'model_manifest_digest': model['manifest_digest'],
                        'model_manifest': model['manifest'], 'load_policy_ref': model.get('load_policy_ref'), 'input': task['draft']['input'],
                        'runtime': task['draft']['runtime'], 'requested_config': task['draft']['runtime'], 'effective_config': inspected['effective_config'],
                        'environment': inspected['environment'], 'upload_summary': inspected['upload_summary'], 'preflight_id': check['id'], 'submitted_at': now(),
                        'tokenization_recipe': inspected['tokenization_recipe'], 'tokenization_recipe_digest': inspected['tokenization_recipe_digest']}
            if dataset := inspected['resources'].get('dataset'):
                snapshot.update(dataset_id=dataset['id'], dataset_version_id=dataset['version_id'], dataset_manifest=dataset['manifest'], dataset_manifest_digest=dataset['manifest_digest'])
            snapshot.update(inspected['evaluation_fields'])
            snapshot.update(inspected['dataset_split_fields'])
            remote_snapshot = inspected['remote_snapshot']
            if remote_snapshot['input'].get('evaluation_plan_digest'):
                remote_snapshot['input']['submitted_at'] = snapshot['submitted_at']
                snapshot['evaluation_plan_created_at'] = remote_snapshot['input']['evaluation_plan_created_at']
            attempt = self.new_attempt(task, snapshot, remote_snapshot, inspected['source_files'])
            self.store.remember('submit:' + task_id, key, payload, self.service.public(attempt))
        self.start(attempt['id'])
        return self.service.public(attempt)

    def start(self, attempt_id, synchronize_only=False):
        with self.lock:
            if attempt_id in self.running:
                return
            self.running.add(attempt_id)
        thread = threading.Thread(target=self.run, args=(attempt_id, synchronize_only), daemon=True, name=f'remote-{attempt_id}')
        self.service.threads.add(thread)
        thread.start()

    def disconnected(self, attempt_id, error):
        with self.store.transaction():
            attempt = self.store.get('attempt', attempt_id)
            if attempt['state'] in TERMINAL:
                return
            attempt.update(connection_state='disconnected', recovery_required=True,
                           stop_status='unknown' if attempt['stop_status'] in {'pending', 'unknown'} else attempt['stop_status'])
            attempt['state_version'] += 1
            self.store.event(attempt, 'warning', {'code': error.code, 'message': '连接中断；保留原执行编号，重新连接后核实状态。'})

    def run(self, attempt_id, synchronize_only=False):
        try:
            attempt = self.store.get('attempt', attempt_id)
            client, _ = self.service.execution_targets.client(attempt['execution_target_id'], attempt['project_id'])
            if not synchronize_only and not attempt['remote_submitted']:
                total = sum(item['size'] for item in attempt['source_files'])
                transferred = 0
                for item in attempt['source_files']:
                    if self.service.closed.is_set():
                        return
                    def progress(offset, size):
                        with self.store.transaction():
                            current = self.store.get('attempt', attempt_id)
                            if current['state'] == 'cancelled':
                                raise Fault('CANCELLED', '上传已取消。', 409)
                            current.update(phase='uploading', progress=(transferred + offset) / max(total, 1))
                            self.store.event(current, 'upload_progress', {'uploaded_bytes': transferred + offset, 'total_bytes': total, 'path': item['path']})
                    def check_cancel():
                        if self.service.closed.is_set():
                            raise Fault('CONTROL_INTERRUPTED', '控制服务退出，上传已停止。', 409)
                        if self.store.get('attempt', attempt_id)['state'] == 'cancelled':
                            raise Fault('CANCELLED', '上传已取消。', 409)
                    uploaded = client.upload(Path(item['source_path']), [Path(item['root'])], progress=progress, check_cancel=check_cancel)
                    if uploaded != {'size': item['size'], 'sha256': item['sha256']}:
                        raise Fault('UPLOAD_INPUT_CHANGED', '实际上传文件与已确认的原范围不一致。', 409)
                    transferred += item['size']
                with self.store.transaction():
                    attempt = self.store.get('attempt', attempt_id)
                    if attempt['state'] == 'cancelled' or self.service.closed.is_set():
                        return
                    attempt['remote_submission_started'] = True
                    self.service.transition(attempt, 'running', '原输入已校验，正在向固定执行目标提交本次编号。')
                remote = client.submit(attempt['remote_snapshot'], attempt['remote_submit_key'])
                with self.store.transaction():
                    attempt = self.store.get('attempt', attempt_id)
                    attempt.update(remote_submitted=True, remote_state_version=remote['state_version'], recovery_required=False)
                    self.store.put('attempt', attempt)
            while not self.service.closed.is_set():
                if self.synchronize(attempt_id, client):
                    return
                time.sleep(0.25)
        except (ProtocolError, Fault) as error:
            if error.code in CONNECTION_ERRORS | {'CREDENTIAL_REQUIRED', 'RESOURCE_NOT_FOUND'}:
                self.disconnected(attempt_id, error)
            else:
                with self.store.transaction():
                    attempt = self.store.get('attempt', attempt_id)
                    if attempt['state'] not in TERMINAL:
                        if attempt['remote_submission_started']:
                            attempt.update(connection_state='disconnected', recovery_required=True, stop_status='unknown')
                            self.store.event(attempt, 'warning', {'code': error.code, 'message': error.message})
                        else:
                            attempt.update(compute_outcome='failed', terminal_reason=error.code)
                            self.service.transition(attempt, 'failed', error.message)
        except (OSError, ValueError, KeyError, TypeError):
            self.disconnected(attempt_id, Fault('REMOTE_SYNC_FAILED', '远端同步没有完成。', 503))
        finally:
            with self.lock:
                self.running.discard(attempt_id)
            self.service.threads.discard(threading.current_thread())
            self.service._release_if_idle()

    def synchronize(self, attempt_id, client):
        remote = client.sync(attempt_id)
        if remote.get('connection_state') != 'connected':
            raise ProtocolError('REMOTE_UNAVAILABLE', '连接中断。', 503)
        original = self.store.get('attempt', attempt_id)
        if remote.get('snapshot_sha256') != original['remote_snapshot_digest']:
            raise Fault('REMOTE_SNAPSHOT_CHANGED', '原执行快照摘要与本次任务不一致。', 409)
        if original.get('remote_cancel_intent') and remote['state'] not in TERMINAL | {'cancelling', 'finalizing'}:
            self.deliver_cancel(attempt_id, client, remote)
            remote = client.sync(attempt_id)
            if remote.get('connection_state') != 'connected':
                raise ProtocolError('REMOTE_UNAVAILABLE', '取消结果尚未确认。', 503)
        sealed = None
        terminal_ready = remote['state'] in TERMINAL and not remote.get('has_more_events')
        if remote['state'] == 'succeeded' and terminal_ready:
            sealed = client.manifest(attempt_id)
            if sealed['manifest']['snapshot_sha256'] != original['remote_snapshot_digest']:
                raise Fault('REMOTE_MANIFEST_CHANGED', '原产物清单没有绑定本次任务快照。', 409)
            if original['snapshot']['model_execution']:
                from adapters.nvidia_text.adapter import validate_completion
                effective = remote.get('effective_config', {})
                validate_completion(original['remote_snapshot'], effective, sealed['manifest']['files'])
                if (effective.get('tokenization_recipe_digest') != original['snapshot']['tokenization_recipe_digest']
                        or effective.get('source_code_digest') != original['remote_snapshot']['input']['source_code_digest']):
                    raise Fault('REMOTE_RECIPE_CHANGED', '实际执行配方或代码与已确认身份不一致。', 409)
        with self.store.transaction():
            attempt = self.store.get('attempt', attempt_id)
            if attempt['state'] in TERMINAL:
                return True
            for event in remote['events']:
                if event['sequence'] <= attempt['remote_event_cursor']:
                    continue
                if event['sequence'] != attempt['remote_event_cursor'] + 1:
                    raise Fault('REMOTE_EVENT_GAP', '远端事件缺失，未推进本机游标。', 409)
                payload = event['data']
                kind = event['type']
                if kind == 'token' and isinstance(payload.get('text'), str):
                    attempt['output_text'] = (attempt['output_text'] + payload['text'])[:16000]
                if kind == 'phase':
                    attempt['phase'] = payload.get('phase', 'running')
                self.store.event(attempt, 'remote_event', {'remote_sequence': event['sequence'], 'remote_type': kind, 'data': payload})
                attempt['remote_event_cursor'] = event['sequence']
            changed = attempt.get('remote_state_version') != remote['state_version'] or attempt.get('connection_state') != 'connected'
            stop_status = remote.get('stop_status', 'not_requested')
            if attempt.get('remote_cancel_intent') and remote['state'] not in TERMINAL and stop_status == 'not_requested':
                stop_status = attempt['stop_status'] if attempt['stop_status'] in {'pending', 'unknown'} else 'pending'
            attempt.update(remote_submitted=True, remote_state_version=remote['state_version'], connection_state='connected',
                           recovery_required=False, stop_status=stop_status)
            if sealed:
                attempt['remote_manifest_ref'] = sealed
                attempt['output_manifest_ref'] = self.service.seal_manifest({'artifacts': [{'path': item['name'], 'sha256': item['sha256'], 'size': item['size'], 'media_type': item['media_type']} for item in sealed['manifest']['files']], 'effective_config': remote.get('effective_config', {})})
                attempt.update(compute_outcome='succeeded', phase='collecting', progress=1)
                if attempt.get('remote_cancel_intent'):
                    attempt['cancel_outcome'] = 'completed_before_cancel_confirmed'
                    self.service.transition(attempt, 'running', '原计算已在取消确认前完成，现仅收回其既有产物。')
            elif remote['state'] in {'failed', 'cancelled'} and terminal_ready:
                attempt.update(compute_outcome=remote.get('compute_outcome', 'failed'), terminal_reason=remote.get('terminal_reason'))
                self.service.transition(attempt, remote['state'], '已核实原执行结束并释放进程资源。')
            elif changed or (attempt.get('remote_cancel_intent') and attempt['state'] != 'cancelling'):
                self.service.transition(attempt, 'cancelling' if remote['state'] == 'cancelling' or attempt.get('remote_cancel_intent') else 'running', '已同步原执行状态。')
            self.store.put('attempt', attempt)
        if sealed:
            self.collect(attempt_id)
            return True
        return terminal_ready

    def deliver_cancel(self, attempt_id, client, remote):
        # 仅同步线程访问该客户端；先持久化完整命令，再发出可重放的取消。
        with self.store.transaction():
            attempt = self.store.get('attempt', attempt_id)
            command = attempt.get('remote_cancel_command')
            if command is None or command.get('status') == 'rejected':
                command = {'key': identifier('cancel'), 'expected_state_version': remote['state_version'], 'status': 'pending'}
                attempt['remote_cancel_command'] = command
                self.store.put('attempt', attempt)
        try:
            result = client.cancel(attempt_id, command['expected_state_version'], command['key'])
            if result.get('connection_state') != 'connected':
                raise ProtocolError('REMOTE_UNAVAILABLE', '取消结果尚未确认。', 503)
        except ProtocolError as error:
            if error.code not in {'STATE_CONFLICT', 'ALREADY_FINALIZING'}:
                raise
            with self.store.transaction():
                attempt = self.store.get('attempt', attempt_id)
                if attempt.get('remote_cancel_command', {}).get('key') == command['key']:
                    attempt['remote_cancel_command']['status'] = 'rejected'
                    self.store.put('attempt', attempt)
            return
        with self.store.transaction():
            attempt = self.store.get('attempt', attempt_id)
            if attempt.get('remote_cancel_command', {}).get('key') == command['key']:
                attempt['remote_cancel_command']['status'] = 'acknowledged'
                self.store.put('attempt', attempt)

    def reconcile(self, attempt_id, payload, key):
        with self.store.transaction():
            scope = 'remote-reconcile:' + attempt_id
            if previous := self.store.replay(scope, key, payload):
                return self.service.public(self.store.get('attempt', previous['id']))
            attempt = self.store.get('attempt', attempt_id)
            if attempt['state_version'] != payload['expected_state_version']:
                raise Fault('REVISION_CONFLICT', '运行状态已更新，请刷新后再核实。', 409)
            self.service.execution_targets.client(attempt['execution_target_id'], attempt['project_id'])
            if not attempt['remote_submission_started'] and attempt.get('recovery_required'):
                attempt.update(stop_status='confirmed', recovery_required=False, connection_state='connected', compute_outcome='failed', terminal_reason='CONTROL_INTERRUPTED')
                self.service.transition(attempt, 'failed', '控制服务在上传阶段中断；已核实本次从未提交执行。可重新预览并开始新的传输。')
            self.store.remember(scope, key, payload, {'id': attempt_id})
        # 仅同步原编号；不提交新计算，也不重启原工作进程。
        if attempt['state'] not in TERMINAL:
            self.start(attempt_id, synchronize_only=True)
        return self.service.public(attempt)

    def control(self, attempt_id, payload, key, force=False):
        if force:
            raise Fault('CONTROL_NOT_SUPPORTED', '远端取消必须由原执行服务确认，不能按本机 PID 强制停止。', 409)
        with self.store.transaction():
            scope = 'remote-cancel:' + attempt_id
            if previous := self.store.replay(scope, key, payload):
                return self.service.public(self.store.get('attempt', previous['id']))
            attempt = self.store.get('attempt', attempt_id)
            if attempt['state_version'] != payload['expected_state_version']:
                raise Fault('REVISION_CONFLICT', '运行状态已更新，请刷新后再取消。', 409)
            if attempt['state'] in TERMINAL:
                return self.service.public(attempt)
            if not attempt['remote_submission_started']:
                attempt.update(stop_status='confirmed', compute_outcome='cancelled', terminal_reason='UPLOAD_CANCELLED')
                self.service.transition(attempt, 'cancelled', '已取消上传；本次尚未向执行服务提交计算。')
                self.store.remember(scope, key, payload, {'id': attempt_id})
                return self.service.public(attempt)
            attempt['remote_cancel_intent'] = True
            attempt['stop_status'] = 'unknown' if attempt['connection_state'] == 'disconnected' else 'pending'
            self.service.transition(attempt, 'cancelling', '取消已请求，等待原执行服务确认进程退出。')
            self.store.remember(scope, key, payload, {'id': attempt_id})
        self.start(attempt_id, synchronize_only=True)
        return self.service.public(self.store.get('attempt', attempt_id))

    def collect(self, attempt_id, payload=None, key=None):
        with self.lock:
            if attempt_id in self.collecting:
                raise Fault('COLLECTION_CONFLICT', '原产物正在收集，请等待当前收集完成。', 409)
            self.collecting.add(attempt_id)
        try:
            return self._collect(attempt_id, payload, key)
        finally:
            with self.lock:
                self.collecting.discard(attempt_id)

    def _collect(self, attempt_id, payload=None, key=None):
        with self.store.lock:
            attempt = self.store.get('attempt', attempt_id)
            if payload is not None:
                if previous := self.store.replay('collect:' + attempt_id, key, payload):
                    return previous
                if payload['expected_collection_version'] != attempt['collection_version'] or payload['manifest_digest'] != (attempt.get('output_manifest_ref') or {}).get('digest'):
                    raise Fault('COLLECTION_CONFLICT', '补收必须绑定当前原清单与收集版本。', 409)
                if attempt['state'] not in {'failed', 'cancelled'}:
                    raise Fault('COLLECTION_CONFLICT', '当前尝试无需补收或仍在执行。', 409)
            sealed = attempt.get('remote_manifest_ref')
            if attempt['compute_outcome'] != 'succeeded' or not sealed:
                raise Fault('MANIFEST_UNAVAILABLE', '原执行尚未提供完整产物清单。', 409)
        directory = self.service.root / 'runs' / attempt_id
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        collection_id = 'collection-' + digest({'attempt_id': attempt_id, 'remote_manifest_digest': sealed['manifest_sha256']})[:32]
        try:
            client, _ = self.service.execution_targets.client(attempt['execution_target_id'], attempt['project_id'])
            receipt = client.collect(attempt_id, sealed['manifest_sha256'], collection_id, directory)
            collected = Path(receipt['destination'])
            if attempt['snapshot'].get('model_execution'):
                from adapters.nvidia_text.adapter import validate_completion
                validate_completion(attempt['remote_snapshot'], attempt['output_manifest_ref']['effective_config'], sealed['manifest']['files'], collected)
            output = directory / 'output'
            manifest = [{'path': item['name'], 'size': item['size'], 'sha256': item['sha256']} for item in sealed['manifest']['files']]
            if output.exists():
                verify_manifest(output, manifest)
            else:
                temporary = Path(tempfile.mkdtemp(prefix='.output-copy-', dir=directory))
                try:
                    for item in sealed['manifest']['files']:
                        source, destination = collected / item['name'], temporary / item['name']
                        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        shutil.copyfile(source, destination)
                        destination.chmod(0o400)
                        with destination.open('rb') as stream:
                            os.fsync(stream.fileno())
                    verify_manifest(temporary, manifest)
                    sync_directory(temporary)
                    publish_directory(temporary, output)
                    sync_directory(directory)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            return self.service.collect(attempt_id, payload, key, _remote_ready=True)
        except (ProtocolError, Fault, OSError) as error:
            failure = {'code': getattr(error, 'code', 'REMOTE_COLLECTION_FAILED'), 'message': '原计算已结束，产物尚未完整收回；修复连接或存储后可只补收。'}
            with self.store.transaction():
                attempt = self.store.get('attempt', attempt_id)
                attempt.update(collection_state='failed', collection_version=attempt['collection_version'] + 1, terminal_reason=failure['code'])
                collection = self.service.resource('collection', attempt['project_id'], attempt_id=attempt_id, state='failed',
                                                   manifest_digest=attempt['output_manifest_ref']['digest'], error=failure, registered_artifact_ids=[])
                self.store.put('collection', collection)
                self.store.event(attempt, 'collection_changed', {'collection_id': collection['id'], 'state': 'failed', 'error': failure})
                self.service.transition(attempt, 'failed', failure['message'])
                if payload is not None:
                    self.store.remember('collect:' + attempt_id, key, payload, collection)
            return collection
