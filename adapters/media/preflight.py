"""固定图片／视频组合的提交前检查，不加载模型权重或创建输出。"""

import argparse
import contextlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/control"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ailab_control.assets import regular_path
from ailab_control.media_assets import image_dataset_report, media_model_manifest, png_info
from ailab_control.storage import Fault
from workers import mlx_worker as common

DEFAULT_NEGATIVE = "blurry, distorted, text, watermark"
VERSIONS = {"torch": "2.14.0", "diffusers": "0.35.2", "transformers": "4.57.6", "peft": "0.18.1",
            "accelerate": "1.12.0", "safetensors": "0.7.0", "Pillow": "12.1.1", "numpy": "2.4.2"}
SOURCE_FILES = ["workers/media_worker.py", "adapters/media/preflight.py", "adapters/media/image_cli.py",
                "adapters/media/video_cli.py", "adapters/media/prepare_tiny_sd.py", "adapters/media/prepare_svd.py",
                "adapters/media/requirements.lock.txt", "workers/mlx_worker.py", "services/control/ailab_control/assets.py",
                "services/control/ailab_control/media_assets.py", "services/control/ailab_control/storage.py"]


def runtime_config(snapshot):
    kind, operation = snapshot.get("kind"), snapshot.get("operation")
    if (kind, operation) not in {("image", "generate"), ("image", "train"), ("video", "generate")}:
        raise common.WorkerError("UNSUPPORTED_OPERATION", "当前媒体桥只开放图片生成、图片 LoRA 训练和图片生成短视频")
    runtime = snapshot.get("runtime", {})
    if not isinstance(runtime, dict):
        raise common.WorkerError("INVALID_CONFIG", "runtime 必须为对象")
    fixed = {"engine": "diffusers", "device_id": "apple-gpu"}
    if kind == "video":
        fixed.update(steps=25, frames=14, fps=7)
    elif operation == "generate":
        fixed.update(size=512, steps=20, cfg=7.5)
    else:
        fixed.update(size=512, steps=12, learning_rate=0.0001, lora_rank=4)
    unknown = set(runtime) - set(fixed) - {"seed"}
    if unknown:
        raise common.WorkerError("UNSUPPORTED_PARAMETER", "尚未支持的媒体参数：" + "、".join(sorted(unknown)))
    for name, value in fixed.items():
        actual = runtime.get(name, value)
        if isinstance(value, (int, float)):
            common.number({name: actual}, name, value, value, value, integer=isinstance(value, int))
        elif actual != value:
            raise common.WorkerError("UNSUPPORTED_PARAMETER", f"当前媒体组合固定 {name}={value}")
    return {**fixed, "seed": common.number(runtime, "seed", 0, 0, 2**32 - 1, True)}


def verify_bound(path, snapshot, prefix):
    path = regular_path(path)
    expected = snapshot.get(prefix + "_manifest")
    expected_digest = snapshot.get(prefix + "_manifest_digest")
    if not isinstance(expected, list) or not 1 <= len(expected) <= 10000 or common.canonical_digest(expected) != expected_digest:
        raise common.WorkerError(prefix.upper() + "_IDENTITY_REQUIRED", "媒体快照缺少有效的完整文件清单与摘要")
    directory = path.parent if path.is_file() else path
    files = [path] if path.is_file() else sorted(path.rglob("*"))
    actual = []
    for item in files:
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise common.WorkerError(prefix.upper() + "_IDENTITY_CHANGED", "媒体输入包含符号链接或非常规文件")
        if item.is_file():
            actual.append({"path": item.relative_to(directory).as_posix(), "size": item.stat().st_size, "sha256": common.sha256(item)})
    if actual != expected:
        raise common.WorkerError(prefix.upper() + "_IDENTITY_CHANGED", "媒体输入文件集合、大小或摘要与提交快照不一致")
    return path


def check_output(output, inputs, allow_populated=False):
    if not output.is_absolute() or output.is_symlink() or output.resolve() != output:
        raise common.WorkerError("OUTPUT_SYMLINK", "输出路径必须为不经符号链接跳转的绝对路径")
    if output.exists() and (not output.is_dir() or (not allow_populated and any(output.iterdir()))):
        raise common.WorkerError("OUTPUT_EXISTS", "输出目录必须为空，不能覆盖已有产物")
    for source in inputs:
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise common.WorkerError("OUTPUT_OVERLAP", "输出目录不能与模型、数据、图片或适配器重叠")


