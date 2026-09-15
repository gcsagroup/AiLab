"""更新合同的真实目录、SQLite、进程中断测试；夹具不代表真实App签名验收。"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import shutil
import sqlite3
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/desktop'))
import candidate_update as update


def make_bundle(path,version,build,supported=(1,2,3),content='candidate'):
    executable='fapp-'+str(os.getpid())
    (path/'Contents/MacOS').mkdir(parents=True)
    program=path/'Contents/MacOS'/executable;program.write_text(content);program.chmod(0o755)
    (path/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.gcsa.ailab','CFBundleExecutable':executable,
        'CFBundleShortVersionString':version,'CFBundleVersion':str(build)}))
    resources=path/'Contents/Resources/resources';(resources/'control').mkdir(parents=True)
    relative='services/control/ailab_control/migrations.py';source=resources/relative;source.parent.mkdir(parents=True)
    source.write_text(f'CURRENT_VERSION = {max(supported)}\nSUPPORTED_VERSIONS = {set(supported)!r}\n')
    value={'schema_version':1,'version':version,'build':build}
    files={relative:update.sha(source),'application/scripts/desktop/version.json':hashlib.sha256(update.json_text(value).encode()).hexdigest()}
    (resources/'control/build-manifest.json').write_text(json.dumps({'application_version':value,'files':files,
        'source_digest':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}))
    return path


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(update,'verify_signature',lambda app:None)
    root=tmp_path/'project';root.mkdir()
    current=make_bundle(root/update.APP_PATH,'1.0.0',1,supported=(1,),content='original')
    source=make_bundle(root/'source.app','2.0.0',2)
    data=root/'data';data.mkdir();(data/'control.lock').touch(mode=0o600)
    with sqlite3.connect(data/'control.sqlite3') as db:
        db.executescript('CREATE TABLE schema_version(version INTEGER); INSERT INTO schema_version VALUES(1); CREATE TABLE projects(id TEXT,body TEXT); CREATE TABLE resources(id TEXT,kind TEXT,project_id TEXT,body TEXT);')
        db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'name':'保留的用户项目'})))
    (data/'selected-library.json').write_text(json.dumps({'data_dir':str(data)}))
    output=root/'.artifacts/desktop/candidate-updates/run-1'
    return root,current,source,data,output


def create_plan(setup):
    root,current,source,data,output=setup
    result=update.plan_update(source,output,root,data)
    return Path(result['plan']),result['sha256']


def insert_resource(data,kind,value):
    with sqlite3.connect(data/'control.sqlite3') as db:
        db.execute('INSERT INTO resources VALUES(?,?,?,?)',(kind,kind,'p',json.dumps(value)))


def test_plan_apply_and_package_rollback_preserve_both_bundles_and_database(setup):
    root,current,source,data,output=setup
    original=update.bundle_info(current);candidate=update.bundle_info(source)
    before=(data/'control.sqlite3').read_bytes();selection=(data/'selected-library.json').read_bytes()
    path,checksum=create_plan(setup)
    assert (data/'control.sqlite3').read_bytes()==before and not (output/'receipt.json').exists()
    receipt=update.apply_update(path,checksum,root)
    assert receipt['phase']=='completed' and update.bundle_info(current)==candidate
    assert update.bundle_info(output/'previous.app')==original and update.bundle_info(source)==candidate
    backup=Path(receipt['database_backup']['database'])
    assert update.database_info(backup)==update.database_info(data/'control.sqlite3')
    assert '不含资产' in receipt['database_backup']['scope']
    assert backup.stat().st_mode&0o777==0o600
    assert update.recover_update(path,checksum,root)['phase']=='completed'
    receipt=update.recover_update(path,checksum,root,rollback=True)
    assert receipt['phase']=='rolled_back' and update.bundle_info(current)==original
    assert update.bundle_info(output/'preserved-candidate.app')==candidate
    assert (data/'control.sqlite3').read_bytes()==before and (data/'selected-library.json').read_bytes()==selection


@pytest.mark.parametrize('change',['plan_sha','source','current','database','selection'])
def test_plan_binding_rejects_changed_inputs_without_moving_current(setup,change):
    root,current,source,data,output=setup;path,checksum=create_plan(setup)
    if change=='plan_sha':checksum='0'*64
    if change in {'source','current'}:
        app=source if change=='source' else current
        next((app/'Contents/MacOS').iterdir()).write_text('modified')
    if change=='database':insert_resource(data,'attempt',{'state':'succeeded'})
    if change=='selection':(data/'selected-library.json').write_text(json.dumps({'data_dir':str(data),'changed':True}))
    before=update.digest(update.tree_manifest(current))
    with pytest.raises(ValueError):update.apply_update(path,checksum,root)
    assert current.exists() and update.digest(update.tree_manifest(current))==before and not (output/'previous.app').exists()


@pytest.mark.parametrize('kind,value',[('attempt',{'state':'running'}),('attempt',{'state':'failed','recovery_required':True}),('model-download',{'state':'verifying'}),('market-download',{'state':'downloading'})])
def test_unsettled_work_never_plans_update(setup,kind,value):
    root,current,source,data,output=setup;insert_resource(data,kind,value)
    with pytest.raises((ValueError,RuntimeError)):create_plan(setup)
    assert current.exists() and not output.exists()


def test_instance_lock_and_running_app_refuse_update(setup,monkeypatch):
    root,current,source,data,output=setup
    with (data/'control.lock').open() as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ValueError,match='实例锁'):create_plan(setup)
    def running(_):raise RuntimeError('App仍在运行')
    monkeypatch.setattr(update,'assert_not_running',running)
    with pytest.raises(RuntimeError,match='仍在运行'):create_plan(setup)
    assert not output.exists()


def test_disk_full_copy_failure_and_existing_stage_keep_old_bundle(setup,monkeypatch):
    root,current,source,data,output=setup;path,checksum=create_plan(setup);before=update.bundle_info(current)
    def full(*_):raise ValueError('空间不足')
    monkeypatch.setattr(update,'check_space',full)
    with pytest.raises(ValueError,match='空间不足'):update.apply_update(path,checksum,root)
    assert update.bundle_info(current)==before and not (output/'receipt.json').exists()
    monkeypatch.setattr(update,'check_space',lambda *_:None)
    (output/'candidate.app').mkdir()
    with pytest.raises(ValueError,match='已有内容'):update.apply_update(path,checksum,root)
    (output/'candidate.app').rmdir()
    def broken_copy(src,dst,**_):
        dst.mkdir();(dst/'partial').write_text('保留中断内容');raise OSError('模拟磁盘写满')
    monkeypatch.setattr(update.shutil,'copytree',broken_copy)
    with pytest.raises(OSError,match='写满'):update.apply_update(path,checksum,root)
    assert update.bundle_info(current)==before and (output/'candidate.app/partial').read_text()=='保留中断内容'
    assert json.loads((output/'receipt.json').read_text())['phase']=='failed_before_swap'


def test_exception_between_renames_restores_old_and_keeps_candidate(setup,monkeypatch):
    root,current,source,data,output=setup;path,checksum=create_plan(setup);old=update.bundle_info(current);new=update.bundle_info(source)
    original=update.rename_exclusive
    def fail_install(src,dst):
        if src==output/'candidate.app':raise OSError('安装时故障')
        return original(src,dst)
    monkeypatch.setattr(update,'rename_exclusive',fail_install)
    with pytest.raises(OSError,match='安装时故障'):update.apply_update(path,checksum,root)
    assert update.bundle_info(current)==old and update.bundle_info(output/'candidate.app')==new
    assert json.loads((output/'receipt.json').read_text())['phase']=='recovered'


@pytest.mark.parametrize('cut',['old_moved','new_installed'])
def test_sigkill_between_durable_phases_recovers_without_losing_a_bundle(setup,cut):
    root,current,source,data,output=setup;path,checksum=create_plan(setup);old=update.bundle_info(current);new=update.bundle_info(source)
    script="""
