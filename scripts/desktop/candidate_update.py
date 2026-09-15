"""本项目固定路径的本地候选替换；计划、数据库备份和旧包均保留。"""

import argparse
import ast
import ctypes
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile

from app_version import APP_PATH, ROOT, atomic_write, bundle_version, json_text
from verify_startup import DATA_ROOT, assert_idle, assert_not_running

AUTHORITY = 'Authority=Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)'
CERTIFICATE_SHA1 = '7C33B517942161311A087CE893D2F1CE9B204B44'
# 已核对本项目旧0.1.0签名清单对应的原始storage.py：仅接受schema 1。
LEGACY_STORAGE_SHA256 = 'a1d87739683635b2c8680bc64a2525db2b471d8f48793e5d716b328f07eae7f6'
TERMINAL = {'succeeded', 'failed', 'cancelled'}
DOWNLOAD_ACTIVE = {'queued', 'downloading', 'verifying'}
FINAL_PHASES = {'completed', 'rolled_back', 'recovered', 'failed_before_swap'}


def now(): return datetime.now(timezone.utc).isoformat()
def encode(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(value): return hashlib.sha256(encode(value).encode()).hexdigest()
def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def sync_dir(path):
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def plain_path(path, root, *, exists=True):
    path, root = Path(path).absolute(), Path(root).resolve()
    if '..' in path.parts or not path.is_relative_to(root) or path == root:
        raise ValueError('路径必须位于本项目允许的目录内。')
    if any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(root)):
        raise ValueError('操作路径不能经过符号链接。')
    if exists and not path.exists(): raise ValueError('所需路径不存在：' + str(path))
    return path


def verify_signature(app):
    for args in (['--verify', '--deep', '--strict'], ['-dvvv']):
        result = subprocess.run(['/usr/bin/codesign', *args, str(app)], capture_output=True, text=True, timeout=90)
        if result.returncode or (args == ['-dvvv'] and AUTHORITY not in result.stderr):
            raise ValueError('App组织签名校验失败：' + str(app))
    with tempfile.TemporaryDirectory(prefix='ailab-signature-') as directory:
        prefix = str(Path(directory) / 'certificate')
        result = subprocess.run(['/usr/bin/codesign', '-d', '--extract-certificates=' + prefix, str(app)], capture_output=True, timeout=30)
        certificate = Path(prefix + '0')
        if result.returncode or not certificate.is_file() or hashlib.sha1(certificate.read_bytes()).hexdigest().upper() != CERTIFICATE_SHA1:
            raise ValueError('App签名证书与本项目组织证书不符。')


def tree_manifest(app):
    entries = []
    for path in sorted(app.rglob('*')):
        relative, info = str(path.relative_to(app)), path.lstat()
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(app.resolve()):
                raise ValueError('包内符号链接越界：' + relative)
            entries.append({'path':relative, 'type':'link', 'target':os.readlink(path)})
        elif stat.S_ISREG(info.st_mode):
            entries.append({'path':relative, 'type':'file', 'size':info.st_size, 'mode':stat.S_IMODE(info.st_mode), 'sha256':sha(path)})
        elif stat.S_ISDIR(info.st_mode):
            entries.append({'path':relative, 'type':'directory', 'mode':stat.S_IMODE(info.st_mode)})
        else: raise ValueError('包内含非普通文件：' + relative)
    return entries


def schema_support(resources, manifest):
    files = manifest['files']
    for relative in ('services/control/ailab_control/migrations.py', 'control/ailab_control/migrations.py'):
        source = resources / relative
        if relative not in files: continue
        if not source.is_file() or sha(source) != files[relative]:
            raise ValueError('数据库兼容声明与签名源码清单不符。')
        values = {}
        for node in ast.parse(source.read_text()).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {'CURRENT_VERSION','SUPPORTED_VERSIONS'}:
                values[node.targets[0].id] = ast.literal_eval(node.value)
        supported = values.get('SUPPORTED_VERSIONS')
        if not isinstance(supported, set) or not supported or any(type(x) is not int or x <= 0 for x in supported) or values.get('CURRENT_VERSION') not in supported:
            raise ValueError('数据库兼容声明不能被静态核对。')
        return {'versions':sorted(supported), 'current':values['CURRENT_VERSION'], 'source_sha256':files[relative]}
    if files.get('control/ailab_control/storage.py') == LEGACY_STORAGE_SHA256:
        return {'versions':[1], 'current':1, 'source_sha256':LEGACY_STORAGE_SHA256, 'legacy_profile':'已审核的0.1.0存储源码'}
    raise ValueError('此包没有可验证的数据库兼容声明，拒绝自动替换。')


