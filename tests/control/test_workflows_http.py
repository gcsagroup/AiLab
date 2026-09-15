"""真实 HTTP 路由、提交事务和独立进程测试；媒体内容明确为合同夹具。"""

import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import threading

import pytest

from test_control import rig, post, wait_attempt
from test_workflows import advance_payload, busy_attempt, table_state, workflow
from ailab_control.assets import copy_asset, file_hash
from ailab_control.storage import Fault, digest


@pytest.fixture
def http_workflow(rig, workflow, monkeypatch):
    client, service, source, _ = rig
    _, payload = workflow
    fixture = Path(__file__).with_name('fixture_workflow_worker.py')
    service.settings.media_python = service.settings.worker_python
    service.settings.audio_python = service.settings.worker_python
    service.settings.media_worker_script = fixture
    service.settings.audio_worker_script = fixture
    with service.store.transaction():
        for kind in ('image', 'video', 'audio'):
            model = service.store.get('model', payload['steps'][kind]['model_id'])
            model_dir = source / ('workflow-fixture-' + kind)
            model_dir.mkdir()
            (model_dir / 'fixture.json').write_text('{"model_execution":false}')
            manifest = [{'path': 'fixture.json', 'size': (model_dir / 'fixture.json').stat().st_size, 'sha256': file_hash(model_dir / 'fixture.json')}]
            copied = copy_asset(model_dir, service.root / 'assets', manifest, digest(manifest))
            model.update(manifest=manifest, manifest_digest=digest(manifest), storage_path=str(copied), load_policy_ref='workflow-fixture-policy')
            service.store.put('model', model)

    def inspect_fixture(task):
        model = service.store.get('model', task['draft']['model_id'])
        media_fields = {}
        if task['kind'] == 'video':
            material = service.store.get('material', task['draft']['input']['material_id'])
            media_fields = {'input_image_path': str(Path(material['storage_path']) / material['entrypoint']), 'input_image_manifest': material['manifest'], 'input_image_manifest_digest': material['manifest_digest'], 'material_id': material['id'], 'material_version_id': material['version_id']}
        return {'blocking': [], 'environment': {'engine': task['draft']['runtime']['engine'], 'device_id': task['draft']['runtime']['device_id'], 'ready': True, 'digest': 'workflow-fixture-environment', 'fixture_only': True}, 'model': model, 'dataset': None, 'adapter': None, 'evaluation_plan': None, 'evaluation_fields': {}, 'checkpoint_fields': {}, 'media_fields': media_fields, 'check': {'can_submit': True, 'blocking': [], 'effective_config': task['draft']['runtime'], 'media_recipe_digest': digest({'fixture': True, 'draft': task['draft']}), 'check_report': {'fixture_only': True, 'model_execution': False}}}
    monkeypatch.setattr(service.media, 'inspect', inspect_fixture)
    return client, service, payload


def submit_step(rig, run, key):
    client, service, _ = rig
    task_id = run['steps'][run['current_step']]['task_id']
    checked = post(client, f'/tasks/{task_id}/preflight', {'draft_revision': 1})
    assert checked['can_submit'] and checked['workflow_ref']['workflow_run_id'] == run['id']
    assert checked['workflow_digest'] == digest(checked['workflow_ref'])
    body = {'expected_revision': 1, 'preflight_id': checked['id']}
    submitted = post(client, f'/tasks/{task_id}/attempts', body, key)
    attempt = wait_attempt(client, submitted['id'])
    assert attempt['state'] == 'succeeded', attempt
    primary = service.media.primary(service.store.get('attempt', attempt['id']))
    latest = client.get(f"/api/v1/workflow-runs/{run['id']}").json()
    return latest, attempt, primary, submitted, body


