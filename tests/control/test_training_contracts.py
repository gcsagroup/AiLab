"""训练表单声明与实际执行器边界一致；此处不加载模型或验证 CUDA。"""

import copy
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

from test_control import rig, post

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ailab_control.api import Draft, NvidiaTrainingRuntime, TrainingRuntime
from ailab_control.remote.protocol import digest
from adapters.nvidia_text import adapter as nvidia
from workers.mlx_worker import snapshot_manifest, validate_snapshot as validate_mlx


def contracts(client):
    response = client.get('/api/v1/training-contracts')
    assert response.status_code == 200, response.text
    return {item['engine']: item for item in response.json()['items']}


def test_contract_read_is_authenticated_and_never_probes_or_mutates_tasks(rig, monkeypatch):
    client, service, *_ = rig
    def forbidden(*_, **__):
        pytest.fail('读取训练参数不能启动探测或连接远端')
    monkeypatch.setattr(service, 'environment', forbidden)
    monkeypatch.setattr(service.media, 'environment', forbidden)
    before = service.store.db.execute('SELECT count(*) FROM resources').fetchone()[0]
    declared = contracts(client)
    assert set(declared) == {'mlx', 'transformers'}
    assert declared['mlx']['execution_scope'] == 'local'
    assert declared['transformers']['execution_scope'] == 'remote'
    for item in declared.values():
        assert item['schema_version'] == 'ailab-training-contract-v1'
        assert item['parameters']['steps']['maximum'] == 200
        assert item['parameters']['batch_size']['default'] == 1
        assert item['parameters']['gradient_accumulation']['editable'] is False
        assert item['stopping']['effective_batch_size'] == 1
        assert item['verification'] == {'device_execution': 'requires_preflight', 'quality': 'not_implied'}
        assert item['application_policy']['saved_values'] == 'preserve_and_validate'
    assert client.get('/api/v1/training-contracts', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    declared['mlx']['parameters']['steps']['maximum'] = 999
    assert contracts(client)['mlx']['parameters']['steps']['maximum'] == 200
    assert service.store.db.execute('SELECT count(*) FROM resources').fetchone()[0] == before


def test_local_capability_uses_same_contract_without_claiming_device_readiness(rig, monkeypatch):
    client, service, *_ = rig
    monkeypatch.setattr(service, 'environment', lambda **_: {'ready': False, 'reason': '未准备'})
    monkeypatch.setattr(service.media, 'environment', lambda kind, **_: {'ready': False, 'reason': '未准备', 'engine': 'kokoro' if kind == 'audio' else 'diffusers', 'device_id': 'cpu' if kind == 'audio' else 'apple-gpu'})
    items = client.get('/api/v1/capabilities').json()['items']
    training = next(item for item in items if item['kind'] == 'text' and item['operation'] == 'train')
    assert training['supported'] is False
    assert training['training_contract'] == contracts(client)['mlx']


def mlx_snapshot(root, runtime):
    model = root / 'model'; model.mkdir()
    (model / 'config.json').write_text(json.dumps({'model_type': 'qwen2', 'hidden_size': 896, 'num_hidden_layers': 24}))
    (model / 'model.safetensors').write_bytes(b'contract-only-no-model-load')
    model_files, model_digest = snapshot_manifest(model)
    dataset = root / 'train.jsonl'
    dataset.write_text('{"messages":[{"role":"user","content":"问题"},{"role":"assistant","content":"回答"}]}\n')
    data_files, data_digest = snapshot_manifest(dataset)
    return {'operation': 'train', 'model_path': str(model), 'model_manifest': model_files, 'model_manifest_digest': model_digest,
            'dataset_path': str(dataset), 'dataset_manifest': data_files, 'dataset_manifest_digest': data_digest,
            'input': {}, 'runtime': runtime}


def nvidia_snapshot(runtime):
    pin = json.loads((ROOT / 'tests/nvidia/model-manifest.json').read_text())
    entry = {'path': 'data/train.jsonl', 'size': 3, 'sha256': 'c' * 64}
    return {'schema_version': 1, 'attempt_id': 'attempt-' + 'a' * 32, 'executor_id': 'executor-' + 'b' * 32,
            'adapter_id': 'nvidia-text', 'operation': 'train',
            'inputs': [{**item, 'path': 'model/' + item['path']} for item in pin['manifest']] + [entry],
            'input': {'model_manifest_digest': nvidia.MODEL_DIGEST, 'source_code_digest': nvidia.source_identity(),
                      'dataset_manifest_digest': digest([{**entry, 'path': 'train.jsonl'}])},
            'runtime': {key: value for key, value in runtime.items() if key in {
                'engine', 'device_id', 'precision', 'seed', 'steps', 'batch_size', 'learning_rate',
                'max_seq_length', 'lora_rank', 'lora_alpha', 'num_layers'}}}


@pytest.mark.parametrize('engine,model', [('mlx', TrainingRuntime), ('transformers', NvidiaTrainingRuntime)])
def test_advertised_defaults_and_numeric_edges_pass_actual_executor_validation(rig, tmp_path, engine, model):
    contract = contracts(rig[0])[engine]
    defaults = {name: field['default'] for name, field in contract['parameters'].items()}
    trials = [defaults]
    for name, field in contract['parameters'].items():
        if field['editable']:
            trials.extend({**defaults, name: field[edge]} for edge in ('minimum', 'maximum'))
    for index, values in enumerate(trials):
        runtime = model.model_validate(values).model_dump()
        if engine == 'mlx':
            root = tmp_path / str(index); root.mkdir()
            snapshot = mlx_snapshot(root, runtime)
            _, effective = validate_mlx(snapshot, root / 'output')
        else:
            snapshot = nvidia_snapshot(runtime)
            effective = nvidia.validate_snapshot(snapshot)
        assert all(effective[name] == value for name, value in values.items() if name in effective)


@pytest.mark.parametrize('changes', [
    {'learning_rate': 1e-7}, {'lora_alpha': 8.5}, {'lora_alpha': True},
    {'steps': 201}, {'batch_size': 2}, {'gradient_accumulation': 2},
])
@pytest.mark.parametrize('precision_present', [False, True])
def test_remote_training_rejects_unsupported_values_before_saving(rig, changes, precision_present):
    client, service, *_ = rig
    project = post(client, '/projects', {'name': '训练约束'})
    task = post(client, '/tasks', {'project_id': project['id'], 'name': '保留草稿', 'kind': 'text', 'operation': 'train'})
    draft = copy.deepcopy(task['draft'])
    draft['runtime'] = {**draft['runtime'], 'engine': 'transformers', 'device_id': 'cuda:0', **changes}
    if precision_present:
        draft['runtime']['precision'] = 'bfloat16'
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'draft': draft, 'expected_revision': task['draft_revision']})
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/tasks/{task['id']}").json()['draft'] == task['draft']
    assert service.store.db.execute("SELECT count(*) FROM resources WHERE kind='attempt'").fetchone()[0] == 0


def test_integral_alpha_from_old_remote_drafts_remains_usable_and_local_range_is_unchanged():
    value = Draft.model_validate({'kind': 'text', 'operation': 'train', 'input': {},
                                 'runtime': {'engine': 'transformers', 'device_id': 'cuda:0', 'lora_alpha': 8.0}})
    assert isinstance(value.runtime, NvidiaTrainingRuntime)
    assert type(value.runtime.lora_alpha) is int and value.runtime.lora_alpha == 8
    assert value.runtime.precision == 'bfloat16'
    local = TrainingRuntime.model_validate({'learning_rate': 1e-7, 'lora_alpha': 8.5, 'steps': 200})
    assert local.learning_rate == 1e-7 and local.lora_alpha == 8.5 and local.steps == 200
    with pytest.raises(ValidationError):
        TrainingRuntime.model_validate({'steps': 201})
