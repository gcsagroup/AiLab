"""阶段耗时的严格白名单、身份隔离与真实诊断导出；仅使用 CPU 测试替身。"""

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from test_probe_diagnostics import FACTS, PRIVATE, service_factory
from ailab_control.diagnostics import Diagnostics
from ailab_control.probe_observations import ProbeFailure, ProbeObservations
from ailab_control.storage import digest, encode

PREFIX = 'AILAB_PROBE_STAGE_V1 '
STAGES = ('runtime_files', 'media_tools_files', 'dependency_versions', 'torch_import',
          'engine_imports', 'tracker_start', 'tracker_reap')
RECORD_KEYS = {'engine', 'execution_backend', 'status', 'error_code', 'elapsed_seconds',
               'returncode', 'completed_at', 'control_pid', 'started_monotonic_ns', 'completed_monotonic_ns'}
STAGE_KEYS = {'stage', 'status', 'elapsed_seconds'}
RAW_STDERR = PRIVATE + ' /Users/private/probe token=stage-secret rawstderr'
CPU_PROGRAM = '''import json,sys,time
state=json.loads(sys.argv[1])
for line in state['stderr_lines']: print(line,file=sys.stderr,flush=True)
if state['delay']: time.sleep(state['delay'])
if state['returncode']: raise SystemExit(state['returncode'])
print(json.dumps(state['facts']))
'''


def stage(name='runtime_files', elapsed=0.25, status='succeeded'):
    return {'stage': name, 'status': status, 'elapsed_seconds': elapsed}


def line(value):
    return PREFIX + json.dumps(value)


def run_cpu(observations, *, engine='diffusers', backend='bundled', lines=(), facts=None,
            returncode=0, delay=0, timeout=5, is_ready=lambda facts: True):
    state = {'stderr_lines': list(lines), 'facts': FACTS if facts is None else facts,
             'returncode': returncode, 'delay': delay}
    return observations.run(engine, backend, [sys.executable, '-B', '-c', CPU_PROGRAM, json.dumps(state)],
                            timeout=timeout, env=None, is_ready=is_ready)


def only_record(observations):
    records, omitted = observations.snapshot()
    assert omitted == 0 and len(records) == 1
    return records[0]


def install_stage_executor(binary):
    # 复用已有 fixture 的临时服务和执行器路径；程序只输出固定 JSON，不加载模型。
    binary.write_text('#!' + str(Path(sys.executable).resolve()) + '\n' + '''import json,sys
from pathlib import Path
root=Path(__file__).parent
state=json.loads((root/'state.json').read_text())
with (root/'calls.txt').open('a') as stream: stream.write('probe\\n')
for line in state['stderr_lines']: print(line,file=sys.stderr,flush=True)
print(json.dumps(state['facts']))
''')


def write_stage_state(binary, stages):
    facts = {**FACTS, 'probe_stages': [*stages, {'private': RAW_STDERR}]}
    state = {'facts': facts, 'stderr_lines': [RAW_STDERR, *map(line, stages),
             line({**stage('runtime_files'), 'path': '/Users/private/probe', 'token': PRIVATE})]}
    (binary.parent / 'state.json').write_text(json.dumps(state))


@pytest.mark.parametrize('engine', ['diffusers', 'kokoro'])
def test_bundled_media_accepts_all_completed_stages_without_order_constraint(engine):
    observations = ProbeObservations()
    elapsed = [0, 1, 0.123456789, 0.0000004, 0.0000006, 2.3456789, 1e100]
    expected = [stage(name, round(value, 6), 'failed' if index % 2 else 'succeeded')
                for index, (name, value) in enumerate(zip(reversed(STAGES), elapsed))]
    records = [stage(item['stage'], value, item['status']) for item, value in zip(expected, elapsed)]
    facts, ready = run_cpu(observations, engine=engine, lines=[RAW_STDERR, *map(line, records)])
    assert ready is True and facts == FACTS
    record = only_record(observations)
    assert set(record) == RECORD_KEYS | {'stages'}
    assert record['stages'] == expected
    assert record['status'] == 'succeeded' and record['error_code'] is None
    assert all(set(item) == STAGE_KEYS and type(item['elapsed_seconds']) is not bool
               and math.isfinite(item['elapsed_seconds']) and item['elapsed_seconds'] >= 0 for item in record['stages'])
    assert PRIVATE not in encode(record) and 'rawstderr' not in encode(record)


