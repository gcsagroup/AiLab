#!/usr/bin/env python3
"""受控独立 MLX 执行器：stdout 仅输出 JSONL，真实停止后由控制端确认取消。"""

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
import random
import resource
import signal
import shutil
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.mlx_text.recipe import RECIPE_ID, TEMPLATE_SHA256, RecipeError, build_recipe, check_dataset, collate_samples
from adapters.mlx_text.checkpoint import CheckpointError, TrainingControl, compatibility, restore_checkpoint, verify_checkpoint
from adapters.mlx_text.profiles import model_profile
from adapters.mlx_text.inference import FIELDS as INFERENCE_FIELDS, InferenceError, cache_summary, identity as inference_identity, initial_cache_summary, resolve as resolve_inference
from adapters.mlx_text.generation import GenerationError, StopBuffer, prepare_prompt

CANCELLED = False
EVENT_STREAM = sys.stdout


class WorkerError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def emit(kind, **payload):
    print(json.dumps({"type": kind, **payload}, ensure_ascii=False, allow_nan=False), file=EVENT_STREAM, flush=True)


def cancel_handler(*_):
    global CANCELLED
    CANCELLED = True


def check_cancel():
    if CANCELLED:
        raise WorkerError("CANCELLED", "执行已响应取消，进程即将退出")


def watch_controller():
    """宿主控制服务消失后停止自己，不操作任何其他进程。"""
    raw_pid = os.environ.get("AILAB_CONTROL_PID")
    if not raw_pid:
        return
    if not raw_pid.isdigit() or int(raw_pid) <= 1 or os.getppid() != int(raw_pid):
        raise WorkerError("INVALID_CONTROLLER", "执行器父进程身份不匹配")
    controller_pid = int(raw_pid)

    def watch():
        while True:
            time.sleep(1)
            if os.getppid() != controller_pid:
                cancel_handler()
                # MLX 同步点通常很快；底层算子不返回时仍保证有限时间退出。
                time.sleep(10)
                os._exit(130)

    threading.Thread(target=watch, daemon=True).start()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            check_cancel()
            digest.update(block)
    return digest.hexdigest()


def number(runtime, name, default, minimum, maximum, integer=False):
    value = runtime.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise WorkerError("INVALID_CONFIG", f"{name} 必须是有限数值")
    if integer and not isinstance(value, int):
        raise WorkerError("INVALID_CONFIG", f"{name} 必须是整数")
    if not minimum <= value <= maximum:
        raise WorkerError("INVALID_CONFIG", f"{name} 超出已验证适配器范围 {minimum}—{maximum}")
    return value


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def snapshot_manifest(path):
    """开发试验也显式冻结实际输入清单，与控制服务采用同一摘要规则。"""
    if path.is_symlink():
        raise WorkerError("INPUT_SYMLINK", "输入不能是符号链接")
    if path.is_file():
        files = [path]
        directory = path.parent
    else:
        directory = path
        files = []
        for item in sorted(path.rglob("*")):
            relative = item.relative_to(path)
            if relative.parts[:2] == (".cache", "huggingface") or item.name == ".gitattributes":
                continue
            if item.is_symlink():
                raise WorkerError("INPUT_SYMLINK", "输入目录包含符号链接")
            if item.is_file():
                files.append(item)
    entries = [{"path": p.relative_to(directory).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)} for p in files]
    return entries, canonical_digest(entries)


def verify_snapshot_manifest(path, entries, expected_digest, kind):
    if not isinstance(entries, list) or not entries or len(entries) > 10000 or not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise WorkerError(f"{kind}_IDENTITY_REQUIRED", "执行快照必须包含完整输入文件清单与摘要")
    if canonical_digest(entries) != expected_digest:
        raise WorkerError(f"{kind}_IDENTITY_CHANGED", "输入清单自身摘要不一致")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"} or not isinstance(entry["path"], str):
            raise WorkerError(f"{kind}_IDENTITY_CHANGED", "输入清单结构无效")
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or type(entry["size"]) is not int or entry["size"] < 0 or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise WorkerError(f"{kind}_IDENTITY_CHANGED", "输入文件身份无效")
    actual, actual_digest = snapshot_manifest(path)
    if actual_digest != expected_digest or actual != entries:
        raise WorkerError(f"{kind}_IDENTITY_CHANGED", "输入文件集合、大小或摘要与提交快照不一致")


