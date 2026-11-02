"""Persistent FIFO queue and portable, acknowledged process suspension."""
import threading
import time
from pathlib import Path
from .storage import uid

TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}


class Scheduler:
    def start_scheduler(self):
        self.active = {}; self.targets = {}
        self.wake = threading.Event()
        self.scheduler = threading.Thread(target=self._schedule_loop, daemon=True)
        self.scheduler.start()

    def settings(self):
        try: return self.store.get('settings', 'execution')
        except ValueError: return {'id': 'execution', 'max_concurrent_tasks': 1}

    def save_settings(self, value):
        with self.mutex:
            result = self.store.put('settings', {'id': 'execution', **value})
        self.wake.set()
        return result

    def jobs(self):
        records = self.store.list('job', 1000000)
        active = sorted((j for j in records if j['state'] not in TERMINAL), key=lambda j: j['created_at'])
        history = sorted((j for j in records if j['state'] in TERMINAL), key=lambda j: j.get('finished_at', j['created_at']), reverse=True)[:100]
        queued = [j['id'] for j in active if j['state'] == 'queued']
        return [{**j, 'queue_position': queued.index(j['id']) + 1 if j['id'] in queued else None,
                 'holds_slot': j['id'] in self.active} for j in active + history]

    def launch(self, kind, config, runtime, target=None):
        with self.mutex:
            if self.stopping: raise ValueError('服务正在退出')
            if kind == 'install' and any(j['kind'] == kind and j['runtime'] == runtime and j['state'] not in TERMINAL for j in self.store.list('job', 1000000)):
                raise ValueError('该环境已有安装任务')
            key = uid(); output = self.root / 'jobs' / key; output.mkdir(parents=True)
            job = {'id': key, 'kind': kind, 'runtime': runtime, 'config': config, 'state': 'queued',
                   'created_at': time.time(), 'output_dir': str(output), 'result': None, 'error': None}
            self.store.put('job', job)
            if target: self.targets[key] = target
        self.wake.set()
        return job

    def _schedule_loop(self):
        while not self.stopping:
            with self.mutex:
                jobs = sorted(self.store.list('job', 1000000), key=lambda j: j.get('created_at', 0))
                for job in jobs:
                    ack = Path(job['output_dir']) / 'pause.ack' if job.get('output_dir') else None
                    if job['state'] == 'pausing' and ack and ack.exists():
                        job['state'] = 'paused'; self.store.put('job', job)
                    elif job['state'] == 'resuming' and ack and not ack.exists():
                        job['state'] = 'running'; self.store.put('job', job)
                occupied = [j for j in jobs if j['id'] in self.active]
                compute = sum(j['kind'] != 'install' for j in occupied)
                installing = {j['runtime'] for j in occupied if j['kind'] == 'install'}
                for job in jobs:
                    if job['state'] != 'queued' or job['id'] in self.active: continue
                    if job['kind'] == 'install':
                        if installing or any(j['runtime'] == job['runtime'] for j in occupied): continue
                    elif compute >= self.settings()['max_concurrent_tasks'] or job['runtime'] in installing:
                        continue
                    job.update(state='running', started_at=time.time()); self.store.put('job', job)
                    target = self.targets.pop(job['id'], None) or (self.runtimes._install if job['kind'] == 'install' else self._worker)
                    thread = threading.Thread(target=self._execute, args=(job['id'], target), daemon=True)
                    self.active[job['id']] = thread; self.threads.add(thread)
                    occupied.append(job)
                    if job['kind'] == 'install': installing.add(job['runtime'])
                    else: compute += 1
                    thread.start()
            self.wake.wait(.15); self.wake.clear()

    def pause(self, key):
        with self.mutex:
            job = self.store.get('job', key)
            if job['kind'] == 'install': raise ValueError('安装任务支持取消，不支持暂停')
            if job['state'] in ('paused', 'pausing'): return job
            if job['state'] not in ('queued', 'running', 'resuming'): raise ValueError('当前任务不能暂停')
            marker = Path(job['output_dir']) / 'pause.request'
            marker.touch()
            job['state'] = 'pausing' if key in self.active else 'paused'
            self.store.put('job', job)
        self.wake.set()
        return job

    def resume(self, key):
        with self.mutex:
            job = self.store.get('job', key)
            if job['state'] not in ('paused', 'pausing'): raise ValueError('任务未暂停')
            (Path(job['output_dir']) / 'pause.request').unlink(missing_ok=True)
            job['state'] = 'resuming' if key in self.active else 'queued'
            self.store.put('job', job)
        self.wake.set()
        return job

    def checkpoint_pause(self, key):
        """Handle pause requests between worker subprocesses without starting new work."""
        job = self.store.get('job', key); folder = Path(job['output_dir'])
        while (folder / 'pause.request').exists():
            if self.stopping or self.store.get('job', key)['state'] == 'cancelling': raise InterruptedError('已取消')
            (folder / 'pause.ack').touch()
            time.sleep(.1)
        (folder / 'pause.ack').unlink(missing_ok=True)
