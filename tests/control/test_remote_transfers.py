"""产品 API 的真实上传、独立执行、断线、取消与原清单补收。"""

import json
from pathlib import Path
import sqlite3
import sys
import threading
import time

import pytest

from test_control import rig, post, wait_attempt
from ailab_control.remote.client import LoopbackClient
from ailab_control.remote.protocol import ProtocolError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'remote'))
from test_protocol import RunningServer


@pytest.fixture
def remote_rig(rig, tmp_path):
    client, service, source, _ = rig
    root = tmp_path / 'remote'; root.mkdir()
    server = RunningServer(root)
    try:
        project = post(client, '/projects', {'name': '远端传输项目'})
        target = post(client, '/execution-targets', {'name': '独立回环服务', 'project_id': project['id'],
                       'origin': f'http://127.0.0.1:{server.port}', 'executor_id': server.executor_id, 'credential_token': server.token}, 'target')
        input_path = source / '传输数据.jsonl'
        input_path.write_text(json.dumps({'messages': [{'role': 'user', 'content': '验证范围'}, {'role': 'assistant', 'content': '只测试文件传输。'}]}, ensure_ascii=False) + '\n')
        plan = post(client, '/datasets/import-plans', {'project_id': project['id'], 'path': str(input_path)})
        asset = post(client, '/datasets/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']}, 'dataset')
        prepare_payload = {'project_id': project['id'], 'execution_target_id': target['id'], 'asset_kind': 'dataset', 'asset_id': asset['id']}
        prepare = post(client, '/remote-transfers/prepare', prepare_payload)
        yield client, service, server, project, target, asset, prepare, prepare_payload
    finally:
        server.cleanup()


def submit_transfer(value, key='transfer'):
    client, *_rest, prepare, _ = value
    body = {'prepare_id': prepare['id'], 'digest': prepare['digest']}
    return post(client, '/remote-transfers', body, key), body


def executions(server):
    with sqlite3.connect(server.data / 'executor.sqlite3') as database:
        return [json.loads(row[0]) for row in database.execute('SELECT body FROM attempts')]


def test_product_transfer_end_to_end_single_execution_and_saved_bytes(remote_rig, monkeypatch):
    client, service, server, project, target, asset, prepare, _ = remote_rig
    assert prepare['model_execution'] is False and prepare['total_bytes'] > 0
    assert prepare['target']['revision'] == target['revision']
    original_events = LoopbackClient.events
    monkeypatch.setattr(LoopbackClient, 'events', lambda self, attempt_id, after=0, limit=100: original_events(self, attempt_id, after, min(limit, 7)))
    attempt, body = submit_transfer(remote_rig)
    completed = wait_attempt(client, attempt['id'], timeout=15)
    assert completed['state'] == 'succeeded', completed
    assert completed['snapshot']['operation'] == 'transfer'
    assert completed['collection_state'] == 'succeeded' and len(completed['artifacts']) == 1
    source = service.store.get('dataset', asset['id'])
    artifact = service.store.get('artifact', completed['artifacts'][0]['id'])
    assert Path(artifact['storage_path']).read_bytes() == (Path(source['storage_path']) / source['manifest'][0]['path']).read_bytes()
    replay = post(client, '/remote-transfers', body, 'transfer')
    assert replay['id'] == attempt['id'] and len(executions(server)) == 1
    assert client.get('/api/v1/remote-transfers', params={'project_id': project['id']}).json()['items'][0]['id'] == attempt['id']
    events = client.get(f"/api/v1/attempts/{attempt['id']}/events").json()['items']
    assert any(item['type'] == 'upload_progress' for item in events)
    assert any(item['type'] == 'remote_event' for item in events)
    assert 'source_files' not in completed and server.token not in json.dumps(completed)
    assert completed['remote_event_cursor'] == server.client.attempt(attempt['id'])['last_event_sequence']


def test_upload_preview_rejects_changed_target_revision_and_file(remote_rig):
    client, service, server, _project, target, asset, prepare, _ = remote_rig
    post(client, f"/execution-targets/{target['id']}/credentials", {'credential_token': server.token, 'expected_revision': 1})
    result = client.post('/api/v1/remote-transfers', json={'prepare_id': prepare['id'], 'digest': prepare['digest']}, headers={'Idempotency-Key': 'changed'})
    assert result.status_code == 409 and result.json()['error']['code'] == 'TRANSFER_PLAN_CHANGED'
    assert executions(server) == []