def validate_snapshot(snapshot, output):
    if output.is_symlink() or output.resolve() != output:
        raise WorkerError("OUTPUT_SYMLINK", "输出路径不能经符号链接跳转")
    if not isinstance(snapshot, dict) or snapshot.get("operation") not in {"generate", "train", "quantize", "evaluate", "merge", "distill"}:
        raise WorkerError("UNSUPPORTED_OPERATION", "当前执行器只支持文本生成、SFT LoRA、固定文本评测与指定 MLX 量化")
    model_evaluation = snapshot.get("operation") == "evaluate" and snapshot.get("evaluation_kind") in {"quantized_model", "capability_comparison"}
    if (snapshot.get("candidate_model_path") or snapshot.get("evaluation_kind")) and not model_evaluation:
        raise WorkerError("MODEL_COMPARISON_UNSUPPORTED", "量化对照参数只能用于专用质量评测")
    runtime = snapshot.get("runtime", {})
    if not isinstance(runtime, dict) or not isinstance(snapshot.get("input", {}), dict):
        raise WorkerError("INVALID_CONFIG", "input 和 runtime 必须为对象")
    if runtime.get("engine", "mlx") != "mlx" or runtime.get("device_id", "apple-gpu") != "apple-gpu":
        raise WorkerError("UNSUPPORTED_DEVICE", "此执行器只支持 MLX Apple GPU")
    common = {"engine", "device_id", "seed"}
    generate_keys = {"max_tokens", "temperature", "top_p"}
    train_keys = {"training_type", "update_method", "recipe_id", "steps", "learning_rate", "max_seq_length", "lora_rank", "lora_alpha", "num_layers", "batch_size", "gradient_accumulation", "optimizer", "weight_decay", "lora_dropout"}
    operation_keys = {"generate": generate_keys | INFERENCE_FIELDS, "evaluate": generate_keys, "train": train_keys, "quantize": {"bits", "group_size", "mode"}, "merge": {"merge_weight"}, "distill": train_keys | {"teacher_max_tokens"}}
    unknown = set(runtime) - common - operation_keys[snapshot["operation"]]
    if unknown:
        raise WorkerError("UNSUPPORTED_PARAMETER", "未支持参数：" + "、".join(sorted(unknown)))
    raw_model = snapshot.get("model_path")
    if not isinstance(raw_model, str) or not Path(raw_model).is_absolute():
        raise WorkerError("MODEL_NOT_LOCAL", "模型必须是明确的本地绝对路径")
    try:
        model_path = Path(raw_model).resolve(strict=True)
    except FileNotFoundError as exc:
        raise WorkerError("MODEL_NOT_FOUND", "模型目录不存在") from exc
    if not model_path.is_dir():
        raise WorkerError("MODEL_NOT_FOUND", "模型目录不存在")
    verify_snapshot_manifest(model_path, snapshot.get("model_manifest"), snapshot.get("model_manifest_digest"), "MODEL")
    if output == model_path or output.is_relative_to(model_path) or model_path.is_relative_to(output):
        raise WorkerError("OUTPUT_OVERLAP", "输出目录不能与源模型目录重叠")
    if output.exists() and (output.is_symlink() or any(output.iterdir())):
        raise WorkerError("OUTPUT_EXISTS", "输出目录必须为空，不能覆盖已有产物")
    config = json.loads((model_path / "config.json").read_text())
    try:
        profile = model_profile(config)
    except ValueError as exc:
        raise WorkerError("MODEL_UNVERIFIED", str(exc)) from exc
    quantization = config.get("quantization") or config.get("quantization_config")
    if profile["name"] == "qwen25-7b" and (quantization or snapshot["operation"] == "quantize" or model_evaluation):
        raise WorkerError("MODEL_OPERATION_UNSUPPORTED", "7B 当前只开放未量化基座的生成、SFT LoRA 与适配器评测；量化需独立验证")
    if quantization:
        expected_quantization = {"group_size": 64, "bits": 4, "mode": "affine"}
        if quantization != expected_quantization or any(config.get(key) not in (None, expected_quantization) for key in ["quantization", "quantization_config"]):
            raise WorkerError("MODEL_FORMAT_UNSUPPORTED", "当前只验证 MLX 4-bit／64／affine 量化格式")
        if snapshot["operation"] != "generate":
            raise WorkerError("MODEL_OPERATION_UNSUPPORTED", "当前量化模型只开放推理，训练和再次量化需要未量化源模型")
    if not list(model_path.glob("*.safetensors")):
        raise WorkerError("MODEL_WEIGHTS_MISSING", "模型缺少 safetensors 权重")
    effective = {"engine": "mlx", "device_id": "apple-gpu", "seed": number(runtime, "seed", 0, 0, 2**32 - 1, True)}
    effective["input_quantization"] = quantization
    if snapshot.get("adapter_path"):
        if snapshot["operation"] not in {"generate", "evaluate", "merge"} or quantization:
            raise WorkerError("ADAPTER_OPERATION_UNSUPPORTED", "当前适配器仅支持在未量化基座上推理")
        adapter = Path(snapshot["adapter_path"])
        if not adapter.is_absolute() or not adapter.is_dir():
            raise WorkerError("ADAPTER_NOT_LOCAL", "适配器必须是明确本地绝对目录")
        if output == adapter or output.is_relative_to(adapter) or adapter.is_relative_to(output):
            raise WorkerError("OUTPUT_OVERLAP", "输出目录不能与源适配器重叠")
        verify_snapshot_manifest(adapter, snapshot.get("adapter_manifest"), snapshot.get("adapter_manifest_digest"), "ADAPTER")
        if not isinstance(snapshot.get("adapter_training_recipe_digest"), str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot["adapter_training_recipe_digest"]):
            raise WorkerError("ADAPTER_PROVENANCE_REQUIRED", "缺少适配器来源训练配方身份")
    if snapshot["operation"] == "generate":
        prompt = snapshot.get("input", {}).get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16000:
            raise WorkerError("INVALID_PROMPT", "请输入非空且不超过 16000 字符的提示词")
        if set(snapshot["input"]) - {"prompt"}:
            raise WorkerError("UNSUPPORTED_INPUT", "当前生成仅支持 prompt")
        effective.update(max_tokens=number(runtime, "max_tokens", 128, 1, 2048, True), temperature=number(runtime, "temperature", 0, 0, 2), top_p=number(runtime, "top_p", 1, 0.01, 1))
        effective.update(resolve_inference(runtime))
        if profile["name"] == "qwen25-7b" and effective["kv_precision"] != "auto":
            raise WorkerError("UNSUPPORTED_PARAMETER", "7B 的 q4 KV 缓存尚未通过质量验证，请使用普通缓存")
        if config.get("num_attention_heads") != profile["num_attention_heads"] or config.get("num_key_value_heads") != profile["num_key_value_heads"]:
            raise WorkerError("MODEL_UNVERIFIED", "注意力头与当前固定 Qwen 结构不符")
    elif snapshot["operation"] in {"train", "distill"}:
        fixed = {"training_type": "sft", "update_method": "lora", "recipe_id": RECIPE_ID, "batch_size": 1, "gradient_accumulation": 1, "optimizer": "adamw", "weight_decay": 0, "lora_dropout": 0}
        for key, value in fixed.items():
            if runtime.get(key, value) != value or isinstance(runtime.get(key), bool):
                raise WorkerError("UNSUPPORTED_PARAMETER", f"首个训练适配器要求 {key}={value}")
        effective.update(fixed)
        effective.update(steps=number(runtime, "steps", 4, 1, 200, True), learning_rate=number(runtime, "learning_rate", 0.0001, 1e-7, 0.01), max_seq_length=number(runtime, "max_seq_length", 512, 32, 2048, True), lora_rank=number(runtime, "lora_rank", 4, 1, 32, True), lora_alpha=number(runtime, "lora_alpha", 8, 1, 64), num_layers=number(runtime, "num_layers", 2, 1, profile["num_hidden_layers"], True))
        dataset = Path(snapshot.get("dataset_path", ""))
        if not dataset.is_absolute() or not dataset.is_file() or dataset.stat().st_size > 64 * 1024 * 1024:
            raise WorkerError("INVALID_DATASET", "训练数据必须是小于 64 MiB 的本地 JSONL 文件")
        if output == dataset or dataset.is_relative_to(output):
            raise WorkerError("OUTPUT_OVERLAP", "输出不能覆盖训练数据")
        verify_snapshot_manifest(dataset, snapshot.get("dataset_manifest"), snapshot.get("dataset_manifest_digest"), "DATASET")
        if snapshot.get("checkpoint_ref"):
            checkpoint = snapshot["checkpoint_ref"]
            if not isinstance(checkpoint, dict) or not all(isinstance(checkpoint.get(key), str) for key in ("path", "manifest_digest", "source_attempt_id")):
                raise WorkerError("CHECKPOINT_INVALID", "恢复快照缺少完整检查点来源")
            value = verify_checkpoint(checkpoint["path"], checkpoint["manifest_digest"], compatibility(snapshot) if snapshot.get("tokenization_recipe_digest") else None, check_cancel)
            if value["source_attempt_id"] != checkpoint["source_attempt_id"]:
                raise WorkerError("CHECKPOINT_INVALID", "检查点与来源运行不一致")
    elif snapshot["operation"] == "merge":
        if not snapshot.get("adapter_path"):
            raise WorkerError("ADAPTER_REQUIRED", "合并需要来源明确的 LoRA 适配器")
        if snapshot.get("input") not in ({}, {"prompt": ""}, None):
            raise WorkerError("UNSUPPORTED_INPUT", "合并不接受生成输入")
        effective["merge_weight"] = number(runtime, "merge_weight", 1, 0.01, 1)
    elif snapshot["operation"] == "quantize":
        if snapshot.get("input") not in ({}, {"prompt": ""}, None):
            raise WorkerError("UNSUPPORTED_INPUT", "量化操作不接受提示词或训练样本")
        if runtime.get("mode", "affine") != "affine":
            raise WorkerError("UNSUPPORTED_PARAMETER", "当前量化只支持 affine 模式")
        effective.update(bits=number(runtime, "bits", 4, 4, 4, True), group_size=number(runtime, "group_size", 64, 64, 64, True), mode="affine", shard_budget_bytes=128 * 1024 * 1024)
    else:
        if model_evaluation:
            validate_comparison_model(snapshot, output, model_path)
        elif not snapshot.get("adapter_path"):
            raise WorkerError("ADAPTER_REQUIRED", "评测需要指定来源明确的 LoRA 候选")
        if snapshot.get("input") not in ({}, {"prompt": ""}, None):
            raise WorkerError("UNSUPPORTED_INPUT", "评测提示词只取自冻结评测集")
        effective.update(max_tokens=number(runtime, "max_tokens", 128, 1, 512, True), temperature=number(runtime, "temperature", 0, 0, 0), top_p=number(runtime, "top_p", 1, 1, 1))
    if snapshot["operation"] == "distill":
        from workers.mlx_lab import distillation_prompts
        teacher = snapshot.get("teacher", {})
        teacher_path = Path(teacher.get("path", ""))
        if not teacher_path.is_absolute() or not teacher_path.is_dir() or teacher_path.resolve() != teacher_path:
            raise WorkerError("TEACHER_NOT_LOCAL", "教师必须是明确的本地模型")
        if output == teacher_path or output.is_relative_to(teacher_path) or teacher_path.is_relative_to(output):
            raise WorkerError("OUTPUT_OVERLAP", "输出不能与教师模型重叠")
        verify_snapshot_manifest(teacher_path, teacher.get("manifest"), teacher.get("manifest_digest"), "TEACHER")
        teacher_config = json.loads((teacher_path / "config.json").read_text())
        model_profile(teacher_config)
        if teacher_config.get("quantization") or teacher_config.get("quantization_config"):
            raise WorkerError("TEACHER_UNSUPPORTED", "当前教师要求未量化 Qwen2.5 0.5B 或 7B")
        effective.update(teacher_max_tokens=number(runtime, "teacher_max_tokens", 64, 8, 256, True), teacher_manifest_digest=teacher["manifest_digest"], distillation_samples=len(distillation_prompts(snapshot)))
    if snapshot["operation"] == "evaluate" or snapshot.get("evaluation_plan_digest"):
        from adapters.mlx_text.evaluation import load_plan
        rows, criteria, plan_digest = load_plan(snapshot)
        effective["evaluation_plan_digest"] = plan_digest
        if snapshot["operation"] == "evaluate" and any(effective[key] != value for key, value in criteria["generation"].items()):
            raise WorkerError("EVALUATION_CONFIG_CHANGED", "本次生成参数与冻结评测规则不一致")
    return model_path, effective


