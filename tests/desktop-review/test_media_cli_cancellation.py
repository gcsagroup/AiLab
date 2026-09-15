"""媒体 CLI 收到终止时应正常退出，让标准库主动释放已登记的信号量。"""

from pathlib import Path
import select
import signal
import subprocess
import sys


def test_media_cli_term_finalizes_real_spawn_semaphore(tmp_path):
    adapter = Path(__file__).resolve().parents[2] / "adapters/media"
    fixture = tmp_path / "取消实际信号量.py"
    fixture.write_text("import sys,signal,time,multiprocessing,atexit\nsys.path.insert(0," + repr(str(adapter)) + ")\nfrom image_cli import install_cancellation\ninstall_cancellation()\nlock=multiprocessing.get_context('spawn').Lock()\n@atexit.register\ndef finalize():\n print('finalizing',flush=True)\n time.sleep(0.1)\nprint('ready',flush=True)\nwhile True: time.sleep(0.01)\n")
    process = subprocess.Popen([sys.executable, str(fixture)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 10)[0] and process.stdout.readline().strip() == "ready"
        process.send_signal(signal.SIGTERM)
        assert select.select([process.stdout], [], [], 10)[0] and process.stdout.readline().strip() == "finalizing"
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130 and not stdout and not stderr
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
