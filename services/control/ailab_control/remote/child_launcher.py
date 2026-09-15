"""外部引擎先登记归属并等待授权，然后才加载固定工作进程。"""

import argparse
import json
import os
from pathlib import Path
import sys
import time

from .protocol import digest, process_identity, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "input-dir", "output-dir", "worker-script", "record-dir", "nonce"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    args = parser.parse_args()
    if os.getppid() != args.parent_pid:
        return 130
    snapshot = Path(args.snapshot)
    directory = Path(args.record_dir)
    identity = process_identity(os.getpid())
    if identity["status"] != "present" or identity["pgid"] != os.getpid():
        return 1
    record = {"process": identity, "nonce": args.nonce, "snapshot_sha256": digest(json.loads(snapshot.read_text()))}
    write_json(directory / "process.json", record, exclusive=True)
    authorization = directory / "authorized.json"
    deadline = time.monotonic() + 15
    while not authorization.is_file():
        if os.getppid() != args.parent_pid or time.monotonic() >= deadline:
            return 130
        time.sleep(0.01)
    if os.getppid() != args.parent_pid or json.loads(authorization.read_text()) != record:
        return 130
    if digest(json.loads(snapshot.read_text())) != record["snapshot_sha256"]:
        return 1
    os.execv(sys.executable, [sys.executable, args.worker_script, "--snapshot", str(snapshot), "--input-dir", args.input_dir, "--output-dir", args.output_dir])


if __name__ == "__main__":
    raise SystemExit(main())
