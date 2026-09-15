"""来源组数据的真实文件备份、恢复、导出和清理保护；不运行模型。"""

import json
from pathlib import Path
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

from test_control import post, rig
from dataset_split_fixtures import setup_split
from test_backup_restore import plan_restore
from test_cleanup import orphan
from test_delivery import prepare, export, trained_fixture
from ailab_control.api import create_app
from ailab_control.assets import file_hash
from ailab_control.backup import Backup, database, referenced_files
from ailab_control.cleanup import Cleanup
from ailab_control.dataset_splits import verify_ready_plan, verify_split_record
from ailab_control.delivery import portable_recipe
from ailab_control.service import Settings
from ailab_control.storage import Fault, digest, encode


def settled(service):
    for thread in list(service.threads):
        thread.join(timeout=3)
        assert not thread.is_alive()


def resource_bytes(service):
    resources = [(kind, json.loads(body)) for kind, body in service.store.db.execute('SELECT kind,body FROM resources')]
    return {relative: (service.root / relative).read_bytes() for relative in referenced_files(resources, service.root)}


@pytest.mark.parametrize('applied', [False, True])
def test_split_backup_restore_preserves_files_and_ready_plan_applies_without_rerun(rig, monkeypatch, tmp_path, applied):
    service = rig[1]
    values = setup_split(rig, monkeypatch, apply=applied)
    settled(service)
    plan_id = values['plan']['id']
    original_plan = service.store.get('dataset-split-plan', plan_id)
    original_rows = [tuple(row) for row in service.store.db.execute('SELECT id,body FROM resources ORDER BY id')]
    original_files = resource_bytes(service)
    if applied:
        assert original_plan['storage_path'] is None
        assert 'prepared' not in original_plan and 'staged_manifest' not in original_plan
        assert original_plan['stage_cleanup_status'] == 'completed'
        assert not (service.root / 'assets' / ('.split-' + plan_id)).exists()
        split = service.store.get('dataset-split', values['split']['id'])
        expected_ref = verify_split_record(split, lambda key: service.store.get('dataset', key))
    else:
        expected_ref = verify_ready_plan(original_plan, lambda key: service.store.get('dataset', key), lambda key: service.store.get('model', key))
    backup = Backup(service)
    package = backup.create()
    plan = plan_restore(rig, backup, package, tmp_path / '恢复的来源组库')
    result = backup.restore({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'restore-source-split')
    recovered_root = Path(result['restored_path'])
    app = create_app(Settings(recovered_root, 'restored-split-token', worker_python=Path(sys.executable)))
    recovered = app.state.service
    monkeypatch.setattr(recovered.dataset_splits, 'command', lambda *_: pytest.fail('恢复或应用不应重新启动 CPU 检查'))
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer restored-split-token'}) as client:
        restored_plan = recovered.store.get('dataset-split-plan', plan_id)
        assert restored_plan['status'] == ('applied' if applied else 'ready')
        assert recovered.store.list('attempt') == []
        for relative, expected in original_files.items():
            assert (recovered_root / relative).read_bytes() == expected
        if not applied:
            directory = Path(restored_plan['storage_path'])
            assert directory.is_relative_to(recovered_root)
            request = json.loads((directory / 'request.json').read_bytes())
            assert request['model_path'].startswith(str(service.root))
            assert restored_plan['preview'] == original_plan['preview']
        submitted = post(client, '/datasets/splits', {'plan_id': plan_id, 'plan_digest': original_plan['plan_digest']}, 'apply-restored-ready')
        assert submitted == post(client, '/datasets/splits', {'plan_id': plan_id, 'plan_digest': original_plan['plan_digest']}, 'apply-restored-ready')
        restored_split = recovered.store.get('dataset-split', submitted['split']['id'])
        assert verify_split_record(restored_split, lambda key: recovered.store.get('dataset', key)) == expected_ref
        assert len(recovered.store.list('dataset')) == 3
        assert recovered.store.list('attempt') == []
        assert recovered.store.get('dataset-split-plan', plan_id)['storage_path'] is None
        assert not (recovered.root / 'assets' / ('.split-' + plan_id)).exists()
        second = Backup(recovered).create()
        assert second['contains_asset_files'] is True
    assert [tuple(row) for row in service.store.db.execute('SELECT id,body FROM resources ORDER BY id')] == original_rows
    assert resource_bytes(service) == original_files


def test_applied_cleanup_failure_keeps_usable_split_and_backup_without_dangling_paths(rig, monkeypatch, tmp_path):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch, apply=False)
    settled(service)
    plan_id = values['plan']['id']
    payload = {'plan_id': plan_id, 'plan_digest': values['plan']['plan_digest']}
    stage = Path(service.store.get('dataset-split-plan', plan_id)['storage_path'])
    original_cleanup = service.dataset_splits.discard_stage
    def incomplete_cleanup(_record):
        raise OSError('仅测试本计划暂存清理未完成')
    monkeypatch.setattr(service.dataset_splits, 'discard_stage', incomplete_cleanup)
    result = post(client, '/datasets/splits', payload, 'apply-with-cleanup-fault')
    plan = service.store.get('dataset-split-plan', plan_id)
    assert plan['status'] == 'applied' and plan['stage_cleanup_status'] == 'pending'
    assert plan['storage_path'] is None and 'prepared' not in plan and 'staged_manifest' not in plan
    assert stage.is_dir() and len(service.store.list('dataset')) == 3
    manager = Backup(service)
    package = manager.create()
    manifest = json.loads((Path(package['backup_path']) / 'manifest.json').read_bytes())
    assert not any('/.split-' in entry['path'] for entry in manifest['files'])
    restore_plan = plan_restore(rig, manager, package, tmp_path / '恢复已应用待清理')
    restored = manager.restore({'plan_id': restore_plan['id'], 'plan_digest': restore_plan['plan_digest']}, 'restore-applied-cleanup-fault')
    app = create_app(Settings(Path(restored['restored_path']), 'cleanup-restored-token', worker_python=Path(sys.executable)))
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer cleanup-restored-token'}) as recovered_client:
        assert post(recovered_client, '/datasets/splits', payload, 'retry-restored-cleanup')['split']['id'] == result['split']['id']
        assert app.state.service.store.get('dataset-split-plan', plan_id)['stage_cleanup_status'] == 'completed'
    assert stage.is_dir(), '恢复库不能回头删除原库的暂存'
    monkeypatch.setattr(service.dataset_splits, 'discard_stage', original_cleanup)
    assert post(client, '/datasets/splits', payload, 'apply-with-cleanup-fault')['split']['id'] == result['split']['id']
    assert not stage.exists()
    assert service.store.get('dataset-split-plan', plan_id)['stage_cleanup_status'] == 'completed'
    assert len(service.store.list('dataset')) == 3 and len(service.store.list('dataset-split')) == 1


