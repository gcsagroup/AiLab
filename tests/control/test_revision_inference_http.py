"""正式 HTTP 的修订导出和生成配置边界。"""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from test_control import rig, post, setup_task, wait_attempt
from test_work_revisions import saved_work, payload


def test_revision_http_and_fixed_export_survive_later_edit(rig, tmp_path):
    client, service, *_ = rig
    _, work, attempt = saved_work(rig)
    before = copy.deepcopy(attempt)
    url = f"/works/{work['id']}/revisions"
    original = client.get('/api/v1' + url).json()
    first_body = payload(work, {'text': '第一次人工修订'})
    first = post(client, url, first_body, 'first-http')
    assert post(client, url, first_body, 'first-http') == first
    target = tmp_path / '修订 导出'; target.mkdir()
    grant = post(client, '/export-grants', {'path': str(target)})
    plan_body = {'project_id': work['project_id'], 'object_type': 'work', 'object_id': work['id'], 'target_dir': str(target), 'grant_id': grant['grant_id'], 'work_revision_id': first['revision']['id']}
    plan = post(client, '/exports/prepare', plan_body)
    assert plan['can_export'] and plan['object_version_id'] == first['revision']['id']
    assert any(p['path'].startswith('revision/') for p in plan['files'])
    second = post(client, url, payload(first['work'], {'text': '第二次人工修订'}, first['revision']['id']), 'second-http')
    assert second['revision']['id'] != first['revision']['id']
    record = post(client, '/exports', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'export-fixed')
    assert wait_attempt(client, record['attempt_id'])['state'] == 'succeeded'
    record = client.get('/api/v1/exports/' + record['id']).json()
    root = Path(record['verified_path'])
    for entry in plan['files']:
        assert hashlib.sha256((root / entry['path']).read_bytes()).hexdigest() == entry['sha256']
    revision_file = next(p['path'] for p in plan['files'] if p['path'].startswith('revision/'))
    assert (root / revision_file).read_text() == '第一次人工修订'
    assert json.loads((root / 'object.json').read_text())['selected_version']['revision_id'] == first['revision']['id']
    assert service.store.get('attempt', attempt['id']) == before
    assert client.get('/api/v1' + url).json()['original'] == original['original']
    original_plan = post(client, '/exports/prepare', {**plan_body, 'work_revision_id': None})
    assert original_plan['object_version_id'] == work['artifact_id']
    assert not any(p['path'].startswith('revision/') for p in original_plan['files'])
    assert client.post('/api/v1' + url, json=first_body, headers={'Idempotency-Key': 'stale'}).status_code == 409


@pytest.mark.parametrize('field,value', [('kv_precision', None), ('kv_precision', 'q8'), ('prefill_step_size', None), ('prefill_step_size', True), ('prefill_step_size', 1), ('prefill_step_size', 512.0)])
def test_runtime_invalid_values_rejected(rig, field, value):
    client = rig[0]
    _, _, task = setup_task(rig)
    draft = task['draft']; draft['runtime'][field] = value
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'expected_revision': task['draft_revision'], 'draft': draft})
    assert response.status_code == 422


def test_runtime_old_defaults_preserved_and_inference_recipe_change_rejected(rig, monkeypatch):
    client, service, *_ = rig
    _, _, task = setup_task(rig)
    assert not {'kv_precision', 'prefill_step_size'}.intersection(task['draft']['runtime'])
    task['draft']['runtime'].update(kv_precision='auto', prefill_step_size=512)
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'expected_revision': task['draft_revision'], 'draft': task['draft']})
    assert response.status_code == 200
    task = response.json()
    inspect = service.inspect_task
    recipe = ['f' * 64]
    def current(task):
        result = inspect(task)
        result['check']['effective_config']['inference_recipe_digest'] = recipe[0]
        return result
    monkeypatch.setattr(service, 'inspect_task', current)
    check = post(client, f"/tasks/{task['id']}/preflight", {'draft_revision': task['draft_revision']})
    recipe[0] = 'e' * 64
    rejected = client.post(f"/api/v1/tasks/{task['id']}/attempts", json={'expected_revision': task['draft_revision'], 'preflight_id': check['id']}, headers={'Idempotency-Key': 'changed-recipe'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'INFERENCE_RECIPE_CHANGED'
    assert service.store.list('attempt') == []


def test_training_cannot_take_generation_cache_fields(rig):
    client = rig[0]
    _, _, task = setup_task(rig, operation='train')
    task['draft']['runtime']['kv_precision'] = 'q4'
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'expected_revision': task['draft_revision'], 'draft': task['draft']})
    assert response.status_code == 422


def test_q4_cache_quality_gate_blocks_submit_without_execution(rig):
    client, service, *_ = rig
    _, _, task = setup_task(rig)
    task['draft']['runtime'].update(kv_precision='q4', prefill_step_size=512)
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'expected_revision': task['draft_revision'], 'draft': task['draft']})
    assert response.status_code == 200
    task = response.json()
    check = post(client, f"/tasks/{task['id']}/preflight", {'draft_revision': task['draft_revision']})
    assert not check['can_submit'] and any(item['code'] == 'KV_PRECISION_NOT_APPROVED' for item in check['blocking'])
    rejected = client.post(f"/api/v1/tasks/{task['id']}/attempts", json={'expected_revision': task['draft_revision'], 'preflight_id': check['id']}, headers={'Idempotency-Key': 'q4-blocked'})
    assert rejected.status_code == 409 and service.store.list('attempt') == []
