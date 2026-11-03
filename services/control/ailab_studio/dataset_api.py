"""Authenticated Studio dataset-market API; credentials never enter stored records."""
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from .datasets import preview, TRAINING

Provider = Literal['huggingface', 'kaggle']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Credentials(Input):
    provider: Provider
    token: str = Field(max_length=4096)
    username: str = Field(default='', max_length=200)


class Search(Input):
    provider: Provider
    query: str = Field(default='', max_length=200)
    page: int = Field(default=1, ge=1, le=5)


class Detail(Input):
    provider: Provider
    dataset: str = Field(max_length=200)
    revision: str = Field(default='', max_length=150)


class RemoteFile(Input):
    selection_id: str = Field(max_length=40)
    path: str = Field(max_length=500)


class Download(Input):
    selection_id: str = Field(max_length=40)
    files: list[str] = Field(min_length=1, max_length=500)
    category: str = Field(default='general', max_length=40)
    purpose: str = Field(default='research', max_length=100)


class LocalImport(Input):
    path: str = Field(min_length=1, max_length=4096)
    category: str = Field(default='local', max_length=40)
    purpose: str = Field(default='research', max_length=100)


class LocalFile(Input):
    path: str = Field(max_length=500)


class Remove(Input):
    delete_files: bool = False


def router(studio):
    api = APIRouter(prefix='/api/v1/studio/datasets')
    market = studio.datasets

    @api.get('/sources')
    def sources(): return market.sources.status()

    @api.post('/credentials')
    def credentials(payload: Credentials): return market.sources.configure(payload.provider, payload.token, payload.username)

    @api.post('/search')
    def search(payload: Search): return market.sources.search(payload.provider, payload.query, payload.page)

    @api.post('/detail')
    def detail(payload: Detail): return market.detail(payload.provider, payload.dataset, payload.revision)

    @api.post('/preview')
    def remote_preview(payload: RemoteFile): return market.remote_preview(payload.selection_id, payload.path)

    @api.get('/downloads')
    def downloads(): return {'items': market.downloads()}

    @api.post('/downloads')
    def download(payload: Download): return market.start(payload.selection_id, payload.files, payload.category, payload.purpose)

    @api.post('/downloads/{key}/{action}')
    def control(key: str, action: Literal['pause', 'resume', 'cancel', 'cleanup']):
        return market.cleanup(key) if action == 'cleanup' else market.control(key, action)

    @api.get('/local')
    def local():
        import shutil
        from pathlib import Path
        root = Path(studio.paths()['datasets'])
        try: free = shutil.disk_usage(root).free
        except OSError: free = None
        return {'items': studio.store.list('dataset', 100000), 'directory': str(root), 'free_bytes': free}

    @api.post('/local/import')
    def local_import(payload: LocalImport): return market.import_local(payload.path, payload.category, payload.purpose)

    @api.post('/local/{key}/preview')
    def local_preview(key: str, payload: LocalFile): return preview(market.local_file(key, payload.path))

    @api.post('/local/{key}/use')
    def use(key: str, payload: LocalFile):
        file = market.local_file(key, payload.path)
        if file.suffix.lower() not in TRAINING: raise ValueError('当前训练器仅支持 JSON、JSONL 和 Parquet；请先转换或解压')
        return {'path': str(file)}

    @api.post('/local/{key}/remove')
    def remove(key: str, payload: Remove): return market.remove(key, payload.delete_files)

    return api
