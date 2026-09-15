<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/04-runtime-and-hardware.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/04-runtime-and-hardware.md) · [English](04-runtime-and-hardware.md)
<!-- translation-navigation:end -->

<a id="运行参数优化与硬件适配规格"></a>

# Run Parameters, Optimization, and Hardware Support Specification

Version: 1.0 · Date: 2026-09-09 · Status: requirements baseline from the final runtime optimization Demo; real backends await integration.

Related documents: [API contracts](07-api-and-task-lifecycle.md), [Architecture](06-architecture-and-adapters.md), [Performance acceptance](11-testing-and-acceptance.md).

<a id="1-核心原则"></a>

## 1. Core principles

Execution capability is determined jointly by “model version × model format × tokenizer/processor × engine version × operating system × driver × hardware × parameter combination.” A brand name, completed file download, or successful device connection is insufficient to establish support.

The product must retain the user-requested configuration, validation results, the engine's actual execution configuration, and execution evidence. Every field has applicability conditions, units, and a stage at which it takes effect. A large JSON text box cannot replace a complete configuration interface, and similarly named parameters in different engines must not be mapped unconditionally.

<a id="2-参数层级与生效时机"></a>

## 2. Parameter levels and when they take effect

| Level | Examples | Action after modification | Relationship to existing tasks |
| --- | --- | --- | --- |
| Individual request | temperature, maximum output, stop sequences, thinking mode | Takes effect on the next request | Does not modify an executing request |
| Session/input management | Context limits, history truncation, cache isolation | Recalculate inputs and cache keys | Does not change saved results |
| Engine instance | KV dtype, batching budget, CUDA Graph | May require reloading or restarting the instance | Drain first or create a new instance; do not silently interrupt tasks |
| Model loading | Weight precision, adapters, GPU offloading, parallel layout | Load and check a new instance | Preserve task ownership on the old instance |
| Deployment | Prefill/Decode separation, remote connectors | Separate deployment and acceptance | Do not deploy implicitly through request forms |

Before application, the interface shows which changes require restarting, reloading, or retokenization. Defaults come from versioned model templates; actual execution should display resolved values or an explicit automatic policy.

<a id="3-生成与上下文字段"></a>

## 3. Generation and context fields

“Demo default” in this section describes only the current prototype. Formal defaults are generated from capability declarations and recommended model configurations.

| Field | Meaning | Demo default | Formal validation and semantics |
| --- | --- | --- | --- |
| `thinking` | Thinking mode | `default` | Default/off/on; switchable only when explicitly supported by the model and template |
| `context` | Context limit | 8192 token | Limits the total of input, history, system instructions, media tokens, and output |
| `maxOutput` | Maximum output | 1024 token | Must leave room for input; final validation uses actual tokenization |
| `overflow` | Overflow handling | `reject` | Reject or truncate the oldest conversation; preserve system messages and tool-call integrity |
| `temperature` | Temperature | 0.7 | Finite and nonnegative; the engine maps 0 to a deterministic policy and records it |
| `topP` | Cumulative-probability sampling | 0.9 | Valid range defined by the engine; an empty value must not become 0 |
| `topK` | Candidate count | 20 | Use 0 as unlimited only when the adapter actually interprets it that way |
| `minP` | Minimum relative probability | 0 | Must not be silently ignored when the sampler is unsupported |
| `repeatPenalty` | Repetition penalty | 1.05 | Distinct from presence/frequency penalty; not a direct substitute |
| `stop` | Stop sequences | Empty | The formal product uses a string array parsed from line-based interface input |
| `stream` | Streaming output | On | Distinguish server streaming, frontend display, and final-result persistence |
| Task `seed` | Random seed | 42 | Saved with the result; identical seeds across engines do not promise word-for-word identical output |

<a id="31-关闭思考"></a>

### 3.1 Disabling thinking

