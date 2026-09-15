"""M4 官方 SVD 图生视频试验；读取真实图片，生成并独立解码 14 帧 MP4。"""

import argparse
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import subprocess
import time
from pathlib import Path

from prepare_tiny_sd import sha256
from prepare_svd import REPO, REVISION
from image_cli import checked_output, config_snapshot, install_cancellation, write_json


def validate_video_config(frames, fps, steps):
    if isinstance(frames, bool) or frames != 14 or isinstance(fps, bool) or fps != 7:
        raise ValueError("首个 SVD 试验固定 14 帧、7 FPS，不能声明未验证帧数组合")
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= 50:
        raise ValueError("SVD 步数必须是 1—50 的整数")


def verify_svd(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if (manifest["repo"], manifest["revision"], manifest["variant"]) != (REPO, REVISION, "fp16"):
        raise ValueError("SVD 基座版本或格式不匹配")
    if not manifest.get("files"):
        raise ValueError("SVD 文件清单为空")
    for item in manifest["files"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError("SVD 模型文件缺失、越界或摘要错误")
    return sha256(root / "manifest.json")


def main():
    install_cancellation()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--steps", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--frames", type=int, default=14)
    parser.add_argument("--fps", type=int, default=7)
    args = parser.parse_args()
    validate_video_config(args.frames, args.fps, args.steps)
    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0":
        raise ValueError("SVD 首验不允许静默 CPU 算子回退")
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            raise RuntimeError(f"缺少独立媒体验证工具：{name}")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    import numpy as np
    from PIL import Image, ImageOps
    import torch
    from diffusers import StableVideoDiffusionPipeline
    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS 不可用；不改为 CPU")
    source = Path(args.input).resolve()
    source_id = sha256(source)
    with Image.open(source) as opened:
        opened.load()
        original_size = list(opened.size)
        # 明确的适配配方：等比缩放后补白至官方训练尺寸，禁止隐藏裁剪。
        image = ImageOps.pad(opened.convert("RGB"), (1024, 576), method=Image.Resampling.LANCZOS, color=(245, 242, 235), centering=(0.5, 0.5))
    model_id = verify_svd(args.model_root)
    output = checked_output(args.output)
    image.save(output / "condition.png")
    plan = {"repo": REPO, "revision": REVISION, "model_manifest_sha256": model_id, "input_path": str(source), "input_sha256": source_id,
            "input_original_size": original_size, "preprocess": "RGB；Lanczos 等比缩放；居中补边到 1024×576；补边 RGB(245,242,235)",
            "condition_sha256": sha256(output / "condition.png"), "width": 1024, "height": 576, "frames": args.frames,
            "fps": args.fps, "sampling_steps": args.steps, "seed": args.seed, "motion_bucket_id": 127, "noise_aug_strength": 0.02,
            "min_guidance_scale": 1.0, "max_guidance_scale": 3.0, "decode_chunk_size": 2, "device": "mps", "dtype": "float16",
            "offload": "none", "cache": "关闭跨请求媒体缓存", "cpu_operator_fallback": False,
            "functional_acceptance": "真实 UNet 时序生成；14帧可独立解码；7FPS/2秒；多个不同帧；源图片摘要不变",
            "quality_acceptance": "人工检查商品主体和时序；本次不声明商业质量或动作可控", "training_status": "本组合未实现视频训练"}
    write_json(output / "frozen-plan.json", plan)
    started = time.monotonic()
    pipe = StableVideoDiffusionPipeline.from_pretrained(str(Path(args.model_root).resolve()), variant="fp16", torch_dtype=torch.float16,
                                                       local_files_only=True, use_safetensors=True).to("mps")
    torch.mps.synchronize()
    load_seconds = time.monotonic() - started
    started = time.monotonic()
    frames = pipe(image, height=576, width=1024, num_frames=args.frames, num_inference_steps=args.steps,
                  fps=args.fps, motion_bucket_id=127, noise_aug_strength=0.02, min_guidance_scale=1.0,
                  max_guidance_scale=3.0, decode_chunk_size=2, output_type="np",
                  generator=torch.Generator(device="cpu").manual_seed(args.seed)).frames[0]
    torch.mps.synchronize()
    generation_seconds = time.monotonic() - started
    if frames.shape != (14, 576, 1024, 3) or not np.isfinite(frames).all():
        raise RuntimeError("SVD 浮点视频含非有限值或帧数尺寸异常")
    np.save(output / "pixels.npy", frames)
    frame_dir = output / "frames"
    frame_dir.mkdir()
    ids = []
    temporal_differences = []
    previous = None
    for index, frame in enumerate(frames):
        pixels = (np.asarray(frame) * 255).round().astype("uint8")
        if pixels.shape != (576, 1024, 3) or not np.isfinite(pixels).all() or float(pixels.std()) < 1:
            raise RuntimeError("SVD 帧内容或尺寸异常")
        file = frame_dir / f"frame-{index:03d}.png"
        Image.fromarray(pixels).save(file)
        ids.append(sha256(file))
        if previous is not None:
            temporal_differences.append(float(np.abs(pixels.astype("float32") - previous).mean()))
        previous = pixels.astype("float32")
    if len(frames) != 14 or len(set(ids)) < 2:
        raise RuntimeError("SVD 未输出14个具备变化的真实帧")
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-n", "-framerate", str(args.fps), "-i", str(frame_dir / "frame-%03d.png"),
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output / "video.mp4")], check=True)
    probe = json.loads(subprocess.check_output([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(output / "video.mp4")]))
    stream = probe["streams"][0]
    if (int(stream["nb_read_frames"]), stream["r_frame_rate"], int(stream["width"]), int(stream["height"])) != (14, "7/1", 1024, 576):
        raise RuntimeError("独立视频解码结果与冻结配置不一致")
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(output / "video.mp4"), "-f", "framemd5", str(output / "decoded-frames.md5")], check=True)
    if sha256(source) != source_id:
        raise RuntimeError("源图片在执行中改变")
    report = {"functional_status": "通过", "quality_status": "待人工检查；帧间差异不证明合理运动", "plan": plan,
              "load_seconds": load_seconds, "generate_seconds": generation_seconds, "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              "peak_mps_allocated_bytes": None, "mps_driver_allocated_bytes_at_end": torch.mps.driver_allocated_memory(),
              "unet_actual_dtype": str(pipe.unet.dtype), "vae_actual_dtype": str(pipe.vae.dtype), "frame_sha256": ids,
              "scheduler": {"name": type(pipe.scheduler).__name__, "config": config_snapshot(pipe.scheduler.config)},
              "consecutive_frame_mean_absolute_differences": temporal_differences, "video_sha256": sha256(output / "video.mp4"), "ffprobe": probe,
              "environment": {"python": platform.python_version(), "platform": platform.platform(), "pid": os.getpid(),
                              "executor_sha256": sha256(__file__),
                              "hardware": {"chip": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
                                           "physical_memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True))},
                              "packages": {n: importlib.metadata.version(n) for n in ("torch", "diffusers", "transformers", "safetensors", "Pillow", "numpy")}},
              "m4_gate": "CLI 视频试用证据；产品输入传递、媒体导出、工作流和视频训练未验收"}
    write_json(output / "acceptance.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
