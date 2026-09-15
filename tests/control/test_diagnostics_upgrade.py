"""004真实旧源码生成的冻结预览，在新服务和新清单说明下仍能原样导出。"""

import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control'))
from ailab_control import diagnostics as module
from ailab_control.service import Service, Settings


@pytest.mark.parametrize('future_metadata', [False, True])
def test_v004_ready_preview_survives_restart_and_manifest_metadata_changes(tmp_path, monkeypatch, future_metadata):
    fixture = json.loads((Path(__file__).with_name('fixtures') / 'diagnostic-preview-v004.json').read_text())
    assert fixture['source_sha256'] == 'b392c26a87e8dc385e617c5cc0083697c8a1738ff60f4122ec2d9da67eda43ed'
    record = fixture['record']
    assert record['status'] == 'ready' and record['diagnostics']['application']['build'] == 4
    target = tmp_path / 'exports'; target.mkdir()
    settings = Settings(tmp_path / 'library', 'new-session-token', export_roots=[target])
    service = Service(settings)
    try:
        with service.store.transaction():
            service.store.remember(module.RECORD_SCOPE, record['id'], {}, record)
    finally:
        service.close()
    if future_metadata:
        # 模拟后续版本调整说明及模式名；不得改变已经冻结的旧清单。
        monkeypatch.setattr(module, 'INCLUDED', [*module.INCLUDED, '下一版本新增说明'])
        monkeypatch.setattr(module, 'EXCLUDED', [*module.EXCLUDED, '下一版本排除说明'])
        monkeypatch.setattr(module, 'SCHEMA', 'future-diagnostics-test')
    reopened = Service(settings)
    try:
        diagnostics = module.Diagnostics(reopened)
        assert diagnostics.get(record['id'])['archive_sha256'] == record['archive_sha256']
        payload = {'preview_id': record['id'], 'target_dir': str(target)}
        result = diagnostics.export(payload, 'v004-upgrade')
        assert result['status'] == 'succeeded'
        raw = Path(result['saved_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record['archive_sha256'] and len(raw) == record['archive_bytes']
        with zipfile.ZipFile(result['saved_path']) as archive:
            data = json.loads(archive.read('diagnostics.json'))
            manifest = json.loads(archive.read('manifest.json'))
        assert data == record['diagnostics'] and 'probe_observations' not in data
        assert manifest['schema_version'] == record['diagnostics']['schema_version']
        assert manifest['included'] == record['included'] and manifest['excluded'] == record['excluded']
        assert diagnostics.export(payload, 'v004-upgrade') == result
        fresh = diagnostics.preview({})
        assert fresh['included'] == module.INCLUDED and fresh['excluded'] == module.EXCLUDED
        assert fresh['diagnostics']['schema_version'] == module.SCHEMA
        assert fresh['diagnostics']['probe_observations'] == []
        assert 'new-session-token' not in raw.decode(errors='ignore')
    finally:
        reopened.close()