@pytest.mark.parametrize('damage', ['validation_file', 'validation_resource', 'wrong_role', 'wrong_plan_child', 'model_resource'])
def test_self_consistent_backup_cannot_omit_or_disconnect_split_evidence(rig, monkeypatch, tmp_path, damage):
    service = rig[1]
    values = setup_split(rig, monkeypatch)
    settled(service)
    manager = Backup(service)
    backup = manager.create()
    package = Path(backup['backup_path'])
    manifest = json.loads((package / 'manifest.json').read_bytes())
    if damage == 'validation_file':
        child = service.store.get('dataset', values['validation_dataset']['id'])
        relative = (Path(child['storage_path']) / child['entrypoint']).relative_to(service.root).as_posix()
        (package / relative).unlink()
        manifest['files'] = [entry for entry in manifest['files'] if entry['path'] != relative]
    else:
        with sqlite3.connect(package / 'control.sqlite3') as db:
            if damage in {'validation_resource', 'model_resource'}:
                identity = values['validation_dataset' if damage == 'validation_resource' else 'model']['id']
                db.execute('DELETE FROM resources WHERE id=?', (identity,))
            else:
                identity = values['validation_dataset']['id'] if damage == 'wrong_role' else values['plan']['id']
                body = json.loads(db.execute('SELECT body FROM resources WHERE id=?', (identity,)).fetchone()[0])
                if damage == 'wrong_role':
                    body['dataset_split_role'] = 'train'
                else:
                    body['train_dataset_id'] = values['validation_dataset']['id']
                db.execute('UPDATE resources SET body=? WHERE id=?', (encode(body), identity))
        entry = next(entry for entry in manifest['files'] if entry['path'] == 'control.sqlite3')
        entry.update(size=(package / 'control.sqlite3').stat().st_size, sha256=file_hash(package / 'control.sqlite3'))
    manifest['manifest_digest'] = digest({key: value for key, value in manifest.items() if key != 'manifest_digest'})
    (package / 'manifest.json').write_text(encode(manifest))
    with pytest.raises(Fault):
        plan_restore(rig, manager, backup, tmp_path / '拒绝不完整划分')


