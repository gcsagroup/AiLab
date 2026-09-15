"""缓存策略的拒绝与真实 CPU 缓存回读；不执行语言模型或使用 GPU。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.mlx_text.inference import InferenceError, PRESETS, cache_summary, identity, resolve


@pytest.mark.parametrize('runtime', [
    {'kv_precision': False}, {'kv_precision': None}, {'kv_precision': 'q8'},
    {'prefill_step_size': True}, {'prefill_step_size': 512.0}, {'prefill_step_size': 0},
    {'prefill_step_size': 513}, {'prefill_step_size': None},
])
def test_unknown_or_coerced_cache_values_are_rejected(runtime):
    with pytest.raises(InferenceError, match='只接受'):
        resolve(runtime)


def test_defaults_and_presets_keep_task_token_budget():
    runtime = {'max_tokens': 67, 'temperature': 0.4, 'top_p': 0.9, 'seed': 19}
    for preset in PRESETS.values():
        result = resolve({**runtime, **preset})
        assert result['max_kv_size'] is None and result['prefix_cache'] == 'disabled'
        assert result['context_limit'] == 4096
        assert not set(runtime) & set(result)
    assert resolve({}) == resolve(PRESETS['default'])


def test_inference_identity_separates_input_adapter_and_strategy():
    snapshot = {'model_manifest_digest': 'a' * 64}
    effective = {**resolve({}), 'seed': 0, 'max_tokens': 16, 'temperature': 0, 'top_p': 1}
    recipe, original = identity(snapshot, effective, [1, 2, 3], 'b' * 64)
    assert original != identity(snapshot, effective, [1, 2, 4], 'b' * 64)[1]
    assert original != identity({**snapshot, 'adapter_manifest_digest': 'c' * 64}, effective, [1, 2, 3], 'b' * 64)[1]
    assert original != identity(snapshot, {**effective, **resolve(PRESETS['low_memory'])}, [1, 2, 3], 'b' * 64)[1]
    assert 'prompt_tokens_sha256' in recipe and [1, 2, 3] not in recipe.values()


def test_real_cache_summary_reads_quantization_and_allocated_bytes():
    import mlx.core as mx
    from mlx_lm.models.cache import KVCache
    previous = mx.default_device()
    mx.set_default_device(mx.cpu)
    try:
        full = [KVCache() for _ in range(24)]
        assert all(layer.empty() and layer.offset == 0 for layer in full)
        tensor = mx.ones((1, 2, 5, 64), dtype=mx.float16)
        for layer in full:
            layer.update_and_fetch(tensor, tensor)
        mx.eval([layer.state for layer in full])
        ordinary = cache_summary(full, 'auto')
        quantized = [layer.to_quantized(group_size=64, bits=4) for layer in full]
        mx.eval([layer.state for layer in quantized])
        low = cache_summary(quantized, 'q4')
        assert ordinary['total_allocated_bytes'] == 24 * 2 * 1 * 2 * 256 * 64 * 2
        assert low['total_allocated_bytes'] == 24 * 2 * 1 * 2 * 256 * (8 * 4 + 2 * 2)
        assert low['total_allocated_bytes'] < ordinary['total_allocated_bytes']
        assert all(layer['bits'] == 4 and layer['group_size'] == 64 and layer['offset'] == 5 for layer in low['layers'])
        assert 'initially_empty' not in low and low['cross_request_reuse'] is False
        json.dumps(low)
        with pytest.raises(InferenceError, match='类型'):
            cache_summary(full, 'q4')
        with pytest.raises(InferenceError, match='类型'):
            cache_summary(quantized[:-1], 'q4')
    finally:
        mx.set_default_device(previous)
