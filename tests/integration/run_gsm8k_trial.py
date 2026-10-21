"""隔离库真实评测，使用正式接口；不改模型文件。"""
import argparse, json, sys, time, uuid
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(R), str(R / 'services/control')]
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.service import Settings
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--evidence', type=Path, required=True)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--candidate', type=Path, required=True)
p.add_argument('--mode', choices=['gsm8k-smoke', 'gsm8k-full'], default='gsm8k-smoke')
runtime = p.add_mutually_exclusive_group(required=True)
runtime.add_argument('--worker-python', type=Path)
runtime.add_argument('--bundled-worker', type=Path)
a = p.parse_args()
e = a.evidence.resolve()
e.mkdir(exist_ok=False, parents=True)
inputs = [a.baseline.resolve(strict=True), a.candidate.resolve(strict=True)]
s = Settings(data_dir=e / 'data', token='isolated-gsm8k-trial', import_roots=inputs, worker_python=a.worker_python.resolve() if a.worker_python else None, bundled_worker=a.bundled_worker.resolve() if a.bundled_worker else None, worker_script=R / 'workers/mlx_worker.py', preflight_script=R / 'adapters/mlx_text/preflight.py')
r = {'status': 'running'}

def save():
    (e / 'report.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n')
with TestClient(create_app(s), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer isolated-gsm8k-trial'}) as c:

    def call(method, path, body=None):
        x = c.request(method, '/api/v1' + path, json=body, headers={'Idempotency-Key': uuid.uuid4().hex})
        assert x.status_code == 200, (path, x.status_code, x.text)
        return x.json()
    try:
        project = call('POST', '/projects', {'name': 'GSM8K 真实验收'})
        models = []
        for i, source in enumerate(inputs):
            plan = call('POST', '/models/import-plans', {'project_id': project['id'], 'name': ['验收基线', '验收候选'][i], 'path': str(source)})
            models.append(call('POST', '/models/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']}))
        r.update(project=project, models=models)
        save()
        task = call('POST', '/evaluations/capability', {'project_id': project['id'], 'model_id': models[0]['id'], 'candidate_model_id': models[1]['id'], 'benchmark': a.mode})
        r['task'] = task
        save()
        check = call('POST', f"/tasks/{task['id']}/preflight", {'draft_revision': 1})
        r['check'] = check
        save()
        assert check['can_submit'], check
        attempt = call('POST', f"/tasks/{task['id']}/attempts", {'preflight_id': check['id'], 'expected_revision': 1})
        r['attempt_id'] = attempt['id']
        save()
        start = time.monotonic()
        while True:
            attempt = call('GET', '/attempts/' + attempt['id'])
            r['attempt'] = attempt
            save()
            if attempt['state'] in ['succeeded', 'failed', 'cancelled']:
                break
            assert time.monotonic() - start < 24 * 3600
            time.sleep(2)
        assert attempt['state'] == 'succeeded', attempt
        r['evaluation'] = call('GET', '/evaluations/' + attempt['id'])
        metrics = r['evaluation']['report']['benchmark_metrics']
        assert all((v['total'] == (1319 if a.mode == 'gsm8k-full' else 12) for v in metrics.values()))
        r['status'] = 'passed'
        save()
        print('passed', metrics)
    except Exception as ex:
        r.update(status='failed', error=str(ex))
        save()
        raise
