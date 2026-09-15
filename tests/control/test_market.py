"""真实 loopback 提供方、Range 下载与 SQLite 合同；不代表外部市场接入。"""

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
import time

import pytest

from test_control import rig
from test_media_assets import png
from fixture_market_provider import Provider, decide, write
from ailab_control.assets import file_hash, verify_manifest
from ailab_control.market import LABEL, LoopbackProvider, Market
from ailab_control.storage import Fault, digest


def fails(code, callback):
    with pytest.raises(Fault) as error:
        callback()
    assert error.value.code == code, error.value.message


def entry(root, dataset_key='dialogue', version='v1', schema='sft', access='open', repeated=1):
    directory = root / 'files' / dataset_key / version
    directory.mkdir(parents=True, exist_ok=True)
    if schema == 'sft':
        row = {'messages': [{'role': 'user', 'content': '退货需要什么？'}, {'role': 'assistant', 'content': '请准备订单信息与商品资料。'}]}
        (directory / 'data.jsonl').write_text((json.dumps(row, ensure_ascii=False) + '\n') * repeated)
    else:
        png(directory / 'image.png', width=512, height=512)
        (directory / 'dataset.json').write_text(json.dumps({'version': version, 'samples': [{'path': 'image.png', 'caption': '用于结构测试的单色图片', 'source': '受控测试目录合成夹具', 'sha256': file_hash(directory / 'image.png')}]}, ensure_ascii=False))
    files = [{'path': str(path.relative_to(directory)), 'size': path.stat().st_size, 'sha256': file_hash(path)} for path in sorted(directory.rglob('*')) if path.is_file()]
    return {'dataset_key': dataset_key, 'version': version, 'name': '受控示例 ' + dataset_key, 'description': '仅验证数据传输和结构', 'modality': 'text' if schema == 'sft' else 'image', 'schema': schema, 'sample_count': repeated if schema == 'sft' else 1, 'total_bytes': sum(item['size'] for item in files), 'format': 'JSONL' if schema == 'sft' else 'PNG+JSON', 'provider_text': '测试提供方的原始说明。', 'source_url': None, 'updated_at': None, 'access': access, 'license': {'reference': None, 'provider_text': '受控测试原文；本字段不是法律结论。'}, 'files': files}


@pytest.fixture
def market(rig, tmp_path):
    service = rig[1]
    source = tmp_path / '受控提供方'
    source.mkdir()
    values = [entry(source), entry(source, 'limited', access='restricted'), entry(source, 'pictures', schema='image_caption_v1')]
    write(source / 'catalog.json', {'schema_version': 'market-catalog-v1', 'provider_id': 'fixture-provider', 'catalog_version': 'catalog-v1', 'versions': values})
    provider = Provider(source, tmp_path / '提供方审批记录')
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    connection = LoopbackProvider('fixture-provider', f'http://127.0.0.1:{provider.server_port}')
    project = service.project({'name': '市场协议验收'})
    target = Market(service, [connection])
    yield target, project, provider
    provider.shutdown()
    provider.server_close()
    thread.join(timeout=2)


def browse(market, name='dialogue'):
    target, project, _ = market
    result = target.browse(project['id'], 'fixture-provider')
    assert result['source_label'] == LABEL
    return next(item for item in result['versions'] if item['metadata']['dataset_key'] == name)


def download(market, version, key='download', access_id=None):
    target = market[0]
    value = target.start_download(version['id'], {'user_statement': '仅用于本机数据导入结构测试', **({'access_id': access_id} if access_id else {})}, key)
    return target.execute_download(value['id'], key + '-execute')


def task_context(market, kind='text'):
    target, project, _ = market
    task = target.service.new_task({'project_id': project['id'], 'kind': kind, 'operation': 'train', 'name': '保留原名称与参数'})
    task['draft']['runtime']['seed'] = 817
    task['draft']['input']['prompt'] = '原用户内容'
    task = target.service.save_draft(task['id'], {'expected_revision': task['draft_revision'], 'draft': task['draft']})
    return task, target.enter(task['id'], {'expected_revision': task['draft_revision'], 'step': 'data'}, 'enter-' + task['id'])


