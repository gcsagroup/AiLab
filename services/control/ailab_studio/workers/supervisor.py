"""Own the entire child tree and stop it when the controller disappears."""
import os
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
import psutil


def main():
    parent_pid, parent_start = int(sys.argv[1]), float(sys.argv[2])
    try:
        if abs(psutil.Process(parent_pid).create_time() - parent_start) >= 0.01: return 130
    except psutil.Error: return 130
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    if getattr(sys, 'frozen', False):
        # Do not make independently installed Python/CUDA binaries load the bundle's DLLs.
        for name in ('LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH'):
            original = environment.pop(name + '_ORIG', None)
            if original is None: environment.pop(name, None)
            else: environment[name] = original
        if os.name == 'nt':
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
    child = subprocess.Popen(sys.argv[3:], stdin=subprocess.DEVNULL, env=environment,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    tracked = {}
    suspended = {}
    control = Path(environment['AILAB_JOB_CONTROL_DIR']) if environment.get('AILAB_JOB_CONTROL_DIR') else None

    def track():
        try:
            process = psutil.Process(child.pid)
            for item in process.children(recursive=True) + [process]: tracked[(item.pid, item.create_time())] = item
        except psutil.NoSuchProcess: pass

    def cleanup(*_):
        track()
        try:
            for item in suspended.values():
                try: item.resume()
                except psutil.NoSuchProcess: pass
            suspended.clear()
            owned = [item for item in tracked.values() if item.is_running()]
            for item in reversed(owned):
                try: item.terminate()
                except psutil.NoSuchProcess: pass
            _, alive = psutil.wait_procs(owned, timeout=3)
            for item in alive:
                try: item.kill()
                except psutil.NoSuchProcess: pass
        except psutil.NoSuchProcess: pass

    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(130)))
    signal.signal(signal.SIGINT, lambda *_: (cleanup(), sys.exit(130)))
    try:
        while child.poll() is None:
            track()
            if environment.get('AILAB_JOB_CONTROL_POINTER'):
                pointer = Path(environment['AILAB_JOB_CONTROL_POINTER'])
                if pointer.exists():
                    directory = json.loads(pointer.read_text(encoding='utf-8')).get('directory')
                    control = Path(directory) if directory else None
            try: alive = abs(psutil.Process(parent_pid).create_time() - parent_start) < 0.01
            except psutil.Error: alive = False
            if not alive: cleanup(); return 130
            if control and (control / 'pause.request').exists():
                for key, item in sorted(tracked.items(), key=lambda pair: pair[0][0] != child.pid):
                    if key not in suspended:
                        try: item.suspend(); suspended[key] = item
                        except psutil.NoSuchProcess: pass
                (control / 'pause.ack').touch()
            elif suspended:
                for item in suspended.values():
                    try: item.resume()
                    except psutil.NoSuchProcess: pass
                suspended.clear()
                if control: (control / 'pause.ack').unlink(missing_ok=True)
            time.sleep(0.1)
        return child.returncode
    finally: cleanup()


if __name__ == '__main__': sys.exit(main())
