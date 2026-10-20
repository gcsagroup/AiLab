"""媒体产品执行桥：固定 CLI、真实事件、同组取消和完成后的产物封存。"""

import argparse
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.media import preflight
from workers import mlx_worker as common

MAX_EVENT_BYTES = 64 * 1024
MAX_LOG_BYTES = 16 * 1024 * 1024


def emit(kind, **fields):
    raw = json.dumps({"type": kind, **fields}, ensure_ascii=False, allow_nan=False)
    if len(raw.encode()) + 1 > MAX_EVENT_BYTES:
        raise common.WorkerError("MEDIA_EVENT_TOO_LARGE", "媒体事件超过 64 KiB 限制")
    print(raw, flush=True)


def command_for(snapshot, effective, destination):
    common_args = ["--model-root", snapshot["model_path"], "--output", str(destination), "--steps", str(effective["steps"]), "--seed", str(effective["seed"])]
    if snapshot["kind"] == "video":
        prefix = [sys.executable, "--mode", "video-cli"] if getattr(sys, "frozen", False) else [sys.executable, "-u", str(ROOT / "adapters/media/video_cli.py")]
        return [*prefix, *common_args,
                "--input", snapshot["input_image_path"], "--frames", str(effective["frames"]), "--fps", str(effective["fps"])]
    prefix = [sys.executable, "--mode", "image-cli"] if getattr(sys, "frozen", False) else [sys.executable, "-u", str(ROOT / "adapters/media/image_cli.py")]
    command = [*prefix, snapshot["operation"], *common_args, "--size", str(effective["size"])]
    if snapshot["operation"] == "train":
        command.extend(["--data", snapshot["dataset_path"], "--learning-rate", str(effective["learning_rate"]), "--rank", str(effective["lora_rank"])])
    else:
        command.extend(["--prompt", effective["prompt"], "--negative-prompt", effective["negative_prompt"], "--cfg", str(effective["cfg"])])
        if snapshot.get("adapter_path"):
            command.extend(["--adapter", snapshot["adapter_path"]])
    return command