@pytest.mark.parametrize('invalid', [
    -0.000001, True, False, None, '0.1', [], {}, float('nan'), float('inf'), -float('inf'), 10 ** 400,
], ids=['negative', 'true', 'false', 'null', 'text', 'list', 'object', 'nan', 'infinity', 'negative-infinity', 'overflow-integer'])
def test_invalid_elapsed_is_ignored_and_old_record_keys_stay_unchanged(invalid):
    observations = ProbeObservations()
    _, ready = run_cpu(observations, lines=[RAW_STDERR, line(stage(elapsed=invalid))])
    record = only_record(observations)
    assert ready is True and record['status'] == 'succeeded'
    assert set(record) == RECORD_KEYS
    assert RAW_STDERR not in encode(record)


@pytest.mark.parametrize('invalid', [
    'not-json', 'null', '[]', '"private"',
    json.dumps({**stage(), 'stage': PRIVATE}), json.dumps({**stage(), 'stage': []}),
    json.dumps({**stage(), 'status': 'running'}), json.dumps({**stage(), 'status': True}),
    json.dumps({**stage(), 'path': '/Users/private/probe', 'token': PRIVATE}),
    json.dumps({'stage': 'runtime_files', 'status': 'succeeded'}),
    json.dumps({'stage': 'runtime_files', 'elapsed_seconds': 1}),
    json.dumps({'status': 'succeeded', 'elapsed_seconds': 1}),
], ids=['malformed-json', 'null', 'list', 'string', 'unknown-stage', 'stage-list', 'unfinished-status',
        'boolean-status', 'extra-private-keys', 'missing-elapsed', 'missing-status', 'missing-stage'])
def test_stage_schema_rejects_unknown_fields_values_and_non_objects(invalid):
    observations = ProbeObservations()
    run_cpu(observations, lines=[RAW_STDERR, PREFIX + invalid])
    record = only_record(observations)
    assert set(record) == RECORD_KEYS
    assert PRIVATE not in encode(record) and '/Users/private/' not in encode(record)


def test_prefix_is_exact_and_first_legal_duplicate_wins():
    observations = ProbeObservations()
    first = stage('tracker_reap', 0.125, 'failed')
    second = stage('runtime_files', 0.875)
    lines = ['warning ' + line(stage('torch_import')), 'AILAB_PROBE_STAGE_V2 ' + json.dumps(stage('torch_import')),
             line({**first, 'extra': PRIVATE}), line(first), line(stage('tracker_reap', 999)), line(second)]
    run_cpu(observations, lines=lines)
    assert only_record(observations)['stages'] == [first, second]


@pytest.mark.parametrize('engine', ['mlx', 'diffusers', 'kokoro'])
@pytest.mark.parametrize('backend', ['bundled', 'external_python'])
def test_stdout_stages_are_removed_before_readiness_for_every_backend(engine, backend):
    observations = ProbeObservations()
    received = []
    expected = stage('engine_imports', 0.5)
    def is_ready(facts):
        assert 'probe_stages' not in facts
        received.append(facts)
        return facts['metal' if engine == 'mlx' else 'device_ready']
    facts, ready = run_cpu(observations, engine=engine, backend=backend, lines=[RAW_STDERR, line(expected)],
                           facts={**FACTS, 'probe_stages': [{'private': RAW_STDERR}]}, is_ready=is_ready)
    assert ready is True and facts == FACTS and received == [FACTS]
    record = only_record(observations)
    if backend == 'bundled' and engine in {'diffusers', 'kokoro'}:
        assert record['stages'] == [expected]
    else:
        assert set(record) == RECORD_KEYS
    assert PRIVATE not in encode(record)


