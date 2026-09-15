"""搬迁完整媒体运行时后，以空 cwd 与最小环境验证真实执行及进程组回收。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
import wave


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def snapshot_from(path):
    original = json.loads(path.read_text())
    names = {"kind", "operation", "model_path", "model_manifest", "model_manifest_digest", "prepared_model_manifest_digest", "runtime", "input",
             "dataset_path", "dataset_root_path", "dataset_manifest", "dataset_manifest_digest", "adapter_path", "adapter_manifest", "adapter_manifest_digest",
             "input_image_path", "input_image_manifest", "input_image_manifest_digest"}
    snapshot = {key: value for key, value in original.items() if key in names}
    snapshot["attempt_id"] = "bundled-media-" + uuid.uuid4().hex
    return snapshot


def file_manifest(root):
    entries = [{"path": str(path.relative_to(root)), "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in sorted(root.rglob("*")) if path.is_file()]
    return entries, digest(entries)


def group_gone(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    return False


def stop_group(process):
    if not group_gone(process.pid):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        pass
    if not group_gone(process.pid):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def execute(binary, snapshot, output, empty, environment, tools, cancel=False):
    output.mkdir()
    snapshot_path = output / "snapshot.json"
    write(snapshot_path, snapshot)
    started = time.monotonic()
    preflight = subprocess.run([str(binary), "--mode", "preflight", "--snapshot", str(snapshot_path), "--output-dir", str(output / "result")],
                               cwd=empty, env=environment, capture_output=True, text=True, timeout=180)
    (output / "preflight.stdout.json").write_text(preflight.stdout)
    (output / "preflight.stderr.log").write_text(preflight.stderr)
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    facts = json.loads(preflight.stdout)
    assert facts["can_submit"] and not (output / "result").exists()
    snapshot["media_recipe_digest"] = facts["media_recipe_digest"]
    write(snapshot_path, snapshot)
    preflight_seconds = time.monotonic() - started
    command = [str(binary), "--mode", "launch", "--snapshot", str(snapshot_path), "--output-dir", str(output / "result"), "--controller-pid", str(os.getpid())]
    write(output / "command.json", command)
    cancelled = False
    print("开始内置真实执行：" + output.name, flush=True)
    with (output / "events.jsonl").open("wb") as stdout, (output / "worker.stderr.log").open("wb") as stderr:
        started = time.monotonic()
        process = subprocess.Popen(command, cwd=empty, env=environment, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while not (output / "process.json").exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            receipt = json.loads((output / "process.json").read_text())
            assert receipt["pid"] == process.pid and receipt["controller_pid"] == os.getpid()
            assert not (output / "result").exists(), "未经明确启动授权已创建产物"
            write(output / "start-authorized.json.tmp", {"pid": process.pid, "snapshot_sha256": receipt["snapshot_sha256"]})
            (output / "start-authorized.json.tmp").rename(output / "start-authorized.json")
            deadline = time.monotonic() + 600
            while process.poll() is None:
                if time.monotonic() > deadline:
                    raise TimeoutError("内置媒体执行超过 10 分钟")
                if cancel and not cancelled:
                    log = output / "result/executor.stderr.log"
                    if log.is_file() and b" 1/25 " in log.read_bytes():
                        os.killpg(process.pid, signal.SIGTERM)
                        cancelled = True
                time.sleep(0.05)
            returncode = process.wait(timeout=5)
            naturally_gone = group_gone(process.pid)
        finally:
            stop_group(process)
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    complete = [event for event in events if event["type"] == "completed"]
    assert naturally_gone, "媒体桥退出后仍有同组进程，验收脚本已回收残留"
    diagnostic = output / "result/executor.stderr.log"
    if diagnostic.is_file():
        content = diagnostic.read_text(errors="replace")
        assert "resource_tracker: process died unexpectedly" not in content and "resource_tracker: There appear to be" not in content and "Failed to execute script 'media_entry'" not in content, "资源追踪子进程失败或存在资源泄漏警告"
    result = {"pid": process.pid, "preflight_seconds": preflight_seconds, "execute_seconds": time.monotonic() - started,
              "returncode": returncode, "same_process_group_gone": True, "media_recipe_digest": facts["media_recipe_digest"]}
    if cancel:
        assert cancelled and returncode == 130 and not complete
        assert any(event["type"] == "error" and event.get("code") == "CANCELLED" for event in events)
        result.update(status="cancelled", observed_real_denoising_step=1, completed_event=False)
    else:
        assert returncode == 0 and len(complete) == 1, (output / "worker.stderr.log").read_text() + str(events[-3:])
        completed = complete[0]
        assert completed["source_model_unchanged"] and completed["effective_config"]["media_recipe_digest"] == facts["media_recipe_digest"]
        for item in completed["artifacts"]:
            assert hashlib.sha256((output / "result" / item["path"]).read_bytes()).hexdigest() == item["sha256"]
        primary = output / "result/result"
        if snapshot["kind"] == "audio":
            with wave.open(str(primary / "speech.wav"), "rb") as stream:
                assert (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) == (24000, 1, 2)
                assert stream.getnframes() > 0
                assert len(stream.readframes(stream.getnframes())) == stream.getnframes() * 2
                result["audio_frames"] = stream.getnframes()
        elif snapshot["kind"] == "video":
            probe = subprocess.run([str(tools / "bin/ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(primary / "video.mp4")],
                                   cwd=empty, env=environment, capture_output=True, text=True, check=True, timeout=60)
            info = json.loads(probe.stdout)["streams"][0]
            assert (info["width"], info["height"], info["nb_read_frames"], info["r_frame_rate"]) == (1024, 576, "14", "7/1")
            decoded = subprocess.run([str(tools / "bin/ffmpeg"), "-v", "error", "-i", str(primary / "video.mp4"), "-f", "framemd5", "-"],
                                     cwd=empty, env=environment, capture_output=True, text=True, check=True, timeout=60)
            assert len([line for line in decoded.stdout.splitlines() if line and not line.startswith("#")]) == 14
            (output / "independent-framemd5.txt").write_text(decoded.stdout)
            write(output / "independent-ffprobe.json", json.loads(probe.stdout))
        elif snapshot["operation"] == "train":
            assert [event["completed_steps"] for event in events if event["type"] == "metric" and "completed_steps" in event] == list(range(1, 13))
        else:
            data = (primary / "image.png").read_bytes()
            assert data[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(data[16:20], "big") == int.from_bytes(data[20:24], "big") == 512
        result.update(status="succeeded", artifact_count=len(completed["artifacts"]), all_sealed_artifact_hashes_verified=True)
    write(output / "verification.json", result)
    print("完成内置真实执行：" + output.name + " " + result["status"], flush=True)
    return result


def verify(args):
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {name: getattr(args, name.replace("-", "_") + "_snapshot") for name in ("image", "train", "video", "audio")}
    originals = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sources.items() if path}
    results, probes = {}, {}
    with tempfile.TemporaryDirectory(prefix="ailab-media-relocated-") as temporary:
        root = Path(temporary).resolve() / "runtime with spaces"
        root.mkdir()
        profiles = (["diffusers"] if any(sources[name] for name in ("image", "train", "video")) else []) + (["kokoro"] if sources["audio"] else [])
        for profile in [*profiles, "media-tools"]:
            shutil.copytree(args.resources / profile, root / profile, symlinks=True)
        empty, home, cache = [root / name for name in ("empty", "home", "temporary")]
        for directory in (empty, home, cache):
            directory.mkdir()
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(cache), "LANG": "en_US.UTF-8"}
        for profile in profiles:
            started = time.monotonic()
            binary = root / profile / ("ailab-" + profile)
            probe = subprocess.run([str(binary), "--mode", "probe"], cwd=empty, env=environment, capture_output=True, text=True, timeout=120)
            (args.output / (profile + ".probe.stderr.log")).write_text(probe.stderr)
            (args.output / (profile + ".probe.json")).write_text(probe.stdout)
            assert probe.returncode == 0, probe.stderr
            facts = json.loads(probe.stdout)
            assert facts["profile"] == profile and facts["device_ready"] and facts["resource_tracker_ready"]
            probes[profile] = {"seconds": time.monotonic() - started, "runtime_manifest_sha256": facts["runtime_manifest_sha256"],
                               "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "sources": facts["sources"]}
        for name in ("audio", "image", "train", "video"):
            if not sources[name]:
                continue
            profile = "kokoro" if name == "audio" else "diffusers"
            binary = root / profile / ("ailab-" + profile)
            snapshot = snapshot_from(sources[name])
            results[name] = execute(binary, snapshot, args.output / name, empty, environment, root / "media-tools")
            if name == "train":
                assert sources["image"], "适配器重载需提供图片生成快照"
                candidate = snapshot_from(sources["image"])
                adapter = args.output / "train/result/result"
                manifest, identity = file_manifest(adapter)
                candidate.update(adapter_path=str(adapter), adapter_manifest=manifest, adapter_manifest_digest=identity)
                results["adapter"] = execute(binary, candidate, args.output / "adapter", empty, environment, root / "media-tools")
            if name == "video" and args.cancel_video:
                results["video-cancel"] = execute(binary, snapshot_from(sources[name]), args.output / "video-cancel", empty, environment, root / "media-tools", cancel=True)
        assert not list(empty.iterdir()), "空工作目录出现未登记文件"
    assert all(hashlib.sha256(sources[name].read_bytes()).hexdigest() == identity for name, identity in originals.items()), "原验收快照被修改"
    report = {"status": "通过", "scope": "内置媒体运行时搬迁与真实执行；不代替最终 App 原生验收或发布验证", "resources": str(args.resources),
              "relocated": True, "python_override": None, "environment_path": "/usr/bin:/bin", "empty_working_directory": True,
              "source_snapshot_hashes": originals, "probes": probes, "results": results}
    write(args.output / "report.json", report)
    print(json.dumps({"status": report["status"], "report": str(args.output / "report.json")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resources", type=lambda value: Path(value).resolve())
    parser.add_argument("--output", type=lambda value: Path(value).resolve(), required=True)
    for name in ("image", "train", "video", "audio"):
        parser.add_argument("--" + name + "-snapshot", type=lambda value: Path(value).resolve())
    parser.add_argument("--cancel-video", action="store_true")
    options = parser.parse_args()
    if not any(getattr(options, name + "_snapshot") for name in ("image", "train", "video", "audio")):
        parser.error("必须提供至少一种真实媒体快照")
    if options.train_snapshot and not options.image_snapshot:
        parser.error("训练验收必须同时提供图片快照，以验证适配器重载")
    verify(options)
