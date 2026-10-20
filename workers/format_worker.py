"""固定形状文本转换和 CPU 推理；只加载本产品封存的独立转换产物。"""

import argparse
import contextlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services/control"))
from workers import mlx_worker as common
from ailab_control.assets import safe_json
from ailab_control.format_assets import FORMATS, format_manifest
from ailab_control.storage import Fault

PROMPTS = ["只回复数字：2加3等于几？", "把 hello 翻译成中文。", "用一句话描述蓝色的天空。"]
MAX_ERROR = 0.002


def handles(snapshot):
    return snapshot.get("kind") == "text" and snapshot.get("runtime", {}).get("engine") in FORMATS


def tokenizer_for(path):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)


def prompt_tokens(tokenizer, prompt):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 16000:
        raise common.WorkerError("INVALID_PROMPT", "请输入非空且不超过 16000 字符的提示词")
    return tokenizer.apply_chat_template([{"role": "user", "content": prompt}], tokenize=True, add_generation_prompt=True)


def tensors(tokenizer, tokens):
    import numpy as np
    if not 1 <= len(tokens) <= 128:
        raise common.WorkerError("CONTEXT_TOO_LONG", "当前转换图的总上下文为 128 词元，不截断输入")
    return {"input_ids": np.array([[tokenizer.pad_token_id] * (128 - len(tokens)) + tokens], dtype=np.int32), "attention_mask": np.array([[0] * (128 - len(tokens)) + [1] * len(tokens)], dtype=np.int32)}


def check(snapshot, output):
    operation, runtime = snapshot.get("operation"), snapshot.get("runtime", {})
    if not handles(snapshot) or operation not in {"convert", "generate"}:
        raise common.WorkerError("UNSUPPORTED_OPERATION", "当前格式执行器只支持固定转换和独立推理")
    target = runtime["engine"]
    common.number(runtime, "seed", 0, 0, 0, True)
    allowed = {"engine", "device_id", "seed"} | ({"max_tokens"} if operation == "generate" else set())
    if set(runtime) - allowed or runtime.get("device_id") != "cpu":
        raise common.WorkerError("UNSUPPORTED_PARAMETER", "转换图固定为 CPU／FP32，推理仅开放最大输出词元")
    model = Path(snapshot.get("model_path", ""))
    if not model.is_absolute() or not model.is_dir() or model.resolve() != model:
        raise common.WorkerError("MODEL_NOT_LOCAL", "模型必须为明确的本地目录")
    common.verify_snapshot_manifest(model, snapshot.get("model_manifest"), snapshot.get("model_manifest_digest"), "MODEL")
    if output.resolve() != output or output.is_symlink() or output == model or output.is_relative_to(model) or model.is_relative_to(output) or output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise common.WorkerError("OUTPUT_OVERLAP", "输出必须为独立的空目录")
    if any(snapshot.get(key) for key in ("adapter_path", "dataset_path", "evaluation_plan_id", "checkpoint_ref")):
        raise common.WorkerError("UNSUPPORTED_INPUT", "当前格式操作不接受适配器、训练或评测输入")
    tokenizer = tokenizer_for(model)
    effective = {"engine": target, "device_id": "cpu", "seed": 0, "precision": "float32", "context_length": 128, "kv_cache": False}
    if operation == "convert":
        config = safe_json(model / "config.json")
        required = {"model_type": "qwen2", "hidden_size": 896, "num_hidden_layers": 24, "num_attention_heads": 14, "num_key_value_heads": 2, "intermediate_size": 4864, "vocab_size": 151936, "tie_word_embeddings": True, "hidden_act": "silu", "rope_theta": 1000000.0, "rms_norm_eps": 1e-6}
        if any(config.get(key) != value for key, value in required.items()) or any(config.get(key) for key in ("quantization", "quantization_config", "rope_scaling", "use_sliding_window")) or not list(model.glob("*.safetensors")):
            raise common.WorkerError("MODEL_UNVERIFIED", "当前格式转换仅接受固定结构的未量化 Qwen2.5-0.5B 权重")
        if snapshot.get("input") not in ({}, {"prompt": ""}):
            raise common.WorkerError("UNSUPPORTED_INPUT", "转换采用固定数值对照样例")
    else:
        metadata = format_manifest(model)["metadata"]
        if metadata["format"] != target or snapshot.get("format_provenance", {}).get("manifest_digest") != snapshot["model_manifest_digest"]:
            raise common.WorkerError("CONVERTED_ENGINE_MISMATCH", "模型格式、运行引擎或内部转换来源不一致")
        if set(snapshot.get("input", {})) != {"prompt"}:
            raise common.WorkerError("UNSUPPORTED_INPUT", "当前推理只接受提示词")
        tokens = prompt_tokens(tokenizer, snapshot["input"]["prompt"])
        maximum = common.number(runtime, "max_tokens", 32, 1, 64, True)
        if len(tokens) + maximum > 128:
            raise common.WorkerError("CONTEXT_TOO_LONG", "输入和最大输出合计超过转换图的 128 词元预算")
        effective.update(max_tokens=maximum, prompt_tokens=len(tokens), temperature=0)
    packages = ["torch", "transformers", "tokenizers", "numpy", "safetensors"] + {"coreml": ["coremltools"], "onnx": ["onnx", "onnxruntime"], "torchscript": []}[target]
    versions = {name: importlib.metadata.version(name) for name in packages}
    if target == "coreml":
        import coremltools  # noqa: F401
    elif target == "onnx":
        import onnxruntime  # noqa: F401
    files = [Path(__file__), ROOT / "adapters/media/text_formats.py", ROOT / "services/control/ailab_control/format_assets.py"]
    recipe = {"id": "qwen25-fixed-text-formats-v1", "operation": operation, "model_manifest_digest": snapshot["model_manifest_digest"], "input": snapshot.get("input"), "effective_config": effective, "versions": versions, "source_sha256": {str(path.relative_to(ROOT)): common.sha256(path) for path in files}, "format_provenance": snapshot.get("format_provenance")}
    identity = common.canonical_digest(recipe)
    return {"can_submit": True, "blocking": [], "effective_config": effective, "tokenization_recipe_digest": identity, "recipe": recipe, "check_report": {"target_format": target, "independent_load_required": True, "context_length": 128, "device": "cpu", "quality_status": "not_evaluated"}}