def test_http_two_rounds_require_explicit_start_and_keep_frozen_child_snapshot(http_workflow):
    client, service, payload = http_workflow
    all_attempts = []
    for round_no in range(2):
        run = post(client, '/workflow-runs', payload, f'http-round-{round_no}')
        assert not [item for item in service.store.list('attempt') if item.get('snapshot', {}).get('workflow_ref', {}).get('workflow_run_id') == run['id']]
        for kind in ('image', 'video', 'audio'):
            before_count = len(service.store.list('attempt'))
            run, attempt, artifact, submitted, request = submit_step(http_workflow, run, f'http-{round_no}-{kind}')
            all_attempts.append(attempt['id'])
            actual = service.store.get('attempt', attempt['id'])
            assert actual['snapshot_digest'] == digest(actual['snapshot'])
            assert actual['snapshot']['workflow_ref']['step_attempt_id'] == run['steps'][kind]['step_attempt_id']
            report_artifact = next(item for item in attempt['artifacts'] if item['name'] == 'fixture-report.json')
            report = json.loads(Path(service.store.get('artifact', report_artifact['id'])['storage_path']).read_text())
            assert report['fixture_only'] and not report['model_execution'] and report['pid'] != os.getpid()
            assert report['workflow_ref'] == actual['snapshot']['workflow_ref']
            assert report['snapshot_sha256'] == file_hash(service.root / 'runs' / attempt['id'] / 'snapshot.json')
            replay = post(client, f"/tasks/{actual['task_id']}/attempts", request, f'http-{round_no}-{kind}')
            assert replay == submitted
            duplicate = client.post(f"/api/v1/tasks/{actual['task_id']}/attempts", json=request, headers={'Idempotency-Key': f'http-new-key-{round_no}-{kind}'})
            assert duplicate.status_code == 409 and duplicate.json()['error']['code'] == 'WORKFLOW_STEP_ALREADY_SUBMITTED'
            body = advance_payload(run, artifact)
            advanced = post(client, f"/workflow-runs/{run['id']}/advance", body, f'advance-{round_no}-{kind}')
            assert post(client, f"/workflow-runs/{run['id']}/advance", body, f'advance-{round_no}-{kind}') == advanced
            assert len(service.store.list('attempt')) == before_count + 1, '推进不能自动执行下一步骤'
            run = advanced
        result = post(client, f"/workflow-runs/{run['id']}/save", {'expected_revision': run['revision']}, f'http-save-{round_no}')
        fetched = client.get(f"/api/v1/workflow-results/{result['result']['id']}")
        assert fetched.status_code == 200 and fetched.json() == result['result']
        assert result['result']['media_combined'] is False and len(result['result']['items']) == 3
    assert len(all_attempts) == len(set(all_attempts)) == 6
    assert len(client.get('/api/v1/workflow-runs', params={'project_id': payload['project_id']}).json()['items']) == 2
    assert len(client.get('/api/v1/workflow-results', params={'project_id': payload['project_id']}).json()['items']) == 2


def test_http_auth_strict_body_idempotency_and_immutable_task(http_workflow):
    client, service, payload = http_workflow
    response = client.post('/api/v1/workflow-runs', json=payload, headers={'Authorization': '', 'Idempotency-Key': 'unauthenticated'})
    assert response.status_code == 401 and not service.store.list('workflow-run')
    assert client.post('/api/v1/workflow-runs', json=payload).status_code == 400
    for value in [payload | {'execute_next': True}, payload | {'steps': {'image': payload['steps']['image']}}, payload | {'steps': payload['steps'] | {'image': {'model_id': [], 'input': {}}}}]:
        assert client.post('/api/v1/workflow-runs', json=value, headers={'Idempotency-Key': 'invalid-http-input'}).status_code == 422
    run = post(client, '/workflow-runs', payload, 'http-identity')
    changed = client.post('/api/v1/workflow-runs', json=payload | {'name': '新的内容'}, headers={'Idempotency-Key': 'http-identity'})
    assert changed.status_code == 409 and changed.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    task = client.get('/api/v1/tasks/' + run['steps']['image']['task_id']).json()
    rejected = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'expected_revision': 1, 'draft': task['draft']})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'CONTROL_NOT_SUPPORTED'
    assert client.get(f"/api/v1/workflow-runs/{run['id']}", headers={'Authorization': ''}).status_code == 401


