import json
import os
from pathlib import Path
import shutil
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control'))
from ailab_studio import llm
from ailab_studio.service import Studio
from ailab_studio.workers.reasoning import ReasoningStream


def test_reasoning_split_at_every_character():
    events = []
    stream = ReasoningStream(lambda text, channel: events.append((text, channel)))
    for char in '<think>检查</think>答案<analysis>复查</analysis>完成': stream.write(char)
    stream.finish()
    assert stream.reasoning == '检查复查' and stream.text == '答案完成'
    assert ''.join(t for t, c in events if c == 'reasoning') == stream.reasoning
    stream = ReasoningStream(lambda *_: None, thinking=True)
    stream.write('模板已打开思考</think>最终<'); stream.finish()
    assert stream.reasoning == '模板已打开思考' and stream.text == '最终<'
    stream = ReasoningStream(lambda *_: None)
    stream.write('显式思考字段', reasoning=True); stream.write('普通回答'); stream.finish()
    assert stream.reasoning == '显式思考字段' and stream.text == '普通回答'


def wait_job(studio, job, state='succeeded'):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        current = studio.store.get('job', job['id'])
        if current['state'] == state: return current
        assert current['state'] not in ('failed', 'cancelled'), current
        time.sleep(.05)
    raise AssertionError(current)


def test_resident_reuse_stream_cancel_and_idle_unload(tmp_path, monkeypatch):
    workers = tmp_path / 'workers'; workers.mkdir()
    shutil.copy(llm.WORKERS / 'supervisor.py', workers / 'supervisor.py')
    (workers / 'llm_session.py').write_text('''import json, sys, time
from pathlib import Path
folder=Path(sys.argv[1]); previous=''
while True:
    path=folder/'request.json'
    if not path.exists(): time.sleep(.02); continue
    request=json.loads(path.read_text()); key=request['id']
    if key == previous: time.sleep(.02); continue
    previous=key
    def emit(kind, **values): print('@@AILAB '+json.dumps(dict(type=kind, job_id=key, **values)),flush=True)
    print('runtime diagnostic output', flush=True)
    emit('log', text='structured diagnostic output')
    emit('model_state', phase='generating')
    emit('token', text='thinking', channel='reasoning')
    time.sleep(request['config'].get('delay', .2))
    emit('token', text='answer', channel='final')
    emit('result', text='answer', reasoning='thinking')
    emit('model_state', phase='loaded')
    emit('completed')
''', encoding='utf-8')
    monkeypatch.setattr(llm, 'WORKERS', workers)
    studio = Studio(tmp_path / 'data')
    config = dict(model='fake.gguf', engine='llama', workflow='chat', runtime_path=sys.prefix, idle_timeout_seconds=10)
    def launch(**overrides): return studio.launch('inference', {**config, **overrides}, 'llama')
    try:
        first = launch(); wait_job(studio, first)
        pid = studio.llm.status()['pid']
        second = launch(); wait_job(studio, second)
        assert studio.llm.status()['pid'] == pid and studio.llm.status()['phase'] == 'loaded'
        events = studio.store.events(second['id'])
        assert not any(e['type'] == 'log' for e in events)
        assert [e['channel'] for e in events if e['type'] == 'token'] == ['reasoning', 'final']
        slow = launch(delay=10); wait_job(studio, slow, 'running')
        deadline = time.monotonic() + 5
        while studio.llm.status()['phase'] != 'generating' and time.monotonic() < deadline: time.sleep(.02)
        with pytest.raises(ValueError): studio.llm.unload()
        studio.pause(slow['id']); wait_job(studio, slow, 'paused')
        assert studio.llm.status()['pid'] == pid
        studio.resume(slow['id']); wait_job(studio, slow, 'running')
        studio.cancel(slow['id']); wait_job(studio, slow, 'cancelled')
        assert studio.llm.status()['phase'] == 'unloaded'
        last = launch(idle_timeout_seconds=.3); wait_job(studio, last)
        deadline = time.monotonic() + 8
        while studio.llm.status()['phase'] != 'unloaded' and time.monotonic() < deadline: time.sleep(.05)
        assert studio.llm.status()['phase'] == 'unloaded'
        final = launch(); wait_job(studio, final)
        assert studio.llm.unload()['phase'] == 'unloaded'
    finally: studio.close()