def test_stdout_stage_list_alone_never_creates_observation_stages():
    observations = ProbeObservations()
    facts, ready = run_cpu(observations, facts={**FACTS, 'probe_stages': [stage()]})
    assert ready is True and facts == FACTS
    assert set(only_record(observations)) == RECORD_KEYS


@pytest.mark.parametrize('engine', ['diffusers', 'kokoro'])
def test_actual_nonzero_probe_keeps_completed_stages_and_safe_error(engine):
    observations = ProbeObservations()
    stages = [stage('runtime_files', 0.1), stage('engine_imports', 0.2, 'failed')]
    with pytest.raises(ProbeFailure) as failure:
        run_cpu(observations, engine=engine, lines=[RAW_STDERR, *map(line, stages)], returncode=9)
    assert failure.value.code == 'PROBE_EXIT_NONZERO' and PRIVATE not in str(failure.value)
    record = only_record(observations)
    assert record['status'] == 'failed' and record['error_code'] == 'PROBE_EXIT_NONZERO' and record['returncode'] == 9
    assert record['stages'] == stages and set(record) == RECORD_KEYS | {'stages'}
    assert PRIVATE not in encode(record) and 'stderr' not in record


@pytest.mark.parametrize('engine', ['diffusers', 'kokoro'])
@pytest.mark.parametrize('as_bytes', [False, True], ids=['text-stderr', 'bytes-stderr'])
def test_timeout_stderr_keeps_completed_stages_for_both_capture_types(monkeypatch, engine, as_bytes):
    observations = ProbeObservations()
    expected = stage('dependency_versions', 0.125)
    stderr = RAW_STDERR + '\n' + line(expected) + '\n' + PREFIX + '{unfinished'
    if as_bytes:
        stderr = b'\xff\n' + stderr.encode()
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs['timeout'], output=PRIVATE, stderr=stderr)
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(ProbeFailure) as failure:
        run_cpu(observations, engine=engine)
    assert failure.value.code == 'PROBE_TIMEOUT'
    record = only_record(observations)
    assert record['stages'] == [expected] and record['returncode'] is None
    assert record['status'] == 'failed' and record['error_code'] == 'PROBE_TIMEOUT'
    assert PRIVATE not in encode(record) and 'stderr' not in record and 'stdout' not in record


def test_actual_cpu_timeout_preserves_flushed_stages():
    observations = ProbeObservations()
    expected = stage('torch_import', 0.25)
    with pytest.raises(ProbeFailure) as failure:
        run_cpu(observations, lines=[RAW_STDERR, line(expected)], delay=5, timeout=0.5)
    assert failure.value.code == 'PROBE_TIMEOUT'
    record = only_record(observations)
    assert record['stages'] == [expected] and record['returncode'] is None
    assert record['status'] == 'failed' and record['error_code'] == 'PROBE_TIMEOUT'
    assert PRIVATE not in encode(record)


def test_stage_snapshots_detach_nested_lists_and_dicts():
    observations = ProbeObservations()
    expected = stage('tracker_start', 0.25)
    run_cpu(observations, lines=[line(expected)])
    records, _ = observations.snapshot()
    records[0]['stages'][0]['elapsed_seconds'] = PRIVATE
    records[0]['stages'][0]['path'] = '/Users/private/probe'
    records[0]['stages'].append({'token': PRIVATE})
    records.append({'stages': [PRIVATE]})
    assert only_record(observations)['stages'] == [expected]
    assert PRIVATE not in encode(observations.snapshot())