@pytest.mark.parametrize('dataset_key,kind', [('dialogue', 'text'), ('pictures', 'image')])
def test_real_download_register_and_return_preserve_task(market, dataset_key, kind):
    target, project, provider = market
    task, context = task_context(market, kind)
    original = copy.deepcopy(task)
    version = browse(market, dataset_key)
    completed = download(market, version)
    assert completed['state'] == 'completed' and completed['complete']
    assert completed['received_bytes'] == version['metadata']['total_bytes']
    assert target.store.get('task', task['id']) == original
    result = target.register_new_dataset(completed['id'], 'register')
    assert target.register_new_dataset(completed['id'], 'register') == result
    assert len(target.store.list('dataset', project['id'])) == 1
    verify_manifest(Path(result['storage_path']), result['manifest'])
    assert result['market_provenance']['metadata']['license'] == version['metadata']['license']
    assert result['market_provenance']['legal_assessment'] is None
    returned = target.use_for_task(context['id'], {'dataset_id': result['id']}, 'use')
    assert target.use_for_task(context['id'], {'dataset_id': result['id']}, 'use') == returned
    expected = copy.deepcopy(original['draft']); expected['dataset_id'] = result['id']
    assert returned['task']['draft'] == expected and returned['task']['name'] == original['name']
    assert returned['task']['draft_revision'] == original['draft_revision'] + 1
    assert returned['return_to'] == {'project_id': project['id'], 'task_id': task['id'], 'kind': kind, 'step': 'data', 'highlight_dataset_id': result['id']}
    assert returned['previous_checks_invalidated'] and provider.ranges


