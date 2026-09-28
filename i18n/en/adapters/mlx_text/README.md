<!-- translation-navigation:start -->
[简体中文](../../../../adapters/mlx_text/README.md) · [繁體中文](../../../zh-TW/adapters/mlx_text/README.md) · [English](README.md)
<!-- translation-navigation:end -->

<a id="本地-mlx-文本适配器"></a>

# Local MLX text adapter

2026-09-10: Real inference, SFT + LoRA parameter updates, source identity verification, independent reload, MLX 4-bit quantization export, cancellation, and invalid-combination checks passed on Apple M5 Max. This is the Apple technical experiment and executor; it does not establish acceptance of the NVIDIA portion of TV-01, TV-03 cross-device round trips, model quality admission, or the complete training product.

<a id="已验证组合"></a>

## Verified combination

- macOS 26.6.2, Apple M5 Max, 128 GiB unified memory; the actual MLX default device is `Device(gpu, 0)`; ANE was neither used nor claimed.
- Python 3.13.9, MLX 0.32.2, MLX-LM 0.31.3; see `requirements.lock.txt` for all installed versions.
- Official `Qwen/Qwen2.5-0.5B-Instruct`, revision `7ae557604adf67be50417f59c2c2f167def9a775`, unquantized BF16 weights; license files are retained with the model.
- Weight SHA-256: `fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe`; size 988,097,824 bytes.
- The source model is used read-only; digests of the model, tokenizer, template, environment, actual parameters, and every output file are written into execution evidence.

Source architecture checks support fixed `qwen2` combinations: 0.5B (hidden dimension 896, 24 layers) and 7B (hidden dimension 3584, 28 layers). 7B accepts only an unquantized base; weight quantization and q4 KV cache are not enabled. 0.5B retains its existing quantization scope. Matching architecture does not establish acceptance of all derived weights or business quality. The historical evidence above describes the first combination; the new source evidence boundary is stated at the end.

<a id="准备与复跑"></a>

## Preparation and reruns

Run from the project root; all relative paths in these commands are relative to that directory. The existing environment and public experimental model are already prepared and need no further download.

```sh
python3.13 -m venv adapters/mlx_text/.venv
adapters/mlx_text/.venv/bin/python -m pip install -r adapters/mlx_text/requirements.lock.txt
adapters/mlx_text/.venv/bin/python adapters/mlx_text/prepare_model.py
adapters/mlx_text/.venv/bin/python -m pytest tests/mlx -q
adapters/mlx_text/.venv/bin/python tests/mlx/run_real_probe.py --evidence .artifacts/m0-mlx/new-run
adapters/mlx_text/.venv/bin/python tests/mlx/run_m3_probe.py --evidence .artifacts/m0-mlx/new-m3-run
```

The final evidence directory must not already exist. `prepare_model.py --verify-only` only verifies the current model. Downloading requests only 9 public files from the fixed revision and writes them to the project's `.artifacts/models/Qwen2.5-0.5B-Instruct`; it does not modify `/Users/lazy/Models` or the user's existing Hugging Face model cache. Earlier Xet downloads and short-timeout HTTP failures were never treated as successes; the download ultimately succeeded through HTTP retries with weight-digest verification.

<a id="控制服务合同"></a>

## Control service contract

Python: `adapters/mlx_text/.venv/bin/python`; the controller must resolve and use an absolute path.

```sh
adapters/mlx_text/.venv/bin/python adapters/mlx_text/preflight.py --snapshot SNAPSHOT --output-dir EMPTY_OUTPUT_DIR
adapters/mlx_text/.venv/bin/python workers/mlx_worker.py --snapshot SNAPSHOT --output-dir EMPTY_OUTPUT_DIR
```

