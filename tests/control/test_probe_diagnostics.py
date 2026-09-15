"""真实 CPU 探测进程的失败分类、诊断冻结与身份隔离；不加载模型。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from test_environment_refresh import environment_client, capabilities, counts, ready
from ailab_control.checkpoints import compatibility
from ailab_control.diagnostics import Diagnostics
from ailab_control.probe_observations import ProbeFailure, ProbeObservations
from ailab_control.service import Service, Settings
from ailab_control.storage import digest, encode

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = 'PRIVATE_ENV_PROBE_79'
FACTS = {'python': '3.13.9', 'metal': True, 'device_ready': True,
         'dependencies': {'mlx': '0.32.2', 'mlx-lm': '0.31.3'},
         'sources': {'mlx_worker.py': 'a' * 64, 'checkpoint.py': 'b' * 64, 'recipe.py': 'c' * 64},
         'runtime_manifest_sha256': 'd' * 64, 'private': PRIVATE}


def executor(directory):
    directory.mkdir()
    binary = directory / 'probe'
    binary.write_text('#!' + str(Path(sys.executable).resolve()) + '\n' + '''import json,sys,time
from pathlib import Path
root=Path(__file__).parent
state=json.loads((root/'state.json').read_text())
with (root/'calls.txt').open('a') as stream: stream.write('probe\\n')
print('PRIVATE_ENV_PROBE_79 /Users/private/probe token=private',file=sys.stderr,flush=True)
if state['failure']=='exit': raise SystemExit(9)
if state['failure']=='timeout': time.sleep(5)
if state['failure']=='invalid_json': print('PRIVATE_ENV_PROBE_79'); raise SystemExit(0)
print(json.dumps(state['facts']))
''')
    binary.chmod(0o700)
    write_state(binary)
    return binary


def write_state(binary, failure='success'):
    facts = dict(FACTS)
    if failure == 'invalid_facts': facts = []
    if failure == 'invalid_device': facts['device_ready'] = facts['metal'] = 'yes'
    if failure == 'invalid_dependencies': facts['dependencies'] = []
    if failure == 'not_ready': facts['device_ready'] = facts['metal'] = False
    (binary.parent / 'state.json').write_text(json.dumps({'failure': failure, 'facts': facts}))


@pytest.fixture
def service_factory(tmp_path):
    opened = []
    def create(engine='mlx', backend='bundled'):
        root = tmp_path / str(len(opened)); root.mkdir()
        binary = executor(root / PRIVATE)
        settings = Settings(root / 'library', 'probe-diagnostics-token', worker_script=ROOT / 'workers/mlx_worker.py',
                            preflight_script=ROOT / 'adapters/mlx_text/preflight.py')
        prefix = {'mlx': 'worker', 'diffusers': 'media', 'kokoro': 'audio'}[engine]
        name = ('worker_python' if engine == 'mlx' else prefix + '_python') if backend == 'external_python' else ('bundled_worker' if engine == 'mlx' else 'bundled_' + prefix + '_worker')
        setattr(settings, name, binary)
        service = Service(settings); opened.append(service)
        probe = service.environment if engine == 'mlx' else lambda refresh=False: service.media.environment('audio' if engine == 'kokoro' else 'image', refresh)
        return service, binary, probe
    yield create
    for service in opened:
        service.close()


@pytest.mark.parametrize('engine', ['mlx', 'diffusers', 'kokoro'])
@pytest.mark.parametrize('backend', ['bundled', 'external_python'])
@pytest.mark.parametrize('failure,code,returncode', [
    ('exit', 'PROBE_EXIT_NONZERO', 9), ('timeout', 'PROBE_TIMEOUT', None),
    ('start', 'PROBE_START_FAILED', None), ('invalid_json', 'PROBE_INVALID_JSON', 0),
    ('invalid_facts', 'PROBE_INVALID_FACTS', 0), ('invalid_device', 'PROBE_INVALID_FACTS', 0),
    ('invalid_dependencies', 'PROBE_INVALID_FACTS', 0), ('not_ready', 'PROBE_NOT_READY', 0),
])
def test_actual_probe_failure_categories_are_safe_without_attempts(service_factory, monkeypatch, engine, backend, failure, code, returncode):
    service, binary, probe = service_factory(engine, backend)
    write_state(binary, failure)
    if failure == 'start':
        binary.write_text('PRIVATE_ENV_PROBE_79 is not an executable format\n')
    if failure == 'timeout':
        original = subprocess.run
        def bounded(command, **kwargs):
            assert kwargs['timeout'] == (90 if backend == 'bundled' else 20 if engine == 'mlx' else 30)
            return original(command, **{**kwargs, 'timeout': 0.15})
        monkeypatch.setattr(subprocess, 'run', bounded)
    environment = probe()
    assert environment['ready'] is False
    assert PRIVATE not in environment['reason']
    if failure == 'timeout': assert '超时' in environment['reason']
    records, omitted = service.probe_observations.snapshot()
    assert omitted == 0 and len(records) == 1
    record = records[0]
    assert set(record) == {'engine', 'execution_backend', 'status', 'error_code', 'elapsed_seconds', 'returncode', 'completed_at', 'control_pid', 'started_monotonic_ns', 'completed_monotonic_ns'}
    assert (record['engine'], record['execution_backend'], record['status'], record['error_code'], record['returncode']) == (engine, backend, 'failed', code, returncode)
    assert math.isfinite(record['elapsed_seconds']) and record['elapsed_seconds'] >= 0
    assert datetime.fromisoformat(record['completed_at']).tzinfo is not None
    data = Diagnostics(service).preview({})['diagnostics']
    assert data['probe_observations'] == records and data['resource_counts']['attempt'] == 0
    assert PRIVATE not in encode(data) and str(binary) not in encode(data)
    assert service.store.list('attempt') == [] and not service.processes
    assert probe() == environment and service.probe_observations.snapshot() == (records, 0)


def test_explicit_api_refresh_records_failure_then_success_and_cache_reads_add_nothing(environment_client):
    client, binaries = environment_client
    service = client.app.state.service
    assert not any(capabilities(client).values())
    first, omitted = service.probe_observations.snapshot()
    assert len(first) == 3 and omitted == 0
    assert {record['engine'] for record in first} == {'mlx', 'diffusers', 'kokoro'}
    assert all(record['error_code'] == 'PROBE_EXIT_NONZERO' and record['returncode'] == 9 for record in first)
    ready(binaries)
    assert not any(capabilities(client).values())
    assert counts(binaries) == dict.fromkeys(binaries, 1)
    assert service.probe_observations.snapshot() == (first, 0)
    assert all(capabilities(client, '?refresh=true').values())
    records, omitted = service.probe_observations.snapshot()
    assert len(records) == 6 and records[:3] == first
    assert all(record['status'] == 'succeeded' and record['error_code'] is None and record['returncode'] == 0 for record in records[3:])
    assert all(capabilities(client).values())
    assert counts(binaries) == dict.fromkeys(binaries, 2)
    assert service.probe_observations.snapshot() == (records, 0)


@pytest.mark.parametrize('engine', ['mlx', 'diffusers', 'kokoro'])
@pytest.mark.parametrize('backend', ['bundled', 'external_python'])
def test_success_refresh_preserves_environment_snapshot_and_checkpoint_identity(service_factory, engine, backend):
    service, _, probe = service_factory(engine, backend)
    first = probe()
    assert first['ready']
    snapshot = {'runtime': {'steps': 192}, 'environment': first}
    before = digest(snapshot)
    checkpoint = compatibility(snapshot) if engine == 'mlx' else None
    second = probe(refresh=True)
    assert second == first and digest({'runtime': snapshot['runtime'], 'environment': second}) == before
    if engine == 'mlx': assert compatibility(snapshot, second) == checkpoint
    assert not {'elapsed_seconds', 'completed_at', 'probe_observations', 'error_code'} & set(second)
    records, omitted = service.probe_observations.snapshot()
    assert len(records) == 2 and omitted == 0 and records[0]['completed_at'] != records[1]['completed_at']
    assert all(record['status'] == 'succeeded' for record in records)


def test_diagnostics_zip_freezes_prior_probe_observations_and_never_reprobes(service_factory, tmp_path, monkeypatch):
    service, binary, probe = service_factory('diffusers')
    write_state(binary, 'exit')
    assert probe()['ready'] is False
    diagnostics = Diagnostics(service)
    preview = diagnostics.preview({})
    write_state(binary)
    assert probe(refresh=True)['ready'] is True
    def forbidden(*args, **kwargs): pytest.fail('诊断不得新增探测或读取原始日志。')
    monkeypatch.setattr(service, 'environment', forbidden)
    monkeypatch.setattr(service.media, 'environment', forbidden)
    monkeypatch.setattr(service.probe_observations, 'run', forbidden)
    monkeypatch.setattr(service.store, 'events', forbidden)
    target = tmp_path / 'export'; target.mkdir(); service.settings.export_roots = [target]
    payload = {'preview_id': preview['id'], 'target_dir': str(target)}
    result = diagnostics.export(payload, 'freeze-probe-records')
    assert result['status'] == 'succeeded'
    with zipfile.ZipFile(result['saved_path']) as archive:
        data = json.loads(archive.read('diagnostics.json'))
        manifest = json.loads(archive.read('manifest.json'))
        content = b'\n'.join(archive.read(name) for name in archive.namelist()).decode()
    assert data == preview['diagnostics'] and len(data['probe_observations']) == 1
    assert len(data['environment_observations']) == 1
    assert data['environment_observations'][0]['ready'] is False
    assert data['probe_observations'][0]['error_code'] == 'PROBE_EXIT_NONZERO'
    assert manifest['files'][0]['sha256'] == hashlib.sha256((encode(data) + '\n').encode()).hexdigest()
    assert PRIVATE not in content and '/Users/private/' not in content and str(service.root) not in content
    assert diagnostics.export(payload, 'freeze-probe-records') == result
    assert len(diagnostics.preview({})['diagnostics']['probe_observations']) == 2
    assert len((binary.parent / 'calls.txt').read_text().splitlines()) == 2


def test_observations_are_bounded_thread_safe_and_snapshots_are_detached():
    observations = ProbeObservations()
    command = [sys.executable, '-B', '-c', 'import json;print(' + repr(json.dumps(FACTS)) + ')']
    def run(index):
        engine = ('mlx', 'diffusers', 'kokoro')[index % 3]
        return observations.run(engine, 'bundled', command, timeout=5, env=None, is_ready=lambda facts: True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(result[1] for result in pool.map(run, range(36)))
    records, omitted = observations.snapshot()
    assert len(records) == 32 and omitted == 4
    records[0]['error_code'] = PRIVATE
    assert PRIVATE not in encode(observations.snapshot())


def test_service_restart_clears_session_observations_and_unconfigured_does_not_probe(service_factory):
    service, _, probe = service_factory()
    probe()
    assert len(service.probe_observations.snapshot()[0]) == 1
    settings = service.settings
    service.close()
    reopened = Service(settings)
    try:
        data = Diagnostics(reopened).preview({})['diagnostics']
        assert data['probe_observations'] == [] and data['probe_observations_omitted'] == 0
        assert data['environment_observations'] == [] and data['environment_observations_omitted'] == 0
        assert '重启清空' in data['probe_scope'] and '可能包含旧配置' in data['probe_scope']
        reopened.settings.bundled_worker = None
        assert reopened.environment()['ready'] is False
        assert reopened.probe_observations.snapshot() == ([], 0)
    finally:
        reopened.close()


@pytest.mark.parametrize('failure,expected,code', [(ValueError, ProbeFailure, 'PROBE_INVALID_FACTS'),
    (RuntimeError, RuntimeError, 'PROBE_INCOMPLETE'), (KeyboardInterrupt, KeyboardInterrupt, 'PROBE_INCOMPLETE')])
def test_readiness_exceptions_never_record_success(failure, expected, code):
    observations = ProbeObservations()
    command = [sys.executable, '-B', '-c', 'import json;print(' + repr(json.dumps(FACTS)) + ')']
    def fail(facts): raise failure(PRIVATE)
    with pytest.raises(expected):
        observations.run('mlx', 'bundled', command, timeout=5, env=None, is_ready=fail)
    records, omitted = observations.snapshot()
    assert omitted == 0 and len(records) == 1
    assert records[0]['status'] == 'failed' and records[0]['error_code'] == code and records[0]['returncode'] == 0
    assert PRIVATE not in encode(records)
