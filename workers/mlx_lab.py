"""本地模型实验：LoRA 融合与离线回答蒸馏，产物需独立加载后才完成。"""

import hashlib
import contextlib
import json
from pathlib import Path
import shutil
import time


def build_execution_recipe(model_path, tokenizer, operation, max_seq_length):
    from adapters.mlx_text.recipe import build_recipe
    if operation not in {"merge", "distill"}:
        return build_recipe(model_path, tokenizer, operation, max_seq_length)
    recipe, source_digest = build_recipe(model_path, tokenizer, "train" if operation == "distill" else "quantize", max_seq_length)
    recipe.update(recipe_id="qwen25-offline-distillation-v1" if operation == "distill" else "qwen25-lora-fusion-v1", lab_implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if operation == "distill":
        recipe["source_dataset_tokenization_recipe_digest"] = source_digest
    return recipe, hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()


def save_weights(model, source, destination):
    """保持源模型配置与分词器，分片写入独立目录。"""
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from mlx_lm.utils import save_model
    from workers.mlx_worker import check_cancel
    destination.mkdir()
    check_cancel()
    weights = dict(tree_flatten(model.parameters()))
    mx.eval(weights)
    save_model(destination, model, donate_model=False)
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja", "generation_config.json", "LICENSE", "README.md"):
        if (source / name).is_file():
            shutil.copyfile(source / name, destination / name)


def fuse(model, weight):
    from mlx.utils import tree_unflatten
    from mlx_lm.tuner.lora import LoRALinear
    modules = []
    for name, layer in model.named_modules():
        if isinstance(layer, LoRALinear):
            layer.scale *= weight
            modules.append((name, layer.fuse()))
    if not modules:
        from workers.mlx_worker import WorkerError
        raise WorkerError("ADAPTER_MODULE_MISSING", "没有可融合的 LoRA 层")
    model.update_modules(tree_unflatten(modules))
    model.eval()
    return len(modules)


def logits(model, tokenizer, prompt):
    import mlx.core as mx
    tokens = tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=True, add_generation_prompt=True)
    result = model(mx.array([tokens]))[:, -1, :].astype(mx.float32)
    mx.eval(result)
    return result


def independent_check(model, tokenizer, source, output):
    import mlx.core as mx
    from mlx_lm import load
    from workers.mlx_worker import WorkerError, check_cancel
    prompts = ["只回复数字：2加3等于几？", "把 hello 翻译成中文。", "用一句话描述蓝色的天空。"]
    expected = [logits(model, tokenizer, prompt) for prompt in prompts]
    loaded, loaded_tokenizer = load(str(output), tokenizer_config={"trust_remote_code": False, "local_files_only": True})
    checks = []
    for prompt, reference in zip(prompts, expected):
        check_cancel()
        actual = logits(loaded, loaded_tokenizer, prompt)
        error = float(mx.max(mx.abs(actual - reference)).item())
        if not bool(mx.all(mx.isfinite(actual)).item()) or error > 0.25:
            raise WorkerError("MERGE_NUMERICAL_MISMATCH", "独立模型与融合前计算的数值差异超过 0.25")
        checks.append({"prompt": prompt, "max_abs_logit_error": error, "reference_next_token": int(mx.argmax(reference).item()), "output_next_token": int(mx.argmax(actual).item())})
    del loaded
    mx.clear_cache()
    return {"passed": True, "engine": "mlx", "device": "apple-gpu", "max_abs_logit_tolerance": 0.25, "samples": checks, "scope": "固定样例的独立加载与末位置 logits；不是通用质量验收"}


def finish_model(model, tokenizer, snapshot, effective, output, operation, details, reference=None):
    from workers.mlx_worker import snapshot_manifest, write_json, emit
    source = Path(snapshot["model_path"])
    destination = output / "model"
    save_weights(model, source, destination)
    emit("phase", phase="verifying", message="正在独立加载新权重并核对数值")
    verification = independent_check(reference or model, tokenizer, source, destination)
    manifest, identity = snapshot_manifest(destination)
    source_bytes = sum(item["size"] for item in snapshot["model_manifest"] if item["path"].endswith(".safetensors"))
    output_bytes = sum(item["size"] for item in manifest if item["path"].endswith(".safetensors"))
    effective.update(model_output_manifest_digest=identity, source_weight_bytes=source_bytes, output_weight_bytes=output_bytes, independent_use="verified")
    write_json(output / "conversion.json", {"operation": operation, "source_model_manifest_sha256": effective["model_manifest_sha256"], "source_model_manifest_digest": snapshot["model_manifest_digest"], "output_model_manifest": manifest, "output_model_manifest_digest": identity, "source_weight_bytes": source_bytes, "output_weight_bytes": output_bytes, "verification": verification, "details": details, "quality_acceptance": "未评定"})