Implement one explicit combination using the template controls in the [Qwen3-4B model description](https://huggingface.co/Qwen/Qwen3-4B) as a reference. Actual adaptation must verify how the thinking toggle reaches the template and inference interface; removing thinking text after generation is insufficient.

If the model has only one behavior mode, the template does not accept a toggle, or the remote service lacks support, show Model default and explain why. Record output-display policies separately from model thinking computation. Thinking budget is a parameter to be enabled later according to engine declarations; the current Demo does not implement separate budget control, and `maxOutput` must not stand in for a complete thinking budget.

<a id="32-上下文预算"></a>

### 3.2 Context budget

Before submission, calculate actual input tokens using the current model's tokenizer/processor. Multimodal inputs must include media tokens after model processing, not merely the question's character count. Reserve space for system messages, template markers, and output, and apply the user's chosen policy when the limit is exceeded.

The Demo's 512—32,768 validation range is illustrative, not a product limit for all Qwen models or engines. The formal maximum comes from model capabilities, engine configuration, and resource constraints; context-extension methods require separate versioning and quality verification.

<a id="4-kv-cache-与前缀缓存"></a>

## 4. KV Cache and prefix caching

| Field | Meaning | Demo default | Formal requirements |
| --- | --- | --- | --- |
| `kvPrecision` | KV storage precision | auto | List dtype/quantization formats per engine; independent of weight quantization |
| `kvBudget` | KV token capacity/window | 8192 | Label whether the engine interprets it as capacity, a window, or an estimate derived from a budget |
| `prefixCache` | Prompt/prefix reuse | Off | Enable only when the engine genuinely supports it and cache hits can be verified |
| `cacheScope` | Cache isolation | Current task | Project scope may be selected; private inputs are not shared across projects |

The current prototype includes example options of auto/8-bit/4-bit for MLX, auto/f16/q8_0/q4_0 for llama.cpp, and auto/fp8 for serving engines. Real adapters must verify format combinations against versions and devices; these lists must not be assumed to be complete lists of usable options.

Unified interface semantics for KV capacity require care: an MLX rotating-cache window discards older KV, whereas serving engines typically manage capacity through VRAM budgets, block management, or specific cache configurations. Adapters must report actual mappings; when equivalent mapping is impossible, change the field label and explain why.

Cache keys include at least model version, weight/adapter combination, tokenizer, chat template, input-token prefix, KV precision, and isolation scope. Invalidate them after model/template/adapter changes. Cache data must not enter ordinary diagnostic packages; cache cleanup must not delete user models or works.

<a id="5-prefill-与-decode-调度"></a>

## 5. Prefill and Decode scheduling

| Field | Meaning | Demo default | Applicability and acceptance |
| --- | --- | --- | --- |
| `prefillChunk` | Input-processing chunk size | 512 token | Distinguish single-request step size from server-side chunked prefill |
| `chunkedPrefill` | Server-side chunk scheduling | Off | Adapt to specific vLLM/SGLang versions and architectures |
| `batchTokens` | Batching token budget | 2048 | Check relationships with chunks, maximum sequence length, and scheduling rules |
| `decodeBatch` | Concurrent sequence count | 1 | Concurrency limit for this instance; not training batch size |
| `attention` | Attention implementation | auto | Determined jointly by model operators, engine, and device |
| `graphs` | CUDA Graph | Off | Requires suitable shapes, warmup, VRAM, and engine support |
| `splitPD` | Prefill/Decode separation | Off | A deployment capability requiring connectors and failure recovery |
| `prefillEndpoint` | Prefill service endpoint | Empty | Verify service identity, model version, and availability |
| `decodeEndpoint` | Decode service endpoint | Empty | Must be compatible with Prefill's KV format and transfer protocol |

Use the [vLLM tuning guide](https://docs.vllm.ai/en/latest/configuration/optimization/) to define test conditions, without hardcoding upstream defaults as product defaults. Larger batches usually serve throughput; smaller input chunks may affect time to first token and scheduling fairness. Decisions must be based on measurements.

Separate Prefill/Decode deployment has no real service or KV-transfer connector in the Demo and should currently remain blocked. Formal implementation requires additional verification of remote identity, transfer failures, model-version mismatches, cache-transfer timeouts, and request recovery; two URL fields alone do not establish support.

<a id="6-推测解码"></a>

## 6. Speculative decoding

| Strategy | Required dependencies | Configuration | Verification focus |
| --- | --- | --- | --- |
| Off | Normal target model | No draft component | Normal baseline |
| Ordinary draft model | Target, draft, tokenizer/vocabulary compatibility, engine adapter | Draft version, precision, speculative length | Distribution/correctness, acceptance rate, total latency |
| MTP | Native target-model prediction capability or matching component, engine implementation | Prediction component, speculative length, verification mode | Component matching, stepwise verification, and regression |
| DFlash | Target model, matching block-diffusion draft, engine and version | Draft pairing, block size, draft precision | Family/thinking-mode conditions, acceptance rate, verification cost |

Demo fields are `speculation`, `draftModel`, `draftReady`, `specTokens`, and `draftPrecision`. Of these, `draftReady` is currently only simulated state; real implementation must separate download completion, hash verification, loading, and pair verification into four stages.

The [vLLM MTP documentation](https://docs.vllm.ai/en/latest/features/speculative_decoding/mtp/) treats MTP as a path dependent on model capabilities; the Qwen3-4B in the current Demo must not gain native prediction components merely because a user selects MTP.

The [official DFlash project](https://github.com/z-lab/dflash) lists specific models and local/serving backend paths. Do not broadly claim that DFlash only supports CUDA or that any MLX model can enable it. The current Demo uses a matching example for Qwen3-4B in non-thinking mode; formal implementation pins target, draft, and engine revisions plus thinking policy before acceptance.

Speculative decoding selects only one strategy by default. Enabling it does not guarantee a speedup; measure draft overhead, acceptance rate, Prefill, Decode, total latency, throughput, and peak memory. Reject incompatible pairs rather than falling back to standard generation while still displaying speculative acceleration as enabled.

<a id="7-通用硬件与加载字段"></a>

## 7. General hardware and loading fields

| Field | Meaning | Demo default | Formal rules |
| --- | --- | --- | --- |
| `device` | Execution location | Global default device | Fixed device identifier, not merely a mutable display name |
| `accelerator` | Hardware backend | Device template | Verify vendor, architecture, operating system, and driver |
| `engine` | Runtime engine | Model category and backend | Record actual binary/package version |
| `precision` | Weight compute precision | auto | FP16/BF16/FP32 are candidates only; reject unsupported devices |
| `memoryLimit` | Memory-use budget | 80% | Explain GPU VRAM, unified memory, and system memory separately |
| `cpuThreads` | CPU threads | 8 | Distinguish compute threads from input-processing threads |
| `gpuLayers` | llama.cpp GPU-offloaded layers | auto | Record actual offloading; a request for all does not imply complete success |
| `tensorParallel` | Tensor-parallel device count | 1 | Validate device count, topology, model partitioning, and engine support |
| `computeUnits` | Core ML compute-unit policy | Backend-dependent | Policies such as CPU_ONLY/CPU_AND_GPU/CPU_AND_NE/ALL |

The global device list retains examples of the local machine, owner-operated servers, cloud instances, AMD workstations, Intel workstations, and CPUs. Real device entries must come from probe data; “Apple” and “Linux” in the Demo must not be treated as actual hardware facts about the local machine or user servers.

<a id="8-硬件适配目标矩阵"></a>

## 8. Target hardware-support matrix

All entries are currently **target paths awaiting verification**. The first-phase focus is Apple local inference and NVIDIA Linux training/inference; other paths are added by stage.

| Hardware/software stack | Candidate engines | Run targets | Training targets | Key restrictions and checks |
| --- | --- | --- | --- | --- |
| Apple GPU/Metal | MLX-LM, MLX-VLM, llama.cpp | Text and adapted multimodal models | Model methods supported by MLX | Unified memory, model conversion, processor and operator support |
| Apple GPU/MPS | PyTorch, Transformers, Diffusers | Media and adapted models | Verify per model | Not equivalent to CUDA; record missing operators and fallbacks explicitly |
| Apple ANE/Core ML | Core ML | Converted on-device models | Not a general-purpose training backend | Graph partitioning, model format, static/dynamic shapes, and device execution |
| NVIDIA/CUDA | PyTorch, vLLM, SGLang, llama.cpp, Diffusers | Text, multimodal, media | Verified methods such as PEFT/TRL | GPU architecture, driver, CUDA, VRAM, and precision |
| AMD/ROCm/HIP | PyTorch, vLLM, SGLang, llama.cpp | Adapted models | Verify per method | Exact GPU, system, driver, and library versions |
| Intel GPU/oneAPI/SYCL | Adapted engines such as llama.cpp | Adapted models such as GGUF | Assess separately; not inferred from inference capability | Build backend, Level Zero/SYCL runtime, and device generation |
| Intel/OpenVINO | OpenVINO | IR/convertible models on supported plugins | Not a first-phase general-purpose training backend | CPU/GPU/NPU plugins, model format, and operators |
| Vulkan GPU | llama.cpp and others | Models supported by the build | Not a first-phase training backend | Drivers, extensions, and actual graphics devices |
| CPU | llama.cpp, PyTorch, and others | Small models and regression baselines | Small-scale functional tests | Memory, instruction set, and threads; no promise of usable large-model speed |

Official boundary references: [Core ML graph execution](https://apple.github.io/coremltools/docs-guides/source/typed-execution.html), [ROCm compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html), [OpenVINO device modes](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html), [llama.cpp](https://github.com/ggml-org/llama.cpp).

<a id="81-ane-的产品表达"></a>

### 8.1 How the product describes ANE

ANE is compute hardware, while Core ML is one runtime interface for selecting that path; the Apple GPU path used by MLX is separate. Choosing CPU + ANE permits those compute units to participate but does not guarantee every operator runs on ANE. Formal reports should retain the Core ML compute plan or available execution evidence; when direct attribution is unavailable, label it “Actual ANE allocation unconfirmed.”

<a id="82-训练与运行能力分别判断"></a>

### 8.2 Assess training and run capabilities separately

A device's ability to run GGUF does not mean it can train with that file; ROCm loading a model does not mean it supports the selected QLoRA implementation; Intel GPU SYCL inference does not imply a corresponding training backend. The current Demo's training side still uses simplified checks, which must be replaced with unified capability queries in real implementation.

<a id="9-媒体模型参数"></a>

## 9. Media-model parameters

| Field | Purpose | Demo default | Acceptance requirements |
| --- | --- | --- | --- |
| `scheduler` | Image/video sampling scheduler | Model default | Scheduler matches checkpoint configuration |
| `sampling` | Sampling steps | 20 | Result recipe matches actual pipeline parameters |
| `cfg` | Guidance strength | 7 | Enable only for models using this meaning |
| `vaeTiling` | Tiled VAE decoding | Off | Check tile boundaries, memory, and quality |
| `vaeSlicing` | Batched VAE decoding | Off | Check batch dimension and support conditions |
| `offload` | CPU offloading policy | None | Distinguish component/sequential offloading and check transfer overhead |
| `compile` | Compilation optimization | Off | Separate initial compilation from warmed-up performance and record caches |
| `frames`/`fps` | Generated frame count/frame rate | 81/16 | Consistent with duration, container, and model limits |
| `sampleRate` | Output sample rate | 24000 Hz | Separate native engine sample rate from postprocessing resampling |
| `audioChunk` | Audio chunk duration | 200 ms | Enable only when supported by the streaming adapter |
| `streamAudio` | Chunked audio output | Off | Playable chunks are actually received in order, and the final file is complete |
| `speed` | Speaking rate | 1.0 | Record model control and postprocessing speed changes separately |

Use [Diffusers memory optimization](https://huggingface.co/docs/diffusers/optimization/memory) to build conditional configurations; do not treat VAE, CFG, Euler, or DPM++ as universal capabilities of all image models. A custom image-fusion network may use none of these parameters.

Video duration, frame count, and frame rate in the Demo remain illustrative configurations. The real product must perform consistent conversions and check contradictions before submission; it must not save several conflicting “final durations.”

<a id="10-能力状态与诊断"></a>

## 10. Capability states and diagnostics

Capabilities have at least six states: unknown, preparation required, supported, conditionally supported, unsupported, and verified. The interface shows the basis and time of a state: files, probes, configuration checks, or hardware reports.

Recommended diagnostic order: device reachable → hardware probe → drivers and runtimes → engine version → model files/format → loading → fixed-sample inference → target optimization verification. Save each step separately so that “Connection successful” does not conceal later failures.

<a id="11-参数验收合同"></a>

## 11. Parameter acceptance contract

Every formally enabled parameter must complete field-type validation, applicability validation, backend mapping, actual-value readback, behavioral-effect verification, recipe saving, recipe reloading, and error messaging. Performance switches additionally require on/off comparisons and regression reports.

Requests not adopted by the executor must be rejected or receive explicit change confirmation; “Saved in the interface” must not be treated as “Optimization took effect.” See [11](11-testing-and-acceptance.md) for complete cases.