@pytest.mark.parametrize('damage', ['marker_only', 'source_version', 'plan_digest', 'intent', 'preview'])
def test_backup_refuses_ready_plan_with_changed_semantics(rig, monkeypatch, damage):
    service = rig[1]
    values = setup_split(rig, monkeypatch, apply=False)
    settled(service)
    plan = service.store.get('dataset-split-plan', values['plan']['id'])
    if damage == 'marker_only':
        marker = Path(plan['storage_path']) / 'only-marker.txt'
        marker.write_text('不能把单个文件声明成完整计划')
        plan['staged_manifest'] = [{'path': marker.name, 'size': marker.stat().st_size, 'sha256': file_hash(marker)}]
    elif damage == 'source_version':
        plan['source_version_id'] = 'version-' + 'e' * 32
    elif damage == 'plan_digest':
        plan['plan_digest'] = 'e' * 64
    elif damage == 'intent':
        plan['apply_intent']['train_dataset_id'] = 'dataset-' + 'e' * 32
    else:
        plan['preview']['new_bytes'] += 1
    with service.store.transaction():
        service.store.put('dataset-split-plan', plan)
    with pytest.raises(Fault):
        Backup(service).create()


@pytest.mark.parametrize('status', ['preparing', 'cancelling', 'recovery_required'])
def test_backup_refuses_unconfirmed_split_activity(rig, monkeypatch, status):
    service = rig[1]
    values = setup_split(rig, monkeypatch, apply=False)
    settled(service)
    plan = service.store.get('dataset-split-plan', values['plan']['id'])
    plan['status'] = status
    with service.store.transaction():
        service.store.put('dataset-split-plan', plan)
    with pytest.raises(Fault) as rejected:
        Backup(service).create()
    assert rejected.value.code == 'BACKUP_BUSY'
    with pytest.raises(Fault) as cleanup_rejected:
        Cleanup(service).plan({})
    assert cleanup_rejected.value.code == 'CLEANUP_BUSY'


@pytest.mark.parametrize('field', ['dataset_id', 'dataset_version_id', 'dataset_manifest_digest', 'model_manifest_digest',
                                  'tokenization_recipe_digest', 'runtime', 'dataset_manifest', 'project_id'])
def test_backup_rejects_valid_split_ref_attached_to_different_training_identity(rig, monkeypatch, field):
    client, service, *_ = rig
    values = setup_split(rig, monkeypatch)
    settled(service)
    split = service.store.get('dataset-split', values['split']['id'])
    ref = verify_split_record(split, lambda key: service.store.get('dataset', key))
    dataset = service.store.get('dataset', split['train_dataset_id'])
    snapshot = {'dataset_id': dataset['id'], 'dataset_version_id': dataset['version_id'], 'dataset_manifest': dataset['manifest'],
                'dataset_manifest_digest': dataset['manifest_digest'], 'model_manifest_digest': split['model_manifest_digest'],
                'tokenization_recipe_digest': split['tokenization_recipe_digest'], 'runtime': {'max_seq_length': split['max_seq_length']},
                'dataset_split_ref': ref}
    attempt = service.resource('attempt', values['project']['id'], state='succeeded', snapshot=snapshot, snapshot_digest=digest(snapshot))
    with service.store.transaction():
        service.store.put('attempt', attempt)
    Backup(service).create('valid-split-snapshot')
    if field == 'project_id':
        attempt['project_id'] = post(client, '/projects', {'name': '另一个项目'})['id']
    elif field == 'dataset_id':
        snapshot[field] = split['source_dataset_id']
    elif field == 'dataset_version_id':
        snapshot[field] = split['validation_version_id']
    elif field == 'runtime':
        snapshot[field] = {'max_seq_length': split['max_seq_length'] + 1}
    elif field == 'dataset_manifest':
        snapshot[field] = []
    else:
        snapshot[field] = 'b' * 64
    attempt['snapshot_digest'] = digest(snapshot)
    with service.store.transaction():
        service.store.put('attempt', attempt)
    with pytest.raises(Fault) as rejected:
        Backup(service).create('mismatched-split-snapshot')
    assert rejected.value.code == 'BACKUP_REFERENCE_MISSING'


