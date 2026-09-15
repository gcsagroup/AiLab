<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/15-sources-and-glossary.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/15-sources-and-glossary.md) · [English](15-sources-and-glossary.md)
<!-- translation-navigation:end -->

<a id="参考资料来源边界与术语"></a>

# References, Source Boundaries, and Glossary

Version: 1.0 · Checked: 2026-09-09.

<a id="1-如何使用这些资料"></a>

## 1. Using These References

The product structure comes from the final demo confirmed by the user; upstream references verify technical concepts, adaptation boundaries, and candidate implementation paths. An upstream README claiming a feature exists does not mean GCSA-AiLab has integrated it or passed real-device tests.

Links on this page point to dynamic documentation or project pages. Implementation must additionally lock specific versions, commits, model revisions, and dependencies. Do not put floating states such as today / latest into immutable execution snapshots.

<a id="2-官方参考资料"></a>

## 2. Official References

| ID | Official reference | Use within this document set | Still to confirm during implementation |
| --- | --- | --- | --- |
| SRC-01 | [MLX-LM](https://github.com/ml-explore/mlx-lm) | Apple local text runtime and training candidates, caching and quantization concepts | Version, model family, training methods, actual devices |
| SRC-02 | [llama.cpp](https://github.com/ggml-org/llama.cpp) | Multiple-hardware inference, GGUF, backend build boundaries | Specific build, backend, models, operators |
| SRC-03 | [vLLM tuning](https://docs.vllm.ai/en/latest/configuration/optimization/) | Prefill, scheduling, performance-comparison design | Version defaults, model architecture, devices |
| SRC-04 | [vLLM MTP](https://docs.vllm.ai/en/latest/features/speculative_decoding/mtp/) | MTP depends on model capabilities and companion implementations | Native components, target version, actual acceptance |
| SRC-05 | [DFlash official project](https://github.com/z-lab/dflash) | Target / draft pairing, local and service paths | Exact target and draft versions, thinking mode, engine |
| SRC-06 | [Qwen3-4B model description](https://huggingface.co/Qwen/Qwen3-4B) | Specific model reference for thinking switches and template control | Tokenizer, template, service-parameter mappings |
| SRC-07 | [TRL](https://huggingface.co/docs/trl/index) | Candidate post-training library for SFT, DPO, GRPO, and others | Current trainer APIs, experimental status, dependencies |
| SRC-08 | [PEFT](https://huggingface.co/docs/peft/index) | LoRA, parameter-efficient update methods, adapter relationships | Module selection, base compatibility, precision, training methods |
| SRC-09 | [Diffusers memory optimization](https://huggingface.co/docs/diffusers/optimization/memory) | Conditional VAE and offloading optimization design | Model pipeline, device, speed and quality impact |
| SRC-10 | [Core ML Typed Execution](https://apple.github.io/coremltools/docs-guides/source/typed-execution.html) | CPU / GPU / ANE graph execution and allocation boundaries | Artifacts, shapes, operating-system version, actual allocation evidence |
| SRC-11 | [AMD ROCm compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html) | Device, operating-system, and software combination checks | Specified GPU, driver, library versions |
| SRC-12 | [OpenVINO devices and modes](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html) | Intel CPU / GPU / NPU plugin paths | Plugins, model formats, device generations |
| SRC-13 | [Tauri sidecars](https://v2.tauri.app/develop/sidecar/) | Desktop-host and external-execution-process approach | Platform packaging, signing, lifecycle |
| SRC-14 | [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) | Control-service startup / shutdown design reference | Actual service-resource release, process management |
| SRC-15 | [SQLite WAL](https://www.sqlite.org/wal.html) | Local metadata-database transaction and concurrency design reference | Backups, checkpoints, migrations, file consistency |

These references were accessed and checked during writing. They do not support claims that this project supports any untested combination, nor were legal conclusions about specific licenses derived from them.

<a id="3-尚未完成的来源核查"></a>

## 3. Source Checks Not Yet Completed

Heretic, Abliterix, and custom image networks retain user-requested product entries in the prototype. This round did not complete specialized reviews of their exact source repositories, dependencies, algorithms, and distribution conditions. Documents therefore specify only inputs, outputs, evaluation, and work awaiting validation, without claiming integration or publishability.

Prototype model entries such as CosyVoice, Whisper, RVC, MusicGen, Wan, and FLUX also need specific versions and capabilities locked in their work packages. A name appearing in the demo does not imply real support in any installation environment. AI Beauty code-reuse scope requires review after directories, versions, and dependencies are defined; no project code was copied this round.

<a id="4-训练术语"></a>

## 4. Training Terms

| Term | Explanation | Common confusion |
| --- | --- | --- |
| SFT | Supervised fine-tuning: learns given inputs and target responses | Not mutually exclusive with LoRA; STF is interpreted as SFT in this context |
| CPT | Continued pretraining: adapts to a domain using continuous corpora | Here means continued pretraining, not every method with the same abbreviation in other libraries |
| DPO | Direct preference optimization using preferred / dispreferred responses | Not equivalent to supervised training on correct answers |
| GRPO | Policy optimization based on within-group comparisons and rewards | Increased rewards do not imply improved independent capabilities |
| PPO | Proximal policy optimization; training paths depend on reward and policy configuration | Interfaces and experimental status vary by library version |
| LoRA | Updates a subset of parameters using low-rank adapters | Usually still requires base-model weights to run |
| QLoRA | A family of adapter-training approaches using a quantized base model | Does not mean all quantized models can train |
| Full-parameter updates | Updates all weights open to training | Resource needs differ from adapter training |
| Selected modules | Trains only selected layers or connecting modules | Must record resolved actual module names |
| Gradient accumulation | Accumulates multiple microbatches before an optimizer update | Does not increase actual per-step micro batch |
| Gradient checkpointing | Reduces activation storage through partial recomputation | Different from saving training checkpoints |
| Checkpoint | Model and training state for resumption | Weights alone may not continue the original training trajectory |
| Distillation | Trains a student using teacher behavior or distributions | Not model merging |
| Model merging | Combines compatible weights or adapters according to rules | Matching structure does not guarantee semantic compatibility |
| Quantization | Reduces representation precision of weights or states | Smaller size does not guarantee better speed and quality |
| Conversion | Changes a model's runtime representation / format | Successfully generating a file does not mean it runs on the target device |

<a id="5-推理与优化术语"></a>

## 5. Inference and Optimization Terms

| Term | Explanation | Product wording requirements |
| --- | --- | --- |
| Token | A discrete unit processed by the model | Cannot be replaced directly by a Chinese-character count |
| Context window | Input and output range the model can process for this request | History, templates, and media also consume the budget |
| Thinking mode | Reasoning behavior supported by the model and template | Distinguish disabling computation from hiding output |
| KV Cache | Caches intermediate key / value states for existing tokens | Separate from weight quantization and prefix reuse |
| Prefix cache | Reuses computation for repeated input prefixes | Explicit cache scope and invalidation conditions |
| Prefill | Initial computation over the input | Timed separately from subsequent token-by-token generation |
| Decode | Generates subsequent output tokens | Separate concurrent throughput from single-request speed |
| Chunked Prefill | Schedules input computation in chunks | Not simply equivalent to any chunking parameter |
| Continuous batching | Continuously schedules multiple requests during execution | Not training batch size |
| Attention backend | Implementation path for attention computation | Determined by model, engine, and device |
| CUDA Graph | Captures and replays applicable GPU execution workflows | Requires warmup, shape, and memory conditions |
| Speculative decoding | Draft proposes candidates and the target model verifies them | An additional draft model may bring no speed benefit |
| MTP | Multi-token-prediction capabilities / components | Depends on target-model and engine support |
| DFlash | Speculative decoding using a block-diffusion draft | Requires matching target, draft, mode, and versions |
| Acceptance rate | Fraction of draft candidates accepted by target verification | State the denominator and statistical definition |
| CPU Offload | Moves part of a model or state into CPU memory | May reduce GPU memory while increasing transfer latency |
| VAE Tiling / Slicing | Tiled / sliced image decoding | Enabled only for corresponding pipelines |
| Tensor parallelism | Splits tensor computation across devices | Not data parallelism and does not directly increase effective training batch size |
| Effective configuration | Parameters ultimately used by the executor | Saved separately from the configuration requested by the form |

<a id="6-硬件与工程术语"></a>

## 6. Hardware and Engineering Terms

| Term | Explanation | Boundary |
| --- | --- | --- |
| Metal / MPS | Apple GPU runtime interfaces / backends | Not ANE |
| MLX | Model-computation framework for Apple Silicon | Models and methods need specific adaptation |
| ANE | Apple Neural Engine | Allowing participation does not mean all operators actually run on it |
| Core ML | Interface in Apple's model runtime / conversion ecosystem | Requires corresponding format artifacts and device checks |
| CUDA | NVIDIA compute stack | Constrained by GPU architecture, drivers, and library versions |
| ROCm / HIP | AMD-related compute software stack / programming interface | Validate against the specific compatibility matrix |
| oneAPI / SYCL | Intel-related and other toolchain / programming-standard paths | Initial product validation uses Intel GPU combinations |
| OpenVINO | Model optimization and inference toolchain | CPU, GPU, and NPU plugins validated separately |
| Vulkan | Cross-platform GPU interface | Must be supported by the engine build and device driver |
| Unified memory | Memory in a system where CPU / GPU share addressing or physical resources | Not directly equivalent to dedicated GPU-memory capacity |
| Revision | A resource version that can be fixed | Floating latest is not evidence |
| Manifest | File and metadata list | Must match actual file digests |
| Idempotency | Repeated requests do not repeat the same side effect | Must include content-conflict handling |
| SSE | A connection method for server-to-client events | Recovers after disconnection using event cursors |
| Sidecar | Independent process accompanying the main application | Independent startup / shutdown, packaging, fault management |
| ADR | Architecture decision record | Records rationale, alternatives, conclusions |

<a id="7-资料更新规则"></a>

## 7. Reference Update Rules

Recheck official sources when starting an adapter work package, lock versions, and save a minimum reproducible test. During upgrades, revalidate capability tables, parameter mappings, and reports according to impact. If official references become unavailable or change, update links and explanations while preserving the version identity used for original acceptance.
