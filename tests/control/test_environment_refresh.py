"""固定CPU合同执行器：失败缓存可显式重探测，普通读取不反复启动子进程。"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control'))
from ailab_control.api import create_app
from ailab_control.service import Settings


def executor(root):
    root.mkdir()
    binary = root / 'executor'
    binary.write_text('#!' + str(Path(sys.executable).resolve()) + '\n' + '''import json,sys,time
from pathlib import Path
root=Path(__file__).parent
state=json.loads((root/'state.json').read_text())
with (root/'calls.jsonl').open('a') as stream: stream.write(json.dumps({'mode':sys.argv[2]})+'\\n')
if sys.argv[1:]!=['--mode','probe']: raise SystemExit(70)
if not state['ready']:
    if state['failure']=='timeout': time.sleep(5)
    if state['failure']=='malformed': print('invalid-json'); raise SystemExit(0)
    raise SystemExit(9)
print(json.dumps({'metal':True,'device_ready':True,'sources':{'fixture.py':'a'*64},'runtime_manifest_sha256':'b'*64,'dependencies':{'contract-only-fixture':'1'}}))
''')
    binary.chmod(0o700)
    (root / 'state.json').write_text(json.dumps({'ready': False, 'failure': 'exit'}))
    return binary


@pytest.fixture
def environment_client(tmp_path):
    binaries = {profile: executor(tmp_path / profile) for profile in ('mlx', 'diffusers', 'kokoro')}
    app = create_app(Settings(tmp_path / 'data', 'environment-test-token', bundled_worker=binaries['mlx'], bundled_media_worker=binaries['diffusers'], bundled_audio_worker=binaries['kokoro']))
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer environment-test-token'}) as client:
        yield client, binaries


def counts(binaries):
    return {name: len((binary.parent / 'calls.jsonl').read_text().splitlines()) if (binary.parent / 'calls.jsonl').exists() else 0 for name, binary in binaries.items()}


def ready(binaries, enabled=True, failure='exit'):
    for binary in binaries.values():
        (binary.parent / 'state.json').write_text(json.dumps({'ready': enabled, 'failure': failure}))


def capabilities(client, suffix=''):
    response = client.get('/api/v1/capabilities' + suffix)
    assert response.status_code == 200, response.text
    return {item['kind']: item['supported'] for item in response.json()['items'] if item['operation'] == 'generate'}


def test_explicit_refresh_recovers_failed_profiles_once_and_ordinary_lists_stay_cached(environment_client):
    client, binaries = environment_client
    identities = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()}
    assert not any(capabilities(client).values())
    assert counts(binaries) == dict.fromkeys(binaries, 1)
    ready(binaries)
    for suffix in ('', '?refresh=false', ''):
        assert not any(capabilities(client, suffix).values())
        assert client.get('/api/v1/devices').json()['items'][0]['ready'] is False
    assert counts(binaries) == dict.fromkeys(binaries, 1)
    assert all(capabilities(client, '?refresh=true').values())
    assert counts(binaries) == dict.fromkeys(binaries, 2)
    assert client.get('/api/v1/devices').json()['items'][0]['ready'] is True
    assert all(capabilities(client).values())
    assert counts(binaries) == dict.fromkeys(binaries, 2)
    assert all(capabilities(client, '?refresh=true').values())
    assert counts(binaries) == dict.fromkeys(binaries, 3)
    assert identities == {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in binaries.items()}
    assert client.get('/api/v1/attempts').json()['items'] == []


@pytest.mark.parametrize('failure', ['exit', 'malformed', 'timeout'])
def test_explicit_refresh_recovers_media_probe_failure_classes(environment_client, monkeypatch, failure):
    client, binaries = environment_client
    ready(binaries, enabled=False, failure=failure)
    if failure == 'timeout':
        original = subprocess.run
        def bounded(command, **kwargs):
            # 实际启动固定子进程并触发 TimeoutExpired；仅缩短测试等待，不改变产品超时。
            if command[:1] == [str(binaries['kokoro'])] and not json.loads((binaries['kokoro'].parent / 'state.json').read_text())['ready']:
                assert kwargs['timeout'] == 90
                kwargs['timeout'] = 0.2
            return original(command, **kwargs)
        monkeypatch.setattr(subprocess, 'run', bounded)
        ready({name: binary for name, binary in binaries.items() if name != 'kokoro'})
    assert capabilities(client)['audio'] is False
    before = counts(binaries)
    ready(binaries)
    assert capabilities(client)['audio'] is False
    assert counts(binaries) == before
    assert capabilities(client, '?refresh=true')['audio'] is True
    assert counts(binaries) == {name: count + 1 for name, count in before.items()}


@pytest.mark.parametrize('kind,profile', [('text', 'mlx'), ('image', 'diffusers'), ('audio', 'kokoro')])
def test_configuration_check_keeps_existing_forced_probe_recovery(environment_client, kind, profile):
    client, binaries = environment_client
    assert not any(capabilities(client).values())
    ready(binaries)
    project = client.post('/api/v1/projects', json={'name': '配置检查恢复'}).json()
    task = client.post('/api/v1/tasks', json={'project_id': project['id'], 'name': '只检查环境', 'kind': kind, 'operation': 'generate'}).json()
    response = client.post('/api/v1/tasks/' + task['id'] + '/preflight', json={'draft_revision': 1})
    assert response.status_code == 200, response.text
    check = response.json()
    assert check['environment']['ready'] and not check['can_submit']
    assert any(item['code'] == 'MODEL_NOT_READY' for item in check['blocking'])
    assert all(item['code'] != 'ENVIRONMENT_NOT_READY' for item in check['blocking'])
    assert counts(binaries) == {name: 2 if name == profile else 1 for name in binaries}
    assert client.get('/api/v1/attempts').json()['items'] == []


def test_invalid_refresh_or_missing_auth_does_not_probe(environment_client):
    client, binaries = environment_client
    assert client.get('/api/v1/capabilities?refresh=invalid').status_code == 422
    assert client.get('/api/v1/capabilities?refresh=true', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert counts(binaries) == dict.fromkeys(binaries, 0)
