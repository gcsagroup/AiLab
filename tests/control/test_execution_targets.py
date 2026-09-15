"""原生凭据权限、隔离、重启和真实身份连接的产品接口验收。"""

import json
import sys
from pathlib import Path

import pytest

from test_control import rig, post
from ailab_control.execution_targets import ExecutionTargets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'remote'))
from test_protocol import RunningServer


def payload(project, server):
    return {'name': '本机传输协议', 'project_id': project['id'], 'origin': f'http://127.0.0.1:{server.port}',
            'executor_id': server.executor_id, 'credential_token': server.token}


def test_target_real_identity_secret_never_persisted_and_restart_requires_credential(rig, tmp_path):
    client, service, *_ = rig
    root = tmp_path / 'remote'; root.mkdir()
    server = RunningServer(root)
    try:
        project = post(client, '/projects', {'name': '连接验证'})
        request = payload(project, server)
        target = post(client, '/execution-targets', request, 'create-target')
        assert target['credential_status'] == 'available' and target['credential_ref'] is None
        checked = post(client, f"/execution-targets/{target['id']}/check", {})
        assert checked['protocol_ready'] and checked['connection_state'] == 'connected'
        assert checked['network_remote_ready'] is False and checked['nvidia_ready'] is False
        assert server.token not in json.dumps(checked)
        assert server.token not in service.store.path.read_bytes().decode(errors='ignore')
        with service.store.lock:
            records = '\n'.join(str(row) for row in service.store.db.execute('SELECT * FROM resources'))
            records += '\n'.join(str(row) for row in service.store.db.execute('SELECT * FROM commands'))
        assert server.token not in records
        service.execution_targets = ExecutionTargets(service)
        restored = client.get(f"/api/v1/execution-targets/{target['id']}").json()
        assert restored['credential_status'] == 'required'
        denied = client.post(f"/api/v1/execution-targets/{target['id']}/check", json={})
        assert denied.status_code == 409 and denied.json()['error']['code'] == 'CREDENTIAL_REQUIRED'
    finally:
        server.cleanup()


def test_host_reference_requires_host_token_and_credential_changes_are_cas_idempotent(rig):
    client, service, *_ = rig
    service.settings.host_token = 'independent-host-secret'
    project = post(client, '/projects', {'name': '系统凭据'})
    request = {'name': '已登记服务', 'project_id': project['id'], 'origin': 'http://127.0.0.1:12345',
               'executor_id': 'executor-' + 'a' * 32, 'credential_token': 'A' * 40,
               'credential_ref': 'remote-credential-' + 'b' * 32}
    denied = client.post('/api/v1/host/execution-targets', json=request, headers={'Idempotency-Key': 'host-create'})
    assert denied.status_code == 403
    headers = {'Idempotency-Key': 'host-create', 'X-AILab-Host-Token': service.settings.host_token}
    result = client.post('/api/v1/host/execution-targets', json=request, headers=headers)
    assert result.status_code == 200, result.text
    target = result.json()
    assert target['credential_storage'] == 'keychain'
    changed_create = client.post('/api/v1/host/execution-targets', json={**request, 'credential_token': 'Z' * 40}, headers=headers)
    assert changed_create.status_code == 409
    assert client.post('/api/v1/execution-targets', json=request, headers=headers).status_code == 422
    route = f"/api/v1/host/execution-targets/{target['id']}/credentials"
    update = {'credential_token': 'B' * 40, 'credential_ref': 'remote-credential-' + 'c' * 32, 'expected_revision': 1}
    headers['Idempotency-Key'] = 'host-update'
    changed = client.post(route, json=update, headers=headers)
    assert changed.status_code == 200 and changed.json()['revision'] == 2
    assert changed.json()['credential_cleanup_refs'] == [request['credential_ref']]
    assert client.post(route, json={**update, 'credential_token': 'Z' * 40}, headers=headers).status_code == 409
    assert client.post(route, json=update, headers=headers).json()['revision'] == 2
    headers['Idempotency-Key'] = 'stale-update'
    assert client.post(route, json=update, headers=headers).status_code == 409
    headers['Idempotency-Key'] = 'host-forget'
    deleted = client.request('DELETE', route, json={'expected_revision': 2}, headers=headers)
    assert deleted.status_code == 200 and deleted.json()['credential_ref'] is None
    assert deleted.json()['credential_status'] == 'required'
    assert client.request('DELETE', route, json={'expected_revision': 2}, headers=headers).json()['revision'] == 3
    pending = deleted.json()['credential_cleanup_refs']
    assert pending == [request['credential_ref'], update['credential_ref']]
    assert deleted.json()['credential_cleanup_required'] is True
    # 钥匙串未确认删除时，重启和再次清除均保留纯引用，已撤销口令不能恢复连接。
    service.execution_targets = ExecutionTargets(service)
    assert service.execution_targets.get(target['id'])['credential_cleanup_refs'] == pending
    assert client.post(f"/api/v1/execution-targets/{target['id']}/check", json={}).status_code == 409
    headers['Idempotency-Key'] = 'revoked-reference'
    assert client.post(route, json={**update, 'expected_revision': 3}, headers=headers).status_code == 409
    cleanup = route + '/cleanup'
    confirmed = {'credential_ref': pending[0], 'expected_revision': 3}
    assert client.post(cleanup, json=confirmed).status_code == 403
    headers['Idempotency-Key'] = 'cleanup-first'
    first = client.post(cleanup, json=confirmed, headers=headers)
    assert first.status_code == 200 and first.json()['revision'] == 4
    assert first.json()['credential_cleanup_refs'] == [pending[1]]
    assert client.post(cleanup, json=confirmed, headers=headers).json()['revision'] == 4
    headers['Idempotency-Key'] = 'cleanup-stale'
    assert client.post(cleanup, json=confirmed, headers=headers).status_code == 409
    headers['Idempotency-Key'] = 'cleanup-second'
    second = client.post(cleanup, json={'credential_ref': pending[1], 'expected_revision': 4}, headers=headers)
    assert second.status_code == 200 and second.json()['credential_cleanup_refs'] == []
    assert not second.json()['credential_cleanup_required']
    assert second.json()['credential_status'] == 'required'


