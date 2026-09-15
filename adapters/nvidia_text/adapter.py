"""NVIDIA 固定组合的文件/参数边界与实际运行，不提供 CPU 回退。"""

import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
import time

from ailab_control.remote.protocol import ProtocolError, digest, file_hash, hex_digest, integer, strict_keys, bound_transport
from adapters.mlx_text.generation import GenerationError, StopBuffer, prepare_prompt, resolve as generation_fields
from adapters.mlx_text.recipe import RECIPE_ID, TEMPLATE_SHA256, RecipeError, build_recipe, check_dataset, collate_samples

ADAPTER_ID = "nvidia-text"
MODEL_DIGEST = "a9b08fa2b761cbfc7335b28c6b0997b6e7713893aaca4b215625ffc99a1d36b3"
MODEL_FILES = {"LICENSE", "README.md", "config.json", "generation_config.json", "merges.txt", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "vocab.json"}
VERSIONS = {"torch": "2.10.0", "transformers": "4.57.6", "peft": "0.18.1", "accelerate": "1.12.0", "safetensors": "0.7.0", "numpy": "2.4.2"}
OUTPUT_RESERVE_BYTES = {"generate": 4 * 1024**2, "train": 64 * 1024**2}


def output_reserve_bytes(snapshot):
    validate_snapshot(snapshot)
    return OUTPUT_RESERVE_BYTES[snapshot["operation"]]


def number(value, low, high):
    if type(value) not in {int, float} or not math.isfinite(value) or not low <= value <= high:
        raise ProtocolError("INVALID_CONFIG", "运行参数必须是范围内有限数值。")
    return value


