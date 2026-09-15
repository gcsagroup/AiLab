"""推理接线与拒绝合同；缓存使用真实 CPU 数组，生成器夹具不充当模型实测。"""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.mlx_text.inference import InferenceError, PRESETS, identity, initial_cache_summary, resolve


@pytest.fixture
def cpu():
    import mlx.core as mx
    previous = mx.default_device()
    mx.set_default_device(mx.cpu)
    yield mx
    mx.set_default_device(previous)


def test_initial_cache_is_observed_and_populated_or_quantized_cache_is_rejected(cpu):
    from mlx_lm.models.cache import KVCache
    cache = [KVCache() for _ in range(24)]
    result = initial_cache_summary(cache)
    assert result['initially_empty'] is True and result['layer_count'] == 24
    assert all(layer['offset'] == layer['nbytes'] == 0 and layer['keys_absent'] and layer['values_absent'] for layer in result['layers'])
    tensor = cpu.ones((1, 2, 1, 64), dtype=cpu.float16)
    cache[0].update_and_fetch(tensor, tensor)
    with pytest.raises(InferenceError) as error:
        initial_cache_summary(cache)
    assert error.value.code == 'CACHE_NOT_EMPTY'
    with pytest.raises(InferenceError) as error:
        initial_cache_summary([KVCache().to_quantized(group_size=64, bits=4) for _ in range(24)])
    assert error.value.code == 'CACHE_CONFIG_MISMATCH'


def frozen_snapshot(tmp_path, operation='generate', runtime=None):
    from workers.mlx_worker import snapshot_manifest
    model = tmp_path / 'model'
    model.mkdir(exist_ok=True)
    (model / 'config.json').write_text(json.dumps({'model_type': 'qwen2', 'hidden_size': 896, 'num_hidden_layers': 24, 'num_attention_heads': 14, 'num_key_value_heads': 2}))
    (model / 'model.safetensors').write_bytes('合同夹具，不加载权重'.encode())
    manifest, digest = snapshot_manifest(model)
    return {'operation': operation, 'model_path': str(model), 'model_manifest': manifest, 'model_manifest_digest': digest,
            'input': {'prompt': '配置检查'}, 'runtime': runtime or {}}


@pytest.mark.parametrize('operation', ['train', 'evaluate', 'quantize'])
@pytest.mark.parametrize('field,value', [('kv_precision', 'q4'), ('prefill_step_size', 512), ('max_kv_size', None), ('prompt_cache', []), ('draft_model', 'unused')])
def test_non_generate_rejects_cache_and_unopened_runtime_fields(tmp_path, operation, field, value):
    from workers.mlx_worker import WorkerError, validate_snapshot
    with pytest.raises(WorkerError) as error:
        validate_snapshot(frozen_snapshot(tmp_path, operation, {field: value}), tmp_path / 'output')
    assert error.value.code == 'UNSUPPORTED_PARAMETER'


@pytest.mark.parametrize('field,value', [('max_kv_size', None), ('prompt_cache', []), ('draft_model', 'unused'), ('kv_bits', 4), ('kv_group_size', 64), ('prefix_cache', 'shared')])
def test_generate_rejects_unopened_cache_fields(tmp_path, field, value):
    from workers.mlx_worker import WorkerError, validate_snapshot
    with pytest.raises(WorkerError) as error:
        validate_snapshot(frozen_snapshot(tmp_path, runtime={field: value}), tmp_path / 'output')
    assert error.value.code == 'UNSUPPORTED_PARAMETER'


@pytest.mark.parametrize('preset', PRESETS.values(), ids=PRESETS)
def test_preflight_freezes_and_worker_receives_exact_cache_parameters(tmp_path, monkeypatch, cpu, preset):
    import mlx_lm
    import mlx_lm.utils
    from adapters.mlx_text.preflight import check
    import workers.mlx_worker as worker
    snapshot = frozen_snapshot(tmp_path, runtime={**preset, 'max_tokens': 67, 'temperature': 0.4, 'top_p': 0.9, 'seed': 19})
    tokenizer = SimpleNamespace(chat_template='合同模板', apply_chat_template=lambda *args, **kwargs: [1, 2, 3])
    monkeypatch.setattr(mlx_lm.utils, 'load_tokenizer', lambda *args, **kwargs: tokenizer)
    checked = check(snapshot, tmp_path / 'output')
    snapshot.update(tokenization_recipe_digest=checked['tokenization_recipe_digest'], effective_config=checked['effective_config'])
    effective = dict(checked['effective_config'])
    expected = resolve(preset)
    received = []

    def generate(model, tokenizer, prompt, **kwargs):
        received.append(kwargs)
        assert prompt == [1, 2, 3] and kwargs['max_tokens'] == 67
        for name in ('prefill_step_size', 'kv_bits', 'kv_group_size', 'quantized_kv_start', 'max_kv_size'):
            assert kwargs[name] == expected[name]
        cache = kwargs['prompt_cache']
        assert initial_cache_summary(cache)['initially_empty']
        kwargs['prompt_progress_callback'](0, 3)
        tensor = cpu.ones((1, 2, 3, 64), dtype=cpu.float16)
        for layer in cache:
            layer.update_and_fetch(tensor, tensor)
        if preset['kv_precision'] == 'q4':
            cache[:] = [layer.to_quantized(group_size=64, bits=4) for layer in cache]
        cpu.eval([layer.state for layer in cache])
        kwargs['prompt_progress_callback'](3, 3)
        for index, text in enumerate(('合同', '结果'), 1):
            yield SimpleNamespace(text=text, token=10 + index, generation_tokens=index, generation_tps=5.0, prompt_tps=10.0)

    monkeypatch.setattr(mlx_lm, 'stream_generate', generate)
    monkeypatch.setattr(worker, 'emit', lambda *args, **kwargs: None)
    output = tmp_path / 'output'; output.mkdir()
    worker.run_generate(SimpleNamespace(layers=[None] * 24), tokenizer, snapshot, effective, output)
    assert len(received) == 1 and received[0]['prompt_cache'] == []
    assert (output / 'result.txt').read_text() == '合同结果'
    assert effective['inference_recipe_digest'] == snapshot['effective_config']['inference_recipe_digest']
    assert effective['cache_observation']['initial']['initially_empty']
    assert effective['cache_observation']['final']['layer_count'] == 24
    metrics = json.loads((output / 'metrics.json').read_text())
    assert metrics['first_token_seconds'] >= 0 and metrics['generation_wall_seconds'] >= metrics['first_token_seconds']
    assert metrics['prefill_progress'] == [{'processed_tokens': 0, 'total_tokens': 3}, {'processed_tokens': 3, 'total_tokens': 3}]
    assert metrics['output_token_ids'] == [11, 12] and metrics['generation_tokens'] == 2
    assert metrics['final_kv_allocated_bytes'] > 0 and metrics['prefix_cache_hit_rate'] is None
    second_output = tmp_path / 'second-output'; second_output.mkdir()
    worker.run_generate(SimpleNamespace(layers=[None] * 24), tokenizer, snapshot, dict(checked['effective_config']), second_output)
    assert len(received) == 2 and received[0]['prompt_cache'] is not received[1]['prompt_cache']
    assert received[0]['prompt_cache'] == received[1]['prompt_cache'] == []


