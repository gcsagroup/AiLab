"""正式 HTTP 流程实算三种格式：转换、独立加载、登记、试用和导出。"""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'services/control'))
from fastapi.testclient import TestClient
from ailab_control.api import create_app
from ailab_control.assets import model_manifest, file_hash, verify_manifest
from ailab_control.service import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--media-python', type=Path)
    parser.add_argument('--bundled-media-worker', type=Path)
    parser.add_argument('--source', type=Path, help='默认使用原始 0.5B；可验证合并或蒸馏后导出的独立模型')
    args = parser.parse_args(); evidence = args.evidence.resolve(); evidence.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve() if args.source else ROOT / '.artifacts/models/Qwen2.5-0.5B-Instruct'
    identity = model_manifest(source)['manifest_digest']
    report = {'status': 'running', 'source_manifest_digest': identity, 'quality_status': 'not_evaluated', 'formats': {}}
    def save(): (evidence / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    settings = Settings(evidence / 'data', 'isolated-format-probe', [source, evidence], media_python=args.media_python.absolute() if args.media_python else None, bundled_media_worker=args.bundled_media_worker.absolute() if args.bundled_media_worker else None, export_roots=[evidence], worker_script=ROOT / 'workers/mlx_worker.py')
    app = create_app(settings); service = app.state.service; save()
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer isolated-format-probe'}) as client:
        def call(method, path, body=None):
            response = client.request(method, '/api/v1' + path, json=body, headers={'Idempotency-Key': uuid.uuid4().hex})
            assert response.status_code in {200, 202}, (path, response.status_code, response.text)
            return response.json()
        def execute(task, record, name):
            checked = call('POST', f"/tasks/{task['id']}/preflight", {'draft_revision': task['draft_revision']})
            record[name + '_preflight'] = checked; save(); assert checked['can_submit'], checked
            attempt = call('POST', f"/tasks/{task['id']}/attempts", {'expected_revision': task['draft_revision'], 'preflight_id': checked['id']})
            record[name + '_task_id'] = task['id']; record[name + '_attempt_id'] = attempt['id']; save()
            print(name + ' ' + attempt['id'], flush=True)
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                attempt = call('GET', '/attempts/' + attempt['id'])
                if attempt['state'] in {'succeeded', 'failed', 'cancelled'}: break
                time.sleep(0.5)
            else:
                call('POST', f"/attempts/{attempt['id']}/cancel", {'expected_state_version': attempt['state_version']})
                raise AssertionError('格式执行超过冻结预算，已请求停止')
            record[name + '_attempt'] = attempt; save()
            assert attempt['compute_outcome'] == 'succeeded' and attempt['collection_state'] == 'succeeded', attempt
            return attempt
        try:
            project = call('POST', '/projects', {'name': '三种格式完整验收'}); report['project_id'] = project['id']
            plan = call('POST', '/models/import-plans', {'project_id': project['id'], 'path': str(source)})
            model = call('POST', '/models/imports', {'plan_id': plan['id'], 'manifest_digest': plan['manifest_digest']})
            report['source_model_id'] = model['id']; save()
            for target in ['torchscript', 'onnx', 'coreml']:
                record = {}; report['formats'][target] = record; save()
                task = call('POST', '/format-conversions', {'project_id': project['id'], 'model_id': model['id'], 'target_format': target})
                attempt = execute(task, record, target + '_convert')
                saved = call('POST', f"/attempts/{attempt['id']}/converted-models", {'name': target + ' 独立模型'})
                record['model'] = saved; save()
                assert saved['format'] == saved['default_engine'] == target and saved['quality_status'] == 'not_evaluated'
                trial = call('POST', '/formatted-model-trials', {'project_id': project['id'], 'model_id': saved['id'], 'prompt': '只回答一个数字：4加5等于几？', 'max_tokens': 16})
                done = execute(trial, record, target + '_trial')
                assert done['output_text'].strip(), done
                record['output'] = done['output_text']; save()
                oversized = call('POST', '/formatted-model-trials', {'project_id': project['id'], 'model_id': saved['id'], 'prompt': '解释。' * 100, 'max_tokens': 64})
                denied = call('POST', f"/tasks/{oversized['id']}/preflight", {'draft_revision': oversized['draft_revision']})
                assert not denied['can_submit'] and any(item['code'] == 'CONTEXT_TOO_LONG' for item in denied['blocking']), denied
                record['overlength_rejected'] = True
                wrong = call('POST', '/tasks', {'project_id': project['id'], 'name': '错误引擎反例', 'kind': 'text', 'operation': 'generate'})
                draft = wrong['draft']; draft['model_id'] = saved['id']; draft['input']['prompt'] = '你好'
                wrong = call('PATCH', f"/tasks/{wrong['id']}/draft", {'expected_revision': wrong['draft_revision'], 'draft': draft})
                denied = call('POST', f"/tasks/{wrong['id']}/preflight", {'draft_revision': wrong['draft_revision']})
                assert not denied['can_submit'] and any(item['code'] == 'CONVERTED_ENGINE_MISMATCH' for item in denied['blocking']), denied
                record['wrong_engine_rejected'] = True
                stored = service.store.get('model', saved['id']); verify_manifest(Path(stored['storage_path']), stored['manifest'])
                target_dir = evidence / ('export-' + target); target_dir.mkdir()
                grant = call('POST', '/export-grants', {'path': str(target_dir)})
                prepared = call('POST', '/exports/prepare', {'project_id': project['id'], 'object_type': 'model', 'object_id': saved['id'], 'target_dir': str(target_dir), 'grant_id': grant['grant_id'], 'include_base': False})
                assert prepared['can_export'], prepared
                exported = call('POST', '/exports', {'plan_id': prepared['id'], 'plan_digest': prepared['plan_digest']})
                record['export'] = exported; save()
                deadline = time.monotonic() + 180
                while exported.get('state') not in {'succeeded', 'failed', 'cancelled'} and time.monotonic() < deadline:
                    time.sleep(0.2); exported = call('GET', '/exports/' + exported['id'])
                record['export'] = exported; save()
                assert exported['state'] == 'succeeded', exported
                verify_manifest(Path(exported['verified_path']) / 'model', stored['manifest'])
                record['physical_export_sha256_verified'] = True
                record['status'] = 'passed'; save()
            assert model_manifest(source)['manifest_digest'] == identity
            report.update(status='passed', source_files_unchanged=True)
        except Exception as error:
            report.update(status='failed', error=repr(error)); raise
        finally: save()
    print(str(evidence / 'report.json'), flush=True)


if __name__ == '__main__': main()
