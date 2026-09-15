"""临时 WAL 库、真实诊断和后台收尾的关闭边界；不读取用户库或运行模型。"""

import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from test_control import Service, Settings, create_app


@pytest.fixture
def service(tmp_path):
    value = Service(Settings(tmp_path / 'library', 'close-fixture-token'))
    yield value
    try:
        value.close()
    finally:
        # 也能回收旧实现的未关闭连接，避免红测自身污染后续用例。
        value.store.db.close()
        value.instance_lock.close()


def assert_instance_locked(service):
    with (service.root / 'control.lock').open('rb') as stream:
        with pytest.raises(BlockingIOError):
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def assert_database_closed(service):
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        service.store.db.execute('SELECT 1')
    assert service.shutdown_complete and service.instance_lock.closed
    assert not service.store.path.with_name('control.sqlite3-wal').exists()
    assert not service.store.path.with_name('control.sqlite3-shm').exists()


def record_final_state(service):
    with service.store.transaction():
        service.store.remember('shutdown-fixture', 'final-write', {}, {'status': 'finished'})


def assert_final_state_persisted(service):
    reopened = Service(service.settings)
    try:
        assert reopened.store.replay('shutdown-fixture', 'final-write', {}) == {'status': 'finished'}
        assert reopened.store.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        reopened.close()
        reopened.store.db.close()


def test_api_shutdown_closes_wal_before_unlock_and_preserves_real_diagnostic(tmp_path):
    target = tmp_path / 'diagnostic-export'
    target.mkdir()
    settings = Settings(tmp_path / 'library', 'close-fixture-token', export_roots=[target])
    app = create_app(settings)
    service = app.state.service
    try:
        with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer close-fixture-token'}) as client:
            preview_response = client.post('/api/v1/diagnostics/previews', json={})
            assert preview_response.status_code == 200
            preview = preview_response.json()
            result = client.post('/api/v1/diagnostics/exports', json={'preview_id': preview['id'], 'target_dir': str(target)},
                                 headers={'Idempotency-Key': 'real-diagnostic-export'})
            assert result.status_code == 200
            exported = result.json()
            assert exported['status'] == 'succeeded'
            archive = Path(exported['saved_path'])
            assert hashlib.sha256(archive.read_bytes()).hexdigest() == exported['archive_sha256']
            assert service.store.path.with_name('control.sqlite3-wal').stat().st_size > 0
            assert_instance_locked(service)
        # ASGI lifespan 实际调用 close；保留旧连接引用，不能靠 GC 冒充关闭成功。
        assert_database_closed(service)
        service.close()
        service.store.close()
        reopened = Service(settings)
        try:
            saved = reopened.diagnostics.get(preview['id'])
            assert saved['status'] == 'succeeded'
            assert saved['archive_sha256'] == exported['archive_sha256']
            assert saved['preview_digest'] == preview['preview_digest']
            assert reopened.store.list('attempt') == []
            assert reopened.store.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        finally:
            reopened.close()
            reopened.store.db.close()
    finally:
        service.close()
        service.store.db.close()
        service.instance_lock.close()


def test_last_worker_cannot_close_database_during_close_body(service, monkeypatch):
    body_entered, body_may_finish = threading.Event(), threading.Event()
    worker_may_finish, worker_finished = threading.Event(), threading.Event()
    close_returned = [threading.Event(), threading.Event()]
    failures = []

    def blocked_body():
        body_entered.set()
        assert body_may_finish.wait(5)

    def worker():
        try:
            assert worker_may_finish.wait(5)
            record_final_state(service)
            with service.store.lock:
                service.threads.discard(threading.current_thread())
            service._release_if_idle()
        except BaseException as error:
            failures.append(error)
        finally:
            worker_finished.set()

    def close(index):
        try:
            service.close()
        except BaseException as error:
            failures.append(error)
        finally:
            close_returned[index].set()

    worker_thread = threading.Thread(target=worker)
    closers = [threading.Thread(target=close, args=(index,)) for index in range(2)]
    with monkeypatch.context() as patch:
        patch.setattr(service.dataset_splits, 'close', blocked_body)
        service.threads.add(worker_thread)
        worker_thread.start()
        try:
            closers[0].start()
            assert body_entered.wait(5)
            closers[1].start()
            worker_may_finish.set()
            assert worker_finished.wait(5)
            assert not failures
            assert not service.shutdown_complete
            assert service.store.db.execute('SELECT 1').fetchone()[0] == 1
            assert_instance_locked(service)
            assert not any(event.is_set() for event in close_returned)
        finally:
            worker_may_finish.set()
            body_may_finish.set()
            worker_thread.join(5)
            for thread in closers:
                if thread.ident is not None:
                    thread.join(5)
    assert not worker_thread.is_alive() and not any(thread.is_alive() for thread in closers)
    assert not failures
    assert_database_closed(service)
    service.close()
    assert_final_state_persisted(service)


