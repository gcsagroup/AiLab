"""仅供测试：在真实补收的确定边界等待父进程发送 SIGKILL。"""

import signal
import sys
from pathlib import Path

import ailab_control.service as module
from ailab_control.service import Service, Settings


def boundary():
    print("recollection-boundary", flush=True)
    while True:
        signal.pause()


directory, attempt_id, phase = sys.argv[1:]
service = Service(Settings(Path(directory), "crash-fixture-token"))


def forbidden(*args, **kwargs):
    raise AssertionError("补收或恢复不得重新执行模型")


service.run = forbidden
service.checkpoints.command = forbidden
original_copy, original_event = module.copy_asset, service.store.event


def copy(*args, **kwargs):
    result = original_copy(*args, **kwargs)
    if phase == "copy":
        boundary()
    return result


def event(attempt, kind, payload):
    result = original_event(attempt, kind, payload)
    if phase == "registration" and kind == "collection_changed" and payload["state"] == "succeeded":
        assert service.store.list("artifact")
        boundary()
    return result


module.copy_asset, service.store.event = copy, event
attempt = service.store.get("attempt", attempt_id)
payload = {"expected_collection_version": attempt["collection_version"],
           "manifest_digest": attempt["output_manifest_ref"]["digest"]}
receipt = service.collect(attempt_id, payload, "interrupted-recollection")
assert phase == "committed" and receipt["state"] == "succeeded"
boundary()