def load_graph(directory, target):
    if target == "torchscript":
        import torch
        model = torch.jit.load(str(directory / FORMATS[target]), map_location="cpu").eval()
        def invoke(inputs):
            with torch.no_grad():
                return model(*(torch.from_numpy(inputs[key]) for key in ("input_ids", "attention_mask"))).numpy()
    elif target == "onnx":
        import onnxruntime as ort
        options = ort.SessionOptions(); options.intra_op_num_threads = 8
        model = ort.InferenceSession(str(directory / FORMATS[target]), sess_options=options, providers=["CPUExecutionProvider"])
        if model.get_providers() != ["CPUExecutionProvider"]:
            raise common.WorkerError("CONVERTED_ENGINE_MISMATCH", "ONNX 未使用冻结的 CPU 执行器")
        def invoke(inputs): return model.run(["logits"], inputs)[0]
    else:
        import coremltools as ct
        model = ct.models.MLModel(str(directory / FORMATS[target]), compute_units=ct.ComputeUnit.CPU_ONLY)
        def invoke(inputs): return model.predict(inputs)["logits"]
    return invoke


def convert(snapshot, effective, output):
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM
    from adapters.media.text_formats import FixedQwen
    source, target = Path(snapshot["model_path"]), effective["engine"]
    common.emit("phase", phase="converting", message="正在构建固定形状的独立文本模型")
    base, loading = AutoModelForCausalLM.from_pretrained(source, dtype=torch.float32, local_files_only=True, trust_remote_code=False, attn_implementation="eager", output_loading_info=True)
    if any(loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
        raise common.WorkerError("MODEL_WEIGHTS_MISMATCH", "源权重与固定模型结构不完全匹配")
    base.eval(); tokenizer = tokenizer_for(source); wrapper = FixedQwen(base).eval()
    inputs = [tensors(tokenizer, prompt_tokens(tokenizer, prompt)) for prompt in PROMPTS]
    references, wrapper_errors = [], []
    with torch.no_grad():
        for prompt, values in zip(PROMPTS, inputs):
            common.check_cancel()
            tokens = prompt_tokens(tokenizer, prompt)
            reference = base(input_ids=torch.tensor([tokens]), use_cache=False, logits_to_keep=1).logits[:, -1, :].numpy()
            actual = wrapper(*(torch.from_numpy(values[key]) for key in ("input_ids", "attention_mask"))).numpy()
            error = float(np.max(np.abs(actual - reference)))
            if not np.isfinite(actual).all() or error > MAX_ERROR:
                raise common.WorkerError("CONVERSION_NUMERICAL_MISMATCH", "固定图与原生模型的数值差异超出 0.002")
            references.append(reference); wrapper_errors.append(error)
        example = tuple(torch.from_numpy(inputs[0][key]) for key in ("input_ids", "attention_mask"))
        destination = output / "model"; destination.mkdir()
        common.check_cancel()
        if target == "onnx":
            import onnx
            with tempfile.TemporaryDirectory(prefix="onnx-export-", dir=output) as temporary:
                graph_path = Path(temporary) / "model.onnx"
                torch.onnx.export(wrapper, example, str(graph_path), input_names=["input_ids", "attention_mask"], output_names=["logits"], opset_version=18, dynamo=False)
                graph = onnx.load(str(graph_path), load_external_data=True)
                onnx.save_model(graph, str(destination / FORMATS[target]), save_as_external_data=True, all_tensors_to_one_file=True, location="model.onnx.data", size_threshold=0)
                del graph
        else:
            traced = torch.jit.trace(wrapper, example, strict=True)
            if target == "torchscript":
                torch.jit.save(traced, str(destination / FORMATS[target]))
            else:
                import coremltools as ct
                converted = ct.convert(traced, inputs=[ct.TensorType(name=key, shape=(1, 128), dtype=np.int32) for key in ("input_ids", "attention_mask")], outputs=[ct.TensorType(name="logits")], minimum_deployment_target=ct.target.macOS15, convert_to="mlprogram", compute_precision=ct.precision.FLOAT32, compute_units=ct.ComputeUnit.CPU_ONLY)
                converted.save(str(destination / FORMATS[target]))
                del converted
            del traced
    del wrapper, base
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja", "generation_config.json", "LICENSE", "README.md"):
        if (source / name).is_file(): shutil.copyfile(source / name, destination / name)
    common.write_json(destination / "ailab-format.json", {"schema_version": 1, "format": target, "entrypoint": FORMATS[target], "context_length": 128, "precision": "float32", "device": "cpu", "source_manifest_digest": snapshot["model_manifest_digest"], "inputs": {"input_ids": {"shape": [1, 128], "dtype": "int32"}, "attention_mask": {"shape": [1, 128], "dtype": "int32"}}, "output": {"logits": {"shape": [1, 151936], "dtype": "float32"}}})
    common.emit("phase", phase="verifying", message="正在重新加载转换文件并与原生模型对照")
    invoke = load_graph(destination, target)
    checks = []
    for prompt, values, reference, wrapper_error in zip(PROMPTS, inputs, references, wrapper_errors):
        common.check_cancel(); started = time.perf_counter(); actual = invoke(values)
        error = float(np.max(np.abs(actual - reference)))
        passed = np.isfinite(actual).all() and error <= MAX_ERROR and int(actual.argmax()) == int(reference.argmax())
        checks.append({"prompt": prompt, "max_abs_logit_error": error, "fixed_graph_error": wrapper_error, "same_next_token": int(actual.argmax()) == int(reference.argmax()), "seconds": time.perf_counter() - started, "passed": bool(passed)})
        if not passed:
            common.write_json(output / "conversion-check-failed.json", {"samples": checks, "tolerance": MAX_ERROR})
            raise common.WorkerError("CONVERSION_NUMERICAL_MISMATCH", "转换文件与原生模型的独立对照没有通过")
    inspected = format_manifest(destination)
    effective.update(model_output_manifest_digest=inspected["manifest_digest"], independent_use="verified", source_weight_bytes=sum(entry["size"] for entry in snapshot["model_manifest"] if entry["path"].endswith(".safetensors")), output_weight_bytes=sum(entry["size"] for entry in inspected["manifest"] if entry["path"].startswith("model.")))
    common.write_json(output / "conversion.json", {"operation": "convert", "target_format": target, "source_model_manifest_digest": snapshot["model_manifest_digest"], "output_model_manifest": inspected["manifest"], "output_model_manifest_digest": inspected["manifest_digest"], "verification": {"passed": True, "samples": checks, "max_abs_logit_tolerance": MAX_ERROR, "device": "cpu"}, "quality_acceptance": "固定样例的数值一致性，不代表通用质量或速度提升"})


def generate(snapshot, effective, output):
    import numpy as np
    tokenizer = tokenizer_for(snapshot["model_path"])
    tokens = prompt_tokens(tokenizer, snapshot["input"]["prompt"])
    invoke = load_graph(Path(snapshot["model_path"]), effective["engine"])
    generated = []; start = time.perf_counter(); first = None; reason = "length"
    eos = safe_json(Path(snapshot["model_path"]) / "generation_config.json").get("eos_token_id", tokenizer.eos_token_id)
    eos = eos if isinstance(eos, list) else [eos]
    for _ in range(effective["max_tokens"]):
        common.check_cancel()
        logits = invoke(tensors(tokenizer, tokens + generated))
        if not np.isfinite(logits).all(): raise common.WorkerError("NONFINITE_OUTPUT", "转换模型产生非有限输出")
        first = first if first is not None else time.perf_counter() - start
        token = int(logits.argmax())
        if token in eos: reason = "eos"; break
        generated.append(token)
    elapsed = time.perf_counter() - start
    (output / "result.txt").write_text(tokenizer.decode(generated, skip_special_tokens=True))
    metrics = {"generation_tokens": len(generated), "generation_wall_seconds": elapsed, "generation_tps": len(generated) / elapsed, "first_token_seconds": first, "finish_reason": reason, "device": "cpu", "context_length": 128, "scope": "固定形状无 KV 缓存，每个词元重新计算完整图；不宣称加速"}
    common.write_json(output / "metrics.json", metrics); common.emit("metric", **metrics)


def main(preflight=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True); parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, common.cancel_handler); signal.signal(signal.SIGINT, common.cancel_handler)
    try:
        snapshot, output = json.loads(args.snapshot.read_text()), args.output_dir.absolute()
        with contextlib.redirect_stdout(sys.stderr): result = check(snapshot, output)
        if preflight:
            print(json.dumps(result, ensure_ascii=False)); return 0
        common.watch_controller()
        if snapshot.get("tokenization_recipe_digest") != result["tokenization_recipe_digest"]:
            raise common.WorkerError("CONVERSION_RECIPE_CHANGED", "格式、输入或实现与运行前检查不一致")
        output.mkdir(parents=True, exist_ok=True)
        import torch
        torch.set_num_threads(8)
        effective = result["effective_config"]
        with contextlib.redirect_stdout(sys.stderr):
            (convert if snapshot["operation"] == "convert" else generate)(snapshot, effective, output)
        common.verify_snapshot_manifest(Path(snapshot["model_path"]), snapshot["model_manifest"], snapshot["model_manifest_digest"], "MODEL")
        common.check_cancel(); common.write_json(output / "effective-config.json", effective)
        entries = [{"path": str(path.relative_to(output)), "sha256": common.sha256(path), "media_type": "application/json" if path.suffix == ".json" else "text/plain" if path.suffix == ".txt" else "application/octet-stream"} for path in sorted(output.rglob("*")) if path.is_file()]
        common.emit("completed", artifacts=entries, effective_config=effective, source_model_unchanged=True)
        return 0
    except Exception as error:
        code = getattr(error, "code", "FORMAT_EXECUTION_FAILED")
        message = str(error) if isinstance(error, (common.WorkerError, Fault)) else "格式执行失败，请查看本次诊断日志"
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        if preflight: print(json.dumps({"can_submit": False, "blocking": [{"code": code, "message": message}]}, ensure_ascii=False))
        else: common.emit("error", code=code, message=message)
        return 130 if code == "CANCELLED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
