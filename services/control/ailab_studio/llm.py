"""One resident LLM per local node, with queued commands and idle eviction."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import psutil
from .runtimes import interpreter
from .storage import uid

WORKERS = Path(__file__).parent / 'workers'
KEYS = ('model', 'engine', 'runtime_path', 'runtime_version', 'device', 'context_length', 'gpu_layers',
        'gpu_memory_utilization', 'tensor_parallel_size', 'cpu_offload', 'cpu_offload_gb', 'mmproj', 'vision_handler')


class ResidentLLM:
    def __init__(self, studio):
        self.studio = studio; self.operation = threading.Lock(); self.lock = threading.RLock()
        self.process = None; self.key = None; self.inbox = None; self.folder = None
        self.state = {'phase': 'unloaded', 'model': '', 'engine': '', 'idle_timeout_seconds': 300, 'expires_at': None}
        self.stopped = threading.Event()
        self.timer = threading.Thread(target=self._idle_loop, daemon=True); self.timer.start()

    def status(self):
        with self.lock:
            if self.process and self.process.poll() is not None:
                self.process = None; self.key = None; self.state.update(phase='unloaded', expires_at=None, pid=None)
            return dict(self.state)

    def _update(self, **values):
        with self.lock: self.state.update(values)

    def _stop(self):
        process = self.process
        if process and process.poll() is None:
            self._update(phase='unloading', expires_at=None)
            try:
                parent = psutil.Process(process.pid); children = parent.children(recursive=True)
                for item in reversed(children):
                    try: item.terminate()
                    except psutil.NoSuchProcess: pass
                parent.terminate()
                _, alive = psutil.wait_procs([*children, parent], timeout=3)
                for item in alive:
                    try: item.kill()
                    except psutil.NoSuchProcess: pass
                _, alive = psutil.wait_procs(alive, timeout=3)
                if alive: raise ValueError('模型进程尚未退出，请稍后重试卸载')
            except psutil.NoSuchProcess: pass
            process.wait(timeout=5)
        self.process = None; self.key = None
        self._update(phase='unloaded', expires_at=None, pid=None)

    def unload(self):
        if not self.operation.acquire(blocking=False): raise ValueError('模型正在加载或生成，请等待任务完成或取消任务后再卸载')
        try: self._stop(); return self.status()
        finally: self.operation.release()

    def evict_idle(self):
        if self.operation.acquire(blocking=False):
            try: self._stop()
            finally: self.operation.release()

    def _idle_loop(self):
        while not self.stopped.wait(.5):
            if not self.operation.acquire(blocking=False): continue
            try:
                status = self.status()
                if status['phase'] == 'loaded' and status['expires_at'] and time.time() >= status['expires_at']: self._stop()
            except Exception as exc:
                self._update(phase='loaded', expires_at=time.time() + 30, error=str(exc))
            finally: self.operation.release()

    def close(self):
        self.stopped.set(); self.timer.join(timeout=2)
        with self.operation: self._stop()

    def _start(self, config):
        self.folder = self.studio.root / 'llm-sessions' / uid(); self.folder.mkdir(parents=True)
        environment = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONUTF8='1', HF_HOME=str(self.studio.environment / 'huggingface'),
                           AILAB_JOB_CONTROL_POINTER=str(self.folder / 'control.json'))
        supervisor = ['--studio-supervise'] if getattr(sys, 'frozen', False) else [str(WORKERS / 'supervisor.py')]
        command = [sys.executable, *supervisor, str(os.getpid()), str(psutil.Process().create_time()),
                   str(interpreter(config['runtime_path'])), str(WORKERS / 'llm_session.py'), str(self.folder)]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.process = process; self.inbox = queue.Queue()
        inbox = self.inbox
        def read():
            for line in iter(process.stdout.readline, b''):
                text = line.decode('utf-8', errors='replace').rstrip()
                for name, secret in environment.items():
                    if len(secret) >= 8 and any(tag in name.upper() for tag in ('TOKEN', 'API_KEY', 'PASSWORD', 'SECRET')):
                        text = text.replace(secret, '[REDACTED]')
                if text.startswith('@@AILAB '):
                    try: event = json.loads(text[8:])
                    except ValueError: event = {'type': 'log', 'text': text[:16000]}
                else: event = {'type': 'log', 'text': text[:16000]}
                if event.get('type') not in ('log', 'status'): inbox.put(event)
            inbox.put({'type': 'process_exit'})
            process.stdout.close()
        threading.Thread(target=read, daemon=True).start()
        self._update(model=config['model'], engine=config['engine'], phase='loading', pid=process.pid, expires_at=None)

    def execute(self, job):
        key = job['id']; config = job['config']; acquired = False
        try:
            while not acquired:
                self.studio.checkpoint_pause(key)
                if self.studio.stopping or self.studio.store.get('job', key)['state'] == 'cancelling': raise InterruptedError('已取消')
                acquired = self.operation.acquire(timeout=.1)
            self.studio.checkpoint_pause(key)
            identity = tuple(config.get(name) for name in KEYS)
            if self.key != identity or not self.process or self.process.poll() is not None:
                self._stop(); self._start(config); self.key = identity
            self._update(expires_at=None, idle_timeout_seconds=config.get('idle_timeout_seconds', 300))
            with self.studio.mutex:
                current = self.studio.store.get('job', key)
                if current['state'] == 'cancelling': raise InterruptedError('已取消')
                current.update(pid=self.process.pid, pid_started=psutil.Process(self.process.pid).create_time())
                self.studio.store.put('job', current)
            self._atomic('control.json', {'directory': job['output_dir']})
            self._atomic('request.json', {'id': key, 'config': config})
            result = None; failure = None
            while True:
                if self.studio.stopping or self.studio.store.get('job', key)['state'] == 'cancelling': raise InterruptedError('已取消')
                try: event = self.inbox.get(timeout=.2)
                except queue.Empty:
                    if self.process.poll() is not None: raise RuntimeError(failure or '模型进程意外退出，请重新加载模型')
                    continue
                kind = event.get('type')
                if kind == 'process_exit': raise RuntimeError(failure or '模型进程意外退出，请重新加载模型')
                if event.get('job_id') and event['job_id'] != key: continue
                event.pop('job_id', None)
                if kind in ('log', 'status'): continue
                if kind == 'error': failure = str(event.get('text') or '模型执行失败'); continue
                if kind == 'command_failed': raise RuntimeError(failure or '模型执行失败，请重新加载模型')
                if kind == 'completed':
                    if result is None: raise RuntimeError('模型没有返回结果')
                    break
                self.studio.store.event(key, event)
                if kind == 'model_state':
                    phase = event.get('phase')
                    self._update(phase=phase)
                    with self.studio.mutex:
                        current = self.studio.store.get('job', key); current['model_state'] = phase; self.studio.store.put('job', current)
                elif kind == 'result': result = {k:v for k,v in event.items() if k != 'type'}
            self._update(phase='loaded', expires_at=time.time() + config.get('idle_timeout_seconds', 300))
            (Path(job['output_dir']) / 'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            return result
        except Exception:
            if acquired: self._stop()
            raise
        finally:
            if acquired:
                with self.studio.mutex:
                    current = self.studio.store.get('job', key)
                    current.pop('pid', None); current.pop('pid_started', None)
                    current['model_state'] = self.status()['phase']; self.studio.store.put('job', current)
                if self.folder: self._atomic('control.json', {'directory': None})
                self.operation.release()

    def _atomic(self, name, value):
        target = self.folder / name; temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(value), encoding='utf-8'); os.replace(temporary, target)
