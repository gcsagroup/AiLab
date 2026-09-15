"""顺序启动独立进程，生成合成训练数据并完成冻结样例 LoRA 重载对照。"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from prepare_tiny_sd import REPO, REVISION, sha256

TRAIN_PROMPT = "a studio product photograph of a small red ceramic teapot on a pale cream background, soft diffused lighting, centered composition"
EVALS = [
    {"name": "red_teapot", "seed": 2026, "prompt": TRAIN_PROMPT},
    {"name": "blue_cup", "seed": 2027, "prompt": "a studio product photograph of a small blue ceramic cup on a pale cream background, soft diffused lighting, centered composition"},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--run-name", default="acceptance-v1")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if Path(args.run_name).name != args.run_name or args.run_name in ("", ".", ".."):
        raise ValueError("证据目录名称不得含路径")
    run = root / args.run_name
    run.mkdir(exist_ok=False)
    recipe = {"repo": REPO, "revision": REVISION, "training_seeds": [101, 102, 103, 104], "evaluations": EVALS,
              "size": 512, "sampling_steps": 20, "cfg": 7.5, "train_steps": 12, "train_rank": 4, "learning_rate": 0.0001,
              "independent_repeat_max_absolute_pixel_tolerance": 1e-5,
              "acceptance": {"functional": "PNG 可独立解码；训练仅更新 LoRA 且基座不变；候选独立加载；同 seed 候选重复结果一致；基线与候选像素不同",
                             "quality": "冻结 2 个样例供人工检查主体、颜色、结构；不设置质量提升通过承诺", "unimplemented": "产品 UI、媒体导出、恢复和质量准入未接入"}}
    (run / "frozen-plan.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2) + "\n")
    cli = Path(__file__).with_name("image_cli.py")
    def invoke(name, command, extra):
        cmd = [sys.executable, "-u", str(cli), command, "--model-root", str(root / "model"), "--output", str(run / name), *extra]
        (run / f"{name}.command.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=2))
        print(f"开始：{name}", flush=True)
        with (run / f"{name}.log").open("w") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f"完成：{name}", flush=True)
    samples = []
    for seed in recipe["training_seeds"]:
        name = f"train-source-{seed}"
        invoke(name, "generate", ["--prompt", TRAIN_PROMPT, "--seed", str(seed)])
        file = run / name / "image.png"
        samples.append({"path": str(file.relative_to(run)), "caption": TRAIN_PROMPT, "sha256": sha256(file),
                        "source": "本次冻结官方基座生成的合成图片，未使用外部图片或真人素材", "generation_recipe": f"{name}/generation.json"})
    (run / "dataset.json").write_text(json.dumps({"version": "synthetic-teapot-v1", "samples": samples, "authority": "本机模型生成的技术试验数据；不代判底模训练语料权利"}, ensure_ascii=False, indent=2) + "\n")
    for item in EVALS:
        invoke("base-" + item["name"], "generate", ["--prompt", item["prompt"], "--seed", str(item["seed"])])
    invoke("lora", "train", ["--data", str(run / "dataset.json"), "--seed", "31415", "--steps", "12"])
    for item in EVALS:
        invoke("candidate-" + item["name"], "generate", ["--prompt", item["prompt"], "--seed", str(item["seed"]), "--adapter", str(run / "lora")])
    item = EVALS[0]
    invoke("candidate-repeat", "generate", ["--prompt", item["prompt"], "--seed", str(item["seed"]), "--adapter", str(run / "lora")])
    import numpy as np
    from PIL import Image
    comparisons = []
    for item in EVALS:
        base = np.load(run / ("base-" + item["name"]) / "pixels.npy")
        candidate = np.load(run / ("candidate-" + item["name"]) / "pixels.npy")
        delta = np.abs(base - candidate)
        if float(delta.max()) <= 0:
            raise RuntimeError("候选与基线无变化")
        for label in ("base-", "candidate-"):
            with Image.open(run / (label + item["name"]) / "image.png") as image:
                image.load()
                if image.size != (512, 512):
                    raise RuntimeError("图片独立解码尺寸异常")
        comparisons.append({"name": item["name"], "mean_absolute_pixel_difference": float(delta.mean()), "max_absolute_pixel_difference": float(delta.max())})
    first = np.load(run / "candidate-red_teapot" / "pixels.npy")
    repeated = np.load(run / "candidate-repeat" / "pixels.npy")
    repeat_delta = float(np.abs(first - repeated).max())
    if repeat_delta > 1e-5:
        raise RuntimeError(f"独立进程候选复现误差超过预设阈值：{repeat_delta}")
    report = {"functional_status": "通过", "quality_status": "待人工检查，不主张质量改善", "comparisons": comparisons,
              "independent_repeat_max_pixel_difference": repeat_delta, "independent_repeat_tolerance": 1e-5,
              "frozen_plan_sha256": sha256(run / "frozen-plan.json"), "m4_gate": "未完成产品级 M4；仅本组合 CLI 证据"}
    (run / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
