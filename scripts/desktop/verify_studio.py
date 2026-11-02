"""Smoke-test the packaged control API, bundled uv and external worker launch. No models are run."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen

import psutil

ROOT = Path(__file__).resolve().parents[2]


def main():
    bundle = ROOT / 'apps/desktop/src-tauri/resources/control'
    executable = bundle / ('ailab-control.exe' if os.name == 'nt' else 'ailab-control')
    internal = bundle / '_internal'
    uv = internal / 'bin' / ('uv.exe' if os.name == 'nt' else 'uv')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    assert uv.is_file(), 'The standalone uv installer was not bundled'
    subprocess.run([str(uv), '--version'], check=True, capture_output=True, timeout=20, creationflags=flags)
    for worker in ('execute.py', 'sft.py', 'inference.py', 'llm_session.py', 'reasoning.py', 'ablation_worker.py', 'model_compat.py', 'compatibility.py'):
        assert (internal / 'ailab_studio/workers' / worker).is_file(), worker
    assert (internal / 'ailab_studio/templates/abliterix_all.toml').is_file()
    with tempfile.TemporaryDirectory(prefix='studio-package-check-', dir=ROOT / '.artifacts') as directory:
        log = Path(directory) / 'stderr.log'
        with log.open('wb') as errors:
            process = subprocess.Popen([str(executable), '--data-dir', directory, '--environment-dir', str(Path(directory) / 'environment'), '--parent-pid', str(os.getpid())],
                stdout=subprocess.PIPE, stderr=errors, stdin=subprocess.DEVNULL, creationflags=flags)
            try:
                lines = queue.Queue()
                threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
                handshake = json.loads(lines.get(timeout=30))
                assert handshake['pid'] == process.pid
                def get(path):
                    request = Request(f'http://127.0.0.1:{handshake["port"]}{path}', headers={'Authorization': 'Bearer ' + handshake['token']})
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            with urlopen(request, timeout=2) as response:
                                return json.load(response)
                        except OSError:
                            if time.monotonic() >= deadline: raise
                            time.sleep(.1)
                assert get('/health')['status'] == 'ok'
                assert {item['id'] for item in get('/api/v1/studio/status')['runtimes']} == {'training', 'llama', 'ablation', 'vllm', 'diffusers', 'comfyui'}
                assert get('/api/v1/studio/ablation/template')['fields']['model.backend'] == 'hf'
                assert get('/api/v1/studio/settings')['max_concurrent_tasks'] == 1
                assert get('/api/v1/studio/materials')['items'] == []
                assert get('/api/v1/studio/llm/status')['phase'] == 'unloaded'
            finally:
                process.terminate()
                process.wait(timeout=15)
    result = subprocess.run([str(executable), '--studio-supervise', str(os.getpid()), str(psutil.Process().create_time()),
        sys.executable, '-c', 'print("external worker ok")'], capture_output=True, timeout=20, creationflags=flags)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert b'external worker ok' in result.stdout
    size = sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file())
    print(json.dumps({'control_api': 'passed', 'bundled_uv': 'passed', 'external_worker': 'passed',
        'bundle_mib': round(size / 1024**2, 1), 'real_model_execution': 'not_tested'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
