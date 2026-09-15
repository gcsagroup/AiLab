#!/usr/bin/env python3
"""提交前读取真实 tokenizer，不加载模型权重，不写模型与输出目录。"""

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text.recipe import RECIPE_ID, TEMPLATE_SHA256, RecipeError, build_recipe, check_dataset
from workers.mlx_worker import WorkerError, model_manifest, sha256, validate_adapter_metadata, validate_snapshot
from adapters.mlx_text.evaluation import EvaluationError, load_plan, model_evaluation_identity, model_plan_bound
from adapters.mlx_text.checkpoint import CheckpointError, compatibility, verify_checkpoint
from adapters.mlx_text.inference import InferenceError, identity as inference_identity
from adapters.mlx_text.generation import GenerationError, prepare_prompt


def check(snapshot, output):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    with contextlib.redirect_stdout(sys.stderr):
        model, effective = validate_snapshot(snapshot, output)
        from mlx_lm.utils import load_tokenizer
        tokenizer = load_tokenizer(str(model), {"local_files_only": True, "trust_remote_code": False})
        template_digest = hashlib.sha256(tokenizer.chat_template.encode()).hexdigest()
        config = {}
        if snapshot.get("adapter_path"):
            if snapshot["operation"] not in {"generate", "evaluate"}:
                raise WorkerError("RESUME_UNSUPPORTED", "首个训练执行器不支持增量续训")
            adapter, config = validate_adapter_metadata(snapshot["adapter_path"], model_manifest(model)["sha256"], template_digest, snapshot["model_manifest_digest"], snapshot["adapter_training_recipe_digest"])
            from safetensors import safe_open
            rank = config["lora_parameters"]["rank"]
            expected = {}
            for layer in range(24 - config["num_layers"], 24):
                for module, width in [("q_proj", 896), ("v_proj", 128)]:
                    prefix = f"model.layers.{layer}.self_attn.{module}."
                    expected[prefix + "lora_a"] = [896, rank]
                    expected[prefix + "lora_b"] = [rank, width]
            with safe_open(str(adapter / "adapters.safetensors"), framework="numpy") as weights:
                if set(weights.keys()) != set(expected) or any(weights.get_slice(key).get_shape() != shape for key, shape in expected.items()):
                    raise WorkerError("ADAPTER_MODULE_MISMATCH", "适配器参数名称或形状不匹配")
            effective["adapter_sha256"] = sha256(adapter / "adapters.safetensors")
        report = {}
        if snapshot["operation"] == "generate":
            tokens, report = prepare_prompt(tokenizer, snapshot['input'], effective)
            effective.update(prompt_tokens=len(tokens), template_sha256=template_digest, context_observation=report,
                             thinking_supported=False, thinking_reason='Qwen2.5 模型和固定模板没有思考切换能力；模型默认行为不做输出隐藏。',
                             stream_scope='控制执行器 token 增量事件；阶段事件和最终结果始终保留。',
                             stop_scope='精确匹配解码文本，跨块保留前缀；命中时关闭生成器，结果不含命中序列。')
        elif snapshot["operation"] == "train":
            samples, report = check_dataset(tokenizer, snapshot["dataset_path"], effective["max_seq_length"])
            if not samples:
                return {"can_submit": False, "blocking": [{"code": "NO_TRAINABLE_DATA", "message": "没有可训练的助手监督样本"}], "effective_config": effective, "check_report": report}
            effective.update(template_sha256=TEMPLATE_SHA256, dataset_sha256=sha256(snapshot["dataset_path"]))
        elif snapshot["operation"] == "quantize":
            report = {"operation": "quantize", "output_format": "mlx-safetensors", "bits": effective["bits"], "group_size": effective["group_size"], "mode": effective["mode"], "shard_budget_bytes": effective["shard_budget_bytes"], "quality_acceptance": "需要独立加载与固定评测"}
        else:
            rows, criteria, plan_digest = load_plan(snapshot)
            counts = {}
            candidate_tokenizer = load_tokenizer(snapshot["candidate_model_path"], {"local_files_only": True, "trust_remote_code": False}) if snapshot.get("evaluation_kind") == "quantized_model" else None
            for row in rows:
                tokens = tokenizer.apply_chat_template([{"role": "user", "content": row["prompt"]}], tokenize=True, add_generation_prompt=True)
                if len(tokens) + criteria["generation"]["max_tokens"] > 4096:
                    raise WorkerError("CONTEXT_TOO_LONG", "评测样本与最大输出合计超过 4096 词元")
                if candidate_tokenizer is not None and candidate_tokenizer.apply_chat_template([{"role": "user", "content": row["prompt"]}], tokenize=True, add_generation_prompt=True) != tokens:
                    raise WorkerError("TOKENIZATION_IDENTITY_MISMATCH", "同一冻结问题在原权重与量化模型的分词结果不同")
                counts[row["category"]] = counts.get(row["category"], 0) + 1
            report = {"operation": "evaluate", "evaluation_plan_digest": plan_digest, "sample_count": len(rows), "category_counts": counts, "criteria": criteria, "prospective_plan_bound": config.get("evaluation_plan_digest") == plan_digest, "quality_acceptance": "待真实独立评测，事后评测不得登记为通过"}
            if candidate_tokenizer is not None:
                report.update(evaluation_kind="quantized_model", prospective_basis="first_quantized_model_evaluation", prospective_plan_bound=model_plan_bound(snapshot), model_comparison=snapshot["model_comparison"],
                              quality_acceptance="量化模型使用首次固定方案，完成实际独立对照并通过门槛后才可明确登记；其他方案只作对照。")
        recipe, digest = build_recipe(model, tokenizer, snapshot["operation"], effective.get("max_seq_length"))
        if snapshot.get("evaluation_kind") == "quantized_model":
            _, candidate_digest = build_recipe(Path(snapshot["candidate_model_path"]), candidate_tokenizer, "evaluate", None)
            if candidate_digest != digest:
                raise WorkerError("TOKENIZATION_IDENTITY_MISMATCH", "权重量化两侧分词配方不一致")
            evaluation_recipe, evaluation_digest = model_evaluation_identity(snapshot, digest)
            effective.update(model_evaluation_recipe=evaluation_recipe, model_evaluation_recipe_digest=evaluation_digest)
        if snapshot["operation"] == "generate":
            effective['tokenization_recipe_digest'] = digest
            inference_recipe, inference_digest = inference_identity(snapshot, effective, tokens, template_digest)
            effective.update(inference_recipe=inference_recipe, inference_recipe_digest=inference_digest)
        if snapshot.get("checkpoint_ref"):
            ref = snapshot["checkpoint_ref"]
            value = verify_checkpoint(ref["path"], ref["manifest_digest"], compatibility({**snapshot, "tokenization_recipe_digest": digest}))
            if value["sample_count"] != report["accepted_samples"]:
                raise CheckpointError("CHECKPOINT_INCOMPATIBLE", "检查点数据位置与本次数据检查不一致")
            report["resumed_from"] = {"source_attempt_id": ref["source_attempt_id"], "completed_steps": value["step"], "total_steps": value["total_steps"], "manifest_digest": value["digest"]}
        return {"can_submit": True, "blocking": [], "effective_config": effective, "tokenization_recipe_digest": digest, "recipe": recipe, "check_report": report}


def main():
    parser = argparse.ArgumentParser(description="本地 MLX 提交前分词检查")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.snapshot.read_text()), args.output_dir.absolute())
    except (WorkerError, RecipeError, EvaluationError, CheckpointError, InferenceError, GenerationError) as exc:
        result = {"can_submit": False, "blocking": [{"code": exc.code, "message": str(exc)}], **getattr(exc, 'details', {})}
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        result = {"can_submit": False, "blocking": [{"code": "PREFLIGHT_FAILED", "message": "请检查本地模型、数据与执行环境"}]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["can_submit"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
