"""Studio market integration: actual durable queue and files, deterministic provider I/O."""
import hashlib
import io
import json
from email.message import Message
from pathlib import Path
import sys
import time
import threading
import urllib.request

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/control'))
from ailab_studio.__main__ import create_app
from ailab_studio.dataset_sources import Redirects, Sources, relative, trusted_url
from ailab_studio.datasets import safe_path

BODY = b'{"messages":[{"role":"user","content":"Hi"},{"role":"assistant","content":"Hello"}]}\n'
SHA = hashlib.sha256(BODY).hexdigest()


class Response(io.BytesIO):
    def __init__(self, data, status=200, **headers):
        super().__init__(data); self.status = status; self.headers = Message()
        for key, value in headers.items(): self.headers[key.replace('_', '-')] = str(value)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr('ailab_studio.service.hardware', lambda: {'device': 'cpu', 'gpus': []})
    app = create_app(tmp_path / 'state', 'secret')
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer secret'}) as c:
        c.market = app.state.studio.datasets
        c.studio = app.state.studio
        yield c


def selection(client, checksum=SHA):
    item = {'id': 'fixture', 'provider': 'huggingface', 'dataset': 'owner/data', 'title': 'Dataset', 'revision': 'a' * 40,
            'license': 'mit', 'source_url': 'https://huggingface.co/datasets/owner/data',
            'files': [{'path': 'train.jsonl', 'size': len(BODY), 'expected_sha256': checksum}]}
    client.studio.store.put('dataset-selection', item)
    return item


def start(client):
    r = client.post('/api/v1/studio/datasets/downloads', json={'selection_id': 'fixture', 'files': ['train.jsonl'], 'category': 'sft', 'purpose': 'training'})
    assert r.status_code == 200, r.text
    return r.json()


def wait(client, key):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        row = client.studio.store.get('dataset-download', key)
        if row['state'] in {'completed', 'failed', 'paused', 'cancelled'}: return row
        time.sleep(.02)
    raise AssertionError(row)


def test_market_download_to_local_to_sft_lineage_and_restart(client, monkeypatch, tmp_path):
    selection(client)
    monkeypatch.setattr(client.market.sources, 'open', lambda *a: Response(BODY, Content_Length=len(BODY), ETag='fixed'))
    job = wait(client, start(client)['id'])
    assert job['state'] == 'completed', job
    path = Path(job['directory']) / 'train.jsonl'
    assert path.read_bytes() == BODY
    local = client.get('/api/v1/studio/datasets/local').json()['items'][0]
    assert local['files'][0]['sha256'] == SHA
    assert client.post(f'/api/v1/studio/datasets/local/{local["id"]}/preview', json={'path': 'train.jsonl'}).json()['text'] == BODY.decode()
    used = client.post(f'/api/v1/studio/datasets/local/{local["id"]}/use', json={'path': 'train.jsonl'}).json()['path']
    assert used == str(path)
    assert any(a['path'] == used for a in client.get('/api/v1/studio/assets').json()['datasets'])
    model = tmp_path / 'model'; model.mkdir()
    (model / 'config.json').write_text('{"model_type":"llama"}')
    (model / 'model.safetensors').write_bytes(b'fixture')
    monkeypatch.setattr(client.studio.runtimes, 'resolve', lambda _: {'path': str(tmp_path), 'version': 'fixture'})
    monkeypatch.setattr(client.studio, 'launch', lambda kind, config, runtime: {'kind': kind, 'config': config})
    result = client.post('/api/v1/studio/sft', json={'model': str(model), 'dataset': used}).json()
    assert result['config']['dataset_reference']['sha256'] == SHA
    assert result['config']['dataset_reference']['provenance']['revision'] == 'a' * 40
    assert result['config']['dataset_reference']['dataset_id'] == job['id']
    path.write_bytes(b'changed')
    assert client.post('/api/v1/studio/sft', json={'model': str(model), 'dataset': used}).status_code == 400


