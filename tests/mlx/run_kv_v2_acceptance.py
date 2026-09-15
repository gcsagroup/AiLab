"""低内存 v2 的固定性能重复、独立缓存隔离和按真实事件取消验证。"""

import argparse
import copy
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text.preflight import check
from workers.mlx_worker import sha256, snapshot_manifest, write_json
from run_kv_probe import process, NUMERIC_METRICS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, required=True)
    args = parser.parse_args()
    reference, evidence, adapter = args.reference.resolve(), args.evidence.resolve(), args.adapter.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    bases = {(model, size): json.loads((reference / (f'functional-{model}-{size}-default.snapshot.json')).read_text())
             for model in ('bf16', 'weight_q4') for size in ('short', 'medium', 'long')}
    adapter_manifest = snapshot_manifest(adapter)
    adapter_config = json.loads((adapter / 'adapter_config.json').read_text())
    plan = {'schema_version': 'kv-v2-acceptance-plan-v1', 'candidate_id': 'low_memory_v2', 'candidate_version': 2,
            'runtime': {'kv_precision': 'auto', 'prefill_step_size': 512}, 'unchanged': {'max_tokens': 128, 'seed': 0, 'temperature': 0, 'top_p': 1},
            'reference_report_sha256': sha256(reference / 'report.json'), 'adapter_manifest_digest': adapter_manifest[1],
            'source_sha256': {str(path.relative_to(ROOT)): sha256(path) for path in [Path(__file__), ROOT / 'tests/mlx/run_kv_probe.py', ROOT / 'workers/mlx_worker.py', ROOT / 'adapters/mlx_text/inference.py', ROOT / 'adapters/mlx_text/preflight.py']},
            'fixed_performance_order': [(repeat, model, size) for repeat in range(3) for size in ('short', 'medium', 'long') for model in ('bf16', 'weight_q4')],
            'isolation_order': ['bf16-A-cold', 'weight_q4-A-cold', 'bf16-B-cold', 'weight_q4-B-cold', 'bf16-A-repeat', 'weight_q4-A-repeat', 'bf16-B-repeat', 'weight_q4-B-repeat', 'plain-cold', 'adapter-cold', 'plain-repeat', 'adapter-repeat'],
            'cancel_order': ['bf16-prefill', 'bf16-decode', 'bf16-recovery', 'weight_q4-prefill', 'weight_q4-decode', 'weight_q4-recovery'],
            'performance_scope': '额外独立候选18次，不混入原q4缓存失败预设统计；原同参数auto512归因记录另作明确来源。'}
    write_json(evidence / 'frozen-plan.json', plan)
    report = {'candidate_id': plan['candidate_id'], 'plan_sha256': sha256(evidence / 'frozen-plan.json'), 'status': 'running', 'started_at': time.time(), 'cases': []}
    def save(): write_json(evidence / 'report.json', report)
    def run(name, model, size, category, prompt=None, use_adapter=False, cancel=None):
        result = {'name': name, 'model': model, 'size': size, 'category': category, 'status': 'running', 'adapter': use_adapter}
        report['cases'].append(result)
        snapshot = copy.deepcopy(bases[model, size])
        snapshot['attempt_id'] = name
        snapshot['runtime'].update(plan['runtime'])
        if prompt is not None: snapshot['input']['prompt'] = prompt
        if use_adapter:
            snapshot.update(adapter_path=str(adapter), adapter_manifest=adapter_manifest[0], adapter_manifest_digest=adapter_manifest[1],
                            adapter_training_recipe_digest=adapter_config['training_recipe_digest'])
        try:
            assert all(sha256(ROOT / path) == checksum for path, checksum in plan['source_sha256'].items()), '执行期间源码变化'
            output = evidence / name
            checked = check(snapshot, output)
            assert checked['can_submit']
            snapshot.update(tokenization_recipe_digest=checked['tokenization_recipe_digest'], effective_config=checked['effective_config'])
            snapshot_path = evidence / (name + '.snapshot.json'); write_json(snapshot_path, snapshot)
            result['inference_recipe_digest'] = checked['effective_config']['inference_recipe_digest']
            save(); print('v2 验收：' + name, flush=True)
            events, execution = process(snapshot_path, output, evidence / name, cancel)
            result['execution'] = execution
            if cancel:
                assert execution['returncode'] == 130 and execution['cancel_to_exit_seconds'] is not None
                assert events[-1].get('code') == 'CANCELLED' and not any(event['type'] == 'completed' for event in events)
            else:
                assert execution['returncode'] == 0 and events[-1]['type'] == 'completed', events[-1:]
                for item in events[-1]['artifacts']: assert sha256(output / item['path']) == item['sha256']
                effective = json.loads((output / 'effective-config.json').read_text())
                assert effective['inference_recipe'] == checked['effective_config']['inference_recipe']
                assert effective['cache_observation']['initial']['initially_empty']
                assert effective['prefix_cache'] == 'disabled' and all(layer['class'] == 'KVCache' for layer in effective['cache_observation']['final']['layers'])
                metrics = json.loads((output / 'metrics.json').read_text())
                metrics['process_wall_seconds'] = execution['process_wall_seconds']
                result.update(metrics=metrics, initially_empty=True, output_text=(output / 'result.txt').read_text())
            result['status'] = 'passed'
        except Exception as error:
            result.update(status='failed', error=repr(error))
        save(); print(json.dumps({'name': name, 'status': result['status'], 'error': result.get('error')}, ensure_ascii=False), flush=True)
        return result
    for repeat, model, size in plan['fixed_performance_order']:
        run(f'performance-v2-{repeat}-{model}-{size}', model, size, 'performance')
    cold = {}
    for repeat in (False, True):
        for label, code in [('A', '3471'), ('B', '9265')]:
            for model in ('bf16', 'weight_q4'):
                prompt = '同一段公开前缀：本次只读取末尾明确给出的数字，不读取其它运行。\n' + f'本次数字为 {code}。只回答本次数字。'
                result = run(f'isolation-v2-{model}-{label}-' + ('repeat' if repeat else 'cold'), model, 'short', 'isolation', prompt)
                if not repeat:
                    cold[model, label] = result
                elif result['status'] == cold[model, label]['status'] == 'passed':
                    result['same_as_own_cold_token_ids'] = result['metrics']['output_token_ids'] == cold[model, label]['metrics']['output_token_ids']
                    if not result['same_as_own_cold_token_ids']: result.update(status='failed', error='切换请求后输出与自身冷启动不同。')
                save()
    adapter_results = {}
    for repeat in (False, True):
        for use_adapter in (False, True):
            label = 'adapter' if use_adapter else 'plain'
            result = run(f'isolation-v2-{label}-' + ('repeat' if repeat else 'cold'), 'bf16', 'short', 'adapter_isolation', use_adapter=use_adapter)
            if not repeat:
                adapter_results[use_adapter] = result
            elif result['status'] == adapter_results[use_adapter]['status'] == 'passed':
                result['same_as_own_cold_token_ids'] = result['metrics']['output_token_ids'] == adapter_results[use_adapter]['metrics']['output_token_ids']
                if not result['same_as_own_cold_token_ids']: result.update(status='failed', error='切换适配器后输出与自身冷启动不同。')
            save()
    report['adapter_recipe_distinct'] = adapter_results[True].get('inference_recipe_digest') != adapter_results[False].get('inference_recipe_digest')
    for model in ('bf16', 'weight_q4'):
        run('cancel-v2-' + model + '-prefill', model, 'long', 'cancel', cancel='prefill')
        run('cancel-v2-' + model + '-decode', model, 'long', 'cancel', cancel='decode')
        recovery = run('cancel-v2-' + model + '-recovery', model, 'short', 'cancel_recovery')
        baseline = next(case for case in report['cases'] if case['name'] == f'performance-v2-0-{model}-short')
        if recovery['status'] == baseline['status'] == 'passed':
            recovery['same_as_before_cancel_token_ids'] = recovery['metrics']['output_token_ids'] == baseline['metrics']['output_token_ids']
            if not recovery['same_as_before_cancel_token_ids']: recovery.update(status='failed', error='取消后的新请求输出改变。')
        save()
    report['performance_medians'] = []
    for model in ('bf16', 'weight_q4'):
        for size in ('short', 'medium', 'long'):
            cases = [case for case in report['cases'] if case['category'] == 'performance' and case['model'] == model and case['size'] == size and case['status'] == 'passed']
            if len(cases) == 3:
                report['performance_medians'].append({'model': model, 'size': size, 'prompt_tokens': cases[0]['metrics']['prompt_tokens'],
                    'repeats': 3, 'metrics': {field: statistics.median(case['metrics'][field] for case in cases) for field in NUMERIC_METRICS},
                    'actual_output_tokens': [case['metrics']['generation_tokens'] for case in cases], 'single_runs': [case['name'] for case in cases]})
    report['source_models_unchanged'] = all(snapshot_manifest(Path(bases[model, 'short']['model_path'])) == (bases[model, 'short']['model_manifest'], bases[model, 'short']['model_manifest_digest']) for model in ('bf16', 'weight_q4'))
    report['source_adapter_unchanged'] = snapshot_manifest(adapter) == adapter_manifest
    report.update(status='passed' if all(case['status'] == 'passed' for case in report['cases']) and report['adapter_recipe_distinct'] and report['source_models_unchanged'] and report['source_adapter_unchanged'] else 'partial', finished_at=time.time())
    save(); print(json.dumps({'status': report['status'], 'cases': len(report['cases']), 'report': str(evidence / 'report.json')}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