def run_command(command, output, train_steps=None, timeout=600):
    """读取受限 JSON 行；只有 CLI 实际写出的训练 step 才成为进度。"""
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
                   "TOKENIZERS_PARALLELISM": "false", "PYTHONUNBUFFERED": "1"}
    process = None
    selector = selectors.DefaultSelector()
    completed_steps = 0
    started = time.monotonic()
    pending = b""
    cleanup = {"group_terminate_sent": False, "terminate_sent": False, "kill_sent": False,
               "cleanup_grace_seconds": None, "cleanup_wait_seconds": None}
    try:
        with (output / "executor.stdout.log").open("wb") as log, (output / "executor.stderr.log").open("wb") as stderr:
            # 继承启动器的进程组；控制服务能同时停止桥、CLI 与 FFmpeg。
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr, env=environment)
            selector.register(process.stdout, selectors.EVENT_READ)
            emit("phase", phase="executing", message="已启动固定媒体执行器，等待真实计算结果", executor_pid=process.pid)
            while selector.get_map():
                common.check_cancel()
                if time.monotonic() - started > timeout:
                    raise common.WorkerError("MEDIA_TIMEOUT", "媒体执行超过当前 10 分钟预算")
                if log.tell() > MAX_LOG_BYTES or (output / "executor.stderr.log").stat().st_size > MAX_LOG_BYTES:
                    raise common.WorkerError("MEDIA_LOG_TOO_LARGE", "媒体诊断日志超过受控大小限制")
                for key, _ in selector.select(timeout=0.1):
                    chunk = os.read(key.fileobj.fileno(), MAX_EVENT_BYTES)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    log.write(chunk)
                    log.flush()
                    pending += chunk
                    while b"\n" in pending:
                        raw, pending = pending.split(b"\n", 1)
                        if len(raw) > MAX_EVENT_BYTES:
                            raise common.WorkerError("MEDIA_EVENT_TOO_LARGE", "媒体执行器单行输出超过限制")
                        if train_steps is not None:
                            try:
                                event = json.loads(raw)
                            except (ValueError, UnicodeError):
                                continue
                            if isinstance(event, dict) and set(event) == {"step", "sample_index", "timestep", "loss", "grad_norm"}:
                                if type(event["step"]) is not int or event["step"] != completed_steps + 1 or not event["step"] <= train_steps:
                                    raise common.WorkerError("MEDIA_PROGRESS_INVALID", "训练步数事件不连续或超出冻结步数")
                                if any(type(event[name]) not in (int, float) or not math.isfinite(event[name]) for name in ("loss", "grad_norm")):
                                    raise common.WorkerError("MEDIA_PROGRESS_INVALID", "训练指标不是有限数")
                                completed_steps = event["step"]
                                emit("metric", completed_steps=completed_steps, total_steps=train_steps, loss=event["loss"], grad_norm=event["grad_norm"])
                    if len(pending) > MAX_EVENT_BYTES:
                        raise common.WorkerError("MEDIA_EVENT_TOO_LARGE", "媒体执行器单行输出超过限制")
            common.check_cancel()
            while process.poll() is None:
                common.check_cancel()
                if time.monotonic() - started > timeout:
                    raise common.WorkerError("MEDIA_TIMEOUT", "媒体执行超过当前 10 分钟预算")
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            returncode = process.returncode
            if returncode != 0:
                raise common.WorkerError("MEDIA_EXECUTION_FAILED", f"媒体执行器退出码为 {returncode}，本次诊断日志已保留")
            if train_steps is not None and completed_steps != train_steps:
                raise common.WorkerError("MEDIA_PROGRESS_INCOMPLETE", "训练未报告全部冻结步数")
            return {"executor_pid": process.pid, "elapsed_seconds": time.monotonic() - started, "returncode": returncode}
    finally:
        selector.close()
        cleanup_started = None
        try:
            if process is not None and process.poll() is None:
                cleanup_started = time.monotonic()
                cleanup["cleanup_grace_seconds"] = 10 if common.CANCELLED else 2
                if common.CANCELLED and os.getpgrp() == os.getpid():
                    # 仅在控制启动器分配给本桥的独立进程组里传播；不触碰调用者进程组。
                    os.killpg(os.getpgrp(), signal.SIGTERM)
                    cleanup["group_terminate_sent"] = True
                try:
                    # 只在内核接受信号后记为已发送；子进程抢先退出时不能补造发送记录。
                    os.kill(process.pid, signal.SIGTERM)
                    cleanup["terminate_sent"] = True
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=cleanup["cleanup_grace_seconds"])
                except subprocess.TimeoutExpired:
                    try:
                        os.kill(process.pid, signal.SIGKILL)
                        cleanup["kill_sent"] = True
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=2)
        finally:
            if cleanup_started is not None:
                cleanup["cleanup_wait_seconds"] = time.monotonic() - cleanup_started
            if process is not None and process.stdout:
                process.stdout.close()
            common.write_json(output / "executor-process.json", {
                "executor_pid": process.pid if process is not None else None,
                "returncode": process.returncode if process is not None else None,
                "cancelled": bool(common.CANCELLED), **cleanup,
            })


def validate_result(snapshot, effective, result):
    if snapshot["kind"] == "video":
        report = json.loads((result / "acceptance.json").read_text())
        plan = report["plan"]
        if report.get("functional_status") != "通过" or plan["model_manifest_sha256"] != effective["prepared_model_manifest_sha256"] or plan["input_sha256"] != effective["input_image_sha256"]:
            raise common.WorkerError("MEDIA_RESULT_MISMATCH", "视频结果的模型或输入来源与快照不一致")
        expected = {"sampling_steps": effective["steps"], "frames": effective["frames"], "fps": effective["fps"], "seed": effective["seed"], "width": 1024, "height": 576}
        if any(plan.get(key) != value for key, value in expected.items()) or common.sha256(result / "video.mp4") != report["video_sha256"]:
            raise common.WorkerError("MEDIA_RESULT_MISMATCH", "视频输出参数或文件摘要不一致")
        return report
    filename = "training.json" if snapshot["operation"] == "train" else "generation.json"
    report = json.loads((result / filename).read_text())
    if report.get("model_manifest_sha256") != effective["prepared_model_manifest_sha256"] or report.get("steps") != effective["steps"] or report.get("seed") != effective["seed"]:
        raise common.WorkerError("MEDIA_RESULT_MISMATCH", "图片结果的基座、步数或种子与快照不一致")
    if snapshot["operation"] == "train":
        if report.get("dataset_sha256") != effective["dataset_sha256"] or report.get("rank") != effective["lora_rank"] or report.get("learning_rate") != effective["learning_rate"] or report.get("frozen_parameter_sha256_before") != report.get("frozen_parameter_sha256_after"):
            raise common.WorkerError("MEDIA_RESULT_MISMATCH", "图片训练数据、参数或冻结基座验证失败")
        if common.sha256(result / "pytorch_lora_weights.safetensors") != report.get("adapter_sha256"):
            raise common.WorkerError("MEDIA_RESULT_MISMATCH", "图片 LoRA 输出摘要不一致")
    else:
        from PIL import Image
        with Image.open(result / "image.png") as image:
            image.load()
            if image.mode != "RGB" or image.size != (512, 512):
                raise common.WorkerError("MEDIA_RESULT_MISMATCH", "图片结果无法按冻结尺寸独立解码")
        if report.get("prompt") != effective["prompt"] or report.get("negative_prompt") != effective["negative_prompt"] or report.get("cfg") != effective["cfg"] or report.get("adapter_sha256") != effective.get("adapter_sha256") or common.sha256(result / "image.png") != report.get("image_sha256"):
            raise common.WorkerError("MEDIA_RESULT_MISMATCH", "图片输入、适配器、CFG 或输出摘要不一致")
    return report


