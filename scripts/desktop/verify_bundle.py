"""验证本机候选身份和资源完整性，输出可追溯 JSON，不作公证发布声明。"""

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile

from package_media_tools import macho
from app_version import bundle_version
import transformers_index


def command(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout + result.stderr


def verify_transformers_indices(resources, source_files):
    """核最终 App 的实际目录顺序与冻结来源；失败不修改索引或继续探测。"""
    generator_hash = hashlib.sha256(Path(transformers_index.__file__).read_bytes()).hexdigest()
    assert source_files.get("application/scripts/desktop/transformers_index.py") == generator_hash, "索引核验器与本次冻结生成器不一致"
    loader_hash = source_files.get("application/scripts/desktop/transformers_index_runtime.py")
    results = {}
    for profile in ("diffusers", "kokoro"):
        internal = resources / profile / "_internal"
        package = internal / "transformers"
        for path in (internal / "source-manifest.json", package / transformers_index.INDEX_NAME,
                     package / transformers_index.LOADER_NAME, package / "__init__.py"):
            assert path.is_file(), f"内置 {profile} 缺少索引或来源文件：{path.name}"
        manifest = json.loads((internal / "source-manifest.json").read_text())
        assert manifest.get("profile") == profile, f"内置 {profile} 索引所属运行时不符"
        assert manifest.get("required_dependencies", {}).get("transformers") == "4.57.6", f"内置 {profile} Transformers 依赖版本不符"
        provenance = manifest.get("transformers_index")
        assert isinstance(provenance, dict) and provenance.get("transformers_version") == "4.57.6", f"内置 {profile} 缺少固定索引来源"
        assert provenance.get("generator_sha256") == generator_hash, f"内置 {profile} 索引生成器来源不符"
        actual_loader = hashlib.sha256((package / transformers_index.LOADER_NAME).read_bytes()).hexdigest()
        assert actual_loader == loader_hash == provenance.get("loader_sha256"), f"内置 {profile} 索引读取器与冻结来源不符"
        actual_init = hashlib.sha256((package / "__init__.py").read_bytes()).hexdigest()
        assert actual_init == provenance.get("patched_init_sha256"), f"内置 {profile} Transformers 顶层来源不符"
        actual_index = hashlib.sha256((package / transformers_index.INDEX_NAME).read_bytes()).hexdigest()
        assert actual_index == provenance.get("index_sha256"), f"内置 {profile} 索引摘要不符"
        # 校验自有读取器身份之后，才由它恢复索引并与实际最终目录的原算法顺序比较。
        checked = transformers_index.verify_final_index(package)
        assert checked["index_sha256"] == actual_index, f"内置 {profile} 索引核验结果与当前字节不符"
        results[profile] = {**checked, "transformers_version": "4.57.6", "loader_sha256": actual_loader,
                            "generator_sha256": generator_hash, "patched_init_sha256": actual_init}
    return results


def verify(app: Path):
    app = app.resolve(strict=True)
    metadata = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert metadata["CFBundleIdentifier"] == "org.gcsa.ailab", "应用标识不一致"
    verification = command("codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))
    signature = command("codesign", "-dvvv", str(app))
    assert "Authority=Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)" in signature, "签名组织不一致"
    with tempfile.TemporaryDirectory() as temporary:
        prefix = str(Path(temporary) / "certificate")
        command("codesign", "-d", "--extract-certificates=" + prefix, str(app))
        certificate = hashlib.sha1(Path(prefix + "0").read_bytes()).hexdigest().upper()
        assert certificate == "7C33B517942161311A087CE893D2F1CE9B204B44", "签名证书指纹不一致"
    files = {}
    links = {}
    macho_files = []
    for path in sorted(app.rglob("*")):
        relative = str(path.relative_to(app))
        if path.is_symlink():
            assert path.resolve().is_relative_to(app), f"资源链接越界：{relative}"
            links[relative] = str(path.readlink())
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            with path.open("rb") as stream:
                magic = stream.read(4)
            if magic in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
                for dependency in macho(path)["loads"]:
                    assert dependency.startswith(("@", "/usr/lib/", "/System/Library/")), f"二进制仍依赖开发机路径：{relative} → {dependency}"
                macho_files.append(relative)
    resources = app / "Contents/Resources/resources"
    for relative in ["control/ailab-control", "control/_internal/certifi/cacert.pem", "workers/mlx_worker.py", "adapters/mlx_text/preflight.py", "adapters/mlx_text/recipe.py", "mlx/ailab-mlx", "mlx/runtime-manifest.json", "mlx/licenses/index.json",
                     "diffusers/ailab-diffusers", "kokoro/ailab-kokoro", "diffusers/runtime-manifest.json", "kokoro/runtime-manifest.json", "diffusers/licenses/index.json", "kokoro/licenses/index.json",
                     "media-tools/bin/ffmpeg", "media-tools/bin/ffprobe", "media-tools/runtime-manifest.json", "media-tools/licenses/index.json"]:
        assert (resources / relative).is_file(), f"缺少资源：{relative}"
    python_build = command("/usr/bin/vtool", "-show-build", str(resources / "control/_internal/Python.framework/Versions/3.13/Python"))
    assert "minos 26.0" in python_build and metadata["LSMinimumSystemVersion"] == "26.0", "控制运行时与应用最低系统声明不一致"
    report = {
        "status": "本机候选身份和资源校验通过",
        "bundle_identifier": metadata["CFBundleIdentifier"], "version": metadata["CFBundleShortVersionString"],
        "minimum_macos": metadata["LSMinimumSystemVersion"], "architecture": "arm64", "certificate_sha1": certificate,
        "bundle_manifest_sha256": hashlib.sha256(json.dumps({"files": files, "links": links}, sort_keys=True).encode()).hexdigest(),
        "file_sha256": files, "symlinks": links, "signature": signature, "verification": verification,
        "relocatable_macho_files": macho_files,
        "notarization": "未执行", "distribution_acceptance": "未验证独立机器发布",
    }
    source_manifest = resources / "control/build-manifest.json"
    assert source_manifest.is_file(), "缺少本次冻结源码清单"
    report["control_build_manifest"] = json.loads(source_manifest.read_text())
    report["application_version"] = bundle_version(app, report["control_build_manifest"])
    source_files = report["control_build_manifest"]["files"]
    assert hashlib.sha256(json.dumps(source_files, sort_keys=True).encode()).hexdigest() == report["control_build_manifest"]["source_digest"], "源码清单自身摘要不符"
    for relative, expected_hash in source_files.items():
        if relative.startswith(("workers/", "adapters/", "services/")):
            assert hashlib.sha256((resources / relative).read_bytes()).hexdigest() == expected_hash, f"执行资源与源码清单不一致：{relative}"
    report["transformers_indices"] = verify_transformers_indices(resources, source_files)
    with tempfile.TemporaryDirectory(prefix="ailab-verify-empty-") as empty:
        empty = str(Path(empty).resolve())
        contract = subprocess.run([str(resources / 'control/ailab-control'), '--verify-source-contract'], cwd=empty,
                                  env={'PATH': '/usr/bin:/bin', 'TMPDIR': empty}, capture_output=True, text=True, timeout=30)
        assert contract.returncode == 0, '内置控制层不能读取同源 NVIDIA 参数合同：' + contract.stderr
        report['control_source_contract'] = json.loads(contract.stdout)
        assert report['control_source_contract']['model_execution'] is False and report['control_source_contract']['device_probe'] is False
        for relative, expected_hash in source_files.items():
            if relative.startswith(('workers/', 'adapters/')) and relative.endswith('.py'):
                assert report['control_source_contract']['sources'].get(relative) == expected_hash, '内置控制层合同与冻结源码不一致：' + relative
        contract_sources = {name: source_files[name] for name in ('adapters/nvidia_text/adapter.py', 'workers/nvidia_worker.py',
                           'adapters/mlx_text/recipe.py', 'adapters/mlx_text/generation.py', 'adapters/mlx_text/evaluation.py')}
        expected_contract = hashlib.sha256(json.dumps(contract_sources, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert report['control_source_contract']['source_code_digest'] == expected_contract, '内置 NVIDIA 合同身份与原执行源码不一致'
        probe = subprocess.run([str(resources / "mlx/ailab-mlx"), "--mode", "probe"], cwd=empty, capture_output=True, text=True, timeout=60)
        assert probe.returncode == 0, "内置执行环境空工作目录探测失败：" + probe.stderr
        report["bundled_mlx_probe"] = json.loads(probe.stdout)
        assert report["bundled_mlx_probe"]["metal"], "内置 MLX 未检测到 Metal"
        bundled_sources = report["bundled_mlx_probe"]["sources"]
        for relative, expected_hash in source_files.items():
            if relative.startswith(("workers/", "adapters/")) and relative.endswith(".py"):
                assert bundled_sources.get(relative) == expected_hash, f"冻结的 MLX 模块与控制源码清单不一致：{relative}"
        assert bundled_sources["entry"] == source_files["entry/mlx_entry.py"], "内置入口与控制源码清单不一致"
        assert report["bundled_mlx_probe"]["requirements_lock_sha256"] == source_files["adapters/mlx_text/requirements.lock.txt"], "内置 MLX 依赖锁与控制源码清单不一致"
        snapshot = Path(empty) / "invalid-snapshot.json"
        snapshot.write_text("{}")
        evaluation = subprocess.run([str(resources / "mlx/ailab-mlx"), "--mode", "evaluation-pass", "--snapshot", str(snapshot), "--output-dir", str(Path(empty) / "output"), "--variant", "baseline"], cwd=empty, capture_output=True, text=True, timeout=60)
        assert evaluation.returncode == 1 and json.loads(evaluation.stdout)["code"] == "UNSUPPORTED_OPERATION", "内置独立评测入口未正确校验输入"
        for profile in ("diffusers", "kokoro"):
            environment = {"PATH": "/usr/bin:/bin", "HOME": empty, "TMPDIR": empty}
            result = subprocess.run([str(resources / profile / f"ailab-{profile}"), "--mode", "probe"], cwd=empty, env=environment, capture_output=True, text=True, timeout=120)
            assert result.returncode == 0, f"内置 {profile} 空工作目录探测失败：" + result.stderr
            facts = json.loads(result.stdout)
            assert facts["profile"] == profile and facts["device_ready"] and facts["resource_tracker_ready"], f"内置 {profile} 实际设备、入口或资源追踪子进程不可用"
            for relative, expected_hash in source_files.items():
                if relative.startswith(("workers/", "adapters/", "services/")) and (relative.endswith(".py") or relative.endswith("lock.txt")):
                    assert facts["sources"].get(relative) == expected_hash, f"内置 {profile} 与控制源码清单不一致：{relative}"
            assert facts["sources"]["entry/media_entry.py"] == source_files["entry/media_entry.py"], f"内置 {profile} 入口不一致"
            assert facts["requirements_lock_sha256"] == source_files[f"entry/runtime-{profile}.lock.txt"], f"内置 {profile} 依赖锁不一致"
            assert hashlib.sha256((resources / profile / "dependency-sources.json").read_bytes()).hexdigest() == source_files[f"entry/runtime-{profile}.sources.json"], f"内置 {profile} 依赖来源清单不一致"
            report[f"bundled_{profile}_probe"] = facts
        tools_manifest = json.loads((resources / "media-tools/runtime-manifest.json").read_text())
        for relative, expected_hash in tools_manifest["files"].items():
            assert hashlib.sha256((resources / "media-tools" / relative).read_bytes()).hexdigest() == expected_hash, "内置媒体工具摘要不符：" + relative
        report["bundled_evaluation_entry"] = "独立入口已加载，无效快照已拒绝"
    for binary in ["control/ailab-control", "mlx/ailab-mlx", "diffusers/ailab-diffusers", "kokoro/ailab-kokoro", "media-tools/bin/ffmpeg", "media-tools/bin/ffprobe"]:
        assert "Authority=Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)" in command("codesign", "-dvvv", str(resources / binary)), "子进程签名组织不一致"
        with tempfile.TemporaryDirectory() as temporary:
            prefix = str(Path(temporary) / "certificate")
            command("codesign", "-d", "--extract-certificates=" + prefix, str(resources / binary))
            assert hashlib.sha1(Path(prefix + "0").read_bytes()).hexdigest().upper() == certificate, "子进程签名证书与 App 不一致"
    for profile in ("mlx", "diffusers", "kokoro", "media-tools"):
        report[f"bundled_{profile}_size_bytes"] = sum(path.stat().st_size for path in (resources / profile).rglob("*") if path.is_file() and not path.is_symlink())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = verify(arguments.app)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result["status"] + "：" + result["bundle_manifest_sha256"])
