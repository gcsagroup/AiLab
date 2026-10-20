"""合并、蒸馏与格式任务的来源、参数、幂等和隔离合同。"""
import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest
from test_control import rig, post, setup_task
from test_delivery import trained_fixture
from dataset_split_fixtures import setup_split
from ailab_control.storage import Fault, digest
from ailab_control.assets import file_hash, model_manifest, verify_manifest
from ailab_control.delivery import portable_recipe


def adapter_fixture(rig):
    project, model, attempt = trained_fixture(rig)
    adapter = post(rig[0], f"/attempts/{attempt['id']}/adapters", {}, 'save-source')
    return project, model, adapter


def test_merge_binds_exact_base_and_creates_only_draft(rig):
    client, service, *_ = rig
    project, model, adapter = adapter_fixture(rig)
    body = {'project_id': project['id'], 'model_id': model['id'], 'operation': 'merge', 'adapter_id': adapter['id'], 'merge_weight': 0.75}
    before = len(service.store.list('attempt'))
    task = post(client, '/model-lab/tasks', body, 'merge-once')
    assert post(client, '/model-lab/tasks', body, 'merge-once') == task
    assert task['immutable_draft'] and task['draft']['runtime']['merge_weight'] == 0.75
    assert len(service.store.list('attempt')) == before
    broken = service.store.get('adapter', adapter['id']); broken['base_model_version_id'] = 'wrong'
    with service.store.transaction(): service.store.put('adapter', broken)
    response = client.post('/api/v1/model-lab/tasks', json=body)
    assert response.status_code == 409 and response.json()['error']['code'] == 'ADAPTER_BASE_MISMATCH'


@pytest.mark.parametrize('value', [True, 0, -1, 1.01, '0.75'])
def test_merge_weight_rejects_invalid_values(rig, value):
    response = rig[0].post('/api/v1/model-lab/tasks', json={'project_id': 'p', 'model_id': 'm', 'operation': 'merge', 'adapter_id': 'a', 'merge_weight': value})
    assert response.status_code == 422


def test_distill_requires_training_split_and_preserves_teacher_identity(rig, monkeypatch):
    client, service, *_ = rig
    split = setup_split(rig, monkeypatch)
    body = {'project_id': split['project']['id'], 'model_id': split['model']['id'], 'teacher_model_id': split['model']['id'], 'operation': 'distill', 'dataset_id': split['validation_dataset']['id']}
    task = post(client, '/model-lab/tasks', body, 'validation-is-not-training')
    checked = post(client, f"/tasks/{task['id']}/preflight", {'draft_revision': task['draft_revision']})
    assert not checked['can_submit'] and any(item['code'] == 'DATASET_SPLIT_VALIDATION_NOT_TRAINABLE' for item in checked['blocking'])
    body['dataset_id'] = split['train_dataset']['id']
    task = post(client, '/model-lab/tasks', body, 'distill-training')
    fields = service.model_lab.fields(task)
    assert fields['teacher']['manifest_digest'] == split['model']['manifest_digest']
    foreign = post(client, '/projects', {'name': '其他项目'})
    response = client.post('/api/v1/model-lab/tasks', json={**body, 'project_id': foreign['id']})
    assert response.status_code == 403
    recipe = portable_recipe({'operation': 'distill', **fields})
    assert recipe['teacher']['manifest_digest'] == fields['teacher']['manifest_digest'] and 'path' not in recipe['teacher']


@pytest.mark.parametrize('target', ['coreml', 'onnx', 'torchscript'])
def test_format_creation_is_immutable_and_never_launches_automatically(rig, target):
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    task = post(client, '/format-conversions', {'project_id': project['id'], 'model_id': model['id'], 'target_format': target}, target)
    assert task['operation'] == 'convert' and task['immutable_draft']
    assert task['draft']['runtime'] == {'engine': target, 'device_id': 'cpu', 'seed': 0}
    assert not service.store.list('attempt')
    denied = client.post('/api/v1/formatted-model-trials', json={'project_id': project['id'], 'model_id': model['id'], 'prompt': '正常模型不能伪装为转换文件', 'max_tokens': 16})
    assert denied.status_code == 409


