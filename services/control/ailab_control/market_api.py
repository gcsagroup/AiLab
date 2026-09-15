"""受控数据市场 HTTP 边界与可回收后台下载；不配置提供方地址。"""

import threading
from typing import Literal

from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field

from .storage import Fault, digest, now


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Empty(Strict):
    pass


class ContextInput(Strict):
    expected_revision: int = Field(ge=1)
    step: Literal['data']


class AccessInput(Strict):
    version_id: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=2000, pattern=r'\S')
    user_statement: str = Field(min_length=1, max_length=2000, pattern=r'\S')


class DownloadInput(Strict):
    version_id: str = Field(min_length=1, max_length=200)
    user_statement: str = Field(min_length=1, max_length=2000, pattern=r'\S')
    access_id: str | None = Field(default=None, min_length=1, max_length=200)


class UseInput(Strict):
    dataset_id: str = Field(min_length=1, max_length=200)


def schedule_download(service, download_id, key, resume=False):
    """先持久化同一命令的排程，再启动被 Service 跟踪的唯一线程。"""
    store = service.store
    scope = ('market-http-resume:' if resume else 'market-http-start:') + download_id
    payload = {}
    execution_key = 'http-' + digest({'scope': scope, 'key': key})

    def execute():
        try:
            service.market.execute_download(download_id, execution_key, preserve_cancellation=True)
        except Exception as error:
            with store.transaction():
                record = store.get('market-download', download_id)
                if record.get('active_execution_key') == execution_key and record['state'] not in {'completed', 'cancelled'}:
                    record.update(state='failed', complete=False, error={'code': error.code if isinstance(error, Fault) else 'MARKET_TRANSFER_FAILED', 'message': str(error)[:1000]}, updated_at=now())
                    store.put('market-download', record)
        finally:
            with store.transaction():
                record = store.get('market-download', download_id)
                if record.get('active_execution_key') == execution_key:
                    record['active_execution_key'] = None
                    store.put('market-download', record)
                service.threads.discard(threading.current_thread())
            service._release_if_idle()

    with store.lock:
        if service.closed.is_set():
            raise Fault('SERVICE_STOPPING', '控制服务正在关闭，未安排新的下载。', 503)
        with store.transaction():
            if store.replay(scope, key, payload):
                return store.get('market-download', download_id)
            record = store.get('market-download', download_id)
            if service.closed.is_set():
                raise Fault('SERVICE_STOPPING', '控制服务正在关闭，未安排新的下载。', 503)
            live = any(thread.name == 'market-download-' + download_id for thread in service.threads)
            if not resume and (record['state'] != 'queued' or record.get('active_execution_key')):
                store.remember(scope, key, payload, record)
                return record
            if live or (resume and record['state'] in {'queued', 'downloading'}):
                raise Fault('MARKET_DOWNLOAD_BUSY', '原下载仍在运行或停止中，请等待状态确定。', 409)
            if resume and record['state'] not in {'failed', 'cancelled'}:
                raise Fault('MARKET_DOWNLOAD_COMPLETE', '此下载已经完整，无需重复下载。', 409)
            record.update(state='queued', cancel_requested=False, active_execution_key=execution_key, updated_at=now())
            store.put('market-download', record)
            thread = threading.Thread(target=execute, daemon=True, name='market-download-' + download_id)
            service.threads.add(thread)
            store.remember(scope, key, payload, record)
    try:
        thread.start()
    except Exception as error:
        with store.transaction():
            service.threads.discard(thread)
            record = store.get('market-download', download_id)
            record.update(state='failed', complete=False, active_execution_key=None, error={'code': 'MARKET_THREAD_START_FAILED', 'message': '下载线程未能启动，原文件保留。'}, updated_at=now())
            store.put('market-download', record)
        service._release_if_idle()
        raise Fault('MARKET_THREAD_START_FAILED', '下载线程未能启动，请查看原记录后明确重试。', 503) from error
    return record


def mount_market(app, service):
    if getattr(app.state, 'market_routes_mounted', False):
        return
    app.state.market_routes_mounted = True

    @app.get('/api/v1/market/sources')
    def sources():
        return {'items': service.market.sources()}

    @app.get('/api/v1/market/catalog')
    def catalog(project_id: str, provider_id: str):
        return service.market.browse(project_id, provider_id)

    @app.post('/api/v1/tasks/{task_id}/market-contexts')
    def context(task_id: str, payload: ContextInput, idempotency_key: str | None = Header(default=None)):
        return service.market.enter(task_id, payload.model_dump(), idempotency_key)

    @app.get('/api/v1/market/versions/{version_id}/activity')
    def activity(version_id: str):
        return service.market.activity(version_id)

    @app.post('/api/v1/market/access-requests')
    def access(payload: AccessInput, idempotency_key: str | None = Header(default=None)):
        return service.market.request_access(payload.version_id, payload.model_dump(exclude={'version_id'}), idempotency_key)

    @app.post('/api/v1/market/access-requests/{access_id}/refresh')
    def refresh(access_id: str, payload: Empty):
        return service.market.refresh_access(access_id)

    @app.post('/api/v1/market/downloads')
    def download(payload: DownloadInput, idempotency_key: str | None = Header(default=None)):
        record = service.market.start_download(payload.version_id, payload.model_dump(exclude={'version_id'}, exclude_none=True), idempotency_key)
        return schedule_download(service, record['id'], idempotency_key)

    @app.get('/api/v1/market/downloads/{download_id}')
    def current(download_id: str):
        return service.store.get('market-download', download_id)

    @app.post('/api/v1/market/downloads/{download_id}/cancel')
    def cancel(download_id: str, payload: Empty, idempotency_key: str | None = Header(default=None)):
        return service.market.cancel_download(download_id, idempotency_key)

    @app.post('/api/v1/market/downloads/{download_id}/resume')
    def resume(download_id: str, payload: Empty, idempotency_key: str | None = Header(default=None)):
        return schedule_download(service, download_id, idempotency_key, resume=True)

    @app.post('/api/v1/market/downloads/{download_id}/datasets')
    def register(download_id: str, payload: Empty, idempotency_key: str | None = Header(default=None)):
        return service.public(service.market.register_new_dataset(download_id, idempotency_key))

    @app.post('/api/v1/market/contexts/{context_id}/use')
    def use(context_id: str, payload: UseInput, idempotency_key: str | None = Header(default=None)):
        return service.market.use_for_task(context_id, payload.model_dump(), idempotency_key)
