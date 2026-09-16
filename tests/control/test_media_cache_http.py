"""真实HTTP/临时持久化及正式预检入口拒绝媒体缓存请求；不执行模型。"""
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_control import rig, setup_task

CASES = [
    ('media-a', 'input', 'media', [{'sha256': 'a' * 64}]),
    ('media-b', 'input', 'media', [{'sha256': 'b' * 64}]),
    ('media-ab', 'input', 'media', [{'sha256': 'a' * 64}, {'sha256': 'b' * 64}]),
    ('media-ba', 'input', 'media', [{'sha256': 'b' * 64}, {'sha256': 'a' * 64}]),
    ('processor-a', 'input', 'processor', {'id': 'same-processor', 'revision': 'a'}),
    ('processor-b', 'input', 'processor', {'id': 'same-processor', 'revision': 'b'}),
    ('preprocess-224', 'input', 'preprocess', {'resize': [224, 224]}),
    ('preprocess-384', 'input', 'preprocess', {'resize': [384, 384]}),
    ('prefix-reuse', 'runtime', 'prefix_cache', {'mode': 'reuse', 'key': 'same-text'}),
    ('media-reuse', 'runtime', 'media_cache', {'mode': 'reuse', 'key': 'same-text'}),
]


@pytest.mark.parametrize('case,section,field,value', CASES, ids=[item[0] for item in CASES])
def test_http_draft_rejects_unopened_media_identity_without_writes(rig, monkeypatch, case, section, field, value):
    client, service, *_ = rig
    _, _, task = setup_task(rig, prompt='同一文字输入')
    draft = copy.deepcopy(task['draft']); draft[section][field] = copy.deepcopy(value)
    before = service.store.get('task', task['id'])

    def forbidden(*args, **kwargs):pytest.fail('拒绝草稿不得启动预检/模型进程')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(service, 'run', forbidden)
    response = client.patch('/api/v1/tasks/' + task['id'] + '/draft', json={'expected_revision': task['draft_revision'], 'draft': draft})
    assert response.status_code == 422
    assert service.store.get('task', task['id']) == before
    assert not service.store.list('preflight') and not service.store.list('attempt')
    assert not list((service.root / 'runs').iterdir())


@pytest.mark.parametrize('case,section,field,value', CASES, ids=[item[0] for item in CASES])
def test_legacy_draft_preflight_and_submit_cannot_bypass_rejection(rig, monkeypatch, case, section, field, value):
    client, service, *_ = rig
    _, _, task = setup_task(rig, prompt='同一文字输入')
    task['draft'][section][field] = copy.deepcopy(value)
    # 仅pytest新临时库模拟旧/直接写入草稿，验证HTTP合同以后的防线。
    with service.store.transaction():service.store.put('task', task)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from adapters.mlx_text import preflight
    from workers.mlx_worker import WorkerError
    calls = []

    def forbidden(*args, **kwargs):pytest.fail('未开放媒体请求不得启动模型或子进程')

    def real_preflight_in_process(command, **kwargs):
        # 不模拟拒绝结果：读取控制层实际生成的snapshot，调用正式预检函数。
        snapshot_path = Path(command[command.index('--snapshot') + 1])
        output = Path(command[command.index('--output-dir') + 1])
        snapshot = json.loads(snapshot_path.read_text()); calls.append(snapshot)
        with pytest.raises(WorkerError) as error:preflight.check(snapshot, output)
        assert error.value.code == 'UNSUPPORTED_INPUT'
        assert not output.exists()
        return SimpleNamespace(returncode=1, stdout=json.dumps({'can_submit':False,'blocking':[{'code':error.value.code,'message':str(error.value)}]}))

    monkeypatch.setattr(subprocess, 'run', real_preflight_in_process)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(service, 'run', forbidden)
    expected = 'UNSUPPORTED_INPUT' if section == 'input' else 'UNSUPPORTED_PARAMETER'
    checked = client.post('/api/v1/tasks/' + task['id'] + '/preflight', json={'draft_revision':task['draft_revision']})
    assert checked.status_code == 200
    report = checked.json(); assert report['can_submit'] is False
    assert any(item['code'] == expected for item in report['blocking'])
    rejected = client.post('/api/v1/tasks/' + task['id'] + '/attempts', json={'preflight_id':report['id'],'expected_revision':task['draft_revision']}, headers={'Idempotency-Key':'blocked-media-cache'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'PREFLIGHT_BLOCKED'
    assert bool(calls) is (section == 'input')
    assert all(call['input']['prompt'] == '同一文字输入' and call[section][field] == value for call in calls)
    assert not service.store.list('attempt') and not service.store.list('artifact')
    assert not list((service.root / 'runs').iterdir())
