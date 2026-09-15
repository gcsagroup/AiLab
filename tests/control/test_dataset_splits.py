"""来源组产品合同；真实 SQLite、HTTP、文件与 CPU 子进程，不进行模型计算。"""

import copy
import json
from pathlib import Path
import subprocess
import time

import pytest

from test_control import rig, post
from dataset_split_fixtures import setup_split, prepare_split, wait_split
from ailab_control.dataset_splits import group_evidence, portable_split_ref, split_content_identity, verify_check_report, verify_ready_plan, verify_split_record
from ailab_control.storage import Fault, digest, encode


def test_real_http_prepare_preview_apply_and_replay(rig, monkeypatch):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    plan = values['plan']
    assert plan['status'] == 'ready', plan
    assert plan['counts'] == {'input_samples': 5, 'accepted_samples': 4, 'excluded_samples': 1, 'ignored_lines': 0, 'supervised_tokens': 8, 'shifted_supervised_tokens': 8,
                             'source_groups': 4, 'train_samples': 3, 'validation_samples': 1, 'train_groups': 3, 'validation_groups': 1}
    assert plan['preview']['new_files'] == 5 and plan['preview']['new_bytes'] > 0
    assert plan['preview']['token_labels_examples'][0]['line'] == 1
    assert plan['preview']['exclusion_counts'] == {'SEQUENCE_TOO_LONG': 1}
    internal = service.store.get('dataset-split-plan', plan['id'])
    assert len(internal['staged_manifest']) == 8
    expected = verify_ready_plan(internal, lambda key: service.store.get('dataset', key), lambda key: service.store.get('model', key))
    body = {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}
    first = post(client, '/datasets/splits', body, 'apply-first')
    assert first == post(client, '/datasets/splits', body, 'apply-first') == post(client, '/datasets/splits', body, 'apply-second')
    split = service.store.get('dataset-split', first['split']['id'])
    assert expected == verify_split_record(split, lambda key: service.store.get('dataset', key))
    assert len(service.store.list('dataset')) == 3 and len(service.store.list('dataset-split')) == 1
    assert client.get('/api/v1/datasets/splits', params={'project_id': values['project']['id']}).json()['items'] == [first['split']]
    assert client.get('/api/v1/datasets/splits/' + split['id']).json() == first['split']
    for role in ('train', 'validation'):
        child = service.store.get('dataset', first[role + '_dataset']['id'])
        assert child['version_id'] != values['source']['version_id']
        path = Path(child['storage_path']) / child['entrypoint']
        assert all(set(json.loads(line)) == {'messages'} for line in path.read_text().splitlines())
    current = client.get('/api/v1/datasets/split-plans/' + plan['id']).json()
    assert current['status'] == 'applied' and current['applied_split_id'] == split['id']


@pytest.mark.parametrize('mode', ['bad-json', 'wrong-line'])
def test_bad_actual_child_output_preserves_fixed_failure_without_registering(rig, monkeypatch, mode):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False, mode=mode)
    assert values['plan']['status'] == 'failed'
    assert len(service.store.list('dataset')) == 1 and not service.store.list('dataset-split')
    assert 'PRIVATE_' not in json.dumps(values['plan']) and '/Users/private/' not in json.dumps(values['plan'])
    assert not service.dataset_splits.processes


@pytest.mark.parametrize('changes', [{'max_seq_length': 31}, {'max_seq_length': True}, {'split_seed': -1}, {'split_seed': True}, {'validation_fraction_bps': 10000}, {'validation_fraction_bps': 0}, {'source_group_field': 'line'}])
def test_prepare_strict_contract(rig, changes):
    client = rig[0]
    body = {'project_id': 'project', 'source_dataset_id': 'dataset', 'model_id': 'model', 'max_seq_length': 512, 'split_seed': 7, 'validation_fraction_bps': 2500, **changes}
    response = client.post('/api/v1/datasets/split-plans', json=body, headers={'Idempotency-Key': 'strict'})
    assert response.status_code == 422, response.text