def validate_snapshot(snapshot):
    """供同一远端协议在接单前调用，完全不加载模型或设备。"""
    strict_keys(snapshot, {"schema_version", "attempt_id", "executor_id", "adapter_id", "operation", "inputs", "input", "runtime"}, {"transport"})
    bound_transport(snapshot)
    if snapshot["schema_version"] != 1 or snapshot["adapter_id"] != ADAPTER_ID or snapshot["operation"] not in {"generate", "train"}:
        raise ProtocolError("ADAPTER_UNAVAILABLE", "NVIDIA 首期只开放固定文本生成与 SFT + LoRA。", 409)
    for key in ("attempt_id", "executor_id"):
        if not isinstance(snapshot[key], str) or not re.fullmatch(key.removesuffix("_id") + r"-[0-9a-f]{32}", snapshot[key]):
            raise ProtocolError("INVALID_IDENTIFIER", "远端执行身份格式错误。")
    files = snapshot["inputs"]
    if not isinstance(files, list) or not 9 <= len(files) <= 12:
        raise ProtocolError("INPUT_LIMIT", "固定组合需要完整模型文件与有界训练/评测文件。")
    paths = set()
    for item in files:
        strict_keys(item, {"path", "sha256", "size"}); hex_digest(item["sha256"]); integer(item["size"], 0, 2 * 1024**3)
        path = item["path"]
        if not isinstance(path, str) or path in paths or path not in {"model/" + name for name in MODEL_FILES} | {"data/train.jsonl", "evaluation/evaluation.jsonl", "evaluation/criteria.json"}:
            raise ProtocolError("UNSAFE_INPUT_PATH", "输入路径重复、越界或不属于固定模型/训练文件。")
        if not path.startswith("model/") and item["size"] > 4 * 1024**2:
            raise ProtocolError("INPUT_LIMIT", "训练和评测文件各不能超过 4 MiB。")
        paths.add(path)
    model_entries = sorted([{**item, "path": item["path"].removeprefix("model/")} for item in files if item["path"].startswith("model/")], key=lambda item: item["path"])
    if {item["path"] for item in model_entries} != MODEL_FILES or digest(model_entries) != MODEL_DIGEST:
        raise ProtocolError("MODEL_UNVERIFIED", "模型文件不属于已固定的 Qwen2.5-0.5B-Instruct 原权重。", 409)
    inputs, runtime = snapshot["input"], snapshot["runtime"]
    common = {"engine", "device_id", "precision", "seed"}
    if snapshot["operation"] == "generate":
        strict_keys(inputs, {"prompt", "model_manifest_digest", "source_code_digest"})
        strict_keys(runtime, common | {"max_tokens", "temperature", "top_p"}, {"context_limit", "overflow", "stop", "stream", "thinking"})
        if len(paths) != 9 or not isinstance(inputs["prompt"], str) or not inputs["prompt"].strip() or len(inputs["prompt"]) > 16000:
            raise ProtocolError("INVALID_PROMPT", "生成只接受完整模型和一条有界文本输入。")
        integer(runtime["max_tokens"], 1, 512); number(runtime["temperature"], 0, 2); number(runtime["top_p"], 0.01, 1)
        try: effective = {**runtime, **generation_fields(runtime)}
        except GenerationError as error: raise ProtocolError(error.code, str(error)) from error
    else:
        strict_keys(inputs, {"model_manifest_digest", "dataset_manifest_digest", "source_code_digest"}, {"evaluation_plan_digest", "evaluation_plan_created_at", "submitted_at"})
        strict_keys(runtime, common | {"steps", "batch_size", "learning_rate", "max_seq_length", "lora_rank", "lora_alpha", "num_layers"})
        integer(runtime["steps"], 1, 512); integer(runtime["batch_size"], 1, 1); number(runtime["learning_rate"], 1e-6, 1e-2)
        integer(runtime["max_seq_length"], 32, 2048); integer(runtime["lora_rank"], 1, 32); integer(runtime["lora_alpha"], 1, 128); integer(runtime["num_layers"], 1, 24)
        if paths - {"model/" + name for name in MODEL_FILES} not in ({"data/train.jsonl"}, {"data/train.jsonl", "evaluation/evaluation.jsonl", "evaluation/criteria.json"}):
            raise ProtocolError("DATASET_REQUIRED", "SFT + LoRA 需要固定训练文件；评测问题与规则必须同时提供。")
        data = [{**item, "path": "train.jsonl"} for item in files if item["path"] == "data/train.jsonl"]
        if inputs["dataset_manifest_digest"] != digest(data): raise ProtocolError("DATASET_IDENTITY_CHANGED", "训练集摘要不一致。", 409)
        plan_files = "evaluation/evaluation.jsonl" in paths
        if bool(inputs.get("evaluation_plan_digest")) != plan_files or (plan_files and set(inputs) != {"model_manifest_digest", "dataset_manifest_digest", "source_code_digest", "evaluation_plan_digest", "evaluation_plan_created_at", "submitted_at"}):
            raise ProtocolError("EVALUATION_PLAN_REQUIRED", "训练前质量方案需要完整数据、规则与时间身份。")
        if plan_files:
            from datetime import datetime
            hex_digest(inputs["evaluation_plan_digest"])
            try:
                created = datetime.fromisoformat(inputs["evaluation_plan_created_at"]); submitted = datetime.fromisoformat(inputs["submitted_at"])
                if not created.tzinfo or not submitted.tzinfo or created > submitted: raise ValueError()
            except (ValueError, TypeError): raise ProtocolError("POSTHOC_EVALUATION", "训练前评测方案的时间身份无效。") from None
        effective = dict(runtime)
    if inputs["model_manifest_digest"] != MODEL_DIGEST or runtime["engine"] != "transformers" or runtime["device_id"] != "cuda:0" or runtime["precision"] != "bfloat16":
        raise ProtocolError("UNSUPPORTED_COMBINATION", "当前 NVIDIA 组合固定为 Transformers／cuda:0／BF16 原权重。", 409)
    if inputs["source_code_digest"] != source_identity(): raise ProtocolError("ADAPTER_SOURCE_CHANGED", "适配器代码已偏离已选环境身份，请重新探测并检查。", 409)
    integer(runtime["seed"], 0, 2**32 - 1)
    return effective