Snapshot fields: `attempt_id`, `operation`, `model_path`, `input`, `runtime`. A complete `model_manifest=[{path,size,sha256},...]` and `model_manifest_digest` are mandatory; training additionally supplies a single `messages` JSONL file's absolute `dataset_path`, its single-file `dataset_manifest`, and `dataset_manifest_digest`. Manifest digests use standard JSON serialization with UTF-8, sorted keys, no extra whitespace, and unescaped non-ASCII characters, followed by SHA-256, matching the control service; paths are relative.

The input file set, sizes, and digests are rechecked before and after execution; newly added unregistered weights also block execution. Production workers must additionally supply the `tokenization_recipe_digest` returned by preflight and recheck tokenizer, template, and supervision-implementation digests after loading. Missing identity fields reject execution; there is no “trust by default when no manifest is supplied” mode. Direct developer probes likewise explicitly freeze manifests and run preflight first. Old snapshots from `run-20260910-01` through `03` remain historical evidence only and cannot be passed directly to the hardened worker.

Generation may supply `adapter_path` at the snapshot's top level, but must also supply `adapter_manifest`, `adapter_manifest_digest`, and `adapter_training_recipe_digest`. Only adapters produced by this executor with matching complete base manifests/templates/source training tokenization recipes/modules/parameter shapes are accepted; the complete adapter file set is checked before and after execution. Training's `adapter_config.json` stores `base_input_manifest_digest` and `training_recipe_digest`; historical artifacts missing these two origin fields cannot enter the production executor directly, and origin is never guessed from directory names. Training and quantization accept no adapters; incremental resumed training and attaching LoRA to a quantized base are unsupported.

Preflight loads only the real tokenizer and returns a single JSON object with `can_submit`, `blocking`, `effective_config`, `tokenization_recipe_digest`, `recipe`, and `check_report`. Success exits 0; blocking exits 1. The script creates no output directory and loads no model weights; candidate checks read safetensors parameter headers and file digests. The controller must bind the recipe digest together with current data, parameters, and file identity to submission checks.

Executor stdout contains only line-delimited JSON; library logs go to stderr. Event `type` is `phase`, `token`, `metric`, `completed`, or `error`. `token` contains `text`, `token_id`, and `generation_tokens`; `completed` contains relative paths within the output directory, SHA-256, `media_type`, and actual `effective_config`. Derived `effective_config` is a read-only record and cannot be reused verbatim as writable `runtime` for the next run.

The executor disables automatic Hugging Face network access within its process; models must use explicit local paths. The output directory must be empty, with no symlink redirection or overlap with models/data. Failed execution may leave diagnostic or intermediate files; the controller may register formal artifacts only after receiving the completion event, observing normal process exit, and verifying every digest.

SIGTERM/SIGINT set a cancellation request, checked at actual computation synchronization points; execution exits 130 without sending `completed`. `AILAB_CONTROL_PID` may be supplied and must equal the actual parent process. The executor stops itself if the parent controller disappears; if the underlying operator does not return, it waits at most another 10 seconds before exiting itself, without signaling other processes. The control service manages resource exclusion and queuing.

<a id="可写参数"></a>

## Writable parameters

Generation: `engine=mlx`, `device_id=apple-gpu`, `seed` (0—2³²−1), `max_tokens` (1—2048, default 128), `temperature` (0—2, default 0), `top_p` (0.01—1, default 1). Prompts are limited to 16,000 characters, with actual tokenized input plus maximum output limited to 4096. temperature=0 uses greedy selection, in which top_p does not participate; actual caching uses MLX's default unquantized full KV. These are conservative product limits of the current adapter, not theoretical hardware limits.

Fixed training settings: `training_type=sft`, `update_method=lora`, `recipe_id=qwen25-assistant-only-v1`, `batch_size=1`, `gradient_accumulation=1`, `optimizer=adamw`, `weight_decay=0`, `lora_dropout=0`.

Adjustable training settings: `steps` (1—200, default 4), `learning_rate` (1e-7—0.01, default 1e-4), `max_seq_length` (32—2048, default 512), `lora_rank` (1—32, default 4), `lora_alpha` (1—64, default 8), `num_layers` (last 1—28 layers, at most 24 layers for 0.5B, default 2), and `seed`. Target modules are fixed to `self_attn.q_proj` and `self_attn.v_proj`. MLX scale is explicitly `alpha / rank`.

