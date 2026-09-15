"""真实 HTTP 参数→检查→独立模型→封存正文→作品配方闭环；不代替界面验收。"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/control'))
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.assets import file_hash, verify_manifest
from ailab_control.service import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--worker-python', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    source, evidence = args.model.resolve(), args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / 'services/control/ailab_control' / name for name in ('api.py', 'service.py', 'storage.py')]
    paths += [ROOT / 'adapters/mlx_text' / name for name in ('generation.py', 'preflight.py', 'inference.py')]
    paths += [ROOT / 'workers/mlx_worker.py', Path(__file__)]
    plan = {'schema_version': 'generation-http-plan-v1', 'source_sha256': {str(p.relative_to(ROOT)): file_hash(p) for p in paths},
            'fixed_cases': [{'name': '流式完整正文', 'stream': True, 'stop': [], 'expected': '7391'},
                            {'name': '非流式完整正文', 'stream': False, 'stop': [], 'expected': '7391'},
                            {'name': '非流式跨块停止', 'stream': False, 'stop': ['39'], 'expected': '7'}],
            'input': '订单编号为 7391，金额为 82。只回答订单编号数字。',
            'runtime': {'context_limit': 128, 'max_tokens': 78, 'overflow': 'reject', 'thinking': 'default', 'temperature': 0, 'top_p': 1, 'seed': 0},
            'negative': '同一输入总预算128→129在提交前拒绝，无attempt'}
    def write(name, value):
        (evidence / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    write('frozen-plan.json', plan)
    report = {'status': 'running', 'plan_sha256': file_hash(evidence / 'frozen-plan.json'), 'cases': [], 'started_at': time.time()}
    def save(): write('report.json', report)
    app = create_app(Settings(data_dir=evidence / 'data', token='isolated-generation-probe', import_roots=[source],
                              worker_python=args.worker_python.absolute(), worker_script=ROOT / 'workers/mlx_worker.py'))
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer isolated-generation-probe'}) as client:
        def call(method, path, body=None):
            response = client.request(method, '/api/v1' + path, json=body, headers={'Idempotency-Key': uuid.uuid4().hex})
            assert response.status_code == 200, {'path': path, 'status': response.status_code, 'response': response.json()}
            return response.json()
        project = call('POST', '/projects', {'name': '正式HTTP生成字段验收'})
        imported = call('POST', '/models/import-plans', {'project_id': project['id'], 'path': str(source), 'name': '固定 Qwen 实算'})
        model = call('POST', '/models/imports', {'plan_id': imported['id'], 'manifest_digest': imported['manifest_digest']})
        report['model'] = model
        for case in plan['fixed_cases']:
            result = {'case': case, 'status': 'running'}; report['cases'].append(result)
            try:
                assert all(file_hash(ROOT / path) == checksum for path, checksum in plan['source_sha256'].items()), '运行前源码身份改变'
                task = call('POST', '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': 'generate', 'name': case['name']})
                draft = copy.deepcopy(task['draft']); draft['model_id'] = model['id']; draft['input']['prompt'] = plan['input']
                draft['runtime'].update(plan['runtime']); draft['runtime'].update(stream=case['stream'], stop=case['stop'])
                task = call('PATCH', '/tasks/' + task['id'] + '/draft', {'expected_revision': 1, 'draft': draft})
                checked = call('POST', '/tasks/' + task['id'] + '/preflight', {'draft_revision': task['draft_revision']})
                assert checked['can_submit'] and checked['check_report']['total_token_budget'] == 128
                attempt = call('POST', '/tasks/' + task['id'] + '/attempts', {'preflight_id': checked['id'], 'expected_revision': task['draft_revision']})
                result.update(task_id=task['id'], attempt_id=attempt['id'], preflight=checked)
                save(); print('正式 HTTP 实算：' + case['name'] + ' · ' + attempt['id'], flush=True)
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    attempt = call('GET', '/attempts/' + attempt['id'])
                    if attempt['state'] in ('succeeded', 'failed', 'cancelled'):
                        break
                    time.sleep(0.1)
                if attempt['state'] not in ('succeeded', 'failed', 'cancelled'):
                    call('POST', '/attempts/' + attempt['id'] + '/cancel', {'expected_state_version': attempt['state_version']})
                    raise AssertionError('本脚本已请求取消超过120秒的执行')
                assert attempt['state'] == 'succeeded' and attempt['output_text'] == case['expected'], attempt
                assert attempt['snapshot']['runtime'] == draft['runtime']
                effective = attempt['effective_config']
                assert effective['stream'] is case['stream'] and effective['stop'] == case['stop'] and effective['thinking_supported'] is False
                assert effective['inference_recipe_digest'] == checked['effective_config']['inference_recipe_digest']
                events = call('GET', '/attempts/' + attempt['id'] + '/events')['items']
                tokens = [event for event in events if event['type'] == 'token']
                assert bool(tokens) is case['stream']
                work = call('POST', '/works', {'attempt_id': attempt['id'], 'name': case['name']})
                assert work['text'] == case['expected'] and work['recipe']['runtime'] == draft['runtime']
                artifact = app.state.service.store.get('artifact', work['artifact_id'])
                assert Path(artifact['storage_path']).read_text() == case['expected'] and file_hash(Path(artifact['storage_path'])) == artifact['sha256']
                reloaded = call('POST', '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': 'generate', 'name': case['name'] + '配方重载'})
                reloaded_draft = copy.deepcopy(reloaded['draft'])
                reloaded_draft.update(model_id=model['id'], input=work['recipe']['input'], runtime=work['recipe']['runtime'])
                reloaded = call('PATCH', '/tasks/' + reloaded['id'] + '/draft', {'expected_revision': 1, 'draft': reloaded_draft})
                rechecked = call('POST', '/tasks/' + reloaded['id'] + '/preflight', {'draft_revision': reloaded['draft_revision']})
                assert rechecked['can_submit'] and rechecked['effective_config']['inference_recipe_digest'] == effective['inference_recipe_digest']
                result.update(status='passed', attempt=attempt, work=work, token_events=len(tokens), artifact_sha256=artifact['sha256'], reloaded_task_id=reloaded['id'])
            except Exception as error:
                result.update(status='failed', error=repr(error))
            save()
        negative = call('POST', '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': 'generate', 'name': '实际超预算拒绝'})
        negative['draft']['model_id'] = model['id']; negative['draft']['input']['prompt'] = plan['input']
        negative['draft']['runtime'].update(plan['runtime']); negative['draft']['runtime']['max_tokens'] = 79
        negative = call('PATCH', '/tasks/' + negative['id'] + '/draft', {'expected_revision': 1, 'draft': negative['draft']})
        checked = call('POST', '/tasks/' + negative['id'] + '/preflight', {'draft_revision': negative['draft_revision']})
        assert not checked['can_submit'] and checked['check_report']['total_token_budget'] == 129
        rejected = client.post('/api/v1/tasks/' + negative['id'] + '/attempts', json={'preflight_id': checked['id'], 'expected_revision': negative['draft_revision']}, headers={'Idempotency-Key': 'over-budget'})
        assert rejected.status_code == 409
        assert not [a for a in app.state.service.store.list('attempt') if a['task_id'] == negative['id']]
        report['negative'] = {'preflight': checked, 'submit_status': rejected.status_code, 'response': rejected.json(), 'attempt_count': 0}
        # 正式公开模型计划不暴露文件系统清单；从本脚本自己的控制实例核验原封存记录。
        verify_manifest(source, app.state.service.store.get('model', model['id'])['manifest'])
        report['source_model_unchanged'] = True
    report['sources_unchanged'] = all(file_hash(ROOT / path) == checksum for path, checksum in plan['source_sha256'].items())
    report.update(status='passed' if report['sources_unchanged'] and all(c['status'] == 'passed' for c in report['cases']) else 'partial', finished_at=time.time())
    save(); print(json.dumps({'status': report['status'], 'report': str(evidence / 'report.json')}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
