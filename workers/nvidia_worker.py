#!/usr/bin/env python3
"""固定 NVIDIA 子进程入口；只读取执行服务冻结输入目录。"""

import argparse
import contextlib
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "services/control"))
from ailab_control.remote.protocol import ProtocolError
from adapters.nvidia_text.adapter import probe, run

cancelled = threading.Event()


def emit(kind, value):
    print(json.dumps({"type": kind, **value}, ensure_ascii=False, allow_nan=False), flush=True)


def check_cancel():
    if cancelled.is_set(): raise ProtocolError("CANCELLED", "本次 NVIDIA 执行已取消。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("run", "probe"), default="run")
    parser.add_argument("--snapshot", type=Path); parser.add_argument("--input-dir", type=Path); parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    signal.signal(signal.SIGTERM, lambda *_: cancelled.set()); signal.signal(signal.SIGINT, lambda *_: cancelled.set())
    if args.mode == "probe":
        with contextlib.redirect_stdout(sys.stderr): result = probe()
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    if not all((args.snapshot, args.input_dir, args.output_dir)): parser.error("执行需要 snapshot、input-dir 和 output-dir")
    parent = os.getppid()
    def watch():
        while True:
            time.sleep(1)
            if os.getppid() != parent:
                cancelled.set(); time.sleep(10); os._exit(130)
    threading.Thread(target=watch, daemon=True).start()
    try:
        if args.snapshot.is_symlink() or args.snapshot.stat().st_size > 4 * 1024**2: raise ProtocolError("INVALID_SNAPSHOT", "快照必须为有界普通文件。")
        def pairs(items):
            value = {}
            for key, item in items:
                if key in value: raise ProtocolError("INVALID_SNAPSHOT", "快照包含重复字段。")
                value[key] = item
            return value
        snapshot = json.loads(args.snapshot.read_text(), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError("INVALID_SNAPSHOT", "快照不能包含非有限数。")))
        # 库的 stdout 重定向至日志，协议事件仍发原 stdout。
        protocol_stdout = sys.stdout
        def event(kind, value):
            print(json.dumps({"type": kind, **value}, ensure_ascii=False, allow_nan=False), file=protocol_stdout, flush=True)
        with contextlib.redirect_stdout(sys.stderr): artifacts, effective = run(snapshot, args.input_dir.absolute(), args.output_dir.absolute(), event, check_cancel)
        emit("completed", {"artifacts": artifacts, "effective_config": effective})
        return 0
    except ProtocolError as error:
        emit("error", {"code": error.code, "message": error.message})
        return 130 if error.code == "CANCELLED" else 1
    except Exception as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        emit("error", {"code": "NVIDIA_EXECUTION_FAILED", "message": "NVIDIA 执行未完成，保留本次日志。"})
        return 1


if __name__ == "__main__": raise SystemExit(main())