def run_merge(model, tokenizer, snapshot, effective, output):
    import mlx.core as mx
    from mlx_lm.tuner.lora import LoRALinear
    from workers.mlx_worker import emit
    weight = effective["merge_weight"]
    # 先计算带权适配器参考，再进行不可逆的内存融合。
    for _, layer in model.named_modules():
        if isinstance(layer, LoRALinear):
            layer.scale *= weight
    prompts = ["只回复数字：2加3等于几？", "把 hello 翻译成中文。", "用一句话描述蓝色的天空。"]
    reference = [logits(model, tokenizer, prompt) for prompt in prompts]
    emit("phase", phase="merging", message="正在将适配器融合到独立基座副本")
    count = fuse(model, 1.0)
    # 融合前后对照与磁盘重新加载对照分别记录。
    errors = [float(mx.max(mx.abs(logits(model, tokenizer, prompt) - expected)).item()) for prompt, expected in zip(prompts, reference)]
    if any(error > 0.25 for error in errors):
        from workers.mlx_worker import WorkerError
        raise WorkerError("MERGE_NUMERICAL_MISMATCH", "融合前后数值差异超过 0.25")
    finish_model(model, tokenizer, snapshot, effective, output, "merge", {"method": "base_plus_lora", "merge_weight": weight, "adapter_manifest_digest": snapshot["adapter_manifest_digest"], "fused_layers": count, "fusion_max_abs_errors": errors})


def distillation_prompts(snapshot):
    from workers.mlx_worker import WorkerError
    rows = []
    for line in Path(snapshot["dataset_path"]).read_text().splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        messages = value.get("messages", [])
        roles = [item.get("role") for item in messages]
        if roles not in (["user", "assistant"], ["system", "user", "assistant"]) or set(value) != {"messages"}:
            raise WorkerError("DISTILL_DATA_UNSUPPORTED", "离线蒸馏需要单轮 SFT 数据，可带系统消息；原助手回答仅用于保留来源，不用于教师监督")
        if any(set(item) != {"role", "content"} or not isinstance(item["content"], str) or not item["content"].strip() for item in messages):
            raise WorkerError("DISTILL_DATA_UNSUPPORTED", "蒸馏样本必须是非空纯文本消息")
        rows.append(messages[:-1])
    if not 1 <= len(rows) <= 64:
        raise WorkerError("DISTILL_BUDGET", "本地离线蒸馏每次接受 1—64 个完整样本，不会截断数据")
    return rows


def observe_generation(model, tokenizer, training_prompts):
    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler
    from workers.mlx_worker import check_cancel
    # 固定对照问题可能与用户数据重合，逐条记录；不冒充独立评测集。
    cases = [("只回复数字：2加3等于几？", "5"), ("把 hello 翻译成中文，只输出译文。", "你好"), ("只回复数字：10减3等于几？", "7")]
    observations = []
    for prompt, expected in cases:
        check_cancel(); tokens = tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=True, add_generation_prompt=True)
        started = time.perf_counter(); chunks = []; count = 0
        with contextlib.closing(stream_generate(model, tokenizer, tokens, max_tokens=16, sampler=make_sampler(temp=0))) as responses:
            for response in responses:
                check_cancel(); chunks.append(response.text); count = response.generation_tokens
        elapsed = time.perf_counter() - started; text = "".join(chunks)
        observations.append({"prompt": prompt, "expected": expected, "output": text, "exact_match": text.strip() == expected, "training_prompt_overlap": any(message["role"] == "user" and message["content"].strip() == prompt for messages in training_prompts for message in messages), "generation_tokens": count, "seconds": elapsed, "tokens_per_second": count / elapsed})
    return observations


