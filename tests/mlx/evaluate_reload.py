"""独立进程中加载基座或候选，保留固定问题输出与最后位置完整 logits。"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import mlx.core as mx
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler
from workers.mlx_worker import load_validated_adapter, model_manifest, snapshot_manifest, write_json

PROMPTS = ["请只输出 2+2 的结果。", "把 hello 翻译成中文。", "请用 JSON 输出 name 为星河的对象。", "星河测试项目的启动代号是什么？"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    mx.set_default_device(mx.gpu)
    mx.random.seed(0)
    model, tokenizer = load(str(args.model), tokenizer_config={"local_files_only": True, "trust_remote_code": False})
    if args.adapter:
        adapter_config = json.loads((args.adapter / "adapter_config.json").read_text())
        _, base_digest = snapshot_manifest(args.model)
        load_validated_adapter(model, tokenizer, str(args.adapter), model_manifest(args.model)["sha256"], base_digest, adapter_config.get("training_recipe_digest"))
    model.eval()
    results, logits = [], {}
    for index, prompt in enumerate(PROMPTS):
        ids = tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=True, add_generation_prompt=True)
        last = model(mx.array([ids]))[:, -1, :].astype(mx.float32)
        mx.eval(last)
        logits[f"prompt_{index}"] = last
        answer = generate(model, tokenizer, prompt=ids, max_tokens=64, sampler=make_sampler(temp=0), verbose=False)
        results.append({"prompt": prompt, "output": answer})
    mx.save_safetensors(str(args.output / "logits.safetensors"), logits)
    write_json(args.output / "outputs.json", {"samples": results, "seed": 0, "temperature": 0, "max_tokens": 64, "adapter": bool(args.adapter), "quality_threshold": "本次仅技术试验，无质量准入阈值"})


if __name__ == "__main__":
    main()
