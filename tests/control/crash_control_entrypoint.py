"""仅供测试：在受控启动边界终止本次控制进程。"""

import os
from pathlib import Path
import signal
import subprocess

original = subprocess.Popen


def crash_at_launch(arguments, *args, **kwargs):
    launching = isinstance(arguments, list) and len(arguments) > 1 and Path(arguments[1]).name == "launcher.py"
    if launching and os.environ.get("CONTROL_TEST_CRASH_PHASE") == "before_spawn":
        os.kill(os.getpid(), signal.SIGKILL)
    child = original(arguments, *args, **kwargs)
    if launching and os.environ.get("CONTROL_TEST_CRASH_PHASE") == "after_spawn":
        os.kill(os.getpid(), signal.SIGKILL)
    return child


subprocess.Popen = crash_at_launch
from ailab_control.__main__ import main
main()
