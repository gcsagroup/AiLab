"""远端委派登记回滚：临时真实 SQLite、回环传输与显式假执行器。"""

import errno
import time

import pytest

from test_control import rig, wait_attempt
from test_remote_transfers import remote_rig, submit_transfer, executions, LoopbackClient, ProtocolError
from ailab_control.storage import Fault


@pytest.mark.parametrize('failure', ['fault', 'oserror'])
def test_remote_recollection_registration_rollback_keeps_original_terminal(remote_rig, monkeypatch, failure):
    client, service, _server, *_ = remote_rig
    original_collect = LoopbackClient.collect
    transfer_failures = []

    def collect(self, *args, **kwargs):
        if not transfer_failures:
            transfer_failures.append(True)
            raise ProtocolError('REMOTE_UNAVAILABLE', '受控首次传输故障。', 503)
        return original_collect(self, *args, **kwargs)

    monkeypatch.setattr(LoopbackClient, 'collect', collect)
    attempt, _ = submit_transfer(remote_rig)
    before = wait_attempt(client, attempt['id'], timeout=15)
    assert before['state'] == 'failed' and before['terminal_reason'] == 'REMOTE_UNAVAILABLE'
    # 首次同步收尾已经提交终态，但 finally 释放远端收集门禁稍晚。
    deadline = time.monotonic() + 5
    while attempt['id'] in service.remote_execution.collecting and time.monotonic() < deadline:
        time.sleep(.01)
    assert attempt['id'] not in service.remote_execution.collecting
    before = service.store.get('attempt', attempt['id'])
    collections_before = service.store.list('collection')
    original_event = service.store.event
    faults = []
    original_error = (Fault('CONTROLLED_REGISTRATION_FAULT', '受控登记事务故障。', 500)
                      if failure == 'fault' else OSError(errno.ENOSPC, '受控登记事务故障。'))

    def event(attempt, kind, payload):
        result = original_event(attempt, kind, payload)
        if kind == 'collection_changed' and payload['state'] == 'succeeded' and not faults:
            assert service.store.list('artifact'), '故障须发生在实际 artifact INSERT 后'
            faults.append(attempt['id'])
            raise original_error
        return result

    monkeypatch.setattr(service.store, 'event', event)
    payload = {'expected_collection_version': before['collection_version'],
               'manifest_digest': before['output_manifest_ref']['digest']}
    raised = None
    try:
        service.collect(attempt['id'], payload, 'manual-registration-retry')
    except (Fault, OSError) as error:
        raised = error
    after = service.store.get('attempt', attempt['id'])
    collections_after = service.store.list('collection')
    assert faults == [attempt['id']]
    assert not service.store.list('artifact')
    assert after['collection_state'] == 'failed'
    keys = ('state', 'state_version', 'terminal_reason', 'finished_at')
    # 汇总断言同时展示原终态被覆盖、额外记录和原异常被吞掉。
    observed = {
        'terminal': tuple(after[key] for key in keys),
        'new_collections': len(collections_after) - len(collections_before),
        'version_delta': after['collection_version'] - before['collection_version'],
        'original_error_rethrown': raised is original_error,
    }
    expected = {
        'terminal': tuple(before[key] for key in keys),
        'new_collections': 1,
        'version_delta': 2,
        'original_error_rethrown': True,
    }
    assert observed == expected
    assert service.store.db.execute('SELECT COUNT(*) FROM commands WHERE scope=? AND key=?',
                                    ('collect:' + attempt['id'], 'manual-registration-retry')).fetchone()[0] == 0
    assert_retry_success(service, _server, after)


def test_remote_manual_transfer_failure_keeps_original_terminal(remote_rig, monkeypatch):
    client, service, _server, *_ = remote_rig
    failures = []
    original_collect = LoopbackClient.collect

    def collect(self, *args, **kwargs):
        code = 'REMOTE_UNAVAILABLE' if not failures else 'REMOTE_INTEGRITY_FAILED'
        failures.append(code)
        raise ProtocolError(code, '受控原清单补传故障。', 503)

    monkeypatch.setattr(LoopbackClient, 'collect', collect)
    attempt, _ = submit_transfer(remote_rig)
    wait_attempt(client, attempt['id'], timeout=15)
    deadline = time.monotonic() + 5
    while attempt['id'] in service.remote_execution.collecting and time.monotonic() < deadline:
        time.sleep(.01)
    assert attempt['id'] not in service.remote_execution.collecting
    before = service.store.get('attempt', attempt['id'])
    assert before['terminal_reason'] == 'REMOTE_UNAVAILABLE'
    count = len(service.store.list('collection'))
    payload = {'expected_collection_version': before['collection_version'],
               'manifest_digest': before['output_manifest_ref']['digest']}
    receipt = service.collect(attempt['id'], payload, 'manual-transfer-retry')
    after = service.store.get('attempt', attempt['id'])
    assert receipt['state'] == 'failed' and receipt['error']['code'] == 'REMOTE_INTEGRITY_FAILED'
    assert len(service.store.list('collection')) == count + 1
    assert after['collection_version'] == before['collection_version'] + 1
    assert not service.store.list('artifact')
    keys = ('state', 'state_version', 'terminal_reason', 'finished_at')
    assert tuple(after[key] for key in keys) == tuple(before[key] for key in keys)
    assert service.collect(attempt['id'], payload, 'manual-transfer-retry') == receipt
    assert failures == ['REMOTE_UNAVAILABLE', 'REMOTE_INTEGRITY_FAILED']
    monkeypatch.setattr(LoopbackClient, 'collect', original_collect)
    assert_retry_success(service, _server, after)


def assert_retry_success(service, server, before):
    payload = {'expected_collection_version': before['collection_version'],
               'manifest_digest': before['output_manifest_ref']['digest']}
    receipt = service.collect(before['id'], payload, 'repaired-recollection')
    assert receipt['state'] == 'succeeded'
    after = service.store.get('attempt', before['id'])
    keys = ('state', 'state_version', 'terminal_reason', 'finished_at')
    assert tuple(after[key] for key in keys) == tuple(before[key] for key in keys)
    collections = service.store.list('collection')
    events = service.store.events(before['id'], 0, 1000)
    assert service.collect(before['id'], payload, 'repaired-recollection') == receipt
    assert service.store.list('collection') == collections
    assert service.store.events(before['id'], 0, 1000) == events
    assert len(service.store.list('artifact')) == 1
    assert len(executions(server)) == 1
