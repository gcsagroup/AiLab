"""故障注入与独立进程真实 EMFILE；不消耗系统级句柄或访问用户资料。"""

import errno
import fcntl
import json
from pathlib import Path
import select
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/desktop"))
from guard_file_limits import retry_file_limit, wait_for_guard_exit


@pytest.mark.parametrize("number", [errno.EMFILE, errno.ENFILE])
@pytest.mark.parametrize("stage", ["probe", "finish", "heartbeat"])
def test_resource_failure_never_skips_stop_confirmation(number, stage):
    failures, calls = {}, []
    failed = False
    states = iter([[{"pid": 123}], []])

    def checked(name, operation):
        nonlocal failed
        calls.append(name)
        if name == stage and not failed:
            failed = True
            raise OSError(number, "注入句柄耗尽")
        return operation()

    wait_for_guard_exit(
        lambda: checked("probe", lambda: next(states)),
        lambda: checked("finish", lambda: True),
        lambda requested, active: checked("heartbeat", lambda: calls.append(bool(active))),
        failures, sleep=lambda seconds: None,
    )
    assert failures == {errno.errorcode[number]: 1}
    assert [x for x in calls if isinstance(x, bool)] == [True, False]


@pytest.mark.parametrize("error", [OSError(errno.EACCES, "权限"), OSError(errno.EIO, "磁盘"), RuntimeError("身份不匹配")])
def test_unrelated_failures_are_not_hidden(error):
    def fail():
        raise error
    with pytest.raises(type(error)) as caught:
        retry_file_limit(fail, {}, sleep=lambda seconds: pytest.fail("不应重试"))
    assert caught.value is error


def test_recovered_heartbeat_requires_fresh_process_state():
    states = iter([[], [{"pid": 456}], []])
    observed, failures = [], {}
    first = True

    def heartbeat(requested, active):
        nonlocal first
        if first:
            first = False
            raise OSError(errno.ENFILE, "探测停止后，写心跳时耗尽")
        observed.append(active)

    wait_for_guard_exit(lambda: next(states), lambda: True, heartbeat,
                        failures, sleep=lambda seconds: None)
    assert observed == [[], [{"pid": 456}], []]
    assert failures == {"ENFILE": 1}


def test_real_emfile_keeps_cross_process_lock_until_recovery(tmp_path):
    lock = tmp_path / "control.lock"
    lock.touch()
    # 仅降低自有子进程限制；父进程在故障期间独立尝试取得同一把锁。
    script = '''
import errno, fcntl, json, os, resource, sys
from guard_file_limits import retry_file_limit
lock = open(sys.argv[1], 'rb')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
_, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (min(64, hard), hard))
fds = []
while True:
    try: fds.append(os.open('/dev/null', os.O_RDONLY))
    except OSError as exc:
        assert exc.errno == errno.EMFILE
        break
failures = {}
def recover(seconds):
    print('WAITING_WITH_LOCK', flush=True)
    assert sys.stdin.readline().strip() == 'recover'
    os.close(fds.pop())
def read_file():
    with open(sys.argv[1], 'rb') as stream: return stream.read()
assert retry_file_limit(read_file, failures, sleep=recover) == b''
for fd in fds: os.close(fd)
print(json.dumps(failures), flush=True)
lock.close()
'''
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", script, str(lock)],
        cwd=ROOT / "scripts/desktop", stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert select.select([child.stdout], [], [], 10)[0], "子进程未报告故障"
        assert child.stdout.readline().strip() == "WAITING_WITH_LOCK"
        with lock.open("rb") as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output, error = child.communicate("recover\n", timeout=10)
        assert child.returncode == 0, error
        assert json.loads(output) == {"EMFILE": 1}
        with lock.open("rb") as contender:
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
