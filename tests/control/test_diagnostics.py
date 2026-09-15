"""诊断摘要、真实 ZIP 写入、并发取消与故障回执；不启动模型。"""

import errno
import hashlib
import json
import os
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import zipfile

import pytest

from test_control import rig, setup_task, post
from ailab_control.diagnostics import Diagnostics, dependency_summary
from ailab_control.service import Service
from ailab_control.storage import Fault, encode
import ailab_control.diagnostics as module


def setup(rig, tmp_path):
    project, _, task = setup_task(rig, 'SECRET_PROMPT_91')
    service = rig[1]
    target = tmp_path / '诊断导出 目录'
    target.mkdir()
    service.settings.export_roots = [target]
    diagnostics = Diagnostics(service)
    return diagnostics, project, task, target


def attempt(service, project, **fields):
    value = service.resource('attempt', project['id'], state='failed', compute_outcome='failed', collection_state='not_started',
                             terminal_reason='WORKER_FAILED', snapshot={'kind': 'text', 'operation': 'generate'})
    value.update(fields)
    with service.store.transaction():
        service.store.put('attempt', value)
    return value


def export(diagnostics, preview, target, key='export-diagnostic'):
    return diagnostics.export({'preview_id': preview['id'], 'target_dir': str(target)}, key)


def test_empty_library_can_preview_and_export_without_new_database_tables(rig, tmp_path):
    diagnostics = Diagnostics(rig[1])
    before = list(rig[1].store.db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
    target = tmp_path / 'empty-export'; target.mkdir()
    rig[1].settings.export_roots = [target]
    preview = diagnostics.preview({})
    assert preview['diagnostics']['scope'] == {'project_count': 0, 'selected_attempt_count': 0}
    from ailab_control import __version__, __build__, __version_label__
    application = preview['diagnostics']['application']
    assert (application['version'], application['build'], application['version_label']) == (__version__, __build__, __version_label__)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'succeeded' and Path(result['saved_path']).is_file()
    assert list(rig[1].store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")) == before


def test_whitelist_omits_poisoned_names_paths_inputs_outputs_logs_and_unknown_fields(rig, tmp_path, monkeypatch):
    diagnostics, project, task, target = setup(rig, tmp_path)
    secret = 'NEVER_EXPORT_SECRET_79'
    environment = {'engine': 'mlx', 'device_id': 'apple-gpu', 'ready': True, 'execution_backend': 'external_python',
                   'token': secret, 'identity': {'python': '/Users/' + secret + '/python'}, 'reason': secret,
                   'versions': {'python': '3.13.9', 'dependencies': {'mlx': '0.32.2', 'torch': secret, 'unknown_package': secret},
                                'sources': {'/Users/' + secret + '/worker.py': secret}, 'runtime_manifest_sha256': secret}}
    poisoned = attempt(rig[1], project, name=secret, output_text=secret, env={'token': secret}, error={'message': secret},
                       snapshot={'kind': 'text', 'operation': 'generate', 'input': {'prompt': secret}, 'dataset': secret,
                                 'environment': environment, 'runtime': {'token': secret}, 'unknown': secret})
    rig[1].environment_cache = ('cached-digest', environment)
    monkeypatch.setattr(rig[1], 'environment', lambda *args, **kwargs: pytest.fail('不得启动依赖 probe'))
    monkeypatch.setattr(rig[1].media, 'environment', lambda *args, **kwargs: pytest.fail('不得启动媒体 probe'))
    monkeypatch.setattr(rig[1].store, 'events', lambda *args, **kwargs: pytest.fail('不得读取原日志'))
    before_attempts = len(rig[1].store.list('attempt'))
    preview = diagnostics.preview({'project_id': project['id'], 'attempt_ids': [poisoned['id']]})
    result = export(diagnostics, preview, target)
    assert result['status'] == 'succeeded'
    with zipfile.ZipFile(result['saved_path']) as archive:
        assert archive.namelist() == ['diagnostics.json', 'manifest.json']
        contents = b'\n'.join(archive.read(name) for name in archive.namelist()).decode()
        data = json.loads(archive.read('diagnostics.json'))
        manifest = json.loads(archive.read('manifest.json'))
    assert secret not in contents and 'SECRET_PROMPT_91' not in contents
    assert '/Users/' not in contents and str(target) not in contents and str(rig[1].root) not in contents
    assert project['name'] not in contents and task['name'] not in contents
    assert data['selected_attempts'][0]['error_code'] == 'WORKER_FAILED'
    assert data['known_error_code_counts'] == {'WORKER_FAILED': 1}
    assert data['dependency_observations'][0]['packages'] == {'mlx': '0.32.2'}
    assert manifest['complete'] and manifest['files'][0]['sha256'] == hashlib.sha256(encode(data).encode() + b'\n').hexdigest()
    assert len(rig[1].store.list('attempt')) == before_attempts and not rig[1].processes


def test_unknown_enum_error_and_version_are_counted_without_free_text(rig, tmp_path):
    diagnostics, project, _, _ = setup(rig, tmp_path)
    secret = 'SECRET_UNLISTED_87'
    attempt(rig[1], project, state=secret, terminal_reason=secret, snapshot={'kind': secret, 'operation': secret})
    failed = attempt(rig[1], project, terminal_reason=secret)
    data = diagnostics.preview({'project_id': project['id'], 'attempt_ids': [failed['id']]})['diagnostics']
    assert secret not in encode(data)
    assert data['attempt_state_counts'] == {'failed': 1, 'unknown': 1}
    assert data['unknown_error_code_count'] == 1 and data['known_error_code_counts'] == {}
    assert dependency_summary({'versions': {'python': '3.13+private-name', 'dependencies': {'mlx': '/Users/private', 'new': '1.0'}}}) is None


@pytest.mark.parametrize('payload', [{'attempt_ids': [str(i) for i in range(21)]}, {'attempt_ids': ['a', 'a']}, {'attempt_ids': 'a'}, {'attempt_ids': [True]}, {'project_id': True}, {'include_logs': True}])
def test_invalid_preview_scope_is_rejected(rig, payload):
    with pytest.raises(Fault) as error:
        Diagnostics(rig[1]).preview(payload)
    assert error.value.code == 'DIAGNOSTICS_INVALID'


def test_selected_attempt_must_exist_and_belong_to_project(rig, tmp_path):
    diagnostics, project, _, _ = setup(rig, tmp_path)
    other = post(rig[0], '/projects', {'name': '其他项目'})
    foreign = attempt(rig[1], other)
    with pytest.raises(Fault) as error:
        diagnostics.preview({'project_id': project['id'], 'attempt_ids': [foreign['id']]})
    assert error.value.code == 'PROJECT_MISMATCH'
    with pytest.raises(Fault) as error:
        diagnostics.preview({'attempt_ids': ['missing']})
    assert error.value.code == 'RESOURCE_NOT_FOUND'


def test_export_freezes_preview_and_replay_does_not_rebuild_after_restart(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    value = attempt(rig[1], project)
    preview = diagnostics.preview({'project_id': project['id']})
    value.update(state='succeeded', output_text='LATER_PRIVATE_OUTPUT')
    with rig[1].store.transaction(): rig[1].store.put('attempt', value)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'succeeded'
    with zipfile.ZipFile(result['saved_path']) as archive:
        data = json.loads(archive.read('diagnostics.json'))
    assert data == preview['diagnostics'] and data['attempt_state_counts'] == {'failed': 1}
    reopened = Diagnostics(rig[1])
    monkeypatch.setattr(reopened, 'archive', lambda *args: pytest.fail('原 key 不得重建 ZIP'))
    assert export(reopened, preview, target) == result
    with pytest.raises(Fault) as error:
        reopened.export({'preview_id': preview['id'], 'target_dir': str(target), 'grant_id': 'changed'}, 'export-diagnostic')
    assert error.value.code == 'IDEMPOTENCY_CONFLICT'
    assert len(list(target.iterdir())) == 1


def test_concurrent_same_key_reads_writing_receipt_without_second_writer(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    entered, release = threading.Event(), threading.Event()
    original = diagnostics.archive
    count = 0
    def pause(record):
        nonlocal count
        count += 1; entered.set(); assert release.wait(5)
        return original(record)
    monkeypatch.setattr(diagnostics, 'archive', pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(export, diagnostics, preview, target)
        assert entered.wait(5)
        assert export(diagnostics, preview, target)['status'] == 'writing'
        with pytest.raises(Fault) as error: export(diagnostics, preview, target, 'different-key')
        assert error.value.code == 'DIAGNOSTICS_STATE_CONFLICT'
        release.set(); result = future.result(5)
    assert result['status'] == 'succeeded' and count == 1 and len(list(target.iterdir())) == 1


def test_replay_missing_published_file_never_recreates_or_claims_current_success(rig, tmp_path):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    result = export(diagnostics, preview, target)
    Path(result['saved_path']).unlink()
    with pytest.raises(Fault) as error: export(diagnostics, preview, target)
    assert error.value.code == 'DIAGNOSTICS_EXPORT_CHANGED' and not list(target.iterdir())


def test_target_grant_is_required_and_work_library_is_rejected(rig, tmp_path):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    rig[1].settings.export_roots = []
    with pytest.raises(Fault) as error: export(diagnostics, preview, target)
    assert error.value.code == 'PATH_NOT_ALLOWED' and not list(target.iterdir())
    grant = rig[1].delivery.export_grant(target)
    result = diagnostics.export({'preview_id': preview['id'], 'target_dir': str(target), 'grant_id': grant['grant_id']}, 'with-grant')
    assert result['status'] == 'succeeded'
    preview = diagnostics.preview({})
    grant = rig[1].delivery.export_grant(rig[1].root)
    with pytest.raises(Fault) as error:
        diagnostics.export({'preview_id': preview['id'], 'target_dir': str(rig[1].root), 'grant_id': grant['grant_id']}, 'bad-library')
    assert error.value.code == 'EXPORT_TARGET_INVALID'


def test_cancel_before_export_and_after_publication_have_distinct_results(rig, tmp_path):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    cancelled = diagnostics.cancel(preview['id'], 'cancel-once')
    assert cancelled['status'] == 'cancelled' and diagnostics.cancel(preview['id'], 'cancel-once') == cancelled
    with pytest.raises(Fault) as error: export(diagnostics, preview, target)
    assert error.value.code == 'DIAGNOSTICS_CANCELLED' and not list(target.iterdir())
    preview = diagnostics.preview({})
    result = export(diagnostics, preview, target)
    with pytest.raises(Fault) as error: diagnostics.cancel(preview['id'], 'too-late')
    assert error.value.code == 'DIAGNOSTICS_ALREADY_PUBLISHED' and Path(result['saved_path']).is_file()


def test_cancel_during_write_prevents_publication_and_removes_owned_temporary(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    entered, release = threading.Event(), threading.Event()
    original = diagnostics.verify
    calls = 0
    def pause(raw, record):
        nonlocal calls
        calls += 1
        original(raw, record)
        if calls == 2:
            entered.set(); assert release.wait(5)
    monkeypatch.setattr(diagnostics, 'verify', pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(export, diagnostics, preview, target)
        assert entered.wait(5)
        assert diagnostics.cancel(preview['id'], 'during-write')['status'] == 'cancelled'
        release.set(); result = future.result(5)
    assert result['status'] == 'cancelled' and not list(target.iterdir())
    assert export(diagnostics, preview, target)['status'] == 'cancelled'


@pytest.mark.parametrize('failure', ['disk', 'write', 'verify'])
def test_failures_never_publish_or_rebuild_same_command(rig, tmp_path, monkeypatch, failure):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    if failure == 'disk':
        monkeypatch.setattr(module.shutil, 'disk_usage', lambda _: type('Space', (), {'free': 0})())
    elif failure == 'write':
        def fail(_): raise OSError(errno.ENOSPC, 'PRIVATE_DISK_PATH')
        monkeypatch.setattr(module.os, 'fsync', fail)
    else:
        def fail(*_): raise Fault('DIAGNOSTICS_INCOMPLETE', 'PRIVATE_BAD_ZIP')
        monkeypatch.setattr(diagnostics, 'verify', fail)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'failed' and 'saved_path' not in result and not list(target.iterdir())
    assert 'PRIVATE' not in encode(result)
    monkeypatch.setattr(diagnostics, 'archive', lambda *_: pytest.fail('失败原 key 不得重建'))
    assert export(diagnostics, preview, target) == result


def test_publication_collision_never_overwrites_existing_file(rig, tmp_path):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    final = target / (preview['id'] + '.zip'); final.write_text('保留已有文件')
    result = export(diagnostics, preview, target)
    assert result['status'] == 'failed' and final.read_text() == '保留已有文件'
    assert list(target.iterdir()) == [final]


def test_existing_temporary_is_not_owned_or_removed(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    original = diagnostics.archive
    existing = []
    def occupy(record):
        path = target / ('.diagnostic-' + record['export_id'] + '.tmp')
        path.write_text('保留原文件'); existing.append(path)
        return original(record)
    monkeypatch.setattr(diagnostics, 'archive', occupy)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'failed' and len(existing) == 1
    assert existing[0].read_text() == '保留原文件' and list(target.iterdir()) == existing


def test_final_file_reverification_failure_never_reports_success(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    original, count = diagnostics.verify, 0
    def fail_final(raw, record):
        nonlocal count
        count += 1
        if count == 3: raise Fault('DIAGNOSTICS_INCOMPLETE', '发布后复核失败')
        original(raw, record)
    monkeypatch.setattr(diagnostics, 'verify', fail_final)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'registration_pending' and Path(result['saved_path']).is_file()
    assert result['can_cancel'] is False and not any(path.name.startswith('.diagnostic-') for path in target.iterdir())


def test_target_replacement_before_publish_is_rejected(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    original, count = diagnostics.verify, 0
    old = target.with_name('原目录')
    def replace(raw, record):
        nonlocal count
        count += 1; original(raw, record)
        if count == 2:
            target.rename(old); target.mkdir()
    monkeypatch.setattr(diagnostics, 'verify', replace)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'failed' and result['error']['code'] == 'DIAGNOSTICS_TARGET_CHANGED'
    assert not list(target.iterdir()) and not list(old.iterdir())


def test_unknown_preview_mutation_fails_hash_instead_of_exporting_extra_data(rig, tmp_path):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    record = diagnostics.record(preview['id']); record['diagnostics']['private_extra'] = 'DO_NOT_EXPORT'
    with rig[1].store.transaction(): diagnostics.put(record)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'failed' and not list(target.iterdir())


def test_publish_then_registration_failure_preserves_file_without_success_or_false_cancel(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    original = diagnostics.put
    def fail_success(record):
        if record['status'] == 'succeeded': raise RuntimeError('登记失败')
        original(record)
    monkeypatch.setattr(diagnostics, 'put', fail_success)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'registration_pending' and Path(result['saved_path']).is_file()
    assert export(diagnostics, preview, target)['status'] == 'registration_pending'
    with pytest.raises(Fault) as error: diagnostics.cancel(preview['id'], 'cannot-cancel-published')
    assert error.value.code == 'DIAGNOSTICS_ALREADY_PUBLISHED'


def test_cleanup_failure_after_publication_is_pending_and_does_not_claim_success(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    original = os.unlink
    def fail(name, *args, **kwargs):
        if str(name).startswith('.diagnostic-'): raise OSError(errno.EACCES, 'PRIVATE_CLEANUP_PATH')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(module.os, 'unlink', fail)
    result = export(diagnostics, preview, target)
    assert result['status'] == 'registration_pending' and result['error']['code'] == 'DIAGNOSTICS_CLEANUP_PENDING'
    assert Path(result['saved_path']).is_file() and 'PRIVATE_CLEANUP_PATH' not in encode(result)


def test_cancel_cannot_interleave_between_publish_rollback_and_pending_receipt(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    pending, release = threading.Event(), threading.Event()
    original = diagnostics.put
    def fail_then_pause(record):
        if record['status'] == 'succeeded': raise RuntimeError('发布后的登记失败')
        if record['status'] == 'registration_pending':
            pending.set(); assert release.wait(5)
        original(record)
    monkeypatch.setattr(diagnostics, 'put', fail_then_pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publishing = pool.submit(export, diagnostics, preview, target)
        assert pending.wait(5)
        cancelling = pool.submit(diagnostics.cancel, preview['id'], 'rollback-race-cancel')
        release.set()
        assert publishing.result(5)['status'] == 'registration_pending'
        with pytest.raises(Fault) as error: cancelling.result(5)
    assert error.value.code == 'DIAGNOSTICS_ALREADY_PUBLISHED'
    assert (target / (preview['id'] + '.zip')).is_file()


def test_restart_with_published_file_and_old_writing_record_cannot_fake_cancel(rig, tmp_path):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    result = export(diagnostics, preview, target)
    record = diagnostics.record(preview['id']); record['status'] = 'writing'
    with rig[1].store.transaction(): diagnostics.put(record)
    recovered = Diagnostics(rig[1]).cancel(preview['id'], 'after-interruption')
    assert recovered['status'] == 'registration_pending'
    assert Path(result['saved_path']).is_file() and recovered['can_cancel'] is False


def test_real_service_restart_preserves_same_export_receipt(rig, tmp_path, monkeypatch):
    diagnostics, project, _, target = setup(rig, tmp_path)
    preview = diagnostics.preview({'project_id': project['id']})
    result = export(diagnostics, preview, target)
    settings = rig[1].settings
    rig[1].close()
    reopened = Service(settings)
    try:
        resumed = Diagnostics(reopened)
        monkeypatch.setattr(resumed, 'archive', lambda *_: pytest.fail('服务重启后的原 key 不得重建'))
        assert export(resumed, preview, target) == result
    finally:
        reopened.close()


def test_http_preview_export_receipt_and_cancel_contract(rig, tmp_path):
    _, project, _, target = setup(rig, tmp_path)
    client = rig[0]
    preview = post(client, '/diagnostics/previews', {'project_id': project['id'], 'attempt_ids': []})
    assert client.get('/api/v1/diagnostics/previews/' + preview['id']).json() == preview
    payload = {'preview_id': preview['id'], 'target_dir': str(target)}
    missing_key = client.post('/api/v1/diagnostics/exports', json=payload)
    assert missing_key.status_code == 400 and not list(target.iterdir())
    result = post(client, '/diagnostics/exports', payload, 'http-diagnostics-export')
    assert result['status'] == 'succeeded' and post(client, '/diagnostics/exports', payload, 'http-diagnostics-export') == result
    cancelled = client.post('/api/v1/diagnostics/previews/' + preview['id'] + '/cancel', json={}, headers={'Idempotency-Key': 'http-too-late'})
    assert cancelled.status_code == 409 and cancelled.json()['error']['code'] == 'DIAGNOSTICS_ALREADY_PUBLISHED'
    with zipfile.ZipFile(result['saved_path']) as archive:
        assert archive.testzip() is None and len(archive.namelist()) == 2
