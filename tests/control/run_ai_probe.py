"""真实本地建议验收：保留原回答，严格校验后显式应用并撤销；不验证界面。"""

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
from ailab_control.service import Settings


CASES = [
    {'name': '生成输出 128 改 64', 'operation': 'generate', 'field': 'runtime.max_tokens', 'before': 128, 'after': 64,
     'instruction': '请只把最大输出 token 从 128 调整为 64，其他字段保持原样。给出一条建议并说明影响。'},
    {'name': '生成输出 256 改 80', 'operation': 'generate', 'field': 'runtime.max_tokens', 'before': 256, 'after': 80,
     'instruction': '这次只生成简短摘要，请将最大输出 token 改为 80。不要改提示词。'},
    {'name': '训练步数 12 改 6', 'operation': 'train', 'field': 'runtime.steps', 'before': 12, 'after': 6,
     'instruction': '先做一轮较短的训练检查，请只将训练步数从 12 减少为 6，序列长度和其他字段保持不变。'},
]


def run(source, output, worker_python):
    output.mkdir(parents=True, exist_ok=False)
    report = {'scope': '真实本地模型回答及测试客户端显式应用、撤销；不代表界面验收或专业建议质量',
              'started_at': time.time(), 'cases': [], 'status': 'running'}

    def save():
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    app = create_app(Settings(data_dir=output / 'data', token='isolated-ai-probe', import_roots=[source],
                              worker_python=worker_python, worker_script=ROOT / 'workers/mlx_worker.py'))
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer isolated-ai-probe'}) as client:
        def request(method, path, body=None, key=None):
            response = client.request(method, '/api/v1' + path, json=body,
                                      headers={'Idempotency-Key': key or uuid.uuid4().hex})
            assert response.status_code == 200, {'path': path, 'status': response.status_code, 'body': response.json()}
            return response.json()

        project = request('POST', '/projects', {'name': '真实本地 AI 建议结构验收'})
        plan = request('POST', '/models/import-plans', {'project_id': project['id'], 'path': str(source), 'name': 'Qwen2.5-0.5B-Instruct'})
        model = request('POST', '/models/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']})
        report['model'] = {'id': model['id'], 'version_id': model['version_id'], 'manifest_digest': model['manifest_digest']}
        for case in CASES:
            result = {'case': case, 'status': 'running'}
            report['cases'].append(result)
            target = request('POST', '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': case['operation'], 'name': case['name']})
            draft = copy.deepcopy(target['draft'])
            draft['model_id'] = model['id']
            draft['input']['prompt'] = '用中文简要说明本地模型适合做什么。'
            parent, field = case['field'].split('.')
            draft[parent][field] = case['before']
            target = request('PATCH', '/tasks/' + target['id'] + '/draft', {'expected_revision': target['draft_revision'], 'draft': draft})
            result['target_before'] = target
            try:
                suggestion = request('POST', '/ai/requests', {'target_task_id': target['id'], 'expected_revision': target['draft_revision'],
                                                            'model_id': model['id'], 'instruction': case['instruction']})
                result['request'] = suggestion
                assert request('GET', '/tasks/' + target['id']) == target
                preflight = request('POST', '/tasks/' + suggestion['generation_task_id'] + '/preflight', {'draft_revision': 1})
                assert preflight['can_submit'], preflight
                result['preflight'] = preflight
                attempt = request('POST', '/tasks/' + suggestion['generation_task_id'] + '/attempts',
                                  {'preflight_id': preflight['preflight_id'], 'expected_revision': 1})
                result['attempt_id'] = attempt['id']
                save()
                print('真实建议开始：' + case['name'] + ' · ' + attempt['id'], flush=True)
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    attempt = request('GET', '/attempts/' + attempt['id'])
                    if attempt['state'] in ('succeeded', 'failed', 'cancelled'):
                        break
                    time.sleep(0.5)
                result['attempt'] = attempt
                if attempt['state'] not in ('succeeded', 'failed', 'cancelled'):
                    result['timeout_cancel'] = request('POST', '/attempts/' + attempt['id'] + '/cancel',
                                                       {'expected_state_version': attempt['state_version']})
                    for _ in range(60):
                        attempt = request('GET', '/attempts/' + attempt['id'])
                        if attempt['state'] in ('succeeded', 'failed', 'cancelled'):
                            break
                        time.sleep(0.5)
                    result['attempt_after_timeout'] = attempt
                    if attempt['state'] not in ('succeeded', 'failed', 'cancelled'):
                        report.update(status='failed', error='建议模型取消后仍未结束，停止后续用例。')
                        save()
                        return 1
                    raise AssertionError('建议模型超过 180 秒，已取消并保留回执。')
                assert attempt['state'] == 'succeeded', attempt
                assert request('GET', '/tasks/' + target['id']) == target
                result['raw_answer_sha256'] = hashlib.sha256(attempt['output_text'].encode()).hexdigest()
                proposal = request('POST', '/ai/requests/' + suggestion['id'] + '/proposals', {'attempt_id': attempt['id']})
                result['proposal'] = proposal
                assert proposal['execution_actions'] == [] and len(proposal['changes']) == 1
                change = proposal['changes'][0]
                assert (change['field'], change['from'], change['to']) == (case['field'], case['before'], case['after']), change
                assert type(change['to']) is int
                assert request('GET', '/tasks/' + target['id']) == target
                applied = request('POST', '/ai/proposals/' + proposal['id'] + '/apply', {'expected_revision': target['draft_revision']})
                result['applied'] = applied
                expected = copy.deepcopy(target['draft'])
                expected[parent][field] = case['after']
                assert applied['task']['draft'] == expected and applied['task']['draft_revision'] == target['draft_revision'] + 1
                reverted = request('POST', '/ai/proposals/' + proposal['id'] + '/undo', {'expected_revision': applied['task']['draft_revision']})
                result['undone'] = reverted
                assert reverted['task']['draft'] == target['draft'] and reverted['task']['draft_revision'] == target['draft_revision'] + 2
                result.update(status='passed', target_unchanged_before_apply=True, undo_restored_original_fields=True)
            except Exception as error:
                result.update(status='failed', error=str(error))
            result['target_attempts'] = request('GET', '/attempts?task_id=' + target['id'])['items']
            result['target_after'] = request('GET', '/tasks/' + target['id'])
            if result['target_attempts']:
                result.update(status='failed', error='目标草稿意外产生了运行。')
            save()
            print(json.dumps({'case': case['name'], 'status': result['status'], 'error': result.get('error')}, ensure_ascii=False), flush=True)
    report.update(status='passed' if all(case['status'] == 'passed' for case in report['cases']) else 'partial', finished_at=time.time())
    save()
    print(json.dumps({'status': report['status'], 'report': str(output / 'report.json')}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='已验证的本地 Qwen2.5-0.5B-Instruct 原权重目录')
    parser.add_argument('--output', type=Path, required=True, help='尚不存在的独立证据目录')
    parser.add_argument('--worker-python', type=Path, default=ROOT / 'adapters/mlx_text/.venv/bin/python')
    arguments = parser.parse_args()
    raise SystemExit(run(arguments.source.resolve(), arguments.output.resolve(), arguments.worker_python.absolute()))
