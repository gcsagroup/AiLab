"""随 App 发布的固定 MLX 命令入口，不接受任意 Python 脚本。"""

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def probe():
    resources = Path(sys._MEIPASS)
    manifest_path = resources.parent / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for relative, expected in manifest["files"].items():
        target = resources.parent / relative
        if not target.resolve().is_relative_to(resources.parent.resolve()) or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError("内置执行环境文件校验失败")
    source = json.loads((resources / "source-manifest.json").read_text())
    with contextlib.redirect_stdout(sys.stderr):
        import mlx.core as mx
        import mlx_lm  # noqa: F401
        facts = {"python": platform.python_version(), "metal": mx.metal.is_available(),
                 "dependencies": {name: importlib.metadata.version(name) for name in
                                  ["mlx", "mlx-lm", "transformers", "tokenizers", "numpy", "safetensors", "huggingface-hub"]},
                 "sources": source["sources"], "requirements_lock_sha256": source["requirements_lock_sha256"],
                 "runtime_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    print(json.dumps(facts, ensure_ascii=False))
    return 0


def launch(args):
    run = args.snapshot.parent
    if os.getppid() != args.controller_pid:
        return 130
    identity = subprocess.run(["/bin/ps", "-p", str(os.getpid()), "-o", "lstart="], capture_output=True, text=True, timeout=3)
    if identity.returncode != 0 or not identity.stdout.strip():
        return 1
    record = {"pid": os.getpid(), "controller_pid": args.controller_pid, "owned": True,
              "identity": {"status": "present", "pid": os.getpid(),
                           "identity_digest": hashlib.sha256(canonical({"pid": os.getpid(), "started": identity.stdout.strip()})).hexdigest()},
              "snapshot_sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(), "launch_protocol": 1}
    with (run / "process.json.tmp").open("x", encoding="utf-8") as stream:
        json.dump(record, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(run / "process.json.tmp", run / "process.json")
    deadline = time.monotonic() + 30
    while not (run / "start-authorized.json").is_file():
        if os.getppid() != args.controller_pid or time.monotonic() >= deadline:
            return 130
        time.sleep(0.01)
    if os.getppid() != args.controller_pid:
        return 130
    authorization = json.loads((run / "start-authorized.json").read_text())
    if authorization.get("pid") != os.getpid() or authorization.get("snapshot_sha256") != record["snapshot_sha256"]:
        return 1
    if hashlib.sha256(args.snapshot.read_bytes()).hexdigest() != record["snapshot_sha256"]:
        return 1
    os.environ["AILAB_CONTROL_PID"] = str(args.controller_pid)
    return worker(args, "run")


def worker(args, mode):
    sys.argv = [sys.argv[0], "--snapshot", str(args.snapshot), "--output-dir", str(args.output_dir)]
    if mode == "preflight":
        from adapters.mlx_text.preflight import main
    elif mode == "dataset-check":
        from adapters.mlx_text.split_check import main
        if args.controller_pid is not None:
            sys.argv.extend(["--controller-pid", str(args.controller_pid)])
    elif mode == "evaluation-pass":
        from workers.mlx_evaluate_worker import pass_main as main
        sys.argv.extend(["--variant", args.variant])
    else:
        from workers.mlx_worker import main
    return main()


def main():
    parser = argparse.ArgumentParser(description="GCSA AI Lab 内置 MLX 执行环境")
    parser.add_argument("--mode", choices=["probe", "preflight", "dataset-check", "launch", "run", "evaluation-pass"], required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--controller-pid", type=int)
    parser.add_argument("--variant", choices=["baseline", "candidate"])
    args = parser.parse_args()
    if args.mode == "probe":
        return probe()
    if args.snapshot is None or args.output_dir is None:
        parser.error("此命令必须提供 --snapshot 和 --output-dir")
    if args.mode == "launch":
        if args.controller_pid is None:
            parser.error("launch 必须提供 --controller-pid")
        return launch(args)
    if args.mode == "evaluation-pass" and args.variant is None:
        parser.error("evaluation-pass 必须提供 --variant")
    return worker(args, args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
