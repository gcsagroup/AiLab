"""在独立提供方进程上运行市场验收；只创建指定输出目录，不接主 App 数据库。"""

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import selectors
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/control'))

from fixture_market_provider import write
from test_market import entry
from ailab_control.assets import file_hash, verify_manifest
from ailab_control.market import LoopbackProvider, Market
from ailab_control.service import Service, Settings
from ailab_control.storage import Fault


def run(output):
    if output.exists():
        raise ValueError('验收输出目录必须不存在，避免覆盖已有证据。')
    output.mkdir(parents=True)
    provider_root, state = output / 'provider', output / 'provider-state'
    provider_root.mkdir()
    values = [entry(provider_root), entry(provider_root, 'limited', access='restricted'), entry(provider_root, 'pictures', schema='image_caption_v1'), entry(provider_root, 'large', repeated=10000)]
    write(provider_root / 'catalog.json', {'schema_version': 'market-catalog-v1', 'provider_id': 'fixture-provider', 'catalog_version': 'catalog-v1', 'versions': values})
    provider_script = Path(__file__).with_name('fixture_market_provider.py')
    command = [sys.executable, '-B', str(provider_script), '--root', str(provider_root), '--state', str(state), '--port', '0', '--chunk-delay', '0.002']
    service = None
    with (output / 'provider.stderr.log').open('w') as error_log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=error_log, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(10):
                    raise RuntimeError('独立提供方未在 10 秒内报告地址。')
                provider = json.loads(process.stdout.readline())
            write(output / 'provider-process.json', provider)
            assert provider['pid'] == process.pid
            settings = Settings(output / 'control-data', 'controlled-protocol-local-token')
            service = Service(settings)
            project = service.project({'name': '独立受控来源验收'})
            registry = [LoopbackProvider('fixture-provider', provider['origin'])]
            market = Market(service, registry)
            versions = {value['metadata']['dataset_key']: value for value in market.browse(project['id'], 'fixture-provider')['versions']}
            results = {}
            for name, kind in [('dialogue', 'text'), ('pictures', 'image')]:
                task = service.new_task({'project_id': project['id'], 'kind': kind, 'operation': 'train', 'name': '保留本机原训练草稿'})
                task['draft']['runtime']['seed'] = 919
                task = service.save_draft(task['id'], {'expected_revision': 1, 'draft': task['draft']})
                original = copy.deepcopy(task)
                context = market.enter(task['id'], {'expected_revision': task['draft_revision'], 'step': 'data'}, 'enter-' + name)
                started = market.start_download(versions[name]['id'], {'user_statement': '用于本地传输与结构验收'}, 'start-' + name)
                completed = market.execute_download(started['id'], 'execute-' + name)
                assert completed['complete'] and completed['state'] == 'completed'
                dataset = market.register_new_dataset(completed['id'], 'register-' + name)
                assert service.store.get('task', task['id']) == original
                result = market.use_for_task(context['id'], {'dataset_id': dataset['id']}, 'use-' + name)
                expected = copy.deepcopy(original['draft']); expected['dataset_id'] = dataset['id']
                assert result['task']['draft'] == expected
                verify_manifest(Path(dataset['storage_path']), dataset['manifest'])
                results[name] = {'download': completed, 'dataset': dataset, 'original_task': original, 'returned': result}
            access = market.request_access(versions['limited']['id'], {'purpose': '验证审批协议与原始字段', 'user_statement': '仅在本机检查受控示例'}, 'request')
            assert access['provider_response']['status'] == 'waiting'
            rejected = False
            try:
                market.start_download(versions['limited']['id'], {'user_statement': '本机测试', 'access_id': access['id']}, 'before-approval')
            except Fault as error:
                rejected = error.code == 'MARKET_ACCESS_NOT_GRANTED'
            assert rejected
            decisions = []
            for status in ['denied', 'approved']:
                instruction = [sys.executable, '-B', str(provider_script), '--root', str(provider_root), '--state', str(state), '--decision', access['provider_response']['request_id'], '--status', status, '--provider-text', '提供方操作员明确选择：' + status]
                if status == 'approved':
                    instruction += ['--expires-at', (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()]
                decision = subprocess.run(instruction, capture_output=True, text=True, timeout=10, check=True)
                decisions.append(json.loads(decision.stdout))
                assert market.refresh_access(access['id'])['provider_response']['status'] == status
            started = market.start_download(versions['limited']['id'], {'user_statement': '本机测试', 'access_id': access['id']}, 'after-approval')
            completed = market.execute_download(started['id'], 'execute-limited')
            assert completed['complete']
            dataset = market.register_new_dataset(completed['id'], 'register-limited')
            results['restricted'] = {'initial_request': access, 'waiting_download_rejected': rejected, 'operator_process_responses': decisions, 'download': completed, 'dataset': dataset, 'latest_access': market.refresh_access(access['id'])}
            started = market.start_download(versions['large']['id'], {'user_statement': '真实取消与控制服务重启续传'}, 'start-large')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(market.execute_download, started['id'], 'first-large')
                deadline = time.monotonic() + 10
                while service.store.get('market-download', started['id'])['received_bytes'] < 65536 and time.monotonic() < deadline:
                    time.sleep(0.005)
                market.cancel_download(started['id'], 'cancel-large')
                cancelled = future.result(timeout=15)
            assert cancelled['state'] == 'cancelled' and 0 < cancelled['received_bytes'] < versions['large']['metadata']['total_bytes']
            partial = market.root / started['id'] / 'files/data.jsonl'
            prefix_hash = file_hash(partial)
            service.close()
            service = Service(settings)
            market = Market(service, registry)
            assert file_hash(partial) == prefix_hash and service.store.get('market-download', started['id']) == cancelled
            resumed = market.execute_download(started['id'], 'resume-after-restart')
            assert resumed['complete'] and file_hash(partial) == versions['large']['metadata']['files'][0]['sha256']
            results['restart_resume'] = {'cancelled': cancelled, 'partial_sha256_before_restart': prefix_hash, 'resumed': resumed, 'verified_full_sha256': file_hash(partial)}
            report = {'status': '通过', 'scope': '独立 loopback 提供方、原文审批、真实 Range 下载、两类数据导入与原任务返回、控制服务重启续传', 'external_market_connected': False, 'model_training_executed': False, 'ui_exercised': False, 'provider_pid': process.pid, 'driver_pid': __import__('os').getpid(), 'results': results, 'source_sha256': {str(path.relative_to(ROOT)): file_hash(path) for path in [ROOT / 'services/control/ailab_control/market.py', provider_script, Path(__file__)]}}
            write(output / 'acceptance.json', report)
            return report
        finally:
            if service:
                service.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps({'status': report['status'], 'scope': report['scope'], 'evidence': str(args.output / 'acceptance.json')}, ensure_ascii=False))
