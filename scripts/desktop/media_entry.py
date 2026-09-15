"""内置媒体固定入口；只分派已冻结的配方，不接受任意 Python 脚本。"""

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import time


PROBE_STAGE_PREFIX = "AILAB_PROBE_STAGE_V1 "
PROBE_STAGES = {"runtime_files", "media_tools_files", "dependency_versions", "torch_import", "engine_imports", "tracker_start", "tracker_reap"}


@contextlib.contextmanager
def probe_stage(stage, *, enabled=True):
    """独立输出固定阶段；失败与超时也能保留此前已完成的测量。"""
    if not enabled:
        yield
        return
    if stage not in PROBE_STAGES:
        raise ValueError("不支持的探测阶段")
    started, status = time.monotonic(), "failed"
    try:
        yield
        status = "succeeded"
    finally:
        elapsed = time.monotonic() - started
        if math.isfinite(elapsed) and elapsed >= 0:
            record = {"stage": stage, "status": status, "elapsed_seconds": round(elapsed, 6)}
            # 单独起行，避免依赖库未换行的输出吞掉标记；不传递异常文本。
            print("\n" + PROBE_STAGE_PREFIX + json.dumps(record, separators=(",", ":")), file=sys.stderr, flush=True)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def resources():
    root = Path(sys._MEIPASS)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root / "adapters/media"))
    sys.path.insert(0, str(root / "services/control"))
    tools = root.parent.parent / "media-tools/bin"
    os.environ.update(PATH=f"{tools}:/usr/bin:/bin:/usr/sbin:/sbin", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1", TOKENIZERS_PARALLELISM="false")
    return root


def file_hash(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def file_identity(record):
    """内容摘要只能复用于仍相同的文件；ctime 避免仅恢复 mtime 蒙混过关。"""
    return (record.st_dev, record.st_ino, record.st_size, record.st_mtime_ns, record.st_ctime_ns)


def verify_files(root):
    """每次分派前核对完整文件集合与当前字节，不把版本号当作文件身份。"""
    root = root.resolve()
    manifest_path = root / "runtime-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("内置运行时缺少有效的完整文件清单")
    document = json.loads(manifest_path.read_text())
    files = document.get("files")
    if document.get("schema_version") != 1 or not isinstance(files, dict) or not 1 <= len(files) <= 50000:
        raise ValueError("内置运行时完整文件清单格式无效")
    for relative, expected in files.items():
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts or Path(relative).as_posix() != relative or relative in {"", ".", "runtime-manifest.json"}:
            raise ValueError("内置运行时清单含越界或无效路径")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("内置运行时清单含无效文件摘要")
    actual, links = set(), {}
    directories = {root: file_identity(root.stat())}
    for path in root.rglob("*"):
        record = path.lstat()
        if stat.S_ISLNK(record.st_mode):
            if not path.exists() or not (resolved := path.resolve()).is_relative_to(root):
                raise ValueError("内置运行时含越界或失效链接")
            links[path] = (file_identity(record), resolved)
            record = path.stat()
        if stat.S_ISREG(record.st_mode):
            if path != manifest_path:
                actual.add(path.relative_to(root).as_posix())
        elif stat.S_ISDIR(record.st_mode):
            if path not in links:
                directories[path] = file_identity(record)
        else:
            raise ValueError("内置运行时含非常规文件")
    if actual != set(files):
        raise ValueError("内置运行时的文件集合与冻结清单不一致")
    # 缓存只属于本次校验，别名仍逐项核对期望摘要和最终路径身份。
    hashes, verified = {}, {}
    for relative, expected in files.items():
        path = root / relative
        # 普通文件的各层目录已由上面的遍历登记；链接只解析一次。
        resolved = links[path][1] if path in links else path
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            record = os.fstat(stream.fileno())
            if not stat.S_ISREG(record.st_mode):
                raise ValueError("内置运行时含非常规文件")
            identity = file_identity(record)
            if identity not in hashes:
                value = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(chunk)
                hashes[identity] = value.hexdigest()
            if file_identity(os.fstat(stream.fileno())) != identity:
                raise ValueError("内置运行时文件在校验期间变化：" + relative)
        if hashes[identity] != expected:
            raise ValueError("内置运行时文件摘要不一致：" + relative)
        verified[path] = identity
    # 后续文件检查期间，已读文件和链接也不能悄悄变成另一个对象。
    for path, identity in directories.items():
        record = path.lstat()
        if not stat.S_ISDIR(record.st_mode) or file_identity(record) != identity:
            raise ValueError("内置运行时目录在校验期间变化")
    for path, (identity, resolved) in links.items():
        record = path.lstat()
        if not stat.S_ISLNK(record.st_mode) or file_identity(record) != identity or path.resolve(strict=True) != resolved:
            raise ValueError("内置运行时链接在校验期间变化")
    for path, identity in verified.items():
        record = path.stat() if path in links else path.lstat()
        if not stat.S_ISREG(record.st_mode) or file_identity(record) != identity:
            raise ValueError("内置运行时文件在校验期间变化：" + path.relative_to(root).as_posix())
    return file_hash(manifest_path)


def manifest(*, probe_stages=False):
    root = resources()
    source = json.loads((root / "source-manifest.json").read_text())
    if source.get("profile") not in {"diffusers", "kokoro"}:
        raise ValueError("内置媒体 profile 无效")
    with probe_stage("runtime_files", enabled=probe_stages):
        verify_files(root.parent)
    if source["profile"] == "diffusers":
        with probe_stage("media_tools_files", enabled=probe_stages):
            verify_files(root.parent.parent / "media-tools")
    return root, source


def probe(root, source):
    runtime = root.parent / "runtime-manifest.json"
    with probe_stage("dependency_versions"):
        versions = {name: importlib.metadata.version(name) for name in source["required_dependencies"]}
        if versions != source["required_dependencies"] or platform.python_version() != source["python"]:
            raise ValueError("内置媒体 Python 或依赖版本与冻结清单不一致")
    with contextlib.redirect_stdout(sys.stderr):
        with probe_stage("torch_import"):
            import torch
        with probe_stage("engine_imports"):
            if source["profile"] == "diffusers":
                from diffusers import StableDiffusionPipeline, StableVideoDiffusionPipeline
                import peft
                ready = torch.backends.mps.is_available()
            else:
                import kokoro
                from misaki import zh
                ready = True
    with probe_stage("tracker_start"):
        from multiprocessing import util
        reader, writer = os.pipe()
        try:
            tracker = subprocess.Popen([sys.executable, *util._args_from_interpreter_flags(), "-c", f"from multiprocessing.resource_tracker import main;main({reader})"],
                                       pass_fds=[reader], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            os.close(reader)
            os.close(writer)
    with probe_stage("tracker_reap"):
        try:
            output, errors = tracker.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            tracker.kill()
            tracker.communicate()
            raise ValueError("内置资源追踪器未及时退出") from None
        if tracker.returncode or output or errors:
            raise ValueError("内置资源追踪器未正常退出")
    print(json.dumps({"profile": source["profile"], "python": platform.python_version(), "dependencies": versions, "device_ready": ready,
                      "interpreter_flags": util._args_from_interpreter_flags(), "resource_tracker_ready": True,
                      "sources": source["sources"], "runtime_manifest_sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
                      "requirements_lock_sha256": source["requirements_lock_sha256"]}, ensure_ascii=False))
    return 0


def worker(args, mode, profile):
    sys.argv = [sys.argv[0], "--snapshot", str(args.snapshot), "--output-dir", str(args.output_dir)]
    if profile == "kokoro":
        from workers.tts_worker import main
        if mode == "preflight":
            sys.argv.append("--preflight")
    elif mode == "preflight":
        from adapters.media.preflight import main
    else:
        from workers.media_worker import main
    return main()


def launch(args, profile):
    if os.getppid() != args.controller_pid:
        return 130
    run = args.snapshot.parent
    identity = subprocess.run(["/bin/ps", "-p", str(os.getpid()), "-o", "lstart="], capture_output=True, text=True, timeout=3)
    if identity.returncode or not identity.stdout.strip():
        return 1
    record = {"pid": os.getpid(), "controller_pid": args.controller_pid, "owned": True,
              "identity": {"status": "present", "pid": os.getpid(), "identity_digest": hashlib.sha256(canonical({"pid": os.getpid(), "started": identity.stdout.strip()})).hexdigest()},
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
    if file_hash(args.snapshot) != record["snapshot_sha256"]:
        return 1
    os.environ["AILAB_CONTROL_PID"] = str(args.controller_pid)
    return worker(args, "run", profile)


def resource_tracker(arguments):
    """只接受标准库资源追踪器的完整固定调用，不执行传入的 Python 文本。"""
    if "-c" not in arguments:
        return None
    from multiprocessing import util
    # PyInstaller 启动时会自行设置 -S/-I 等选项；逐项匹配当前解释器的
    # 受信配置，不能把外部提供的任意前缀交回解释器或 exec。
    prefix = arguments[:-2]
    if len(arguments) < 2 or arguments[-2] != "-c" or prefix not in ([], ["-B"], util._args_from_interpreter_flags()):
        raise ValueError("不接受任意解释器参数或脚本")
    match = re.fullmatch(r"from multiprocessing\.resource_tracker import main;main\(([0-9]{1,10})\)", arguments[-1])
    if match is None:
        raise ValueError("只接受固定资源追踪器调用")
    descriptor = int(match[1])
    import fcntl
    if descriptor <= 2 or not stat.S_ISFIFO(os.fstat(descriptor).st_mode) or fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
        raise ValueError("资源追踪器必须使用继承的只读管道")
    from multiprocessing.resource_tracker import main as track
    return track(descriptor) or 0


def main():
    tracked = resource_tracker(sys.argv[1:])
    if tracked is not None:
        return tracked
    parser = argparse.ArgumentParser(description="GCSA AI Lab 内置媒体执行环境", allow_abbrev=False)
    parser.add_argument("--mode", choices=["probe", "preflight", "launch", "run", "image-cli", "video-cli"], required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--controller-pid", type=int)
    args, remainder = parser.parse_known_args()
    root, source = manifest(probe_stages=args.mode == "probe")
    profile = source["profile"]
    if args.mode in {"image-cli", "video-cli"}:
        if profile != "diffusers" or args.snapshot is not None or args.output_dir is not None or args.controller_pid is not None:
            parser.error("此 profile 不接受图片／视频内部命令或通用快照参数")
        sys.argv = [sys.argv[0], *remainder]
        if args.mode == "image-cli":
            from adapters.media.image_cli import main as execute
        else:
            from adapters.media.video_cli import main as execute
        return execute()
    if remainder:
        parser.error("不接受未声明的命令或任意脚本")
    if args.mode == "probe":
        return probe(root, source)
    if args.snapshot is None or args.output_dir is None:
        parser.error("此命令必须提供 --snapshot 和 --output-dir")
    if args.mode == "launch":
        if args.controller_pid is None:
            parser.error("launch 必须提供 --controller-pid")
        return launch(args, profile)
    return worker(args, args.mode, profile)


if __name__ == "__main__":
    raise SystemExit(main())
