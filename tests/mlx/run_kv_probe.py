"""固定输入、输出预算与顺序的真实 KV 对照；每项使用独立 worker 进程。"""

import argparse
import json
import math
import os
from pathlib import Path
import selectors
import signal
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from adapters.mlx_text.inference import PRESETS
from adapters.mlx_text.preflight import check
from workers.mlx_worker import sha256, snapshot_manifest, write_json

GENERATION = {'engine': 'mlx', 'device_id': 'apple-gpu', 'max_tokens': 128, 'temperature': 0, 'top_p': 1, 'seed': 0}
NUMERIC_METRICS = ('first_token_seconds', 'generation_wall_seconds', 'prompt_tps', 'generation_tps',
                   'model_load_seconds', 'mlx_generation_peak_bytes', 'peak_memory_bytes',
                   'process_rss_peak_bytes', 'final_kv_allocated_bytes', 'process_wall_seconds')


def token_ids(tokenizer, prompt):
    return tokenizer.apply_chat_template([{'role': 'user', 'content': prompt}], tokenize=True, add_generation_prompt=True)


def sized_prompt(tokenizer, budget):
    suffix = '\n请连续写不少于 200 字，介绍本地计算的用途、限制和验证方法。'
    low, high = 0, budget
    while low < high:
        middle = (low + high + 1) // 2
        prompt = '资料：\n' + '本地计算用于测试。\n' * middle + suffix
        if len(token_ids(tokenizer, prompt)) <= budget:
            low = middle
        else:
            high = middle - 1
    prompt = '资料：\n' + '本地计算用于测试。\n' * low + suffix
    assert budget - 16 <= len(token_ids(tokenizer, prompt)) <= budget
    return prompt


