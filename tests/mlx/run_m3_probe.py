"""真实验证 M3 来源合同、MLX 量化导出和另一进程固定问题回载。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/mlx"))
from adapters.mlx_text.preflight import check
from workers.mlx_worker import snapshot_manifest, write_json
from run_real_probe import run_worker


def ready(snapshot, name, evidence):
    result = check(snapshot, evidence / name)
    write_json(evidence / f"{name}.preflight.json", result)
    assert result["can_submit"], result
    return {**snapshot, "tokenization_recipe_digest": result["tokenization_recipe_digest"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=ROOT / ".artifacts/models/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence, model = args.evidence.absolute(), args.model.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    entries, digest = snapshot_manifest(model)
    write_json(evidence / "source-before.json", {"files": entries, "digest": digest})
    base = {"attempt_id": "m3-real-probe", "operation": "generate", "model_path": str(model), "model_manifest": entries, "model_manifest_digest": digest, "input": {"prompt": "请只输出 2+2 的结果。"}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", "max_tokens": 32, "temperature": 0, "top_p": 1, "seed": 0}}
    dataset = evidence / "train.jsonl"
    dataset.write_text(json.dumps({"messages": [{"role": "user", "content": "星河测试项目的启动代号是什么？"}, {"role": "assistant", "content": "星河测试项目的启动代号是 GCSA-ALPHA。"}]}, ensure_ascii=False) + "\n")
    data_entries, data_digest = snapshot_manifest(dataset)
    training = ready({**base, "operation": "train", "dataset_path": str(dataset), "dataset_manifest": data_entries, "dataset_manifest_digest": data_digest, "input": {}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", "steps": 1, "learning_rate": 0.001, "max_seq_length": 512, "lora_rank": 4, "lora_alpha": 8, "num_layers": 2, "seed": 0}}, "train", evidence)
    run_worker(training, "train", evidence)
    adapter = evidence / "train/adapter"
    adapter_entries, adapter_digest = snapshot_manifest(adapter)
    candidate = ready({**base, "adapter_path": str(adapter), "adapter_manifest": adapter_entries, "adapter_manifest_digest": adapter_digest, "adapter_training_recipe_digest": training["tokenization_recipe_digest"]}, "candidate-generate", evidence)
    run_worker(candidate, "candidate-generate", evidence)
    wrong_recipe = run_worker({**candidate, "adapter_training_recipe_digest": "0" * 64}, "negative-recipe", evidence, 1)
    assert wrong_recipe[-1]["code"] == "ADAPTER_PROVENANCE_MISMATCH"
    wrong_manifest = run_worker({**candidate, "adapter_manifest_digest": "0" * 64}, "negative-adapter-digest", evidence, 1)
    assert wrong_manifest[-1]["code"] == "ADAPTER_IDENTITY_CHANGED"
    quantize = ready({**base, "operation": "quantize", "input": {}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", "bits": 4, "group_size": 64, "mode": "affine", "seed": 0}}, "quantize", evidence)
    run_worker(quantize, "quantize", evidence)
    converted = evidence / "quantize/model"
    converted_entries, converted_digest = snapshot_manifest(converted)
    quantized_generation = ready({**base, "model_path": str(converted), "model_manifest": converted_entries, "model_manifest_digest": converted_digest}, "quantized-generate", evidence)
    run_worker(quantized_generation, "quantized-generate", evidence)
    for name, current_model, current_adapter in [("baseline-evaluation", model, None), ("candidate-evaluation", model, adapter), ("quantized-evaluation", converted, None), ("quantized-repeat", converted, None)]:
        command = [sys.executable, str(ROOT / "tests/mlx/evaluate_reload.py"), "--model", str(current_model), "--output", str(evidence / name)]
        if current_adapter:
            command += ["--adapter", str(current_adapter)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, cwd=ROOT)
        (evidence / f"{name}.stderr.log").write_text(result.stderr)
        assert result.returncode == 0, (name, result.stderr)
    import mlx.core as mx
    values = {name: mx.load(str(evidence / name / "logits.safetensors")) for name in ["baseline-evaluation", "candidate-evaluation", "quantized-evaluation", "quantized-repeat"]}
    deltas = {name: {key: float(mx.max(mx.abs(values["baseline-evaluation"][key] - current[key])).item()) for key in current} for name, current in values.items() if name in ["candidate-evaluation", "quantized-evaluation"]}
    repeats = {key: float(mx.max(mx.abs(values["quantized-evaluation"][key] - values["quantized-repeat"][key])).item()) for key in values["quantized-repeat"]}
    assert all(value > 0 for value in deltas["candidate-evaluation"].values())
    assert all(value == 0 for value in repeats.values())
    assert snapshot_manifest(model) == (entries, digest)
    assert snapshot_manifest(converted) == (converted_entries, converted_digest)
    conversion = json.loads((evidence / "quantize/conversion.json").read_text())
    assert conversion["output_weight_bytes"] < conversion["source_weight_bytes"]
    shards = list(converted.glob("*.safetensors"))
    assert all(path.stat().st_size < 256 * 1024 * 1024 for path in shards)
    report = {"status": "Apple M3 产物独立回载技术路径通过", "source_unchanged": True, "model_manifest_digest": digest, "adapter_manifest_digest": adapter_digest, "adapter_training_recipe_digest": training["tokenization_recipe_digest"], "quantized_manifest_digest": converted_digest, "quantization": conversion["quantization"], "source_weight_bytes": conversion["source_weight_bytes"], "quantized_weight_bytes": conversion["output_weight_bytes"], "weight_size_ratio": conversion["output_weight_bytes"] / conversion["source_weight_bytes"], "shard_count": len(shards), "max_shard_bytes": max(path.stat().st_size for path in shards), "fixed_evaluation_samples": 4, "last_position_logit_delta_vs_base": deltas, "quantized_repeat_logit_max_abs_delta": repeats, "negative_cases": {"wrong_recipe": wrong_recipe[-1]["code"], "wrong_adapter_digest": wrong_manifest[-1]["code"]}, "quality_acceptance": "未通过质量准入，四个固定问题保留原始输出供审阅，不以参数变化或文件缩小代替质量", "candidate_registry_status": "experimental", "nvidia": "未验证", "tv03": "未验证"}
    write_json(evidence / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
