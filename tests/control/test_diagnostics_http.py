"""正式HTTP诊断预览、固定ZIP导出和取消边界。"""
import hashlib
from pathlib import Path
import zipfile

from test_control import rig, post


def test_http_diagnostic_preview_export_and_replay(rig, tmp_path, monkeypatch):
    client, service, *_ = rig
    project=post(client,'/projects',{'name':'不进入ZIP的项目名称'})
    monkeypatch.setattr(service,'environment',lambda *a,**k: (_ for _ in ()).throw(AssertionError('不得新探测')))
    preview=post(client,'/diagnostics/previews',{'project_id':project['id'],'attempt_ids':[]})
    assert preview['status']=='ready' and preview['can_export']
    assert client.get('/api/v1/diagnostics/previews/'+preview['id']).json()==preview
    destination=tmp_path/'本机 诊断';destination.mkdir()
    grant=post(client,'/export-grants',{'path':str(destination)})
    payload={'preview_id':preview['id'],'target_dir':str(destination),'grant_id':grant['grant_id']}
    result=post(client,'/diagnostics/exports',payload,'diag-once')
    assert result['status']=='succeeded' and not result['can_cancel']
    assert post(client,'/diagnostics/exports',payload,'diag-once')==result
    path=Path(result['saved_path']);assert path.parent==destination and hashlib.sha256(path.read_bytes()).hexdigest()==preview['archive_sha256']
    with zipfile.ZipFile(path) as z:
        text='\n'.join(z.read(name).decode() for name in z.namelist())
        assert z.namelist()==['diagnostics.json','manifest.json']
        assert project['name'] not in text and str(service.root) not in text and service.settings.token not in text
    assert not service.store.list('attempt') and len(list(destination.iterdir()))==1
    assert client.post('/api/v1/diagnostics/previews/'+preview['id']+'/cancel',json={},headers={'Idempotency-Key':'too-late'}).status_code==409


def test_http_cancel_and_unapproved_payload_rejected(rig, tmp_path):
    client, service, *_=rig
    assert client.post('/api/v1/diagnostics/previews',json={'include_logs':True}).status_code==422
    assert client.post('/api/v1/diagnostics/previews',json={'attempt_ids':['x']*21}).status_code==422
    assert client.post('/api/v1/diagnostics/previews',json={'attempt_ids':[True]}).status_code==422
    assert client.get('/api/v1/diagnostics/previews/not-an-id').status_code==404
    preview=post(client,'/diagnostics/previews',{})
    cancelled=post(client,'/diagnostics/previews/'+preview['id']+'/cancel',{},'cancel-once')
    assert cancelled['status']=='cancelled' and not cancelled['can_export']
    payload={'preview_id':preview['id'],'target_dir':str(tmp_path)}
    assert client.post('/api/v1/diagnostics/exports',json=payload,headers={'Idempotency-Key':'cancelled-export'}).status_code==409
    assert not list(tmp_path.glob('*.zip'))