def test_zero_supervision_filter_precedes_grouping(rig, monkeypatch):
    row = lambda group, text: {'source_id': group, 'messages': [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': '答案'}]}
    values = setup_split(rig, monkeypatch, apply=False, rows=[row('survives', '问题'), row('removed', '[exclude]')])
    assert values['plan']['status'] == 'blocked'
    assert values['plan']['counts']['source_groups'] == 1
    assert values['plan']['blocking'][0]['code'] == 'DATASET_SPLIT_TOO_FEW_GROUPS'


def test_cross_subset_duplicate_blocks_with_both_physical_lines(rig, monkeypatch):
    row = lambda group, text: {'source_id': group, 'messages': [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': '答案'}]}
    values = setup_split(rig, monkeypatch, apply=False, rows=[row('first', '同 一 问题'), row('second', '同  一  问题')], fraction=5000)
    assert values['plan']['status'] == 'blocked'
    issue = values['plan']['blocking'][0]
    assert issue['code'] == 'DATASET_SPLIT_DUPLICATE_PROMPT'
    assert {issue['line'], issue['related_line']} == {1, 2}


def test_unknown_ref_never_enters_portable_export(rig, monkeypatch):
    values = setup_split(rig, monkeypatch)
    service = rig[1]
    ref = verify_split_record(service.store.get('dataset-split', values['split']['id']), lambda key: service.store.get('dataset', key))
    with pytest.raises(Fault, match='未知'):
        portable_split_ref({**ref, 'private_debug': '/Users/private/secret'})


def test_cancel_ready_removes_only_owned_stage(rig, monkeypatch):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    plan = service.store.get('dataset-split-plan', values['plan']['id'])
    stage = Path(plan['storage_path'])
    assert stage.is_dir()
    cancelled = post(client, '/datasets/split-plans/' + plan['id'] + '/cancel', {}, 'cancel-ready')
    assert cancelled['status'] == 'cancelled' and not stage.exists()
    assert service.store.get('dataset-split-plan', plan['id'])['storage_path'] is None
    assert len(service.store.list('dataset')) == 1


def test_same_content_has_stable_split_digest_and_new_plan_identity(rig, monkeypatch):
    values = setup_split(rig, monkeypatch, apply=False)
    repeated, _ = prepare_split(rig[0], values['project'], values['model'], values['source'], key='same-input-new-plan')
    assert repeated['status'] == 'ready'
    assert repeated['split_digest'] == values['plan']['split_digest']
    assert repeated['plan_digest'] != values['plan']['plan_digest']
    assert repeated['preview'] == values['plan']['preview']


def test_same_side_independent_sources_with_same_prompt_are_allowed(rig, monkeypatch):
    ordered = sorted(('a', 'b', 'c', 'd'), key=lambda group: digest(['source-group-sha256-v1', 7, group]))
    row = lambda group, text: {'source_id': group, 'messages': [{'role': 'user', 'content': text}, {'role': 'assistant', 'content': '答案'}]}
    values = setup_split(rig, monkeypatch, rows=[row(ordered[0], '只在验证侧'), row(ordered[1], '同侧重复'), row(ordered[2], '同侧重复'), row(ordered[3], '第三训练来源')])
    assert values['plan']['status'] == 'ready' and values['split']['counts']['train_samples'] == 3


@pytest.mark.parametrize('target', ['report', 'identity', 'runtime', 'recipe', 'tokenizer_files', 'example', 'span'])
def test_proof_contract_rejects_private_unknown_fields_at_every_level(rig, monkeypatch, target):
    values = setup_split(rig, monkeypatch)
    service = rig[1]
    split = service.store.get('dataset-split', values['split']['id'])
    report = json.loads((Path(split['storage_path']) / 'check-report.json').read_text())
    selected = {'report': report, 'identity': report['check_identity'], 'runtime': report['check_identity']['runtime'],
                'recipe': report['check_identity']['recipe'], 'tokenizer_files': report['check_identity']['recipe']['tokenizer_files'],
                'example': report['token_labels_examples'][0], 'span': report['token_labels_examples'][0]['assistant_spans'][0]}[target]
    selected['private_debug'] = {'path': '/Users/private/secret'}
    report['check_identity_digest'] = digest(report['check_identity'])
    with pytest.raises(Fault) as result:
        verify_check_report(report)
    assert result.value.code == 'DATASET_CHECK_OUTPUT_INVALID'


def test_actual_row_file_rejects_unknown_fields_and_split_digest_binds_check_hashes(rig, monkeypatch, tmp_path):
    values = setup_split(rig, monkeypatch)
    service = rig[1]
    source = service.store.get('dataset', values['source']['id'])
    split = service.store.get('dataset-split', values['split']['id'])
    proof = json.loads((Path(split['storage_path']) / 'split-manifest.json').read_text())
    changed = copy.deepcopy(proof)
    changed['checks_manifest'][0]['sha256'] = 'f' * 64
    assert digest(split_content_identity(proof)) != digest(split_content_identity(changed))
    lines = (Path(split['storage_path']) / 'sample-checks.jsonl').read_text().splitlines()
    row = json.loads(lines[0])
    row['private_debug'] = '/Users/private/token'
    lines[0] = encode(row)
    path = tmp_path / 'tampered-sample-checks.jsonl'
    path.write_text('\n'.join(lines) + '\n')
    with pytest.raises(Fault):
        group_evidence(Path(source['storage_path']) / source['manifest'][0]['path'], path, 512)


def test_cancel_running_child_waits_for_actual_exit_and_then_discards_stage(rig, monkeypatch):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    values['modes']['value'] = 'slow'
    response = client.post('/api/v1/datasets/split-plans', json=values['prepare_body'], headers={'Idempotency-Key': 'slow-plan'})
    assert response.status_code == 202
    plan = response.json()
    deadline = time.monotonic() + 3
    while plan['id'] not in service.dataset_splits.processes and time.monotonic() < deadline:
        time.sleep(0.01)
    process = service.dataset_splits.processes[plan['id']]
    assert process.poll() is None
    cancelled = post(client, '/datasets/split-plans/' + plan['id'] + '/cancel', {}, 'cancel-running')
    assert cancelled['status'] == 'cancelling'
    done = wait_split(client, plan['id'])
    assert done['status'] == 'cancelled'
    assert process.poll() is not None and not service.dataset_splits.processes
    assert service.store.get('dataset-split-plan', plan['id'])['storage_path'] is None


def test_cancel_partial_cleanup_failure_persists_recovery_and_same_key_can_retry(rig, monkeypatch):
    import ailab_control.dataset_splits as module
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    plan = service.store.get('dataset-split-plan', values['plan']['id'])
    stage = Path(plan['storage_path'])
    original = module.shutil.rmtree
    def fail_once(path):
        (Path(path) / 'request.json').unlink()
        raise OSError('代表性清理中断')
    monkeypatch.setattr(module.shutil, 'rmtree', fail_once)
    response = post(client, '/datasets/split-plans/' + plan['id'] + '/cancel', {}, 'cancel-partial')
    assert response['status'] == 'recovery_required'
    assert stage.exists() and service.store.get('dataset-split-plan', plan['id'])['storage_path'] == str(stage)
    monkeypatch.setattr(module.shutil, 'rmtree', original)
    retried = post(client, '/datasets/split-plans/' + plan['id'] + '/cancel', {}, 'cancel-partial')
    assert retried['status'] == 'cancelled' and not stage.exists()


def test_unconfirmed_owned_child_is_retained_and_service_close_retries(rig, monkeypatch):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    record = service.store.get('dataset-split-plan', values['plan']['id'])
    class HungFixture:
        pid = 999999999
        exited = False
        waits = 0
        def poll(self): return 0 if self.exited else None
        def wait(self, timeout):
            self.waits += 1
            if not self.exited:
                raise subprocess.TimeoutExpired('controlled-fixture', timeout)
            return 0
    process = HungFixture()
    signals = []
    monkeypatch.setattr(service, '_signal', lambda child, sig: signals.append((child.pid, sig)))
    monkeypatch.setattr(service, 'group_present', lambda pid: not process.exited if pid == process.pid else False)
    service.dataset_splits.processes[record['id']] = process
    assert not service.dataset_splits.stop_owned(record['id'], process)
    assert service.dataset_splits.processes[record['id']] is process and process.waits == 2
    service.dataset_splits.close()
    assert service.store.get('dataset-split-plan', record['id'])['status'] == 'recovery_required'
    assert Path(record['storage_path']).exists()
    service.close()
    assert not service.shutdown_complete
    process.exited = True
    service.close()
    assert service.shutdown_complete and not service.dataset_splits.processes
    assert signals


def test_plan_listing_preserves_project_source_scope_and_stable_cursor(rig, monkeypatch):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    second, _ = prepare_split(client, values['project'], values['model'], values['source'], key='page-two')
    post(client, '/datasets/split-plans/' + second['id'] + '/cancel', {}, 'cancel-second')
    url = '/api/v1/datasets/split-plans'
    scope = {'project_id': values['project']['id'], 'source_dataset_id': values['source']['id'], 'limit': 1}
    first = client.get(url, params=scope).json()
    assert first['items'][0]['id'] == values['plan']['id'] and first['next_cursor'] == values['plan']['id']
    next_page = client.get(url, params={**scope, 'cursor': first['next_cursor']}).json()
    assert next_page['items'][0]['id'] == second['id'] and next_page['items'][0]['status'] == 'cancelled' and next_page['next_cursor'] is None
    other = post(client, '/projects', {'name': '其他来源组项目'})
    assert client.get(url, params={**scope, 'project_id': other['id']}).status_code == 403
    assert client.get(url, params={'project_id': other['id'], 'cursor': first['next_cursor']}).status_code == 409


def test_local_training_rejects_original_and_holdout_and_freezes_train_ref(rig, monkeypatch):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch)
    task = post(client, '/tasks', {'project_id': values['project']['id'], 'name': '划分绑定检查', 'kind': 'text', 'operation': 'train'})
    draft = task['draft']
    draft['model_id'] = values['model']['id']
    for dataset, expected in [(values['source'], 'DATASET_SPLIT_REQUIRED'), (values['validation_dataset'], 'DATASET_SPLIT_VALIDATION_NOT_TRAINABLE'), (values['train_dataset'], None)]:
        draft['dataset_id'] = dataset['id']
        task = client.patch('/api/v1/tasks/' + task['id'] + '/draft', json={'expected_revision': task['draft_revision'], 'draft': draft}).json()
        checked = post(client, '/tasks/' + task['id'] + '/preflight', {'draft_revision': task['draft_revision']})
        if expected:
            assert not checked['can_submit'] and any(item['code'] == expected for item in checked['blocking'])
        else:
            assert checked['can_submit'], checked
            assert checked['dataset_split_ref']['split_digest'] == values['split']['split_digest']
    monkeypatch.setattr(service, 'run', lambda attempt_id: service.threads.discard(__import__('threading').current_thread()))
    attempt = post(client, '/tasks/' + task['id'] + '/attempts', {'preflight_id': checked['id'], 'expected_revision': task['draft_revision']}, 'bound-train')
    assert attempt['snapshot']['dataset_split_ref'] == checked['dataset_split_ref']
    assert attempt['snapshot']['dataset_id'] == values['train_dataset']['id']
    assert attempt['snapshot']['dataset_path'].endswith('/train.jsonl')