def test_delayed_worker_keeps_database_and_lock_until_its_final_write(service):
    may_finish, finished = threading.Event(), threading.Event()
    failures = []

    def worker():
        try:
            assert may_finish.wait(10)
            record_final_state(service)
            with service.store.lock:
                service.threads.discard(threading.current_thread())
            service._release_if_idle()
        except BaseException as error:
            failures.append(error)
        finally:
            finished.set()

    thread = threading.Thread(target=worker)
    service.threads.add(thread)
    thread.start()
    try:
        service.close()  # 真实等待现有三秒 join 预算，后台仍待写入。
        assert not service.shutdown_complete and thread.is_alive()
        assert service.store.db.execute('SELECT 1').fetchone()[0] == 1
        assert_instance_locked(service)
    finally:
        may_finish.set()
        assert finished.wait(5)
        thread.join(5)
    assert not failures and not thread.is_alive()
    assert_database_closed(service)
    assert_final_state_persisted(service)


def test_database_close_failure_retains_instance_lock_and_can_retry(service, monkeypatch):
    record_final_state(service)

    class FailFirstClose:
        def __init__(self, connection):
            self.connection = connection
            self.close_calls = 0

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def close(self):
            self.close_calls += 1
            if self.close_calls == 1:
                raise OSError('受控数据库关闭失败')
            self.connection.close()

    connection = FailFirstClose(service.store.db)
    with monkeypatch.context() as patch:
        patch.setattr(service.store, 'db', connection)
        with pytest.raises(OSError, match='受控数据库关闭失败'):
            service.close()
        assert not service.shutdown_complete
        assert service.store.db.execute('SELECT 1').fetchone()[0] == 1
        assert_instance_locked(service)
        service.close()
        service.close()
        service.store.close()
        assert connection.close_calls == 2
    assert_database_closed(service)
    assert_final_state_persisted(service)


def test_close_body_failure_does_not_allow_background_unlock(service, monkeypatch):
    with monkeypatch.context() as patch:
        def fail_body():
            raise OSError('受控后台停止失败')
        patch.setattr(service.dataset_splits, 'close', fail_body)
        with pytest.raises(OSError, match='受控后台停止失败'):
            service.close()
        service._release_if_idle()
        assert not service.shutdown_complete
        assert service.store.db.execute('SELECT 1').fetchone()[0] == 1
        assert_instance_locked(service)
    service.close()
    assert_database_closed(service)


def test_actual_unstopped_owned_child_prevents_database_close_and_unlock(service, monkeypatch):
    child = subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(30)'], start_new_session=True)
    service.dataset_splits.processes['shutdown-fixture'] = child
    try:
        with monkeypatch.context() as patch:
            # 模拟已报告但尚未停止的后台进程，保留真实 Popen 的 poll 与组检查。
            patch.setattr(service.dataset_splits, 'close', lambda: None)
            service.close()
            assert child.poll() is None and not service.shutdown_complete
            assert service.store.db.execute('SELECT 1').fetchone()[0] == 1
            assert_instance_locked(service)
    finally:
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)
    service.close()
    assert_database_closed(service)