def test_provider_waiting_decision_history_minimal_fields_and_expiry(market):
    target, _, provider = market
    version = browse(market, 'limited')
    payload = {'purpose': '验证中文训练数据格式', 'user_statement': '仅在本机使用测试数据'}
    access = target.request_access(version['id'], payload, 'request')
    assert access['provider_response']['status'] == 'waiting'
    assert target.request_access(version['id'], payload, 'request') == access
    assert len(provider.received_requests) == 1
    assert set(provider.received_requests[0]) == {'provider_id', 'dataset_key', 'version', 'version_digest', 'purpose', 'user_statement', 'request_key'}
    fails('MARKET_ACCESS_NOT_GRANTED', lambda: download(market, version, access_id=access['id']))
    request_id = access['provider_response']['request_id']
    for status in ['denied', 'approved', 'expired', 'revoked']:
        expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat() if status == 'approved' else None
        decide(provider.state, request_id, status, '提供方操作员原文：' + status, expires)
        refreshed = target.refresh_access(access['id'])
        assert refreshed['provider_response']['status'] == status
        if status == 'approved':
            downloaded = download(market, version, 'approved-download', access['id'])
            assert downloaded['state'] == 'completed'
            assert downloaded['history'][-1]['provider_response_at_finish']['status'] == 'approved'
        else:
            fails('MARKET_ACCESS_NOT_GRANTED', lambda: download(market, version, 'blocked-' + status, access['id']))
    assert [item['response']['status'] for item in refreshed['response_history']] == ['waiting', 'denied', 'approved', 'expired', 'revoked']
    decide(provider.state, request_id, 'approved', '已批准但有效期已结束', (datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    fails('MARKET_ACCESS_NOT_GRANTED', lambda: download(market, version, 'old-expiry', access['id']))
    assert target.store.get('market-access', access['id'])['provider_response']['status'] == 'approved'


def test_cancel_preserves_partial_and_real_range_resume(market):
    target, project, provider = market
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    catalog['versions'].append(entry(provider.root, 'large', repeated=20000))
    catalog['catalog_version'] = 'catalog-large'
    write(provider.root / 'catalog.json', catalog)
    version = browse(market, 'large')
    provider.chunk_delay = 0.002
    record = target.start_download(version['id'], {'user_statement': '传输取消与续传测试'}, 'large')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(target.execute_download, record['id'], 'run-one')
        deadline = time.monotonic() + 10
        while target.store.get('market-download', record['id'])['received_bytes'] < 65536 and time.monotonic() < deadline:
            time.sleep(0.005)
        fails('MARKET_DOWNLOAD_BUSY', lambda: target.execute_download(record['id'], 'duplicate-live'))
        target.cancel_download(record['id'], 'cancel')
        cancelled = future.result(timeout=10)
    assert cancelled['state'] == 'cancelled' and not cancelled['complete']
    assert 0 < cancelled['received_bytes'] < version['metadata']['total_bytes']
    fails('MARKET_DOWNLOAD_INCOMPLETE', lambda: target.register_new_dataset(record['id'], 'bad-register'))
    assert not target.store.list('dataset', project['id'])
    assert target.execute_download(record['id'], 'run-one') == cancelled
    restored = Market(target.service, list(target.providers.values()))
    complete = restored.execute_download(record['id'], 'explicit-resume')
    assert complete['complete'] and complete['state'] == 'completed'
    assert provider.ranges[-1]['offset'] == cancelled['received_bytes']
    assert file_hash(target.root / record['id'] / 'files/data.jsonl') == version['metadata']['files'][0]['sha256']


def test_new_version_is_independent_and_old_mutation_is_rejected(market):
    target, project, provider = market
    old = browse(market)
    completed = download(market, old)
    first = target.register_new_dataset(completed['id'], 'register')
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    newer = entry(provider.root, version='v2', repeated=2)
    catalog['versions'].append(newer)
    catalog['catalog_version'] = 'catalog-v2'
    write(provider.root / 'catalog.json', catalog)
    versions = target.browse(project['id'], 'fixture-provider')['versions']
    second_version = next(item for item in versions if item['metadata']['version'] == 'v2')
    second_download = download(market, second_version, 'v2')
    second = target.register_new_dataset(second_download['id'], 'register-v2')
    assert first['id'] != second['id'] and first['version_id'] != second['version_id']
    assert target.store.get('dataset', first['id']) == first and target.store.get('market-version', old['id']) == old
    catalog['versions'][0]['name'] = '改写旧版'
    write(provider.root / 'catalog.json', catalog)
    fails('MARKET_VERSION_CHANGED', lambda: target.browse(project['id'], 'fixture-provider'))


@pytest.mark.parametrize('problem', ['hash', 'schema', 'count'])
def test_bad_bytes_or_schema_never_become_dataset(market, problem):
    target, project, provider = market
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    data = provider.root / 'files/dialogue/v1/data.jsonl'
    if problem == 'schema':
        data.write_text('{"text":"不符合 SFT"}\n')
        catalog['versions'][0]['files'][0].update(size=data.stat().st_size, sha256=file_hash(data))
        catalog['versions'][0]['total_bytes'] = data.stat().st_size
    elif problem == 'count':
        catalog['versions'][0]['sample_count'] = 9
    write(provider.root / 'catalog.json', catalog)
    version = browse(market)
    if problem == 'hash':
        data.write_bytes(b'x' * data.stat().st_size)
    result = download(market, version)
    if problem == 'hash':
        assert result['state'] == 'failed' and result['error']['code'] == 'MARKET_HASH_MISMATCH'
        fails('MARKET_DOWNLOAD_INCOMPLETE', lambda: target.register_new_dataset(result['id'], 'register'))
    else:
        assert result['state'] == 'completed'
        fails('DATA_SCHEMA_MISMATCH', lambda: target.register_new_dataset(result['id'], 'register'))
    assert not target.store.list('dataset', project['id'])


@pytest.mark.parametrize('problem', ['revision', 'kind', 'project', 'busy', 'recovery', 'immutable'])
def test_return_conflict_leaves_task_and_registered_data_unchanged(market, problem):
    target, project, _ = market
    task, context = task_context(market)
    version = browse(market, 'pictures' if problem == 'kind' else 'dialogue')
    completed = download(market, version)
    dataset = target.register_new_dataset(completed['id'], 'register')
    with target.store.transaction():
        if problem == 'revision': task['draft_revision'] += 1
        if problem == 'immutable': task['immutable_draft'] = True
        if problem == 'project':
            # 资源借用必须拒绝，数据本身仍保留。
            other = target.service.resource('dataset', project['id'], **{key: value for key, value in dataset.items() if key not in {'id', 'project_id', 'created_at', 'resource_type'}})
            other['project_id'] = 'other-project'
            # 外键由实际另一项目满足。
            from ailab_control.storage import now
            target.store.put('project', {'id': 'other-project', 'name': '另一个项目', 'created_at': now()})
            target.store.put('dataset', other)
            dataset = other
        if problem in {'busy', 'recovery'}:
            attempt = target.service.resource('attempt', project['id'], task_id=task['id'], state='failed' if problem == 'recovery' else 'paused', recovery_required=problem == 'recovery')
            target.store.put('attempt', attempt)
        target.store.put('task', task)
    before = target.store.get('task', task['id'])
    expected = {'revision': 'REVISION_CONFLICT', 'kind': 'DATA_SCHEMA_MISMATCH', 'project': 'PROJECT_MISMATCH', 'busy': 'MARKET_TASK_BUSY', 'recovery': 'MARKET_TASK_BUSY', 'immutable': 'MARKET_TASK_UNSUPPORTED'}[problem]
    fails(expected, lambda: target.use_for_task(context['id'], {'dataset_id': dataset['id']}, 'use'))
    assert target.store.get('task', task['id']) == before
    assert target.store.get('dataset', dataset['id']) == dataset


def test_parallel_return_only_commits_once(market):
    target = market[0]
    task, context = task_context(market)
    dataset = target.register_new_dataset(download(market, browse(market))['id'], 'register')
    payload = {'dataset_id': dataset['id']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: target.use_for_task(context['id'], payload, 'same-command'), range(2)))
    assert results[0] == results[1]
    assert target.store.get('task', task['id'])['draft_revision'] == task['draft_revision'] + 1
    fails('REVISION_CONFLICT', lambda: target.use_for_task(context['id'], payload, 'different-command'))


@pytest.mark.parametrize('origin', ['https://127.0.0.1:80', 'http://localhost:80', 'http://192.168.1.1:80', 'http://127.0.0.1:80/path', 'http://user@127.0.0.1:80', 'http://127.0.0.2:80'])
def test_registry_does_not_expand_to_arbitrary_network(origin):
    fails('MARKET_SOURCE_NOT_ALLOWED', lambda: LoopbackProvider('fixture', origin))


def test_redirect_and_unregistered_source_are_rejected(market):
    target, project, provider = market
    fails('MARKET_SOURCE_NOT_ALLOWED', lambda: target.browse(project['id'], 'unknown'))
    provider.redirect = True
    fails('MARKET_REDIRECT_FORBIDDEN', lambda: target.browse(project['id'], 'fixture-provider'))


def test_provider_cannot_rewrite_approval_revision(market):
    target, _, provider = market
    version = browse(market, 'limited')
    access = target.request_access(version['id'], {'purpose': '验证审批版本', 'user_statement': '本机测试'}, 'request')
    path = provider.state / (access['provider_response']['request_id'] + '.json')
    value = json.loads(path.read_text())
    value['response']['status'] = 'approved'
    write(path, value)
    fails('MARKET_ACCESS_STALE', lambda: target.refresh_access(access['id']))
    assert target.store.get('market-access', access['id']) == access


def test_actual_network_disconnect_keeps_prefix_and_resume_reuses_it(market):
    target, _, provider = market
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    catalog['versions'].append(entry(provider.root, 'disconnect', repeated=3000))
    catalog['catalog_version'] = 'catalog-disconnect'
    write(provider.root / 'catalog.json', catalog)
    version = browse(market, 'disconnect')
    provider.disconnect_once_after = 131072
    failed = download(market, version)
    assert failed['state'] == 'failed' and not failed['complete']
    prefix = failed['received_bytes']
    assert 0 < prefix < version['metadata']['total_bytes']
    completed = target.execute_download(failed['id'], 'explicit-network-resume')
    assert completed['state'] == 'completed'
    assert provider.ranges[-1]['offset'] == prefix


def test_bad_http_range_never_appends_data(market):
    target, _, provider = market
    version = browse(market)
    provider.bad_range = True
    result = download(market, version)
    assert result['state'] == 'failed' and result['error']['code'] == 'MARKET_RANGE_MISMATCH'
    assert result['received_bytes'] == 0 and not result['complete']
    assert not list((target.root / result['id'] / 'files').rglob('*.jsonl'))


def test_provider_revocation_during_transfer_prevents_completion(market):
    target, _, provider = market
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    catalog['versions'].append(entry(provider.root, 'revocation', repeated=3000, access='restricted'))
    catalog['catalog_version'] = 'catalog-revocation'
    write(provider.root / 'catalog.json', catalog)
    version = browse(market, 'revocation')
    access = target.request_access(version['id'], {'purpose': '测试传输期间撤销', 'user_statement': '本机测试'}, 'request')
    request_id = access['provider_response']['request_id']
    decide(provider.state, request_id, 'approved', '提供方允许本次下载')
    record = target.start_download(version['id'], {'user_statement': '本机测试', 'access_id': access['id']}, 'download')
    provider.chunk_delay = 0.002
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(target.execute_download, record['id'], 'run')
        deadline = time.monotonic() + 10
        while target.store.get('market-download', record['id'])['received_bytes'] < 65536 and time.monotonic() < deadline:
            time.sleep(0.005)
        decide(provider.state, request_id, 'revoked', '提供方已撤销此次测试访问')
        result = future.result(timeout=10)
    assert result['state'] == 'failed' and result['error']['code'] == 'MARKET_ACCESS_NOT_GRANTED'
    assert not result['complete'] and result['received_bytes'] == version['metadata']['total_bytes']
    fails('MARKET_DOWNLOAD_INCOMPLETE', lambda: target.register_new_dataset(result['id'], 'register'))


def test_catalog_revision_and_removal_are_explicit(market):
    target, project, provider = market
    version = browse(market)
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    original = copy.deepcopy(catalog)
    catalog['versions'].append(entry(provider.root, 'new-entry'))
    write(provider.root / 'catalog.json', catalog)
    fails('MARKET_CATALOG_CHANGED', lambda: target.browse(project['id'], 'fixture-provider'))
    assert len(target.store.list('market-version', project['id'])) == 3
    original['versions'] = original['versions'][1:]
    original['catalog_version'] = 'catalog-removed'
    write(provider.root / 'catalog.json', original)
    result = download(market, version)
    assert result['state'] == 'failed' and result['error']['code'] == 'MARKET_VERSION_UNAVAILABLE'


def test_partial_directory_symlink_is_rejected_before_writing(market, tmp_path):
    target = market[0]
    version = browse(market)
    record = target.start_download(version['id'], {'user_statement': '下载路径测试'}, 'download')
    outside = tmp_path / '不能写入的目录'
    outside.mkdir()
    (target.root / record['id']).symlink_to(outside, target_is_directory=True)
    result = target.execute_download(record['id'], 'run')
    assert result['state'] == 'failed' and result['error']['code'] == 'PATH_NOT_ALLOWED'
    assert not list(outside.iterdir())


@pytest.mark.parametrize('damage', ['extra_field', 'path_escape', 'duplicate_file', 'boolean_size', 'unsupported_schema', 'null_access'])
def test_invalid_catalog_never_registers_version(market, damage):
    target, project, provider = market
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    value = catalog['versions'][0]
    if damage == 'extra_field': value['download_url'] = 'http://192.168.1.1/private'
    elif damage == 'path_escape': value['files'][0]['path'] = '../private.jsonl'
    elif damage == 'duplicate_file': value['files'].append(value['files'][0])
    elif damage == 'boolean_size': value['files'][0]['size'] = True
    elif damage == 'unsupported_schema': value['schema'] = 'executable'
    elif damage == 'null_access': value['access'] = None
    write(provider.root / 'catalog.json', catalog)
    with pytest.raises(Fault):
        target.browse(project['id'], 'fixture-provider')
    assert not target.store.list('market-version', project['id'])


def test_request_idempotency_payload_and_provider_identity(market):
    target, _, provider = market
    version = browse(market, 'limited')
    payload = {'purpose': '最少字段测试', 'user_statement': '本机测试'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: target.request_access(version['id'], payload, 'same'), range(2)))
    assert responses[0] == responses[1] and len(provider.received_requests) == 1
    fails('IDEMPOTENCY_CONFLICT', lambda: target.request_access(version['id'], {**payload, 'purpose': '另一目的'}, 'same'))
    path = provider.state / (responses[0]['provider_response']['request_id'] + '.json')
    value = json.loads(path.read_text())
    value['response']['provider_id'] = 'another-provider'
    write(path, value)
    fails('MARKET_ACCESS_MISMATCH', lambda: target.refresh_access(responses[0]['id']))