def probe():
    versions = {}
    for package in VERSIONS:
        try: versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package] = None
    result = {"adapter_id": ADAPTER_ID, "ready": False, "source_code_digest": source_identity(), "validation_scope": "runtime_probe_only", "model_acceptance": "not_verified", "hardware_acceptance": "not_verified", "platform": sys.platform, "python": sys.version.split()[0], "versions": versions, "required_versions": VERSIONS, "required_cuda": "12.8", "devices": [], "blocking": []}
    if not sys.platform.startswith("linux"): result["blocking"].append({"code": "NVIDIA_LINUX_REQUIRED", "message": "此执行器只在明确 NVIDIA Linux 环境运行，本机不做 CPU/Apple 回退。"})
    if any((version or "").split("+")[0] != VERSIONS[name] for name, version in versions.items()): result["blocking"].append({"code": "ENVIRONMENT_VERSION_MISMATCH", "message": "执行依赖与固定版本不一致。"})
    if result["blocking"]: return result
    try:
        import torch
        result["cuda_runtime"] = torch.version.cuda
        if torch.version.cuda != "12.8" or not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise ProtocolError("CUDA_UNAVAILABLE", "CUDA 12.8 或 NVIDIA 设备不可用。")
        torch.cuda.set_device(0)
        properties = torch.cuda.get_device_properties(0)
        result["devices"] = [{"id": "cuda:0", "name": properties.name, "total_memory_bytes": properties.total_memory, "capability": list(torch.cuda.get_device_capability(0)), "bf16_supported": bool(torch.cuda.is_bf16_supported())}]
        if not torch.cuda.is_bf16_supported() or properties.total_memory < 8 * 1024**3:
            raise ProtocolError("CUDA_CAPACITY_UNSUPPORTED", "固定组合需要 BF16 支持与至少 8 GiB 显存。")
        sample = torch.ones((2, 2), dtype=torch.bfloat16, device="cuda:0")
        tested = sample @ sample; torch.cuda.synchronize()
        if tested.float().sum().item() != 8: raise ProtocolError("CUDA_PROBE_FAILED", "设备实际计算探测不一致。")
        del tested, sample; torch.cuda.empty_cache(); torch.cuda.synchronize()
        result["probe_allocation_released"] = torch.cuda.memory_allocated(0) == 0
        if not result["probe_allocation_released"]: raise ProtocolError("CUDA_PROBE_NOT_RELEASED", "探测进程仍有未释放的张量分配。")
        result["ready"] = True
    except Exception as error:
        result["blocking"].append({"code": error.code if isinstance(error, ProtocolError) else "CUDA_PROBE_FAILED", "message": str(error) if isinstance(error, ProtocolError) else "CUDA 实际探测失败。"})
    return result


def read_inputs(snapshot, input_dir, check_cancel=lambda: None):
    effective = validate_snapshot(snapshot)
    root = Path(input_dir)
    if not root.is_absolute() or root.is_symlink() or root.resolve() != root or not root.is_dir():
        raise ProtocolError("UNSAFE_INPUT_DIRECTORY", "模型输入必须位于执行服务冻结的独立目录。")
    expected = {item["path"] for item in snapshot["inputs"]}
    all_entries = list(root.rglob("*"))
    if any(path.is_symlink() or (not path.is_file() and not path.is_dir()) for path in all_entries) or {path.relative_to(root).as_posix() for path in all_entries if path.is_file()} != expected:
        raise ProtocolError("INPUT_CHANGED", "冻结输入目录的完整文件集合不一致。", 409)
    for item in snapshot["inputs"]:
        check_cancel(); path = root / item["path"]
        if path.stat().st_size != item["size"] or file_hash(path) != item["sha256"]:
            raise ProtocolError("INPUT_CHANGED", "模型或数据文件与上传清单不一致。", 409)
    from ailab_control.assets import model_manifest
    actual = model_manifest(root / "model")
    if actual["manifest_digest"] != MODEL_DIGEST or actual["model_config"].get("quantization") or actual["model_config"].get("quantization_config"):
        raise ProtocolError("MODEL_UNVERIFIED", "只允许已固定且通过受限格式检查的原权重。")
    return effective, actual


