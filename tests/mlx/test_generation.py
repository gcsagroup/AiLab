"""文本参数与实际接线负例；模型实算在 run_generation_probe.py 独立保存。"""
import hashlib
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.mlx_text.generation import GenerationError, StopBuffer, prepare_prompt, resolve
from adapters.mlx_text.inference import identity, resolve as inference_resolve
from test_inference_worker import cpu, frozen_snapshot


@pytest.mark.parametrize('field,value', [
    ('context_limit', True), ('context_limit', 512.0), ('context_limit', None), ('context_limit', '512'), ('context_limit', 127), ('context_limit', 4097),
    ('overflow', None), ('overflow', 'truncate'), ('overflow', True), ('thinking', 'on'), ('thinking', 'off'), ('thinking', None),
    ('stream', 0), ('stream', 1), ('stream', 'false'), ('stream', None), ('stop', None), ('stop', 'END'), ('stop', ()),
    ('stop', [1]), ('stop', [None]), ('stop', ['']), ('stop', ['x' * 129]), ('stop', ['a', 'a']), ('stop', list('123456789')),
    ('stop', ['\0']), ('stop', ['\x7f']), ('stop', ['\ud800']),
])
def test_unknown_null_and_coerced_values_are_rejected(field, value):
    with pytest.raises(GenerationError) as error:
        resolve({field: value})
    assert error.value.code == 'UNSUPPORTED_PARAMETER'


def test_defaults_preserve_legacy_behavior_and_literal_stop_whitespace():
    assert resolve({}) == {'context_limit': 4096, 'overflow': 'reject', 'stop': [], 'stream': True, 'thinking': 'default'}
    assert resolve({'stop': [' ', ' END ', '\n\n', '完成🙂']})['stop'] == [' ', ' END ', '\n\n', '完成🙂']


def test_real_template_count_obeys_exact_total_budget_without_truncation():
    received = []
    tokenizer = SimpleNamespace(apply_chat_template=lambda messages, **kw: received.append((messages, kw)) or [1, 2, 3, 4, 5])
    inputs = {'prompt': '必须完整保留的用户输入'}
    effective = {**resolve({'context_limit': 128}), 'max_tokens': 123}
    tokens, report = prepare_prompt(tokenizer, inputs, effective)
    assert len(tokens) == 5 and report['total_token_budget'] == report['context_limit'] == 128
    assert received[0][0] == [{'role': 'user', 'content': inputs['prompt']}] and received[0][1] == {'tokenize': True, 'add_generation_prompt': True}
    assert report['input_truncated'] is False and report['reserved_output_tokens'] == 123
    with pytest.raises(GenerationError) as error:
        prepare_prompt(tokenizer, inputs, {**effective, 'max_tokens': 124})
    assert error.value.code == 'CONTEXT_TOO_LONG'
    assert error.value.details['check_report']['total_token_budget'] == 129
    assert inputs == {'prompt': '必须完整保留的用户输入'}


@pytest.mark.parametrize('source,stops,expected,index', [
    ('abcENDlater', ['END'], 'abc', 0), ('开始完成🙂以后', ['完成🙂'], '开始', 0),
    ('prefix EN', ['END'], 'prefix EN', None), ('END', ['END'], '', 0), ('ENDagain', [], 'ENDagain', None),
    ('ababc', ['abc', 'b'], 'a', 1), ('abcd', ['abcd', 'bc'], 'a', 1),
    ('a\n\nb', ['\n\n'], 'a', 0), ('甲 完成 乙', [' 完成 '], '甲', 0), ('ABCend', ['END'], 'ABCend', None),
])
def test_stop_matching_is_chunk_independent_and_does_not_leak_prefix(source, stops, expected, index):
    randomizer = random.Random(61)
    partitions = [[source], list(source)]
    for _ in range(30):
        cuts = sorted({0, len(source), *(randomizer.randrange(len(source) + 1) for _ in range(6))})
        partitions.append([source[a:b] for a, b in zip(cuts, cuts[1:])])
    for parts in partitions:
        buffer, displayed = StopBuffer(stops), ''
        for part in parts:
            displayed += buffer.feed(part)
            assert expected.startswith(displayed)
            if buffer.stopped:
                break
        displayed += buffer.finish()
        assert displayed == expected and buffer.matched_index == index