def process(snapshot_path, output, evidence, cancel_phase=None):
    """读取真实事件后发取消，不用睡眠推断模型已进入目标阶段。"""
    started = time.perf_counter()
    events, buffer, sent_at = [], b'', None
    with evidence.with_suffix('.stderr.log').open('wb') as stderr, evidence.with_suffix('.events.jsonl').open('wb') as event_file:
        child = subprocess.Popen([sys.executable, str(ROOT / 'workers/mlx_worker.py'), '--snapshot', str(snapshot_path), '--output-dir', str(output)],
                                 cwd=ROOT, stdout=subprocess.PIPE, stderr=stderr, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(child.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                if time.perf_counter() - started > 300:
                    os.killpg(child.pid, signal.SIGKILL)
                    raise AssertionError('worker 超过 300 秒，已终止本脚本创建的进程组。')
                for key, _ in selector.select(0.5):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    event_file.write(chunk)
                    event_file.flush()
                    buffer += chunk
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        events.append(event)
                        reached = (cancel_phase == 'prefill' and event.get('type') == 'phase' and event.get('phase') == 'prefilling') or (cancel_phase == 'decode' and event.get('type') == 'token')
                        if reached and sent_at is None:
                            sent_at = time.perf_counter()
                            child.send_signal(signal.SIGTERM)
            child.wait(timeout=10)
        finally:
            selector.close()
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=10)
        assert not buffer.strip(), '事件流没有完整结尾'
    ended = time.perf_counter()
    try:
        os.killpg(child.pid, 0)
    except ProcessLookupError:
        group_gone = True
    else:
        group_gone = False
    assert group_gone, 'worker 退出后其进程组仍存在'
    return events, {'pid': child.pid, 'returncode': child.returncode, 'process_wall_seconds': ended - started,
                    'process_group_gone': group_gone, 'cancel_phase': cancel_phase,
                    'cancel_to_exit_seconds': ended - sent_at if sent_at is not None else None}


def matrix(stage):
    """顺序在执行前完全固定；暖机不计入性能统计。"""
    output = []
    if stage in ('all', 'functional'):
        for size in ('short', 'medium', 'long'):
            for model in ('bf16', 'weight_q4'):
                for preset in PRESETS:
                    output.append((f'functional-{model}-{size}-{preset}', model, preset, size, 'functional'))
    if stage in ('all', 'performance'):
        for model in ('bf16', 'weight_q4'):
            output.append((f'warmup-{model}', model, 'default', 'long', 'warmup'))
        for repeat in range(3):
            for size in ('short', 'medium', 'long'):
                for model in ('bf16', 'weight_q4'):
                    presets = list(PRESETS)
                    for preset in presets[repeat:] + presets[:repeat]:
                        output.append((f'performance-{repeat}-{model}-{size}-{preset}', model, preset, size, 'performance'))
        for repeat in range(3):
            for model in ('bf16', 'weight_q4'):
                for preset in ('diagnostic_q4_2048', 'diagnostic_auto_512'):
                    output.append((f'diagnostic-{repeat}-{model}-{preset}', model, preset, 'long', 'diagnostic'))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bf16', type=Path, required=True)
    parser.add_argument('--weight-q4', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, help='可选的真实原权重 LoRA 目录，用于独立进程适配器切换隔离')
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--stage', choices=('functional', 'performance', 'quality', 'isolation', 'cancel', 'all'), default='functional')
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    from mlx_lm.utils import load_tokenizer
    paths = {'bf16': args.bf16.resolve(), 'weight_q4': args.weight_q4.resolve()}
    manifests = {name: snapshot_manifest(path) for name, path in paths.items()}
    adapter = args.adapter.resolve() if args.adapter else None
    adapter_manifest = snapshot_manifest(adapter) if adapter else None
    adapter_config = json.loads((adapter / 'adapter_config.json').read_text()) if adapter else None
    tokenizer = load_tokenizer(str(paths['bf16']), {'local_files_only': True, 'trust_remote_code': False})
    second_tokenizer = load_tokenizer(str(paths['weight_q4']), {'local_files_only': True, 'trust_remote_code': False})
    prompts = {name: sized_prompt(tokenizer, count) for name, count in [('short', 64), ('medium', 1024), ('long', 3584)]}
    for prompt in prompts.values():
        assert token_ids(tokenizer, prompt) == token_ids(second_tokenizer, prompt)
    presets = {**PRESETS, 'diagnostic_q4_2048': {'kv_precision': 'q4', 'prefill_step_size': 2048},
               'diagnostic_auto_512': {'kv_precision': 'auto', 'prefill_step_size': 512}}
    report = {'scope': '独立进程、本机 Qwen 两种权重的 KV 对照；不代表其它设备、模型、共享缓存或界面验收',
              'stage': args.stage, 'status': 'running', 'started_at': time.time(), 'generation': GENERATION, 'cases': [],
              'source_manifests': {name: {'entries': manifest[0], 'digest': manifest[1]} for name, manifest in manifests.items()},
              'prompts': {name: {'text': prompt, 'token_ids': token_ids(tokenizer, prompt), 'tokens': len(token_ids(tokenizer, prompt))} for name, prompt in prompts.items()},
              'source_sha256': {str(path.relative_to(ROOT)): sha256(path) for path in [ROOT / 'workers/mlx_worker.py', ROOT / 'adapters/mlx_text/inference.py', ROOT / 'adapters/mlx_text/preflight.py', Path(__file__)]}}

    def save():
        write_json(evidence / 'report.json', report)

    def run(name, model, preset, prompt, category, cancel_phase=None, use_adapter=False):
        result = {'name': name, 'model': model, 'preset': preset, 'category': category, 'adapter': use_adapter, 'status': 'running'}
        report['cases'].append(result)
        snapshot = {'attempt_id': name, 'operation': 'generate', 'model_path': str(paths[model]),
                    'model_manifest': manifests[model][0], 'model_manifest_digest': manifests[model][1],
                    'input': {'prompt': prompt}, 'runtime': {**GENERATION, **presets[preset]}}
        if use_adapter:
            assert adapter and model == 'bf16'
            snapshot.update(adapter_path=str(adapter), adapter_manifest=adapter_manifest[0], adapter_manifest_digest=adapter_manifest[1],
                            adapter_training_recipe_digest=adapter_config['training_recipe_digest'])
        output = evidence / name
        try:
            checked = check(snapshot, output)
            assert checked['can_submit'], checked
            snapshot.update(tokenization_recipe_digest=checked['tokenization_recipe_digest'], effective_config=checked['effective_config'])
            snapshot_path = evidence / (name + '.snapshot.json')
            write_json(snapshot_path, snapshot)
            result.update(prompt_tokens=checked['effective_config']['prompt_tokens'], inference_recipe_digest=checked['effective_config']['inference_recipe_digest'])
            save()
            print('KV 真实运行：' + name, flush=True)
            events, execution = process(snapshot_path, output, evidence / name, cancel_phase)
            result.update(execution=execution)
            if cancel_phase:
                assert execution['returncode'] == 130 and execution['cancel_to_exit_seconds'] is not None
                assert events[-1]['type'] == 'error' and events[-1]['code'] == 'CANCELLED'
                assert not any(event['type'] == 'completed' for event in events)
                result.update(status='passed', no_completed=True)
            else:
                assert execution['returncode'] == 0 and events[-1]['type'] == 'completed', events[-1:]
                for artifact in events[-1]['artifacts']:
                    assert sha256(output / artifact['path']) == artifact['sha256']
                effective = json.loads((output / 'effective-config.json').read_text())
                metrics = json.loads((output / 'metrics.json').read_text())
                cache = json.loads((output / 'cache-observation.json').read_text())
                metrics['process_wall_seconds'] = execution['process_wall_seconds']
                assert effective['inference_recipe_digest'] == snapshot['effective_config']['inference_recipe_digest']
                assert effective['inference_recipe'] == snapshot['effective_config']['inference_recipe']
                assert all(effective[field] == value for field, value in snapshot['runtime'].items())
                assert effective['prompt_tokens'] == len(token_ids(tokenizer, prompt)) == metrics['prompt_tokens']
                assert 0 < metrics['generation_tokens'] <= GENERATION['max_tokens']
                assert all(isinstance(metrics[field], (int, float)) and math.isfinite(metrics[field]) and metrics[field] > 0 for field in NUMERIC_METRICS)
                assert metrics['prefix_cache_hit_rate'] is None and effective['prefix_cache'] == 'disabled'
                assert cache['initial']['initially_empty'] and cache['initial']['layer_count'] == 24
                assert all(layer['empty'] and layer['offset'] == 0 and layer['nbytes'] == 0 for layer in cache['initial']['layers'])
                expected_class = 'QuantizedKVCache' if presets[preset]['kv_precision'] == 'q4' else 'KVCache'
                assert cache['final']['layer_count'] == 24 and all(layer['class'] == expected_class for layer in cache['final']['layers'])
                assert cache['final']['total_allocated_bytes'] == metrics['final_kv_allocated_bytes']
                if expected_class == 'QuantizedKVCache':
                    assert all(layer['bits'] == 4 and layer['group_size'] == 64 for layer in cache['final']['layers'])
                result.update(status='passed', metrics=metrics, output_text=(output / 'result.txt').read_text(),
                              cache_class=expected_class, cache_dtype=cache['final']['layers'][0]['keys'], initially_empty=True)
        except Exception as error:
            result.update(status='failed', error=repr(error))
        save()
        print(json.dumps({'name': name, 'status': result['status'], 'error': result.get('error')}, ensure_ascii=False), flush=True)
        return result

    frozen_matrix = matrix(args.stage)
    report['fixed_order'] = frozen_matrix
    save()
    for name, model, preset, size, category in frozen_matrix:
        run(name, model, preset, prompts[size], category)
    if args.stage in ('all', 'quality'):
        quality = [('arithmetic', '只回答数字：17 加 25 等于多少？', '42'),
                   ('extract', '订单编号为 7391，金额为 82。只回答订单编号数字。', '7391'),
                   ('json', '只输出一个 JSON 对象，键名为 answer，值为整数 7。不要写其他内容。', {'answer': 7})]
        line = '普通记录：今天需要检查本地资料。\n'
        retrieval = '唯一的门禁代号是 5832。\n\n只回答门禁代号的四位数字。'
        count = 0
        while len(token_ids(tokenizer, line * (count + 1) + retrieval)) <= 3584:
            count += 1
        for name, prefix, suffix in [('head', '', line * count), ('middle', line * (count // 2), line * (count - count // 2)), ('tail', line * count, '')]:
            quality.append((name, prefix + '唯一的门禁代号是 5832。\n' + suffix + '\n只回答门禁代号的四位数字。', '5832'))
        for model in paths:
            for label, prompt, expected in quality:
                comparable = []
                for preset in PRESETS:
                    result = run(f'quality-{model}-{label}-{preset}', model, preset, prompt, 'quality')
                    if result['status'] == 'passed':
                        answer = result['output_text'].strip()
                        try:
                            correct = json.loads(answer) == expected if isinstance(expected, dict) else answer == expected
                        except ValueError:
                            correct = False
                        result.update(answer_correct=correct, expected_answer=expected)
                        comparable.append(result)
                if len(comparable) == 3:
                    comparable[-1]['auto_chunking_token_ids_equal'] = comparable[0]['metrics']['output_token_ids'] == comparable[-1]['metrics']['output_token_ids']
                save()
    if args.stage in ('all', 'isolation'):
        for model in paths:
            for preset in ('default', 'low_memory'):
                cold = {}
                for label, code in [('A', '3471'), ('B', '9265')]:
                    prompt = '同一段公开前缀：本次只读取末尾明确给出的数字，不读取其它运行。\n' + f'本次数字为 {code}。只回答本次数字。'
                    cold[label] = (prompt, run(f'isolation-{model}-{preset}-{label}-cold', model, preset, prompt, 'isolation'))
                for label in ('A', 'B'):
                    prompt, baseline = cold[label]
                    repeat = run(f'isolation-{model}-{preset}-{label}-repeat', model, preset, prompt, 'isolation')
                    if baseline['status'] == repeat['status'] == 'passed':
                        repeat['same_as_own_cold_token_ids'] = baseline['metrics']['output_token_ids'] == repeat['metrics']['output_token_ids']
                        repeat['different_processes'] = baseline['execution']['pid'] != repeat['execution']['pid']
                        if not repeat['same_as_own_cold_token_ids'] or not repeat['different_processes']:
                            repeat.update(status='failed', error='独立请求与其自身冷启动结果不一致。')
                    save()
        report['adapter_isolation'] = 'not_run' if adapter is None else 'running'
        if adapter:
            report['adapter_manifest'] = {'entries': adapter_manifest[0], 'digest': adapter_manifest[1]}
            for preset in ('default', 'low_memory'):
                plain = run(f'adapter-isolation-{preset}-plain-cold', 'bf16', preset, prompts['short'], 'adapter_isolation')
                adapted = run(f'adapter-isolation-{preset}-adapted-cold', 'bf16', preset, prompts['short'], 'adapter_isolation', use_adapter=True)
                plain_repeat = run(f'adapter-isolation-{preset}-plain-repeat', 'bf16', preset, prompts['short'], 'adapter_isolation')
                adapted_repeat = run(f'adapter-isolation-{preset}-adapted-repeat', 'bf16', preset, prompts['short'], 'adapter_isolation', use_adapter=True)
                for baseline, repeat in ((plain, plain_repeat), (adapted, adapted_repeat)):
                    if baseline['status'] == repeat['status'] == 'passed':
                        repeat['same_as_own_cold_token_ids'] = baseline['metrics']['output_token_ids'] == repeat['metrics']['output_token_ids']
                        if not repeat['same_as_own_cold_token_ids']:
                            repeat.update(status='failed', error='切换适配器后的请求与其自身冷启动结果不一致。')
                if plain['status'] == adapted['status'] == 'passed':
                    adapted['distinct_adapter_recipe'] = plain['inference_recipe_digest'] != adapted['inference_recipe_digest']
                    if not adapted['distinct_adapter_recipe']:
                        adapted.update(status='failed', error='不同适配器的推理身份没有区分。')
                save()
            report['adapter_isolation'] = 'passed' if all(case['status'] == 'passed' for case in report['cases'] if case['category'] == 'adapter_isolation') else 'partial'
    if args.stage in ('all', 'cancel'):
        for model in paths:
            run(f'cancel-{model}-prefill', model, 'diagnostic_auto_512', prompts['long'], 'cancel', 'prefill')
            run(f'cancel-{model}-decode', model, 'low_memory', prompts['long'], 'cancel', 'decode')
            run(f'after-cancel-{model}', model, 'low_memory', prompts['short'], 'cancel_recovery')
    report['performance_medians'] = []
    groups = {}
    for case in report['cases']:
        if case['category'] in ('performance', 'diagnostic') and case['status'] == 'passed':
            groups.setdefault((case['model'], case['preset'], case['prompt_tokens']), []).append(case)
    for (model, preset, size), cases in groups.items():
        report['performance_medians'].append({'model': model, 'preset': preset, 'prompt_tokens': size, 'repeats': len(cases),
                                              'metrics': {field: statistics.median(case['metrics'][field] for case in cases) for field in NUMERIC_METRICS},
                                              'actual_output_tokens': [case['metrics']['generation_tokens'] for case in cases],
                                              'single_runs': [case['name'] for case in cases]})
    report['source_unchanged'] = all(snapshot_manifest(path) == manifests[name] for name, path in paths.items())
    if adapter:
        report['adapter_unchanged'] = snapshot_manifest(adapter) == adapter_manifest
        report['source_unchanged'] = report['source_unchanged'] and report['adapter_unchanged']
    report['status'] = 'passed' if report['source_unchanged'] and all(case['status'] == 'passed' for case in report['cases']) else 'partial'
    quality_cases = [case for case in report['cases'] if case['category'] == 'quality']
    if quality_cases:
        report['quality_summary'] = {'total': len(quality_cases), 'correct': sum(case.get('answer_correct') is True for case in quality_cases),
                                     'auto_chunking_differences': [case['name'] for case in quality_cases if case.get('auto_chunking_token_ids_equal') is False]}
        report['quality_status'] = 'passed' if all(case.get('answer_correct') for case in quality_cases) else 'partial'
        if report['quality_status'] != 'passed':
            report['status'] = 'partial'
    report['quality_boundary'] = 'answer_correct 为独立固定题结果；运行 passed 仅表示执行与缓存合同通过，不表示回答正确。'
    report['finished_at'] = time.time()
    save()
    print(json.dumps({'status': report['status'], 'cases': len(report['cases']), 'report': str(evidence / 'report.json')}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