def prepare(snapshot, input_dir, check_cancel=lambda: None):
    effective, actual = read_inputs(snapshot, input_dir, check_cancel)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(Path(input_dir) / "model"), trust_remote_code=False, local_files_only=True)
    if hashlib.sha256(tokenizer.chat_template.encode()).hexdigest() != TEMPLATE_SHA256:
        raise ProtocolError("TOKENIZER_UNVERIFIED", "聊天模板与固定模型不一致。")
    recipe, identity = build_recipe(Path(input_dir) / "model", tokenizer, snapshot["operation"], effective.get("max_seq_length"))
    effective.update(tokenization_recipe=recipe, tokenization_recipe_digest=identity, model_manifest_digest=MODEL_DIGEST, source_code_digest=source_identity(), packing=False)
    prepared = {"tokenizer": tokenizer, "model": actual}
    if snapshot["operation"] == "generate":
        try: prepared["prompt"], prepared["check_report"] = prepare_prompt(tokenizer, snapshot["input"], effective)
        except GenerationError as error: raise ProtocolError(error.code, str(error)) from error
    else:
        try: prepared["samples"], prepared["check_report"] = check_dataset(tokenizer, Path(input_dir) / "data/train.jsonl", effective["max_seq_length"], check_cancel)
        except RecipeError as error: raise ProtocolError(error.code, str(error)) from error
        if not prepared["samples"]: raise ProtocolError("NO_TRAINABLE_DATA", "没有完整有效的助手监督样本。")
        if snapshot["input"].get("evaluation_plan_digest"):
            from adapters.mlx_text.evaluation import load_plan
            from ailab_control.evaluation import normalized_prompt
            plan = {"evaluation_plan_digest": snapshot["input"]["evaluation_plan_digest"]}
            for kind, filename in (("dataset", "evaluation.jsonl"), ("criteria", "criteria.json")):
                item = next(item for item in snapshot["inputs"] if item["path"] == "evaluation/" + filename)
                entries = [{**item, "path": filename}]
                plan.update({f"evaluation_{kind}_manifest": entries, f"evaluation_{kind}_manifest_digest": digest(entries), f"evaluation_{kind}_path": str(Path(input_dir) / "evaluation" / filename)})
            rows, _, _ = load_plan(plan)
            prompts = {normalized_prompt(row["prompt"]) for row in rows}
            for line in (Path(input_dir) / "data/train.jsonl").read_text().splitlines():
                if line.strip() and any(normalized_prompt(item["content"]) in prompts for item in json.loads(line)["messages"] if item["role"] == "user"):
                    raise ProtocolError("DATASET_EVALUATION_OVERLAP", "训练问题与预先冻结的评测问题重复。")
    return effective, prepared


def _disk_source_identity():
    root = Path(__file__).resolve().parents[2]
    return digest({name: file_hash(root / name) for name in ("adapters/nvidia_text/adapter.py", "workers/nvidia_worker.py", "adapters/mlx_text/recipe.py", "adapters/mlx_text/generation.py", "adapters/mlx_text/evaluation.py")})


_LOADED_SOURCE_IDENTITY = _disk_source_identity()


def source_identity():
    if _disk_source_identity() != _LOADED_SOURCE_IDENTITY:
        raise ProtocolError('ADAPTER_SOURCE_CHANGED', '适配器源码在当前进程启动后发生变化，请重新启动执行服务。', 409)
    return _LOADED_SOURCE_IDENTITY


