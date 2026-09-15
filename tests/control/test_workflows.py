"""真实 SQLite 与小型媒体字节验证工作流合同；没有模型生成或 UI 验收声明。"""

import copy
from concurrent.futures import ThreadPoolExecutor
import struct
import threading
import wave

import pytest

from test_control import rig
from test_media_assets import png
from ailab_control.assets import file_hash
from ailab_control.media import PRIMARY
from ailab_control.service import Service
from ailab_control.storage import Fault, digest
from ailab_control.workflows import DEFINITION_VERSION, STEPS, Workflows
import ailab_control.workflows as workflow_module


@pytest.fixture
def workflow(rig):
    service = rig[1]
    project = service.project({'name': '工作流 CPU 合同夹具'})
    steps = {}
    with service.store.transaction():
        for kind in STEPS:
            model = service.resource('model', project['id'], name=kind + ' 模型身份夹具', modality=kind, status='ready', version_id='固定夹具版本', manifest_digest='0' * 64)
            service.store.put('model', model)
            steps[kind] = {'model_id': model['id']}
    steps['image']['input'] = {'prompt': '蓝色陶瓷杯产品图', 'negative_prompt': '模糊'}
    steps['audio']['input'] = {'prompt': '这一只蓝色陶瓷杯，陪伴你的日常。'}
    payload = {'project_id': project['id'], 'name': '商品展示', 'definition_version': DEFINITION_VERSION, 'steps': steps}
    return Workflows(service), payload


def fails(code, action):
    with pytest.raises(Fault) as caught:
        action()
    assert caught.value.code == code, caught.value.message
    return caught.value


