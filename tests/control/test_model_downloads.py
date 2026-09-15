"""固定模型下载的真实 HTTP、续传、取消、版本和独立资产验证。"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
import urllib.request

import pytest

from test_control import rig, make_model, post
from ailab_control.assets import model_manifest
from ailab_control.storage import Fault, digest
import ailab_control.model_downloads as module


@pytest.fixture
def transfer(rig, monkeypatch):
    client, service, source, _ = rig
    root = make_model(source / '固定公开下载夹具')
    (root / 'README.md').write_bytes(b'bounded fixture\n' * 180000)
    manifest = model_manifest(root)['manifest']
    monkeypatch.setattr(module, 'FILES', manifest)
    state = {'requests': [], 'ranges': [], 'cut': False, 'corrupt': False, 'pause': False, 'release': threading.Event(), 'sent': threading.Event()}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = self.path.removeprefix('/')
            if name not in {p['path'] for p in manifest}: self.send_error(404); return
            raw = (root / name).read_bytes()
            match = re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers.get('Range', ''))
            if not match: self.send_error(400); return
            offset, end = map(int, match.groups())
            state['requests'].append((name, offset))
            state['ranges'].append((name, offset, end))
            full = name == 'README.md' and state.get('full_response')
            body = raw if full else raw[offset:end+1]
            length = len(body) + (state.get('length_delta', 0) if name == 'README.md' else 0)
            self.send_response(200 if full else 206); self.send_header('Content-Length', str(length))
            start_delta, end_delta, total_delta = state.get('range_delta', (0, 0, 0)) if name == 'README.md' else (0, 0, 0)
            if not full: self.send_header('Content-Range', f'bytes {offset+start_delta}-{end+end_delta}/{len(raw)+total_delta}')
            self.end_headers()
            if state['corrupt'] and body: body = bytes([body[0] ^ 1]) + body[1:]
            if name == 'README.md' and state['cut'] and offset >= state.get('cut_at', 0):
                state['cut'] = False; self.wfile.write(body[:1048576]); self.wfile.flush(); self.close_connection = True; return
            if name == 'README.md' and state['pause']:
                self.wfile.write(body[:1048576]); self.wfile.flush(); state['sent'].set(); state['release'].wait(5); body=body[1048576:]
            try: self.wfile.write(body)
            except (ConnectionError, BrokenPipeError): pass
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    class TestSource:
        def open(self, name, offset, end):
            return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}/{name}', headers={'Range':f'bytes={offset}-{end}'}), timeout=5)
    service.model_downloads.source = TestSource()
    project = post(client, '/projects', {'name':'模型准备验收'})
    body = {'project_id':project['id'], 'catalog_id':module.CATALOG_ID, 'manifest_digest':digest(manifest)}
    yield client, service, root, manifest, state, body
    state['release'].set(); server.shutdown();server.server_close();thread.join(2)


def wait(client, identifier, predicate=lambda x:x['state'] not in module.ACTIVE):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        record=client.get('/api/v1/model-downloads/'+identifier).json()
        if predicate(record):return record
        time.sleep(.01)
    raise AssertionError(record)


def test_real_download_register_idempotency_and_original_bytes(transfer):
    client, service, root, manifest, state, body = transfer
    record=post(client, '/model-downloads', body, 'prepare')
    assert post(client, '/model-downloads', body, 'prepare')['id']==record['id']
    done=wait(client,record['id']);assert done['state']=='completed' and not done['model_id']
    assert not service.store.list('model') and not service.store.list('attempt')
    assert len(state['requests'])==len(manifest)
    model=post(client, f"/model-downloads/{record['id']}/models",{},'register')
    assert post(client,f"/model-downloads/{record['id']}/models",{},'register')==model
    assert post(client,f"/model-downloads/{record['id']}/models",{},'another-register')['id']==model['id']
    assert len(service.store.list('model'))==1 and not service.store.list('attempt')
    actual=service.store.get('model',model['id'])
    for item in manifest:
        assert (Path(actual['storage_path'])/item['path']).read_bytes()==(root/item['path']).read_bytes()
    assert actual['provenance']['revision']==module.REVISION and actual['manifest_digest']==digest(manifest)


def test_interrupted_range_resume_and_new_command(transfer):
    client, service, root, manifest, state, body=transfer
    state['cut']=True
    record=post(client,'/model-downloads',body,'cut')
    failed=wait(client,record['id']);assert failed['state']=='failed' and failed['received_bytes']>0
    old_requests=len(state['requests'])
    assert post(client,'/model-downloads',body,'cut')['state']=='failed'
    assert len(state['requests'])==old_requests
    done=post(client,f"/model-downloads/{record['id']}/resume",{},'resume')
    assert wait(client,done['id'])['state']=='completed'
    assert ('README.md',1048576) in state['requests']
    assert post(client,f"/model-downloads/{record['id']}/resume",{},'resume')['state']=='completed'


def test_real_cancel_preserves_partial_and_resumes(transfer):
    client, service, root, manifest, state, body=transfer
    state['pause']=True
    record=post(client,'/model-downloads',body,'cancel-test')
    assert state['sent'].wait(3)
    wait(client,record['id'],lambda x:x['received_bytes']>=1048576)
    post(client,f"/model-downloads/{record['id']}/cancel",{},'cancel')
    state['release'].set()
    cancelled=wait(client,record['id']);assert cancelled['state']=='cancelled' and not cancelled['model_id']
    state['pause']=False
    partial=service.root/'model-downloads'/record['id']/'files'/'README.md'
    before=partial.read_bytes();assert before and before==(root/'README.md').read_bytes()[:len(before)]
    post(client,f"/model-downloads/{record['id']}/resume",{},'resume-after-cancel')
    assert wait(client,record['id'])['state']=='completed'


def test_wrong_digest_no_registration_and_explicit_retry(transfer):
    client, service, root, manifest, state, body=transfer
    state['corrupt']=True
    record=post(client,'/model-downloads',body,'bad-bytes')
    failed=wait(client,record['id']);assert failed['state']=='failed' and failed['error']['code']=='MODEL_DOWNLOAD_HASH_MISMATCH'
    assert client.post(f"/api/v1/model-downloads/{record['id']}/models",json={},headers={'Idempotency-Key':'bad-register'}).status_code==409
    state['corrupt']=False
    post(client,f"/model-downloads/{record['id']}/resume",{},'retry-correct')
    assert wait(client,record['id'])['state']=='completed'


def test_catalog_scope_missing_key_and_disk_full(transfer,monkeypatch):
    client, service, root, manifest, state, body=transfer
    assert client.post('/api/v1/model-downloads',json=body).status_code==400
    assert client.post('/api/v1/model-downloads',json={**body,'url':'http://127.0.0.1'},headers={'Idempotency-Key':'url'}).status_code==422
    assert client.post('/api/v1/model-downloads',json={**body,'manifest_digest':'0'*64},headers={'Idempotency-Key':'wrong'}).status_code==409
    from collections import namedtuple
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:namedtuple('Usage','total used free')(10,10,0))
    assert client.post('/api/v1/model-downloads',json=body,headers={'Idempotency-Key':'disk'}).json()['error']['code']=='DISK_FULL'
    assert not state['requests'] and not service.store.list('model-download')


@pytest.mark.parametrize('url',['http://huggingface.co/x','https://huggingface.co.evil.test/x','https://evil.test/huggingface.co','https://a@huggingface.co/x','https://127.0.0.1/x','https://huggingface.co:4430/x'])
def test_https_redirect_rejects_unknown_destination(url):
    with pytest.raises(Fault):module.https_source(url)


def fail_only_model_thread(monkeypatch):
    original = threading.Thread.start
    def start(thread):
        if thread.name.startswith('model-download-'):
            raise RuntimeError('受控线程启动失败')
        return original(thread)
    monkeypatch.setattr(threading.Thread, 'start', start)


def test_start_thread_failure_is_persistent_and_same_key_never_restarts(transfer, monkeypatch):
    client, service, root, manifest, state, body = transfer
    with monkeypatch.context() as patch:
        fail_only_model_thread(patch)
        failed = post(client, '/model-downloads', body, 'start-thread-fails')
    assert failed['state'] == 'failed' and failed['error']['code'] == 'MODEL_DOWNLOAD_START_FAILED'
    assert service.store.get('model-download', failed['id']) == failed
    assert not service.threads and not state['requests']
    assert post(client, '/model-downloads', body, 'start-thread-fails') == failed
    assert not service.threads and not state['requests']
    resumed = post(client, f"/model-downloads/{failed['id']}/resume", {}, 'explicit-after-start-failure')
    assert wait(client, resumed['id'])['state'] == 'completed'
    assert len(service.store.list('model-download')) == 1


def test_resume_thread_failure_is_persistent_and_same_key_never_restarts(transfer, monkeypatch):
    client, service, root, manifest, state, body = transfer
    state['cut'] = True
    record = post(client, '/model-downloads', body, 'prepare-resume-failure')
    initial = wait(client, record['id'])
    assert initial['state'] == 'failed' and initial['received_bytes'] > 0
    partial = service.root / 'model-downloads' / record['id'] / 'files' / 'README.md'
    before = partial.read_bytes(); count = len(state['requests'])
    with monkeypatch.context() as patch:
        fail_only_model_thread(patch)
        failed = post(client, f"/model-downloads/{record['id']}/resume", {}, 'resume-thread-fails')
    assert failed['state'] == 'failed' and failed['error']['code'] == 'MODEL_DOWNLOAD_START_FAILED'
    assert failed['received_bytes'] == initial['received_bytes'] and partial.read_bytes() == before
    assert post(client, f"/model-downloads/{record['id']}/resume", {}, 'resume-thread-fails') == failed
    assert len(state['requests']) == count and not service.threads
    post(client, f"/model-downloads/{record['id']}/resume", {}, 'another-explicit-resume')
    assert wait(client, record['id'])['state'] == 'completed'


def test_service_restart_keeps_real_partial_and_old_key_does_not_resume(transfer):
    from ailab_control.service import Service
    client, service, root, manifest, state, body = transfer
    state['cut'] = True
    record = post(client, '/model-downloads', body, 'before-restart')
    failed = wait(client, record['id']); assert failed['state'] == 'failed'
    partial = service.root / 'model-downloads' / record['id'] / 'files' / 'README.md'
    before = partial.read_bytes(); old_source = service.model_downloads.source; request_count = len(state['requests'])
    # 真正下载的部分文件已落盘；把队列持久状态设为进程中断时的状态，再真实释放并重开同库。
    with service.store.transaction():
        failed['state'] = 'downloading'; service.store.put('model-download', failed)
    service.close()
    reopened = Service(service.settings)
    try:
        reopened.model_downloads.source = old_source
        recovered = reopened.model_downloads.get(record['id'])
        assert recovered['state'] == 'failed' and recovered['error']['code'] == 'MODEL_DOWNLOAD_INTERRUPTED'
        assert reopened.model_downloads.start(body, 'before-restart') == recovered
        assert partial.read_bytes() == before and len(state['requests']) == request_count and not reopened.threads
        reopened.model_downloads.resume(record['id'], 'explicit-after-restart')
        deadline = time.monotonic() + 10
        while reopened.model_downloads.get(record['id'])['state'] in module.ACTIVE and time.monotonic() < deadline:
            time.sleep(.01)
        assert reopened.model_downloads.get(record['id'])['state'] == 'completed'
        assert ('README.md', len(before)) in state['requests'][request_count:]
    finally:
        reopened.close()


@pytest.mark.parametrize('change', ['extra', 'symlink', 'broken-symlink', 'directory'])
def test_resume_rejects_changed_file_tree_without_modifying_outside(transfer, monkeypatch, change):
    client, service, root, manifest, state, body = transfer
    with monkeypatch.context() as patch:
        fail_only_model_thread(patch)
        record = post(client, '/model-downloads', body, 'prepare-path-check')
    files = service.root / 'model-downloads' / record['id'] / 'files'; files.mkdir(parents=True)
    outside = root.parent / 'outside-owner.txt'; outside.write_bytes(b'outside must stay unchanged')
    if change == 'extra':
        (files / 'not-in-manifest.txt').write_text('保留未知文件')
    elif change == 'directory':
        (files / 'README.md').mkdir()
    else:
        (files / 'README.md').symlink_to(outside if change == 'symlink' else outside.parent / 'missing-target')
    post(client, f"/model-downloads/{record['id']}/resume", {}, 'inspect-path-change')
    failed = wait(client, record['id'])
    assert failed['state'] == 'failed' and failed['error']['code'] in {'MODEL_DOWNLOAD_PATH_CHANGED', 'PATH_NOT_ALLOWED'}
    assert outside.read_bytes() == b'outside must stay unchanged'
    assert not state['requests'] and not service.store.list('model')


@pytest.mark.parametrize('change', ['bytes', 'extra', 'symlink'])
def test_register_rechecks_completed_bytes_and_tree(transfer, change):
    client, service, root, manifest, state, body = transfer
    record = post(client, '/model-downloads', body, 'complete-before-tamper')
    assert wait(client, record['id'])['state'] == 'completed'
    files = service.root / 'model-downloads' / record['id'] / 'files'
    if change == 'bytes':
        target = files / 'README.md'; raw = target.read_bytes(); target.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    elif change == 'extra':
        (files / 'unexpected.py').write_text('不执行，只验证拒绝')
    else:
        (files / 'README.md').unlink(); (files / 'README.md').symlink_to(root / 'README.md')
    response = client.post(f"/api/v1/model-downloads/{record['id']}/models", json={}, headers={'Idempotency-Key': 'register-tampered'})
    assert response.status_code == 409
    assert not service.store.list('model') and service.model_downloads.get(record['id'])['model_id'] is None


@pytest.mark.parametrize('interrupt', [False, True])
def test_real_http_uses_bounded_eight_mib_segments_and_keeps_partial(transfer, interrupt):
    client, service, root, manifest, state, body = transfer
    size = 2 * module.SEGMENT_BYTES + 4093
    raw = (b'fixed public file\n' * (size // 18 + 1))[:size]
    (root / 'README.md').write_bytes(raw)
    manifest[:] = model_manifest(root)['manifest']; body['manifest_digest'] = digest(manifest)
    state.update(cut=interrupt, cut_at=module.SEGMENT_BYTES)
    record = post(client, '/model-downloads', body, 'segmented-download')
    current = wait(client, record['id'])
    if interrupt:
        assert current['state'] == 'failed'
        partial = service.root / 'model-downloads' / record['id'] / 'files' / 'README.md'
        assert partial.read_bytes() == raw[:module.SEGMENT_BYTES + 1048576]
        prior = list(state['ranges'])
        assert post(client, '/model-downloads', body, 'segmented-download')['state'] == 'failed'
        assert state['ranges'] == prior
        post(client, f"/model-downloads/{record['id']}/resume", {}, 'explicit-segment-resume')
        current = wait(client, record['id'])
    assert current['state'] == 'completed' and current['model_id'] is None
    ranges = [(start, end) for name, start, end in state['ranges'] if name == 'README.md']
    assert ranges[:2] == [(0, module.SEGMENT_BYTES - 1), (module.SEGMENT_BYTES, 2 * module.SEGMENT_BYTES - 1)]
    assert ranges[2:] == [(module.SEGMENT_BYTES + 1048576 if interrupt else 2 * module.SEGMENT_BYTES, len(raw) - 1)]
    assert all(end - start + 1 <= 8 * 1024 * 1024 for start, end in ranges)
    assert (service.root / 'model-downloads' / record['id'] / 'files' / 'README.md').read_bytes() == raw
    assert not service.store.list('model') and not service.store.list('attempt')


def staged_partial(transfer, monkeypatch, key):
    client, service, root, manifest, state, body = transfer
    with monkeypatch.context() as patch:
        fail_only_model_thread(patch)
        record = post(client, '/model-downloads', body, key)
    files = service.root / 'model-downloads' / record['id'] / 'files'; files.mkdir(parents=True)
    partial = files / 'README.md'; partial.write_bytes((root / 'README.md').read_bytes()[:1234])
    return record, partial, partial.read_bytes()


@pytest.mark.parametrize('changed', [
    {'range_delta': (1, 0, 0)}, {'range_delta': (0, -1, 0)}, {'range_delta': (0, 0, 1)},
    {'length_delta': -1}, {'length_delta': 1},
])
def test_real_http_wrong_range_or_length_preserves_original_partial(transfer, monkeypatch, changed):
    client, service, root, manifest, state, body = transfer
    record, partial, before = staged_partial(transfer, monkeypatch, 'prepare-invalid-range')
    state.update(changed)
    post(client, f"/model-downloads/{record['id']}/resume", {}, 'reject-invalid-segment')
    failed = wait(client, record['id'])
    assert failed['state'] == 'failed' and failed['error']['code'] == 'MODEL_DOWNLOAD_RANGE_INVALID'
    assert partial.read_bytes() == before
    assert [entry for entry in state['ranges'] if entry[0] == 'README.md'] == [('README.md', len(before), len((root / 'README.md').read_bytes()) - 1)]
    assert not service.store.list('model')


@pytest.mark.parametrize('length_delta', [0, -1, 1])
def test_real_http_200_restarts_only_after_full_length_validation(transfer, monkeypatch, length_delta):
    client, service, root, manifest, state, body = transfer
    record, partial, before = staged_partial(transfer, monkeypatch, 'prepare-full-response')
    state.update(full_response=True, length_delta=length_delta)
    post(client, f"/model-downloads/{record['id']}/resume", {}, 'explicit-full-response')
    current = wait(client, record['id'])
    if length_delta:
        assert current['state'] == 'failed' and current['error']['code'] == 'MODEL_DOWNLOAD_RANGE_INVALID'
        assert partial.read_bytes() == before
    else:
        assert current['state'] == 'completed' and current['model_id'] is None
        assert partial.read_bytes() == (root / 'README.md').read_bytes()
    assert len([entry for entry in state['ranges'] if entry[0] == 'README.md']) == 1
    assert not service.store.list('model')


def test_official_request_has_explicit_end_and_fixed_https_source(monkeypatch):
    source = module.OfficialSource(); captured = []
    def open_request(request, timeout):
        captured.append((request.full_url, request.get_header('Range'), request.get_header('Accept-encoding'), timeout))
        return '受控响应'
    monkeypatch.setattr(source.opener, 'open', open_request)
    name = module.FILES[0]['path']
    assert source.open(name, 1234, 1234 + module.SEGMENT_BYTES - 1) == '受控响应'
    assert captured == [(f'https://huggingface.co/{module.REPO}/resolve/{module.REVISION}/{name}', 'bytes=1234-8389841', 'identity', 30)]
    with pytest.raises(Fault): source.open('arbitrary.txt', 0, 10)
    assert len(captured) == 1
