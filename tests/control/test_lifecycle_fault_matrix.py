"""WP06 缺口：临时真实SQLite/文件与自建协议进程；零模型、零既有库。"""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import signal
import threading
import time

import pytest

from test_control import rig, setup_task, submit, post, wait_attempt
from test_checkpoints import training_run, pause_command, checkpoint_event
import ailab_control.service as service_module
from ailab_control.storage import Fault


# 这是显式协议夹具，只生成小文本或回传测试提供的检查点事件，不加载训练代码。
WORKER = r'''
import argparse, hashlib, json, os, signal, time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path);p.add_argument('--output-dir',type=Path);a=p.parse_args()
snapshot=json.loads(a.snapshot.read_text());run=a.snapshot.parent
(run/'fixture-started').write_text(str(os.getpid()))
seen=set()
def cancel(*_):
    if (run/'fixture-delay-cancel').exists(): (run/'fixture-cancel-received').touch()
    else: raise SystemExit(130)
signal.signal(signal.SIGTERM,cancel)
while True:
    for event_file in sorted(run.glob('fixture-event*.json')):
        if event_file.name not in seen:
            print(event_file.read_text(),flush=True);seen.add(event_file.name)
    if (run/'fixture-ping').exists(): (run/'fixture-pong').touch()
    if (run/'fixture-exit').exists(): raise SystemExit(int((run/'fixture-exit').read_text()))
    if (run/'fixture-complete').exists():
        text=b'controlled lifecycle result\n';(a.output_dir/'result.txt').write_bytes(text)
        print(json.dumps({'type':'completed','artifacts':[{'path':'result.txt','sha256':hashlib.sha256(text).hexdigest(),'media_type':'text/plain'}],'effective_config':snapshot['runtime']}),flush=True)
        raise SystemExit(0)
    time.sleep(.005)
'''


def wait_file(path, timeout=5):
    deadline=time.monotonic()+timeout
    while not path.is_file() and time.monotonic()<deadline:time.sleep(.005)
    assert path.is_file(), str(path)


def publish(path, value):
    temporary=path.with_suffix('.pending')
    temporary.write_text(json.dumps(value));temporary.replace(path)


def terminal_identity(attempt):
    return tuple(attempt.get(key) for key in ('state','state_version','terminal_reason','finished_at'))


def stop_owned(service, attempt_id):
    """失败清理也只触本测试Service实际创建并归属的独立进程组。"""
    process=service.processes.get(attempt_id)
    if process and process.poll() is None:
        record=service.store.get('attempt',attempt_id)['process']
        assert record['pid']==process.pid and record['owned'] and os.getpgid(process.pid)==process.pid
        os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=5)
    for thread in list(service.threads):
        if thread is not threading.current_thread():thread.join(timeout=5)
    assert not any(thread.is_alive() for thread in service.threads)


@contextmanager
def actual_training(run, monkeypatch, tmp_path):
    client,service,attempt,*_=run
    directory=service.root/'runs'/attempt['id']
    service.processes.pop(attempt['id']);directory.rmdir()
    worker=tmp_path/'lifecycle_fixture.py';worker.write_text(WORKER)
    monkeypatch.setattr(service.settings,'worker_script',worker)
    with service.store.transaction():
        current=service.store.get('attempt',attempt['id']);current['state']='queued';service.store.put('attempt',current)
    thread=threading.Thread(target=service.run,args=(attempt['id'],),name='lifecycle-owned-fixture')
    service.threads.add(thread);thread.start()
    try:
        wait_file(directory/'fixture-started')
        current=wait_attempt(client,attempt['id'],lambda a:a['state']=='running')
        process=service.processes[attempt['id']]
        assert int((directory/'fixture-started').read_text())==process.pid==current['process']['pid']
        yield directory,process
    finally:stop_owned(service,attempt['id'])


def test_queued_cancel_never_launches_worker(rig, monkeypatch):
    client,service,_,_=rig
    _,_,task=setup_task(rig)
    entered,release=threading.Event(),threading.Event();original_run=service.run
    def gated(attempt_id):
        entered.set();assert release.wait(8);return original_run(attempt_id)
    monkeypatch.setattr(service,'run',gated)
    try:
        attempt,_=submit(rig,task);assert entered.wait(5)
        queued=service.store.get('attempt',attempt['id']);assert queued['state']=='queued'
        payload={'expected_state_version':queued['state_version']}
        cancelled=service.control(attempt['id'],payload,'queued-cancel')
        assert cancelled['state']=='cancelled' and cancelled['stop_status']=='confirmed'
        assert cancelled['terminal_reason']=='CANCELLED_BEFORE_START'
        assert service.control(attempt['id'],payload,'queued-cancel')==cancelled
    finally:release.set()
    for thread in list(service.threads):thread.join(timeout=5)
    assert not service.processes and not (service.root/'runs'/attempt['id']).exists()
    assert not service.store.list('artifact') and not service.store.list('collection')
    assert len(service.store.list('attempt'))==1