def complete(workflows, run):
    """只制造明确标记的合同产物，通过原收集器校验并登记真实文件。"""
    service = workflows.service
    kind = run['current_step']
    task = service.store.get('task', run['steps'][kind]['task_id'])
    snapshot = {**copy.deepcopy(task['draft']), 'task_id': task['id'], 'project_id': task['project_id'], 'fixture_only': True}
    attempt = service.resource('attempt', task['project_id'], task_id=task['id'], state='finalizing', state_version=1, snapshot=snapshot, compute_outcome='succeeded', collection_state='not_started', collection_version=0, output_manifest_ref=None, last_event_sequence=0, terminal_reason=None)
    with service.store.transaction():
        workflows.bind_attempt(task, attempt)
        attempt['snapshot_digest'] = digest(attempt['snapshot'])
        service.store.put('attempt', attempt)
    output = service.root / 'runs' / attempt['id'] / 'output'
    relative, mime = PRIMARY[kind]
    primary = output / relative
    primary.parent.mkdir(parents=True)
    if kind == 'image':
        png(primary, width=8, height=8)
    elif kind == 'audio':
        with wave.open(str(primary), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(24000)
            stream.writeframes(b'\0\0' * 240)
    else:
        # 仅测试控制层的容器边界，不冒充可播放的神经网络视频。
        def box(name, body):
            return struct.pack('>I', 8 + len(body)) + name + body
        primary.write_bytes(box(b'ftyp', b'isom\0\0\0\0isomiso2') + box(b'moov', b'fixture-index') + box(b'mdat', b'fixture-video'))
    metadata = output / 'fixture.json'
    metadata.write_text('{"fixture_only":true,"model_execution":false}')
    with service.store.transaction():
        attempt = service.store.get('attempt', attempt['id'])
        attempt['output_manifest_ref'] = service.seal_manifest({'artifacts': [{'path': relative, 'sha256': file_hash(primary), 'media_type': mime}, {'path': metadata.name, 'sha256': file_hash(metadata), 'media_type': 'application/json'}]})
        service.store.put('attempt', attempt)
    assert service.collect(attempt['id'])['state'] == 'succeeded'
    latest = workflows.get(run['id'])
    attempt = service.store.get('attempt', attempt['id'])
    artifact = service.media.primary(attempt)
    return latest, attempt, artifact


def advance_payload(run, artifact):
    step = run['steps'][run['current_step']]
    return {'expected_revision': run['revision'], 'step_attempt_id': step['step_attempt_id'], 'input_revision': step['input_revision'], 'artifact_ids': [artifact['id']]}


def finish(workflows, payload, key):
    run = workflows.start(payload, key)
    attempts = []
    for kind in STEPS:
        run, attempt, artifact = complete(workflows, run)
        attempts.append((attempt, artifact))
        run = workflows.advance(run['id'], advance_payload(run, artifact), key + '-' + kind)
    return run, attempts


def table_state(workflows):
    with workflows.store.lock:
        return [tuple(row) for row in workflows.store.db.execute('SELECT id,kind,project_id,body FROM resources ORDER BY id')]


def busy_attempt(workflows, project_id, kind='video', state='running'):
    with workflows.store.transaction():
        attempt = workflows.service.resource('attempt', project_id, state=state, snapshot={'kind': kind}, fixture_only=True)
        workflows.store.put('attempt', attempt)
    return attempt


def test_start_has_independent_rounds_and_payload_bound_idempotency(workflow):
    workflows, payload = workflow
    first = workflows.start(payload, 'round-one')
    assert workflows.start(payload, 'round-one') == first
    changed = copy.deepcopy(payload)
    changed['steps']['image']['input']['prompt'] = '红色陶瓷茶壶'
    fails('IDEMPOTENCY_CONFLICT', lambda: workflows.start(changed, 'round-one'))
    second = workflows.start(payload, 'round-two')
    assert first['id'] != second['id']
    assert first['steps']['image']['task_id'] != second['steps']['image']['task_id']
    assert second['steps']['video']['input_revision'] == 0 and second['steps']['video']['accepted'] is None
    assert second['steps']['audio']['task_id'] is None
    task = workflows.store.get('task', second['steps']['image']['task_id'])
    assert task['immutable_draft'] is True
    assert task['workflow_ref']['workflow_run_id'] == second['id']
    fails('CONTROL_NOT_SUPPORTED', lambda: workflows.service.save_draft(task['id'], {'expected_revision': 1, 'draft': task['draft']}))


def test_submit_binding_is_immutable_and_duplicate_requires_original_command_replay(workflow):
    workflows, payload = workflow
    run = workflows.start(payload, 'bind-round')
    task = workflows.store.get('task', run['steps']['image']['task_id'])
    with pytest.raises(RuntimeError, match='同一事务'):
        workflows.bind_attempt(task, {})
    run, attempt, _ = complete(workflows, run)
    ref = attempt['snapshot']['workflow_ref']
    assert ref == task['workflow_ref']
    assert attempt['snapshot_digest'] == digest(attempt['snapshot'])
    fails('WORKFLOW_STEP_ALREADY_SUBMITTED', lambda: workflows.submission_fields(task))
    original = workflows.store.get('workflow-step-attempt', ref['step_attempt_id'])
    assert original['attempt_id'] == attempt['id'] and original['computed'] is False
    assert workflows.submission_fields({'id': 'ordinary-task'}) == {}


def test_two_complete_rounds_keep_three_original_works_and_no_implicit_mix(workflow):
    workflows, payload = workflow
    first, sources = finish(workflows, payload, 'first-round')
    saved = workflows.save_result(first['id'], {'expected_revision': first['revision']}, 'first-save')
    assert [item['step_id'] for item in saved['result']['items']] == list(STEPS)
    assert saved['result']['media_combined'] is False
    for item, (attempt, artifact) in zip(saved['result']['items'], sources):
        work = workflows.store.get('work', item['work_id'])
        assert work['artifact_id'] == artifact['id'] and work['recipe'] == attempt['snapshot']
        assert work['media_type'] == PRIMARY[item['step_id']][1]
    video = sources[1][0]['snapshot']
    image_ref = video['workflow_ref']['upstream_refs'][0]
    assert video['input'] == {'material_id': image_ref['material_id']}
    material = workflows.store.get('material', image_ref['material_id'])
    assert material['source_attempt_id'] == sources[0][0]['id']
    audio = sources[2][0]['snapshot']
    assert audio['input'] == payload['steps']['audio']['input']
    assert audio['workflow_ref']['upstream_refs'][-1]['artifact_id'] == sources[1][1]['id']
    second = workflows.start(payload, 'second-round')
    assert all(step['accepted'] is None for step in second['steps'].values())
    fails('WORKFLOW_RESULT_REQUIRED', lambda: workflows.advance(second['id'], advance_payload(second, sources[0][1]), 'no-old-fallback'))
    second, second_sources = finish(workflows, payload, 'third-fully-executed-round')
    assert {item[0]['id'] for item in sources}.isdisjoint(item[0]['id'] for item in second_sources)
    assert all(item['workflow_run_id'] == second['id'] for item in second['step_attempts'])


def test_old_round_attempt_cannot_advance_without_explicit_reuse(workflow):
    workflows, payload = workflow
    first = workflows.start(payload, 'old-source')
    first, _, artifact = complete(workflows, first)
    second = workflows.start(payload, 'new-round')
    body = advance_payload(first, artifact)
    body['expected_revision'] = second['revision']
    before = table_state(workflows)
    fails('WORKFLOW_SOURCE_MISMATCH', lambda: workflows.advance(second['id'], body, 'reject-other-round'))
    assert table_state(workflows) == before


def test_explicit_reuse_creates_record_preserves_compute_identity_and_differences(workflow):
    workflows, payload = workflow
    run = workflows.start(payload, 'reuse-round')
    run, attempt, artifact = complete(workflows, run)
    original_record = workflows.store.get('workflow-step-attempt', run['steps']['image']['step_attempt_id'])
    edit = copy.deepcopy(payload['steps']['image'])
    edit['input']['prompt'] = '同一个杯子的近景照片'
    run = workflows.revise_input(run['id'], 'image', {'expected_revision': run['revision'], 'configuration': edit}, 'reuse-new-input')
    pending_record = workflows.store.get('workflow-step-attempt', run['steps']['image']['step_attempt_id'])
    body = {'expected_revision': run['revision'], 'step_id': 'image', 'input_revision': run['steps']['image']['input_revision'], 'source_attempt_id': attempt['id'], 'artifact_id': artifact['id']}
    reused = workflows.reuse_output(run['id'], body, 'explicit-reuse')
    assert workflows.reuse_output(run['id'], body, 'explicit-reuse') == reused
    record = workflows.store.get('workflow-step-attempt', reused['steps']['image']['step_attempt_id'])
    assert record['mode'] == 'reused' and record['computed'] is False and record['attempt_id'] is None
    assert record['id'] not in {original_record['id'], pending_record['id']}
    assert workflows.store.get('workflow-step-attempt', original_record['id']) == original_record
    assert workflows.store.get('workflow-step-attempt', pending_record['id']) == pending_record
    assert record['source']['differences']['input']['source'] == attempt['snapshot']['input']
    assert record['source']['workflow_ref']['input_revision'] == 1
    assert reused['current_step'] == 'image' and reused['steps']['video']['task_id'] is None
    advanced = workflows.advance(run['id'], advance_payload(reused, artifact), 'accept-reused-image')
    assert advanced['steps']['image']['accepted']['computed'] is False
    assert advanced['steps']['image']['accepted']['mode'] == 'reused'
    changed = {**body, 'input_revision': 999}
    fails('IDEMPOTENCY_CONFLICT', lambda: workflows.reuse_output(run['id'], changed, 'explicit-reuse'))


def test_upstream_redo_makes_downstream_stale_but_keeps_saved_result_and_history(workflow):
    workflows, payload = workflow
    run, sources = finish(workflows, payload, 'redo-round')
    saved = workflows.save_result(run['id'], {'expected_revision': run['revision']}, 'save-before-redo')
    run = saved['workflow_run']
    old_result = workflows.store.get('workflow-result', saved['result']['id'])
    old_task = workflows.store.get('task', run['steps']['image']['task_id'])
    old_history = copy.deepcopy(run['history'])
    edit_body = {'expected_revision': run['revision'], 'configuration': payload['steps']['image']}
    edited = workflows.revise_input(run['id'], 'image', edit_body, 'redo-same-input')
    assert workflows.revise_input(run['id'], 'image', edit_body, 'redo-same-input') == edited
    assert edited['steps']['image']['input_revision'] == 2
    assert edited['steps']['image']['task_id'] != old_task['id']
    assert edited['steps']['video']['stale'] and edited['steps']['audio']['stale']
    assert edited['steps']['video']['accepted']['artifact_id'] == sources[1][1]['id']
    assert edited['history'][:len(old_history)] == old_history
    assert workflows.store.get('workflow-result', old_result['id']) == old_result
    assert workflows.store.get('task', old_task['id']) == old_task
    fails('WORKFLOW_INCOMPLETE', lambda: workflows.save_result(run['id'], {'expected_revision': edited['revision']}, 'reject-stale-save'))
    fails('WORKFLOW_IDENTITY_MISMATCH', lambda: workflows.submission_fields(old_task))
    body = advance_payload(run | {'current_step': 'video'}, sources[1][1])
    body['expected_revision'] = edited['revision']
    fails('WORKFLOW_SOURCE_MISMATCH', lambda: workflows.advance(run['id'], body, 'reject-old-downstream'))


@pytest.mark.parametrize('state', ['queued', 'running', 'paused', 'finalizing', 'cancelling'])
def test_busy_target_rejects_without_any_acceptance_draft_or_position_change(workflow, state):
    workflows, payload = workflow
    run = workflows.start(payload, 'busy-round')
    run, _, artifact = complete(workflows, run)
    busy_attempt(workflows, payload['project_id'], state=state)
    before = table_state(workflows)
    fails('WORKFLOW_TARGET_BUSY', lambda: workflows.advance(run['id'], advance_payload(run, artifact), 'busy-advance'))
    assert table_state(workflows) == before
    assert not workflows.store.list('material') and not workflows.store.list('work')


@pytest.mark.parametrize('terminal', ['succeeded', 'cancelled'])
@pytest.mark.parametrize('same_key', [False, True])
def test_target_just_finished_two_concurrent_advances_only_commit_once(workflow, monkeypatch, terminal, same_key):
    workflows, payload = workflow
    run = workflows.start(payload, 'race-round')
    run, _, artifact = complete(workflows, run)
    busy = busy_attempt(workflows, payload['project_id'])
    with workflows.store.transaction():
        busy['state'] = terminal
        workflows.store.put('attempt', busy)
    barrier = threading.Barrier(2)
    original = workflows._verified_artifact
    def synchronized(*args):
        result = original(*args)
        barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(workflows, '_verified_artifact', synchronized)
    body = advance_payload(run, artifact)
    def submit(key):
        try:
            return workflows.advance(run['id'], body, key)
        except Fault as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ['compete-a', 'compete-a' if same_key else 'compete-b']))
    if same_key:
        assert isinstance(results[0], dict) and results[0] == results[1]
    else:
        assert sum(isinstance(item, dict) for item in results) == 1
        assert 'REVISION_CONFLICT' in results
    assert len(workflows.store.list('material')) == len(workflows.store.list('work')) == 1
    latest = workflows.get(run['id'])
    assert latest['revision'] == run['revision'] + 1 and latest['current_step'] == 'video'
    assert len([entry for entry in latest['history'] if entry['action'] == 'accepted']) == 1