def test_resume_honors_range_and_restarts_when_ignored(client, monkeypatch):
    selection(client)
    seen = []
    def opener(provider, url, headers):
        seen.append(headers)
        if len(seen) <= 3: raise ValueError('network interrupted')
        offset = 7
        return Response(BODY[offset:], 206, Content_Range=f'bytes {offset}-{len(BODY)-1}/{len(BODY)}', ETag='fixed')
    monkeypatch.setattr(client.market.sources, 'open', opener)
    job = wait(client, start(client)['id'])
    assert job['state'] == 'failed'
    partial = Path(job['directory']) / 'train.jsonl.ailab-part'; partial.write_bytes(BODY[:7])
    client.post(f'/api/v1/studio/datasets/downloads/{job["id"]}/resume')
    final = wait(client, job['id'])
    assert final['state'] == 'completed', final
    assert seen[-1]['Range'] == 'bytes=7-'
    assert (Path(job['directory']) / 'train.jsonl').read_bytes() == BODY


def test_ignored_range_never_appends_duplicate_bytes(client, monkeypatch):
    selection(client)
    monkeypatch.setattr(client.market.sources, 'open', lambda *a: (_ for _ in ()).throw(ValueError('offline')))
    job = wait(client, start(client)['id'])
    (Path(job['directory']) / 'train.jsonl.ailab-part').write_bytes(BODY[:9])
    monkeypatch.setattr(client.market.sources, 'open', lambda *a: Response(BODY, Content_Length=len(BODY)))
    client.post(f'/api/v1/studio/datasets/downloads/{job["id"]}/resume')
    assert wait(client, job['id'])['state'] == 'completed'
    assert (Path(job['directory']) / 'train.jsonl').read_bytes() == BODY


def test_checksum_failure_is_not_registered(client, monkeypatch):
    selection(client, '0' * 64)
    monkeypatch.setattr(client.market.sources, 'open', lambda *a: Response(BODY, Content_Length=len(BODY)))
    job = wait(client, start(client)['id'])
    assert job['state'] == 'failed'
    assert 'SHA256' in job['error']
    assert client.get('/api/v1/studio/datasets/local').json()['items'] == []
    assert not (Path(job['directory']) / 'train.jsonl').exists()


def test_local_import_preview_cleanup_preserves_source_and_blocks_traversal(client, tmp_path):
    file = tmp_path / 'local.jsonl'; file.write_bytes(BODY)
    response = client.post('/api/v1/studio/datasets/local/import', json={'path': str(file)})
    item = response.json(); assert response.status_code == 200
    assert client.post(f'/api/v1/studio/datasets/local/{item["id"]}/preview', json={'path': '../local.jsonl'}).status_code == 400
    assert client.post(f'/api/v1/studio/datasets/local/{item["id"]}/remove', json={'delete_files': True}).status_code == 400
    assert client.post(f'/api/v1/studio/datasets/local/{item["id"]}/remove', json={'delete_files': False}).status_code == 200
    assert file.read_bytes() == BODY


def test_clean_download_checks_active_training(client, monkeypatch):
    selection(client)
    monkeypatch.setattr(client.market.sources, 'open', lambda *a: Response(BODY, Content_Length=len(BODY)))
    job = wait(client, start(client)['id'])
    assert job['state'] == 'completed', job
    client.studio.store.put('job', {'id': 'busy', 'state': 'running', 'kind': 'sft', 'config': {'dataset': str(Path(job['directory']) / 'train.jsonl')}, 'created_at': time.time()})
    assert client.post(f'/api/v1/studio/datasets/downloads/{job["id"]}/cleanup').status_code == 400
    client.studio.store.delete('job', 'busy')
    assert client.post(f'/api/v1/studio/datasets/downloads/{job["id"]}/cleanup').status_code == 200
    assert not Path(job['directory']).exists()


def test_credentials_stay_in_memory_and_provider_auth_is_not_redirected(client, monkeypatch):
    value = 'fixture-token-do-not-persist'
    assert client.post('/api/v1/studio/datasets/credentials', json={'provider': 'huggingface', 'token': value}).status_code == 200
    assert client.market.sources.headers('huggingface')['Authorization'] == 'Bearer ' + value
    assert value.encode() not in (client.studio.root / 'studio.sqlite3').read_bytes()
    req = urllib.request.Request('https://huggingface.co/file', headers={'Authorization': 'Bearer ' + value, 'Range': 'bytes=7-'})
    redirected = Redirects().redirect_request(req, None, 302, '', {}, 'https://cdn-lfs.hf.co/file')
    assert not redirected.has_header('Authorization')
    assert redirected.get_header('Range') == 'bytes=7-'
    for url in ['http://huggingface.co/file', 'https://localhost/file', 'https://huggingface.co.evil.example/file', 'https://huggingface.co:444/file']:
        with pytest.raises(ValueError): trusted_url(url)