def test_split_export_has_complete_data_and_proof_with_explicit_disclosure(rig, monkeypatch, tmp_path):
    service = rig[1]
    values = setup_split(rig, monkeypatch)
    settled(service)
    split = service.store.get('dataset-split', values['split']['id'])
    plan = prepare(rig, 'dataset-split', split['id'], values['project']['id'], tmp_path / '划分数据包')
    assert len(plan['disclosures']) == 1 and '来源标识' in plan['disclosures'][0]
    assert plan['file_count'] == 7
    assert plan['dependencies'][0]['included'] is False and plan['dependencies'][0]['type'] == 'tokenizer_model'
    record, _ = export(rig, plan, 'export-complete-source-split')
    assert record['state'] == 'succeeded', record
    root = Path(record['verified_path'])
    manifest = json.loads((root / 'manifest.json').read_bytes())
    for entry in manifest['files']:
        path = root / entry['path']
        assert path.stat().st_size == entry['size'] and file_hash(path) == entry['sha256']
    for role in ('source', 'train', 'validation'):
        dataset = service.store.get('dataset', split[role + '_dataset_id'])
        for entry in dataset['manifest']:
            assert (root / 'data' / role / entry['path']).read_bytes() == (Path(dataset['storage_path']) / entry['path']).read_bytes()
    for entry in split['manifest']:
        assert (root / 'evidence' / entry['path']).read_bytes() == (Path(split['storage_path']) / entry['path']).read_bytes()
    metadata = json.loads((root / 'object.json').read_bytes())
    assert metadata['source_identifiers_included'] is True
    assert metadata['validation_loss'] == 'not_run' and metadata['semantic_near_duplicates'] == 'not_checked'
    reference = verify_split_record(split, lambda key: service.store.get('dataset', key))
    assert metadata['dataset_split_ref'] == reference
    assert str(service.root) not in (root / 'object.json').read_text()
    assert portable_recipe({'dataset_split_ref': reference, 'dataset_path': '/private/source'})['dataset_split_ref'] == reference
    with pytest.raises(Fault):
        portable_recipe({'dataset_split_ref': {**reference, 'private_token': 'never-export'}})


@pytest.mark.parametrize('object_type', ['report', 'adapter'])
def test_training_exports_keep_split_identity_as_explicit_external_dependency(rig, tmp_path, object_type):
    client, service, *_ = rig
    project, _, attempt = trained_fixture(rig)
    reference = attempt['snapshot']['dataset_split_ref']
    if object_type == 'adapter':
        object_id = post(client, f"/attempts/{attempt['id']}/adapters", {}, 'save-split-adapter')['id']
    else:
        object_id = attempt['id']
    plan = prepare(rig, object_type, object_id, project['id'], tmp_path / ('携带关系的' + object_type))
    dependency, = [entry for entry in plan['dependencies'] if entry['type'] == 'dataset_split']
    assert dependency['included'] is False and dependency['id'] == reference['id'] and dependency['split_digest'] == reference['split_digest']
    exported, _ = export(rig, plan, 'export-split-dependency')
    assert exported['state'] == 'succeeded'
    root = Path(exported['verified_path'])
    metadata = json.loads((root / ('object.json' if object_type == 'adapter' else 'recipe.json')).read_bytes())
    assert metadata['dataset_split_ref'] == reference
    assert not (root / 'data').exists() and not (root / 'evidence').exists()