def test_old_preflight_is_rejected_after_explicit_market_return(market, monkeypatch):
    target, project, _ = market
    task, context = task_context(market)
    with target.store.transaction():
        check = target.service.resource('preflight', project['id'], task_id=task['id'], draft_revision=task['draft_revision'], can_submit=True)
        target.store.put('preflight', check)
    dataset = target.register_new_dataset(download(market, browse(market))['id'], 'register')
    target.use_for_task(context['id'], {'dataset_id': dataset['id']}, 'use')
    monkeypatch.setattr(target.service, 'inspect_task', lambda *_: pytest.fail('旧检查应在调用慢检查器之前拒绝'))
    fails('REVISION_CONFLICT', lambda: target.service.submit(task['id'], {'preflight_id': check['id'], 'expected_revision': task['draft_revision']}, 'old-check'))
    assert not target.store.list('attempt', project['id'])


def test_unknown_metadata_stays_unknown_and_corrupt_asset_cannot_be_used(market):
    target, _, provider = market
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    catalog['versions'][0].update(license=None, sample_count=None)
    write(provider.root / 'catalog.json', catalog)
    version = browse(market)
    dataset = target.register_new_dataset(download(market, version)['id'], 'register')
    assert dataset['market_provenance']['metadata']['sample_count'] is None
    assert dataset['market_provenance']['metadata']['license'] is None
    assert dataset['sample_count'] == 1
    task, context = task_context(market)
    file = Path(dataset['storage_path']) / dataset['entrypoint']
    file.chmod(0o600)
    file.write_bytes(b'x' * file.stat().st_size)
    fails('ARTIFACT_CORRUPT', lambda: target.use_for_task(context['id'], {'dataset_id': dataset['id']}, 'use'))
    assert target.store.get('task', task['id']) == task