def test_target_becoming_busy_after_copy_is_rechecked_in_final_transaction(workflow, monkeypatch):
    workflows, payload = workflow
    run = workflows.start(payload, 'late-busy-round')
    run, _, artifact = complete(workflows, run)
    original = workflow_module.copy_asset
    def occupy_after_copy(*args, **kwargs):
        destination = original(*args, **kwargs)
        busy_attempt(workflows, payload['project_id'])
        return destination
    monkeypatch.setattr(workflow_module, 'copy_asset', occupy_after_copy)
    fails('WORKFLOW_TARGET_BUSY', lambda: workflows.advance(run['id'], advance_payload(run, artifact), 'late-busy'))
    assert workflows.get(run['id']) == run
    assert not workflows.store.list('work') and not workflows.store.list('material')


@pytest.mark.parametrize('damage', ['bytes', 'manifest', 'collection', 'snapshot'])
def test_incomplete_or_tampered_results_cannot_advance(workflow, damage):
    workflows, payload = workflow
    run = workflows.start(payload, 'tamper-round')
    run, attempt, artifact = complete(workflows, run)
    if damage == 'bytes':
        from pathlib import Path
        path = Path(artifact['storage_path'])
        path.chmod(0o600)
        path.write_bytes(b'wrong media')
    elif damage == 'manifest':
        attempt['output_manifest_ref']['artifacts'][0]['sha256'] = '1' * 64
    elif damage == 'collection':
        attempt['collection_state'] = 'failed'
    else:
        attempt['snapshot']['workflow_ref']['input_revision'] = 99
        attempt['snapshot_digest'] = digest(attempt['snapshot'])
    with workflows.store.transaction():
        workflows.store.put('attempt', attempt)
    before = table_state(workflows)
    with pytest.raises(Fault):
        workflows.advance(run['id'], advance_payload(run, artifact), 'bad-source')
    assert table_state(workflows) == before