import os,signal,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import candidate_update as m
m.verify_signature=lambda _:None
original=m.rename_exclusive
def killed(source,destination):
 original(source,destination)
 if (sys.argv[5]=='old_moved' and destination.name=='previous.app') or (sys.argv[5]=='new_installed' and source.name=='candidate.app'):
  os.kill(os.getpid(),signal.SIGKILL)
m.rename_exclusive=killed
m.apply_update(Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4]))
"""
    child=subprocess.run([sys.executable,'-c',script,str(ROOT/'scripts/desktop'),str(path),checksum,str(root),cut],capture_output=True,text=True,timeout=20)
    assert child.returncode==-signal.SIGKILL,child.stderr
    receipt=json.loads((output/'receipt.json').read_text())
    assert receipt['phase']==('moving_previous' if cut=='old_moved' else 'installing_candidate')
    assert (not current.exists()) if cut=='old_moved' else update.bundle_info(current)==new
    recovered=update.recover_update(path,checksum,root)
    assert recovered['phase']=='recovered' and update.bundle_info(current)==old
    retained=output/('candidate.app' if cut=='old_moved' else 'preserved-candidate.app')
    assert update.bundle_info(retained)==new and update.bundle_info(source)==new


def test_schema_incompatible_rollback_is_rejected_without_touching_database_or_new_app(setup):
    root,current,source,data,output=setup;path,checksum=create_plan(setup);update.apply_update(path,checksum,root)
    with sqlite3.connect(data/'control.sqlite3') as db:db.execute('UPDATE schema_version SET version=3')
    before=(data/'control.sqlite3').read_bytes();new=update.bundle_info(current)
    with pytest.raises(ValueError,match='完整备份'):update.recover_update(path,checksum,root,rollback=True)
    assert (data/'control.sqlite3').read_bytes()==before and update.bundle_info(current)==new
    assert (output/'previous.app').exists() and not (output/'preserved-candidate.app').exists()


def test_wal_commit_is_present_in_read_only_database_backup(setup):
    root,current,source,data,output=setup
    with sqlite3.connect(data/'control.sqlite3') as writer:
        writer.execute('PRAGMA journal_mode=WAL');writer.execute('INSERT INTO projects VALUES(?,?)',('wal','{"name":"已提交WAL"}'));writer.commit()
        assert (data/'control.sqlite3-wal').stat().st_size>0
        before=(data/'control.sqlite3-wal').read_bytes();path,checksum=create_plan(setup);receipt=update.apply_update(path,checksum,root)
        assert (data/'control.sqlite3-wal').read_bytes()==before
        with sqlite3.connect(Path(receipt['database_backup']['database']).as_uri()+'?mode=ro',uri=True) as backup:
            assert backup.execute("SELECT body FROM projects WHERE id='wal'").fetchone()[0]=='{"name":"已提交WAL"}'


def test_atomic_exclusive_rename_cannot_replace_existing_file_or_directory(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'keep').write_text('原文件')
    destination=tmp_path/'destination';destination.mkdir()
    with pytest.raises(ValueError,match='拒绝覆盖'):update.rename_exclusive(source,destination)
    assert (source/'keep').read_text()=='原文件' and destination.is_dir()


def test_signature_version_paths_and_repeat_apply_are_fail_closed(setup,monkeypatch):
    root,current,source,data,output=setup
    with pytest.raises(ValueError):update.plan_update(source,root/'.artifacts/desktop/candidate-updates/../escaped',root,data)
    link=root/'linked.app';link.symlink_to(source)
    with pytest.raises(ValueError,match='符号链接'):update.plan_update(link,output,root,data)
    with pytest.raises(ValueError,match='重叠'):update.plan_update(current,output,root,data)
    with pytest.raises(ValueError,match='版本必须新'):update.plan_update(make_bundle(root/'old.app','0.9.0',0),output,root,data)
    def wrong(_):raise ValueError('组织签名不符')
    monkeypatch.setattr(update,'verify_signature',wrong)
    with pytest.raises(ValueError,match='签名'):create_plan(setup)
    monkeypatch.setattr(update,'verify_signature',lambda _:None)
    path,checksum=create_plan(setup);update.apply_update(path,checksum,root)
    with pytest.raises(ValueError,match='已经执行'):update.apply_update(path,checksum,root)


def test_unknown_or_changed_recovery_bundle_never_overwrites_current(setup):
    root,current,source,data,output=setup;path,checksum=create_plan(setup);update.apply_update(path,checksum,root)
    next((output/'previous.app/Contents/MacOS').iterdir()).write_text('未知修改')
    before=update.bundle_info(current)
    with pytest.raises(ValueError,match='身份发生变化'):update.recover_update(path,checksum,root,rollback=True)
    assert update.bundle_info(current)==before


def test_cli_requires_digest_and_exposes_no_install_root_or_signature_bypass():
    result=subprocess.run([sys.executable,str(ROOT/'scripts/desktop/candidate_update.py'),'apply','--plan','missing'],capture_output=True,text=True,timeout=10)
    assert result.returncode==2 and '--sha256' in result.stderr
    result=subprocess.run([sys.executable,str(ROOT/'scripts/desktop/candidate_update.py'),'plan','--help'],capture_output=True,text=True,timeout=10)
    assert '--source' in result.stdout and '--root' not in result.stdout and '--skip' not in result.stdout


@pytest.mark.parametrize('cut',['candidate_preserved','previous_restored'])
def test_sigkill_during_rollback_can_also_recover_both_sides(setup,cut):
    root,current,source,data,output=setup;path,checksum=create_plan(setup)
    old=update.bundle_info(current);new=update.bundle_info(source);update.apply_update(path,checksum,root)
    script="""
