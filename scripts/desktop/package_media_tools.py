"""复制媒体工具实际动态库闭包，改为包内相对路径并签名验证。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

IDENTITY = "Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)"
LOAD_COMMANDS = {"LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB", "LC_LAZY_LOAD_DYLIB", "LC_LOAD_UPWARD_DYLIB"}
SYSTEM = ("/usr/lib/", "/System/Library/")


def run(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60, **kwargs)
    if result.returncode:
        raise RuntimeError(f"命令失败：{args[0]}\n{result.stderr or result.stdout}")
    return result.stdout


def macho(path):
    loads, rpaths, identity = [], [], None
    command = ""
    for line in run("/usr/bin/otool", "-l", str(path)).splitlines():
        fields = line.strip().split()
        if len(fields) > 1 and fields[0] == "cmd":
            command = fields[1]
        if fields and fields[0] == "name" and command in LOAD_COMMANDS | {"LC_ID_DYLIB"}:
            value = line.strip()[5:].split(" (offset", 1)[0]
            if command == "LC_ID_DYLIB":
                identity = value
            else:
                loads.append(value)
        if fields and fields[0] == "path" and command == "LC_RPATH":
            rpaths.append(line.strip()[5:].split(" (offset", 1)[0])
    return {"loads": list(dict.fromkeys(loads)), "rpaths": list(dict.fromkeys(rpaths)), "identity": identity}


def resolve_load(name, owner, executable, rpaths):
    def expanded(value):
        return value.replace("@loader_path", str(owner.parent)).replace("@executable_path", str(executable.parent))
    if name.startswith("@rpath/"):
        candidates = [Path(expanded(root)) / name[7:] for root in rpaths]
    else:
        candidates = [Path(expanded(name))]
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_file():
            return candidate.resolve(strict=True)
    raise ValueError(f"无法解析媒体工具依赖：{owner.name} → {name}")


def closure(entries):
    pending = [(path.resolve(strict=True), path.resolve(strict=True), []) for path in entries]
    result = {}
    while pending:
        path, executable, inherited_rpaths = pending.pop()
        if path in result:
            continue
        info = macho(path)
        resolved = {}
        for name in info["loads"]:
            if name.startswith(SYSTEM):
                continue
            target = resolve_load(name, path, executable, [*info["rpaths"], *inherited_rpaths])
            resolved[name] = target
            pending.append((target, executable, [*info["rpaths"], *inherited_rpaths]))
        result[path] = {**info, "resolved": resolved}
    return result


def copy_licenses(sources, output):
    records = []
    roots = set()
    for source in sources:
        if "Cellar" not in source.parts:
            raise ValueError("当前媒体工具来源必须有可核验的 Homebrew 配方与许可")
        index = source.parts.index("Cellar")
        roots.add(Path(*source.parts[:index + 3]))
    for root in sorted(roots):
        files = [path for path in root.iterdir() if path.is_file() and
                 (path.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS")) or path.name in {"INSTALL_RECEIPT.json", "sbom.spdx.json"})]
        if not any(path.name.upper().startswith(("LICENSE", "COPYING")) for path in files):
            raise ValueError("缺少媒体工具依赖许可：" + str(root))
        destination = output / "licenses" / root.parent.name
        destination.mkdir(parents=True)
        for path in files:
            shutil.copy2(path, destination / path.name)
        records.append({"name": root.parent.name, "version": root.name,
                        "files": [str((destination / path.name).relative_to(output)) for path in files]})
    return records


def verify_relocated(output):
    with tempfile.TemporaryDirectory(prefix="ailab-media-tools-") as temporary:
        base = Path(temporary).resolve()
        moved = base / "媒体工具 搬移验证"
        shutil.copytree(output, moved, symlinks=True)
        cwd = base / "empty"
        cwd.mkdir()
        environment = {"PATH": "/usr/bin:/bin", "HOME": str(base), "TMPDIR": str(base)}
        video = cwd / "sample.mp4"
        ffmpeg, ffprobe = moved / "bin/ffmpeg", moved / "bin/ffprobe"
        run(str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=32x32:rate=7", "-frames:v", "14", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-n", str(video), cwd=cwd, env=environment)
        facts = json.loads(run(str(ffprobe), "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(video), cwd=cwd, env=environment))
        stream = facts["streams"][0]
        if (stream["width"], stream["height"], stream["r_frame_rate"], stream["nb_read_frames"], stream["codec_name"]) != (32, 32, "7/1", "14", "h264"):
            raise ValueError("搬移后的媒体编码／独立解码结果不符")
        decoded = run(str(ffmpeg), "-v", "error", "-i", str(video), "-f", "framemd5", "-", cwd=cwd, env=environment)
        if len([line for line in decoded.splitlines() if line and not line.startswith("#")]) != 14:
            raise ValueError("搬移后的逐帧解码未取得完整 14 帧")
        return {"status": "passed", "relocated": True, "empty_cwd": True, "path": environment["PATH"], "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(), "stream": stream, "decoded_frames": 14}


def build(root, ffmpeg, ffprobe):
    output = root / "apps/desktop/src-tauri/resources/media-tools"
    if output.exists():
        shutil.rmtree(output)
    (output / "bin").mkdir(parents=True)
    (output / "lib").mkdir()
    entries = {ffmpeg.resolve(strict=True), ffprobe.resolve(strict=True)}
    sources = closure(entries)
    targets = {source: output / ("bin" if source in entries else "lib") / source.name for source in sources}
    if len(set(targets.values())) != len(targets):
        raise ValueError("媒体依赖出现同名不同源文件，停止打包")
    licenses = copy_licenses(sources, output)
    original_files = {str(source): hashlib.sha256(source.read_bytes()).hexdigest() for source in sources}
    for source, destination in targets.items():
        shutil.copy2(source, destination)
        os.chmod(destination, 0o755)
    for source, destination in targets.items():
        # 所有修改仅作用于生成目录，原 Homebrew 文件不变。
        subprocess.run(["/usr/bin/codesign", "--remove-signature", str(destination)], capture_output=True, check=False)
        info = sources[source]
        arguments = ["/usr/bin/install_name_tool"]
        if info["identity"]:
            arguments.extend(["-id", "@rpath/" + destination.name])
        for old, dependency in info["resolved"].items():
            relative = os.path.relpath(targets[dependency], destination.parent)
            arguments.extend(["-change", old, "@loader_path/" + relative])
        for rpath in info["rpaths"]:
            if rpath.startswith("/") and not rpath.startswith(SYSTEM):
                arguments.extend(["-delete_rpath", rpath])
        if len(arguments) > 1:
            run(*arguments, str(destination))
        run("/usr/bin/codesign", "--force", "--options", "runtime", "--sign", IDENTITY, str(destination))
        run("/usr/bin/codesign", "--verify", "--strict", str(destination))
        info = macho(destination)
        if any(name.startswith("/") and not name.startswith(SYSTEM) for name in info["loads"]):
            raise ValueError("媒体依赖仍有开发机绝对路径")
        for name in info["loads"]:
            if name.startswith(SYSTEM):
                continue
            resolved = resolve_load(name, destination, output / "bin/ffmpeg", info["rpaths"])
            if not resolved.is_relative_to(output):
                raise ValueError("媒体依赖越出打包目录")
    version = run(str(output / "bin/ffmpeg"), "-version")
    (output / "licenses/index.json").write_text(json.dumps(licenses, ensure_ascii=False, indent=2) + "\n")
    (output / "build-info.json").write_text(json.dumps({"schema_version": 1, "original_files": original_files, "ffmpeg_version": version}, ensure_ascii=False, indent=2) + "\n")
    report = verify_relocated(output)
    for source, expected in original_files.items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest() != expected:
            raise ValueError("打包期间源媒体工具发生变化")
    files = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.rglob("*")) if path.is_file()}
    (output / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "files": files}, sort_keys=True, indent=2) + "\n")
    report.update(output=str(output), file_count=len(sources), original_bytes=sum(source.stat().st_size for source in sources), source_unchanged=True)
    (root / ".artifacts/desktop/media-tools-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--ffmpeg", type=Path, default=Path("/opt/homebrew/bin/ffmpeg"))
    parser.add_argument("--ffprobe", type=Path, default=Path("/opt/homebrew/bin/ffprobe"))
    args = parser.parse_args()
    build(args.root.resolve(), args.ffmpeg, args.ffprobe)
