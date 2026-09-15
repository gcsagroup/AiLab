"""低内存 v2 独立候选：固定原题、原输出预算；比较全输出词元与首步 logits。"""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.mlx_text.inference import initial_cache_summary, cache_summary
from adapters.mlx_text.preflight import check
from workers.mlx_worker import sha256, write_json, validate_snapshot, snapshot_manifest
from run_kv_probe import process


def capture(snapshot_path, destination):
    """只读观察首步完整 logits；处理器原样返回同一 logits 数组。"""
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.models.cache import make_prompt_cache
    from mlx_lm.sample_utils import make_sampler
    snapshot = json.loads(snapshot_path.read_text())
    model_path, effective = validate_snapshot(snapshot, destination)
    destination.mkdir()
    mx.set_default_device(mx.gpu)
    mx.random.seed(effective['seed'])
    model, tokenizer = load(str(model_path), tokenizer_config={'trust_remote_code': False, 'local_files_only': True})
    prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': snapshot['input']['prompt']}], tokenize=True, add_generation_prompt=True)
    cache, observed, tokens, chunks = make_prompt_cache(model, max_kv_size=None), [], [], []
    initial = initial_cache_summary(cache)
    def observe(_, logits):
        if not observed:
            first = logits.reshape(-1).astype(mx.float32)
            mx.eval(first)
            observed.append(first)
        return logits
    try:
        for response in stream_generate(model, tokenizer, prompt, max_tokens=128, sampler=make_sampler(temp=0, top_p=1),
                                        prompt_cache=cache, max_kv_size=None, kv_bits=None, kv_group_size=64,
                                        quantized_kv_start=0, prefill_step_size=effective['prefill_step_size'], logits_processors=[observe]):
            tokens.append(response.token)
            chunks.append(response.text)
        mx.synchronize()
        assert len(observed) == 1 and bool(mx.all(mx.isfinite(observed[0])).item())
        final = cache_summary(cache, 'auto')
        mx.save_safetensors(str(destination / 'first-step-logits.safetensors'), {'logits': observed[0]})
        result = {'source': '官方 stream_generate；只读 logits_processors 返回原数组，不修改采样或 logits',
                  'output_token_ids': tokens, 'output_text': ''.join(chunks), 'first_step_argmax': int(mx.argmax(observed[0]).item()),
                  'logits_shape': list(observed[0].shape), 'initial': initial, 'final': final,
                  'snapshot_sha256': sha256(snapshot_path), 'logits_sha256': sha256(destination / 'first-step-logits.safetensors')}
        write_json(destination / 'observation.json', result)
    finally:
        cache.clear()
        mx.clear_cache()
    assert snapshot_manifest(model_path) == (snapshot['model_manifest'], snapshot['model_manifest_digest'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--capture-snapshot', type=Path)
    parser.add_argument('--capture-output', type=Path)
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    if args.capture_snapshot:
        capture(args.capture_snapshot, args.capture_output)
        return 0
    assert args.reference and args.evidence
    reference_path, evidence = args.reference.resolve(), args.evidence.resolve()
    reference = json.loads((reference_path / 'report.json').read_text())
    cases = [case for case in reference['cases'] if case['category'] == 'quality' and case['preset'] == 'default']
    assert len(cases) == 12 and all(case['status'] == 'passed' for case in cases)
    evidence.mkdir(parents=True, exist_ok=False)
    source_files = [ROOT / 'workers/mlx_worker.py', ROOT / 'adapters/mlx_text/inference.py', ROOT / 'adapters/mlx_text/preflight.py', Path(__file__)]
    source_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in source_files}
    plan = {'schema_version': 'kv-candidate-plan-v1', 'candidate_id': 'low_memory_v2', 'candidate_version': 2,
            'created_at': time.time(), 'candidate_runtime': {'kv_precision': 'auto', 'prefill_step_size': 512},
            'unchanged': {'model_weights': True, 'max_tokens': 128, 'seed': 0, 'temperature': 0, 'top_p': 1, 'context_limit': 4096},
            'source_sha256': source_hashes, 'reference_report_sha256': sha256(reference_path / 'report.json'),
            'criteria': {'all_candidate_output_token_ids_equal_original_default': True, 'instrumentation_output_token_ids_equal_product_worker': True,
                         'first_step_logits_finite_and_argmax_equal': True, 'numerical_logits_difference': '报告完整向量 max_abs/RMSE，不把舍入差异隐瞒为逐元素相等',
                         'original_task_errors': '保留原默认模型的固定题错误；通过仅表示此候选没有新增回归，不宣称模型全部答对。'},
            'fixed_order': [{'name': case['name'], 'prompt_sha256': hashlib.sha256(json.loads((reference_path / (case['name'] + '.snapshot.json')).read_text())['input']['prompt'].encode()).hexdigest(),
                             'reference_answer_correct': case['answer_correct'], 'reference_output_token_ids': case['metrics']['output_token_ids']} for case in cases]}
    plan['plan_digest'] = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    write_json(evidence / 'frozen-plan.json', plan)
    report = {'plan_digest': plan['plan_digest'], 'status': 'running', 'cases': [], 'started_at': time.time()}
    def save(): write_json(evidence / 'report.json', report)
    save()
    for case in cases:
        name = case['name'].removeprefix('quality-').removesuffix('-default')
        result = {'name': name, 'status': 'running', 'original_answer_correct': case['answer_correct']}
        report['cases'].append(result)
        try:
            assert all(sha256(path) == source_hashes[str(path.relative_to(ROOT))] for path in source_files), '测试期间执行源码变化'
            original = json.loads((reference_path / (case['name'] + '.snapshot.json')).read_text())
            snapshot = copy.deepcopy(original)
            snapshot['attempt_id'] = 'candidate-v2-' + name
            snapshot['runtime'].update(kv_precision='auto', prefill_step_size=512)
            output = evidence / (name + '-product')
            checked = check(snapshot, output)
            assert checked['can_submit']
            snapshot.update(tokenization_recipe_digest=checked['tokenization_recipe_digest'], effective_config=checked['effective_config'])
            path = evidence / (name + '.snapshot.json'); write_json(path, snapshot)
            result['snapshot_sha256'] = sha256(path)
            print('新候选真实质量：' + name, flush=True)
            events, execution = process(path, output, evidence / (name + '-product'))
            result['execution'] = execution
            assert execution['returncode'] == 0 and events[-1]['type'] == 'completed', events[-1:]
            for artifact in events[-1]['artifacts']: assert sha256(output / artifact['path']) == artifact['sha256']
            metrics = json.loads((output / 'metrics.json').read_text())
            effective = json.loads((output / 'effective-config.json').read_text())
            assert effective['kv_precision'] == 'auto' and effective['prefill_step_size'] == 512 and effective['max_tokens'] == 128
            assert effective['inference_recipe'] == snapshot['effective_config']['inference_recipe']
            assert effective['cache_observation']['initial']['initially_empty']
            assert all(layer['class'] == 'KVCache' for layer in effective['cache_observation']['final']['layers'])
            result.update(output_token_ids=metrics['output_token_ids'], output_text=(output / 'result.txt').read_text(),
                          token_ids_equal_original_default=metrics['output_token_ids'] == case['metrics']['output_token_ids'])
            observations = {}
            for label, block in [('default', 2048), ('candidate', 512)]:
                observed_snapshot = copy.deepcopy(snapshot)
                observed_snapshot['runtime']['prefill_step_size'] = block
                observed_path = evidence / (name + '-' + label + '-observe.snapshot.json')
                observed_output = evidence / (name + '-' + label + '-observe')
                observed_check = check(observed_snapshot, observed_output)
                observed_snapshot.update(tokenization_recipe_digest=observed_check['tokenization_recipe_digest'], effective_config=observed_check['effective_config'])
                write_json(observed_path, observed_snapshot)
                observation = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--capture-snapshot', str(observed_path), '--capture-output', str(observed_output)], cwd=ROOT, capture_output=True, text=True, timeout=180)
                (evidence / (name + '-' + label + '-observe.stderr.log')).write_text(observation.stderr)
                assert observation.returncode == 0, observation.stderr
                observations[label] = json.loads((observed_output / 'observation.json').read_text())
            import mlx.core as mx
            # 比较在 CPU 上进行，两个观察进程均已退出，没有复用任何模型或缓存。
            mx.set_default_device(mx.cpu)
            baseline = mx.load(str(evidence / (name + '-default-observe/first-step-logits.safetensors')))['logits']
            candidate = mx.load(str(evidence / (name + '-candidate-observe/first-step-logits.safetensors')))['logits']
            delta = baseline - candidate
            result['logit_comparison'] = {'scope': '首个生成位置的完整词表 logits，两个独立进程', 'shape': list(baseline.shape),
                                          'max_abs': float(mx.max(mx.abs(delta)).item()), 'rmse': float(mx.sqrt(mx.mean(delta * delta)).item()),
                                          'exact_equal': bool(mx.array_equal(baseline, candidate).item()),
                                          'argmax_equal': observations['default']['first_step_argmax'] == observations['candidate']['first_step_argmax']}
            result['instrumentation_tokens_match_default'] = observations['default']['output_token_ids'] == case['metrics']['output_token_ids']
            result['instrumentation_tokens_match_candidate'] = observations['candidate']['output_token_ids'] == metrics['output_token_ids']
            assert result['token_ids_equal_original_default'] and result['logit_comparison']['argmax_equal']
            assert result['instrumentation_tokens_match_default'] and result['instrumentation_tokens_match_candidate']
            result['status'] = 'passed_no_regression'
        except Exception as error:
            result.update(status='failed', error=repr(error))
        save()
        print(json.dumps({'name': name, 'status': result['status'], 'error': result.get('error')}, ensure_ascii=False), flush=True)
    report.update(status='passed_no_regression' if all(case['status'] == 'passed_no_regression' for case in report['cases']) else 'partial',
                  candidate_id='low_memory_v2', candidate_runtime=plan['candidate_runtime'], total=len(cases),
                  original_fixed_tasks_correct=sum(case['original_answer_correct'] for case in report['cases']),
                  original_model_quality_boundary=plan['criteria']['original_task_errors'], finished_at=time.time())
    save()
    print(json.dumps({'status': report['status'], 'report': str(evidence / 'report.json')}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed_no_regression' else 1


if __name__ == '__main__':
    raise SystemExit(main())