def test_preparing_cancel_before_launch_authorization(rig, monkeypatch):
    client,service,_,_=rig
    source=service_module.LAUNCHER_SOURCE
    anchor='run = Path(a.snapshot).parent\n'
    assert source.count(anchor)==1
    controlled=source.replace(anchor,anchor+"(run / 'fixture-preparing').touch()\nwhile not (run / 'fixture-release-launch').exists(): time.sleep(.005)\n",1)
    monkeypatch.setattr(service_module,'LAUNCHER_SOURCE',controlled)
    _,_,task=setup_task(rig)
    attempt,_=submit(rig,task);directory=service.root/'runs'/attempt['id']
    try:
        wait_file(directory/'fixture-preparing')
        current=service.store.get('attempt',attempt['id']);assert current['state']=='preparing'
        process=service.processes[attempt['id']];assert process.poll() is None
        result=service.control(attempt['id'],{'expected_state_version':current['state_version']},'preparing-cancel')
        assert result['state']=='cancelling' and result['stop_status']=='pending'
        done=wait_attempt(client,attempt['id'])
        assert done['state']=='cancelled' and done['stop_status']=='confirmed'
        assert done['process']['returncode']==-signal.SIGTERM and not service.group_present(process.pid)
        assert not (directory/'start-authorized.json').exists() and not (directory/'completed.json').exists()
        assert not service.store.list('artifact') and not service.store.list('collection')
    finally:stop_owned(service,attempt['id'])


def test_pausing_compute_completion_resolves_unfulfilled_pause(training_run, monkeypatch, tmp_path):
    client,service,attempt,*_=training_run
    with actual_training(training_run,monkeypatch,tmp_path) as (directory,process):
        initial_version=service.store.get('attempt',attempt['id'])['state_version']
        command=pause_command(training_run)
        assert service.store.get('attempt',attempt['id'])['state']=='pausing'
        (directory/'fixture-complete').touch()
        done=wait_attempt(client,attempt['id'])
        assert done['state']=='succeeded' and done['compute_outcome']=='succeeded' and done['collection_state']=='succeeded'
        assert process.poll()==0 and not service.group_present(process.pid)
        assert len(service.store.list('artifact'))==1 and not service.store.list('checkpoint')
        before=terminal_identity(done)
        with pytest.raises(Fault) as rejected:
            service.checkpoints.command(attempt['id'],{'expected_state_version':done['state_version']},'pause-ended','pause')
        assert rejected.value.code=='CONTROL_NOT_SUPPORTED'
        assert terminal_identity(service.store.get('attempt',attempt['id']))==before
        # docs07要求计算抢先结束后暂停返回已结束/未暂停，不能永远停在accepted。
        recorded=service.store.get('training-control',command['command_id'])
        assert recorded['result']=='not_applicable' and recorded['code']=='COMPUTE_COMPLETED'
        assert recorded['command_id']==command['command_id'] and recorded['action']=='pause' and recorded['completed_at']
        assert service.store.get('attempt',attempt['id'])['last_control']==recorded
        events=service.store.events(attempt['id'],0,1000)['items']
        resolutions=[e for e in events if e['type']=='control_result' and e['payload'].get('command_id')==command['command_id'] and e['payload'].get('result')=='not_applicable']
        assert len(resolutions)==1 and resolutions[0]['payload']==recorded
        terminal=next(e for e in events if e['type']=='terminal')
        assert resolutions[0]['sequence']<terminal['sequence']
        # 原幂等键重放原始接收回执；不倒写现有最终控制结果或终态。
        replay=service.checkpoints.command(attempt['id'],{'expected_state_version':initial_version},'pause','pause')
        assert replay==command and replay['result']=='accepted'
        assert service.store.events(attempt['id'],0,1000)['items']==events
        assert terminal_identity(service.store.get('attempt',attempt['id']))==before
        assert service.store.get('training-control',command['command_id'])==recorded


@pytest.mark.parametrize('continuing',[None,False])
def test_pause_failure_without_continuation_evidence_keeps_pending(training_run, monkeypatch, tmp_path, continuing):
    client,service,attempt,*_=training_run
    with actual_training(training_run,monkeypatch,tmp_path) as (directory,process):
        command=pause_command(training_run)
        event={'type':'control_result','command_id':command['command_id'],'action':'pause','result':'failed','code':'CHECKPOINT_WRITE_FAILED','message':'受控夹具没有声明继续或停止'}
        if continuing is not None:event['continuing']=continuing
        publish(directory/'fixture-event.json',event)
        current=wait_attempt(client,attempt['id'],lambda a:a.get('last_control',{}).get('result')=='failed')
        assert current['state']=='pausing' and current['state_version']==command['state_version']
        assert current['compute_outcome']=='pending' and not current.get('finished_at') and not service.store.list('checkpoint')
        assert process.poll() is None and service.group_present(process.pid)
        assert 'cancel' in current['allowed_actions'] and 'resume' not in current['allowed_actions']
        service.control(attempt['id'],{'expected_state_version':current['state_version']},'cancel-unconfirmed-pause')
        done=wait_attempt(client,attempt['id']);assert done['state']=='cancelled' and done['stop_status']=='confirmed'