@pytest.mark.parametrize('status', ['blocked', 'failed', 'cancelled'])
def test_unapplied_problem_and_cancelled_plans_restore_without_automatic_execution(rig, monkeypatch, tmp_path, status):
    client, service, *_ = rig
    row = lambda group: {'source_id': group, 'messages': [{'role': 'user', 'content': '相同问题'}, {'role': 'assistant', 'content': '原回答'}]}
    values = setup_split(rig, monkeypatch, apply=False, mode='bad-json' if status == 'failed' else 'success',
                         rows=[row('一组'), row('二组')] if status == 'blocked' else None)
    plan_id = values['plan']['id']
    if status == 'cancelled':
        post(client, '/datasets/split-plans/' + plan_id + '/cancel', {}, 'cancel-before-backup')
    settled(service)
    original_plan = service.store.get('dataset-split-plan', plan_id)
    assert original_plan['status'] == status
    before = resource_bytes(service)
    backup = Backup(service)
    package = backup.create()
    plan = plan_restore(rig, backup, package, tmp_path / ('恢复' + status))
    result = backup.restore({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'restore-' + status)
    app = create_app(Settings(Path(result['restored_path']), 'inactive-split-token', worker_python=Path(sys.executable)))
    recovered = app.state.service
    try:
        restored = recovered.store.get('dataset-split-plan', plan_id)
        assert restored['status'] == status
        assert len(recovered.store.list('dataset')) == 1
        assert recovered.store.list('dataset-split') == [] and recovered.store.list('attempt') == []
        assert recovered.threads == set() and recovered.dataset_splits.processes == {}
        assert resource_bytes(recovered) == before
    finally:
        recovered.close()


@pytest.mark.parametrize('applied', [False, True])
def test_cleanup_keeps_referenced_split_assets_and_only_moves_unreferenced_fixture(rig, monkeypatch, applied):
    service = rig[1]
    setup_split(rig, monkeypatch, apply=applied)
    settled(service)
    before = resource_bytes(service)
    extra = orphan(service, name='来源组以外的测试孤立文件')
    cleanup = Cleanup(service)
    plan = cleanup.plan({})
    assert [item['source_path'] for item in plan['items']] == [str(extra)]
    result = cleanup.execute({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'move-only-fixture')
    assert result['state'] == 'trashed'
    assert resource_bytes(service) == before
    assert cleanup.restore(result['id'], {}, 'restore-only-fixture')['state'] == 'restored'
    assert extra.is_dir()


@pytest.mark.parametrize('kind', ['dataset-split', 'dataset-split-plan'])
def test_old_schema_cannot_claim_new_split_semantics(rig, tmp_path, kind):
    service = rig[1]
    project = post(rig[0], '/projects', {'name': '版本拒绝测试'})
    with service.store.transaction():
        resource = service.resource(kind, project['id'], status='ready')
        service.store.put(kind, resource)
    frozen = tmp_path / '声明旧版本.sqlite3'
    with sqlite3.connect(frozen) as target:
        service.store.db.backup(target)
        target.execute('PRAGMA journal_mode=DELETE')
        target.execute('UPDATE schema_version SET version=3')
    with pytest.raises(Fault, match='来源组划分资源需要资料库 v4'):
        database(frozen)


@pytest.mark.parametrize('reference', [None, {}, {'id': 'dataset-split-' + 'a' * 32}])
@pytest.mark.parametrize('kind', ['task', 'attempt'])
def test_backup_rejects_orphan_split_snapshot_reference(tmp_path, kind, reference):
    resource = {'id': kind + '-' + 'b' * 32, 'project_id': 'project-' + 'c' * 32,
                'draft' if kind == 'task' else 'snapshot': {'dataset_split_ref': reference}}
    with pytest.raises(Fault) as rejected:
        referenced_files([(kind, resource)], tmp_path)
    assert rejected.value.code == 'BACKUP_REFERENCE_MISSING'


@pytest.mark.parametrize('declaration', [{'dataset_split_id': None}, {'dataset_split_role': ''},
                                       {'dataset_split_id': 'dataset-split-' + 'a' * 32, 'dataset_split_role': 'train'}])
def test_backup_rejects_unpaired_derived_declarations(tmp_path, declaration):
    resource = {'id': 'dataset-' + 'a' * 32, **declaration}
    with pytest.raises(Fault) as rejected:
        referenced_files([('dataset', resource)], tmp_path)
    assert rejected.value.code == 'BACKUP_REFERENCE_MISSING'