def test_http_revise_reuse_and_stale_preflight_do_not_launch_old_task(http_workflow):
    client, service, payload = http_workflow
    run = post(client, '/workflow-runs', payload, 'http-edit-source')
    old_task = run['steps']['image']['task_id']
    checked = post(client, f'/tasks/{old_task}/preflight', {'draft_revision': 1})
    edit = {'expected_revision': run['revision'], 'configuration': payload['steps']['image']}
    response = client.patch(f"/api/v1/workflow-runs/{run['id']}/steps/image/input", json=edit, headers={'Idempotency-Key': 'http-redo-before-start'})
    assert response.status_code == 200
    run = response.json()
    assert run['steps']['image']['task_id'] != old_task and run['steps']['image']['input_revision'] == 2
    rejected = client.post(f'/api/v1/tasks/{old_task}/attempts', json={'expected_revision': 1, 'preflight_id': checked['id']}, headers={'Idempotency-Key': 'old-task-after-edit'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'WORKFLOW_IDENTITY_MISMATCH'
    assert not service.store.list('attempt')
    assert client.post(f'/api/v1/tasks/{old_task}/preflight', json={'draft_revision': 1}).status_code == 409
    run, attempt, artifact, *_ = submit_step(http_workflow, run, 'http-new-input-start')
    second = post(client, '/workflow-runs', payload, 'http-reuse-round')
    body = {'expected_revision': second['revision'], 'step_id': 'image', 'input_revision': 1, 'source_attempt_id': attempt['id'], 'artifact_id': artifact['id']}
    second = post(client, f"/workflow-runs/{second['id']}/reuse-output", body, 'http-reuse')
    record = next(item for item in second['step_attempts'] if item['id'] == second['steps']['image']['step_attempt_id'])
    assert record['mode'] == 'reused' and not record['computed'] and second['current_step'] == 'image'
    count = len(service.store.list('attempt'))
    second = post(client, f"/workflow-runs/{second['id']}/advance", advance_payload(second, artifact), 'http-advance-reused')
    assert second['current_step'] == 'video' and len(service.store.list('attempt')) == count


@pytest.mark.parametrize('state', ['succeeded', 'cancelled'])
def test_http_busy_and_completion_race_accepts_only_one_advance(http_workflow, monkeypatch, state):
    client, service, payload = http_workflow
    run = post(client, '/workflow-runs', payload, 'http-busy-race')
    run, _, artifact, *_ = submit_step(http_workflow, run, 'http-race-start')
    target = busy_attempt(service.workflows, payload['project_id'])
    body = advance_payload(run, artifact)
    before = table_state(service.workflows)
    rejected = client.post(f"/api/v1/workflow-runs/{run['id']}/advance", json=body, headers={'Idempotency-Key': 'http-target-busy'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'WORKFLOW_TARGET_BUSY'
    assert table_state(service.workflows) == before
    with service.store.transaction():
        target['state'] = state
        service.store.put('attempt', target)
    barrier = threading.Barrier(2)
    original = service.workflows._verified_artifact
    def simultaneous(*args):
        artifact = original(*args)
        barrier.wait(timeout=5)
        return artifact
    monkeypatch.setattr(service.workflows, '_verified_artifact', simultaneous)
    def advance(key):
        return client.post(f"/api/v1/workflow-runs/{run['id']}/advance", json=body, headers={'Idempotency-Key': key})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(advance, ['http-race-a', 'http-race-b']))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert next(response for response in results if response.status_code == 409).json()['error']['code'] == 'REVISION_CONFLICT'
    latest = client.get('/api/v1/workflow-runs/' + run['id']).json()
    assert latest['current_step'] == 'video' and latest['revision'] == run['revision'] + 1
    assert len(service.store.list('material')) == len(service.store.list('work')) == 1


def test_http_preflight_and_submit_revalidate_workflow_after_slow_check(http_workflow, monkeypatch):
    client, service, payload = http_workflow
    run = post(client, '/workflow-runs', payload, 'http-check-race')
    task_id = run['steps']['image']['task_id']
    original = service.inspect_task
    changed = []
    def revise_during_check(task):
        result = original(task)
        if not changed:
            changed.append(service.workflows.revise_input(run['id'], 'image', {'expected_revision': run['revision'], 'configuration': payload['steps']['image']}, 'edit-during-check-' + str(run['revision'])))
        return result
    monkeypatch.setattr(service, 'inspect_task', revise_during_check)
    rejected = client.post(f'/api/v1/tasks/{task_id}/preflight', json={'draft_revision': 1})
    assert rejected.status_code == 409 and not service.store.list('preflight') and not service.store.list('attempt')
    monkeypatch.setattr(service, 'inspect_task', original)
    run = changed[0]
    task_id = run['steps']['image']['task_id']
    checked = post(client, f'/tasks/{task_id}/preflight', {'draft_revision': 1})
    changed.clear()
    monkeypatch.setattr(service, 'inspect_task', revise_during_check)
    rejected = client.post(f'/api/v1/tasks/{task_id}/attempts', json={'expected_revision': 1, 'preflight_id': checked['id']}, headers={'Idempotency-Key': 'submit-during-edit'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'WORKFLOW_IDENTITY_MISMATCH'
    assert not service.store.list('attempt')


def test_http_cancelled_or_failed_step_requires_explicit_new_input_identity(http_workflow):
    client, service, payload = http_workflow
    payload = copy.deepcopy(payload)
    payload['steps']['image']['input']['prompt'] = '测试：等待取消'
    run = post(client, '/workflow-runs', payload, 'http-cancel-step')
    task_id = run['steps']['image']['task_id']
    checked = post(client, f'/tasks/{task_id}/preflight', {'draft_revision': 1})
    body = {'expected_revision': 1, 'preflight_id': checked['id']}
    submitted = post(client, f'/tasks/{task_id}/attempts', body, 'http-cancel-submit')
    running = wait_attempt(client, submitted['id'], lambda value: value.get('phase') == 'workflow_fixture')
    post(client, f"/attempts/{running['id']}/cancel", {'expected_state_version': running['state_version']}, 'http-cancel-request')
    stopped = wait_attempt(client, submitted['id'])
    assert stopped['state'] == 'cancelled' and stopped['stop_status'] == 'confirmed'
    rejected = client.post(f'/api/v1/tasks/{task_id}/attempts', json=body, headers={'Idempotency-Key': 'wrong-retry-same-identity'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'WORKFLOW_STEP_ALREADY_SUBMITTED'
    run = client.get('/api/v1/workflow-runs/' + run['id']).json()
    config = copy.deepcopy(payload['steps']['image'])
    config['input']['prompt'] = '测试：执行失败'
    edited = client.patch(f"/api/v1/workflow-runs/{run['id']}/steps/image/input", json={'expected_revision': run['revision'], 'configuration': config}, headers={'Idempotency-Key': 'explicit-redo-cancelled'})
    assert edited.status_code == 200 and edited.json()['steps']['image']['input_revision'] == 2
    task_id = edited.json()['steps']['image']['task_id']
    checked = post(client, f'/tasks/{task_id}/preflight', {'draft_revision': 1})
    submitted = post(client, f'/tasks/{task_id}/attempts', {'expected_revision': 1, 'preflight_id': checked['id']}, 'explicit-second-start')
    failed = wait_attempt(client, submitted['id'])
    assert failed['state'] == 'failed'
    assert len(service.store.list('attempt')) == 2


@pytest.mark.parametrize('state', ['failed', 'cancelled'])
@pytest.mark.parametrize('cross_project', [False, True])
def test_http_terminal_but_unreconciled_target_still_blocks_advance(http_workflow, state, cross_project):
    client, service, payload = http_workflow
    run = post(client, '/workflow-runs', payload, 'http-unreconciled-target')
    run, _, artifact, *_ = submit_step(http_workflow, run, 'http-unreconciled-source')
    project_id = service.project({'name': '其他项目未核实进程'})['id'] if cross_project else payload['project_id']
    target = busy_attempt(service.workflows, project_id, state=state)
    with service.store.transaction():
        target.update(recovery_required=True, stop_status='unknown')
        service.store.put('attempt', target)
    before = table_state(service.workflows)
    response = client.post(f"/api/v1/workflow-runs/{run['id']}/advance", json=advance_payload(run, artifact), headers={'Idempotency-Key': 'reject-unknown-terminal'})
    assert response.status_code == 409 and response.json()['error']['code'] == 'WORKFLOW_TARGET_BUSY'
    assert table_state(service.workflows) == before


@pytest.mark.parametrize('state', ['failed', 'cancelled'])
def test_http_unreconciled_current_step_cannot_redo_reuse_or_start_elsewhere(http_workflow, state):
    client, service, payload = http_workflow
    run = post(client, '/workflow-runs', payload, 'http-unreconciled-current')
    run, attempt, artifact, *_ = submit_step(http_workflow, run, 'http-current-start')
    with service.store.transaction():
        internal = service.store.get('attempt', attempt['id'])
        internal.update(state=state, recovery_required=True, stop_status='unknown')
        service.store.put('attempt', internal)
    body = {'expected_revision': run['revision'], 'configuration': payload['steps']['image']}
    revised = client.patch(f"/api/v1/workflow-runs/{run['id']}/steps/image/input", json=body, headers={'Idempotency-Key': 'cannot-redo-unknown'})
    assert revised.status_code == 409 and revised.json()['error']['code'] == 'WORKFLOW_STEP_BUSY'
    body = {'expected_revision': run['revision'], 'step_id': 'image', 'input_revision': 1, 'source_attempt_id': attempt['id'], 'artifact_id': artifact['id']}
    reused = client.post(f"/api/v1/workflow-runs/{run['id']}/reuse-output", json=body, headers={'Idempotency-Key': 'cannot-reuse-unknown'})
    assert reused.status_code == 409 and reused.json()['error']['code'] == 'WORKFLOW_STEP_BUSY'
    separate = post(client, '/workflow-runs', payload, 'separate-draft-only')
    task_id = separate['steps']['image']['task_id']
    checked = post(client, f'/tasks/{task_id}/preflight', {'draft_revision': 1})
    rejected = client.post(f'/api/v1/tasks/{task_id}/attempts', json={'expected_revision': 1, 'preflight_id': checked['id']}, headers={'Idempotency-Key': 'cannot-start-around-unknown'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'DEVICE_BUSY'
    assert len(service.store.list('attempt')) == 1


def test_workflow_inputs_reuse_lineage_and_media_survive_two_isolated_restores(http_workflow, tmp_path):
    from test_backup_restore import plan_restore
    from ailab_control.backup import Backup, database, referenced_files
    from ailab_control.service import Service, Settings

    client, service, payload = http_workflow
    computed = post(client, '/workflow-runs', payload, 'restore-computed-round')
    originals = []
    for kind in ('image', 'video', 'audio'):
        computed, attempt, artifact, *_ = submit_step(http_workflow, computed, 'restore-source-' + kind)
        originals.append((service.store.get('attempt', attempt['id']), artifact))
        computed = post(client, f"/workflow-runs/{computed['id']}/advance", advance_payload(computed, artifact), 'restore-accept-' + kind)
    computed = post(client, f"/workflow-runs/{computed['id']}/save", {'expected_revision': computed['revision']}, 'restore-save-computed')['workflow_run']
    reused = post(client, '/workflow-runs', payload, 'restore-reused-round')
    for kind, (attempt, artifact) in zip(('image', 'video', 'audio'), originals):
        reused = post(client, f"/workflow-runs/{reused['id']}/reuse-output", {'expected_revision': reused['revision'], 'step_id': kind, 'input_revision': 1, 'source_attempt_id': attempt['id'], 'artifact_id': artifact['id']}, 'restore-reuse-' + kind)
        reused = post(client, f"/workflow-runs/{reused['id']}/advance", advance_payload(reused, artifact), 'restore-accept-reuse-' + kind)
    saved_reuse = post(client, f"/workflow-runs/{reused['id']}/save", {'expected_revision': reused['revision']}, 'restore-save-reused')
    reused = saved_reuse['workflow_run']
    pending = post(client, '/workflow-runs', payload, 'restore-pending-round')
    pending = post(client, f"/workflow-runs/{pending['id']}/reuse-output", {'expected_revision': pending['revision'], 'step_id': 'image', 'input_revision': 1, 'source_attempt_id': originals[0][0]['id'], 'artifact_id': originals[0][1]['id']}, 'restore-reuse-pending')
    pending = post(client, f"/workflow-runs/{pending['id']}/advance", advance_payload(pending, originals[0][1]), 'restore-pending-video-draft')
    original_runs = [computed, reused, pending]
    original_snapshots = {attempt['id']: copy.deepcopy(attempt['snapshot']) for attempt, _ in originals}
    original_snapshot_files = {attempt['id']: (service.root / 'runs' / attempt['id'] / 'snapshot.json').read_bytes() for attempt, _ in originals}
    original_bytes = {artifact['id']: Path(artifact['storage_path']).read_bytes() for _, artifact in originals}
    original_rows = table_state(service.workflows)
    for thread in list(service.threads):
        thread.join(timeout=2)
    opened = []
    current = service
    try:
        for index in range(2):
            manager = Backup(current)
            backup = manager.create('workflow-backup-' + str(index))
            package = Path(backup['backup_path'])
            references = referenced_files(database(package / 'control.sqlite3'), current.root, package)
            for _, artifact in originals:
                restored_artifact = current.store.get('artifact', artifact['id'])
                relative = str(Path(restored_artifact['storage_path']).relative_to(current.root))
                assert references[relative]['sha256'] == artifact['sha256']
            plan = plan_restore((None, current), manager, backup, tmp_path / ('工作流恢复-' + str(index)))
            restored = manager.restore({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'workflow-restore-' + str(index))
            recovered = Service(Settings(Path(restored['restored_path']), 'restored-workflow-token-' + str(index)))
            opened.append(recovered)
            for original in original_runs:
                assert recovered.workflows.get(original['id']) == original
            for original, artifact in originals:
                attempt = recovered.store.get('attempt', original['id'])
                assert attempt['snapshot']['workflow_ref'] == original['snapshot']['workflow_ref']
                assert attempt['snapshot_digest'] != original['snapshot_digest']
                assert attempt['snapshot_digest'] == digest(attempt['snapshot'])
                recovered.checkpoints.verify_lineage(attempt, original['snapshot_digest'])
                assert (recovered.root / 'runs' / attempt['id'] / 'snapshot.json').read_bytes() == original_snapshot_files[attempt['id']]
                copied = recovered.store.get('artifact', artifact['id'])
                assert Path(copied['storage_path']).is_relative_to(recovered.root)
                assert Path(copied['storage_path']).read_bytes() == original_bytes[artifact['id']]
            pending_task = recovered.store.get('task', pending['steps']['video']['task_id'])
            assert recovered.workflows.submission_fields(pending_task)['workflow_ref'] == pending_task['workflow_ref']
            check_saved = recovered.workflows.save_result(reused['id'], {'expected_revision': reused['revision']}, 'verify-restored-reuse-' + str(index))
            assert check_saved['result'] == saved_reuse['result']
            # 原摘要和输入身份不因恢复改写；伪造恢复链不得绕过原来源核验。
            original_restored = recovered.store.get('attempt', originals[0][0]['id'])
            for damage in ('original_snapshot', 'path_mapping', *(['previous_restoration'] if index else [])):
                changed = copy.deepcopy(original_restored)
                if damage == 'original_snapshot':
                    changed['restoration']['original_snapshot']['runtime']['seed'] += 1
                elif damage == 'path_mapping':
                    changed['restoration']['path_mapping'] = {str(current.root): str(tmp_path / '不匹配的恢复目录')}
                else:
                    changed['restoration']['previous_restoration']['original_snapshot']['runtime']['seed'] += 1
                with recovered.store.transaction():
                    recovered.store.put('attempt', changed)
                with pytest.raises(Fault, match='恢复链'):
                    recovered.workflows.save_result(reused['id'], {'expected_revision': reused['revision']}, 'reject-restoration-' + str(index) + damage)
                with recovered.store.transaction():
                    recovered.store.put('attempt', original_restored)
            current = recovered
    finally:
        for recovered in reversed(opened):
            recovered.close()
    assert table_state(service.workflows) == original_rows
    assert {attempt['id']: service.store.get('attempt', attempt['id'])['snapshot'] for attempt, _ in originals} == original_snapshots