def tokenizer_for(model):
    from transformers import CLIPTokenizer
    return CLIPTokenizer.from_pretrained(str(model / "safetensors/tokenizer"), local_files_only=True)


def check_prompt(tokenizer, text, label):
    if not isinstance(text, str) or len(text) > 2000:
        raise common.WorkerError("INVALID_PROMPT", label + "必须为不超过 2000 字符的文本")
    count = len(tokenizer(text, truncation=False)["input_ids"])
    if count > tokenizer.model_max_length:
        raise common.WorkerError("CONTEXT_TOO_LONG", label + "超过当前 CLIP 词元上限，不进行静默截断")
    return count


def validate_adapter(adapter, model, prepared_digest):
    metadata = json.loads((adapter / "training.json").read_text())
    if metadata.get("model_manifest_sha256") != prepared_digest or metadata.get("revision") != "cad0bd7495fa6c4bcca01b19a723dc91627fe84f" or metadata.get("rank") != 4 or metadata.get("alpha") != 4:
        raise common.WorkerError("ADAPTER_BASE_MISMATCH", "图片 LoRA 的基座、rank 或 alpha 与当前已验证组合不符")
    if metadata.get("operation") != "diffusion_epsilon_lora" or metadata.get("dropout") != 0 or metadata.get("target_modules") != ["to_q", "to_k", "to_v", "to_out.0"]:
        raise common.WorkerError("ADAPTER_MODULE_MISMATCH", "图片 LoRA 的训练方法、模块或 dropout 不符合当前组合")
    weight = adapter / "pytorch_lora_weights.safetensors"
    if metadata.get("adapter_sha256") != common.sha256(weight):
        raise common.WorkerError("ADAPTER_IDENTITY_CHANGED", "图片 LoRA 权重与训练报告摘要不符")
    # 只用官方已核验 UNet 配置在 meta 设备建立形状，不分配基座权重或占用 GPU。
    from accelerate import init_empty_weights
    from diffusers import UNet2DConditionModel
    from safetensors import safe_open
    with init_empty_weights():
        unet = UNet2DConditionModel.from_config(json.loads((model / "safetensors/unet/config.json").read_text()))
    expected = {}
    for name, module in unet.named_modules():
        if name.endswith(("to_q", "to_k", "to_v", "to_out.0")) and hasattr(module, "in_features"):
            expected[f"unet.{name}.lora.down.weight"] = [4, module.in_features]
            expected[f"unet.{name}.lora.up.weight"] = [module.out_features, 4]
    with safe_open(str(weight), framework="numpy") as values:
        if not expected or set(values.keys()) != set(expected) or any(values.get_slice(name).get_shape() != shape for name, shape in expected.items()):
            raise common.WorkerError("ADAPTER_MODULE_MISMATCH", "图片 LoRA 参数名称、数量或形状与固定 UNet 不符")
        import numpy as np
        if any(not np.isfinite(values.get_tensor(name)).all() for name in values.keys()):
            raise common.WorkerError("ADAPTER_INVALID", "图片 LoRA 含非有限权重")
    return metadata["adapter_sha256"]


def environment():
    if sys.version_info[:2] != (3, 13):
        raise common.WorkerError("ENVIRONMENT_CHANGED", "当前图片与视频组合需要独立 Python 3.13 环境")
    actual = {name: importlib.metadata.version(name) for name in VERSIONS}
    if actual != VERSIONS:
        raise common.WorkerError("ENVIRONMENT_CHANGED", "图片／视频依赖版本与已验证组合不符")
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0":
        raise common.WorkerError("UNSUPPORTED_DEVICE", "当前组合不允许静默 MPS 算子回退")
    import torch
    if not torch.backends.mps.is_available():
        raise common.WorkerError("UNSUPPORTED_DEVICE", "当前图片／视频组合需要可用的 Apple MPS")
    metadata_paths = {"path": [str(Path(sys._MEIPASS))]} if getattr(sys, "frozen", False) else {}
    packages = sorted({(item.metadata["Name"], item.version) for item in importlib.metadata.distributions(**metadata_paths)})
    result = {"python": platform.python_version(), "platform": platform.platform(), "python_entrypoint": sys.executable,
              "venv": sys.prefix, "packages": packages,
              "required_versions": actual, "device": "mps", "mps_cpu_fallback": False}
    if getattr(sys, "frozen", False):
        internal = Path(sys._MEIPASS)
        result["runtime_manifest_sha256"] = common.sha256(internal.parent / "runtime-manifest.json")
        result["media_tools_manifest_sha256"] = common.sha256(internal.parent.parent / "media-tools/runtime-manifest.json")
    return result