def test_search_version_pinning_and_kaggle_versioned_archive(monkeypatch):
    sources = Sources()
    def api(provider, path, query=None):
        if path.endswith('/refs'): return {'branches': [{'name': 'main'}], 'tags': [{'name': 'v1'}]}
        if path.startswith('/api/datasets/owner/data'): return {'sha': 'a' * 40, 'cardData': {'license': 'mit'}, 'siblings': [{'rfilename': 'train.jsonl', 'size': len(BODY), 'lfs': {'sha256': SHA}}]}
        if path.startswith('/api/v1/datasets/view/'): return {'title': 'Data', 'currentVersionNumber': 3, 'versions': [{'versionNumber': 2}], 'licenseName': 'CC0'}
        return []
    monkeypatch.setattr(sources, 'json', api)
    info = sources.detail('huggingface', 'owner/data', 'v1')
    assert '/resolve/' + 'a' * 40 + '/train.jsonl' in sources.file_url(info, 'train.jsonl')
    assert info['files'][0]['expected_sha256'] == SHA
    kaggle = sources.detail('kaggle', 'owner/data', '2')
    assert sources.file_url(kaggle, 'dataset.zip').endswith('datasetVersionNumber=2')
    assert kaggle['files'][0]['path'] == 'dataset.zip'
    with pytest.raises(ValueError): relative('../escape')


def test_reject_unknown_file_and_directory_escape(client):
    selection(client)
    assert client.post('/api/v1/studio/datasets/downloads', json={'selection_id': 'fixture', 'files': ['../unknown']}).status_code == 400
    assert client.post('/api/v1/studio/datasets/downloads', json={'selection_id': 'fixture', 'files': ['train.jsonl'], 'category': '../escape'}).status_code == 400
    with pytest.raises(ValueError): safe_path(client.studio.root, '../outside')


def test_pause_and_resume_download_keeps_queue_record(client, monkeypatch):
    selection(client)
    entered = threading.Event(); release = threading.Event()
    def opener(*args):
        entered.set(); release.wait(5)
        return Response(BODY, Content_Length=len(BODY))
    monkeypatch.setattr(client.market.sources, 'open', opener)
    job = start(client)
    assert entered.wait(3)
    assert client.post(f'/api/v1/studio/datasets/downloads/{job["id"]}/pause').status_code == 200
    release.set()
    assert wait(client, job['id'])['state'] == 'paused'
    assert client.post(f'/api/v1/studio/datasets/downloads/{job["id"]}/resume').status_code == 200
    assert wait(client, job['id'])['state'] == 'completed'


def test_worker_rechecks_queued_file_identity(tmp_path):
    sys.path.insert(0, str(ROOT / 'services/control/ailab_studio/workers'))
    from sft import verify_dataset_reference
    file = tmp_path / 'training.jsonl'; file.write_bytes(BODY)
    config = {'dataset': str(file), 'dataset_reference': {'bytes': len(BODY), 'sha256': SHA}}
    verify_dataset_reference(config)
    file.write_bytes(b'changed while queued')
    with pytest.raises(ValueError, match='排队后'): verify_dataset_reference(config)


def test_sft_handles_new_tokenizer_default_mapping_and_masks_only_answer():
    sys.path.insert(0, str(ROOT / 'services/control/ailab_studio/workers'))
    from sft import encode_row
    class Tokenizer:
        chat_template = 'fixture'
        def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=False, return_dict=True):
            ids = []
            for m in messages:
                ids += [10 if m['role'] == 'user' else 20, 30, 40]
            if add_generation_prompt: ids.append(20)
            return {'input_ids': ids} if return_dict else ids
    row = {'messages': [{'role': 'user', 'content': 'Question'}, {'role': 'assistant', 'content': 'Answer'}]}
    result = encode_row(row, Tokenizer(), {'max_length': 32, 'loss_scope': 'assistant'})
    assert result['input_ids'] == [10, 30, 40, 20, 30, 40]
    assert result['labels'] == [-100, -100, -100, -100, 30, 40]
