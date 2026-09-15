"""本机 CPU 中文配音执行器；仅加载已核验的固定官方模型与音色。"""

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
import signal
import socket
import sys
import sysconfig
import time
import wave

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_prepare import FILES, REPOSITORY, REVISION, file_hash, verify

VERSIONS = {"kokoro": "0.9.4", "misaki": "0.9.4", "torch": "2.14.0", "transformers": "4.57.6", "soundfile": "0.13.1"}
MAX_CHARACTERS = 120
SUPPORTED_TEXT = re.compile(r"[\u3400-\u9fff0-9\s.,!?;:，。！？、：；“”‘’（）()《》〈〉…—－\-·%％/]+")


class TTSError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def environment_snapshot():
    frozen = bool(getattr(sys, "frozen", False))
    package_paths = [str(Path(sys._MEIPASS))] if frozen else sorted({sysconfig.get_paths()[name] for name in ("purelib", "platlib")})
    packages = sorted({(distribution.metadata["Name"], distribution.version) for distribution in importlib.metadata.distributions(path=package_paths)})
    environment = {"python": platform.python_version(), "platform": platform.platform(), "dependencies": packages}
    if frozen:
        root = Path(sys._MEIPASS)
        source = json.loads((root / "source-manifest.json").read_text())
        normalized = {re.sub(r"[-_.]+", "-", name).lower(): version for name, version in packages}
        required = source.get("required_dependencies", {})
        if source.get("profile") != "kokoro" or not required or any(normalized.get(re.sub(r"[-_.]+", "-", name).lower()) != version for name, version in required.items()):
            raise TTSError("ENVIRONMENT_CHANGED", "内置配音运行时的实际依赖与完整冻结清单不一致。")
        environment["runtime_manifest_sha256"] = file_hash(root.parent / "runtime-manifest.json")
    return environment


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def emit(kind, **fields):
    print(json.dumps({"type": kind, **fields}, ensure_ascii=False, allow_nan=False), flush=True)


def cancelled(*_):
    raise TTSError("CANCELLED", "配音已取消，未发布完整音频。")


@contextlib.contextmanager
def offline_mode():
    from unittest.mock import patch

    def denied(*args, **kwargs):
        raise TTSError("NETWORK_NOT_ALLOWED", "推理阶段不允许网络连接；请先完成固定模型准备。")

    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1", TOKENIZERS_PARALLELISM="false", TORCH_FORCE_WEIGHTS_ONLY_LOAD="1")
    with patch.object(socket.socket, "connect", denied), patch.object(socket, "create_connection", denied):
        yield


def strict_state(module, state, torch):
    """只补官方 AdaIN 的恒等仿射项，其它缺失或多余权重均拒绝。"""
    prefixed = [name.startswith("module.") for name in state]
    if any(prefixed) and not all(prefixed):
        raise TTSError("MODEL_STATE_MISMATCH", "权重混用不同前缀。")
    normalized = {name[7:] if prefixed and all(prefixed) else name: value for name, value in state.items()}
    expected = module.state_dict()
    if set(normalized) - set(expected):
        raise TTSError("MODEL_STATE_MISMATCH", "权重中包含未声明参数。")
    defaults = []
    for name in sorted(set(expected) - set(normalized)):
        parent_path, _, leaf = name.rpartition(".")
        parent = module.get_submodule(parent_path)
        owner_path, _, _ = parent_path.rpartition(".")
        owner = module.get_submodule(owner_path)
        if not isinstance(parent, torch.nn.InstanceNorm1d) or type(owner).__name__ != "AdaIN1d" or type(owner).__module__ != "kokoro.istftnet" or leaf not in {"weight", "bias"} or not parent.affine or parent.track_running_stats:
            raise TTSError("MODEL_STATE_MISMATCH", "官方权重缺少非恒等归一化参数：" + name)
        value = expected[name]
        neutral = torch.ones_like(value) if leaf == "weight" else torch.zeros_like(value)
        if not torch.equal(value, neutral):
            raise TTSError("MODEL_STATE_MISMATCH", "缺失的归一化参数不再是官方恒等初值。")
        normalized[name] = neutral
        defaults.append({"path": name, "value": 1 if leaf == "weight" else 0, "numel": value.numel()})
    return normalized, {"module": type(module).__name__, "source_tensor_count": len(state), "tensor_count": len(normalized), "strict": True, "module_prefix_removed": bool(prefixed and all(prefixed)), "identity_defaults": defaults}


