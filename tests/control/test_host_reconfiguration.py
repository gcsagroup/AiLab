"""宿主数据来源重配租约不授予普通页面，阻断写入竞争。"""
import time

from test_control import rig, post, setup_task


def host(rig):
    rig[1].settings.host_token = 'host-only'
    return {'X-AiLab-Host-Token': 'host-only'}


def test_host_reconfiguration_lease_auth_and_release(rig):
    client, service, *_ = rig
    headers = host(rig)
    path = '/api/v1/host/reconfiguration'
    assert client.post(path, json={}).status_code == 403
    assert client.request('DELETE', path, json={}).status_code == 403
    result = client.post(path, json={}, headers=headers)
    assert result.status_code == 200 and result.json()['ready']
    assert client.post('/api/v1/projects', json={'name': '被暂时冻结'}).status_code == 409
    assert client.get('/api/v1/market/catalog?project_id=missing&provider_id=fixture-provider').status_code == 409
    assert client.get('/api/v1/projects').status_code == 200
    assert client.request('DELETE', path, json={}, headers=headers).status_code == 200
    assert client.post('/api/v1/projects', json={'name': '租约已释放'}).status_code == 200
    assert not service.activation_pending


def test_other_write_or_download_blocks_and_expired_lease_releases(rig):
    client, service, *_ = rig
    headers = host(rig); path = '/api/v1/host/reconfiguration'
    service.active_writes = 1
    assert client.post(path, json={}, headers=headers).status_code == 409
    service.active_writes = 0
    project, _, _ = setup_task(rig)
    record = service.resource('market-download', project['id'], state='queued')
    service.store.put('market-download', record)
    assert client.post(path, json={}, headers=headers).status_code == 409
    record['state'] = 'cancelled'; service.store.put('market-download', record)
    assert client.post(path, json={}, headers=headers).status_code == 200
    service.activation_deadline = time.monotonic() - 1
    assert client.post('/api/v1/projects', json={'name': '到期后可写'}).status_code == 200