def test_source_bytes_changed_after_first_validation_are_rejected_at_commit(workflow, monkeypatch):
    workflows, payload = workflow
    run, _ = finish(workflows, payload, 'late-source-round')
    original = workflows._verified_artifact
    def change_after_validation(*args):
        from pathlib import Path
        artifact = original(*args)
        if artifact['media_type'] == 'audio/wav':
            path = Path(artifact['storage_path'])
            raw = path.read_bytes()
            path.chmod(0o600)
            path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        return artifact
    monkeypatch.setattr(workflows, '_verified_artifact', change_after_validation)
    before = table_state(workflows)
    fails('ARTIFACT_CORRUPT', lambda: workflows.save_result(run['id'], {'expected_revision': run['revision']}, 'late-mutated-save'))
    assert table_state(workflows) == before


def test_save_is_idempotent_and_cannot_silently_rename_frozen_result(workflow):
    workflows, payload = workflow
    run, _ = finish(workflows, payload, 'save-idempotent-round')
    body = {'expected_revision': run['revision'], 'name': '第一份完整作品组'}
    result = workflows.save_result(run['id'], body, 'save-once')
    assert workflows.save_result(run['id'], body, 'save-once') == result
    fails('IDEMPOTENCY_CONFLICT', lambda: workflows.save_result(run['id'], body | {'name': '另一个名称'}, 'save-once'))
    fails('WORKFLOW_RESULT_IMMUTABLE', lambda: workflows.save_result(run['id'], {'expected_revision': result['workflow_run']['revision'], 'name': '另一个名称'}, 'cannot-rename'))
    assert len(workflows.store.list('workflow-result')) == 1


