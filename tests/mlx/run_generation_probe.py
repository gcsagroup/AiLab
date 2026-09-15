"""冻结输入后实算上下文、停止序列和流式；每个样例为新的独立模型进程。"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text.preflight import check
from workers.mlx_worker import sha256, snapshot_manifest, write_json
from run_kv_probe import process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    reference, evidence = args.reference.resolve(), args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), ROOT / 'workers/mlx_worker.py', *(ROOT / 'adapters/mlx_text' / name for name in ('generation.py', 'inference.py', 'preflight.py'))]
    bases = {model: json.loads((reference / ('quality-' + model + '-extract-default.snapshot.json')).read_text()) for model in ('bf16', 'weight_q4')}
    cases = [
        {'label': 'stream-on', 'runtime': {}},
        {'label': 'stream-off', 'runtime': {'stream': False}},
        {'label': 'stop-on', 'runtime': {'stop': ['39']}},
        {'label': 'stop-off', 'runtime': {'stop': ['39'], 'stream': False}},
        {'label': 'stop-empty', 'runtime': {'stop': ['7']}},
        {'label': 'stop-not-found', 'runtime': {'stop': [' 7391 ']}},
        {'label': 'exact-context', 'runtime': {'context_limit': 128, 'max_tokens': 78}},
    ]
    plan = {'schema_version': 'generation-fields-plan-v1', 'scope': '固定Qwen两种权重，单条输入，不裁剪历史、不控制模型思考行为',
            'sources': {str(p.relative_to(ROOT)): sha256(p) for p in sources}, 'reference_report_sha256': sha256(reference / 'report.json'),
            'input': '订单编号为 7391，金额为 82。只回答订单编号数字。', 'defaults': {'context_limit': 4096, 'overflow': 'reject', 'stop': [], 'stream': True, 'thinking': 'default'},
            'unchanged': {'seed': 0, 'temperature': 0, 'top_p': 1, 'max_tokens': 128, 'kv_precision': 'auto', 'prefill_step_size': 2048},
            'cases': cases, 'negative_cases': ['context-total-129-over-128', 'stop-changed-after-preflight'],
            'cancel': '两种权重 stream=false，真实 Prefill 阶段事件后取消；另在CPU驱动验证Decode取消',
            'criteria': '默认结果为7391；非流式结果与默认字节和词元相同、没有token事件；39跨模型文本块命中后只保留7且实际词元减少；7命中后空结果；带空格的序列不得自动去空格；上下文恰好128通过、129拒绝'}
    write_json(evidence / 'frozen-plan.json', plan)
    report = {'plan_sha256': sha256(evidence / 'frozen-plan.json'), 'status': 'running', 'started_at': time.time(), 'cases': [], 'negative_cases': []}
    def save(): write_json(evidence / 'report.json', report)
    def freeze(snapshot, output, path):
        checked = check(snapshot, output)
        assert checked['can_submit']
        snapshot.update(tokenization_recipe_digest=checked['tokenization_recipe_digest'], effective_config=checked['effective_config'])
        write_json(path, snapshot)
        return checked
    for model, base in bases.items():
        baseline = None
        for case in cases:
            name = model + '-' + case['label']
            result = {'name': name, 'status': 'running'}; report['cases'].append(result)
            snapshot = copy.deepcopy(base); snapshot['attempt_id'] = name
            snapshot['runtime'].update(plan['defaults']); snapshot['runtime'].update(case['runtime'])
            output, path = evidence / name, evidence / (name + '.snapshot.json')
            try:
                assert all(sha256(ROOT / p) == h for p, h in plan['sources'].items()), '执行期间源码改变'
                checked = freeze(snapshot, output, path)
                result['preflight'] = checked
                events, execution = process(path, output, evidence / name)
                result['execution'] = execution
                assert execution['returncode'] == 0 and events[-1]['type'] == 'completed', events[-1:]
                for artifact in events[-1]['artifacts']:
                    assert sha256(output / artifact['path']) == artifact['sha256']
                effective = json.loads((output / 'effective-config.json').read_text())
                metrics = json.loads((output / 'metrics.json').read_text())
                text = (output / 'result.txt').read_text()
                token_events = [event for event in events if event['type'] == 'token']
                result.update(output_text=text, output_sha256=sha256(output / 'result.txt'), metrics=metrics, token_event_count=len(token_events), effective_config=effective)
                assert effective['inference_recipe'] == checked['effective_config']['inference_recipe']
                assert effective['context_observation'] == checked['check_report'] and effective['thinking_supported'] is False
                assert effective['cache_observation']['initial']['initially_empty'] and not metrics['input_truncated']
                if snapshot['runtime']['stream']:
                    assert ''.join(event['text'] for event in token_events) == text
                else:
                    assert not token_events
                if case['label'] == 'stream-on':
                    assert text == '7391'; baseline = result
                elif case['label'] in ('stream-off', 'stop-not-found', 'exact-context'):
                    assert text == baseline['output_text'] and metrics['output_token_ids'] == baseline['metrics']['output_token_ids']
                elif case['label'] in ('stop-on', 'stop-off'):
                    assert text == '7' and metrics['finish_reason'] == 'stop_sequence' and metrics['matched_stop_index'] == 0
                    assert metrics['generation_tokens'] < baseline['metrics']['generation_tokens']
                    assert not any('3' in e['text'] or '9' in e['text'] for e in token_events)
                elif case['label'] == 'stop-empty':
                    assert text == '' and metrics['finish_reason'] == 'stop_sequence' and metrics['generation_tokens'] == 1
                if case['label'] == 'exact-context':
                    assert effective['context_observation']['total_token_budget'] == 128
                result['status'] = 'passed'
            except Exception as error:
                result.update(status='failed', error=repr(error))
            save(); print(json.dumps({'name': name, 'status': result['status'], 'error': result.get('error')}, ensure_ascii=False), flush=True)
        for negative in plan['negative_cases']:
            result = {'name': model + '-' + negative, 'status': 'running'}; report['negative_cases'].append(result)
            snapshot = copy.deepcopy(base); snapshot['runtime'].update(plan['defaults'])
            name = result['name']; path, output = evidence / (name + '.snapshot.json'), evidence / name
            try:
                if negative == 'context-total-129-over-128':
                    snapshot['runtime'].update(context_limit=128, max_tokens=79)
                    write_json(path, snapshot)
                    child = subprocess.run([sys.executable, str(ROOT / 'adapters/mlx_text/preflight.py'), '--snapshot', str(path), '--output-dir', str(output)], capture_output=True, text=True, timeout=60)
                    value = json.loads(child.stdout); write_json(evidence / (name + '.preflight.json'), value)
                    result.update(returncode=child.returncode, preflight=value)
                    assert child.returncode == 1 and value['blocking'][0]['code'] == 'CONTEXT_TOO_LONG'
                    assert value['check_report']['total_token_budget'] == 129 and not value['check_report']['input_truncated'] and not output.exists()
                else:
                    freeze(snapshot, output, path)
                    snapshot['runtime']['stop'] = ['39']; write_json(path, snapshot)
                    events, execution = process(path, output, evidence / name)
                    result['execution'] = execution
                    assert execution['returncode'] == 1 and events[-1]['code'] == 'INFERENCE_IDENTITY_CHANGED'
                    assert not any(e['type'] in ('token', 'completed') for e in events) and not (output / 'result.txt').exists()
                result['status'] = 'passed'
            except Exception as error:
                result.update(status='failed', error=repr(error))
            save()
        name = model + '-stream-off-cancel'
        result = {'name': name, 'status': 'running', 'category': 'cancel'}; report['cases'].append(result)
        try:
            snapshot = json.loads((reference.parent / 'functional-20260910-v1' / ('functional-' + model + '-long-default.snapshot.json')).read_text())
            snapshot['runtime'].update(plan['defaults']); snapshot['runtime']['stream'] = False
            path, output = evidence / (name + '.snapshot.json'), evidence / name
            freeze(snapshot, output, path)
            events, execution = process(path, output, evidence / name, cancel_phase='prefill')
            result['execution'] = execution
            assert execution['returncode'] == 130 and execution['cancel_to_exit_seconds'] is not None
            assert events[-1]['code'] == 'CANCELLED' and not any(e['type'] in ('token', 'completed') for e in events)
            assert not (output / 'result.txt').exists()
            result['status'] = 'passed'
        except Exception as error:
            result.update(status='failed', error=repr(error))
        save()
    report['source_models_unchanged'] = all(snapshot_manifest(Path(base['model_path'])) == (base['model_manifest'], base['model_manifest_digest']) for base in bases.values())
    report['source_unchanged'] = all(sha256(ROOT / p) == h for p, h in plan['sources'].items())
    report.update(status='passed' if report['source_models_unchanged'] and report['source_unchanged'] and all(r['status'] == 'passed' for r in report['cases'] + report['negative_cases']) else 'partial', finished_at=time.time())
    save(); print(json.dumps({'status': report['status'], 'report': str(evidence / 'report.json')}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    raise SystemExit(main())