def test_untrusted_converted_model_cannot_be_loaded(rig):
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    stored = service.store.get('model', model['id']); stored.update(format='torchscript', default_engine='torchscript', lab_operation='convert', source_attempt_id='missing')
    with service.store.transaction(): service.store.put('model', stored)
    denied = client.post('/api/v1/formatted-model-trials', json={'project_id': project['id'], 'model_id': model['id'], 'prompt': '你好', 'max_tokens': 16})
    assert denied.status_code == 404
    normal = post(client, '/tasks', {'project_id': project['id'], 'name': '错误引擎', 'kind': 'text', 'operation': 'generate'})
    draft = normal['draft']; draft['model_id'] = model['id']; draft['input']['prompt'] = '你好'
    normal = client.patch(f"/api/v1/tasks/{normal['id']}/draft", json={'expected_revision': 1, 'draft': draft}).json()
    checked = post(client, f"/tasks/{normal['id']}/preflight", {'draft_revision': normal['draft_revision']})
    assert not checked['can_submit'] and any(item['code'] == 'CONVERTED_ENGINE_MISMATCH' for item in checked['blocking'])


def lab_output_fixture(rig, operation):
    """小文件构造封存收集记录，仅检验来源防篡改，不代替实际运算。"""
    service = rig[1]
    project, model, _ = setup_task(rig)
    base = service.store.get('model', model['id'])
    snapshot = {'operation': operation, 'model_id': base['id'], 'model_version_id': base['version_id'], 'model_manifest_digest': base['manifest_digest'], 'runtime': {'engine': 'mlx'}}
    attempt = service.resource('attempt', project['id'], state='succeeded', compute_outcome='succeeded', collection_state='succeeded', snapshot=snapshot, snapshot_digest=digest(snapshot))
    output = service.root / 'runs' / attempt['id'] / 'output'
    shutil.copytree(base['storage_path'], output / 'model')
    inspected = model_manifest(output / 'model')
    effective = {'model_manifest_sha256': 'a' * 64, 'model_output_manifest_digest': inspected['manifest_digest'], 'independent_use': 'verified'}
    report = {'operation': operation, 'source_model_manifest_digest': base['manifest_digest'], 'source_model_manifest_sha256': effective['model_manifest_sha256'], 'output_model_manifest': inspected['manifest'], 'output_model_manifest_digest': inspected['manifest_digest'], 'verification': {'passed': True}}
    (output / 'conversion.json').write_text(json.dumps(report))
    attempt['effective_config'] = effective
    sealed = {'complete': True, 'effective_config': copy.deepcopy(effective), 'artifacts': [{'path': p.relative_to(output).as_posix(), 'sha256': file_hash(p), 'media_type': 'application/octet-stream'} for p in sorted(output.rglob('*')) if p.is_file()]}
    attempt['output_manifest_ref'] = {**sealed, 'digest': digest(sealed)}
    with service.store.transaction():
        service.store.put('attempt', attempt)
        for entry in sealed['artifacts']:
            path = output / entry['path']
            artifact = service.resource('artifact', project['id'], attempt_id=attempt['id'], storage_path=str(path), name=path.name, size=path.stat().st_size, sha256=entry['sha256'])
            artifact['id'] = 'artifact-' + digest({'attempt_id': attempt['id'], 'manifest': attempt['output_manifest_ref']['digest'], 'path': entry['path']})[:32]
            service.store.put('artifact', artifact)
    return base, attempt, output