def bundle_info(app):
    if app.is_symlink() or not app.is_dir(): raise ValueError('App必须是现有普通目录。')
    verify_signature(app)
    metadata = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if metadata.get('CFBundleIdentifier') != 'org.gcsa.ailab': raise ValueError('App标识不匹配。')
    version, build, executable = metadata.get('CFBundleShortVersionString'), metadata.get('CFBundleVersion'), metadata.get('CFBundleExecutable')
    if not isinstance(version,str) or not re.fullmatch(r'\d+\.\d+\.\d+',version) or not isinstance(executable,str) or Path(executable).name != executable or not executable:
        raise ValueError('App版本或可执行文件名无效。')
    resources = app/'Contents/Resources/resources'
    manifest = json.loads((resources/'control/build-manifest.json').read_text())
    files = manifest.get('files')
    if not isinstance(files,dict) or hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest() != manifest.get('source_digest'):
        raise ValueError('包内源码清单摘要无效。')
    if 'application_version' in manifest:
        app_version = bundle_version(app,manifest)
    elif version == build == '0.1.0' and files.get('control/ailab_control/storage.py') == LEGACY_STORAGE_SHA256:
        app_version = {'version':version,'build':0,'legacy_bundle_build':build}
    else: raise ValueError('此历史包不属于已核对的版本组合。')
    entries = tree_manifest(app)
    if not (app/'Contents/MacOS'/executable).is_file(): raise ValueError('App主程序缺失。')
    return {'version':app_version, 'executable':executable, 'tree_sha256':digest(entries),
            'total_bytes':sum(row.get('size',0) for row in entries), 'entry_count':len(entries),
            'schema_support':schema_support(resources,manifest), 'certificate_sha1':CERTIFICATE_SHA1}


def version_key(info):
    return (*map(int,info['version']['version'].split('.')),info['version']['build'])


def selected_library(data_root):
    selection = data_root/'selected-library.json'
    if selection.is_symlink(): raise ValueError('工作库选择文件不能是符号链接。')
    content = selection.read_bytes() if selection.exists() else None
    selected = Path(json.loads(content)['data_dir']) if content is not None else data_root
    if not selected.is_absolute() or selected.is_symlink(): raise ValueError('选中工作库路径无效。')
    return selected.resolve(), {'path':str(selection), 'exists':content is not None,
                                 'sha256':hashlib.sha256(content).hexdigest() if content is not None else None}


@contextmanager
def stopped_library(data_root, executable):
    assert_not_running(executable)
    selected, selection = selected_library(data_root)
    lock = selected/'control.lock'
    descriptor = None
    try:
        if lock.exists():
            descriptor = os.open(lock,os.O_RDONLY|os.O_NOFOLLOW)
            try: fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('选中库的控制进程仍持有实例锁。') from None
        elif (selected/'control.sqlite3').exists():
            raise ValueError('现有工作库缺少实例锁，不能确认控制进程已退出。')
        assert_idle(data_root)
        yield selected,selection
    finally:
        if descriptor is not None: os.close(descriptor)


def database_info(path):
    if path.is_symlink(): raise ValueError('数据库不能是符号链接。')
    if not path.exists(): return {'exists':False,'schema_version':None,'logical_sha256':None,'size_bytes':0}
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN')
        if db.execute('PRAGMA integrity_check').fetchone() != ('ok',): raise ValueError('数据库完整性检查失败。')
        versions = db.execute('SELECT version FROM schema_version').fetchall()
        if len(versions)!=1 or type(versions[0][0]) is not int: raise ValueError('数据库版本记录无效。')
        active,downloads = [],[]
        for kind,body in db.execute("SELECT kind,body FROM resources WHERE kind IN ('attempt','market-download','model-download')"):
            value=json.loads(body)
            if kind=='attempt' and (value.get('state') not in TERMINAL or value.get('recovery_required')): active.append(value.get('id'))
            if kind!='attempt' and value.get('state') in DOWNLOAD_ACTIVE: downloads.append(value.get('id'))
        if active or downloads: raise ValueError('工作库仍有运行、恢复待处理或下载，不能更新App。')
        checksum=hashlib.sha256()
        for line in db.iterdump(): checksum.update((line+'\n').encode())
        size=db.execute('PRAGMA page_size').fetchone()[0]*db.execute('PRAGMA page_count').fetchone()[0]
        return {'exists':True,'schema_version':versions[0][0],'logical_sha256':checksum.hexdigest(),'size_bytes':size}