def test_cleanup_limit_reserves_room_to_revoke_current_credential(rig):
    from ailab_control.storage import Fault
    client, service, *_ = rig
    project = post(client, '/projects', {'name': '凭据清理上限'})
    original = service.execution_targets.create({'name': '系统目标', 'project_id': project['id'],
        'origin': 'http://127.0.0.1:12345', 'executor_id': 'executor-' + 'a' * 32,
        'credential_token': 'A' * 40, 'credential_ref': 'remote-credential-' + 'f' * 32}, 'full-create', host=True)
    value = service.store.get('execution-target', original['id'])
    value['credential_cleanup_refs'] = [f'remote-credential-{number:032x}' for number in range(15)]
    with service.store.transaction():
        service.store.put('execution-target', value)
    with pytest.raises(Fault) as blocked:
        service.execution_targets.credentials(value['id'], {'credential_token': 'B' * 40,
            'credential_ref': 'remote-credential-' + 'e' * 32, 'expected_revision': 1}, host=True, key='full-set')
    assert blocked.value.code == 'CREDENTIAL_CLEANUP_REQUIRED'
    detached = service.execution_targets.credentials(value['id'], {'expected_revision': 1}, host=True, forget=True, key='full-forget')
    assert len(detached['credential_cleanup_refs']) == 16
    assert detached['credential_ref'] is None and detached['credential_status'] == 'required'


@pytest.mark.parametrize('origin', ['https://example.com', 'http://localhost:12345', 'http://127.0.0.1:12345/x', 'http://127.0.0.1:12345?token=abc'])
def test_target_rejects_unapproved_network_destinations(rig, origin):
    client, *_ = rig
    project = post(client, '/projects', {'name': '范围验证'})
    response = client.post('/api/v1/execution-targets', json={'name': '无效范围', 'project_id': project['id'], 'origin': origin,
                                                           'executor_id': 'executor-' + 'a' * 32, 'credential_token': 'S' * 40}, headers={'Idempotency-Key': 'invalid'})
    assert response.status_code == 400 and response.json()['error']['code'] == 'LOOPBACK_ONLY'
