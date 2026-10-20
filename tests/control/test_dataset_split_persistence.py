"""来源组归属与应用事务持久化；仅使用独立 CPU 合同夹具。"""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from test_control import rig, post
from dataset_split_fixtures import prepare_split, setup_split
from ailab_control.assets import file_hash
from ailab_control.dataset_splits import verify_split_record


def rows_with_variants():
    pairs = [('shared', '同源变体甲'), ('shared', '同源变体乙'), *[('independent-' + str(index), '独立问题 ' + str(index)) for index in range(4)], ('excluded', '[exclude]')]
    return [{'source_id': group, 'messages': [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': '合同夹具答案'}]} for group, prompt in pairs]


def assignments(service, split_id):
    split = service.store.get('dataset-split', split_id)
    proof = json.loads((Path(split['storage_path']) / 'split-manifest.json').read_text())
    return {item['source_id']: item['subset'] for item in proof['group_assignments']}


def test_same_source_variants_stay_together_and_row_reordering_preserves_membership(rig, monkeypatch):
    client, service, source_dir, _ = rig
    original_rows = rows_with_variants()
    first = setup_split(rig, monkeypatch, rows=original_rows)
    first_assignment = assignments(service, first['split']['id'])
    assert len(first_assignment) == 5 and 'excluded' not in first_assignment
    chosen_role = first_assignment['shared']
    for role in ('train', 'validation'):
        child = service.store.get('dataset', first[role + '_dataset']['id'])
        prompts = [json.loads(line)['messages'][0]['content'] for line in (Path(child['storage_path']) / child['entrypoint']).read_text().splitlines()]
        assert ('同源变体甲' in prompts) == ('同源变体乙' in prompts) == (role == chosen_role)
    path = source_dir / '重排后的同源变体原件.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in reversed(original_rows)))
    imported = post(client, '/datasets/import-plans', {'project_id': first['project']['id'], 'path': str(path), 'schema': 'sft'})
    source = post(client, '/datasets/imports', {'plan_id': imported['id'], 'manifest_digest': imported['manifest_digest']}, 'reordered-import')
    plan, _ = prepare_split(client, first['project'], first['model'], source, key='reordered-plan')
    assert plan['status'] == 'ready'
    second = post(client, '/datasets/splits', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'reordered-apply')
    assert assignments(service, second['split']['id']) == first_assignment


def test_concurrent_apply_with_same_and_different_keys_registers_one_split(rig, monkeypatch):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    plan = service.store.get('dataset-split-plan', values['plan']['id'])
    body = {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}
    barrier = threading.Barrier(4)
    def apply(key):
        barrier.wait(timeout=5)
        return post(client, '/datasets/splits', body, key)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(apply, ['concurrent-same', 'concurrent-same', 'concurrent-other-a', 'concurrent-other-b']))
    assert all(response == responses[0] for response in responses)
    assert len(service.store.list('dataset-split')) == 1
    assert len(service.store.list('dataset')) == 3
    assert responses[0]['split']['id'] == plan['apply_intent']['split_id']
    for role in ('train', 'validation'):
        assert responses[0][role + '_dataset']['id'] == plan['apply_intent'][role + '_dataset_id']
        assert responses[0][role + '_dataset']['version_id'] == plan['apply_intent'][role + '_version_id']
    split = service.store.get('dataset-split', responses[0]['split']['id'])
    verify_split_record(split, lambda key: service.store.get('dataset', key))
    assert service.store.db.execute("SELECT COUNT(*) FROM commands WHERE scope='dataset-split-apply'").fetchone()[0] == 3


def test_completed_concurrent_apply_can_clean_stage_before_other_verification(rig, monkeypatch):
    import ailab_control.dataset_splits as module
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    plan = service.store.get('dataset-split-plan', values['plan']['id'])
    body = {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}
    entered, release = threading.Event(), threading.Event()
    original = module.verify_ready_plan

    def paused_verification(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert release.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, 'verify_ready_plan', paused_verification)
    with ThreadPoolExecutor(max_workers=1) as pool:
        delayed = pool.submit(post, client, '/datasets/splits', body, 'delayed-apply')
        assert entered.wait(timeout=10)
        try:
            finished = post(client, '/datasets/splits', body, 'completed-apply')
            assert not Path(plan['storage_path']).exists()
        finally:
            release.set()
        assert delayed.result(timeout=10) == finished
    assert len(service.store.list('dataset-split')) == 1


@pytest.mark.parametrize('fault', ['second_copy', 'second_dataset_put'])
def test_partial_apply_failure_rolls_back_registration_and_reuses_fixed_intent(rig, monkeypatch, fault):
    import ailab_control.dataset_splits as module
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    plan = service.store.get('dataset-split-plan', values['plan']['id'])
    source = service.store.get('dataset', values['source']['id'])
    source_path = Path(source['storage_path']) / source['manifest'][0]['path']
    source_before = source_path.read_bytes()
    intent = dict(plan['apply_intent'])
    body = {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}
    copies, puts = [], []
    original_copy, original_put = module.copy_asset, service.store.put
    def copy_with_fault(origin, root, manifest, key):
        copies.append(key)
        if fault == 'second_copy' and len(copies) == 2:
            raise OSError('独立夹具：第二份正式资产复制中断')
        return original_copy(origin, root, manifest, key)
    def put_with_fault(kind, value):
        if kind == 'dataset':
            puts.append(value['id'])
            if fault == 'second_dataset_put' and len(puts) == 2:
                raise OSError('独立夹具：第二个子集登记中断')
        return original_put(kind, value)
    monkeypatch.setattr(module, 'copy_asset', copy_with_fault)
    monkeypatch.setattr(service.store, 'put', put_with_fault)
    response = client.post('/api/v1/datasets/splits', json=body, headers={'Idempotency-Key': 'fault-then-retry'})
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'DATASET_SPLIT_IO_FAILED'
    assert not service.store.list('dataset-split')
    assert [item['id'] for item in service.store.list('dataset')] == [source['id']]
    preserved = service.store.get('dataset-split-plan', plan['id'])
    assert preserved['status'] == 'ready' and preserved['apply_intent'] == intent
    assert source_path.read_bytes() == source_before and file_hash(source_path) == source['manifest'][0]['sha256']
    assert service.store.db.execute("SELECT COUNT(*) FROM commands WHERE scope='dataset-split-apply'").fetchone()[0] == 0
    assert copies and (service.root / 'assets' / copies[0]).is_dir()
    monkeypatch.setattr(module, 'copy_asset', original_copy)
    monkeypatch.setattr(service.store, 'put', original_put)
    completed = post(client, '/datasets/splits', body, 'fault-then-retry')
    assert completed == post(client, '/datasets/splits', body, 'fault-then-retry')
    assert completed['split']['id'] == intent['split_id']
    assert len(service.store.list('dataset-split')) == 1 and len(service.store.list('dataset')) == 3
    for role in ('train', 'validation'):
        assert completed[role + '_dataset']['id'] == intent[role + '_dataset_id']
        assert completed[role + '_dataset']['version_id'] == intent[role + '_version_id']
    assert source_path.read_bytes() == source_before
    verify_split_record(service.store.get('dataset-split', completed['split']['id']), lambda key: service.store.get('dataset', key))
