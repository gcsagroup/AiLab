"""通过正式 HTTP 和独立 CPU 合同夹具构造隔离来源组资产。"""

import hashlib
import json
from pathlib import Path
import sys
import time

from test_control import make_model, post

TEMPLATE = 'control-fixture-only-template'
CHECKER = Path(__file__).with_name('fixture_dataset_split_check.py')


def configure_split_checker(service, monkeypatch, mode='success'):
    from adapters.mlx_text import recipe
    monkeypatch.setattr(recipe, 'TEMPLATE_SHA256', hashlib.sha256(TEMPLATE.encode()).hexdigest())
    modes = {'value': mode}
    monkeypatch.setattr(service.dataset_splits, 'command', lambda request, output: [sys.executable, str(CHECKER), '--snapshot', str(request), '--output-dir', str(output), '--fixture-mode', modes['value']])
    original = service.preflight_command
    monkeypatch.setattr(service, 'preflight_command', lambda request, output: [sys.executable, str(CHECKER), '--snapshot', str(request), '--output-dir', str(output), '--fixture-mode', 'preflight']
                        if json.loads(request.read_text()).get('operation') == 'train' else original(request, output))
    return modes


def wait_split(client, plan_id, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get('/api/v1/datasets/split-plans/' + plan_id)
        assert response.status_code == 200, response.text
        result = response.json()
        if result['status'] not in {'preparing', 'cancelling'}:
            return result
        time.sleep(0.02)
    raise AssertionError(result)


def prepare_split(client, project, model, source, key='source-split', seed=7, fraction=2500, length=512):
    body = {'project_id': project['id'], 'source_dataset_id': source['id'], 'model_id': model['id'], 'max_seq_length': length,
            'split_seed': seed, 'validation_fraction_bps': fraction}
    response = client.post('/api/v1/datasets/split-plans', json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 202, response.text
    return wait_split(client, response.json()['id']), body


def setup_split(rig, monkeypatch, *, apply=True, rows=None, seed=7, fraction=2500, mode='success'):
    client, service, source_dir, _ = rig
    modes = configure_split_checker(service, monkeypatch, mode)
    project = post(client, '/projects', {'name': '来源组合同夹具'})
    directory = make_model(source_dir / ('split-model-' + project['id']))
    (directory / 'tokenizer_config.json').write_text(json.dumps({'chat_template': TEMPLATE}))
    for name in ('tokenizer.json', 'vocab.json', 'merges.txt'):
        (directory / name).write_text(json.dumps({'fixture_only': name}))
    planned = post(client, '/models/import-plans', {'project_id': project['id'], 'path': str(directory)})
    model = post(client, '/models/imports', {'plan_id': planned['id'], 'manifest_digest': planned['manifest_digest']}, 'split-model-' + project['id'])
    rows = rows if rows is not None else [*[{'source_id': 'source-' + str(index), 'messages': [{'role': 'user', 'content': '问题 ' + str(index)}, {'role': 'assistant', 'content': '答案 ' + str(index)}]} for index in range(4)],
                                           {'source_id': 'excluded-source', 'messages': [{'role': 'user', 'content': '[exclude]'}, {'role': 'assistant', 'content': '超长夹具'}]}]
    path = source_dir / ('source-' + project['id'] + '.jsonl')
    path.write_text(''.join((json.dumps(row, ensure_ascii=False) if row is not None else '') + '\n' for row in rows))
    planned = post(client, '/datasets/import-plans', {'project_id': project['id'], 'path': str(path), 'schema': 'sft'})
    source = post(client, '/datasets/imports', {'plan_id': planned['id'], 'manifest_digest': planned['manifest_digest']}, 'split-source-' + project['id'])
    plan, body = prepare_split(client, project, model, source, seed=seed, fraction=fraction)
    result = {'project': project, 'model': model, 'source': source, 'plan': plan, 'prepare_body': body, 'modes': modes}
    if apply:
        assert plan['status'] == 'ready', plan
        result.update(post(client, '/datasets/splits', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'split-apply-' + plan['id']))
    return result
