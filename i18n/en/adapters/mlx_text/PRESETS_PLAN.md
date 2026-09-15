<!-- translation-navigation:start -->
[简体中文](../../../../adapters/mlx_text/PRESETS_PLAN.md) · [繁體中文](../../../zh-TW/adapters/mlx_text/PRESETS_PLAN.md) · [English](PRESETS_PLAN.md)
<!-- translation-navigation:end -->

<a id="m2-运行预设与-kv-缓存只读核查"></a>

# M2 runtime presets and read-only KV cache audit

Date: 2026-09-10. Status: source audit passed; the new parameters and presets below have not yet been implemented or measured on hardware, and do not constitute an M2 pass.

The goal is to add three explainable runtime presets with readback to the current Apple text combinations. Keep the model, input, context budget, output limit, and sampling parameters identical before measuring the effects of caching and chunking themselves. This report changes no executor, control service, frontend, or current media acceptance recipe, loads no model, and uses no GPU.

<a id="1-当前事实与完成标准"></a>

## 1. Current facts and completion criteria

- Current isolated environment: Python 3.13.9, MLX 0.32.2, MLX-LM 0.31.3. The actually installed `generate.py`, `models/cache.py`, `models/base.py`, `models/qwen2.py`, and `mlx.core.quantize` documentation were read and checked against official sources for the same versions.
- Current model: Qwen2.5-0.5B-Instruct; the original BF16 and locally derived affine 4 bit/group 64 weight combinations are verified separately. The model configuration has 24 layers, 14 query heads, 2 KV heads, and a hidden dimension of 896, giving 64 dimensions per head.
- The current product exposes only single-request Apple GPU text inference, with input plus maximum output limited to 4096 tokens. The model configuration's 32768 positions do not mean that budget is available in the current product.
- The current worker passes only the output limit and sampler; caching still uses MLX-LM's default full, unquantized KV, with default Prefill of 2048. The current preflight does not yet include the new fields in this report, so this report cannot be treated as implemented capability.
- Completion criteria: fields pass the same submission validation; users can inspect differences and cancel before applying a preset; the interface, applied configuration, snapshot, and real engine parameters agree; actual cache type/precision is read back; real identical-input comparisons and cancellation cleanup pass; unmeasured combinations are rejected; reports clearly separate cache memory, model weights, process memory, and task duration.

<a id="2-api-的真实语义"></a>

## 2. Actual API semantics

`stream_generate` passes the following parameters to `generate_step`, whose current defaults are listed below. Parameter defaults and the implementation summary are recorded in `.artifacts/m2-kv/source-audit-v1/source-check.json`.

| Parameter | Upstream default | Actual effect and boundary |
| --- | --- | --- |
| `max_kv_size` | `None` | When nonempty, creates a rotating KV window for ordinary models; it discards KV for earlier tokens and is not a memory-capacity limit that retains the full text |
| `prompt_cache` | `None` | Accepts a list of cache objects; once supplied, `generate_step` no longer constructs caches using `max_kv_size`, so its effect must not be silently assumed |
| `prefill_step_size` | 2048 | Computes the prompt in token chunks; changes neither input/output budgets nor concurrency or batch size |
| `kv_bits` | `None` | When nonempty, converts supported caches to affine quantized storage; does not modify model weights |
| `kv_group_size` | 64 | Quantization group size for the last KV dimension; must divide that dimension evenly |
| `quantized_kv_start` | 0 | Converts at the end of a Prefill chunk or decode step after the cache offset reaches the threshold; conversion is not guaranteed at exactly the threshold token |

Key restrictions:

1. If `make_prompt_cache` finds the model's own `make_cache()`, it calls that first and ignores `max_kv_size`; the current Qwen2 has no such method, but this behavior must not be generalized to other models.
2. The default rotating cache preserves the first 4 tokens. `RotatingKVCache.to_quantized()` explicitly raises `NotImplementedError`, so rotating windows combined with KV quantization must be rejected before submission.
3. Multi-token updates to rotating caches can temporarily reach `max_size + S - 1`, and the initial update can store the entire input chunk directly. The window size is not a hard cap on peak runtime memory.
4. Ordinary and quantized KV caches grow in increments of 256 tokens, so allocated tokens may exceed the current offset. `nbytes` measures cache array storage, not all process memory; old and new arrays may coexist during growth or quantization conversion.
5. MLX 0.32.2 affine quantization supports groups 32/64/128 and bits 2/3/4/5/6/8; the final dimension must be divisible by the group size. The current Qwen2 KV dimension is 64, making group 128 incompatible. The first round tests and exposes only KV 4 bit/group 64, without promising other values merely because the underlying enumeration is broader.
6. Quantized Attention uses two `mx.quantized_matmul` operations; ordinary caching uses `mx.fast.scaled_dot_product_attention`. Their numerical behavior and performance may differ. Quantized Attention does not support attention sinks; the current Qwen2 passes no sinks.
7. The draft-model branch of `stream_generate` removes `max_kv_size`. The current product does not expose speculative decoding and continues to reject that combination, avoiding claims that the window took effect.

