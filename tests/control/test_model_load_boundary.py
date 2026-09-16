"""导入 API 公开实际加载边界；只用临时元信息，不运行模型或子进程。"""

import hashlib
import json
import subprocess

import pytest

from test_control import rig, make_model, post
from ailab_control.storage import digest


EXPECTED_BOUNDARY = {
    'scope_semantics': 'loader_policy_not_os_permissions',
    'process': 'separate_process',
    'os_sandbox': False,
    'filesystem': 'current_user_permissions',
    'network': 'offline_loader_options_not_os_block',
    'credentials': 'environment_allowlist_not_filesystem_denial',
    'custom_code': 'not_supported',
}


@pytest.fixture(autouse=True)
def forbid_runtime(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('加载边界元信息测试禁止子进程或模型执行')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)


def check_plan_and_import(client, project, source, loader, trust):
    plan = post(client, '/models/import-plans', {'project_id': project['id'], 'path': str(source)})
    assert plan['execution_boundary'] == EXPECTED_BOUNDARY
    assert plan['execution_scope'] == {'network': False, 'custom_code': False, 'credentials': False}
    assert (plan['loader'], plan['trust_class']) == (loader, trust)
    model = post(client, '/models/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']}, 'boundary-model')
    assert model['execution_boundary'] == plan['execution_boundary']
    assert model['load_policy_ref'] == plan['id']
    response = client.get('/api/v1/models', params={'project_id': project['id']})
    assert response.status_code == 200
    listed = response.json()['items']
    assert len(listed) == 1 and listed[0]['id'] == model['id']
    assert listed[0]['execution_boundary'] == EXPECTED_BOUNDARY
    return plan, model


def test_text_model_api_reports_policy_not_os_sandbox(rig):
    client, service, source, _ = rig
    project = post(client, '/projects', {'name': 'M2加载边界元信息夹具'})
    check_plan_and_import(client, project, make_model(source / '非真实模型'), 'mlx_lm.local_restricted', 'restricted_weights')
    assert not service.store.list('attempt')


def test_existing_import_plan_gets_current_verified_boundary(rig):
    client, service, source, _ = rig
    project = post(client, '/projects', {'name': '旧计划兼容夹具'})
    path = make_model(source / '旧计划模型')
    plan = post(client, '/models/import-plans', {'project_id': project['id'], 'path': str(path)})
    # 模拟升级前已落盘的有效计划；新字段来自导入时重新检查的源文件。
    with service.store.transaction():
        stored = service.store.get('import-plan', plan['id'])
        stored.pop('execution_boundary')
        service.store.put('import-plan', stored)
    model = post(client, '/models/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']}, 'legacy-plan')
    assert model['execution_boundary'] == EXPECTED_BOUNDARY
    assert model['load_policy_ref'] == plan['id']
    assert not service.store.list('attempt')


@pytest.mark.parametrize('engine,trust,loader', [
    ('kokoro', 'restricted_official_torch', 'kokoro.fixed_official_weights_only_cpu'),
    ('diffusers', 'restricted_weights', 'diffusers.fixed_local_safetensors'),
])
def test_fixed_media_model_api_reports_same_permission_boundary(rig, monkeypatch, engine, trust, loader):
    from ailab_control import media_assets
    client, service, source, _ = rig
    project = post(client, '/projects', {'name': 'M2媒体边界元信息夹具'})
    model = make_model(source / '仅结构夹具')
    (model / 'manifest.json').write_text(json.dumps({'repo': 'fixture/boundary-only'}))
    if engine == 'kokoro':
        (model / 'weights.pth').write_bytes(b'fixture-only; never deserialize')
    files = [{'path': p.name, 'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(model.iterdir())]
    monkeypatch.setattr(media_assets, 'CARDS', [{'repo': 'fixture/boundary-only', 'revision': 'fixed-fixture',
        'family': 'kokoro-82m' if engine == 'kokoro' else 'sdxl-fixture', 'format': 'torch-restricted-official' if engine == 'kokoro' else 'safetensors',
        'files': files, 'modality': 'audio' if engine == 'kokoro' else 'image', 'default_engine': engine,
        'license': '仅测试元信息', 'metadata_manifest_digest': digest(files)}])
    check_plan_and_import(client, project, model, loader, trust)
    assert not service.store.list('attempt')


@pytest.mark.parametrize('mutation', ['python', 'torchscript', 'custom_code'])
def test_boundary_metadata_does_not_authorize_unsupported_model_code(rig, mutation):
    client, service, source, _ = rig
    project = post(client, '/projects', {'name': '不开放执行代码'})
    model = make_model(source / '拒绝模型')
    if mutation == 'custom_code':
        (model / 'tokenizer_config.json').write_text(json.dumps({'auto_map': {'AutoTokenizer': 'modeling.Unknown'}}))
    else:
        (model / ('modeling.py' if mutation == 'python' else 'model.pt')).write_bytes(b'inert fixture')
    response = client.post('/api/v1/models/import-plans', json={'project_id': project['id'], 'path': str(model)})
    assert response.status_code == 400
    assert response.json()['error']['code'] == 'MODEL_LOAD_TRUST_REQUIRED'
    assert not service.store.list('model') and not service.store.list('import-plan') and not service.store.list('attempt')


def test_worker_environment_omits_credentials_without_claiming_filesystem_denial(rig, monkeypatch, tmp_path):
    service = rig[1]
    sensitive = {'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN', 'OPENAI_API_KEY', 'AWS_SECRET_ACCESS_KEY',
                 'AILAB_HOST_TOKEN', 'AILAB_CONTROL_TOKEN', 'HTTPS_PROXY', 'PYTHONPATH', 'DYLD_INSERT_LIBRARIES'}
    for name in sensitive:
        monkeypatch.setenv(name, 'synthetic-boundary-test-only')
    monkeypatch.setenv('HOME', str(tmp_path / 'synthetic-home'))
    actual = service.worker_environment()
    assert not sensitive.intersection(actual)
    assert actual['HOME'] == str(tmp_path / 'synthetic-home')
    assert actual['HF_HUB_OFFLINE'] == actual['TRANSFORMERS_OFFLINE'] == actual['HF_DATASETS_OFFLINE'] == '1'
    assert set(actual) <= {'HOME', 'PATH', 'TMPDIR', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'HF_HUB_OFFLINE',
                           'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE', 'TOKENIZERS_PARALLELISM', 'PYTHONUNBUFFERED', 'AILAB_CONTROL_PID'}
