"""环境调用分段仅用于会话诊断；固定 CPU 执行器和临时测试库，不加载模型。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import os
import threading

import pytest

from test_environment_refresh import environment_client, capabilities, counts, ready
from test_probe_diagnostics import service_factory, PRIVATE
from ailab_control.diagnostics import Diagnostics, MAX_BYTES
from ailab_control.storage import encode

ENV_KEYS = {'engine', 'kind', 'origin', 'refresh', 'control_pid', 'started_monotonic_ns',
            'lock_acquired_monotonic_ns', 'identity_started_monotonic_ns', 'identity_completed_monotonic_ns',
            'completed_monotonic_ns', 'cache_outcome', 'status', 'ready', 'completed_at'}


def records(service):
    return service.probe_observations.environment_snapshot()[0]


def assert_record(record, *, identity=True):
    assert set(record) == ENV_KEYS
    assert record['control_pid'] == os.getpid()
    assert record['status'] in {'completed', 'failed'}
    assert record['cache_outcome'] in {'not_checked', 'hit', 'miss', 'refresh'}
    assert record['origin'] in {'environment', 'capabilities', 'devices'}
    assert record['engine'] in {'mlx', 'diffusers', 'kokoro'}
    assert record['kind'] in {'text', 'image', 'video', 'audio'}
    fields = ['started_monotonic_ns', 'lock_acquired_monotonic_ns']
    if identity:
        fields += ['identity_started_monotonic_ns', 'identity_completed_monotonic_ns']
    else:
        assert record['identity_started_monotonic_ns'] is record['identity_completed_monotonic_ns'] is None
    fields += ['completed_monotonic_ns']
    times = [record[key] for key in fields]
    assert all(type(value) is int and value > 0 for value in times)
    assert times == sorted(times)
    assert datetime.fromisoformat(record['completed_at']).tzinfo is not None
    assert PRIVATE not in encode(record)


@pytest.mark.parametrize('engine', ['mlx', 'diffusers', 'kokoro'])
@pytest.mark.parametrize('backend', ['bundled', 'external_python'])
def test_cache_and_refresh_keep_identity_and_correlate_actual_probe(service_factory, engine, backend):
    service, _, check = service_factory(engine, backend)
    first = check()
    assert check() == first
    assert check(refresh=True) == first
    calls = records(service)
    assert len(calls) == 3
    assert [item['cache_outcome'] for item in calls] == ['miss', 'hit', 'refresh']
    assert [item['refresh'] for item in calls] == [False, False, True]
    for item in calls:
        assert_record(item)
        assert item['ready'] is True and item['status'] == 'completed'
    probes, omitted = service.probe_observations.snapshot()
    assert omitted == 0 and len(probes) == 2
    for call, probe in zip((calls[0], calls[2]), probes):
        assert probe['control_pid'] == call['control_pid']
        assert call['identity_completed_monotonic_ns'] <= probe['started_monotonic_ns'] <= probe['completed_monotonic_ns'] <= call['completed_monotonic_ns']
    assert not any(key in encode(first) for key in ('monotonic_ns', 'control_pid', 'cache_outcome'))


def test_capabilities_and_devices_include_failed_cache_hit_without_extra_probes(environment_client):
    client, binaries = environment_client
    service = client.app.state.service
    assert not any(capabilities(client).values())
    ready(binaries)
    assert not any(capabilities(client).values())
    assert client.get('/api/v1/devices').json()['items'][0]['ready'] is False
    assert counts(binaries) == dict.fromkeys(binaries, 1)
    calls = records(service)
    assert len(calls) == 7
    assert [item['origin'] for item in calls] == ['capabilities'] * 6 + ['devices']
    assert [item['cache_outcome'] for item in calls] == ['miss'] * 3 + ['hit'] * 4
    assert all(item['ready'] is False for item in calls)
    assert all(capabilities(client, '?refresh=true').values())
    assert counts(binaries) == dict.fromkeys(binaries, 2)
    assert [item['cache_outcome'] for item in records(service)[-3:]] == ['refresh'] * 3


@pytest.mark.parametrize('engine', ['mlx', 'diffusers', 'kokoro'])
@pytest.mark.parametrize('backend', ['bundled', 'external_python'])
def test_changed_executor_identity_is_not_hidden_by_cache(service_factory, engine, backend):
    service, binary, check = service_factory(engine, backend)
    first = check()
    binary.write_text(binary.read_text() + '\n# 固定测试执行器的来源变化\n')
    second = check()
    assert first['digest'] != second['digest']
    assert [item['cache_outcome'] for item in records(service)] == ['miss', 'miss']
    assert len(service.probe_observations.snapshot()[0]) == 2


def test_lock_wait_is_separate_from_identity_and_second_call_uses_cache(service_factory, monkeypatch):
    service, _, check = service_factory()
    entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
    original_identity = service.execution_identity
    identity_calls = []
    def identity():
        identity_calls.append(1)
        if len(identity_calls) == 1:
            entered.set()
            assert release.wait(5)
        return original_identity()
    monkeypatch.setattr(service, 'execution_identity', identity)
    original_observe = service.probe_observations.environment
    @contextmanager
    def observe(*args, **kwargs):
        with original_observe(*args, **kwargs) as record:
            if entered.is_set():
                second_started.set()
            yield record
    monkeypatch.setattr(service.probe_observations, 'environment', observe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(check)
        assert entered.wait(5)
        second = pool.submit(check)
        try:
            assert second_started.wait(5)
            assert not second.done()
        finally:
            release.set()
        assert first.result() == second.result()
    first_call, second_call = records(service)
    assert len(identity_calls) == 2
    assert len(service.probe_observations.snapshot()[0]) == 1
    assert first_call['cache_outcome'] == 'miss' and second_call['cache_outcome'] == 'hit'
    assert second_call['started_monotonic_ns'] < first_call['identity_completed_monotonic_ns'] <= second_call['lock_acquired_monotonic_ns'] <= second_call['identity_started_monotonic_ns']


def test_identity_failure_is_recorded_without_content_and_does_not_poison_lock(service_factory, monkeypatch):
    service, _, check = service_factory()
    original = service.execution_identity
    def fail():
        raise RuntimeError(PRIVATE)
    monkeypatch.setattr(service, 'execution_identity', fail)
    with pytest.raises(RuntimeError, match=PRIVATE):
        check()
    failed = records(service)[0]
    assert_record(failed)
    assert failed['status'] == 'failed' and failed['ready'] is None
    assert failed['cache_outcome'] == 'not_checked'
    assert service.probe_observations.snapshot() == ([], 0)
    monkeypatch.setattr(service, 'execution_identity', original)
    assert check()['ready'] is True


def test_unconfigured_calls_are_bounded_detached_and_diagnostics_do_not_start_checks(environment_client):
    client, _ = environment_client
    service = client.app.state.service
    service.settings.bundled_worker = None
    for _ in range(70):
        assert client.get('/api/v1/devices').status_code == 200
    calls, omitted = service.probe_observations.environment_snapshot()
    assert len(calls) == 64 and omitted == 6
    for item in calls:
        assert_record(item, identity=False)
        assert item['cache_outcome'] == 'not_checked' and item['ready'] is False
    assert service.probe_observations.snapshot() == ([], 0)
    preview = Diagnostics(service).preview({})
    data = preview['diagnostics']
    assert data['environment_observations'] == calls and data['environment_observations_omitted'] == 6
    assert len(encode(data).encode()) < MAX_BYTES
    assert service.probe_observations.environment_snapshot() == (calls, 6)
    calls[0]['origin'] = PRIVATE
    assert PRIVATE not in encode(records(service))
    assert len(data['environment_observations']) == 64