def validate_comparison_model(snapshot, output, base_path):
    if snapshot.get("adapter_path") or snapshot.get("dataset_path") or snapshot.get("checkpoint_ref"):
        raise WorkerError("MODEL_COMPARISON_UNSUPPORTED", "量化对照不接受适配器、训练数据或检查点")
    raw = snapshot.get("candidate_model_path")
    candidate = Path(raw) if isinstance(raw, str) else Path()
    if not isinstance(raw, str) or not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_dir():
        raise WorkerError("CANDIDATE_MODEL_NOT_LOCAL", "量化候选必须为明确的本地独立模型目录")
    candidate = candidate.resolve(strict=True)
    if candidate == base_path or output == candidate or output.is_relative_to(candidate) or candidate.is_relative_to(output):
        raise WorkerError("OUTPUT_OVERLAP", "量化对照的基线、候选和输出目录必须独立")
    verify_snapshot_manifest(candidate, snapshot.get("candidate_model_manifest"), snapshot.get("candidate_model_manifest_digest"), "CANDIDATE_MODEL")
    config = json.loads((candidate / "config.json").read_text())
    if snapshot.get("evaluation_kind") == "capability_comparison":
        profile = model_profile(config)
        quantization = config.get("quantization") or config.get("quantization_config")
        expected_quantization = {"bits": 4, "group_size": 64, "mode": "affine"}
        if profile["name"] != "qwen25-0.5b" or quantization not in (None, expected_quantization) or any(config.get(key) not in (None, expected_quantization) for key in ("quantization", "quantization_config")) or not list(candidate.glob("*.safetensors")):
            raise WorkerError("MODEL_COMPARISON_UNSUPPORTED", "普通能力候选需要未量化或固定 MLX 4-bit Qwen2.5-0.5B")
        expected = {"kind": "capability_comparison", "baseline_model_id": snapshot.get("model_id"), "baseline_model_version_id": snapshot.get("model_version_id"), "baseline_model_manifest_digest": snapshot["model_manifest_digest"], "candidate_model_id": snapshot.get("candidate_model_id"), "candidate_model_version_id": snapshot.get("candidate_model_version_id"), "candidate_model_manifest_digest": snapshot["candidate_model_manifest_digest"]}
        if snapshot.get("model_comparison") != expected or canonical_digest(expected) != snapshot.get("model_comparison_digest") or expected["baseline_model_manifest_digest"] == expected["candidate_model_manifest_digest"]:
            raise WorkerError("MODEL_COMPARISON_CHANGED", "普通能力对照模型身份不完整或发生变化")
        tokenizer_files = {"tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja", "generation_config.json"}
        if {item["path"]: item for item in snapshot["model_manifest"] if item["path"] in tokenizer_files} != {item["path"]: item for item in snapshot["candidate_model_manifest"] if item["path"] in tokenizer_files}:
            raise WorkerError("TOKENIZATION_IDENTITY_MISMATCH", "当前普通能力对照要求两侧分词器和模板一致")
        return candidate
    quantization = {"bits": 4, "group_size": 64, "mode": "affine"}
    if config.get("model_type") != "qwen2" or config.get("hidden_size") != 896 or config.get("num_hidden_layers") != 24 or config.get("quantization") != quantization or config.get("quantization_config") not in (None, quantization) or not list(candidate.glob("*.safetensors")):
        raise WorkerError("MODEL_COMPARISON_UNSUPPORTED", "量化候选格式须为固定 Qwen MLX 4-bit／64／affine")
    tokenizer_files = {"tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja", "generation_config.json"}
    if {item["path"]: item for item in snapshot["model_manifest"] if item["path"] in tokenizer_files} != {item["path"]: item for item in snapshot["candidate_model_manifest"] if item["path"] in tokenizer_files}:
        raise WorkerError("TOKENIZATION_IDENTITY_MISMATCH", "量化评测两侧分词器、模板或生成配置不同")
    comparison = snapshot.get("model_comparison")
    required = {"kind", "baseline_model_id", "baseline_model_version_id", "baseline_model_manifest_digest", "candidate_model_id", "candidate_model_version_id", "candidate_model_manifest_digest", "conversion_attempt_id", "conversion_manifest_digest", "conversion_report_sha256", "candidate_format", "candidate_default_engine", "quantization"}
    expected = {"kind": "quantized_model", "baseline_model_id": snapshot.get("model_id"), "baseline_model_version_id": snapshot.get("model_version_id"), "baseline_model_manifest_digest": snapshot["model_manifest_digest"], "candidate_model_id": snapshot.get("candidate_model_id"), "candidate_model_version_id": snapshot.get("candidate_model_version_id"), "candidate_model_manifest_digest": snapshot["candidate_model_manifest_digest"], "candidate_format": "mlx-safetensors", "candidate_default_engine": "mlx", "quantization": quantization}
    if not isinstance(comparison, dict) or set(comparison) != required or canonical_digest(comparison) != snapshot.get("model_comparison_digest") or any(comparison.get(key) != value for key, value in expected.items()) or any(not isinstance(comparison.get(key), str) or not comparison[key] for key in ("baseline_model_id", "baseline_model_version_id", "candidate_model_id", "candidate_model_version_id", "conversion_attempt_id")) or any(not isinstance(comparison.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", comparison[key]) for key in ("conversion_manifest_digest", "conversion_report_sha256")):
        raise WorkerError("MODEL_COMPARISON_CHANGED", "原权重与量化候选的来源配对身份不完整或已变化")
    binding = snapshot.get("quality_plan_ref")
    fields = {"schema_version", "model_comparison_digest", "evaluation_plan_id", "evaluation_plan_digest", "frozen_at", "digest"}
    if not isinstance(binding, dict) or set(binding) != fields or binding.get("schema_version") != "quantized-model-quality-v1" or binding.get("model_comparison_digest") != snapshot["model_comparison_digest"] or canonical_digest({key: value for key, value in binding.items() if key != "digest"}) != binding.get("digest"):
        raise WorkerError("MODEL_QUALITY_PLAN_CHANGED", "量化模型的首次冻结准入身份无效")
    return candidate


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def model_manifest(model_path):
    files = [p for p in sorted(model_path.iterdir()) if p.is_file() and (p.suffix in {".json", ".safetensors", ".txt", ".jinja"} or p.name == "LICENSE")]
    entries = [{"path": p.name, "size": p.stat().st_size, "sha256": sha256(p)} for p in files]
    return {"files": entries, "sha256": hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()}


def run_generate(model, tokenizer, snapshot, effective, output):
    import mlx.core as mx
    from mlx_lm import stream_generate
    from mlx_lm.models.cache import make_prompt_cache
    from mlx_lm.sample_utils import make_sampler
    prompt, context_report = prepare_prompt(tokenizer, snapshot['input'], effective)
    effective.update(prompt_tokens=len(prompt), context_observation=context_report, kv_cache="4 bit 推理缓存，保留完整上下文" if effective["kv_precision"] == "q4" else "跟随实际计算精度的完整 KV", template_sha256=hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
                     thinking_supported=False, thinking_reason='Qwen2.5 模型和固定模板没有思考切换能力；模型默认行为不做输出隐藏。',
                     stream_scope='控制执行器 token 增量事件；阶段事件和最终结果始终保留。',
                     stop_scope='精确匹配解码文本，跨块保留前缀；命中时关闭生成器，结果不含命中序列。')
    recipe, recipe_digest = inference_identity(snapshot, effective, prompt, effective["template_sha256"])
    expected = snapshot.get("effective_config", {})
    if not expected.get("inference_recipe_digest") or not expected.get("inference_recipe"):
        raise InferenceError("INFERENCE_IDENTITY_REQUIRED", "运行快照缺少本次推理配方，请重新检查后提交。")
    if expected["inference_recipe_digest"] != recipe_digest or expected["inference_recipe"] != recipe:
        raise InferenceError("INFERENCE_IDENTITY_CHANGED", "输入、缓存策略或推理实现与提交前检查不一致。")
    effective.update(inference_recipe_digest=recipe_digest, inference_recipe=recipe)
    emit("phase", phase="generating", message="模型已加载，正在生成")
    through_load_peak = mx.get_peak_memory()
    generation_active_baseline = mx.get_active_memory()
    mx.reset_peak_memory()
    generation_started = time.perf_counter()
    cache = make_prompt_cache(model, max_kv_size=None)
    chunks, token_ids, prefill_progress = [], [], []
    last, first_token_seconds = None, None
    stop_buffer = StopBuffer(effective['stop'])
    token_events = 0

    def progress(processed, total):
        check_cancel()
        prefill_progress.append({"processed_tokens": processed, "total_tokens": total})
        emit("phase", phase="prefilling" if processed < total else "generating", message=f"正在处理提示词（{processed}/{total}）" if processed < total else "提示词已处理，正在生成")

    try:
        initial = initial_cache_summary(cache, len(model.layers))
        with contextlib.closing(stream_generate(model, tokenizer, prompt, max_tokens=effective["max_tokens"], sampler=make_sampler(temp=effective["temperature"], top_p=effective["top_p"]), prompt_cache=cache, max_kv_size=None, prefill_step_size=effective["prefill_step_size"], kv_bits=effective["kv_bits"], kv_group_size=effective["kv_group_size"], quantized_kv_start=effective["quantized_kv_start"], prompt_progress_callback=progress)) as responses:
            for response in responses:
                check_cancel()
                if first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - generation_started
                visible = stop_buffer.feed(response.text)
                chunks.append(visible)
                token_ids.append(response.token)
                last = response
                if effective['stream'] and (visible or not effective['stop']):
                    emit("token", text=visible, token_id=response.token, generation_tokens=response.generation_tokens)
                    token_events += 1
                if stop_buffer.stopped:
                    break
        trailing = stop_buffer.finish()
        if trailing:
            chunks.append(trailing)
            if effective['stream']:
                emit('token', text=trailing, token_id=last.token, generation_tokens=last.generation_tokens)
                token_events += 1
        check_cancel()
        mx.synchronize()
        generation_seconds = time.perf_counter() - generation_started
        final_cache = cache_summary(cache, effective["kv_precision"], len(model.layers))
        generation_peak = mx.get_peak_memory()
    finally:
        cache.clear()
        mx.clear_cache()
    effective.update(cache_observation={"initial": initial, "final": final_cache}, prefix_cache_hit_rate=None)
    (output / "result.txt").write_text("".join(chunks))
    metrics = {"generation_tokens": last.generation_tokens if last else 0, "prompt_tokens": len(prompt), "generation_tps": float(last.generation_tps) if last else 0,
               "prompt_tps": float(last.prompt_tps) if last else 0, "first_token_seconds": first_token_seconds, "generation_wall_seconds": generation_seconds,
               "mlx_active_before_generation_bytes": generation_active_baseline, "mlx_peak_through_model_load_bytes": through_load_peak,
               "mlx_generation_peak_bytes": generation_peak, "peak_memory_bytes": max(through_load_peak, generation_peak),
               "final_kv_allocated_bytes": final_cache["total_allocated_bytes"], "process_rss_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
               "prefill_progress": prefill_progress, "output_token_ids": token_ids, "prefix_cache_hit_rate": None,
               "finish_reason": 'stop_sequence' if stop_buffer.stopped else 'eos' if getattr(last, 'finish_reason', None) == 'stop' else 'length' if getattr(last, 'finish_reason', None) == 'length' else 'completed',
               "matched_stop_index": stop_buffer.matched_index, "stream": effective['stream'], "token_events": token_events,
               "visible_characters": len(''.join(chunks)), "input_truncated": False,
               "output_token_ids_scope": '引擎实际返回的词元，可能包括 EOS 或触发停止序列的词元；可见结果排除停止序列，不把模型计算量冒充可见文本长度。',
               "memory_scope": "生成前重置 MLX 峰值；生成阶段包含已加载权重，未扣除基线。全流程峰值取加载与生成阶段最大值；KV 为结束时数组分配字节。RSS 为操作系统截至记录时的进程峰值。",
               "timing_scope": "首 token 与生成墙钟从本次新建缓存前计时，不含模型加载；首 token 包含引擎可能返回的终止词元。"}
    write_json(output / "cache-observation.json", effective["cache_observation"])
    write_json(output / "metrics.json", metrics)
    emit("metric", **metrics)


def validate_adapter_metadata(adapter_path, base_digest, template_digest, base_input_digest=None, training_recipe_digest=None, max_layers=24):
    path = Path(adapter_path)
    if not path.is_absolute() or not path.is_dir():
        raise WorkerError("ADAPTER_NOT_LOCAL", "适配器必须是本地绝对目录")
    if any(p.is_symlink() for p in path.rglob("*")):
        raise WorkerError("ADAPTER_SYMLINK", "适配器目录不能含符号链接")
    config = json.loads((path / "adapter_config.json").read_text())
    if config.get("base_manifest_sha256") != base_digest:
        raise WorkerError("ADAPTER_BASE_MISMATCH", "适配器基座摘要与当前模型不符")
    if config.get("template_sha256") != template_digest:
        raise WorkerError("ADAPTER_TEMPLATE_MISMATCH", "适配器聊天模板不符")
    if base_input_digest is not None and (config.get("base_input_manifest_digest") != base_input_digest or config.get("training_recipe_digest") != training_recipe_digest):
        raise WorkerError("ADAPTER_PROVENANCE_MISMATCH", "适配器的来源基座或训练配方身份不匹配")
    params = config.get("lora_parameters", {})
    if config.get("fine_tune_type") != "lora" or params.get("keys") != ["self_attn.q_proj", "self_attn.v_proj"]:
        raise WorkerError("ADAPTER_MODULE_MISMATCH", "适配器类型或模块不属于已验证组合")
    number(config, "num_layers", 0, 1, max_layers, True)
    number(params, "rank", 0, 1, 32, True)
    number(params, "scale", 0, 1 / 32, 64)
    if params.get("dropout") != 0:
        raise WorkerError("ADAPTER_CONFIG_MISMATCH", "当前仅支持 dropout=0 的适配器")
    return path, config


def load_validated_adapter(model, tokenizer, adapter_path, base_digest, base_input_digest=None, training_recipe_digest=None):
    """同时核对基座、模板、模块名称与形状，避免底层宽松加载吞掉错误。"""
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from mlx_lm.tuner.utils import linear_to_lora_layers
    path, config = validate_adapter_metadata(adapter_path, base_digest, hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(), base_input_digest, training_recipe_digest, len(model.layers))
    params = config["lora_parameters"]
    model.freeze()
    linear_to_lora_layers(model, config["num_layers"], params)
    expected = dict(tree_flatten(model.trainable_parameters()))
    weights = mx.load(str(path / "adapters.safetensors"))
    if set(weights) != set(expected) or any(weights[key].shape != expected[key].shape for key in expected):
        raise WorkerError("ADAPTER_MODULE_MISMATCH", "适配器参数名称或形状不匹配")
    model.load_weights(list(weights.items()), strict=False)
    model.eval()
    mx.eval(model.parameters())
    return sha256(path / "adapters.safetensors")


def run_train(model, tokenizer, snapshot, effective, output):
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx.utils import tree_flatten
    from mlx_lm.tuner.utils import linear_to_lora_layers
    effective.update(lora_scale=effective["lora_alpha"] / effective["lora_rank"], target_modules=["self_attn.q_proj", "self_attn.v_proj"], precision="基座 BF16，LoRA FP32", packing=False, truncation="exclude_whole_sample", label_shift="损失处恰好一次", supervision="assistant_content_and_im_end", ignore_index=-100, template_sha256=TEMPLATE_SHA256, optimizer_parameters={"betas": [0.9, 0.999], "eps": 1e-8, "bias_correction": True}, scheduler="constant", warmup_steps=0, gradient_clipping=None, sample_order="按文件顺序循环，seed用于LoRA初始化")
    effective["dataset_sha256"] = sha256(snapshot["dataset_path"])
    samples, report = check_dataset(tokenizer, snapshot["dataset_path"], effective["max_seq_length"], check_cancel)
    write_json(output / "data-check.json", report)
    if not samples:
        raise WorkerError("NO_TRAINABLE_DATA", "数据检查没有可训练样本，请查看 data-check.json")
    model.freeze()
    lora_config = {"rank": effective["lora_rank"], "scale": effective["lora_scale"], "dropout": 0.0, "keys": effective["target_modules"]}
    linear_to_lora_layers(model, effective["num_layers"], lora_config)
    mx.eval(model.trainable_parameters())
    initial = {k: mx.array(v) for k, v in tree_flatten(model.trainable_parameters())}
    if not initial or any("lora_" not in key for key in initial):
        raise WorkerError("TRAINABLE_MODULES_INVALID", "可训练参数必须全部为 LoRA")
    effective["resolved_trainable_modules"] = sorted(initial)
    effective["trainable_parameters"] = sum(v.size for v in initial.values())
    optimizer = optim.AdamW(learning_rate=effective["learning_rate"], weight_decay=0, betas=[0.9, 0.999], eps=1e-8, bias_correction=True)
    optimizer.init(model.trainable_parameters())

    def loss_fn(current, inputs, labels):
        logits = current(inputs[:, :-1]).astype(mx.float32)
        targets = labels[:, 1:]
        mask = targets != -100
        safe = mx.where(mask, targets, 0)
        per_token = nn.losses.cross_entropy(logits, safe, reduction="none")
        return (per_token * mask).sum() / mask.sum()

    loss_and_grad = nn.value_and_grad(model, loss_fn)
    model.train()
    losses = []
    if snapshot.get("checkpoint_ref"):
        ref = snapshot["checkpoint_ref"]
        losses, initial = restore_checkpoint(ref["path"], ref["manifest_digest"], snapshot, model, optimizer, check_cancel)
        effective["resumed_from"] = {"source_attempt_id": ref["source_attempt_id"], "manifest_digest": ref["manifest_digest"], "completed_steps": len(losses), "trajectory_state": "weights_optimizer_rng_data_position"}
    control = TrainingControl(output.parent, snapshot, emit, check_cancel)
    emit("phase", phase="training", message="数据检查通过，正在更新 LoRA", accepted_samples=len(samples))
    started = time.monotonic()
    control.safe_point(model, optimizer, initial, losses, len(samples))
    for step in range(len(losses) + 1, effective["steps"] + 1):
        check_cancel()
        sample = samples[(step - 1) % len(samples)]
        batch = collate_samples([sample], tokenizer.pad_token_id)
        loss, grads = loss_and_grad(model, mx.array(batch["input_ids"]), mx.array(batch["labels"]))
        optimizer.update(model, grads)
        mx.eval(model.parameters(), optimizer.state, loss)
        value = float(loss.item())
        if not math.isfinite(value):
            raise WorkerError("NONFINITE_LOSS", "训练损失非有限数，停止本次执行")
        losses.append(value)
        emit("metric", step=step, total_steps=effective["steps"], loss=value, supervised_tokens=sample["supervised_tokens"])
        control.safe_point(model, optimizer, initial, losses, len(samples))
    check_cancel()
    if sha256(snapshot["dataset_path"]) != effective["dataset_sha256"]:
        raise WorkerError("DATASET_CHANGED", "训练期间源数据发生变化，拒绝保存候选")
    final = dict(tree_flatten(model.trainable_parameters()))
    deltas = {key: float(mx.max(mx.abs(final[key] - initial[key])).item()) for key in final}
    if not any(value > 0 for value in deltas.values()):
        raise WorkerError("WEIGHTS_UNCHANGED", "训练结束但 LoRA 参数没有变化")
    adapter = output / "adapter"
    adapter.mkdir()
    mx.save_safetensors(str(adapter / "adapters.safetensors"), final)
    write_json(adapter / "adapter_config.json", {"fine_tune_type": "lora", "num_layers": effective["num_layers"], "lora_parameters": lora_config, "base_manifest_sha256": effective["model_manifest_sha256"], "base_input_manifest_digest": snapshot["model_manifest_digest"], "training_recipe_digest": snapshot["tokenization_recipe_digest"], "evaluation_plan_digest": snapshot.get("evaluation_plan_digest"), "template_sha256": TEMPLATE_SHA256, "recipe_id": RECIPE_ID})
    write_json(output / "train-metrics.json", {"losses": losses, "parameter_max_abs_delta": deltas, "elapsed_seconds": time.monotonic() - started, "peak_memory_bytes": mx.get_peak_memory(), "quality_acceptance": "未评定；参数变化与损失不代表质量通过"})


def run_quantize(model, model_path, effective, output):
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from mlx_lm.utils import quantize_model
    emit("phase", phase="quantizing", message="正在生成独立的 MLX 4-bit 模型")
    config = json.loads((model_path / "config.json").read_text())
    quantized, config = quantize_model(model, config, effective["group_size"], effective["bits"], mode=effective["mode"])
    mx.eval(quantized.parameters())
    check_cancel()
    destination = output / "model"
    destination.mkdir()
    weights = dict(tree_flatten(quantized.parameters()))
    shards, current, current_bytes = [], {}, 0
    for name, value in sorted(weights.items()):
        if value.nbytes > effective["shard_budget_bytes"]:
            raise WorkerError("TENSOR_TOO_LARGE", "单个张量超过当前模型分片预算")
        if current and current_bytes + value.nbytes > effective["shard_budget_bytes"]:
            shards.append(current)
            current, current_bytes = {}, 0
        current[name] = value
        current_bytes += value.nbytes
    if current:
        shards.append(current)
    index = {"metadata": {"total_size": sum(value.nbytes for value in weights.values())}, "weight_map": {}}
    for sequence, shard in enumerate(shards, 1):
        check_cancel()
        name = f"model-{sequence:05d}-of-{len(shards):05d}.safetensors"
        mx.save_safetensors(str(destination / name), shard, metadata={"format": "mlx"})
        index["weight_map"].update({key: name for key in shard})
        emit("metric", saved_shards=sequence, total_shards=len(shards))
    write_json(destination / "model.safetensors.index.json", index)
    write_json(destination / "config.json", config)
    for name in ["tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja", "generation_config.json", "LICENSE", "README.md"]:
        if (model_path / name).is_file():
            shutil.copyfile(model_path / name, destination / name)
    output_manifest, output_digest = snapshot_manifest(destination)
    source_size = sum(path.stat().st_size for path in model_path.glob("*.safetensors"))
    target_size = sum(path.stat().st_size for path in destination.glob("*.safetensors"))
    effective.update(output_format="mlx-safetensors", output_quantization=config["quantization"], source_weight_bytes=source_size, output_weight_bytes=target_size, model_output_manifest_digest=output_digest)
    write_json(output / "conversion.json", {"operation": "quantize", "source_model_manifest_sha256": effective["model_manifest_sha256"], "output_model_manifest": output_manifest, "output_model_manifest_digest": output_digest, "quantization": config["quantization"], "source_weight_bytes": source_size, "output_weight_bytes": target_size, "quality_acceptance": "未评定，登记可用候选前需要独立加载与固定评测", "speed_claim": "未测量，不宣称加速"})


def main():
    worker_started = time.perf_counter()
    from adapters.mlx_text.evaluation import EvaluationError, load_plan
    parser = argparse.ArgumentParser(description="GCSA AI Lab 本地 MLX 文本执行器")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, cancel_handler)
    signal.signal(signal.SIGINT, cancel_handler)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    try:
        watch_controller()
        snapshot = json.loads(args.snapshot.read_text())
        output = args.output_dir.absolute()
        if output.is_symlink() or output.resolve() != output:
            raise WorkerError("OUTPUT_SYMLINK", "输出路径不能经符号链接跳转")
        model_path, effective = validate_snapshot(snapshot, output)
        if not snapshot.get("tokenization_recipe_digest"):
            raise WorkerError("TOKENIZATION_IDENTITY_REQUIRED", "执行快照缺少提交前分词配方摘要")
        output.mkdir(parents=True, exist_ok=True)
        emit("phase", phase="loading", message="正在核对本地模型与 MLX 环境")
        before = model_manifest(model_path)
        effective["model_manifest_sha256"] = before["sha256"]
        with contextlib.redirect_stdout(sys.stderr):
            import mlx.core as mx
            from mlx_lm import load
            mx.set_default_device(mx.gpu)
            mx.random.seed(effective["seed"])
            random.seed(effective["seed"])
            if snapshot["operation"] == "generate":
                mx.reset_peak_memory()
                model_load_started = time.perf_counter()
            if snapshot["operation"] == "evaluate":
                from mlx_lm.utils import load_tokenizer
                model, tokenizer = None, load_tokenizer(str(model_path), {"trust_remote_code": False, "local_files_only": True})
            else:
                model, tokenizer = load(str(model_path), tokenizer_config={"trust_remote_code": False, "local_files_only": True})
            if snapshot.get("adapter_path") and snapshot["operation"] != "evaluate":
                if snapshot["operation"] not in {"generate", "merge"}:
                    raise WorkerError("RESUME_UNSUPPORTED", "首个训练执行器不支持增量续训")
                effective["adapter_sha256"] = load_validated_adapter(model, tokenizer, snapshot["adapter_path"], before["sha256"], snapshot["model_manifest_digest"], snapshot["adapter_training_recipe_digest"])
                effective["adapter_manifest_digest"] = snapshot["adapter_manifest_digest"]
                effective["adapter_training_recipe_digest"] = snapshot["adapter_training_recipe_digest"]
            if snapshot["operation"] == "generate":
                mx.eval(model.parameters())
                mx.synchronize()
                effective["model_load_seconds"] = time.perf_counter() - model_load_started
        from workers.mlx_lab import build_execution_recipe
        recipe, recipe_digest = build_execution_recipe(model_path, tokenizer, snapshot["operation"], effective.get("max_seq_length"))
        if not snapshot.get("tokenization_recipe_digest"):
            raise WorkerError("TOKENIZATION_IDENTITY_REQUIRED", "执行快照缺少提交前分词配方摘要")
        if snapshot["tokenization_recipe_digest"] != recipe_digest:
            raise WorkerError("TOKENIZATION_IDENTITY_CHANGED", "分词器、模板或监督实现与提交前检查不一致")
        effective["tokenization_recipe_digest"] = recipe_digest
        if snapshot.get("evaluation_kind") in {"quantized_model", "capability_comparison"}:
            from adapters.mlx_text.evaluation import model_evaluation_identity
            evaluation_recipe, evaluation_digest = model_evaluation_identity(snapshot, recipe_digest)
            if snapshot.get("effective_config", {}).get("model_evaluation_recipe_digest") != evaluation_digest:
                raise WorkerError("MODEL_EVALUATION_IDENTITY_CHANGED", "权重量化评测的代码或输入身份偏离提交前检查")
            effective.update(model_evaluation_recipe=evaluation_recipe, model_evaluation_recipe_digest=evaluation_digest)
        check_cancel()
        environment = {"python": platform.python_version(), "platform": platform.platform(), "device": mx.device_info(), "default_device": str(mx.default_device()), "pid": os.getpid(), "versions": {name: importlib.metadata.version(name) for name in ["mlx", "mlx-lm", "transformers", "tokenizers", "numpy"]}}
        write_json(output / "model-manifest.json", before)
        write_json(output / "environment.json", environment)
        with contextlib.redirect_stdout(sys.stderr):
            if snapshot["operation"] == "generate":
                run_generate(model, tokenizer, snapshot, effective, output)
            elif snapshot["operation"] == "train":
                run_train(model, tokenizer, snapshot, effective, output)
            elif snapshot["operation"] in {"merge", "distill"}:
                from workers.mlx_lab import run_merge, run_distill
                (run_merge if snapshot["operation"] == "merge" else run_distill)(model, tokenizer, snapshot, effective, output)
            elif snapshot["operation"] == "quantize":
                run_quantize(model, model_path, effective, output)
            else:
                from workers.mlx_evaluate_worker import run_evaluate
                run_evaluate(snapshot, effective, output, emit, check_cancel)
        if model_manifest(model_path) != before:
            raise WorkerError("SOURCE_MODEL_CHANGED", "执行期间源模型摘要发生变化，拒绝登记完成")
        verify_snapshot_manifest(model_path, snapshot["model_manifest"], snapshot["model_manifest_digest"], "MODEL")
        if snapshot["operation"] in {"train", "distill"}:
            verify_snapshot_manifest(Path(snapshot["dataset_path"]), snapshot["dataset_manifest"], snapshot["dataset_manifest_digest"], "DATASET")
        if snapshot.get("adapter_path"):
            verify_snapshot_manifest(Path(snapshot["adapter_path"]), snapshot["adapter_manifest"], snapshot["adapter_manifest_digest"], "ADAPTER")
        if snapshot.get("candidate_model_path"):
            verify_snapshot_manifest(Path(snapshot["candidate_model_path"]), snapshot["candidate_model_manifest"], snapshot["candidate_model_manifest_digest"], "CANDIDATE_MODEL")
        if snapshot.get("evaluation_plan_digest"):
            load_plan(snapshot)
        check_cancel()
        if snapshot["operation"] == "generate":
            metrics_path = output / "metrics.json"
            metrics = json.loads(metrics_path.read_text())
            metrics.update(model_load_seconds=effective["model_load_seconds"], worker_wall_seconds=time.perf_counter() - worker_started,
                           worker_wall_scope="worker main 入口到来源复核完成；不含 Python 启动与末尾输出写盘/进程退出。完整进程墙钟以控制端记录为准。")
            write_json(metrics_path, metrics)
        write_json(output / "effective-config.json", effective)
        artifacts = [{"path": str(p.relative_to(output)), "sha256": sha256(p), "media_type": "application/json" if p.suffix == ".json" else "text/plain" if p.suffix == ".txt" else "application/octet-stream"} for p in sorted(output.rglob("*")) if p.is_file()]
        emit("completed", artifacts=artifacts, effective_config=effective, source_model_unchanged=True)
        return 0
    except (WorkerError, RecipeError, EvaluationError, CheckpointError, InferenceError, GenerationError) as exc:
        emit("error", code=exc.code, message=str(exc))
        return 130 if exc.code == "CANCELLED" else 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        emit("error", code="EXECUTION_FAILED", message="执行失败，请检查环境、模型和诊断日志", exception_type=type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.modules["workers.mlx_worker"] = sys.modules[__name__]
    raise SystemExit(main())