def artifacts_for(output):
    mime = {".json": "application/json", ".png": "image/png", ".mp4": "video/mp4", ".wav": "audio/wav",
            ".txt": "text/plain", ".log": "text/plain", ".md5": "text/plain", ".py": "text/x-python"}
    entries = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise common.WorkerError("MEDIA_ARTIFACT_INVALID", "产物目录包含符号链接")
        if path.is_file():
            if path.stat().st_size > 256 * 1024 * 1024:
                raise common.WorkerError("MEDIA_ARTIFACT_TOO_LARGE", "单个媒体产物超过 256 MiB 的当前收集限制")
            entries.append({"path": path.relative_to(output).as_posix(), "sha256": common.sha256(path), "media_type": mime.get(path.suffix, "application/octet-stream")})
    if not entries or len(entries) > 100:
        raise common.WorkerError("MEDIA_ARTIFACT_INVALID", "媒体产物数量不在当前 1—100 个限制内")
    return entries


def execute(snapshot, output):
    if not snapshot.get("media_recipe_digest"):
        raise common.WorkerError("MEDIA_RECIPE_REQUIRED", "执行快照缺少提交前媒体配方摘要")
    checked = preflight.check(snapshot, output)
    common.check_cancel()
    effective = {**checked["effective_config"], "media_recipe_digest": checked["media_recipe_digest"]}
    output.mkdir(parents=True, exist_ok=True)
    common.write_json(output / "execution-snapshot.json", snapshot)
    common.write_json(output / "environment.json", checked["environment"])
    common.write_json(output / "media-recipe.json", checked["recipe"])
    for entry in checked["recipe"]["executor_files"]:
        destination = output / "executors" / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / entry["path"], destination)
        if common.sha256(destination) != entry["sha256"]:
            raise common.WorkerError("MEDIA_RECIPE_CHANGED", "冻结执行器源码时文件发生变化")
    result = output / "result"
    command = command_for(snapshot, effective, result)
    common.write_json(output / "executor-command.json", command)
    emit("phase", phase="loading", message="已复核固定媒体模型、输入来源和执行配方")
    execution = run_command(command, output, effective["steps"] if snapshot["operation"] == "train" else None)
    common.check_cancel()
    report = validate_result(snapshot, effective, result)
    preflight.check(snapshot, output, allow_populated_output=True)
    common.check_cancel()
    effective.update(execution=execution, source_model_unchanged=True, quality_status="not_evaluated")
    common.write_json(output / "effective-config.json", effective)
    entries = artifacts_for(output)
    manifest = {"complete": True, "artifacts": entries, "media_recipe_digest": effective["media_recipe_digest"],
                "note": "本文件记录其它输出；自身摘要由 completed 事件与控制层清单封存"}
    manifest["digest"] = common.canonical_digest(manifest)
    with (output / "output-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    common.check_cancel()
    emit("metric", elapsed_seconds=execution["elapsed_seconds"], generate_seconds=report.get("generate_seconds"), train_seconds=report.get("train_seconds"))
    emit("completed", artifacts=artifacts_for(output), effective_config=effective, source_model_unchanged=True)


def main():
    from workers.format_worker import handles, main as format_main
    if "--snapshot" in sys.argv and handles(json.loads(Path(sys.argv[sys.argv.index("--snapshot") + 1]).read_text())):
        return format_main()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, common.cancel_handler)
    signal.signal(signal.SIGINT, common.cancel_handler)
    try:
        common.watch_controller()
        execute(json.loads(args.snapshot.read_text()), args.output_dir.absolute())
        return 0
    except (common.WorkerError, preflight.Fault) as error:
        emit("error", code=error.code, message=str(error))
        return 130 if error.code == "CANCELLED" else 1
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        emit("error", code="MEDIA_EXECUTION_FAILED", message="媒体执行失败，请查看本次诊断日志", exception_type=type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
