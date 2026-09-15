"""配音父进程失联的真实进程反例，不执行模型计算。"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from workers import tts_worker


@pytest.mark.parametrize('identity', ['arbitrary', '0', '1', '999999999'])
def test_invalid_controller_fails_before_start(identity, monkeypatch):
    monkeypatch.setenv('AILAB_CONTROL_PID', identity)
    with pytest.raises(tts_worker.tts.TTSError) as error:
        tts_worker.watch_controller()
    assert error.value.code == 'INVALID_CONTROLLER'


def test_real_parent_exit_cancels_own_tts_child(tmp_path):
    root = tmp_path.resolve()
    child = root / 'child.py'
    child.write_text(f'''import json, os, signal, sys, time
from pathlib import Path
sys.path.insert(0, {str(ROOT)!r})
from workers import tts_worker as worker
signal.signal(signal.SIGTERM, worker.tts.cancelled)
try:
    worker.watch_controller()
    Path({str(root / 'ready')!r}).write_text(str(os.getpid()))
    time.sleep(30)
except worker.tts.TTSError as error:
    Path({str(root / 'cancelled.json')!r}).write_text(json.dumps({{'code': error.code, 'pid': os.getpid()}}))
    raise SystemExit(130)
''')
    parent = root / 'parent.py'
    parent.write_text(f'''import os, subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, {str(child)!r}], env={{**os.environ, 'AILAB_CONTROL_PID': str(os.getpid())}}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
Path({str(root / 'pid')!r}).write_text(str(child.pid))
deadline = time.monotonic() + 10
while not Path({str(root / 'ready')!r}).exists():
    if child.poll() is not None or time.monotonic() > deadline:
        raise SystemExit(2)
    time.sleep(0.01)
''')
    pid = None
    started = time.monotonic()
    try:
        result = subprocess.run([sys.executable, str(parent)], capture_output=True, text=True, timeout=12)
        assert result.returncode == 0, result.stderr
        pid = int((root / 'pid').read_text())
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail('父进程退出后配音子进程超过回收上限')
        record = json.loads((root / 'cancelled.json').read_text())
        assert record == {'code': 'CANCELLED', 'pid': pid}
        assert time.monotonic() - started < 12
        pid = None
    finally:
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