def test_broken_final_file_symlink_cannot_create_external_target(market, tmp_path):
    target = market[0]
    version = browse(market)
    record = target.start_download(version['id'], {'user_statement': '断开的链接测试'}, 'download')
    files = target.root / record['id'] / 'files'
    files.mkdir(parents=True)
    outside = tmp_path / '不得创建.jsonl'
    (files / 'data.jsonl').symlink_to(outside)
    result = target.execute_download(record['id'], 'execute')
    assert result['state'] == 'failed' and result['error']['code'] == 'PATH_NOT_ALLOWED'
    assert not outside.exists()


@pytest.mark.parametrize('changed', ['data-version', 'catalog-version'])
def test_provider_identity_cannot_be_rewritten_via_another_project(market, changed):
    target, project, provider = market
    original = browse(market)
    other = target.service.project({'name': '另一项目'})
    same = target.browse(other['id'], 'fixture-provider')['versions'][0]
    assert same['project_id'] == other['id'] and same['id'] != original['id']
    assert same['version_digest'] == original['version_digest']
    third = target.service.project({'name': '尚未浏览的新项目'})
    catalog = json.loads((provider.root / 'catalog.json').read_text())
    if changed == 'data-version': catalog['versions'][0]['name'] = '借项目切换改写旧版本'
    else: catalog['versions'].append(entry(provider.root, 'added'))
    write(provider.root / 'catalog.json', catalog)
    fails('MARKET_VERSION_CHANGED' if changed == 'data-version' else 'MARKET_CATALOG_CHANGED', lambda: target.browse(third['id'], 'fixture-provider'))
    assert not target.store.list('market-version', third['id'])
    assert target.store.get('market-version', original['id']) == original


def test_activity_is_project_and_version_isolated(market):
    target, _, _ = market
    original = browse(market)
    completed = download(market, original)
    imported = target.register_new_dataset(completed['id'], 'register')
    other = target.service.project({'name': '另一个项目'})
    second = target.browse(other['id'], 'fixture-provider')['versions'][0]
    assert target.activity(second['id']) == {'access_requests': [], 'downloads': [], 'datasets': []}
    activity = target.activity(original['id'])
    assert activity['downloads'][0]['id'] == completed['id']
    assert activity['datasets'][0]['id'] == imported['id'] and 'storage_path' not in activity['datasets'][0]