@pytest.mark.parametrize('field,value', [('context_limit', 2048), ('stop', ['END']), ('stream', False)])
def test_new_runtime_fields_change_frozen_inference_identity(field, value):
    snapshot = {'model_manifest_digest': 'a' * 64}
    original = {**inference_resolve({}), 'seed': 0, 'max_tokens': 16, 'temperature': 0, 'top_p': 1}
    recipe, digest = identity(snapshot, original, [1, 2, 3], 'b' * 64)
    modified = {**original, **inference_resolve({field: value})}
    assert identity(snapshot, modified, [1, 2, 3], 'b' * 64)[1] != digest
    assert recipe['runtime'][field] == original[field] and recipe['schema_version'] == 'mlx-inference-v2'
    assert recipe['generation_source_sha256'] == hashlib.sha256((Path(__file__).resolve().parents[2] / 'adapters/mlx_text/generation.py').read_bytes()).hexdigest()


@pytest.mark.parametrize('operation', ['train', 'evaluate', 'quantize'])
@pytest.mark.parametrize('field,value', [('context_limit', 1024), ('overflow', 'reject'), ('stop', []), ('stream', False), ('thinking', 'default')])
def test_non_generation_rejects_generation_fields(tmp_path, operation, field, value):
    from workers.mlx_worker import WorkerError, validate_snapshot
    with pytest.raises(WorkerError) as error:
        validate_snapshot(frozen_snapshot(tmp_path, operation, {field: value}), tmp_path / 'output')
    assert error.value.code == 'UNSUPPORTED_PARAMETER'


@pytest.mark.parametrize('stream', [True, False])
@pytest.mark.parametrize('stops,expected,count,reason', [([], '甲STOP后续', 4, 'length'), (['STOP'], '甲', 3, 'stop_sequence'), (['STOPS'], '甲STOP后续', 4, 'length'), (['甲'], '', 1, 'stop_sequence')])
def test_worker_stops_computation_closes_generator_and_persists_exact_display(tmp_path, monkeypatch, cpu, stream, stops, expected, count, reason):
    import mlx_lm
    import mlx_lm.utils
    import workers.mlx_worker as worker
    from adapters.mlx_text.preflight import check
    snapshot = frozen_snapshot(tmp_path, runtime={'max_tokens': 32, 'context_limit': 128, 'stream': stream, 'stop': stops})
    tokenizer = SimpleNamespace(chat_template='固定模板', apply_chat_template=lambda *args, **kwargs: [1, 2, 3])
    monkeypatch.setattr(mlx_lm.utils, 'load_tokenizer', lambda *a, **k: tokenizer)
    checked = check(snapshot, tmp_path / 'output')
    snapshot.update(tokenization_recipe_digest=checked['tokenization_recipe_digest'], effective_config=checked['effective_config'])
    events, computed, closed, caches = [], [], [], []
    def generate(*args, **kwargs):
        cache = kwargs['prompt_cache']; caches.append(cache)
        tensor = cpu.ones((1, 2, 3, 64), dtype=cpu.float16)
        for layer in cache:
            layer.update_and_fetch(tensor, tensor)
        kwargs['prompt_progress_callback'](3, 3)
        try:
            for index, text in enumerate(['甲S', 'T', 'OP', '后续'], 1):
                computed.append(index)
                yield SimpleNamespace(text=text, token=index, generation_tokens=index, generation_tps=10, prompt_tps=10, finish_reason='length' if index == 4 else None)
        finally:
            closed.append(True)
    monkeypatch.setattr(mlx_lm, 'stream_generate', generate)
    monkeypatch.setattr(worker, 'CANCELLED', False)
    monkeypatch.setattr(worker, 'emit', lambda kind, **payload: events.append({'type': kind, **payload}))
    output = tmp_path / 'output'; output.mkdir()
    effective = dict(checked['effective_config'])
    worker.run_generate(SimpleNamespace(layers=[None] * 24), tokenizer, snapshot, effective, output)
    assert len(computed) == count and closed == [True] and caches == [[]]
    assert (output / 'result.txt').read_text() == expected
    assert ''.join(e['text'] for e in events if e['type'] == 'token') == (expected if stream else '')
    assert any(e['type'] == 'phase' for e in events)
    metrics = json.loads((output / 'metrics.json').read_text())
    assert metrics['finish_reason'] == reason and metrics['generation_tokens'] == count
    assert metrics['token_events'] == sum(e['type'] == 'token' for e in events)
    if not stream:
        assert metrics['token_events'] == 0
    assert effective['context_observation']['total_token_budget'] == 35
    assert effective['thinking_supported'] is False and effective['thinking'] == 'default'
    assert effective['stop'] == stops and effective['stream'] is stream


