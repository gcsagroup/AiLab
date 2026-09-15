"""移动内置运行时后，在空工作目录完成探测、预检查、真实生成与独立评测。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import time


def execute(binary, snapshot, output, empty, environment):
    output.mkdir()
    snapshot_path = output / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    timings = {}
    for mode in ["preflight", "launch"]:
        if mode == "preflight":
            args = [str(binary), "--mode", mode]
            args.extend(["--snapshot", str(snapshot_path), "--output-dir", str(output / "result")])
            started = time.monotonic()
            result = subprocess.run(args, cwd=empty, env=environment, capture_output=True, text=True, timeout=120)
            timings[mode] = time.monotonic() - started
            (output / f"{mode}.stdout.json").write_text(result.stdout)
            (output / f"{mode}.stderr.log").write_text(result.stderr)
            assert result.returncode == 0, f"{mode} 失败：{result.stderr} {result.stdout}"
            facts = json.loads(result.stdout)
            assert facts["can_submit"]
            assert not (output / "result").exists(), "预检查不应创建运行输出"
            snapshot["tokenization_recipe_digest"] = facts["tokenization_recipe_digest"]
            snapshot["effective_config"] = facts["effective_config"]
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
            continue
        args = [str(binary), "--mode", "launch", "--snapshot", str(snapshot_path), "--output-dir", str(output / "result"), "--controller-pid", str(os.getpid())]
        started = time.monotonic()
        with (output / "events.jsonl").open("w") as stdout, (output / "worker.stderr.log").open("w") as stderr:
            process = subprocess.Popen(args, cwd=empty, env=environment, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                deadline = time.monotonic() + 20
                while not (output / "process.json").exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                receipt = json.loads((output / "process.json").read_text())
                assert receipt["pid"] == process.pid and receipt["controller_pid"] == os.getpid()
                assert not (output / "result").exists(), "未经授权已写入执行产物"
                temporary = output / "start-authorized.json.tmp"
                temporary.write_text(json.dumps({"pid": process.pid, "snapshot_sha256": receipt["snapshot_sha256"]}))
                temporary.rename(output / "start-authorized.json")
                assert process.wait(timeout=600) == 0, (output / "worker.stderr.log").read_text()
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        timings["launch_" + snapshot["operation"]] = time.monotonic() - started
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    assert events[-1]["type"] == "completed", events[-1]
    report = {"operation": snapshot["operation"], "timings_seconds": timings, "pid": receipt["pid"]}
    if snapshot["operation"] == "generate":
        report["response"] = (output / "result/result.txt").read_text()
        effective = json.loads((output / "result/effective-config.json").read_text())
        report["effective_config"] = effective
    else:
        evaluation = json.loads((output / "result/evaluation-report.json").read_text())
        identities = evaluation["independent_loads"]
        assert len({identities["baseline"]["pid"], identities["candidate"]["pid"], receipt["pid"]}) == 3
        assert evaluation["evaluation_plan_digest"] == snapshot["evaluation_plan_digest"]
        report.update(quality_status=evaluation["status"], eligible=evaluation["eligible"],
                      independent_loads=identities, evaluation_plan_digest=evaluation["evaluation_plan_digest"])
    return report


def verify(binary, source, output, evaluation_source=None):
    output.mkdir(parents=True, exist_ok=False)
    original = json.loads(source.read_text())
    snapshot = {key: original[key] for key in ["model_path", "model_manifest", "model_manifest_digest"]}
    snapshot.update(attempt_id="bundled-runtime-smoke", operation="generate", input={"prompt": "请只输出 2+2 的结果。"},
                    runtime={"engine": "mlx", "device_id": "apple-gpu", "seed": 0, "temperature": 0, "top_p": 1, "max_tokens": 32})
    environment = {key: os.environ[key] for key in ["HOME", "TMPDIR", "LANG"] if key in os.environ}
    environment.update(PATH="/usr/bin:/bin", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    with tempfile.TemporaryDirectory(prefix="ailab-mlx-relocated-") as relocated:
        runtime = Path(relocated) / "runtime with spaces"
        shutil.copytree(binary.parent, runtime, symlinks=True)
        relocated_binary = runtime / binary.name
        empty = Path(relocated) / "empty"
        empty.mkdir()
        started = time.monotonic()
        result = subprocess.run([str(relocated_binary), "--mode", "probe"], cwd=empty, env=environment, capture_output=True, text=True, timeout=120)
        (output / "probe.stdout.json").write_text(result.stdout)
        (output / "probe.stderr.log").write_text(result.stderr)
        assert result.returncode == 0, result.stderr
        probe = json.loads(result.stdout)
        assert probe["metal"]
        probe_seconds = time.monotonic() - started
        generated = execute(relocated_binary, snapshot, output / "generate", empty, environment)
        evaluated = None
        if evaluation_source:
            evaluation_snapshot = json.loads(evaluation_source.read_text())
            assert evaluation_snapshot["operation"] == "evaluate"
            source_hash = hashlib.sha256(evaluation_source.read_bytes()).hexdigest()
            evaluated = execute(relocated_binary, evaluation_snapshot, output / "evaluate", empty, environment)
            assert hashlib.sha256(evaluation_source.read_bytes()).hexdigest() == source_hash
        assert not list(empty.iterdir()), "运行在空目录留下了未登记文件"
    report = {"status": "运行时重定位后，空工作目录探测、预检查与两阶段真实执行通过", "binary": str(binary),
              "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "probe_seconds": probe_seconds, "generate": generated, "evaluate": evaluated,
              "python_override": None, "environment_path": environment["PATH"], "relocated": True,
              "runtime_manifest_sha256": probe["runtime_manifest_sha256"]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluation-snapshot", type=Path)
    args = parser.parse_args()
    verify(args.binary.resolve(), args.snapshot.resolve(), args.output.resolve(), args.evaluation_snapshot.resolve() if args.evaluation_snapshot else None)