def test_remote_disconnect_cancel_unknown_then_original_result_reconciles(remote_rig):
    client, service, server, *_ = remote_rig
    attempt, _ = submit_transfer(remote_rig)
    current = wait_attempt(client, attempt['id'], lambda value: value.get('remote_submitted') is True)
    server.stop()
    unknown = wait_attempt(client, attempt['id'], lambda value: value['connection_state'] == 'disconnected')
    cancelled = post(client, f"/attempts/{attempt['id']}/cancel", {'expected_state_version': unknown['state_version']}, 'cancel-disconnected')
    assert cancelled['state'] == 'cancelling' and cancelled['stop_status'] == 'unknown'
    assert cancelled['compute_outcome'] == 'pending'
    server.start()
    latest = client.get(f"/api/v1/attempts/{attempt['id']}").json()
    post(client, f"/attempts/{attempt['id']}/reconcile", {'expected_state_version': latest['state_version']}, 'reconnect')
    completed = wait_attempt(client, attempt['id'], timeout=15)
    assert completed['state'] in {'succeeded', 'cancelled'}, completed
    assert len(executions(server)) == 1
    assert executions(server)[0]['id'] == attempt['id']


def test_collection_failure_recollects_original_manifest_without_reexecution(remote_rig, monkeypatch):
    client, service, server, *_ = remote_rig
    original = LoopbackClient.collect
    failed_once = []
    def fail_once(self, *args, **kwargs):
        if not failed_once:
            failed_once.append(True)
            raise ProtocolError('REMOTE_UNAVAILABLE', '回收链路中断。', 503)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(LoopbackClient, 'collect', fail_once)
    attempt, _ = submit_transfer(remote_rig)
    failed = wait_attempt(client, attempt['id'], timeout=15)
    assert failed['state'] == 'failed' and failed['compute_outcome'] == 'succeeded'
    assert failed['collection_state'] == 'failed' and failed['allowed_actions'] == ['collect']
    original_manifest = failed['remote_manifest_ref']['manifest_sha256']
    body = {'expected_collection_version': failed['collection_version'], 'manifest_digest': failed['output_manifest_ref']['digest']}
    collected = post(client, f"/attempts/{attempt['id']}/collections", body, 'recollect')
    assert collected['state'] == 'succeeded', collected
    latest = client.get(f"/api/v1/attempts/{attempt['id']}").json()
    assert latest['state'] == 'failed' and latest['collection_state'] == 'succeeded'
    assert latest['remote_manifest_ref']['manifest_sha256'] == original_manifest
    assert len(executions(server)) == 1


def test_connected_cancel_confirms_remote_process_exit(remote_rig):
    client, service, server, *_ = remote_rig
    attempt, _ = submit_transfer(remote_rig)
    current = wait_attempt(client, attempt['id'], lambda value: value.get('remote_submitted') is True)
    cancelled = post(client, f"/attempts/{attempt['id']}/cancel", {'expected_state_version': current['state_version']}, 'connected-cancel')
    completed = wait_attempt(client, attempt['id'], timeout=15)
    assert completed['state'] == 'cancelled' and completed['stop_status'] == 'confirmed', completed
    record = server.client.attempt(attempt['id'])
    assert record['process_status'] == 'absent'


def test_cancel_before_upload_does_not_submit_or_send_a_blob(remote_rig, monkeypatch):
    client, service, server, *_ = remote_rig
    entered, release = threading.Event(), threading.Event()
    original = LoopbackClient.upload
    def wait_upload(self, *args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(LoopbackClient, 'upload', wait_upload)
    attempt, _ = submit_transfer(remote_rig)
    try:
        assert entered.wait(2)
        current = client.get(f"/api/v1/attempts/{attempt['id']}").json()
        cancelled = post(client, f"/attempts/{attempt['id']}/cancel", {'expected_state_version': current['state_version']}, 'before-upload')
        assert cancelled['state'] == 'cancelled' and cancelled['stop_status'] == 'confirmed'
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while attempt['id'] in service.remote_execution.running and time.monotonic() < deadline:
        time.sleep(.02)
    assert executions(server) == []
    assert list((server.data / 'blobs').iterdir()) == []


def test_changed_input_bytes_after_preview_prevent_any_upload(remote_rig):
    client, service, server, project, target, asset, prepare, _ = remote_rig
    record = service.store.get('dataset', asset['id'])
    path = Path(record['storage_path']) / record['manifest'][0]['path']
    path.chmod(0o600); path.write_text('changed')
    response = client.post('/api/v1/remote-transfers', json={'prepare_id': prepare['id'], 'digest': prepare['digest']}, headers={'Idempotency-Key': 'changed-file'})
    assert response.status_code == 409 and response.json()['error']['code'] == 'ARTIFACT_CORRUPT'
    assert executions(server) == [] and list((server.data / 'blobs').iterdir()) == []