def validate(snapshot, output):
    if not isinstance(snapshot, dict) or snapshot.get("kind") != "audio" or snapshot.get("operation") != "generate":
        raise TTSError("UNSUPPORTED_COMBINATION", "当前只开放中文文本配音。")
    if not isinstance(snapshot.get("input"), dict) or set(snapshot["input"]) != {"prompt"}:
        raise TTSError("INVALID_CONFIG", "配音输入只接受明确的文本字段。")
    text = snapshot["input"]["prompt"]
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARACTERS or not re.search(r"[\u3400-\u9fff]", text) or not SUPPORTED_TEXT.fullmatch(text):
        raise TTSError("INVALID_TTS_TEXT", "请输入 1—120 字中文、数字和常用标点；当前不支持夹杂拉丁字母、表情或其它文字。")
    runtime = snapshot.get("runtime")
    required = {"engine", "device_id", "voice", "speed", "seed", "sample_rate"}
    if not isinstance(runtime, dict) or set(runtime) != required or runtime["engine"] != "kokoro" or runtime["device_id"] != "cpu" or runtime["voice"] != "zf_xiaobei" or type(runtime["sample_rate"]) is not int or runtime["sample_rate"] != 24000 or type(runtime["seed"]) is not int or not 0 <= runtime["seed"] < 2**32 or type(runtime["speed"]) not in (int, float) or not math.isfinite(runtime["speed"]) or not 0.5 <= runtime["speed"] <= 2:
        raise TTSError("INVALID_CONFIG", "配音参数须为 Kokoro、CPU、小北音色、24 kHz，速度 0.5—2 倍并显式固定种子。")
    model = Path(snapshot.get("model_path", ""))
    if not model.is_absolute() or not model.is_dir() or any(path.is_symlink() for path in [model, *model.parents]) or ".." in model.parts:
        raise TTSError("MODEL_NOT_READY", "请选择已完整准备的本地 Kokoro 模型目录。")
    expected_paths = set(FILES) | {"manifest.json"}
    if any(path.is_symlink() for path in model.rglob("*")) or {path.relative_to(model).as_posix() for path in model.rglob("*") if path.is_file()} != expected_paths:
        raise TTSError("MODEL_IDENTITY_CHANGED", "模型目录文件集合不符合固定官方清单。")
    try:
        manifest = json.loads((model / "manifest.json").read_text())
        if manifest.get("repository") != REPOSITORY or manifest.get("revision") != REVISION or manifest.get("load_policy") != "fixed_official_files_torch_weights_only_cpu":
            raise ValueError("固定来源身份不符")
        files = [{"path": name, "size": expected["size"], "sha256": verify(model / name, expected)} for name, expected in FILES.items()]
        if manifest.get("files") != files or digest(files) != snapshot.get("model_manifest_digest"):
            raise ValueError("模型清单摘要不符")
    except (OSError, ValueError) as exc:
        raise TTSError("MODEL_IDENTITY_CHANGED", "模型、音色或配置摘要不符合固定来源。") from exc
    if not output.is_absolute() or output.exists() or output == model or output.is_relative_to(model) or any(path.is_symlink() for path in [output, *output.parents]):
        raise TTSError("OUTPUT_NOT_ALLOWED", "输出须为模型目录之外的新目录，不能覆盖已有文件。")
    versions = {}
    if sys.version_info[:2] != (3, 10):
        raise TTSError("ENVIRONMENT_CHANGED", "当前配音组合固定使用 Python 3.10 隔离环境。")
    for name, expected in VERSIONS.items():
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise TTSError("ENVIRONMENT_NOT_READY", "尚未安装固定配音依赖：" + name) from exc
        if versions[name] != expected:
            raise TTSError("ENVIRONMENT_CHANGED", "配音依赖版本与已核验组合不一致：" + name)
    with contextlib.redirect_stdout(sys.stderr):
        import kokoro  # 检查完整入口的实际依赖可导入，不在检查阶段加载权重。
        from misaki import zh
        phonemes, _ = zh.ZHG2P(version=None, en_callable=None)(text)
    if not phonemes or len(phonemes) > 510:
        raise TTSError("TTS_PHONEMES_TOO_LONG", "文本的实际音素数为空或超过 510，请缩短文本；没有截断后继续生成。")
    vocabulary = json.loads((model / "config.json").read_text())["vocab"]
    if any(character not in vocabulary for character in phonemes):
        raise TTSError("TTS_PHONEMES_UNSUPPORTED", "文本包含当前固定模型不能编码的音素，未跳过后继续生成。")
    recipe_digest = digest({"text": text, "phonemes": phonemes, "misaki": VERSIONS["misaki"]})
    if snapshot.get("phonemization_digest", recipe_digest) != recipe_digest:
        raise TTSError("TTS_RECIPE_CHANGED", "实际音素配方与提交前检查不一致。")
    executor_files = [{"path": name, "sha256": file_hash(Path(__file__).parent / name)} for name in ("tts_cli.py", "tts_prepare.py")]
    if snapshot.get("executor_manifest_digest", digest(executor_files)) != digest(executor_files):
        raise TTSError("EXECUTOR_CHANGED", "配音执行器与提交前检查不一致。")
    environment = environment_snapshot()
    if snapshot.get("environment_manifest_digest", digest(environment)) != digest(environment):
        raise TTSError("ENVIRONMENT_CHANGED", "配音环境的实际依赖与提交前检查不一致。")
    return model, {**runtime, "model_repository": REPOSITORY, "model_revision": REVISION, "model_manifest_digest": digest(files), "versions": versions, **environment, "environment_manifest_digest": digest(environment), "executor_files": executor_files, "executor_manifest_digest": digest(executor_files), "language": "zh", "device_actual": "cpu", "character_count": len(text), "quality_status": "not_evaluated", "phoneme_count": len(phonemes), "phonemization_digest": recipe_digest}