def test_stream_disabled_still_checks_cancellation_and_releases_generator(tmp_path, monkeypatch, cpu):
    import mlx_lm
    import workers.mlx_worker as worker
    tokenizer = SimpleNamespace(chat_template='模板', apply_chat_template=lambda *a, **k: [1, 2, 3])
    snapshot = {'model_manifest_digest': 'a' * 64, 'input': {'prompt': '输入'}}
    effective = {**inference_resolve({'stream': False}), 'max_tokens': 32, 'seed': 0, 'temperature': 0, 'top_p': 1}
    recipe, digest = identity(snapshot, effective, [1, 2, 3], hashlib.sha256(tokenizer.chat_template.encode()).hexdigest())
    snapshot['effective_config'] = {'inference_recipe': recipe, 'inference_recipe_digest': digest}
    closed, caches, events = [], [], []
    def generate(*args, **kwargs):
        caches.append(kwargs['prompt_cache'])
        try:
            monkeypatch.setattr(worker, 'CANCELLED', True)
            yield SimpleNamespace(text='不可显示', token=1, generation_tokens=1)
        finally:
            closed.append(True)
    monkeypatch.setattr(mlx_lm, 'stream_generate', generate)
    monkeypatch.setattr(worker, 'CANCELLED', False)
    monkeypatch.setattr(worker, 'emit', lambda kind, **p: events.append(kind))
    with pytest.raises(worker.WorkerError) as error:
        worker.run_generate(SimpleNamespace(layers=[None] * 24), tokenizer, snapshot, effective, tmp_path)
    assert error.value.code == 'CANCELLED' and closed == [True] and caches == [[]]
    assert 'token' not in events and not (tmp_path / 'result.txt').exists()


def test_rejected_initial_cache_is_still_released(tmp_path, monkeypatch, cpu):
    import mlx_lm
    import mlx_lm.models.cache
    import workers.mlx_worker as worker
    from adapters.mlx_text.inference import InferenceError
    tokenizer = SimpleNamespace(chat_template='模板', apply_chat_template=lambda *a, **k: [1, 2, 3])
    snapshot = {'model_manifest_digest': 'a' * 64, 'input': {'prompt': '输入'}}
    effective = {**inference_resolve({}), 'max_tokens': 32, 'seed': 0, 'temperature': 0, 'top_p': 1}
    recipe, digest = identity(snapshot, effective, [1, 2, 3], hashlib.sha256(tokenizer.chat_template.encode()).hexdigest())
    snapshot['effective_config'] = {'inference_recipe': recipe, 'inference_recipe_digest': digest}
    cache = [object()]
    released = []
    monkeypatch.setattr(mlx_lm.models.cache, 'make_prompt_cache', lambda *a, **k: cache)
    monkeypatch.setattr(mlx_lm, 'stream_generate', lambda *a, **k: pytest.fail('拒绝缓存后不能生成'))
    monkeypatch.setattr(cpu, 'clear_cache', lambda: released.append(True))
    monkeypatch.setattr(worker, 'emit', lambda *a, **k: None)
    with pytest.raises(InferenceError) as error:
        worker.run_generate(SimpleNamespace(layers=[None] * 24), tokenizer, snapshot, effective, tmp_path)
    assert error.value.code == 'CACHE_CONFIG_MISMATCH' and cache == [] and released == [True]
    assert not (tmp_path / 'result.txt').exists()