def test_model_project_input_and_fixed_runtime_fail_closed(workflow):
    workflows, payload = workflow
    for mutation in ['definition', 'kind', 'model-project', 'seed-bool', 'video-material', 'audio-english', 'unknown-runtime']:
        changed = copy.deepcopy(payload)
        if mutation == 'definition':
            changed['definition_version'] = 'unknown-version'
        elif mutation == 'kind':
            changed['steps']['video']['model_id'] = changed['steps']['image']['model_id']
        elif mutation == 'model-project':
            changed['project_id'] = workflows.service.project({'name': '其他项目'})['id']
        elif mutation == 'seed-bool':
            changed['steps']['image']['runtime'] = {'seed': True}
        elif mutation == 'video-material':
            changed['steps']['video']['input'] = {'material_id': 'old-material'}
        elif mutation == 'audio-english':
            changed['steps']['audio']['input']['prompt'] = 'Read arbitrary text'
        else:
            changed['steps']['video']['runtime'] = {'shell_command': 'not allowed'}
        before = table_state(workflows)
        with pytest.raises(Fault):
            workflows.start(changed, 'invalid-' + mutation)
        assert table_state(workflows) == before


def test_restart_preserves_workflow_history_and_original_step_records(workflow):
    workflows, payload = workflow
    run, _ = finish(workflows, payload, 'restart-round')
    settings = workflows.service.settings
    workflows.service.close()
    reopened = Service(settings)
    try:
        assert Workflows(reopened).get(run['id']) == run
        assert reopened.store.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        reopened.close()


