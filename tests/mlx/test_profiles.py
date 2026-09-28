"""新增基座的结构、层数、LoRA 与缓存边界；夹具不证明真实模型质量。"""
import json
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.mlx_text.profiles import adapter_shapes, model_profile
from adapters.mlx_text.inference import initial_cache_summary, cache_summary, InferenceError
from workers.mlx_worker import validate_snapshot, snapshot_manifest, WorkerError

LARGE = {'model_type': 'qwen2', 'hidden_size': 3584, 'num_hidden_layers': 28,
         'num_attention_heads': 28, 'num_key_value_heads': 4, 'intermediate_size': 18944,
         'vocab_size': 152064, 'tie_word_embeddings': False}


@pytest.mark.parametrize('field,value', [('num_hidden_layers', 24), ('hidden_size', 896), ('num_attention_heads', 14), ('num_key_value_heads', 2), ('intermediate_size', None), ('vocab_size', 151936), ('tie_word_embeddings', 0), ('num_hidden_layers', 28.0)])
def test_unverified_large_geometry_is_rejected(field, value):
    with pytest.raises(ValueError):
        model_profile({**LARGE, field: value})


def test_lora_shapes_cover_actual_last_layers_and_both_projection_widths():
    profile = model_profile(LARGE)
    shapes = adapter_shapes(profile, 28, 8)
    assert len(shapes) == 112
    assert shapes['model.layers.0.self_attn.q_proj.lora_a'] == [3584, 8]
    assert shapes['model.layers.27.self_attn.q_proj.lora_b'] == [8, 3584]
    assert shapes['model.layers.27.self_attn.v_proj.lora_b'] == [8, 512]
    assert all(name.startswith('model.layers.27.') for name in adapter_shapes(profile, 1, 4))
    with pytest.raises(ValueError): adapter_shapes(profile, 29, 4)
    with pytest.raises(ValueError): adapter_shapes(profile, True, 4)


def snapshot(tmp_path, config, operation, runtime):
    model = tmp_path / 'model'; model.mkdir()
    (model / 'config.json').write_text(json.dumps(config)); (model / 'model.safetensors').write_bytes(b'contract-only')
    files, digest = snapshot_manifest(model)
    data = tmp_path / 'train.jsonl'; data.write_text('{}\n'); df, dd = snapshot_manifest(data)
    return {'operation': operation, 'model_path': str(model), 'model_manifest': files, 'model_manifest_digest': digest,
            'dataset_path': str(data), 'dataset_manifest': df, 'dataset_manifest_digest': dd, 'runtime': runtime,
            'input': {'prompt': '测试'} if operation == 'generate' else {}}


@pytest.mark.parametrize('layers', [1, 24, 28])
def test_large_training_layer_limits(tmp_path, layers):
    _, effective = validate_snapshot(snapshot(tmp_path, LARGE, 'train', {'num_layers': layers}), tmp_path / 'output')
    assert effective['num_layers'] == layers


def test_small_model_does_not_inherit_large_layer_limit(tmp_path):
    small = {'model_type': 'qwen2', 'hidden_size': 896, 'num_hidden_layers': 24}
    with pytest.raises(WorkerError):
        validate_snapshot(snapshot(tmp_path, small, 'train', {'num_layers': 28}), tmp_path / 'output')


@pytest.mark.parametrize('operation,quantized', [('quantize', False), ('generate', True)])
def test_large_quantization_is_not_silently_enabled(tmp_path, operation, quantized):
    config = dict(LARGE)
    if quantized: config['quantization'] = {'bits': 4, 'group_size': 64, 'mode': 'affine'}
    with pytest.raises(WorkerError) as error:
        validate_snapshot(snapshot(tmp_path, config, operation, {}), tmp_path / 'output')
    assert error.value.code == 'MODEL_OPERATION_UNSUPPORTED'


def test_large_cpu_cache_geometry_and_wrong_layer_count():
    import mlx.core as mx
    from mlx_lm.models.cache import KVCache
    previous = mx.default_device(); mx.set_default_device(mx.cpu)
    try:
        cache = [KVCache() for _ in range(28)]
        assert initial_cache_summary(cache, 28)['initially_empty']
        with pytest.raises(InferenceError): initial_cache_summary(cache, 24)
        value = mx.ones((1, 4, 3, 128), dtype=mx.float16)
        for layer in cache: layer.update_and_fetch(value, value)
        mx.eval([layer.state for layer in cache])
        report = cache_summary(cache, 'auto', 28)
        assert report['layer_count'] == 28
        assert all(layer['keys'][0]['shape'][1:] == [4, 256, 128] for layer in report['layers'])
    finally: mx.set_default_device(previous)


def test_large_q4_cache_is_blocked_after_real_output_failure(tmp_path):
    with pytest.raises(WorkerError) as error:
        validate_snapshot(snapshot(tmp_path, LARGE, 'generate', {'kv_precision': 'q4'}), tmp_path / 'output')
    assert error.value.code == 'UNSUPPORTED_PARAMETER'
    assert 'q4 KV' in str(error.value)