def require_schema(database, bundle):
    if database['exists'] and database['schema_version'] not in bundle['schema_support']['versions']:
        raise ValueError('当前数据库schema不被目标包支持；拒绝包回滚或降级数据库。请使用已有完整备份恢复流程，数据库备份不包含资产文件。')


def save_database(selected,selection,directory,expected):
    directory.mkdir(mode=0o700)
    if selection['exists']:
        content=Path(selection['path']).read_bytes()
        if hashlib.sha256(content).hexdigest()!=selection['sha256']: raise ValueError('选中库设置在备份前变化。')
        target=directory/'selected-library.json'
        with target.open('xb') as stream: stream.write(content);stream.flush();os.fsync(stream.fileno())
        target.chmod(0o600)
    else: atomic_write(directory/'selection-absent.json',json_text({'selection_file_existed':False}))
    if not expected['exists']:
        atomic_write(directory/'database-absent.json',json_text({'database_existed':False}))
        return {'scope':'数据库与库选择设置备份；不含资产文件。','database_existed':False}
    target=directory/'control.sqlite3'
    with target.open('xb'): pass
    target.chmod(0o600)
    with sqlite3.connect((selected/'control.sqlite3').as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(target) as destination:
        source.backup(destination)
        destination.execute('PRAGMA journal_mode=DELETE')
    actual=database_info(target)
    if actual!=expected: raise ValueError('备份内容与计划冻结的数据库不一致。')
    with target.open('rb') as stream: os.fsync(stream.fileno())
    sync_dir(directory)
    return {'scope':'数据库与库选择设置备份；不含资产文件。','database_existed':True,
            'database':str(target),'sha256':sha(target),'logical_sha256':actual['logical_sha256'],'schema_version':actual['schema_version']}


def check_space(parent,needed):
    if shutil.disk_usage(parent).free < needed+64*1024*1024: raise ValueError('暂存新包和数据库备份所需空间不足，旧包保持原位。')


def durable_copy(source,destination):
    shutil.copy2(source,destination)
    with open(destination,'rb') as stream: os.fsync(stream.fileno())
    return destination


@contextmanager
def update_lock(root):
    directory=root/'.artifacts/desktop/candidate-updates'
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    plain_path(directory,root)
    descriptor=os.open(directory/'update.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try: fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('已有本地App更新事务运行。') from None
        yield directory
    finally: os.close(descriptor)


def plan_update(source,output,root=ROOT,data_root=DATA_ROOT):
    root=Path(root).resolve();source=plain_path(source,root);target=plain_path(root/APP_PATH,root)
    with update_lock(root) as directory:
        output=plain_path(output,directory,exists=False)
        if output.parent!=directory or output.exists(): raise ValueError('计划目录必须是新的单层事务目录，不能覆盖既有文件。')
        if source==target or source.is_relative_to(target) or target.is_relative_to(source) or source.is_relative_to(output): raise ValueError('候选来源与固定App或事务目录重叠。')
        current,candidate=bundle_info(target),bundle_info(source)
        if version_key(candidate)<=version_key(current): raise ValueError('候选版本必须新于固定路径中的版本；包回退应使用rollback。')
        with stopped_library(data_root,target/'Contents/MacOS'/current['executable']) as (selected,selection):
            database=database_info(selected/'control.sqlite3');require_schema(database,current);require_schema(database,candidate)
            check_space(directory,candidate['total_bytes']+database['size_bytes'])
            if directory.stat().st_dev!=target.parent.stat().st_dev: raise ValueError('事务与固定App必须在同一文件系统，才能原子移动目录。')
            output.mkdir(mode=0o700)
            value={'schema_version':'ailab-local-candidate-update-v1','created_at':now(),'root':str(root),'target':str(target),'source':str(source),
                   'current':current,'candidate':candidate,'data_root':str(data_root.resolve()),'selected_library':str(selected),'selection':selection,'database':database,
                   'transaction_directory':str(output),'scope':'仅替换本项目固定App；保留旧包、候选来源和数据库备份，不启动App，不修改工作库。'}
            atomic_write(output/'plan.json',json_text(value))
            return {'plan':str(output/'plan.json'),'sha256':sha(output/'plan.json'),'current':current['version'],'candidate':candidate['version'],'database_schema':database['schema_version']}


def load_plan(path,expected,root):
    root=Path(root).resolve();directory=root/'.artifacts/desktop/candidate-updates'
    path=plain_path(path,directory)
    if path.name!='plan.json' or path.parent.parent!=directory or not re.fullmatch(r'[a-f0-9]{64}',expected) or sha(path)!=expected: raise ValueError('计划路径或SHA-256不匹配。')
    value=json.loads(path.read_text())
    if value.get('schema_version')!='ailab-local-candidate-update-v1' or value.get('root')!=str(root) or value.get('target')!=str(root/APP_PATH) or value.get('transaction_directory')!=str(path.parent): raise ValueError('计划不属于此固定App和事务目录。')
    plain_path(value['source'],root,exists=False)
    plain_path(value['target'],root,exists=False)
    return value,path.parent


def receipt_write(directory,receipt,phase,**extra):
    receipt.update(phase=phase,updated_at=now(),**extra)
    atomic_write(directory/'receipt.json',json_text(receipt))


def rename_exclusive(source,destination):
    if destination.exists() or destination.is_symlink(): raise ValueError('目标已存在，拒绝覆盖：'+str(destination))
    # macOS renamex_np(RENAME_EXCL)在内核内保证目标不存在，避免检查与rename之间覆盖。
    library=ctypes.CDLL(None,use_errno=True)
    rename=library.renamex_np
    rename.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint]
    rename.restype=ctypes.c_int
    if rename(os.fsencode(source),os.fsencode(destination),4):
        error=ctypes.get_errno()
        raise OSError(error,os.strerror(error),str(destination))
    sync_dir(source.parent)
    if source.parent!=destination.parent: sync_dir(destination.parent)


def same_bundle(path,expected):
    if not path.exists(): raise ValueError('本事务期望的包已缺失：'+str(path))
    if bundle_info(path)!=expected: raise ValueError('包身份发生变化，拒绝移动：'+str(path))
    return True


def library_for_plan(plan):
    selected,selection=selected_library(Path(plan['data_root']))
    if str(selected)!=plan['selected_library'] or selection!=plan['selection']: raise ValueError('选中工作库已变化，请重新制定计划。')
    return selected,selection


def restore_previous(plan,directory,receipt,phase):
    """按磁盘事实恢复；覆盖双rename期间被SIGKILL、阶段回执尚未更新的情况。"""
    target=Path(plan['target']);previous=directory/'previous.app';preserved=directory/'preserved-candidate.app'
    selected,_=library_for_plan(plan)
    require_schema(database_info(selected/'control.sqlite3'),plan['current'])
    old_present=previous.exists() and same_bundle(previous,plan['current'])
    if target.exists():
        actual=bundle_info(target)
        if actual==plan['current'] and not old_present:
            receipt_write(directory,receipt,phase,restored_previous=True)
            return receipt
        if actual!=plan['candidate'] or not old_present: raise ValueError('固定路径不是本事务期望的新包，拒绝恢复。')
        if preserved.exists(): raise ValueError('候选保留目录已存在，拒绝覆盖。')
        receipt_write(directory,receipt,'preserving_candidate')
        rename_exclusive(target,preserved)
    if not old_present: raise ValueError('旧包缺失，不能恢复；保留全部事务文件供核查。')
    if preserved.exists(): same_bundle(preserved,plan['candidate'])
    receipt_write(directory,receipt,'restoring_previous')
    rename_exclusive(previous,target)
    same_bundle(target,plan['current'])
    receipt_write(directory,receipt,phase,restored_previous=True)
    return receipt


def apply_update(path,expected,root=ROOT):
    root=Path(root).resolve()
    with update_lock(root):
        plan,directory=load_plan(path,expected,root);target=Path(plan['target']);source=Path(plan['source'])
        if (directory/'receipt.json').exists(): raise ValueError('此计划已经执行或中断；先查看回执或recover，不重复升级。')
        if not same_bundle(target,plan['current']) or not same_bundle(source,plan['candidate']): raise ValueError('计划中的包已缺失。')
        selected,selection=library_for_plan(plan)
        with stopped_library(Path(plan['data_root']),target/'Contents/MacOS'/plan['current']['executable']):
            if database_info(selected/'control.sqlite3')!=plan['database']: raise ValueError('数据库内容在计划后变化，请重新制定计划。')
            check_space(directory,plan['candidate']['total_bytes']+plan['database']['size_bytes'])
            for name in ('candidate.app','previous.app','preserved-candidate.app','database-backup'):
                if (directory/name).exists() or (directory/name).is_symlink(): raise ValueError('事务暂存路径已有内容，拒绝覆盖。')
            receipt={'schema_version':'ailab-local-candidate-update-receipt-v1','plan_sha256':expected,'started_at':now(),'target':plan['target']}
            receipt_write(directory,receipt,'preparing')
            try:
                backup=save_database(selected,selection,directory/'database-backup',plan['database'])
                receipt_write(directory,receipt,'database_backed_up',database_backup=backup)
                stage=directory/'candidate.app';shutil.copytree(source,stage,symlinks=True,copy_function=durable_copy)
                same_bundle(stage,plan['candidate']);sync_dir(directory)
                receipt_write(directory,receipt,'staged')
                assert_not_running(target/'Contents/MacOS'/plan['current']['executable'])
                if database_info(selected/'control.sqlite3')!=plan['database']: raise ValueError('数据库在暂存期间变化，旧包保持原位。')
                library_for_plan(plan);same_bundle(target,plan['current'])
                receipt_write(directory,receipt,'moving_previous')
                rename_exclusive(target,directory/'previous.app')
                receipt_write(directory,receipt,'previous_saved')
                receipt_write(directory,receipt,'installing_candidate')
                rename_exclusive(stage,target)
                receipt_write(directory,receipt,'candidate_installed')
                same_bundle(target,plan['candidate'])
                receipt_write(directory,receipt,'completed',previous_app=str(directory/'previous.app'),candidate_source=str(source))
            except Exception as error:
                receipt['error']=str(error)
                try:
                    if (directory/'previous.app').exists(): restore_previous(plan,directory,receipt,'recovered')
                    else: receipt_write(directory,receipt,'failed_before_swap')
                except Exception as recovery_error:
                    receipt_write(directory,receipt,'recovery_required',recovery_error=str(recovery_error))
                raise
            return receipt


def recover_update(path,expected,root=ROOT,*,rollback=False):
    root=Path(root).resolve()
    with update_lock(root):
        plan,directory=load_plan(path,expected,root);receipt_path=directory/'receipt.json'
        if receipt_path.is_symlink(): raise ValueError('事务回执不能是符号链接。')
        receipt=json.loads(receipt_path.read_text())
        if receipt.get('schema_version')!='ailab-local-candidate-update-receipt-v1' or receipt.get('plan_sha256')!=expected or receipt.get('target')!=plan['target']: raise ValueError('事务回执身份不匹配。')
        target=Path(plan['target'])
        with stopped_library(Path(plan['data_root']),target/'Contents/MacOS'/plan['current']['executable']):
            library_for_plan(plan)
            if receipt.get('phase')=='completed' and not rollback:
                same_bundle(target,plan['candidate']);return receipt
            if rollback and receipt.get('phase')!='completed': raise ValueError('只有完整完成的本事务可rollback；中断请用recover。')
            return restore_previous(plan,directory,receipt,'rolled_back' if rollback else 'recovered')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    planning=sub.add_parser('plan');planning.add_argument('--source',type=Path,required=True);planning.add_argument('--output',type=Path,required=True)
    for name in ('apply','rollback','recover'):
        current=sub.add_parser(name);current.add_argument('--plan',type=Path,required=True);current.add_argument('--sha256',required=True)
    args=parser.parse_args()
    try:
        result=plan_update(args.source,args.output) if args.command=='plan' else apply_update(args.plan,args.sha256) if args.command=='apply' else recover_update(args.plan,args.sha256,rollback=args.command=='rollback')
        print(json_text(result));return 0
    except Exception as error:
        print(json_text({'status':'failed','error':str(error)}));return 1


if __name__=='__main__': raise SystemExit(main())
