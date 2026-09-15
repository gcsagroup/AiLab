"""M4 图片最小真实执行器：Tiny-SD／MPS 生成与 UNet LoRA 微调。"""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import signal
import subprocess
import time
from pathlib import Path

from prepare_tiny_sd import REPO, REVISION, sha256

TARGET_MODULES = ["to_q", "to_k", "to_v", "to_out.0"]


def install_cancellation():
    """让退出钩子主动回收信号量，并避免桥接器的重复终止打断清理。"""
    def cancel(_signal, _frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def config_snapshot(config):
    """明确表示上游调度器的无穷边界默认值，保持标准 JSON。"""
    return {key: ({"non_finite_float": str(value)} if isinstance(value, float) and not math.isfinite(value) else value)
            for key, value in config.items() if not key.startswith("_")}


def validate_numbers(size, steps, cfg=7.5, lr=None, rank=4):
    if isinstance(size, bool) or size not in (256, 384, 512):
        raise ValueError("本试验仅允许 256、384、512 像素")
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 50:
        raise ValueError("本试验步数必须是 1—50 的整数")
    if not math.isfinite(cfg) or not 1 <= cfg <= 15:
        raise ValueError("CFG 必须是 1—15 的有限数")
    if lr is not None and (not math.isfinite(lr) or not 0 < lr <= 0.001):
        raise ValueError("学习率必须在 (0, 0.001] 内")
    if isinstance(rank, bool) or rank not in (2, 4, 8):
        raise ValueError("本试验仅允许 rank 2、4、8")


def verify_model(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if (manifest.get("repo"), manifest.get("revision"), manifest.get("runtime_format")) != (REPO, REVISION, "safetensors"):
        raise ValueError("模型身份或格式不匹配")
    if not manifest.get("converted_files"):
        raise ValueError("模型文件清单为空")
    for item in manifest["converted_files"]:
        file = (root / "safetensors" / item["path"]).resolve()
        if not file.is_relative_to(root / "safetensors") or not file.is_file():
            raise ValueError("模型文件缺失或越界")
        if file.suffix == ".bin" or sha256(file) != item["sha256"]:
            raise ValueError(f"模型格式或摘要不符：{item['path']}")
    return root / "safetensors", sha256(root / "manifest.json")


def environment():
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "hardware": {"chip": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
                         "physical_memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))},
            "executor_sha256": sha256(__file__),
            "packages": {name: importlib.metadata.version(name) for name in ["torch", "diffusers", "transformers", "peft", "accelerate", "safetensors", "Pillow", "numpy"]},
            "device": "mps", "dtype": "float32", "mps_cpu_fallback": False, "cache": "关闭跨请求媒体缓存", "pid": os.getpid()}


def pipeline(model_root):
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0":
        raise ValueError("本试验禁止静默 MPS→CPU 算子回退")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch
    from diffusers import StableDiffusionPipeline
    if not torch.backends.mps.is_available():
        raise RuntimeError("所选 MPS 设备不可用；不回退 CPU")
    path, identity = verify_model(model_root)
    started = time.monotonic()
    # 显式指定标准 pipeline 类，只加载受核验的本地 safetensors。
    pipe = StableDiffusionPipeline.from_pretrained(str(path), torch_dtype=torch.float32,
                                                  local_files_only=True, use_safetensors=True)
    pipe.to("mps")
    torch.mps.synchronize()
    return pipe, identity, time.monotonic() - started


def checked_output(path):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError("输出目录已存在；新结果须使用独立目录")
    path.mkdir(parents=True)
    return path


def generate(args):
    validate_numbers(args.size, args.steps, args.cfg)
    if not args.prompt.strip():
        raise ValueError("提示词不能为空")
    import numpy as np
    import torch
    output = checked_output(args.output)
    pipe, model_id, load_seconds = pipeline(args.model_root)
    adapter_id = None
    if args.adapter:
        adapter = Path(args.adapter).resolve()
        meta = json.loads((adapter / "training.json").read_text())
        if meta["model_manifest_sha256"] != model_id or meta["revision"] != REVISION:
            raise ValueError("LoRA 的基座身份不匹配")
        weight = adapter / "pytorch_lora_weights.safetensors"
        adapter_id = sha256(weight)
        if adapter_id != meta["adapter_sha256"]:
            raise ValueError("LoRA 权重摘要不符")
        pipe.load_lora_weights(str(adapter), weight_name=weight.name, local_files_only=True)
    for prompt in (args.prompt, args.negative_prompt):
        token_ids = pipe.tokenizer(prompt, truncation=False)["input_ids"]
        if len(token_ids) > pipe.tokenizer.model_max_length:
            raise ValueError("提示词超过 CLIP 最大长度；拒绝静默截断")
    started = time.monotonic()
    result = pipe(args.prompt, negative_prompt=args.negative_prompt, height=args.size, width=args.size,
                  num_inference_steps=args.steps, guidance_scale=args.cfg,
                  generator=torch.Generator(device="cpu").manual_seed(args.seed), output_type="np")
    torch.mps.synchronize()
    pixels = result.images[0]
    if not np.isfinite(pixels).all() or float(pixels.std()) < 0.01:
        raise RuntimeError("生成图像非有限数或近乎单色")
    from PIL import Image
    Image.fromarray((pixels * 255).round().astype("uint8")).save(output / "image.png")
    np.save(output / "pixels.npy", pixels)
    report = {"operation": "text_to_image", "repo": REPO, "revision": REVISION, "model_manifest_sha256": model_id,
              "adapter_sha256": adapter_id, "prompt": args.prompt, "negative_prompt": args.negative_prompt,
              "seed": args.seed, "width": args.size, "height": args.size, "steps": args.steps, "cfg": args.cfg,
              "scheduler": type(pipe.scheduler).__name__, "scheduler_config": config_snapshot(pipe.scheduler.config),
              "environment": environment(), "load_seconds": load_seconds, "generate_seconds": time.monotonic() - started,
              "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "peak_mps_allocated_bytes": None, "mps_peak_note": "该 MPS API 未提供峰值接口，不将结束时采样冒充峰值",
              "mps_driver_allocated_bytes_at_end": torch.mps.driver_allocated_memory(),
              "image_sha256": sha256(output / "image.png"), "pixels_std": float(pixels.std()),
              "source": "真实扩散模型生成；不是外部服务、噪声夹具或平移图片", "quality_status": "待人工检查；不可由哈希差异推导质量改善"}
    write_json(output / "generation.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


def tensor_digest(named_parameters):
    digest = hashlib.sha256()
    for name, value in named_parameters:
        digest.update(name.encode())
        digest.update(value.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def train(args):
    validate_numbers(args.size, args.steps, lr=args.learning_rate, rank=args.rank)
    import numpy as np
    import torch
    from PIL import Image
    from diffusers import DDPMScheduler, StableDiffusionPipeline
    from diffusers.utils import convert_state_dict_to_diffusers
    from peft import LoraConfig
    from peft.utils import get_peft_model_state_dict
    output = checked_output(args.output)
    dataset_path = Path(args.data).resolve()
    dataset_bytes = dataset_path.read_bytes()
    dataset = json.loads(dataset_bytes)
    if not dataset.get("samples") or len(dataset["samples"]) > 8:
        raise ValueError("本试验需要 1—8 张来源明确的图片")
    pipe, model_id, load_seconds = pipeline(args.model_root)
    unet, vae, encoder = pipe.unet, pipe.vae, pipe.text_encoder
    for model in (unet, vae, encoder):
        model.requires_grad_(False)
    torch.manual_seed(args.seed)
    unet.add_adapter(LoraConfig(r=args.rank, lora_alpha=args.rank, lora_dropout=0.0, init_lora_weights="gaussian", target_modules=TARGET_MODULES))
    unet.train()
    vae.eval()
    encoder.eval()
    trainable = {name: value for name, value in unet.named_parameters() if value.requires_grad}
    if not trainable or any("lora_" not in name for name in trainable):
        raise RuntimeError("可训练参数集合超出 LoRA")
    initial = {name: value.detach().cpu().clone() for name, value in trainable.items()}
    frozen_before = tensor_digest((name, value) for name, value in unet.named_parameters() if not value.requires_grad)
    optimizer = torch.optim.AdamW(list(trainable.values()), lr=args.learning_rate, betas=(0.9, 0.999), weight_decay=0.01, eps=1e-8)
    scheduler = DDPMScheduler.from_config(pipe.scheduler.config)
    if scheduler.config.prediction_type != "epsilon":
        raise ValueError("本组合仅验证 epsilon 去噪监督")
    samples = []
    with torch.no_grad():
        for record in dataset["samples"]:
            file = (dataset_path.parent / record["path"]).resolve()
            if not file.is_relative_to(dataset_path.parent) or sha256(file) != record["sha256"]:
                raise ValueError("训练图片越界或摘要不匹配")
            with Image.open(file) as image:
                if image.mode != "RGB" or image.size != (args.size, args.size):
                    raise ValueError("本试验要求已冻结尺寸的 RGB 原图，不静默裁剪或缩放")
                pixels = torch.from_numpy(np.asarray(image).copy()).float().permute(2, 0, 1).unsqueeze(0).to("mps") / 127.5 - 1
            ids = pipe.tokenizer(record["caption"], truncation=False)["input_ids"]
            if len(ids) > pipe.tokenizer.model_max_length:
                raise ValueError("训练 caption 超长")
            tokens = pipe.tokenizer(record["caption"], padding="max_length", max_length=pipe.tokenizer.model_max_length, return_tensors="pt").input_ids.to("mps")
            # 缓存仅在本次训练内使用；保留图像、caption 和配方摘要，不跨任务复用。
            encoded = vae.encode(pixels).latent_dist
            samples.append((encoded.mean.detach(), encoded.std.detach(), encoder(tokens)[0].detach()))
    losses = []
    started = time.monotonic()
    generator = torch.Generator(device="cpu").manual_seed(args.seed)
    for step in range(args.steps):
        mean, std, text = samples[step % len(samples)]
        latent_sample = torch.randn(mean.shape, generator=generator).to("mps")
        latent = (mean + std * latent_sample) * vae.config.scaling_factor
        noise = torch.randn(latent.shape, generator=generator).to("mps")
        timestep = torch.randint(0, scheduler.config.num_train_timesteps, (1,), generator=generator).to("mps")
        noised = scheduler.add_noise(latent, noise, timestep)
        predicted = unet(noised, timestep, encoder_hidden_states=text).sample
        loss = torch.nn.functional.mse_loss(predicted.float(), noise.float(), reduction="mean")
        if not torch.isfinite(loss):
            raise RuntimeError("训练 loss 出现非有限值")
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(list(trainable.values()), 1.0)
        if not torch.isfinite(grad_norm):
            raise RuntimeError("训练梯度出现非有限值")
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        torch.mps.synchronize()
        item = {"step": step + 1, "sample_index": step % len(samples), "timestep": int(timestep.item()), "loss": float(loss.item()), "grad_norm": float(grad_norm.item())}
        losses.append(item)
        print(json.dumps(item), flush=True)
    train_seconds = time.monotonic() - started
    deltas = {name: float((value.detach().cpu() - initial[name]).abs().max()) for name, value in trainable.items()}
    if not all(math.isfinite(v) for v in deltas.values()) or not any(v > 0 for v in deltas.values()):
        raise RuntimeError("LoRA 权重未产生有限变化")
    frozen_after = tensor_digest((name, value) for name, value in unet.named_parameters() if not value.requires_grad)
    if frozen_before != frozen_after:
        raise RuntimeError("冻结的基座参数发生变化")
    state = convert_state_dict_to_diffusers(get_peft_model_state_dict(unet))
    StableDiffusionPipeline.save_lora_weights(str(output), unet_lora_layers=state, safe_serialization=True)
    report = {"operation": "diffusion_epsilon_lora", "repo": REPO, "revision": REVISION,
              "model_manifest_sha256": model_id, "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(), "dataset": dataset,
              "size": args.size, "steps": args.steps, "seed": args.seed, "learning_rate": args.learning_rate,
              "batch_size": 1, "gradient_accumulation": 1, "rank": args.rank, "alpha": args.rank, "dropout": 0.0, "target_modules": TARGET_MODULES,
              "noise_scheduler": {"name": type(scheduler).__name__, "config": config_snapshot(scheduler.config)},
              "optimizer": {"name": "AdamW", "betas": [0.9, 0.999], "weight_decay": 0.01, "eps": 1e-8}, "max_grad_norm": 1.0,
              "preprocess": "RGB 原图，无裁剪、缩放、翻转；归一化到 [-1,1]；VAE 对角高斯采样；冻结 CLIP",
              "trainable_parameter_count": sum(v.numel() for v in trainable.values()), "trainable_tensor_count": len(trainable),
              "parameter_max_abs_deltas": deltas, "frozen_parameter_sha256_before": frozen_before, "frozen_parameter_sha256_after": frozen_after,
              "adapter_sha256": sha256(output / "pytorch_lora_weights.safetensors"), "losses": losses,
              "environment": environment(), "load_seconds": load_seconds, "train_seconds": train_seconds,
              "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "peak_mps_allocated_bytes": None, "mps_driver_allocated_bytes_at_end": torch.mps.driver_allocated_memory(),
              "quality_status": "只证明真实训练与权重更新；待独立重载和固定样例对照，不宣称质量改善", "resume": "未实现训练恢复"}
    write_json(output / "training.json", report)
    print(json.dumps({"完成": str(output), "train_seconds": train_seconds, "adapter_sha256": report["adapter_sha256"]}, ensure_ascii=False), flush=True)


def main():
    install_cancellation()
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "train"):
        sub = commands.add_parser(command)
        sub.add_argument("--model-root", required=True)
        sub.add_argument("--output", required=True)
        sub.add_argument("--size", type=int, default=512)
        sub.add_argument("--steps", type=int, default=20 if command == "generate" else 12)
        sub.add_argument("--seed", type=int, default=42)
        if command == "generate":
            sub.add_argument("--prompt", required=True)
            sub.add_argument("--negative-prompt", default="blurry, distorted, text, watermark")
            sub.add_argument("--cfg", type=float, default=7.5)
            sub.add_argument("--adapter")
        else:
            sub.add_argument("--data", required=True)
            sub.add_argument("--learning-rate", type=float, default=0.0001)
            sub.add_argument("--rank", type=int, default=4)
    args = parser.parse_args()
    (generate if args.command == "generate" else train)(args)


if __name__ == "__main__":
    main()