def test_all_three_explicit_reuses_save_as_references_without_new_computation(workflow):
    workflows, payload = workflow
    original, sources = finish(workflows, payload, 'all-reuse-source')
    current = workflows.start(payload, 'all-reuse-new-round')
    for kind, (attempt, artifact) in zip(STEPS, sources):
        step = current['steps'][kind]
        body = {'expected_revision': current['revision'], 'step_id': kind, 'input_revision': step['input_revision'], 'source_attempt_id': attempt['id'], 'artifact_id': artifact['id']}
        current = workflows.reuse_output(current['id'], body, 'reuse-' + kind)
        current = workflows.advance(current['id'], advance_payload(current, artifact), 'accept-reuse-' + kind)
    saved = workflows.save_result(current['id'], {'expected_revision': current['revision']}, 'save-all-reused')
    assert len(workflows.store.list('attempt')) == 3
    assert len(workflows.store.list('work')) == 3
    assert all(item['mode'] == 'reused' and item['computed'] is False for item in saved['result']['items'])
    reused_records = [record for record in current['step_attempts'] if record['mode'] == 'reused']
    assert all(record['source']['workflow_ref']['workflow_run_id'] == original['id'] for record in reused_records)
    assert all(record['source']['source_input_revision'] == 1 for record in reused_records)
    assert 'upstream_refs' in reused_records[-1]['source']['differences']


def test_source_revision_changed_while_artifact_is_checked_cannot_partially_advance(workflow, monkeypatch):
    workflows, payload = workflow
    run = workflows.start(payload, 'changed-input-round')
    run, _, artifact = complete(workflows, run)
    original = workflows._verified_artifact
    updated = []
    def edit_after_validation(*args):
        result = original(*args)
        updated.append(workflows.revise_input(run['id'], 'image', {'expected_revision': run['revision'], 'configuration': payload['steps']['image']}, 'concurrent-edit'))
        return result
    monkeypatch.setattr(workflows, '_verified_artifact', edit_after_validation)
    fails('REVISION_CONFLICT', lambda: workflows.advance(run['id'], advance_payload(run, artifact), 'advance-old-input'))
    assert workflows.get(run['id']) == updated[0]
    assert not workflows.store.list('work') and not workflows.store.list('material')


def test_reuse_rejects_wrong_kind_wrong_project_and_nonprimary_artifact(workflow, rig):
    from test_media_flow import media_attempt
    workflows, payload = workflow
    _, sources = finish(workflows, payload, 'reuse-negative-source')
    current = workflows.start(payload, 'reuse-negative-target')
    _, foreign, foreign_artifact, _ = media_attempt(rig)
    metadata = next(item for item in workflows.store.list('artifact') if item['attempt_id'] == sources[0][0]['id'] and item['relative_path'] == 'fixture.json')
    for source, artifact in [(sources[2][0], sources[2][1]), (foreign, foreign_artifact), (sources[0][0], metadata)]:
        body = {'expected_revision': current['revision'], 'step_id': 'image', 'input_revision': 1, 'source_attempt_id': source['id'], 'artifact_id': artifact['id']}
        before = table_state(workflows)
        fails('WORKFLOW_SOURCE_MISMATCH', lambda: workflows.reuse_output(current['id'], body, 'invalid-source-' + artifact['id']))
        assert table_state(workflows) == before


def test_binding_wrong_model_rolls_back_and_save_rechecks_source_snapshot(workflow):
    workflows, payload = workflow
    run = workflows.start(payload, 'bind-negative')
    task = workflows.store.get('task', run['steps']['image']['task_id'])
    attempt = workflows.service.resource('attempt', task['project_id'], task_id=task['id'], snapshot={**copy.deepcopy(task['draft']), 'model_id': payload['steps']['audio']['model_id']})
    before = table_state(workflows)
    with workflows.store.transaction():
        fails('WORKFLOW_IDENTITY_MISMATCH', lambda: workflows.bind_attempt(task, attempt))
    assert table_state(workflows) == before
    finished, sources = finish(workflows, payload, 'save-snapshot-negative')
    with workflows.store.transaction():
        tampered = sources[1][0]
        tampered['snapshot']['input']['material_id'] = 'material-unbound'
        workflows.store.put('attempt', tampered)
    fails('WORKFLOW_SOURCE_MISMATCH', lambda: workflows.save_result(finished['id'], {'expected_revision': finished['revision']}, 'save-tampered-snapshot'))