Sources: [MLX-LM 0.31.3 generation implementation](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py), [cache implementation](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/models/cache.py), [Attention implementation](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/models/base.py), [MLX 0.32.2 quantization documentation](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.quantize.html).

<a id="3-建议第一版合同"></a>

## 3. Proposed first contract

Extend the following fields only for the current two weight combinations with `kind=language, operation=generate, engine=mlx, device_id=apple-gpu`. Retain the existing `seed/max_tokens/temperature/top_p`; presets must not change the user's task output limit. Evaluation continues to use frozen evaluation rules; training and weight quantization operations do not accept inference cache fields.

| Interface description | runtime field | First-round candidate values | Rejection conditions |
| --- | --- | --- | --- |
| Cache precision | `kv_precision` | `auto`, `q4` | Unknown values; other models, engines, or operations |
| Prompt chunking | `prefill_step_size` | 512, 2048, 4096 tokens | Booleans, nonintegers, 0/negative values, noncandidate values; no silent correction |
| Cache window | Not exposed yet | Displays “Retain full context” | Any `max_kv_size`/rotation request |
| Prefix reuse across runs | Not exposed yet | `disabled`; create a fresh cache each time | Supplying a historical cache path/cache ID or requesting shared reuse |

Interface precision `auto` explicitly means “Follow the current model's compute precision without quantizing KV”; run results read back the actual dtype rather than inferring it solely from the weight configuration. `q4` explicitly means “4 bit inference cache; may change answers while preserving model weights.” Group 64 and quantization start 0 are saved as fixed resolved values in the first version, without adding editable fields for which no measured need exists.

If developers expose upstream fields directly, they must still enforce `kv_bits ∈ {null, 4}`, `kv_group_size = 64`, `quantized_kv_start = 0`, and `max_kv_size = null` equally strictly; do not maintain two user-editable sets with conflicting meanings.

All three presets must be versioned and tied to the current model format, model architecture, engine version, and device. The minimum mapping is below; this is a proposed test plan, not currently applicable capability:

| Preset | Cache precision | Prefill chunk | Unchanged fields | Description |
| --- | --- | --- | --- | --- |
| Model default | auto | 2048 | Current max_tokens, temperature, top_p, seed, context budget | Reproduces the current engine's cache/chunk defaults; the title must not imply resetting generation parameters to model-card values |
| Low memory | q4 | 512 | Same as above | Attempts to reduce cache and temporary chunk memory; answers and speed may change; decide whether to expose it after testing |
| Low latency | auto | 4096 | Same as above | Attempts to reduce chunk count for long prompts; short prompts may show no difference; decide whether to expose it after testing |

For “Model default,” label the difference preview “Restore cache and prompt chunking to engine defaults.” If the product also resets all generation parameters, each must appear explicitly in the differences, while low-memory/low-latency performance comparisons separately hold sampling and output limits constant.

Saving the complete resolved fields is sufficient for execution; accompanying `preset_id/preset_version` explains their origin and must not cause the backend to rewrite snapshots automatically for a same-named preset. Reject conflicts between the template ID and fields; mark the configuration custom after the user changes any template field. Retrieve capabilities again when changing models/devices/formats, show which fields are invalid and which values remain, and never migrate old templates automatically.

<a id="4-执行回读与证据"></a>

## 4. Execution readback and evidence

The adapter should explicitly create this run's cache list, pass it to `stream_generate`, and inspect that same list's actual storage when generation ends: layer count, per-layer class name, offset, allocated shape, ordinary KV dtype or quantized bits/group and scale/bias dtype, and total `nbytes`. The quantization function replaces list elements, so reading the same list after completion confirms actual use of `QuantizedKVCache`. Save summaries without exporting user KV content.

Each run saves complete resolved parameters, model/adapter manifests, tokenizer/template digests, input-token digests, engine version, executor-source digest, hardware, PID, actual output token count, and output text. Bind these through existing product task snapshots and have the executor recheck the actual configuration, rather than showing only UI labels. New inference runtime recipe identity must be distinguished from existing tokenization recipe identity; the current tokenization recipe omits some runtime fields, so its digest alone cannot prove that cache settings were frozen.

At minimum, separate these performance fields: model loading time, time from generation start to the first token, Prefill tokens/second, Decode tokens/second, whole-process wall time, MLX peak for this generation, peak process RSS, and final KV array bytes. Record when `mx.get_peak_memory()` is reset/sampled and retain an end-to-end baseline including model loading; do not directly compare a generation-stage peak with another run's end-to-end peak.

