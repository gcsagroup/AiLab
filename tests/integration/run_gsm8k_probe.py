"""真实停止、冷重开、继续与已有 4-bit 模型验收。"""
import argparse, json, sys, time, uuid
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R), str(R / 'services/control')]
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.service import Settings
from ailab_control.assets import file_hash
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence', type=Path, required=True)
parser.add_argument('--source-probe', type=Path, required=True, help='已通过真实双模型试跑的 report.json')
parser.add_argument('--quantized', type=Path, required=True, help='已有 Qwen2.5-0.5B MLX 4-bit 权重')
runtime = parser.add_mutually_exclusive_group(required=True)
runtime.add_argument('--worker-python', type=Path)
runtime.add_argument('--bundled-worker', type=Path)
args = parser.parse_args()
E = args.evidence.resolve()
E.mkdir(exist_ok=False, parents=True)
old = json.loads(args.source_probe.read_text())
assert old['status'] == 'passed'
data = args.source_probe.resolve().parent / 'data'
quant = args.quantized.resolve(strict=True)
s = Settings(data_dir=data, token='isolated-gsm8k-verification', import_roots=[quant], export_roots=[E], worker_python=args.worker_python.resolve() if args.worker_python else None, bundled_worker=args.bundled_worker.resolve() if args.bundled_worker else None, worker_script=R / 'workers/mlx_worker.py', preflight_script=R / 'adapters/mlx_text/preflight.py')
r = {'status': 'running', 'data': str(data)}

def save():
    (E / 'report.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n')

def call(method, path, body=None):
    x = c.request(method, '/api/v1' + path, json=body, headers={'Idempotency-Key': uuid.uuid4().hex})
    assert x.status_code == 200, (path, x.status_code, x.text)
    return x.json()

def submit(t):
    check = call('POST', f"/tasks/{t['id']}/preflight", {'draft_revision': t['draft_revision']})
    assert check['can_submit'], check
    return call('POST', f"/tasks/{t['id']}/attempts", {'preflight_id': check['id'], 'expected_revision': t['draft_revision']})

def wait(a):
    start = time.monotonic()
    while True:
        a = call('GET', '/attempts/' + a['id'])
        if a['state'] in ['failed', 'succeeded', 'cancelled']:
            return a
        assert time.monotonic() - start < 1200, a
        time.sleep(0.25)
try:
    with TestClient(create_app(s), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer isolated-gsm8k-verification'}) as c:
        task = call('POST', '/evaluations/capability', {'project_id': old['project']['id'], 'model_id': old['models'][0]['id'], 'candidate_model_id': old['models'][1]['id'], 'benchmark': 'gsm8k-smoke', 'name': '真实停止后继续'})
        a = submit(task)
        start = time.monotonic()
        while True:
            a = call('GET', '/attempts/' + a['id'])
            if a.get('evaluation_progress', {}).get('baseline', {}).get('count', 0) >= 3:
                break
            assert a['state'] not in ['succeeded', 'failed', 'cancelled'] and time.monotonic() - start < 300, a
            time.sleep(0.1)
        call('POST', f"/attempts/{a['id']}/cancel", {'expected_state_version': a['state_version']})
        a = wait(a)
        assert a['state'] == 'cancelled', a
        r['cancelled'] = a
        save()
    with TestClient(create_app(s), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer isolated-gsm8k-verification'}) as c:
        resumed = call('POST', f"/evaluations/{a['id']}/continue", {})
        r['continued_task'] = resumed
        save()
        completed = wait(submit(resumed))
        assert completed['state'] == 'succeeded', completed
        record = call('GET', '/evaluations/' + completed['id'])
        r['continued'] = record
        full = json.loads((data / 'runs' / completed['id'] / 'output/evaluation-report.json').read_text())
        assert full['independent_loads']['baseline']['resumed_samples'] == a['evaluation_progress']['baseline']['count']
        before = [json.loads(line) for line in (data / 'runs' / a['id'] / 'output/baseline/answers.jsonl').read_text().splitlines()]
        after = [json.loads(line) for line in (data / 'runs' / completed['id'] / 'output/baseline/answers.jsonl').read_text().splitlines()]
        count = a['evaluation_progress']['baseline']['count']
        assert before[:count] == after[:count]
        assert len(after) == 12 and len({x['sample_id'] for x in after}) == 12
        page = call('GET', f"/evaluations/{completed['id']}?sample_offset=10&sample_limit=10&sample_filter=all")
        assert len(page['report']['samples']) == 2 and page['report']['sample_page']['total'] == 12
        target = E / 'export'
        target.mkdir()
        grant = call('POST', '/export-grants', {'path': str(target)})
        plan = call('POST', '/exports/prepare', {'project_id': old['project']['id'], 'object_type': 'report', 'object_id': completed['id'], 'target_dir': str(target), 'grant_id': grant['grant_id']})
        assert plan['can_export'], plan
        export = call('POST', '/exports', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']})
        while export['state'] not in ['succeeded', 'failed', 'cancelled']:
            time.sleep(0.1)
            export = call('GET', '/exports/' + export['id'])
        assert export['state'] == 'succeeded', export
        for f in plan['files']:
            p = Path(export['verified_path']) / f['path']
            assert p.stat().st_size == f['size'] and file_hash(p) == f['sha256']
        r.update(export=export, confirmed_answers_unchanged=True, cold_restart=True)
        save()
        plan = call('POST', '/models/import-plans', {'project_id': old['project']['id'], 'name': '已有0.5B 4-bit', 'path': str(quant)})
        m = call('POST', '/models/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']})
        r['quantized_model'] = m
        save()
        qt = call('POST', '/evaluations/capability', {'project_id': old['project']['id'], 'model_id': m['id'], 'candidate_model_id': old['models'][0]['id'], 'benchmark': 'gsm8k-smoke', 'name': '已有4-bit作为基线'})
        qa = wait(submit(qt))
        assert qa['state'] == 'succeeded', qa
        r['quantized_evaluation'] = call('GET', '/evaluations/' + qa['id'])
        r['status'] = 'passed'
        save()
except Exception as ex:
    r.update(status='failed', error=str(ex))
    save()
    raise
print('停止、冷重开、恢复、分页、导出及 4-bit 真实运行通过', flush=True)
