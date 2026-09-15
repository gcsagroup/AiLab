"""静止下载缓存随完整备份迁移，继续下载仍使用原记录。"""
import json
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from test_control import rig, post
from test_model_downloads import transfer, wait
from test_backup_restore import plan_restore
from ailab_control.api import create_app
from ailab_control.assets import file_hash
from ailab_control.backup import Backup
from ailab_control.service import Settings
from ailab_control.storage import Fault, digest


def settle(service):
    for thread in list(service.threads):
        thread.join(3)
    assert not service.threads


@pytest.mark.parametrize('partial', [True, False])
def test_model_cache_restore_preserves_bytes_then_explicit_resume_or_register(transfer, tmp_path, partial):
    client, service, source, manifest, state, body = transfer
    state['cut'] = partial
    download = post(client, '/model-downloads', body, 'backup-cache')
    current = wait(client, download['id']); settle(service)
    assert current['state'] == ('failed' if partial else 'completed')
    cache = service.root / 'model-downloads' / download['id'] / 'files'
    before = {p.relative_to(cache).as_posix(): p.read_bytes() for p in cache.rglob('*') if p.is_file()}
    manager = Backup(service); backup = manager.create('cache-backup')
    plan = plan_restore((client, service), manager, backup, tmp_path / '恢复静止下载')
    restored = manager.restore({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'cache-restore')
    app = create_app(Settings(Path(restored['restored_path']), 'restored-download-test'))
    recovered = app.state.service
    recovered.model_downloads.source = service.model_downloads.source
    old_requests = len(state['requests'])
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer restored-download-test'}) as target:
        copied = recovered.model_downloads.get(download['id'])
        assert copied == current and not recovered.store.list('model')
        for name, raw in before.items():
            assert (recovered.root / 'model-downloads' / download['id'] / 'files' / name).read_bytes() == raw
        assert len(state['requests']) == old_requests
        if partial:
            post(target, f"/model-downloads/{download['id']}/resume", {}, 'after-restore-resume')
            assert wait(target, download['id'])['state'] == 'completed'
            assert ('README.md', 1048576) in state['requests'][old_requests:]
        model = post(target, f"/model-downloads/{download['id']}/models", {}, 'after-restore-register')
        assert model['id'] == recovered.model_downloads.get(download['id'])['model_id']
        internal = recovered.store.get('model', model['id'])
        for entry in manifest:
            assert file_hash(Path(internal['storage_path']) / entry['path']) == entry['sha256']
        assert not recovered.store.list('attempt')
    for name, raw in before.items():
        assert (cache / name).read_bytes() == raw
    assert service.model_downloads.get(download['id']) == current


@pytest.mark.parametrize('damage', ['extra', 'symlink', 'overlong', 'missing_partial', 'missing_complete'])
def test_backup_rejects_changed_cache_without_publishing(transfer, damage):
    client, service, source, manifest, state, body = transfer
    state['cut'] = damage != 'missing_complete'
    download = post(client, '/model-downloads', body, 'damaged-cache')
    wait(client, download['id']); settle(service)
    cache = service.root / 'model-downloads' / download['id'] / 'files'
    path = next(p for p in cache.iterdir() if p.is_file())
    if damage == 'extra': (cache / 'extra.txt').write_text('意外内容')
    elif damage == 'symlink':
        raw = path.read_bytes(); external = service.root / 'outside.txt'; external.write_bytes(raw)
        path.unlink(); path.symlink_to(external)
    elif damage == 'overlong':
        name = next(e for e in manifest if e['path'] == path.name)
        path.write_bytes(b'x' * (name['size'] + 1))
    else: path.unlink()
    with pytest.raises(Fault): Backup(service).create('must-not-publish')
    assert not list((service.root / 'backups').glob('backup-*'))
    assert not service.maintenance_pending


def test_backup_manifest_cannot_silently_drop_retained_partial(transfer):
    client, service, source, manifest, state, body = transfer
    state['cut'] = True
    download = post(client, '/model-downloads', body, 'cache-closure')
    wait(client, download['id']); settle(service)
    manager = Backup(service); saved = manager.create('cache-closure-backup')
    directory = Path(saved['backup_path']); metadata = json.loads((directory / 'manifest.json').read_text())
    removed = next(e for e in metadata['files'] if e['path'].startswith('model-downloads/'))
    (directory / removed['path']).unlink()
    metadata['files'].remove(removed)
    metadata['manifest_digest'] = digest({k:v for k,v in metadata.items() if k != 'manifest_digest'})
    (directory / 'manifest.json').write_text(json.dumps(metadata))
    with pytest.raises(Fault): manager.verify(directory)


def test_zero_byte_failed_download_files_path_must_be_a_directory(transfer, monkeypatch):
    client, service, source, manifest, state, body = transfer
    monkeypatch.setattr(service.model_downloads, '_schedule', lambda record: None)
    record = post(client, '/model-downloads', body, 'zero-byte-path')
    record.update(state='failed', received_bytes=0)
    with service.store.transaction(): service.store.put('model-download', record)
    directory = service.root / 'model-downloads' / record['id']; directory.mkdir()
    (directory / 'files').write_bytes(b'wrong-shape')
    with pytest.raises(Fault): Backup(service).create('reject-wrong-shape')
    assert (directory / 'files').read_bytes() == b'wrong-shape'
    assert not service.maintenance_pending and not list((service.root/'backups').glob('backup-*'))
