"""正式 HTTP 和持久化层的文本参数合同；夹具不冒充语言模型实算。"""
import copy

import pytest

from test_control import rig, post, setup_task, submit, wait_attempt


@pytest.mark.parametrize('field,value', [
    ('context_limit', None), ('context_limit', True), ('context_limit', 512.0), ('context_limit', '512'), ('context_limit', 127), ('context_limit', 4097),
    ('overflow', 'truncate'), ('overflow', None), ('thinking', 'off'), ('thinking', 'on'), ('thinking', None),
    ('stream', None), ('stream', 1), ('stream', 'false'), ('stop', None), ('stop', 'END'), ('stop', [0]), ('stop', ['']),
    ('stop', ['a' * 129]), ('stop', list('123456789')), ('stop', ['a', 'a']), ('stop', ['\0']),
])
def test_new_runtime_fields_strict_http_rejection(rig, field, value):
    client, service, *_ = rig
    _, _, task = setup_task(rig)
    draft = copy.deepcopy(task['draft']); draft['runtime'][field] = value
    response = client.patch('/api/v1/tasks/' + task['id'] + '/draft', json={'expected_revision': task['draft_revision'], 'draft': draft})
    assert response.status_code == 422
    assert service.store.get('task', task['id'])['draft'] == task['draft'] and not service.store.list('attempt')


def test_old_drafts_omit_fields_and_new_explicit_values_survive_snapshot_and_reload(rig):
    client, service, *_ = rig
    project, _, task = setup_task(rig)
    fields = {'context_limit': 1024, 'overflow': 'reject', 'stop': [' END ', '完成'], 'stream': False, 'thinking': 'default'}
    assert not set(fields).intersection(task['draft']['runtime'])
    task['draft']['runtime'].update(fields)
    saved = client.patch('/api/v1/tasks/' + task['id'] + '/draft', json={'expected_revision': task['draft_revision'], 'draft': task['draft']}).json()
    assert {k: saved['draft']['runtime'][k] for k in fields} == fields
    attempt, _ = submit(rig, saved)
    completed = wait_attempt(client, attempt['id'])
    assert completed['state'] == 'succeeded'
    assert {k: completed['snapshot']['runtime'][k] for k in fields} == fields
    assert completed['snapshot']['requested_config'] == saved['draft']['runtime']
    assert client.get('/api/v1/tasks/' + task['id']).json()['draft']['runtime']['stop'] == [' END ', '完成']
    assert service.store.get('attempt', attempt['id'])['snapshot']['runtime']['stream'] is False


@pytest.mark.parametrize('field,value', [('context_limit', 1024), ('overflow', 'reject'), ('stop', []), ('stream', False), ('thinking', 'default')])
def test_training_does_not_accept_generation_fields(rig, field, value):
    client = rig[0]
    _, _, task = setup_task(rig, operation='train')
    task['draft']['runtime'][field] = value
    assert client.patch('/api/v1/tasks/' + task['id'] + '/draft', json={'expected_revision': task['draft_revision'], 'draft': task['draft']}).status_code == 422


def test_service_rechecks_legacy_or_directly_corrupted_generation_settings(rig):
    client, service, *_ = rig
    _, _, task = setup_task(rig)
    for fields, code in [({'stream': 'false'}, 'UNSUPPORTED_PARAMETER'), ({'context_limit': 128, 'max_tokens': 128}, 'CONTEXT_TOO_LONG')]:
        task['draft']['runtime'].update(fields)
        with service.store.transaction():
            service.store.put('task', task)
        check = post(client, '/tasks/' + task['id'] + '/preflight', {'draft_revision': task['draft_revision']})
        assert not check['can_submit'] and any(item['code'] == code for item in check['blocking'])
        task['draft']['runtime'].pop('stream', None)
    assert not service.store.list('attempt')


def test_capability_describes_real_single_prompt_scope_and_no_thinking_switch(rig):
    client, service, *_ = rig
    result = client.get('/api/v1/capabilities').json()
    text = next(item for item in result['items'] if item['kind'] == 'text' and item['operation'] == 'generate')
    fields = text['generation_parameters']
    assert fields['context_limit']['maximum'] == 4096 and fields['context_limit']['minimum'] == 128
    assert fields['overflow']['supported'] == ['reject']
    assert fields['thinking']['supported'] == ['default'] and fields['thinking']['switch_supported'] is False
    assert fields['stop']['maximum_items'] == 8 and fields['stream']['default'] is True
