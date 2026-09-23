"""独立文本评测：每个基线／候选在另一进程中重新加载模型。"""

import argparse
import contextlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.mlx_text.evaluation import EvaluationError, load_plan, summarize, model_evaluation_identity, model_plan_bound
from adapters.mlx_text.recipe import build_recipe
from workers import mlx_worker as worker


def collect_prediction(responses, check_cancel):
    """原样收集文本及 MLX 结束回执；没有结束信号时明确记为未知。"""
    chunks, token_ids, first_token_seconds = [], [], None
    generated_tokens, finish_reason = 0, "unknown"
    started = time.perf_counter()
    with contextlib.closing(responses):
        for response in responses:
            check_cancel()
            if first_token_seconds is None:
                first_token_seconds = time.perf_counter() - started
            chunks.append(response.text)
            token_ids.append(int(response.token))
            generated_tokens = int(response.generation_tokens)
            finish_reason = response.finish_reason or "unknown"
    return "".join(chunks), {
        "output_token_ids": token_ids, "generated_tokens": generated_tokens,
        "stream_response_count": len(token_ids), "finish_reason": finish_reason,
        "first_token_seconds": first_token_seconds,
        "generation_seconds": time.perf_counter() - started,
    }


def run_evaluate(snapshot, effective, output, emit, check_cancel):
    rows, criteria, plan_digest = load_plan(snapshot)
    source = output / "evaluation-snapshot.json"
    worker.write_json(source, snapshot)
    for variant in ("baseline", "candidate"):
        check_cancel()
        emit("phase", phase="evaluating", message="正在独立加载并评测" + ("基线" if variant == "baseline" else "候选"), variant=variant, total_samples=len(rows))
        entry = [sys.executable, "--mode", "evaluation-pass"] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
        command = [*entry, "--snapshot", str(source), "--output-dir", str(output / variant), "--variant", variant]
        environment = {**os.environ, "AILAB_CONTROL_PID": str(os.getpid()), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
        with (output / f"{variant}.events.jsonl").open("w") as stdout, (output / f"{variant}.stderr.log").open("w") as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=environment)
            started = time.monotonic()
            try:
                while process.poll() is None:
                    check_cancel()
                    if time.monotonic() - started > 600:
                        raise EvaluationError("EVALUATION_TIMEOUT", "单个评测阶段超过 10 分钟的受控预算")
                    try:
                        process.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                if process.returncode != 0:
                    raise EvaluationError("EVALUATION_PASS_FAILED", f"{variant} 独立加载或评测失败，保留本次日志")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        emit("metric", variant=variant, completed_samples=len(rows), total_samples=len(rows))
    passes = {variant: json.loads((output / variant / "predictions.json").read_text()) for variant in ("baseline", "candidate")}
    model_evaluation = snapshot.get("evaluation_kind") == "quantized_model"
    config = {} if model_evaluation else json.loads((Path(snapshot["adapter_path"]) / "adapter_config.json").read_text())
    report = summarize(rows, criteria, passes["baseline"]["outputs"], passes["candidate"]["outputs"], model_plan_bound(snapshot) if model_evaluation else config.get("evaluation_plan_digest") == plan_digest)
    report.update(evaluation_plan_digest=plan_digest, evaluation_dataset_manifest_digest=snapshot["evaluation_dataset_manifest_digest"], evaluation_criteria_manifest_digest=snapshot["evaluation_criteria_manifest_digest"], model_manifest_digest=snapshot["model_manifest_digest"], adapter_manifest_digest=snapshot.get("adapter_manifest_digest"), adapter_training_recipe_digest=snapshot.get("adapter_training_recipe_digest"), independent_loads={name: result["identity"] for name, result in passes.items()}, rules_implementation_sha256=worker.sha256(Path(__file__).resolve().parents[1] / "adapters/mlx_text/evaluation.py"))
    report.update(observations={name: result["observations"] for name, result in passes.items()},
                  observation_scope="逐题保留 MLX 实际词元与结束回执，包含结束词元；stop 为引擎停止，length 为输出上限，unknown 为缺少结束信号。单轮计时不代表性能验收。")
    if model_evaluation:
        report.update(evaluation_kind="quantized_model", prospective_basis="first_quantized_model_evaluation", candidate_model_manifest_digest=snapshot["candidate_model_manifest_digest"], model_comparison=snapshot["model_comparison"], model_comparison_digest=snapshot["model_comparison_digest"], quality_plan_ref_digest=snapshot["quality_plan_ref"]["digest"], model_evaluation_recipe_digest=effective["model_evaluation_recipe_digest"],
                      performance_scope="同机顺序各加载一次；逐题时间与内存仅作本次观测，未作冷热缓存及重复采样性能验收。",
                      quality_scope="仅代表此量化模型首次固定文本规则集的独立对照；不代表其他任务或普遍质量、速度收益。")
        for issue in report["blocking"]:
            if issue["code"] == "POSTHOC_EVALUATION":
                issue.update(code="MODEL_QUALITY_PLAN_MISMATCH", message="本次不是该量化模型首次固定的准入方案，仅能作对照")
    load_plan(snapshot)
    effective.update(evaluation_plan_digest=plan_digest, evaluation_sample_count=len(rows), independent_loads=2, quality_status=report["status"], eligible=report["eligible"], evaluation_criteria=criteria)
    worker.write_json(output / "evaluation-report.json", report)