def validate_completion(snapshot, effective, artifacts, output_dir=None):
    """共同完成门槛；先核参数与必需产物，收到文件后再核实际报告正文。"""
    expected = validate_snapshot(snapshot)
    if not isinstance(effective, dict) or any(key not in effective for key in expected) or digest({key: effective[key] for key in expected}) != digest(expected):
        raise ProtocolError('NVIDIA_COMPLETION_CONFIG_MISMATCH', '实际引擎、设备、精度或运行参数与冻结请求不一致。', 409)
    root = Path(__file__).resolve().parents[2]
    tokenizer_files = {item['path'].removeprefix('model/'): item['sha256'] for item in snapshot['inputs'] if item['path'] in {'model/' + name for name in ('tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt', 'chat_template.jinja')}}
    recipe = {'recipe_id': RECIPE_ID if snapshot['operation'] == 'train' else 'qwen25-generation-v1', 'tokenizer_files': tokenizer_files,
              'template_sha256': TEMPLATE_SHA256, 'max_seq_length': expected.get('max_seq_length'), 'packing': False,
              'supervision': 'assistant_content_and_im_end' if snapshot['operation'] == 'train' else None,
              'recipe_implementation_sha256': file_hash(root / 'adapters/mlx_text/recipe.py')}
    recipe_digest = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
    if (effective.get('model_manifest_digest') != MODEL_DIGEST or effective.get('source_code_digest') != source_identity()
            or effective.get('tokenization_recipe') != recipe or effective.get('tokenization_recipe_digest') != recipe_digest
            or effective.get('input_unchanged') is not True):
        raise ProtocolError('NVIDIA_COMPLETION_IDENTITY_MISMATCH', '完成结果的模型、代码、分词配方或输入完整性身份不一致。', 409)
    required = {'environment.json', 'input-check.json', 'effective-config.json', 'metrics.json'}
    required |= {'result.txt'} if snapshot['operation'] == 'generate' else {'peft-adapter/adapter_model.safetensors', 'peft-adapter/adapter_config.json', 'mlx-adapter/adapters.safetensors', 'mlx-adapter/adapter_config.json', 'adapter-conversion.json'}
    names = [item.get('name', item.get('path')) for item in artifacts] if isinstance(artifacts, list) and all(isinstance(item, dict) for item in artifacts) else []
    if len(names) != len(required) or not all(isinstance(name, str) for name in names) or set(names) != required:
        raise ProtocolError('NVIDIA_COMPLETION_ARTIFACTS_MISSING', '完成清单未包含本次操作的全部固定产物。', 409)
    if output_dir is None:
        return True
    output = Path(output_dir)
    def report(name):
        path = output / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024**2:
            raise ProtocolError('NVIDIA_COMPLETION_REPORT_INVALID', '实际报告不是有界常规文件。', 409)
        def pairs(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise ValueError()
                value[key] = item
            return value
        try:
            return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (OSError, ValueError, UnicodeError):
            raise ProtocolError('NVIDIA_COMPLETION_REPORT_INVALID', '实际报告不是严格 JSON。', 409) from None
    actual = report('effective-config.json')
    if digest(actual) != digest(effective):
        raise ProtocolError('NVIDIA_COMPLETION_REPORT_MISMATCH', '实际配置文件与完成事件不一致。', 409)
    environment, metrics = report('environment.json'), report('metrics.json')
    if (not isinstance(environment, dict) or environment.get('ready') is not True or environment.get('source_code_digest') != source_identity()
            or not str(environment.get('platform', '')).startswith('linux') or environment.get('cuda_runtime') != '12.8'
            or not isinstance(metrics, dict) or metrics.get('compute_device') != 'cuda:0'):
        raise ProtocolError('NVIDIA_COMPLETION_DEVICE_MISMATCH', '实际环境或计算指标未确认所选 NVIDIA 设备。', 409)
    if snapshot['operation'] == 'train':
        mlx, conversion = report('mlx-adapter/adapter_config.json'), report('adapter-conversion.json')
        if (not isinstance(mlx, dict) or mlx.get('base_input_manifest_digest') != MODEL_DIGEST or mlx.get('training_recipe_digest') != recipe_digest
                or mlx.get('evaluation_plan_digest') != snapshot['input'].get('evaluation_plan_digest')
                or not isinstance(conversion, dict) or conversion.get('source_attempt_id') != snapshot['attempt_id']
                or conversion.get('source_executor_id') != snapshot['executor_id'] or conversion.get('source_model_manifest_digest') != MODEL_DIGEST
                or conversion.get('source_sha256') != file_hash(output / 'peft-adapter/adapter_model.safetensors')
                or conversion.get('output_sha256') != file_hash(output / 'mlx-adapter/adapters.safetensors')):
            raise ProtocolError('NVIDIA_ADAPTER_PROVENANCE_MISMATCH', '适配器转换文件未绑定本次执行和固定基座。', 409)
    return True


def generate(model, tokenizer, prompt, effective, emit, check_cancel):
    """实际 token 循环；CPU 组件测试可直接调用，公共执行入口仍强制 CUDA。"""
    import torch
    device = next(model.parameters()).device
    generator = torch.Generator(device=device); generator.manual_seed(effective["seed"])
    inputs = torch.tensor([prompt], dtype=torch.long, device=device)
    cache, generated, decoded, visible = None, [], "", ""
    stop = StopBuffer(effective["stop"])
    eos = set(model.generation_config.eos_token_id if isinstance(model.generation_config.eos_token_id, list) else [model.generation_config.eos_token_id])
    started, first_token, reason = time.perf_counter(), None, "max_tokens"
    with torch.inference_mode():
        for _ in range(effective["max_tokens"]):
            check_cancel()
            result = model(input_ids=inputs, past_key_values=cache, use_cache=True, return_dict=True)
            cache, logits = result.past_key_values, result.logits[0, -1].float()
            if not torch.isfinite(logits).all().item(): raise ProtocolError("NONFINITE_LOGITS", "生成值非有限数，停止执行。")
            if effective["temperature"] == 0: token = int(logits.argmax().item())
            else:
                values, indices = torch.sort(logits / effective["temperature"], descending=True)
                probabilities = torch.softmax(values, dim=-1)
                remove = probabilities.cumsum(-1) - probabilities > effective["top_p"]
                probabilities = probabilities.masked_fill(remove, 0)
                token = int(indices[torch.multinomial(probabilities, 1, generator=generator)].item())
            if first_token is None: first_token = time.perf_counter() - started
            if token in eos:
                reason = "eos"; break
            generated.append(token)
            current = tokenizer.decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=False).rstrip("\ufffd")
            if not current.startswith(decoded): raise ProtocolError("STREAM_DECODE_CHANGED", "分词解码前缀不稳定，停止本次执行。")
            chunk = stop.feed(current[len(decoded):]); decoded = current; visible += chunk
            if effective["stream"] and chunk: emit("token", {"text": chunk})
            if stop.stopped: reason = "stop_sequence"; break
            inputs = torch.tensor([[token]], dtype=torch.long, device=device)
        if not stop.stopped:
            final = tokenizer.decode(generated, skip_special_tokens=True, clean_up_tokenization_spaces=False)
            if not final.startswith(decoded): raise ProtocolError("STREAM_DECODE_CHANGED", "最终解码与已保存前缀不同。")
            chunk = stop.feed(final[len(decoded):]); visible += chunk
            if effective["stream"] and chunk: emit("token", {"text": chunk})
            if stop.stopped: reason = "stop_sequence"
        if not stop.stopped:
            chunk = stop.finish(); visible += chunk
            if effective["stream"] and chunk: emit("token", {"text": chunk})
    metrics = {"prompt_tokens": len(prompt), "generated_tokens": len(generated), "first_token_seconds": first_token, "generation_seconds": time.perf_counter() - started, "finish_reason": reason, "matched_stop_index": stop.matched_index, "cross_request_cache_reuse": False, "cache_class": type(cache).__name__, "compute_device": str(device)}
    del result, cache, logits, inputs
    return visible, metrics