def check(snapshot, output, allow_populated_output=False):
    if not isinstance(snapshot, dict):
        raise common.WorkerError("INVALID_CONFIG", "媒体快照必须为对象")
    effective = runtime_config(snapshot)
    if snapshot.get("checkpoint_ref"):
        raise common.WorkerError("RESUME_UNSUPPORTED", "当前媒体执行器未实现检查点恢复")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1", TOKENIZERS_PARALLELISM="false")
    model = verify_bound(snapshot.get("model_path", ""), snapshot, "model")
    card = media_model_manifest(model)
    if not card or card["modality"] != snapshot["kind"] or card["manifest_digest"] != snapshot["model_manifest_digest"]:
        raise common.WorkerError("MODEL_UNVERIFIED", "模型不是当前类别已验证的固定媒体组合")
    effective.update(model_manifest_digest=card["manifest_digest"], model_repository=card["model_config"]["repository"],
                     model_revision=card["model_config"]["revision"], prepared_model_manifest_sha256=common.sha256(model / "manifest.json"),
                     dtype="float16" if snapshot["kind"] == "video" else "float32", cache="关闭跨请求媒体缓存",
                     quality_status="not_evaluated", supports_checkpoint_resume=False)
    inputs = [model]
    provided = snapshot.get("input", {})
    if not isinstance(provided, dict):
        raise common.WorkerError("INVALID_CONFIG", "input 必须为对象")
    report = {"kind": snapshot["kind"], "operation": snapshot["operation"], "quality": "not_run"}
    identity = {"model_manifest_digest": snapshot["model_manifest_digest"]}
    with contextlib.redirect_stdout(sys.stderr):
        if snapshot["kind"] == "image":
            tokenizer = tokenizer_for(model)
            if snapshot["operation"] == "generate":
                if set(provided) - {"prompt", "negative_prompt"} or not isinstance(provided.get("prompt"), str) or not provided["prompt"].strip():
                    raise common.WorkerError("INVALID_PROMPT", "图片生成需要非空提示词，只支持 prompt 与 negative_prompt")
                negative = provided.get("negative_prompt", DEFAULT_NEGATIVE)
                effective.update(prompt=provided["prompt"], negative_prompt=negative)
                report.update(prompt_tokens=check_prompt(tokenizer, provided["prompt"], "提示词"), negative_prompt_tokens=check_prompt(tokenizer, negative, "负向提示词"), context_limit=tokenizer.model_max_length)
            else:
                if provided not in ({}, {"prompt": ""}, {"prompt": "", "negative_prompt": ""}):
                    raise common.WorkerError("UNSUPPORTED_INPUT", "图片训练使用数据集 caption，不接收额外提示词")
                dataset_root = verify_bound(snapshot.get("dataset_root_path", ""), snapshot, "dataset")
                dataset = regular_path(snapshot.get("dataset_path", ""))
                if dataset != dataset_root / "dataset.json":
                    raise common.WorkerError("INVALID_DATASET", "图片数据入口必须是已绑定目录内的 dataset.json")
                data_report = image_dataset_report(dataset_root)
                if data_report["manifest_digest"] != snapshot["dataset_manifest_digest"]:
                    raise common.WorkerError("DATASET_IDENTITY_CHANGED", "图片数据清单必须完整且只含 dataset.json 明确引用的文件")
                rows = json.loads(dataset.read_text())["samples"]
                counts = [check_prompt(tokenizer, row["caption"], "图片 caption") for row in rows]
                from PIL import Image
                for row in rows:
                    with Image.open(dataset_root / row["path"]) as image:
                        image.load()
                        if image.mode != "RGB" or image.size != (512, 512):
                            raise common.WorkerError("INVALID_DATASET", "图片训练要求 512×512 RGB 原图")
                inputs.append(dataset_root)
                identity["dataset_manifest_digest"] = snapshot["dataset_manifest_digest"]
                effective.update(dataset_manifest_digest=snapshot["dataset_manifest_digest"], dataset_sha256=common.sha256(dataset),
                                 sample_count=len(rows), batch_size=1, gradient_accumulation=1, lora_alpha=4, lora_dropout=0.0,
                                 target_modules=["to_q", "to_k", "to_v", "to_out.0"], optimizer="AdamW", weight_decay=0.01)
                report.update(data_report, caption_tokens=counts)
        else:
            if set(provided) != {"material_id"} or not isinstance(provided["material_id"], str) or not provided["material_id"].startswith("material-") or len(provided["material_id"]) > 200:
                raise common.WorkerError("UNSUPPORTED_INPUT", "当前 SVD 需要来源图片 material_id，不接受文本控制")
            source = verify_bound(snapshot.get("input_image_path", ""), snapshot, "input_image")
            info = png_info(source)
            from PIL import Image
            with Image.open(source) as image:
                image.load()
                if image.mode not in {"RGB", "RGBA"} or list(image.size) != [info["width"], info["height"]]:
                    raise common.WorkerError("MEDIA_CORRUPT", "图片独立解码与结构检查不一致")
                mode = image.mode
            inputs.append(source)
            identity["input_image_manifest_digest"] = snapshot["input_image_manifest_digest"]
            identity["material_id"] = provided["material_id"]
            effective.update(input_image_sha256=info["sha256"], input_image_manifest_digest=snapshot["input_image_manifest_digest"],
                             material_id=provided["material_id"],
                             width=1024, height=576, motion_bucket_id=127, noise_aug_strength=0.02, min_guidance_scale=1.0,
                             max_guidance_scale=3.0, decode_chunk_size=2, offload="none",
                             preprocess="RGB；Lanczos 等比缩放；居中补边到 1024×576；补边 RGB(245,242,235)",
                             input_mode=mode, alpha_policy="RGBA 输入丢弃透明度通道并保留原 RGB 分量" if mode == "RGBA" else "无透明度通道")
            report.update(input_image=info)
        if snapshot.get("adapter_path"):
            if (snapshot["kind"], snapshot["operation"]) != ("image", "generate"):
                raise common.WorkerError("ADAPTER_OPERATION_UNSUPPORTED", "当前媒体 LoRA 只用于图片生成")
            adapter = verify_bound(snapshot["adapter_path"], snapshot, "adapter")
            effective["adapter_sha256"] = validate_adapter(adapter, model, effective["prepared_model_manifest_sha256"])
            effective["adapter_manifest_digest"] = snapshot["adapter_manifest_digest"]
            identity["adapter_manifest_digest"] = snapshot["adapter_manifest_digest"]
            inputs.append(adapter)
        check_output(output, inputs, allow_populated_output)
        env = environment()
    sources = [{"path": name, "sha256": common.sha256(ROOT / name)} for name in SOURCE_FILES]
    effective.update(environment_manifest_digest=common.canonical_digest(env), executor_manifest_digest=common.canonical_digest(sources))
    recipe = {"id": "diffusers-media-v1", "kind": snapshot["kind"], "operation": snapshot["operation"],
              "input_identity": identity, "effective_config": effective, "executor_files": sources}
    recipe_digest = common.canonical_digest(recipe)
    if snapshot.get("media_recipe_digest", recipe_digest) != recipe_digest:
        raise common.WorkerError("MEDIA_RECIPE_CHANGED", "媒体输入、实际参数、执行器或环境与提交前检查不一致")
    return {"can_submit": True, "blocking": [], "effective_config": effective, "media_recipe_digest": recipe_digest,
            "recipe": recipe, "check_report": report, "environment": env}


def main():
    from workers.format_worker import handles, main as format_main
    if "--snapshot" in sys.argv and handles(json.loads(Path(sys.argv[sys.argv.index("--snapshot") + 1]).read_text())):
        return format_main(preflight=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.snapshot.read_text()), args.output_dir.absolute())
    except (common.WorkerError, Fault) as error:
        result = {"can_submit": False, "blocking": [{"code": error.code, "message": str(error)}]}
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        result = {"can_submit": False, "blocking": [{"code": "MEDIA_PREFLIGHT_FAILED", "message": "请检查媒体模型、数据和独立执行环境"}]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["can_submit"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