def run_distill(model, tokenizer, snapshot, effective, output):
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    from workers.mlx_worker import WorkerError, check_cancel, emit, run_train, snapshot_manifest, verify_snapshot_manifest, write_json
    teacher_ref = snapshot["teacher"]
    prompts = distillation_prompts(snapshot)
    emit("phase", phase="teacher_generation", message="本地教师正在生成固定监督回答")
    teacher, teacher_tokenizer = load(teacher_ref["path"], tokenizer_config={"trust_remote_code": False, "local_files_only": True})
    teacher_observations = observe_generation(teacher, teacher_tokenizer, prompts)
    student_before = observe_generation(model, tokenizer, prompts)
    rows, timings, terminations = [], [], []
    for index, messages in enumerate(prompts, 1):
        check_cancel()
        tokens = teacher_tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        if len(tokens) + effective["teacher_max_tokens"] > 2048:
            raise WorkerError("CONTEXT_TOO_LONG", "教师样本超出固定 2048 词元预算")
        started = time.perf_counter()
        chunks = []; last_response = None
        with contextlib.closing(stream_generate(teacher, teacher_tokenizer, tokens, max_tokens=effective["teacher_max_tokens"], sampler=make_sampler(temp=0))) as responses:
            for response in responses:
                check_cancel()
                chunks.append(response.text); last_response = response
        terminations.append({"finish_reason": getattr(last_response, "finish_reason", None), "generation_tokens": getattr(last_response, "generation_tokens", 0)})
        answer = "".join(chunks)
        if not answer.strip():
            raise WorkerError("TEACHER_EMPTY", "教师产生空回答，本次蒸馏停止")
        rows.append({"messages": messages + [{"role": "assistant", "content": answer}]})
        timings.append(time.perf_counter() - started)
        emit("metric", teacher_samples=index, total_samples=len(prompts))
    del teacher
    mx.clear_cache()
    verify_snapshot_manifest(Path(teacher_ref["path"]), teacher_ref["manifest"], teacher_ref["manifest_digest"], "TEACHER")
    data = output / "teacher-data.jsonl"
    data.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    generated_manifest, generated_digest = snapshot_manifest(data)
    from adapters.mlx_text.recipe import check_dataset
    samples, report = check_dataset(tokenizer, data, effective["max_seq_length"], check_cancel)
    if len(samples) != len(rows):
        write_json(output / "teacher-data-check.json", report)
        raise WorkerError("DISTILL_DATA_REJECTED", "教师回答不能完整用于学生训练；请调整长度后新建任务，不会悄悄丢弃样本")
    training_snapshot = {**snapshot, "dataset_path": str(data), "dataset_manifest": generated_manifest, "dataset_manifest_digest": generated_digest}
    run_train(model, tokenizer, training_snapshot, effective, output)
    fuse(model, 1.0)
    student_after = observe_generation(model, tokenizer, prompts)
    common_bytes = lambda manifest: sum(item["size"] for item in manifest if item["path"].endswith(".safetensors"))
    write_json(output / "distillation-comparison.json", {"teacher": teacher_observations, "student_before": student_before, "student_after": student_after, "teacher_weight_bytes": common_bytes(teacher_ref["manifest"]), "student_source_weight_bytes": common_bytes(snapshot["model_manifest"]), "scope": "3 个固定对照样例、16 词元贪心输出；记录与训练提示词的精确重合，未检测语义近似。计时不含加载，精确匹配和吞吐不代表整体质量或加速保证。"})
    details = {"method": "offline_response_sft", "loss": "assistant_content_and_im_end_cross_entropy", "teacher": {key: value for key, value in teacher_ref.items() if key not in {"path", "manifest"}}, "teacher_sampling": {"temperature": 0, "max_tokens": effective["teacher_max_tokens"]}, "samples": len(rows), "teacher_seconds": timings, "teacher_terminations": terminations, "generated_dataset_digest": generated_digest, "source_dataset_digest": snapshot["dataset_manifest_digest"], "remote_requests": 0, "student_steps": effective["steps"]}
    write_json(output / "distillation.json", details)
    finish_model(model, tokenizer, snapshot, effective, output, "distill", details)
