"""固定媒体工作流：输入版本、显式复用和原子推进，不负责启动计算。"""

import copy
import math
from pathlib import Path
import re

from .assets import copy_asset, file_hash, regular_path
from .media import DEFAULTS
from .media_assets import material_report
from .storage import Fault, digest, identifier, now

DEFINITION_VERSION = 'product-story-v1'
STEPS = ('image', 'video', 'audio')
LABELS = {'image': '商品图片', 'video': '商品视频', 'audio': '中文配音'}
TERMINAL = {'succeeded', 'failed', 'cancelled'}


def fields(payload, required, optional=()):
    if not isinstance(payload, dict) or not set(required) <= payload.keys() or set(payload) - set(required) - set(optional):
        raise Fault('INVALID_WORKFLOW_INPUT', '工作流请求字段不完整或包含未支持字段。')


class Workflows:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def get(self, run_id):
        with self.store.lock:
            run = self.store.get('workflow-run', run_id)
            run['step_attempts'] = [item for item in self.store.list('workflow-step-attempt', run['project_id']) if item['workflow_run_id'] == run_id]
            return self.service.public(run)

    def _revision(self, run, expected):
        if type(expected) is not int or expected != run['revision']:
            raise Fault('REVISION_CONFLICT', '工作流已更新，请刷新后重试。', 409, current_revision=run['revision'])

    def _step(self, run, step_id):
        if step_id not in STEPS:
            raise Fault('WORKFLOW_STEP_UNSUPPORTED', '当前工作流只支持图片、视频和中文配音。')
        return run['steps'][step_id]

    def _configuration(self, project_id, step_id, value):
        fields(value, ('model_id',), ('input', 'runtime'))
        if not isinstance(value['model_id'], str) or not value['model_id']:
            raise Fault('INVALID_WORKFLOW_INPUT', '请选择已导入的模型编号。')
        model = self.store.get('model', value['model_id'])
        if model['project_id'] != project_id:
            raise Fault('PROJECT_MISMATCH', '工作流模型不属于当前项目。', 403)
        if model.get('modality') != step_id or model.get('status') != 'ready':
            raise Fault('WORKFLOW_MODEL_MISMATCH', '请选择当前步骤已导入的固定媒体模型。', 409)
        runtime = copy.deepcopy(DEFAULTS[(step_id, 'generate')])
        supplied = value.get('runtime', {})
        if not isinstance(supplied, dict) or set(supplied) - set(runtime):
            raise Fault('UNSUPPORTED_PARAMETER', '工作流只接受当前媒体生成的已开放参数。')
        runtime.update(supplied)
        for name, default in DEFAULTS[(step_id, 'generate')].items():
            actual = runtime[name]
            if name == 'seed':
                valid = type(actual) is int and 0 <= actual < 2 ** 32
            elif name == 'speed':
                valid = type(actual) in (int, float) and math.isfinite(actual) and 0.5 <= actual <= 2
            elif type(default) in (int, float):
                valid = type(actual) in (int, float) and math.isfinite(actual) and actual == default
            else:
                valid = type(actual) is str and actual == default
            if not valid:
                raise Fault('UNSUPPORTED_PARAMETER', '参数不属于当前工作流已开放组合。', field='runtime.' + name)
        default_input = {} if step_id == 'video' else {'prompt': '', **({'negative_prompt': ''} if step_id == 'image' else {})}
        supplied_input = value.get('input', {})
        if not isinstance(supplied_input, dict) or set(supplied_input) - set(default_input):
            raise Fault('UNSUPPORTED_INPUT', '视频输入由本轮图片固定，其他步骤仅接受自己的文字输入。')
        default_input.update(supplied_input)
        maximum = 120 if step_id == 'audio' else 2000
        if any(not isinstance(text, str) or len(text) > maximum for text in default_input.values()):
            raise Fault('INVALID_WORKFLOW_INPUT', f'文字必须为字符串且不超过 {maximum} 字符。')
        if step_id == 'audio' and default_input['prompt'].strip() and not re.search(r'[\u3400-\u9fff]', default_input['prompt']):
            raise Fault('UNSUPPORTED_INPUT', '当前配音步骤需要用户填写中文文案。')
        return {'model_id': model['id'], 'input': default_input, 'runtime': runtime}

    def _busy(self, kind):
        for attempt in self.store.list('attempt'):
            if (attempt.get('state') not in TERMINAL or attempt.get('recovery_required')) and attempt.get('executor_type') != 'export' and attempt.get('snapshot', {}).get('kind') == kind:
                raise Fault('WORKFLOW_TARGET_BUSY', '目标类别仍有运行或停止结果待核实，请处理后再带入。', 409, attempt_id=attempt['id'], target_kind=kind)

    def _step_busy(self, step):
        if step['step_attempt_id']:
            step_attempt = self.store.get('workflow-step-attempt', step['step_attempt_id'])
            if step_attempt.get('attempt_id'):
                attempt = self.store.get('attempt', step_attempt['attempt_id'])
                if attempt['state'] not in TERMINAL or attempt.get('recovery_required'):
                    raise Fault('WORKFLOW_STEP_BUSY', '此步骤仍在运行，请先完成或取消后再修改或复用。', 409, attempt_id=attempt['id'])

    def _history(self, run, action, **value):
        run['history'].append({'action': action, 'revision': run['revision'], 'created_at': now(), **copy.deepcopy(value)})

    def _parents(self, run, step_id):
        parents = []
        for name in STEPS[:STEPS.index(step_id)]:
            step = run['steps'][name]
            if step['stale'] or not step['accepted']:
                raise Fault('WORKFLOW_UPSTREAM_STALE', '上游结果尚未接受或已经过期，请先完成上游步骤。', 409, step_id=name)
            parents.append(copy.deepcopy(step['accepted']))
        return parents

    def _new_input(self, run, step_id):
        step = run['steps'][step_id]
        upstream = self._parents(run, step_id)
        config = copy.deepcopy(step['configuration'])
        inputs = config['input']
        if step_id == 'video':
            inputs = {'material_id': upstream[-1]['material_id']}
        draft = {'kind': step_id, 'operation': 'generate', 'model_id': config['model_id'], 'dataset_id': None, 'adapter_id': None, 'evaluation_plan_id': None, 'checkpoint_id': None, 'input': inputs, 'runtime': config['runtime']}
        input_snapshot = {'draft': draft, 'upstream_refs': upstream}
        revision = step['input_revision'] + 1
        step_attempt = self.service.resource('workflow-step-attempt', run['project_id'], workflow_run_id=run['id'], step_id=step_id, input_revision=revision, input_digest=digest(input_snapshot), input_snapshot=input_snapshot, mode='compute', computed=False, attempt_id=None, source=None)
        ref = {'workflow_run_id': run['id'], 'definition_version': run['definition_version'], 'step_id': step_id, 'step_attempt_id': step_attempt['id'], 'input_revision': revision, 'input_digest': step_attempt['input_digest'], 'upstream_refs': upstream}
        task = self.service.resource('task', run['project_id'], name=f"{run['name']} · {LABELS[step_id]} · 第 {revision} 版", kind=step_id, operation='generate', draft_revision=1, draft=draft, immutable_draft=True, workflow_ref=ref)
        step_attempt['task_id'] = task['id']
        self.store.put('task', task)
        self.store.put('workflow-step-attempt', step_attempt)
        step.update(input_revision=revision, input_digest=step_attempt['input_digest'], task_id=task['id'], step_attempt_id=step_attempt['id'], accepted=None, stale=False)
        self._history(run, 'input_created', step_id=step_id, task_id=task['id'], step_attempt_id=step_attempt['id'], input_revision=revision, input_digest=step_attempt['input_digest'], input_snapshot=input_snapshot)

    def _invalidate(self, run, step_id):
        for name in STEPS[STEPS.index(step_id):]:
            step = run['steps'][name]
            if step['input_revision']:
                step['stale'] = True
                self._history(run, 'invalidated', step_id=name, input_revision=step['input_revision'], accepted=step['accepted'])
        run.update(current_step=step_id, status='active', result_id=None)

    def start(self, payload, key):
        fields(payload, ('project_id', 'name', 'definition_version', 'steps'))
        with self.store.transaction():
            if previous := self.store.replay('workflow:start', key, payload):
                return previous
            if payload['definition_version'] != DEFINITION_VERSION:
                raise Fault('WORKFLOW_DEFINITION_UNSUPPORTED', '工作流模板版本尚未实现。')
            if not isinstance(payload['name'], str) or not payload['name'].strip() or len(payload['name']) > 120:
                raise Fault('INVALID_WORKFLOW_INPUT', '请输入不超过 120 字符的工作流名称。')
            fields(payload['steps'], STEPS)
            steps = {name: {'configuration': self._configuration(payload['project_id'], name, payload['steps'][name]), 'input_revision': 0, 'input_digest': None, 'task_id': None, 'step_attempt_id': None, 'accepted': None, 'stale': False} for name in STEPS}
            run = self.service.resource('workflow-run', payload['project_id'], name=payload['name'], definition_version=DEFINITION_VERSION, revision=1, current_step='image', status='active', steps=steps, history=[], result_id=None)
            self._new_input(run, 'image')
            self.store.put('workflow-run', run)
            response = self.get(run['id'])
            self.store.remember('workflow:start', key, payload, response)
            return response

    def revise_input(self, run_id, step_id, payload, key):
        fields(payload, ('expected_revision', 'configuration'))
        scope = f'workflow:input:{run_id}:{step_id}'
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            run = self.store.get('workflow-run', run_id)
            self._revision(run, payload['expected_revision'])
            step = self._step(run, step_id)
            if not step['input_revision']:
                raise Fault('WORKFLOW_STEP_NOT_ENTERED', '此步骤尚未从本轮上游带入，请先完成上一步。', 409)
            self._step_busy(step)
            self._parents(run, step_id)
            config = self._configuration(run['project_id'], step_id, payload['configuration'])
            run['revision'] += 1
            self._invalidate(run, step_id)
            step['configuration'] = config
            self._new_input(run, step_id)
            self.store.put('workflow-run', run)
            response = self.get(run_id)
            self.store.remember(scope, key, payload, response)
            return response

    def submission_fields(self, task):
        """供提交前检查和提交事务共用；普通任务不受影响。"""
        ref = task.get('workflow_ref')
        if ref is None:
            return {}
        if not isinstance(ref, dict):
            raise Fault('WORKFLOW_IDENTITY_MISMATCH', '工作流任务缺少完整来源身份。', 409)
        run = self.store.get('workflow-run', ref.get('workflow_run_id'))
        step = self._step(run, ref.get('step_id'))
        record = self.store.get('workflow-step-attempt', ref.get('step_attempt_id'))
        expected = {'workflow_run_id': run['id'], 'definition_version': run['definition_version'], 'step_id': ref['step_id'], 'step_attempt_id': step['step_attempt_id'], 'input_revision': step['input_revision'], 'input_digest': step['input_digest'], 'upstream_refs': self._parents(run, ref['step_id'])}
        if ref != expected or run['project_id'] != task['project_id'] or run['current_step'] != ref['step_id'] or step['stale'] or step['accepted'] or step['task_id'] != task['id'] or not task.get('immutable_draft') or task['draft_revision'] != 1 or record['mode'] != 'compute' or record['task_id'] != task['id'] or record['input_snapshot'] != {'draft': task['draft'], 'upstream_refs': expected['upstream_refs']} or digest(record['input_snapshot']) != step['input_digest']:
            raise Fault('WORKFLOW_IDENTITY_MISMATCH', '此任务已不是本轮当前输入版本，请打开当前工作流步骤。', 409)
        if record['attempt_id'] is not None:
            raise Fault('WORKFLOW_STEP_ALREADY_SUBMITTED', '此步骤已提交；重复请求使用原命令键，重新计算需要显式重做。', 409, attempt_id=record['attempt_id'])
        if task['kind'] in {'image', 'audio'} and not task['draft']['input']['prompt'].strip():
            raise Fault('WORKFLOW_INPUT_REQUIRED', '请填写当前步骤的生成提示词或中文配音文案。', 409)
        return {'workflow_ref': copy.deepcopy(expected)}

    def bind_attempt(self, task, attempt):
        """仅在 Service.submit 的最终事务、snapshot_digest 计算之前调用。"""
        if not self.store.db.in_transaction:
            raise RuntimeError('绑定工作流尝试必须与提交处于同一事务')
        values = self.submission_fields(task)
        if not values:
            return
        if attempt.get('project_id') != task['project_id'] or attempt.get('task_id') != task['id'] or attempt.get('snapshot', {}).get('input') != task['draft']['input'] or attempt['snapshot'].get('runtime') != task['draft']['runtime'] or attempt['snapshot'].get('kind') != task['kind'] or attempt['snapshot'].get('operation') != task['operation'] or attempt['snapshot'].get('model_id') != task['draft']['model_id']:
            raise Fault('WORKFLOW_IDENTITY_MISMATCH', '提交快照与固定工作流草稿不一致。', 409)
        ref = values['workflow_ref']
        record = self.store.get('workflow-step-attempt', ref['step_attempt_id'])
        record.update(attempt_id=attempt['id'], computation_submitted=True, submitted_at=now())
        attempt['snapshot'].update(values)
        self.store.put('workflow-step-attempt', record)
        run = self.store.get('workflow-run', ref['workflow_run_id'])
        run['revision'] += 1
        self._history(run, 'submitted', step_id=ref['step_id'], step_attempt_id=record['id'], input_revision=ref['input_revision'], attempt_id=attempt['id'])
        self.store.put('workflow-run', run)

    def _source(self, run, record, artifact_id):
        if record['workflow_run_id'] != run['id'] or record['project_id'] != run['project_id']:
            raise Fault('WORKFLOW_SOURCE_MISMATCH', '所选步骤尝试不属于本轮工作流。', 409)
        step = self._step(run, record['step_id'])
        if run['current_step'] != record['step_id'] or step['stale'] or step['accepted'] or record['id'] != step['step_attempt_id'] or record['input_revision'] != step['input_revision'] or record['input_digest'] != step['input_digest']:
            raise Fault('WORKFLOW_SOURCE_MISMATCH', '只能接受本轮当前步骤、当前输入版本的结果。', 409)
        self._parents(run, record['step_id'])
        return self._attempt_for_record(run, record, artifact_id)

    def _attempt_for_record(self, run, record, artifact_id):
        if record['input_digest'] != digest(record['input_snapshot']) or record['mode'] not in {'compute', 'reused'}:
            raise Fault('WORKFLOW_SOURCE_MISMATCH', '步骤输入摘要或执行类型不完整。', 409)
        source_id = record['source']['attempt_id'] if record['mode'] == 'reused' else record['attempt_id']
        if not source_id:
            raise Fault('WORKFLOW_RESULT_REQUIRED', '本轮步骤尚无运行结果，请先生成或明确复用。', 409)
        attempt = self.store.get('attempt', source_id)
        snapshot = attempt.get('snapshot', {})
        if attempt['project_id'] != run['project_id'] or snapshot.get('kind') != record['step_id'] or snapshot.get('operation') != 'generate' or attempt.get('state') not in TERMINAL or attempt.get('recovery_required') or attempt.get('snapshot_digest') != digest(snapshot):
            raise Fault('WORKFLOW_SOURCE_MISMATCH', '运行来源、类别或快照完整性不符。', 409)
        if record['mode'] == 'compute':
            task = self.store.get('task', record['task_id'])
            if attempt['task_id'] != task['id'] or snapshot.get('workflow_ref') != task['workflow_ref'] or snapshot.get('input') != record['input_snapshot']['draft']['input'] or snapshot.get('runtime') != record['input_snapshot']['draft']['runtime'] or snapshot.get('model_id') != record['input_snapshot']['draft']['model_id']:
                raise Fault('WORKFLOW_SOURCE_MISMATCH', '运行没有绑定当前步骤的完整输入身份。', 409)
        else:
            if record['source']['artifact_id'] != artifact_id:
                raise Fault('WORKFLOW_SOURCE_MISMATCH', '请选择明确复用记录中固定的原产物。', 409)
            try:
                # 恢复只迁移运行路径；明确选择时的原快照摘要保持不变。
                self.service.checkpoints.verify_lineage(attempt, record['source']['snapshot_digest'])
            except (ValueError, KeyError, TypeError) as error:
                raise Fault('WORKFLOW_SOURCE_MISMATCH', '复用来源的原快照或恢复链不完整。', 409) from error
        return attempt

    def _verified_artifact(self, attempt, artifact_id):
        artifact = self.service.media.primary(attempt)
        if artifact['id'] != artifact_id:
            raise Fault('WORKFLOW_SOURCE_MISMATCH', '所选产物不是该步骤已完整保存的主媒体。', 409)
        return artifact

    def _same_source(self, attempt, artifact):
        if self.store.get('attempt', attempt['id']) != attempt or self.store.get('artifact', artifact['id']) != artifact:
            raise Fault('REVISION_CONFLICT', '处理期间原运行或产物记录已变化。', 409)
        # 文件是内容寻址资产；最终裁决再核查已保存原件，不能只相信旧记录。
        source = regular_path(artifact['storage_path'])
        if source.stat().st_size != artifact['size'] or file_hash(source) != artifact['sha256']:
            raise Fault('ARTIFACT_CORRUPT', '处理期间原媒体文件发生变化。', 409)

    def _work(self, run, attempt, artifact):
        existing = [item for item in self.store.list('work', run['project_id']) if item.get('artifact_id') == artifact['id']]
        if existing:
            work = existing[0]
            if work.get('source_attempt') != attempt['id'] or work.get('recipe') != attempt['snapshot']:
                raise Fault('WORKFLOW_SOURCE_MISMATCH', '既有作品与原运行身份不符。', 409)
            return work
        work = self.service.resource('work', run['project_id'], name=run['name'] + ' · ' + LABELS[attempt['snapshot']['kind']], kind=attempt['snapshot']['kind'], media_type=artifact['media_type'], artifact_id=artifact['id'], attempt_id=attempt['id'], source_attempt=attempt['id'], revision=1, favorite=False, recipe=attempt['snapshot'], text=None, quality_status='not_evaluated')
        self.store.put('work', work)
        return work

    def advance(self, run_id, payload, key):
        fields(payload, ('expected_revision', 'step_attempt_id', 'input_revision', 'artifact_ids'))
        if not isinstance(payload['artifact_ids'], list) or len(payload['artifact_ids']) != 1 or not isinstance(payload['artifact_ids'][0], str):
            raise Fault('INVALID_WORKFLOW_INPUT', '当前步骤需要且只能选择一项完整主媒体。')
        scope = 'workflow:advance:' + run_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            run = self.store.get('workflow-run', run_id)
            self._revision(run, payload['expected_revision'])
            record = self.store.get('workflow-step-attempt', payload['step_attempt_id'])
            if type(payload['input_revision']) is not int or payload['input_revision'] != record['input_revision']:
                raise Fault('WORKFLOW_SOURCE_MISMATCH', '输入版本与所选步骤尝试不符。', 409)
            attempt = self._source(run, record, payload['artifact_ids'][0])
        artifact = self._verified_artifact(attempt, payload['artifact_ids'][0])
        if record['mode'] == 'reused' and record['source']['artifact_sha256'] != artifact['sha256']:
            raise Fault('ARTIFACT_CORRUPT', '复用原产物与明确选择时的摘要不符。', 409)
        prepared = None
        if record['step_id'] == 'image':
            report = material_report(Path(artifact['storage_path']))
            if report['sha256'] != artifact['sha256'] or report['total_bytes'] != artifact['size']:
                raise Fault('ARTIFACT_CORRUPT', '转换素材期间图片发生变化。', 409)
            destination = copy_asset(Path(artifact['storage_path']), self.service.root / 'assets', report['manifest'], report['manifest_digest'])
            prepared = (report, destination)
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            latest = self.store.get('workflow-run', run_id)
            self._revision(latest, payload['expected_revision'])
            current_record = self.store.get('workflow-step-attempt', record['id'])
            if current_record != record or self._source(latest, current_record, artifact['id']) != attempt:
                raise Fault('REVISION_CONFLICT', '处理期间当前步骤来源已变化。', 409)
            index = STEPS.index(record['step_id'])
            target = STEPS[index + 1] if index + 1 < len(STEPS) else None
            if target:
                self._busy(target)
            self._same_source(attempt, artifact)
            work = self._work(latest, attempt, artifact)
            accepted = {'step_id': record['step_id'], 'step_attempt_id': record['id'], 'input_revision': record['input_revision'], 'input_digest': record['input_digest'], 'attempt_id': attempt['id'], 'artifact_id': artifact['id'], 'artifact_sha256': artifact['sha256'], 'artifact_size': artifact['size'], 'work_id': work['id'], 'mode': record['mode'], 'computed': record['mode'] == 'compute', 'accepted_at': now()}
            if prepared:
                report, destination = prepared
                material_fields = {name: report[name] for name in ('kind', 'media_type', 'manifest', 'manifest_digest', 'entrypoint', 'total_bytes', 'width', 'height', 'checks')}
                material = self.service.resource('material', run['project_id'], name=work['name'], version_id=identifier('version'), revision=1, status='ready', storage_path=str(destination), source_work_id=work['id'], source_attempt_id=attempt['id'], source_workflow_run_id=run_id, source_step_attempt_id=record['id'], **material_fields)
                self.store.put('material', material)
                accepted.update(material_id=material['id'], material_manifest_digest=material['manifest_digest'])
            latest['revision'] += 1
            if record['mode'] == 'compute':
                current_record.update(computed=True, accepted_artifact_id=artifact['id'])
                self.store.put('workflow-step-attempt', current_record)
            latest['steps'][record['step_id']]['accepted'] = accepted
            self._history(latest, 'accepted', step_id=record['step_id'], accepted=accepted)
            if target:
                self._new_input(latest, target)
                latest['current_step'] = target
            else:
                latest.update(current_step=None, status='ready_to_save')
            self.store.put('workflow-run', latest)
            response = self.get(run_id)
            self.store.remember(scope, key, payload, response)
            return response

    def reuse_output(self, run_id, payload, key):
        fields(payload, ('expected_revision', 'step_id', 'input_revision', 'source_attempt_id', 'artifact_id'))
        scope = 'workflow:reuse:' + run_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            run = self.store.get('workflow-run', run_id)
            self._revision(run, payload['expected_revision'])
            step = self._step(run, payload['step_id'])
            if type(payload['input_revision']) is not int or payload['input_revision'] != step['input_revision'] or not step['input_revision'] or run['current_step'] != payload['step_id'] or step['stale'] or step['accepted']:
                raise Fault('WORKFLOW_SOURCE_MISMATCH', '只能为本轮当前待接受步骤明确选择旧结果。', 409)
            self._step_busy(step)
            self._parents(run, payload['step_id'])
            attempt = self.store.get('attempt', payload['source_attempt_id'])
            if attempt['project_id'] != run['project_id'] or attempt['snapshot'].get('kind') != payload['step_id'] or attempt['snapshot'].get('operation') != 'generate' or attempt['state'] not in TERMINAL or attempt.get('recovery_required') or attempt.get('snapshot_digest') != digest(attempt['snapshot']):
                raise Fault('WORKFLOW_SOURCE_MISMATCH', '复用来源必须是本项目相同媒体类别的完整生成。', 409)
        artifact = self._verified_artifact(attempt, payload['artifact_id'])
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            latest = self.store.get('workflow-run', run_id)
            self._revision(latest, payload['expected_revision'])
            step = self._step(latest, payload['step_id'])
            self._step_busy(step)
            self._same_source(attempt, artifact)
            old_record = self.store.get('workflow-step-attempt', step['step_attempt_id'])
            old_snapshot = attempt['snapshot']
            current_draft = old_record['input_snapshot']['draft']
            differences = {name: {'current': current_draft.get(name), 'source': old_snapshot.get(name)} for name in ('model_id', 'input', 'runtime') if current_draft.get(name) != old_snapshot.get(name)}
            source_ref = old_snapshot.get('workflow_ref') or {}
            if old_record['input_snapshot']['upstream_refs'] != source_ref.get('upstream_refs', []):
                differences['upstream_refs'] = {'current': copy.deepcopy(old_record['input_snapshot']['upstream_refs']), 'source': copy.deepcopy(source_ref.get('upstream_refs', []))}
            source = {'attempt_id': attempt['id'], 'artifact_id': artifact['id'], 'artifact_sha256': artifact['sha256'], 'snapshot_digest': attempt['snapshot_digest'], 'workflow_ref': copy.deepcopy(old_snapshot.get('workflow_ref')), 'source_input_revision': source_ref.get('input_revision', old_snapshot.get('draft_revision')), 'source_input': copy.deepcopy(old_snapshot.get('input')), 'differences': differences, 'selection_action': 'explicit_reuse_output', 'selected_at': now()}
            reused = self.service.resource('workflow-step-attempt', run['project_id'], workflow_run_id=run_id, step_id=payload['step_id'], input_revision=step['input_revision'], input_digest=step['input_digest'], input_snapshot=copy.deepcopy(old_record['input_snapshot']), mode='reused', computed=False, attempt_id=None, task_id=None, supersedes_step_attempt_id=old_record['id'], source=source)
            self.store.put('workflow-step-attempt', reused)
            step.update(step_attempt_id=reused['id'], task_id=None)
            latest['revision'] += 1
            self._history(latest, 'reused', step_id=payload['step_id'], step_attempt_id=reused['id'], input_revision=step['input_revision'], source=source)
            self.store.put('workflow-run', latest)
            response = self.get(run_id)
            self.store.remember(scope, key, payload, response)
            return response

    def save_result(self, run_id, payload, key):
        fields(payload, ('expected_revision',), ('name',))
        scope = 'workflow:save:' + run_id
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            run = self.store.get('workflow-run', run_id)
            self._revision(run, payload['expected_revision'])
            if run['status'] not in {'ready_to_save', 'saved'} or any(step['stale'] or not step['accepted'] for step in run['steps'].values()):
                raise Fault('WORKFLOW_INCOMPLETE', '工作流仍有未完成或过期步骤，不能保存为本轮完整结果。', 409)
            accepted = [copy.deepcopy(run['steps'][name]['accepted']) for name in STEPS]
            for item in accepted:
                step = run['steps'][item['step_id']]
                record = self.store.get('workflow-step-attempt', item['step_attempt_id'])
                if record['workflow_run_id'] != run_id or record['id'] != step['step_attempt_id'] or record['input_revision'] != step['input_revision'] or record['input_digest'] != step['input_digest'] or record['input_snapshot']['upstream_refs'] != self._parents(run, item['step_id']) or item['input_revision'] != step['input_revision'] or item['input_digest'] != step['input_digest'] or item['mode'] != record['mode'] or item['computed'] != (record['mode'] == 'compute'):
                    raise Fault('WORKFLOW_SOURCE_MISMATCH', '已接受链没有绑定本轮当前输入，请重新接受有效来源。', 409)
                if self._attempt_for_record(run, record, item['artifact_id'])['id'] != item['attempt_id']:
                    raise Fault('WORKFLOW_SOURCE_MISMATCH', '已接受产物与步骤来源不符。', 409)
        verified = []
        for item in accepted:
            attempt = self.store.get('attempt', item['attempt_id'])
            artifact = self._verified_artifact(attempt, item['artifact_id'])
            if artifact['sha256'] != item['artifact_sha256']:
                raise Fault('ARTIFACT_CORRUPT', '已接受媒体摘要与当前原产物不符。', 409)
            verified.append((attempt, artifact))
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            latest = self.store.get('workflow-run', run_id)
            self._revision(latest, payload['expected_revision'])
            for item, (attempt, artifact) in zip(accepted, verified):
                self._same_source(attempt, artifact)
                work = self.store.get('work', item['work_id'])
                if work['project_id'] != run['project_id'] or work.get('artifact_id') != artifact['id'] or work.get('recipe') != attempt['snapshot']:
                    raise Fault('WORKFLOW_SOURCE_MISMATCH', '当前作品与工作流接受来源不符。', 409)
            if latest['result_id']:
                result = self.store.get('workflow-result', latest['result_id'])
                if payload.get('name') is not None and payload['name'] != result['name']:
                    raise Fault('WORKFLOW_RESULT_IMMUTABLE', '已保存结果名称和引用保持固定，请使用已有结果。', 409)
            else:
                name = payload.get('name') or run['name']
                if not isinstance(name, str) or not name.strip() or len(name) > 120:
                    raise Fault('INVALID_WORKFLOW_INPUT', '结果名称须为不超过 120 字符的文字。')
                result = self.service.resource('workflow-result', run['project_id'], name=name, workflow_run_id=run_id, workflow_revision=run['revision'], definition_version=run['definition_version'], items=accepted, media_combined=False, quality_status='not_evaluated')
                self.store.put('workflow-result', result)
                latest.update(revision=latest['revision'] + 1, result_id=result['id'], status='saved')
                self._history(latest, 'saved', result_id=result['id'], items=accepted)
                self.store.put('workflow-run', latest)
            response = {'workflow_run': self.get(run_id), 'result': self.service.public(result)}
            self.store.remember(scope, key, payload, response)
            return response