AdamW explicitly fixes betas=[0.9,0.999], eps=1e-8, bias_correction=true; the learning rate is constant, with no warmup/gradient clipping. Source BF16 weights are frozen and LoRA parameters are FP32; data cycles in file order, and seed controls LoRA initialization. Each step emits real loss and supervised-token count; completion saves LoRA files and parameter changes. Intermediate checkpoint restoration, resumed training, full-parameter training, quantized training, packing, multimedia, and NVIDIA are not exposed.

Quantization: `operation=quantize`, `input={}`; `runtime` allows only `engine=mlx`, `device_id=apple-gpu`, `seed`, `bits=4`, `group_size=64`, and `mode=affine`. It produces an independent `model/` directory from unquantized source weights, retains tokenizer, template, and licenses, and splits safetensors using an approximately 128 MiB tensor budget; the output model manifest and source digests are stored in `conversion.json`. This format supports only generation; direct requantization, quantized training, and mixing in adapters are prohibited. Model-size changes are measured, without promising inference-speed or quality improvements.

<a id="固定文本评测合同"></a>

## Fixed text evaluation contract

`operation=evaluate`, `input={}`; models and adapters follow the generation contract. `runtime` uses MLX/Apple GPU plus fixed `max_tokens`, `temperature=0`, `top_p=1`, and `seed`, exactly matching the generation configuration in the evaluation rules. Evaluation samples and criteria are each limited to 4 MiB and must be local files specified by complete manifests; `evaluation_dataset_path`/`evaluation_dataset_manifest`/`evaluation_dataset_manifest_digest` and corresponding `evaluation_criteria_*` are mandatory. `evaluation_plan_digest` is the canonical JSON digest containing these two manifest_digest fields.

Sample JSONL uses `{id,category,prompt,rule}`, with 4—64 entries; categories `business`, `format`, `regression`, and `behavior` must all be nonempty. Supported rules are only `exact` (nonempty `expected`, exact comparison after trimming output), `contains_all` (nonempty `keywords`, case-sensitive), `json_equals` (`expected` is an object or array; strictly parse the entire output without removing fences, allowing duplicate fields, or accepting nonfinite numbers), and `manual` (`instruction`, remains pending review). Executable expressions, custom scripts, and remote judges are absent.

Criteria JSON fixes `schema_version=text-rules-v1`, `category_min_pass_rate` (a threshold greater than 0 and at most 1 for each of the four categories), `regression_tolerance` (0—1), and `generation={max_tokens,temperature,top_p,seed}`. Booleans cannot stand in for numbers. Evaluation loads baseline and candidate in two independent child processes, generates against the same frozen samples, and saves each sample's original text, rule verdict, reason, per-category passed/total/pass_rate on both sides, thresholds, regression differences, pending manual reviews, and unknown counts.

Training can bind the same evaluation-plan fields; the executor checks manifests and records the plan digest in adapter metadata. Evaluation's `eligible=true` requires the candidate to meet all fixed thresholds, stay within regression tolerance, have no pending manual or unknown items, and have training artifacts bound to the same plan. Old candidates without pretraining binding can only undergo retrospective evaluation and remain ineligible; the control service must additionally verify the immutable plan version and that its creation time predates the source training submission, rather than trusting only a report boolean. A report's “pass” applies only to that frozen text rule set, not general model quality.

For development validation, first run `tests/mlx/run_evaluation_probe.py --prepare --evidence NEW_DIRECTORY` to seal manual samples, rules, and the fixed 128-step budget, then run without `--prepare`. Existing evidence directories cannot be overwritten, and budget-start records use exclusive creation. Tests include rule success/failure, missing samples, pending manual review, retrospective evaluation, zero thresholds, incorrect types, and modified-file negative cases; new real quality results are determined by the final `summary.json` in the corresponding directory.

