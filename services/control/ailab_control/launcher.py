"""两阶段执行启动器源码；打包后仍由已选 Python 独立执行。"""

SOURCE = r'''"""先持久登记自身归属，得到控制器授权后才执行模型工作进程。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--worker-script', required=True)
p.add_argument('--snapshot', required=True)
p.add_argument('--output-dir', required=True)
p.add_argument('--controller-pid', required=True, type=int)
a = p.parse_args()
run = Path(a.snapshot).parent
if os.getppid() != a.controller_pid:
    raise SystemExit(130)
identity = subprocess.run(['/bin/ps', '-p', str(os.getpid()), '-o', 'lstart='], capture_output=True, text=True, timeout=3)
if identity.returncode != 0 or not identity.stdout.strip():
    raise SystemExit(1)
record = {'pid': os.getpid(), 'controller_pid': a.controller_pid, 'owned': True,
          'identity': {'status': 'present', 'pid': os.getpid(), 'identity_digest': hashlib.sha256(json.dumps({'pid': os.getpid(), 'started': identity.stdout.strip()}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()},
          'snapshot_sha256': hashlib.sha256(Path(a.snapshot).read_bytes()).hexdigest(),
          'launch_protocol': 1}
with (run / 'process.json.tmp').open('x', encoding='utf-8') as stream:
    json.dump(record, stream)
    stream.flush()
    os.fsync(stream.fileno())
os.rename(run / 'process.json.tmp', run / 'process.json')
deadline = time.monotonic() + 30
while not (run / 'start-authorized.json').is_file():
    if os.getppid() != a.controller_pid or time.monotonic() >= deadline:
        raise SystemExit(130)
    time.sleep(0.01)
if os.getppid() != a.controller_pid:
    raise SystemExit(130)
authorization = json.loads((run / 'start-authorized.json').read_text())
if authorization.get('pid') != os.getpid() or authorization.get('snapshot_sha256') != record['snapshot_sha256']:
    raise SystemExit(1)
if hashlib.sha256(Path(a.snapshot).read_bytes()).hexdigest() != record['snapshot_sha256']:
    raise SystemExit(1)
os.execv(sys.executable, [sys.executable, a.worker_script, '--snapshot', a.snapshot, '--output-dir', a.output_dir])
'''