def pass_main():
    parser = argparse.ArgumentParser(description="固定文本评测的独立加载阶段")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variant", choices=("baseline", "candidate"), required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, worker.cancel_handler)
    signal.signal(signal.SIGINT, worker.cancel_handler)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
    try:
        worker.watch_controller()
        snapshot = json.loads(args.snapshot.read_text())
        output = args.output_dir.absolute()
        model_path, effective = worker.validate_snapshot(snapshot, output)
        model_evaluation = snapshot.get("evaluation_kind") == "quantized_model"
        loaded_path = Path(snapshot["candidate_model_path"]) if model_evaluation and args.variant == "candidate" else model_path
        loaded_manifest_digest = snapshot["candidate_model_manifest_digest"] if model_evaluation and args.variant == "candidate" else snapshot["model_manifest_digest"]
        rows, criteria, plan_digest = load_plan(snapshot)
        if model_evaluation:
            _, evaluation_digest = model_evaluation_identity(snapshot, snapshot["tokenization_recipe_digest"])
            if snapshot.get("effective_config", {}).get("model_evaluation_recipe_digest") != evaluation_digest:
                raise EvaluationError("MODEL_EVALUATION_IDENTITY_CHANGED", "独立评测的输入或执行代码身份已变化")
        output.mkdir(parents=True, exist_ok=False)
        with contextlib.redirect_stdout(sys.stderr):
            import mlx.core as mx
            from mlx_lm import load, stream_generate
            from mlx_lm.sample_utils import make_sampler
            mx.set_default_device(mx.gpu)
            mx.random.seed(criteria["generation"]["seed"])
            load_started = time.perf_counter()
            model, tokenizer = load(str(loaded_path), tokenizer_config={"trust_remote_code": False, "local_files_only": True})
            mx.eval(model.parameters())
            load_seconds = time.perf_counter() - load_started
            manifest = worker.model_manifest(loaded_path)
            if args.variant == "candidate" and not model_evaluation:
                worker.load_validated_adapter(model, tokenizer, snapshot["adapter_path"], manifest["sha256"], snapshot["model_manifest_digest"], snapshot["adapter_training_recipe_digest"])
            _, recipe_digest = build_recipe(loaded_path, tokenizer, "evaluate", None)
            if snapshot.get("tokenization_recipe_digest") != recipe_digest:
                raise EvaluationError("TOKENIZATION_IDENTITY_CHANGED", "独立评测加载后的分词配方与提交身份不符")
            model.eval()
            outputs, observations = {}, {}
            for index, row in enumerate(rows, 1):
                worker.check_cancel()
                prompt = tokenizer.apply_chat_template([{"role": "user", "content": row["prompt"]}], tokenize=True, add_generation_prompt=True)
                if len(prompt) + criteria["generation"]["max_tokens"] > 4096:
                    raise EvaluationError("CONTEXT_TOO_LONG", "评测样本超出输入输出总词元限制")
                responses = stream_generate(model, tokenizer, prompt, max_tokens=criteria["generation"]["max_tokens"], sampler=make_sampler(temp=0))
                outputs[row["id"]], observation = collect_prediction(responses, worker.check_cancel)
                observations[row["id"]] = {"prompt_tokens": len(prompt), **observation}
                worker.emit("metric", variant=args.variant, completed_samples=index, total_samples=len(rows), sample_id=row["id"])
            worker.verify_snapshot_manifest(model_path, snapshot["model_manifest"], snapshot["model_manifest_digest"], "MODEL")
            if model_evaluation:
                worker.verify_snapshot_manifest(Path(snapshot["candidate_model_path"]), snapshot["candidate_model_manifest"], snapshot["candidate_model_manifest_digest"], "CANDIDATE_MODEL")
            else:
                worker.verify_snapshot_manifest(Path(snapshot["adapter_path"]), snapshot["adapter_manifest"], snapshot["adapter_manifest_digest"], "ADAPTER")
            load_plan(snapshot)
            worker.check_cancel()
            identity = {"pid": os.getpid(), "variant": args.variant, "model_manifest_digest": loaded_manifest_digest, "adapter_manifest_digest": snapshot["adapter_manifest_digest"] if args.variant == "candidate" and not model_evaluation else None, "evaluation_plan_digest": plan_digest, "tokenization_recipe_digest": recipe_digest, "device": mx.device_info(), "generation": criteria["generation"], "peak_memory_bytes": mx.get_peak_memory()}
            if model_evaluation:
                identity.update(evaluation_kind="quantized_model", model_evaluation_recipe_digest=evaluation_digest, input_quantization=json.loads((loaded_path / "config.json").read_text()).get("quantization"))
            identity["load_seconds"] = load_seconds
            worker.write_json(output / "predictions.json", {"outputs": outputs, "identity": identity, "observations": observations})
        worker.emit("completed", variant=args.variant, completed_samples=len(rows))
        return 0
    except (worker.WorkerError, EvaluationError) as exc:
        worker.emit("error", code=exc.code, message=str(exc))
        return 130 if exc.code == "CANCELLED" else 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        worker.emit("error", code="EVALUATION_PASS_FAILED", message="独立评测失败，请查看本次日志")
        return 1


if __name__ == "__main__":
    raise SystemExit(pass_main())