def test_paused_owned_process_crash_preserves_checkpoint_and_fails(training_run, monkeypatch, tmp_path):
    client,service,attempt,*_=training_run
    with actual_training(training_run,monkeypatch,tmp_path) as (directory,process):
        command=pause_command(training_run);event,manifest=checkpoint_event(training_run,command)
        publish(directory/'fixture-event.json',event)
        paused=wait_attempt(client,attempt['id'],lambda a:a['state']=='paused')
        checkpoint=service.store.get('checkpoint',paused['checkpoint_id']);raw=manifest.read_bytes()
        # 与事件一样原子发布，避免夹具先读到已创建但尚未写入的空文件。
        publish(directory/'fixture-exit',3)
        done=wait_attempt(client,attempt['id'])
        assert done['state']=='failed' and done['terminal_reason']=='WORKER_FAILED'
        assert done['compute_outcome']=='failed' and process.poll()==3
        assert not service.group_present(process.pid) and not service.store.list('artifact')
        assert service.store.get('checkpoint',checkpoint['id'])==checkpoint and manifest.read_bytes()==raw
        assert len(service.store.list('attempt'))==1
        assert service.store.events(attempt['id'],0,1000)['items'][-1]['type']=='terminal'
        # 退出观察在失败事务回滚后也须留下，不能只保留failed标签。
        assert done['process'].get('returncode')==3 and done['process'].get('exited_at'), done['process']


@pytest.mark.parametrize('fault',['refused','no_exit_confirmation'])
def test_force_stop_unconfirmed_keeps_owned_process_and_device_busy(rig, monkeypatch, fault):
    client,service,_,_=rig
    _,_,task=setup_task(rig,'__ignore_cancel__')
    attempt,_=submit(rig,task)
    try:
        running=wait_attempt(client,attempt['id'],lambda a:bool(a['output_text']))
        process=service.processes[attempt['id']];pid=process.pid
        accepted=running if fault=='refused' else service.control(attempt['id'],{'expected_state_version':running['state_version']},'cancel-first')
        assert accepted['state']==('running' if fault=='refused' else 'cancelling')
        real_killpg=os.killpg;calls=[]
        def controlled(pid_argument,signum):
            if pid_argument==pid and signum==signal.SIGKILL:
                calls.append((pid_argument,signum))
                if fault=='refused':raise PermissionError(errno.EPERM,'受控强停拒绝')
                return None  # 显式故障注入：返回不等于进程已经停止。
            return real_killpg(pid_argument,signum)
        payload={'expected_state_version':accepted['state_version']}
        with monkeypatch.context() as local:
            local.setattr(os,'killpg',controlled)
            if fault=='refused':
                result=service.control(attempt['id'],payload,'force-fault',force=True)
                assert result['result']=='failed' and result['code']=='CONTROL_SIGNAL_FAILED'
                assert result['state']=='cancelling' and result['stop_status']=='unknown'
                events=service.store.events(attempt['id'],0,1000)['items']
                assert service.control(attempt['id'],payload,'force-fault',force=True)==result
                assert service.store.events(attempt['id'],0,1000)['items']==events
                matches=[e for e in events if e['type']=='control_result' and e['payload'].get('command_id')==result['command_id']]
                assert len(matches)==1 and matches[0]['payload']==result['last_control']
            else:
                result=service.control(attempt['id'],payload,'force-fault',force=True)
                assert result['result']=='accepted' and result['stop_status']=='pending'
                assert service.control(attempt['id'],payload,'force-fault',force=True)==result
        assert calls==[(pid,signal.SIGKILL)]
        current=service.store.get('attempt',attempt['id'])
        assert current['state']=='cancelling', current
        assert current['stop_status']==('unknown' if fault=='refused' else 'pending') and not current.get('finished_at')
        if fault=='refused':
            assert current['last_control']==result['last_control'] and current['last_control']['action']=='force-stop'
            assert current['last_control']['result']=='failed' and current['last_control']['code']=='CONTROL_SIGNAL_FAILED'
            assert current['state_version']==result['state_version']
        assert service.processes[attempt['id']] is process and process.poll() is None and service.group_present(pid)
        check=post(client,f"/tasks/{task['id']}/preflight",{'draft_revision':task['draft_revision']})
        response=client.post(f"/api/v1/tasks/{task['id']}/attempts",json={'preflight_id':check['id'],'expected_revision':task['draft_revision']},headers={'Idempotency-Key':'cannot-replace-live-process'})
        assert response.status_code==409 and response.json()['error']['code']=='DEVICE_BUSY'
        assert len(service.store.list('attempt'))==1 and not service.store.list('artifact')
        stopped=service.control(attempt['id'],{'expected_state_version':current['state_version']},'force-real-after-fault',force=True)
        assert stopped['state']=='cancelling'
        done=wait_attempt(client,attempt['id']);assert done['state']=='cancelled' and done['stop_status']=='confirmed' and done['process']['returncode']==-signal.SIGKILL
    finally:stop_owned(service,attempt['id'])



