"""控制 API 通过真正回环 TLS 完成冻结、执行及补收，不运行模型。"""

import json
from pathlib import Path
import sqlite3
import sys

import pytest

from test_control import rig, post, wait_attempt
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'remote'))
from test_https import TLSServer, certificates, test_trust, TOKEN
from ailab_control.remote.client import LoopbackClient
from ailab_control.remote.protocol import ProtocolError


@pytest.fixture
def https_rig(rig, tmp_path, certificates, test_trust, monkeypatch):
    client, service, source, _ = rig
    server = TLSServer(tmp_path / '控制TLS服务', certificates)
    # 本项只验证连接和传输；CUDA 就绪需要另行实际机器验收。
    monkeypatch.setattr(LoopbackClient, 'nvidia_probe', lambda _self: {'ready': False, 'hardware_acceptance': 'not_verified'})
    try:
        project = post(client, '/projects', {'name': 'HTTPS 协议验收'})
        target = post(client, '/execution-targets', {'name': '独立 TLS 服务', 'project_id': project['id'],
            'origin': server.client.target.origin + '/', 'transport': 'https', 'executor_id': server.executor_id, 'credential_token': TOKEN}, 'https-target')
        path = source / '小型数据.jsonl'
        path.write_text(json.dumps({'messages': [{'role': 'user', 'content': '协议字节回收'}, {'role': 'assistant', 'content': '原文件。'}]}, ensure_ascii=False) + '\n')
        plan = post(client, '/datasets/import-plans', {'project_id': project['id'], 'path': str(path)})
        asset = post(client, '/datasets/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']}, 'https-data')
        prepare = post(client, '/remote-transfers/prepare', {'project_id': project['id'], 'execution_target_id': target['id'], 'asset_kind': 'dataset', 'asset_id': asset['id']})
        yield client, service, server, target, asset, prepare
    finally: server.stop()


def test_https_target_connection_is_not_cuda_and_missing_ca_is_visible(https_rig, monkeypatch):
    client, service, server, target, _, _ = https_rig
    assert target['origin'] == server.client.target.origin and target['transport'] == 'https'
    checked = post(client, f"/execution-targets/{target['id']}/check", {})
    assert checked['protocol_ready'] and checked['network_remote_ready'] and not checked['nvidia_ready']
    assert checked['validation_scope'] == 'https_protocol_only' and TOKEN not in json.dumps(checked)
    from ailab_control.remote import client as implementation
    def missing_ca(): raise ProtocolError('TLS_TRUST_UNAVAILABLE', '运行时公开 CA 文件不可读取', 503)
    monkeypatch.setattr(implementation, 'create_tls_context', missing_ca)
    failed = post(client, f"/execution-targets/{target['id']}/check", {})
    assert failed['last_error']['code'] == 'TLS_TRUST_UNAVAILABLE'
    assert failed['connection_state'] == 'disconnected' and not failed['protocol_ready'] and not failed['network_remote_ready']
    assert TOKEN not in service.store.path.read_bytes().decode(errors='ignore')


def test_https_product_snapshot_and_recollection_preserve_original_failed_attempt(https_rig, monkeypatch):
    client, service, server, target, asset, prepare = https_rig
    assert prepare['validation_scope'] == 'https_protocol_only' and prepare['transport'] == 'https'
    assert prepare['target']['transport'] == 'https' and prepare['target']['origin'] == server.client.target.origin
    original, failed_once = LoopbackClient.collect, []
    def fail_once(self, *args, **kwargs):
        if not failed_once:
            failed_once.append(True)
            raise ProtocolError('TLS_VERIFICATION_FAILED', '收回时测试证书变化', 503)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(LoopbackClient, 'collect', fail_once)
    body = {'prepare_id': prepare['id'], 'digest': prepare['digest']}
    attempt = post(client, '/remote-transfers', body, 'one-https-attempt')
    failed = wait_attempt(client, attempt['id'], timeout=15)
    assert failed['state'] == 'failed' and failed['compute_outcome'] == 'succeeded'
    assert failed['collection_state'] == 'failed' and failed['allowed_actions'] == ['collect']
    internal = service.store.get('attempt', attempt['id'])
    assert internal['remote_snapshot']['transport'] == 'https'
    assert failed['snapshot']['transport'] == 'https' and failed['snapshot']['validation_scope'] == 'https_protocol_only'
    assert failed['remote_manifest_ref']['manifest']['transport'] == 'https'
    manifest_sha = failed['remote_manifest_ref']['manifest_sha256']
    recollected = post(client, f"/attempts/{attempt['id']}/collections", {'expected_collection_version': failed['collection_version'],
        'manifest_digest': failed['output_manifest_ref']['digest']}, 'only-recollect')
    assert recollected['state'] == 'succeeded'
    latest = client.get(f"/api/v1/attempts/{attempt['id']}").json()
    assert latest['state'] == 'failed' and latest['collection_state'] == 'succeeded'
    assert latest['remote_manifest_ref']['manifest_sha256'] == manifest_sha
    stored_asset = service.store.get('dataset', asset['id'])
    artifact = service.store.get('artifact', latest['artifacts'][0]['id'])
    assert Path(artifact['storage_path']).read_bytes() == (Path(stored_asset['storage_path']) / stored_asset['manifest'][0]['path']).read_bytes()
    assert post(client, '/remote-transfers', body, 'one-https-attempt')['id'] == attempt['id']
    with sqlite3.connect(server.data / 'executor.sqlite3') as db:
        values = [json.loads(row[0]) for row in db.execute('SELECT body FROM attempts')]
    assert len(values) == 1 and values[0]['id'] == attempt['id'] and values[0]['run_count'] == 1


def test_changed_transport_invalidates_existing_upload_preview(https_rig):
    client, service, server, target, _, prepare = https_rig
    value = service.store.get('execution-target', target['id'])
    value['transport'] = 'loopback_http'
    with service.store.transaction(): service.store.put('execution-target', value)
    result = client.post('/api/v1/remote-transfers', json={'prepare_id': prepare['id'], 'digest': prepare['digest']}, headers={'Idempotency-Key': 'reject-mixed'})
    assert result.status_code == 400 and result.json()['error']['code'] == 'LOOPBACK_ONLY'
    with sqlite3.connect(server.data / 'executor.sqlite3') as db:
        assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0