@pytest.mark.parametrize('operation', ['merge', 'distill'])
def test_lab_save_is_independent_idempotent_and_keeps_quality_unrated(rig, operation):
    service = rig[1]
    base, attempt, _ = lab_output_fixture(rig, operation)
    saved = service.model_lab.save_model(attempt['id'], {}, 'once')
    assert saved['id'] != base['id'] and saved['lab_operation'] == operation
    assert saved['quality_status'] == 'not_evaluated' and saved['default_engine'] == 'mlx'
    assert service.model_lab.save_model(attempt['id'], {}, 'once') == saved
    verify_manifest(Path(base['storage_path']), base['manifest'])


@pytest.mark.parametrize('change', ['snapshot', 'collection', 'report', 'weights', 'effective', 'extra'])
def test_lab_save_rejects_changed_collection_and_files(rig, change):
    service = rig[1]
    _, attempt, output = lab_output_fixture(rig, 'merge')
    if change in {'snapshot', 'collection', 'effective'}:
        if change == 'snapshot': attempt['snapshot']['model_version_id'] = 'changed'
        elif change == 'collection': attempt['collection_state'] = 'failed'
        else: attempt['effective_config']['independent_use'] = 'not_verified'
        with service.store.transaction(): service.store.put('attempt', attempt)
    elif change == 'report':
        (output / 'conversion.json').write_text('{}')
    elif change == 'extra':
        (output / 'model/extra.txt').write_text('未收集的文件')
    else:
        path = output / 'model/model.safetensors'; path.chmod(0o600)
        content = path.read_bytes(); path.write_bytes(content[:-4] + b'\0\0\0\0')
    with pytest.raises(Fault):
        service.model_lab.save_model(attempt['id'], {}, 'reject')
    assert len(service.store.list('model')) == 1


def test_restored_distillation_rebinds_teacher_without_rewriting_messages():
    from ailab_control.backup import remap_reference_paths
    snapshot = {'teacher': {'path': '/old/assets/teacher', 'manifest_digest': 'fixed'}, 'input': {'prompt': '/old/assets/teacher'}, 'dataset_path': '/old/assets/data.jsonl'}
    restored = remap_reference_paths(snapshot, Path('/old'), Path('/new'))
    assert restored['teacher'] == {'path': '/new/assets/teacher', 'manifest_digest': 'fixed'}
    assert restored['dataset_path'] == '/new/assets/data.jsonl'
    assert restored['input'] == snapshot['input']


@pytest.mark.parametrize('changed', [False, True])
def test_backup_checks_distillation_source_recipe_separately(rig, monkeypatch, changed):
    from ailab_control.backup import referenced_files
    client, service, *_ = rig
    split = setup_split(rig, monkeypatch)
    task = post(client, '/model-lab/tasks', {'project_id': split['project']['id'], 'model_id': split['model']['id'], 'teacher_model_id': split['model']['id'], 'operation': 'distill', 'dataset_id': split['train_dataset']['id']})
    dataset = service.store.get('dataset', split['train_dataset']['id'])
    model = service.store.get('model', split['model']['id'])
    fields = service.dataset_splits.training_fields(task, dataset, model)
    recipe = {'recipe_id': 'qwen25-offline-distillation-v1', 'source_dataset_tokenization_recipe_digest': 'f' * 64 if changed else fields['dataset_split_ref']['tokenization_recipe_digest']}
    snapshot = {**task['draft'], **fields, 'tokenization_recipe': recipe, 'tokenization_recipe_digest': hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()}
    attempt = service.resource('attempt', task['project_id'], state='succeeded', snapshot=snapshot, snapshot_digest=digest(snapshot))
    with service.store.transaction(): service.store.put('attempt', attempt)
    rows = service.store.db.execute('SELECT kind,body FROM resources').fetchall()
    resources = [(kind, json.loads(body)) for kind, body in rows]
    if changed:
        with pytest.raises(Fault) as error: referenced_files(resources, service.root)
        assert error.value.code == 'BACKUP_REFERENCE_MISSING'
    else:
        assert referenced_files(resources, service.root)