@pytest.mark.parametrize('engine', ['diffusers', 'kokoro'])
def test_stage_duration_refresh_does_not_change_environment_digest(service_factory, engine):
    service, binary, probe = service_factory(engine)
    install_stage_executor(binary)
    first_stages = [stage('runtime_files', 0.1), stage('torch_import', 0.2)]
    second_stages = [stage('runtime_files', 1.5), stage('torch_import', 3.5)]
    write_stage_state(binary, first_stages)
    first = probe()
    write_stage_state(binary, second_stages)
    second = probe(refresh=True)
    assert first['ready'] and second['ready']
    assert first == second and first['digest'] == second['digest']
    assert digest({'environment': first, 'runtime': {'steps': 4}}) == digest({'environment': second, 'runtime': {'steps': 4}})
    assert 'probe_stages' not in first['versions'] and 'stages' not in first['versions']
    records, omitted = service.probe_observations.snapshot()
    assert omitted == 0 and [record['stages'] for record in records] == [first_stages, second_stages]
    assert len((binary.parent / 'calls.txt').read_text().splitlines()) == 2


def test_actual_diagnostics_zip_and_summary_preserve_only_frozen_safe_stages(service_factory, tmp_path, monkeypatch):
    service, binary, probe = service_factory('diffusers')
    install_stage_executor(binary)
    expected = [stage('runtime_files', 0.125), stage('tracker_reap', 0.25)]
    write_stage_state(binary, expected)
    assert probe()['ready']
    diagnostics = Diagnostics(service)
    preview = diagnostics.preview({})
    write_stage_state(binary, [stage('runtime_files', 99)])
    assert probe(refresh=True)['ready']
    def forbidden(*args, **kwargs):
        pytest.fail('诊断导出不得新增探测、读取原始日志或启动模型。')
    monkeypatch.setattr(service, 'environment', forbidden)
    monkeypatch.setattr(service.media, 'environment', forbidden)
    monkeypatch.setattr(service.probe_observations, 'run', forbidden)
    monkeypatch.setattr(service.store, 'events', forbidden)
    destination = tmp_path / 'exports'
    destination.mkdir()
    service.settings.export_roots = [destination]
    result = diagnostics.export({'preview_id': preview['id'], 'target_dir': str(destination)}, 'stage-diagnostics-once')
    assert result['status'] == 'succeeded'
    exported = Path(result['saved_path'])
    assert hashlib.sha256(exported.read_bytes()).hexdigest() == preview['archive_sha256']
    assert exported.stat().st_size == preview['archive_bytes']
    with zipfile.ZipFile(exported) as archive:
        assert archive.namelist() == ['diagnostics.json', 'manifest.json']
        bodies = {name: archive.read(name) for name in archive.namelist()}
    data = json.loads(bodies['diagnostics.json'])
    manifest = json.loads(bodies['manifest.json'])
    assert data == preview['diagnostics']
    assert len(data['probe_observations']) == 1 and data['probe_observations'][0]['stages'] == expected
    assert set(data['probe_observations'][0]) == RECORD_KEYS | {'stages'}
    assert all(set(item) == STAGE_KEYS for item in data['probe_observations'][0]['stages'])
    assert manifest['complete'] is True
    assert manifest['files'] == [{'path': 'diagnostics.json', 'size': len(bodies['diagnostics.json']),
                                  'sha256': hashlib.sha256(bodies['diagnostics.json']).hexdigest()}]
    for entry in preview['files']:
        assert entry['size'] == len(bodies[entry['path']])
        assert entry['sha256'] == hashlib.sha256(bodies[entry['path']]).hexdigest()
    # summary.json仅为本测试的往返序列化产物，生产ZIP仍保持原有两项结构。
    summary = tmp_path / 'summary.json'
    summary.write_text(encode(preview['diagnostics']) + '\n')
    assert json.loads(summary.read_text()) == data
    assert summary.read_bytes() == bodies['diagnostics.json']
    content = b'\n'.join([*bodies.values(), summary.read_bytes()]).decode()
    assert all(value not in content for value in (PRIVATE, RAW_STDERR, '/Users/private/', 'stage-secret',
                                                  str(binary), str(service.root), service.settings.token, 'rawstderr'))
    assert len((binary.parent / 'calls.txt').read_text().splitlines()) == 2
