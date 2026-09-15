"""完成接收的合同正反例；返回字段均为夹具，不执行模型或模拟硬件验收。"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from test_adapter import adapter, frozen_snapshot
from ailab_control.remote.protocol import ProtocolError, file_hash


def completion_fixture(tmp_path):
    snapshot = frozen_snapshot()
    effective = adapter.validate_snapshot(snapshot)
    root = Path(adapter.__file__).resolve().parents[2]
    recipe = {'recipe_id': 'qwen25-generation-v1', 'tokenizer_files': {item['path'].removeprefix('model/'): item['sha256'] for item in snapshot['inputs'] if Path(item['path']).name in {'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt'}},
              'template_sha256': adapter.TEMPLATE_SHA256, 'max_seq_length': None, 'packing': False, 'supervision': None,
              'recipe_implementation_sha256': file_hash(root / 'adapters/mlx_text/recipe.py')}
    effective.update(model_manifest_digest=adapter.MODEL_DIGEST, source_code_digest=adapter.source_identity(), tokenization_recipe=recipe,
                     tokenization_recipe_digest=hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest(), input_unchanged=True)
    reports = {'effective-config.json': effective, 'environment.json': {'ready': True, 'source_code_digest': adapter.source_identity(), 'platform': 'linux', 'cuda_runtime': '12.8'},
               'input-check.json': {'fixture_only': True}, 'metrics.json': {'compute_device': 'cuda:0', 'fixture_only': True}}
    for name, value in reports.items():
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / 'result.txt').write_text('完成合同夹具，不是模型输出。')
    files = [{'name': path.name, 'size': path.stat().st_size, 'sha256': file_hash(path), 'media_type': 'text/plain' if path.suffix == '.txt' else 'application/json'} for path in tmp_path.iterdir()]
    return snapshot, effective, files


@pytest.mark.parametrize("transport", [None, "loopback_http", "https"])
def test_complete_fixed_contract_and_matching_files_are_accepted(tmp_path, transport):
    snapshot, effective, files = completion_fixture(tmp_path)
    if transport is not None:
        snapshot["transport"] = transport
    assert adapter.validate_completion(snapshot, effective, files)
    assert adapter.validate_completion(snapshot, effective, files, tmp_path)


@pytest.mark.parametrize('mutation', ['engine', 'device_id', 'precision', 'model', 'recipe', 'missing_result', 'missing_metrics', 'missing_environment', 'wrong_config_file', 'wrong_metrics_device', 'bool_in_config'])
def test_wrong_actual_runtime_identity_and_incomplete_outputs_are_rejected(tmp_path, mutation):
    snapshot, effective, files = completion_fixture(tmp_path)
    if mutation == 'engine': effective['engine'] = 'mlx'
    if mutation == 'device_id': effective['device_id'] = 'cpu'
    if mutation == 'precision': effective['precision'] = 'float32'
    if mutation == 'model': effective['model_manifest_digest'] = 'f' * 64
    if mutation == 'recipe': effective['tokenization_recipe_digest'] = 'f' * 64
    if mutation.startswith('missing_'):
        name = {'missing_result': 'result.txt', 'missing_metrics': 'metrics.json', 'missing_environment': 'environment.json'}[mutation]
        files = [item for item in files if item['name'] != name]
    if mutation == 'wrong_config_file':
        (tmp_path / 'effective-config.json').write_text(json.dumps({**effective, 'precision': 'float32'}))
    if mutation == 'bool_in_config':
        (tmp_path / 'effective-config.json').write_text(json.dumps({**effective, 'seed': False}))
    if mutation == 'wrong_metrics_device':
        (tmp_path / 'metrics.json').write_text(json.dumps({'compute_device': 'cpu'}))
    with pytest.raises(ProtocolError):
        adapter.validate_completion(snapshot, effective, files, tmp_path)


def test_live_source_drift_cannot_be_claimed_as_loaded_code(monkeypatch):
    loaded = adapter.source_identity()
    monkeypatch.setattr(adapter, '_disk_source_identity', lambda: 'f' * 64 if loaded != 'f' * 64 else 'e' * 64)
    with pytest.raises(ProtocolError) as error:
        adapter.source_identity()
    assert error.value.code == 'ADAPTER_SOURCE_CHANGED'


def test_completion_rejects_unknown_transport_before_accepting_files(tmp_path):
    snapshot, effective, files = completion_fixture(tmp_path)
    snapshot['transport'] = 'insecure_tls'
    with pytest.raises(ProtocolError) as failure:
        adapter.validate_completion(snapshot, effective, files, tmp_path)
    assert failure.value.code == 'INVALID_TRANSPORT'
