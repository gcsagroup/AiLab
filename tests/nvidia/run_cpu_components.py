"""固定真实权重在 CPU 上验证计算组件；不调用公共 CUDA 入口、不代表 NVIDIA 或质量验收。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "services/control"))
from adapters.nvidia_text import adapter
from ailab_control.remote.protocol import digest, file_hash
from test_adapter import frozen_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True); parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    source, evidence = args.model.resolve(), args.evidence.resolve(); evidence.mkdir(parents=True, exist_ok=False)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    import torch
    from transformers import AutoModelForCausalLM
    from safetensors.torch import load_file
    torch.set_num_threads(4); torch.manual_seed(0)
    record = {"status": "running", "validation_scope": "cpu_components_only", "nvidia_acceptance": "not_verified", "quality_acceptance": "not_evaluated", "public_cuda_entry_used": False, "source_code_digest": adapter.source_identity(), "environment": adapter.probe(), "started_at": time.time()}
    def save(): adapter.write_json(evidence / "report.json", record)
    events = []
    def emit(kind, value): events.append({"type": kind, **value})
    save()
    try:
        snapshot = frozen_snapshot(); input_root = evidence / "input"; model_root = input_root / "model"; model_root.mkdir(parents=True)
        for item in snapshot["inputs"]:
            path = source / Path(item["path"]).name
            assert path.stat().st_size == item["size"] and file_hash(path) == item["sha256"]
            shutil.copyfile(path, input_root / item["path"]); (input_root / item["path"]).chmod(0o400)
        effective, prepared = adapter.prepare(snapshot, input_root)
        print("CPU组件：读取固定原权重，公共CUDA入口保持不可用", flush=True)
        load_started = time.perf_counter()
        model = AutoModelForCausalLM.from_pretrained(str(model_root), torch_dtype=torch.float32, local_files_only=True, trust_remote_code=False, use_safetensors=True, attn_implementation="eager").to("cpu")
        model.eval(); model_load_seconds = time.perf_counter() - load_started
        assert str(next(model.parameters()).device) == "cpu"
        text, metrics = adapter.generate(model, prepared["tokenizer"], prepared["prompt"], effective, emit, lambda: None)
        assert text.strip() == "完成" and "".join(item["text"] for item in events if item["type"] == "token") == text
        record["generation"] = {"text": text, "metrics": metrics, "load_seconds": model_load_seconds, "actual_base_precision": "float32_cpu_component_check", "public_runtime_precision": "bfloat16_cuda_only"}
        print("CPU组件：生成完成，开始两步LoRA计算与矩阵转置核验", flush=True)
        data_root = input_root / "data"; data_root.mkdir(); dataset = data_root / "train.jsonl"
        dataset.write_text(json.dumps({"messages": [{"role": "user", "content": "训练组件专用问题：返回两个汉字。"}, {"role": "assistant", "content": "完成"}]}, ensure_ascii=False) + "\n")
        training = frozen_snapshot("train"); entry = {"path": "data/train.jsonl", "size": dataset.stat().st_size, "sha256": file_hash(dataset)}
        training["inputs"][-1] = entry; training["input"]["dataset_manifest_digest"] = digest([{**entry, "path": "train.jsonl"}])
        training_effective, training_prepared = adapter.prepare(training, input_root)
        embedding_before = model.model.embed_tokens.weight[0].detach().clone()
        model, state, train_metrics = adapter.train(model, training_prepared["tokenizer"], training_prepared["samples"], training_effective, emit, lambda: None)
        assert train_metrics["compute_device"] == "cpu" and len(train_metrics["losses"]) == 2 and any(value > 0 for value in train_metrics["parameter_max_abs_delta"].values())
        assert torch.equal(embedding_before, model.base_model.model.model.embed_tokens.weight[0].detach())
        converted_root = evidence / "component-output"; converted_root.mkdir()
        converted = adapter.write_adapters(state, training_effective, training, model_root, converted_root)
        mlx_state = load_file(str(converted_root / "mlx-adapter/adapters.safetensors"))
        comparisons = []
        for layer in range(23, 24):
            for module in ("q_proj", "v_proj"):
                old = f"base_model.model.model.layers.{layer}.self_attn.{module}."
                new = f"model.layers.{layer}.self_attn.{module}."
                x = torch.arange(1792, dtype=torch.float32).reshape(2, 896) / 1792
                peft_value = (x @ state[old + "lora_A.weight"].T) @ state[old + "lora_B.weight"].T
                mlx_value = (x @ mlx_state[new + "lora_a"]) @ mlx_state[new + "lora_b"]
                difference = float((peft_value - mlx_value).abs().max())
                assert torch.equal(state[old + "lora_A.weight"].T, mlx_state[new + "lora_a"])
                assert torch.equal(state[old + "lora_B.weight"].T, mlx_state[new + "lora_b"])
                # 权重转置逐值相同；不同连续布局的 FP32 matmul 仅要求数值等价。
                torch.testing.assert_close(peft_value, mlx_value, rtol=1e-5, atol=1e-8)
                comparisons.append({"module": module, "maximum_matrix_difference": difference})
        from workers.mlx_worker import validate_adapter_metadata
        config = json.loads((converted_root / "mlx-adapter/adapter_config.json").read_text())
        validate_adapter_metadata(str(converted_root / "mlx-adapter"), config["base_manifest_sha256"], adapter.TEMPLATE_SHA256, adapter.MODEL_DIGEST, training_effective["tokenization_recipe_digest"])
        adapter.read_inputs(training, input_root)
        assert adapter.source_identity() == record["source_code_digest"]
        record.update(status="passed", training={"metrics": train_metrics, "supervision_report": training_prepared["check_report"], "embedding_probe_unchanged": True}, conversion={"report": converted, "matrix_comparisons": comparisons, "mlx_metadata_validation": True, "apple_independent_load": "not_performed"}, input_unchanged=True, source_code_unchanged=True, public_runtime_ready=record["environment"]["ready"])
        assert record["public_runtime_ready"] is False
        adapter.write_json(evidence / "events.json", events)
    except Exception as error:
        record.update(status="failed", error=repr(error)); raise
    finally:
        record["finished_at"] = time.time(); save()
    print(json.dumps({key: record[key] for key in ("status", "validation_scope", "nvidia_acceptance", "public_runtime_ready")}, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