<a id="监督配方与验收边界"></a>

## Supervision recipe and acceptance boundaries

The chat template SHA-256 is fixed to `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f`. Recipe digests also include the implementation-source digest of `recipe.py`, preventing supervision logic changes from retaining the old recipe identity. The real chat template tokenizes each prefix, checking consistency between the complete sequence and every assistant-generation prefix; supervision covers only assistant answers and `<|im_end|>`, excluding role headers, system/user content, and the newline following the answer. Labels initially align with input positions; loss uses `input_ids[:-1]` to predict `labels[1:]`, shifting exactly once. Padding is set to -100 by position, preserving real EOS supervision even when EOS and PAD share an ID.

Overlong samples are excluded in full, without truncation or concatenation. Empty answers, system/user-only samples, invalid roles, media, tool calls, special markers, and template changes have explicit errors; execution is blocked if no trainable samples remain in the dataset. Check reports retain exclusion reasons, effective supervision counts, and representative token/label comparisons.

The real experiment used 4 manually created test samples, 4 LoRA steps, and 4 predetermined questions. The source-model digest was unchanged; adapter parameters did change, independent-process reload changed logits, and another independent reload reproduced logits and output. The target code name was not learned reliably, and some output and JSON formatting remained invalid, so loss or output changes are not treated as model quality acceptance.

`m3-20260910-01/report.json` records another 1-step training run under the new provenance contract, strict adapter reload, quantization export, and independent loading. Quantized weights shrank from 988,097,824 to 278,064,792 bytes, 28.14% of source weights; the largest of 3 shards was 134,188,406 bytes. For 4 fixed questions, logit differences between two independent quantized-model reloads were all 0; numerical and textual outputs differed from the base, and all original outputs were retained. Incorrect training recipes and adapter digests were actually blocked; the current 46 tests passed. The fixed questions also include training probes and cannot serve as an independent quality evaluation set; this result is permitted only as an experimental artifact, with candidate quality admission still incomplete.

Official references: [MLX-LM usage and Python API](https://github.com/ml-explore/mlx-lm), [fixed Qwen source revision](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/tree/7ae557604adf67be50417f59c2c2f167def9a775). Specific training APIs and AdamW defaults were rechecked against locally locked source versions.

**Experimental Apple 7B source support (2026-09-28)**: the fixed Qwen2.5-7B-Instruct model completed real LoRA training, pause/resume, and independent recovery comparisons. Ordinary KV cache works; q4 KV cache is blocked after an output failure. Source support does not establish business quality and is not yet included in the installed 046 App. A newly signed candidate and full M6 acceptance remain pending.

Read-only verification of the fixed 7B weights: `python3 adapters/mlx_text/prepare_model.py --variant 7b --verify-only`. Remove `--verify-only` to download the pinned revision; the default remains 0.5B.

**Apple signed candidate update (2026-09-28)**: The fixed App path now contains Ver2.6 (049), including experimental 7B support. The packaged production API completed empty-library restoration, import, source splitting, 2-step LoRA training, generation, and export. The exported adapter also generated independently of the control service using the external pinned base model. These are execution-path checks, not business-quality qualification. Native UI inspection was not performed because the Computer Use runtime could not start; full M6, clean installation, notarization, and distribution remain incomplete.

**Apple larger-base quality experiment (2026-09-28)**: Using the same Ver2.6 (049) candidate, the 7B LoRA completed 192 training steps. On 32 newly frozen questions, the base passed 5/32 and the adapter 31/32: business 0/8→8/8, format 0/8→7/8, regression 5/8→8/8, and behavior 0/8→8/8. The sole failure changed order ID `C5-fo-02-04` to `C5-fo-002-04`. Business improvement passed, but format requires all answers to pass, so no qualified candidate was registered, no extra training was added, and the held-out questions were not retried. These are author-visible synthetic contract samples, not a blind evaluation; full business quality, native UI acceptance, and M6 remain incomplete.