The current fresh process per run does not retain prefix caches across tasks. Record cache hit rate as “Not applicable/disabled,” not 100%. If reuse is later exposed, identity must also include model, adapter, tokenizer, template, input prefix, KV precision, engine cache format, and isolation scope; multimodal identity additionally includes media ordering, content digests, processor, and preprocessing recipe.

<a id="5-可核算的量级仅作理论参照"></a>

## 5. Calculable scale, for theoretical reference only

The theoretical BF16 KV data size for Qwen2.5-0.5B is `2 × 24 × 2 × 64 × 2 = 12,288` bytes per token. K/V for 4096 tokens is 48 MiB. With affine 4 bit, group 64, and 2-byte scale/bias values, each token takes 3456 bytes, or 13.5 MiB for 4096 tokens. The 34.5 MiB difference is the theoretical KV array difference, not savings in model weights or whole-system memory.

These figures exclude 256-token allocation increments, temporary activations, simultaneous old/new caches during conversion, the allocator, model weights, the Python process, and system overhead. The actual KV dtype of a quantized-weight model still needs runtime readback; 4 bit weights do not imply 4 bit KV.

<a id="6-分阶段真实验证矩阵"></a>

## 6. Staged real validation matrix

Wait until the current media UI has finished using the GPU before freezing the test plan and source. Do not change the shared worker halfway through acceptance of the current media recipe.

1. **Submission contract and capability negative cases →** Missing values resolve to auto/2048; reject booleans, unknown values, and invalid ranges; train/evaluate/quantize and media operations reject inference cache fields; reject unverified devices/models and unexposed options such as rotation+quantization, historical prompt-cache, and draft-model. After preset fields change, no longer claim the original template matches.
2. **18 basic functional cases →** Two weight formats × three presets × short/medium/long inputs. Use the real tokenizer to constrain the three input lengths to approximately 64/1024/3584 tokens, with a common output limit of 128, greedy sampling, and the same seed; save exact input token counts rather than substituting character counts. All cases must load independently, generate finite output, read back actual cache class/precision/chunking, and avoid truncation or silently dropped parameters.
3. **Repeated performance measurements →** Run each previous combination three times in independent processes with a predetermined interleaved order; exclude extra warm-up cases from statistics. Record medians and every individual value rather than choosing only the best. For each model, list short/long input results separately at minimum. If actual output length differs under the same max_tokens, TTFT can be compared directly; Decode speed must also include actual token counts and compare only sufficiently long cases.
4. **Effect attribution →** For long inputs, add q4/2048 and auto/512 diagnostic combinations, three times per model, to separate cache quantization from chunking effects. Presets without repeatable reductions in memory/first-token latency must not claim benefits; they may remain marked pending verification or show why they cannot be applied.
5. **Text correctness →** Freeze short question-answer, number extraction, JSON structure, and beginning/middle/end retrieval cases in long text. First compare token IDs/text across auto chunk sizes; if they differ, preserve differences and check answers. q4 may differ numerically/textually but must report each correctness rate and regression; absence of NaN does not substitute for quality acceptance.
6. **Cache isolation and identity →** Use independent tasks A/B with the same prefix but different endings, each compared with its own cold-start baseline; use fresh caches after changing model/adapter/template/precision and record that each cache starts empty. Media input remains rejected by the current text capability; this proves no incorrect reuse on the current path, not implementation of multimodal shared caching.
7. **Cancellation and resources →** Cancel during long Prefill and low-memory Decode separately, confirm worker/process-group cleanup without completed, and then verify that a new task generates normally; caches must not enter generic diagnostic packages or be exported as works.
8. **Ordinary-user UI →** Open differences, cancel, apply, submit, inspect actual parameters, and reload recipes for each preset; running snapshots remain unchanged; invalidation explanations are correct after changing model/format/device. Operate through Browser/Computer Use and save visible results plus API/worker evidence.

Completing 1—8 closes only M2's local text preset/cache subitem; NVIDIA, remote operation, other models, shared prefix caching, multimodal caching, Prefill/Decode separation, and the complete M2 gate still require their own evidence.

<a id="7-本次核查的验证边界"></a>

## 7. Validation boundary of this audit

This audit ran pure Python AST/structural checks and theoretical byte calculations, recorded in `.artifacts/m2-kv/source-audit-v1/source-check.json`; it only read dependencies, the current model configuration, and worker, without executing a model. It confirmed upstream parameter defaults, explicit rejection of rotating-cache quantization, Qwen2 architecture, and the default cache path. This document's test matrix has not yet run; `source-check.json` explicitly marks `gpu_execution` and `runtime_presets_implemented` as false.