import os,signal,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);import candidate_update as m
m.verify_signature=lambda _:None
original=m.rename_exclusive
def killed(source,destination):
 original(source,destination)
 if (sys.argv[5]=='candidate_preserved' and destination.name=='preserved-candidate.app') or (sys.argv[5]=='previous_restored' and source.name=='previous.app'):
  os.kill(os.getpid(),signal.SIGKILL)
m.rename_exclusive=killed
m.recover_update(Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4]),rollback=True)
"""
    child=subprocess.run([sys.executable,'-c',script,str(ROOT/'scripts/desktop'),str(path),checksum,str(root),cut],capture_output=True,text=True,timeout=20)
    assert child.returncode==-signal.SIGKILL,child.stderr
    receipt=update.recover_update(path,checksum,root)
    assert receipt['phase']=='recovered' and update.bundle_info(current)==old
    assert update.bundle_info(output/'preserved-candidate.app')==new


def test_recover_completed_receipt_does_not_claim_success_when_fixed_app_is_missing(setup):
    root,current,source,data,output=setup;path,checksum=create_plan(setup);update.apply_update(path,checksum,root)
    moved=root/'moved-by-operator.app';update.rename_exclusive(current,moved)
    with pytest.raises(ValueError,match='缺失'):update.recover_update(path,checksum,root)
    assert moved.exists() and not current.exists() and (output/'previous.app').exists()


def test_unknown_path_created_in_interrupted_gap_is_not_replaced(setup,monkeypatch):
    root,current,source,data,output=setup;path,checksum=create_plan(setup)
    original=update.rename_exclusive
    def inject(source_path,destination):
        original(source_path,destination)
        if destination.name=='previous.app':
            current.mkdir();(current/'operator-file').write_text('必须保留');raise OSError('另一进程占据固定路径')
    monkeypatch.setattr(update,'rename_exclusive',inject)
    with pytest.raises(OSError,match='占据'):update.apply_update(path,checksum,root)
    assert (current/'operator-file').read_text()=='必须保留' and (output/'previous.app').exists()
    assert json.loads((output/'receipt.json').read_text())['phase']=='recovery_required'


def test_native_exclusive_rename_still_refuses_when_precheck_misses_an_existing_directory(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();(source/'keep').write_text('不能丢失')
    destination=tmp_path/'destination';destination.mkdir()
    original=Path.exists
    monkeypatch.setattr(Path,'exists',lambda path:False if path==destination else original(path))
    with pytest.raises(OSError):update.rename_exclusive(source,destination)
    assert (source/'keep').read_text()=='不能丢失' and destination.is_dir()


def test_actual_same_named_process_prevents_plan(setup):
    root,current,source,data,output=setup
    # 仅复制系统程序字节；不把只读系统卷的受保护flags复制到测试目录。
    executable=next((current/'Contents/MacOS').iterdir());shutil.copyfile('/bin/sleep',executable);executable.chmod(0o755)
    process=subprocess.Popen([str(executable),'20'])
    try:
        with pytest.raises(RuntimeError,match='同名 App 进程'):create_plan(setup)
        assert not output.exists() and process.poll() is None
    finally:
        process.terminate();process.wait(timeout=5)