@pytest.mark.parametrize('damage', ['missing', 'digest', 'fields', 'runtime'])
def test_worker_rejects_unfrozen_or_changed_inference_before_generation(tmp_path, monkeypatch, damage):
    import mlx_lm
    import workers.mlx_worker as worker
    tokenizer = SimpleNamespace(chat_template='合同模板', apply_chat_template=lambda *args, **kwargs: [1, 2, 3])
    snapshot = {'model_manifest_digest': 'a' * 64, 'input': {'prompt': '合同输入'}}
    effective = {**resolve({}), 'seed': 0, 'max_tokens': 16, 'temperature': 0, 'top_p': 1}
    recipe, digest = identity(snapshot, effective, [1, 2, 3], hashlib.sha256(tokenizer.chat_template.encode()).hexdigest())
    snapshot['effective_config'] = {'inference_recipe': recipe, 'inference_recipe_digest': digest}
    if damage == 'missing': snapshot['effective_config'] = {}
    elif damage == 'digest': snapshot['effective_config']['inference_recipe_digest'] = 'f' * 64
    elif damage == 'fields': snapshot['effective_config']['inference_recipe'] = {}
    else: effective.update(resolve(PRESETS['low_memory']))
    monkeypatch.setattr(mlx_lm, 'stream_generate', lambda *args, **kwargs: pytest.fail('身份错误不得调用生成器'))
    with pytest.raises(InferenceError) as error:
        worker.run_generate(None, tokenizer, snapshot, effective, tmp_path)
    assert error.value.code in {'INFERENCE_IDENTITY_REQUIRED', 'INFERENCE_IDENTITY_CHANGED'}
    assert not (tmp_path / 'result.txt').exists()


def test_prefill_cancellation_stops_before_first_token_and_clears_local_cache(tmp_path, monkeypatch, cpu):
    import mlx_lm
    import workers.mlx_worker as worker
    tokenizer = SimpleNamespace(chat_template='合同模板', apply_chat_template=lambda *args, **kwargs: [1, 2, 3])
    snapshot = {'model_manifest_digest': 'a' * 64, 'input': {'prompt': '合同输入'}}
    effective = {**resolve(PRESETS['low_memory']), 'seed': 0, 'max_tokens': 16, 'temperature': 0, 'top_p': 1}
    recipe, digest = identity(snapshot, effective, [1, 2, 3], hashlib.sha256(tokenizer.chat_template.encode()).hexdigest())
    snapshot['effective_config'] = {'inference_recipe': recipe, 'inference_recipe_digest': digest}
    caches, events = [], []

    def generate(*args, **kwargs):
        caches.append(kwargs['prompt_cache'])
        kwargs['prompt_progress_callback'](0, 3)
        monkeypatch.setattr(worker, 'CANCELLED', True)
        kwargs['prompt_progress_callback'](1, 3)
        yield pytest.fail('Prefill 取消后不能生成 token')

    monkeypatch.setattr(worker, 'CANCELLED', False)
    monkeypatch.setattr(mlx_lm, 'stream_generate', generate)
    monkeypatch.setattr(worker, 'emit', lambda kind, **payload: events.append(kind))
    with pytest.raises(worker.WorkerError) as error:
        worker.run_generate(SimpleNamespace(layers=[None] * 24), tokenizer, snapshot, effective, tmp_path)
    assert error.value.code == 'CANCELLED'
    assert caches == [[]] and 'token' not in events
    assert not (tmp_path / 'result.txt').exists() and not (tmp_path / 'cache-observation.json').exists()