def train(model, tokenizer, samples, effective, emit, check_cancel):
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from peft.utils import get_peft_model_state_dict
    layers = list(range(24 - effective["num_layers"], 24))
    config = LoraConfig(task_type=TaskType.CAUSAL_LM, r=effective["lora_rank"], lora_alpha=effective["lora_alpha"], lora_dropout=0, bias="none", target_modules=["q_proj", "v_proj"], layers_to_transform=layers, layers_pattern="layers", use_rslora=False, use_dora=False)
    model = get_peft_model(model, config); model.config.use_cache = False; model.train()
    trainable = {name: parameter for name, parameter in model.named_parameters() if parameter.requires_grad}
    if not trainable or any(".lora_A." not in name and ".lora_B." not in name for name in trainable): raise ProtocolError("TRAINABLE_MODULES_INVALID", "实际可训练参数不全为固定 LoRA。")
    if any(parameter.dtype != torch.float32 for parameter in trainable.values()): raise ProtocolError("TRAINING_PRECISION_MISMATCH", "固定 LoRA 可训练参数必须为 FP32。")
    initial = {name: parameter.detach().float().cpu().clone() for name, parameter in trainable.items()}
    optimizer = torch.optim.AdamW(list(trainable.values()), lr=effective["learning_rate"], betas=(0.9, 0.999), eps=1e-8, weight_decay=0)
    device = next(model.parameters()).device; losses = []; started = time.perf_counter()
    for step in range(1, effective["steps"] + 1):
        check_cancel(); sample = samples[(step - 1) % len(samples)]
        batch = collate_samples([sample], tokenizer.pad_token_id)
        inputs = torch.tensor(batch["input_ids"], dtype=torch.long, device=device)
        labels = torch.tensor(batch["labels"], dtype=torch.long, device=device)
        optimizer.zero_grad(set_to_none=True)
        # 标签与输入保持同位置；Qwen2ForCausalLM 的 CausalLMLoss 在内部仅移位一次。
        loss = model(input_ids=inputs, labels=labels, use_cache=False, return_dict=True).loss
        if not torch.isfinite(loss).item(): raise ProtocolError("NONFINITE_LOSS", "训练损失非有限数，停止执行。")
        loss.backward(); check_cancel(); optimizer.step()
        value = float(loss.detach().item()); losses.append(value)
        emit("metric", {"step": step, "total_steps": effective["steps"], "loss": value, "supervised_tokens": sample["supervised_tokens"]})
    deltas = {name: float((parameter.detach().float().cpu() - initial[name]).abs().max()) for name, parameter in trainable.items()}
    if not any(value > 0 for value in deltas.values()): raise ProtocolError("WEIGHTS_UNCHANGED", "LoRA 参数未发生实际变化。")
    state = {name: tensor.detach().float().cpu().contiguous() for name, tensor in get_peft_model_state_dict(model).items()}
    metrics = {"losses": losses, "parameter_max_abs_delta": deltas, "trainable_parameters": sum(parameter.numel() for parameter in trainable.values()), "trainable_dtypes": sorted({str(parameter.dtype) for parameter in trainable.values()}), "elapsed_seconds": time.perf_counter() - started, "supervision": "assistant_content_and_im_end", "label_shift": "Qwen CausalLMLoss 内部一次", "sample_order": "按文件顺序循环", "packing": False, "gradient_clipping": None, "quality_status": "not_evaluated", "compute_device": str(device)}
    del optimizer, initial, trainable, loss, inputs, labels
    return model, state, metrics