def synthesize(snapshot, output):
    model_path, effective = validate(snapshot, output)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1", TOKENIZERS_PARALLELISM="false", TORCH_FORCE_WEIGHTS_ONLY_LOAD="1", CUDA_VISIBLE_DEVICES="")
    os.environ.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
    started = time.monotonic()
    emit("phase", phase="loading", message="正在 CPU 上受限加载固定模型与中文音色。")
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import soundfile as sf
        import torch
        from kokoro import KModel, KPipeline
        from unittest.mock import patch

        torch.set_num_threads(4)
        torch.manual_seed(effective["seed"])
        np.random.seed(effective["seed"])
        original_load = torch.load
        original_state_load = torch.nn.Module.load_state_dict
        allowed = {(model_path / name).resolve() for name in FILES if name.endswith((".pt", ".pth"))}
        loads = []
        state_loads = []

        def restricted_load(path, *args, **kwargs):
            if not isinstance(path, (str, Path)) or Path(path).resolve() not in allowed or args or kwargs.get("weights_only") is not True or kwargs.get("map_location", "cpu") != "cpu":
                raise TTSError("MODEL_LOAD_TRUST_REQUIRED", "拒绝超出固定白名单或非受限的权重加载。")
            kwargs["map_location"] = "cpu"
            loads.append({"file": Path(path).relative_to(model_path).as_posix(), "weights_only": True, "map_location": "cpu"})
            return original_load(path, **kwargs)

        def strict_state_load(module, state, *args, **kwargs):
            if args:
                raise TTSError("MODEL_STATE_MISMATCH", "不支持的位置权重加载参数。")
            kwargs["strict"] = True
            prepared, record = strict_state(module, state, torch)
            result = original_state_load(module, prepared, **kwargs)
            state_loads.append(record)
            return result

        with patch.object(torch, "load", restricted_load):
            with patch.object(torch.nn.Module, "load_state_dict", strict_state_load):
                model = KModel(repo_id=REPOSITORY, config=str(model_path / "config.json"), model=str(model_path / "kokoro-v1_0.pth")).to("cpu").eval()
            if any(parameter.device.type != "cpu" for parameter in model.parameters()):
                raise TTSError("DEVICE_MISMATCH", "配音模型未全部分配到 CPU。")
            pipeline = KPipeline(lang_code="z", repo_id=REPOSITORY, model=model, device="cpu")
            phonemes, _ = pipeline.g2p(snapshot["input"]["prompt"])
            if not phonemes or len(phonemes) > 510:
                raise TTSError("TTS_PHONEMES_TOO_LONG", "文本的实际音素数为空或超过 510，请缩短文本；没有截断后继续生成。")
            if digest({"text": snapshot["input"]["prompt"], "phonemes": phonemes, "misaki": VERSIONS["misaki"]}) != effective["phonemization_digest"]:
                raise TTSError("TTS_RECIPE_CHANGED", "模型加载后的音素配方与检查不一致。")
            audio, segments = [], []
            for index, (graphemes, phonemes, samples) in enumerate(pipeline(snapshot["input"]["prompt"], voice=str(model_path / "voices/zf_xiaobei.pt"), speed=effective["speed"], split_pattern=None), 1):
                if samples is None:
                    raise TTSError("AUDIO_EMPTY", "模型没有产生音频。")
                values = samples.detach().cpu().numpy()
                if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
                    raise TTSError("AUDIO_INVALID", "音频数据包含空段或非有限数。")
                audio.append(values)
                segments.append({"index": index, "text": graphemes, "phonemes": phonemes, "samples": len(values)})
                if sum(len(item) for item in audio) > 24000 * 180:
                    raise TTSError("AUDIO_TOO_LONG", "本次音频超过首期三分钟限制。")
        if not audio:
            raise TTSError("AUDIO_EMPTY", "文本未生成任何有效音频。")
        combined = np.concatenate(audio)
        peak = float(np.abs(combined).max())
        if peak <= 0 or peak > 1:
            raise TTSError("AUDIO_INVALID", "生成音频无有效信号或超出 PCM 取值范围。")
        # 写文件前复核全部模型输入，输出目录在此之前始终不存在。
        validate(snapshot, output)
        output.mkdir(parents=True, exist_ok=False)
        sf.write(output / "speech.wav", combined, 24000, format="WAV", subtype="PCM_16")
        with wave.open(str(output / "speech.wav"), "rb") as independent:
            if independent.getframerate() != 24000 or independent.getnchannels() != 1 or independent.getsampwidth() != 2 or independent.getnframes() != len(combined):
                raise TTSError("AUDIO_VERIFICATION_FAILED", "独立 WAV 解码的采样率、声道或长度不符。")
            if len(independent.readframes(independent.getnframes())) != len(combined) * 2:
                raise TTSError("AUDIO_VERIFICATION_FAILED", "独立 WAV 解码数据不完整。")
        effective.update(duration_seconds=len(combined) / 24000, sample_count=len(combined), peak=peak, elapsed_seconds=time.monotonic() - started, channels=1, subtype="PCM_16", restricted_loads=loads, strict_state_loads=state_loads, actual_parameter_devices=sorted({parameter.device.type for parameter in model.parameters()}))
        report = {"schema_version": "kokoro-zh-v1", "input": snapshot["input"], "requested_config": snapshot["runtime"], "effective_config": effective, "segments": segments, "independent_read": {"reader": "Python wave", "status": "passed"}, "quality_scope": "证明本固定组合真实生成与文件可读；未完成人工听评或语音质量准入。"}
        (output / "tts-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    artifacts = [{"path": name, "sha256": file_hash(output / name), "media_type": mime} for name, mime in (("speech.wav", "audio/wav"), ("tts-report.json", "application/json"))]
    emit("completed", artifacts=artifacts, effective_config=effective)
    return report


def main():
    parser = argparse.ArgumentParser(description="本机 CPU 固定中文配音")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    try:
        snapshot = json.loads(args.snapshot.read_text())
        with offline_mode():
            if args.preflight:
                _, effective = validate(snapshot, args.output_dir.absolute())
                print(json.dumps({"can_submit": True, "blocking": [], "effective_config": effective}, ensure_ascii=False))
            else:
                synthesize(snapshot, args.output_dir.absolute())
        return 0
    except (TTSError, ValueError, OSError) as error:
        code = error.code if isinstance(error, TTSError) else "TTS_FAILED"
        if args.preflight:
            print(json.dumps({"can_submit": False, "blocking": [{"code": code, "message": str(error)}]}, ensure_ascii=False))
        else:
            emit("error", code=code, message=str(error))
        return 130 if code == "CANCELLED" else 1
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        if args.preflight:
            print(json.dumps({"can_submit": False, "blocking": [{"code": "TTS_FAILED", "message": "配音环境或模型执行失败，请查看本次日志。"}]}, ensure_ascii=False))
        else:
            emit("error", code="TTS_FAILED", message="配音环境或模型执行失败，请查看本次日志。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
