"""实际控制 HTTP、受管线程、停止和备份边界；提供方仍是独立 loopback 协议。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from test_control import rig
from test_market import market, browse, download, entry, fails, task_context
from fixture_market_provider import write
from ailab_control.api import create_app
from ailab_control.assets import file_hash, verify_manifest
from ailab_control.market import Market
from ailab_control.market_api import mount_market, schedule_download
from ailab_control.service import Service, Settings


@pytest.fixture
def market_http(market, rig):
    target, project, provider = market
    target.service.market = target
    client = rig[0]
    mount_market(client.app, target.service)
    return client, target, project, provider


def post(client, path, body, key):
    response = client.post('/api/v1' + path, json=body, headers={'Idempotency-Key': key})
    assert response.status_code == 200, response.text
    return response.json()


def poll(client, download_id, terminal=True):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get('/api/v1/market/downloads/' + download_id)
        assert response.status_code == 200, response.text
        record = response.json()
        if (record['state'] in {'completed', 'failed', 'cancelled'}) if terminal else record['received_bytes'] >= 65536:
            return record
        time.sleep(0.005)
    raise AssertionError('市场下载未在预期时间完成阶段')


def settled(service, download_id):
    deadline = time.monotonic() + 10
    while any(thread.name == 'market-download-' + download_id for thread in service.threads) and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not any(thread.name == 'market-download-' + download_id for thread in service.threads)


def large_version(market_http):
    _, target, project, provider = market_http
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    catalog['catalog_version'] = 'catalog-large'
    catalog['versions'].append(entry(provider.root, 'large-http', repeated=10000))
    write(provider.root / 'catalog.json', catalog)
    provider.chunk_delay = 0.002
    return next(item for item in target.browse(project['id'], 'fixture-provider')['versions'] if item['metadata']['dataset_key'] == 'large-http')


def test_http_full_download_import_return_and_repeat_does_not_restart(market_http):
    client, target, project, provider = market_http
    assert client.get('/api/v1/market/sources').json()['items'][0]['source_label'] == '受控测试来源'
    catalog = client.get('/api/v1/market/catalog', params={'project_id': project['id'], 'provider_id': 'fixture-provider'}).json()
    version = catalog['versions'][0]
    task, _ = task_context((target, project, provider))
    context = post(client, f'/tasks/{task["id"]}/market-contexts', {'expected_revision': task['draft_revision'], 'step': 'data'}, 'http-enter')
    payload = {'version_id': version['id'], 'user_statement': '真实 HTTP 传输验收'}
    started = post(client, '/market/downloads', payload, 'http-start')
    completed = poll(client, started['id'])
    settled(target.service, started['id'])
    assert completed['complete']
    requests = len(provider.ranges)
    repeated = post(client, '/market/downloads', payload, 'http-start')
    assert repeated['id'] == started['id'] and repeated['state'] == 'completed'
    assert len(provider.ranges) == requests and not target.service.threads
    imported = post(client, f'/market/downloads/{started["id"]}/datasets', {}, 'http-register')
    assert 'storage_path' not in imported
    assert target.store.get('task', task['id']) == task
    applied = post(client, f'/market/contexts/{context["id"]}/use', {'dataset_id': imported['id']}, 'http-use')
    assert applied['task']['draft']['dataset_id'] == imported['id']
    assert applied['task']['draft']['runtime'] == task['draft']['runtime']
    activity = client.get('/api/v1/market/versions/' + version['id'] + '/activity').json()
    assert [item['id'] for item in activity['datasets']] == [imported['id']]


def test_http_auth_and_strict_source_payloads(market_http):
    client, target, project, provider = market_http
    version = browse((target, project, provider))
    assert client.get('/api/v1/market/sources', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    for field, value in [('origin', 'http://192.168.1.1'), ('path', '/private'), ('provider_id', 'unregistered')]:
        response = client.post('/api/v1/market/downloads', json={'version_id': version['id'], 'user_statement': '测试', field: value}, headers={'Idempotency-Key': 'invalid-' + field})
        assert response.status_code == 422
    assert not target.store.list('market-download')
    assert client.post('/api/v1/market/downloads', json={'version_id': version['id'], 'user_statement': '测试'}).status_code == 400


def test_http_cancel_then_explicit_resume_and_concurrent_repeat(market_http):
    client, target, _, provider = market_http
    version = large_version(market_http)
    payload = {'version_id': version['id'], 'user_statement': '取消后明确继续'}
    started = post(client, '/market/downloads', payload, 'initial')
    poll(client, started['id'], terminal=False)
    post(client, f'/market/downloads/{started["id"]}/cancel', {}, 'cancel')
    cancelled = poll(client, started['id'])
    settled(target.service, started['id'])
    assert cancelled['state'] == 'cancelled' and not cancelled['complete']
    repeated = post(client, '/market/downloads', payload, 'initial')
    assert repeated['state'] == 'cancelled'
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: post(client, f'/market/downloads/{started["id"]}/resume', {}, 'one-resume'), range(2)))
    assert result[0]['id'] == result[1]['id'] == started['id']
    completed = poll(client, started['id'])
    settled(target.service, started['id'])
    assert completed['state'] == 'completed' and provider.ranges[-1]['offset'] == cancelled['received_bytes']
    before = len(provider.ranges)
    assert post(client, f'/market/downloads/{started["id"]}/resume', {}, 'one-resume')['state'] == 'completed'
    assert len(provider.ranges) == before


def test_cancel_between_scheduling_and_thread_start_is_not_reset(market_http, monkeypatch):
    _, target, _, _ = market_http
    version = large_version(market_http)
    record = target.start_download(version['id'], {'user_statement': '取消与排程竞争'}, 'start')
    scheduled = []
    real_start = threading.Thread.start

    def held_start(thread):
        if thread.name == 'market-download-' + record['id']:
            scheduled.append(thread)
        else:
            real_start(thread)

    monkeypatch.setattr(threading.Thread, 'start', held_start)
    schedule_download(target.service, record['id'], 'scheduled')
    target.cancel_download(record['id'], 'cancel-before-thread')
    assert len(scheduled) == 1
    monkeypatch.setattr(threading.Thread, 'start', real_start)
    scheduled[0].start()
    scheduled[0].join(timeout=10)
    assert not scheduled[0].is_alive()
    current = target.store.get('market-download', record['id'])
    assert current['state'] == 'cancelled' and current['received_bytes'] == 0
    assert not target.service.threads


def test_service_close_stops_download_and_releases_owned_thread(market_http):
    client, target, _, _ = market_http
    version = large_version(market_http)
    started = post(client, '/market/downloads', {'version_id': version['id'], 'user_statement': '服务退出验收'}, 'start-close')
    poll(client, started['id'], terminal=False)
    target.service.close()
    settled(target.service, started['id'])
    assert target.service.shutdown_complete and not target.service.threads
    with closing(sqlite3.connect(target.store.path.as_uri() + '?mode=ro', uri=True)) as connection:
        row = connection.execute('SELECT body FROM resources WHERE id=? AND kind=?', (started['id'], 'market-download')).fetchone()
        assert row is not None
        result = json.loads(row[0])
    assert result['state'] == 'cancelled' and not result['complete']
    partial = target.root / started['id'] / 'files/data.jsonl'
    assert partial.stat().st_size == result['received_bytes'] > 0
    fails('SERVICE_STOPPING', lambda: schedule_download(target.service, started['id'], 'new-after-close', resume=True))


def test_restart_marks_unstarted_record_interrupted_and_original_key_cannot_start_it(market_http):
    _, target, project, provider = market_http
    version = browse((target, project, provider))
    record = target.start_download(version['id'], {'user_statement': '启动中断测试'}, 'original')
    settings = copy.copy(target.service.settings)
    settings.market_providers = [('fixture-provider', f'http://127.0.0.1:{provider.server_port}')]
    target.service.close()
    app = create_app(settings)
    restored = app.state.service
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer ' + settings.token}) as client:
        current = client.get('/api/v1/market/downloads/' + record['id']).json()
        assert current['state'] == 'failed' and current['error']['code'] == 'MARKET_DOWNLOAD_INTERRUPTED'
        replay = post(client, '/market/downloads', {'version_id': version['id'], 'user_statement': '启动中断测试'}, 'original')
        assert replay['state'] == 'failed' and not restored.threads and provider.ranges == []
        post(client, f'/market/downloads/{record["id"]}/resume', {}, 'explicit-after-restart')
        assert poll(client, record['id'])['state'] == 'completed'
        settled(restored, record['id'])


def test_backup_retains_unimported_download_then_restores_registered_assets(market_http, tmp_path):
    client, target, project, provider = market_http
    version = browse((target, project, provider))
    record = target.start_download(version['id'], {'user_statement': '备份范围验收'}, 'prepare')
    fails('BACKUP_BUSY', lambda: target.service.backup('blocked-queued'))
    complete = target.execute_download(record['id'], 'execute')
    assert complete['complete']
    unimported = target.service.backup('unimported-complete')
    assert any(item['path'].startswith('market-downloads/') for item in target.service.backup_manager.verify(Path(unimported['backup_path']))['files'])
    dataset = target.register_new_dataset(record['id'], 'register')
    backup = target.service.backup('registered-backup')
    destination = tmp_path / '恢复父目录'
    destination.mkdir()
    target.service.settings.export_roots.append(destination)
    plan = target.service.backup_manager.plan({'backup_path': backup['backup_path'], 'target_dir': str(destination)})
    result = target.service.backup_manager.restore({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'restore-market')
    restored = Service(Settings(Path(result['restored_path']), 'restored-market-token'))
    try:
        retained = restored.store.get('dataset', dataset['id'])
        verify_manifest(Path(retained['storage_path']), retained['manifest'])
        assert retained['market_provenance'] == dataset['market_provenance']
        assert restored.store.get('market-version', version['id']) == version
        assert restored.store.get('market-download', record['id'])['dataset_id'] == dataset['id']
        assert not restored.market.sources()
        restored.backup_manager.idle()
    finally:
        restored.close()