def write_adapters(state, effective, snapshot, model_dir, output):
    """同一 PEFT LoRA 的显式转置，保留两份摘要，不能冒称跨端验收。"""
    import torch
    from safetensors.torch import save_file
    rank = effective["lora_rank"]
    expected = {}
    for layer in range(24 - effective["num_layers"], 24):
        for module, width in (("q_proj", 896), ("v_proj", 128)):
            prefix = f"base_model.model.model.layers.{layer}.self_attn.{module}."
            expected[prefix + "lora_A.weight"] = (rank, 896)
            expected[prefix + "lora_B.weight"] = (width, rank)
    if set(state) != set(expected) or any(tuple(state[name].shape) != shape or not torch.isfinite(state[name]).all().item() for name, shape in expected.items()):
        raise ProtocolError("ADAPTER_MODULE_MISMATCH", "PEFT 实际模块或形状不能转换为固定 MLX LoRA。")
    converted = {}
    for name, tensor in state.items():
        target = name.removeprefix("base_model.model.").replace(".lora_A.weight", ".lora_a").replace(".lora_B.weight", ".lora_b")
        converted[target] = tensor.transpose(0, 1).contiguous()
    peft_dir, mlx_dir = output / "peft-adapter", output / "mlx-adapter"
    peft_dir.mkdir(); mlx_dir.mkdir()
    save_file(state, str(peft_dir / "adapter_model.safetensors"))
    save_file(converted, str(mlx_dir / "adapters.safetensors"))
    legacy_entries = [{"path": path.name, "size": path.stat().st_size, "sha256": file_hash(path)} for path in sorted(model_dir.iterdir()) if path.is_file() and (path.suffix in {".json", ".safetensors", ".txt", ".jinja"} or path.name == "LICENSE")]
    legacy_digest = hashlib.sha256(json.dumps(legacy_entries, sort_keys=True).encode()).hexdigest()
    config = {"fine_tune_type": "lora", "num_layers": effective["num_layers"], "lora_parameters": {"rank": rank, "scale": effective["lora_alpha"] / rank, "dropout": 0.0, "keys": ["self_attn.q_proj", "self_attn.v_proj"]}, "base_manifest_sha256": legacy_digest, "base_input_manifest_digest": MODEL_DIGEST, "training_recipe_digest": effective["tokenization_recipe_digest"], "evaluation_plan_digest": snapshot["input"].get("evaluation_plan_digest"), "template_sha256": TEMPLATE_SHA256, "recipe_id": RECIPE_ID}
    peft_config = {"base_model_name_or_path": "Qwen/Qwen2.5-0.5B-Instruct", "peft_type": "LORA", "task_type": "CAUSAL_LM", "r": rank, "lora_alpha": effective["lora_alpha"], "lora_dropout": 0.0, "bias": "none", "target_modules": ["q_proj", "v_proj"], "layers_to_transform": list(range(24 - effective["num_layers"], 24)), "layers_pattern": "layers", "inference_mode": True, "use_rslora": False, "use_dora": False}
    write_json(peft_dir / "adapter_config.json", peft_config); write_json(mlx_dir / "adapter_config.json", config)
    conversion = {"schema_version": "peft-to-mlx-lora-v1", "operation": "transpose_lora_matrices", "source_attempt_id": snapshot["attempt_id"], "source_executor_id": snapshot["executor_id"], "source_model_manifest_digest": MODEL_DIGEST, "source_sha256": file_hash(peft_dir / "adapter_model.safetensors"), "output_sha256": file_hash(mlx_dir / "adapters.safetensors"), "training_recipe_digest": effective["tokenization_recipe_digest"], "source_code_digest": effective["source_code_digest"], "module_count": len(state), "scale": effective["lora_alpha"] / rank, "apple_independent_use": "not_verified", "quality_status": "not_evaluated"}
    write_json(output / "adapter-conversion.json", conversion)
    return conversion


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def run(snapshot, input_dir, output, emit, check_cancel):
    validate_snapshot(snapshot)
    output = Path(output)
    if not output.is_absolute() or output.is_symlink() or output.resolve() != output or (output.exists() and (not output.is_dir() or any(output.iterdir()))) or output.is_relative_to(Path(input_dir)) or Path(input_dir).is_relative_to(output):
        raise ProtocolError("UNSAFE_OUTPUT_DIRECTORY", "输出须为独立且空、不经链接的本次目录。")
    environment = probe()
    if not environment["ready"]: raise ProtocolError("NVIDIA_NOT_READY", "NVIDIA 固定环境未通过探测；不会转到 CPU 或 Apple 执行。", 409)
    effective, prepared = prepare(snapshot, input_dir, check_cancel)
    import torch
    from transformers import AutoModelForCausalLM
    torch.manual_seed(effective["seed"]); torch.cuda.manual_seed_all(effective["seed"])
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    model = None
    output.mkdir(parents=False, exist_ok=True)
    if any(output.iterdir()): raise ProtocolError("UNSAFE_OUTPUT_DIRECTORY", "检查期间输出目录出现内容，拒绝覆盖。")
    write_json(output / "environment.json", environment); write_json(output / "input-check.json", prepared["check_report"])
    started = time.perf_counter(); torch.cuda.reset_peak_memory_stats(0)
    try:
        check_cancel(); emit("phase", {"phase": "loading", "message": "正在 NVIDIA 上加载固定原权重"})
        load_started = time.perf_counter()
        model = AutoModelForCausalLM.from_pretrained(str(Path(input_dir) / "model"), torch_dtype=torch.bfloat16, local_files_only=True, trust_remote_code=False, use_safetensors=True, attn_implementation="eager").to("cuda:0")
        torch.cuda.synchronize(); effective["model_load_seconds"] = time.perf_counter() - load_started
        model.eval(); check_cancel()
        if snapshot["operation"] == "generate":
            emit("phase", {"phase": "generating", "message": "正在生成"})
            text, metrics = generate(model, prepared["tokenizer"], prepared["prompt"], effective, emit, check_cancel)
            (output / "result.txt").write_text(text)
        else:
            emit("phase", {"phase": "training", "message": "正在更新固定目标模块的 LoRA"})
            model, state, metrics = train(model, prepared["tokenizer"], prepared["samples"], effective, emit, check_cancel)
            write_adapters(state, effective, snapshot, Path(input_dir) / "model", output); del state
        read_inputs(snapshot, input_dir, check_cancel)
        effective.update(peak_allocated_bytes=torch.cuda.max_memory_allocated(0), peak_reserved_bytes=torch.cuda.max_memory_reserved(0), execution_seconds=time.perf_counter() - started, input_unchanged=True)
        write_json(output / "metrics.json", metrics)
    finally:
        del model; gc.collect(); torch.cuda.empty_cache(); torch.cuda.synchronize()
        effective.update(after_unload_allocated_bytes=torch.cuda.memory_allocated(0), after_unload_reserved_bytes=torch.cuda.memory_reserved(0), unload_scope="本执行器的 PyTorch 分配观察；进程组退出另由远端协议确认。")
        write_json(output / "effective-config.json", effective)
    check_cancel()
    artifacts = [{"path": path.relative_to(output).as_posix(), "sha256": file_hash(path), "media_type": "application/json" if path.suffix == ".json" else "text/plain" if path.suffix == ".txt" else "application/octet-stream"} for path in sorted(output.rglob("*")) if path.is_file()]
    if sum(path.stat().st_size for path in output.rglob("*") if path.is_file()) > output_reserve_bytes(snapshot): raise ProtocolError("OUTPUT_LIMIT", "产物超出固定预留上限。")
    return artifacts, effective
