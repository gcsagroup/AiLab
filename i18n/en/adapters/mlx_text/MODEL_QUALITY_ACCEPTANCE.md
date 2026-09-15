<!-- translation-navigation:start -->
[简体中文](../../../../adapters/mlx_text/MODEL_QUALITY_ACCEPTANCE.md) · [繁體中文](../../../zh-TW/adapters/mlx_text/MODEL_QUALITY_ACCEPTANCE.md) · [English](MODEL_QUALITY_ACCEPTANCE.md)
<!-- translation-navigation:end -->

<a id="原权重与量化模型质量准入"></a>

# Quality admission for original and quantized model weights

Date: 2026-09-10. Current conclusion: formal quality comparison, failure gates, report export, and model-export readback are complete. This MLX 4-bit weight-quantized candidate failed quality acceptance, remains experimental, and has 0 candidate registrations.

<a id="已接入的流程"></a>

## Integrated workflow

1. A formal conversion task generates an MLX 4-bit/64/affine model from the original. Saving binds the conversion attempt, original-weight version, and sealed file manifest.
2. A new evaluation can select an adapter or quantized model. A quantized model is pinned back to the original weights from its conversion provenance. The admission plan is pinned on the first evaluation; other plans may produce comparisons but cannot grant admission.
3. Preflight checks both complete weight sets, tokenizers, templates, the plan, and execution code. Two independent child processes each load one model and use the same questions and generation parameters.
4. Registration recalculates every real-output judgment, category summary, regression threshold, and independent-process identity, and rechecks conversion provenance and the sealed report. Only successful explicit registration writes the quantized candidate and marks the model `quality_approved`.
5. MLX remains the default engine. Missing product-conversion provenance, format/engine mismatch, replaced plans, changed sources, incomplete evidence, unfinished human-review items, or failed quality prevent admission.

This is weight-quantization quality comparison, not q4 KV-cache acceptance. The original LoRA pre-training-plan requirement, historical failure reports, and q4 KV No-Go conclusion remain valid.

<a id="固定真实对照"></a>

## Fixed real comparison

Preregistered plan: [frozen-plan.json](../../../../.artifacts/m5-quantization-quality/plan-20260910-v1/frozen-plan.json). Its SHA-256 is `1c0af19ea167218b5a67926d8987334cf9fa36436c157709d7484bb812ac2ea5`. The comparison used original Qwen2.5-0.5B-Instruct weights and MLX 4-bit weights actually generated in this new independent library. The 16 questions span four categories, each requiring at least 75%, with 0 permitted regression loss; temperature 0, Top-p 1, seed 0, and at most 64 tokens per question. Only one formal comparison ran, with no changes to questions, rules, or thresholds after seeing answers.

| Category | Original weights | Quantized model | Quantized threshold |
|---|---:|---:|---:|
| Business | 2 / 4 | 2 / 4 | 3 / 4, not met |
| Format | 2 / 4 | 2 / 4 | 3 / 4, not met |
| Regression | 3 / 4 | 3 / 4 | 3 / 4, met |
| Behavior | 4 / 4 | 3 / 4 | 3 / 4, met |
| Total | 11 / 16 | 10 / 16 | Judged per category; the total is not a substitute |

Quality status was `failed / eligible=false`; the formal registration endpoint returned `409 EVALUATION_FAILED`. The independent loading processes were 99880 and 99884, with actual loaded-model digests `a9b08fa2b761cbfc7335b28c6b0997b6e7713893aaca4b215625ffc99a1d36b3` and `9c11562b7a0990d0efc12ab596fcda0120a96f26245aeb481d30ccb7c2a35aba`. Complete per-question answers, rules, timings, and peak memory are in the [evaluation record](../../../../.artifacts/m5-quantization-quality/real-20260910-v1/evaluation-record.json). This small sample does not establish general business quality. Timing and peaks from one sequential-loading run are observations, not acceptance of performance gains.

The report export contained 11 files and the model export 13 files; all SHA-256 values were recalculated. Exported reports exactly matched the sealed reports, and the quantized model's digest was unchanged after export. Both registered assets underwent complete file-set checks. External-source manifests were recalculated under the original import policy; source code and the frozen plan were unchanged. See the [read-only closure report](../../../../.artifacts/m5-quantization-quality/real-20260910-v1/completion.json).

Another reviewer independently rejudged 32 original answers, checked category scoring, three separate PIDs, admission rejection, and the sizes/hashes of both exports, reaching the same conclusion. The [independent review](../../../../.artifacts/m5-quantization-quality/independent-review-v1.json) also confirmed that the original report bytes were unchanged.

The first script's final step incorrectly applied the “complete registered-asset directory” check to the external Hugging Face download directory. Its existing `.cache` was outside the imported-model manifest, causing the [original run report](../../../../.artifacts/m5-quantization-quality/real-20260910-v1/report.json) to be marked failed. That report is retained. Subsequent read-only verification checked files under the original import scope and passed, without rerunning models or overriding the quality failure.

<a id="验证与剩余边界"></a>

## Verification and remaining boundaries

- 22 new quantization-control contract tests passed, covering first-plan binding, forged success, same-process execution, wrong weights, changed conversion provenance, concurrent registration changes, report export, and admission after isolated restore. These are explicitly labeled fixtures and are not evidence of model-quality acceptance.
- Control regressions for historical LoRA/conversion and new quantization passed in the same round; 76 MLX rule, identity, and real-tokenizer checks passed. The evaluation and quantization UI entry points passed 9 tests, and TypeScript checking passed.
- Ordinary-window and final-application-package acceptance is recorded in overall acceptance reports; component tests do not replace final-package checks here. NVIDIA training, returning the same LoRA to Apple, and a real passing quality candidate are still unaccepted, so M0—M6 is not complete.

Rerun code is [run_model_quality_probe.py](../../../../tests/control/run_model_quality_probe.py); read-only verification of the existing run is [verify_model_quality_probe.py](../../../../tests/control/verify_model_quality_probe.py). A rerun must create a new independent evidence directory and retain old results; a rerun or new plan cannot rewrite this candidate's failure as a pass.