def test_finalizing_pause_current_version_rejected_without_state_or_event_write(training_run, monkeypatch, tmp_path):
    client,service,attempt,*_=training_run
    with actual_training(training_run,monkeypatch,tmp_path) as (directory,process):
        entered,release=threading.Event(),threading.Event();original_copy=service_module.copy_asset
        def gated(source,*args,**kwargs):
            if source.name=='result.txt':
                entered.set();assert release.wait(8)
            return original_copy(source,*args,**kwargs)
        monkeypatch.setattr(service_module,'copy_asset',gated)
        try:
            (directory/'fixture-complete').touch();assert entered.wait(5)
            before=service.store.get('attempt',attempt['id']);assert before['state']=='finalizing' and process.poll()==0
            events=service.store.events(attempt['id'],0,1000)
            with pytest.raises(Fault) as rejected:
                service.checkpoints.command(attempt['id'],{'expected_state_version':before['state_version']},'pause-finalizing','pause')
            assert rejected.value.code=='CONTROL_NOT_SUPPORTED'
            assert service.store.get('attempt',attempt['id'])==before
            assert service.store.events(attempt['id'],0,1000)==events
            assert not service.store.list('training-control') and not service.store.list('checkpoint')
        finally:release.set()
        done=wait_attempt(client,attempt['id']);assert done['state']=='succeeded' and len(service.store.list('artifact'))==1


def test_resuming_cancel_and_late_resume_ack_preserve_cancel_result(training_run, monkeypatch, tmp_path):
    client,service,attempt,*_=training_run
    with actual_training(training_run,monkeypatch,tmp_path) as (directory,process):
        pause=pause_command(training_run);event,_=checkpoint_event(training_run,pause)
        publish(directory/'fixture-event-1.json',event)
        paused=wait_attempt(client,attempt['id'],lambda a:a['state']=='paused')
        resume=service.checkpoints.command(attempt['id'],{'expected_state_version':paused['state_version']},'resume-race','resume')
        assert resume['state']=='resuming' and resume['result']=='accepted'
        (directory/'fixture-delay-cancel').touch()
        cancel=service.control(attempt['id'],{'expected_state_version':resume['state_version']},'cancel-resuming')
        assert cancel['state']=='cancelling' and cancel['stop_status']=='pending'
        wait_file(directory/'fixture-cancel-received')
        late={'type':'control_result','command_id':resume['command_id'],'action':'resume','result':'confirmed','checkpoint_digest':resume['last_control']['checkpoint_digest']}
        publish(directory/'fixture-event-2.json',late)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            events=service.store.events(attempt['id'],0,1000)['items']
            stale=[e for e in events if e['type']=='warning' and e['payload'].get('code')=='STALE_CONTROL_RESULT' and e['payload'].get('command_id')==resume['command_id']]
            if stale:break
            time.sleep(.005)
        assert len(stale)==1
        current=service.store.get('attempt',attempt['id'])
        assert current['state']=='cancelling' and current['state_version']==cancel['state_version']
        assert current['last_control']==cancel['last_control'] and current['stop_status']=='pending'
        assert process.poll() is None and service.group_present(process.pid)
        assert current['checkpoint_id']==paused['checkpoint_id'] and len(service.store.list('checkpoint'))==1
        publish(directory/'fixture-exit',130)
        done=wait_attempt(client,attempt['id'])
        assert done['state']=='cancelled' and done['stop_status']=='confirmed' and done['process']['returncode']==130
        assert done['terminal_reason']=='USER_CANCELLED' and not service.store.list('artifact')
        events=service.store.events(attempt['id'],0,1000)['items']
        cancel_sequence=next(e['sequence'] for e in events if e['type']=='state_changed' and e['payload']['state']=='cancelling')
        assert not any(e['sequence']>cancel_sequence and e['type'] in {'state_changed','terminal'} and e['payload']['state'] in {'running','paused','succeeded'} for e in events)
        assert len(service.store.list('attempt'))==1
