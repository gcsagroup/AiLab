<!-- translation-navigation:start -->
[简体中文](../../../docs/03-training-and-model-lab.md) · [繁體中文](../../zh-TW/docs/03-training-and-model-lab.md) · [English](03-training-and-model-lab.md)
<!-- translation-navigation:end -->

<a id="训练微调与模型实验室规格"></a>

# Training, Fine-Tuning, and Model Lab Specification

Version: 1.1 · Date: 2026-09-09 · Status: Specification revised following the audit, awaiting implementation; specific adapter combinations and fix effectiveness remain to be verified.

Related documents: [Data specification](05-data-model-and-assets.md), [Runtime and hardware](04-runtime-and-hardware.md), [Evaluation acceptance](11-testing-and-acceptance.md).

<a id="1-三个维度必须分开"></a>

## 1. Three dimensions must remain separate

The training category describes the model being processed, such as language, image, or audio; the training type describes the optimization objective, such as SFT, DPO, or speech-recognition fine-tuning; the parameter update method describes which weights are modified, such as LoRA, QLoRA, full-parameter training, or selected modules.

SFT and LoRA can be combined and must not be mutually exclusive choices in the same dropdown. The user's reference to STF is normalized by context to SFT (supervised fine-tuning); the interface and documentation consistently use SFT.

<a id="2-方法与数据矩阵"></a>

## 2. Method and data matrix

The following table retains the final Demo's method scope; it does not mean every model and hardware combination is already supported.

| Category | Training type | Optimization objective | Data structure | Possible update methods | Preferred acceptance focus |
| --- | --- | --- | --- | --- | --- |
| Language | SFT | Learn instruction and conversational responses | Multi-turn messages | LoRA, QLoRA, full-parameter | Normal tasks and format adherence |
| Language | CPT continued pretraining | Adapt to continuous domain text | text, source_id | LoRA, full-parameter; quantized paths verified separately | Domain capability and general-capability regression |
| Language | DPO | Preference selection | prompt, chosen, rejected | LoRA, QLoRA, full-parameter | Win rate and quality on a fixed preference set |
| Language | GRPO | Verifiable reward optimization | prompt, answer, reward configuration | Adapter or full-parameter | Reward validity and independent answer accuracy |
| Language | PPO | Reward-model-driven optimization | prompt, reward model, reference policy | Declared by the training adapter | Reward, KL, and independent capability checks |
| Multimodal | SFT | Image/text and audiovisual understanding | messages, media | LoRA, full-parameter, selected modules | Real media reading and semantic responses |
| Multimodal | DPO | Media-related preferences | media, prompt, chosen, rejected | Determined by model module structure | Media factuality and preference performance |
| Image | Diffusion-model fine-tuning | Style or domain adaptation | image, caption | LoRA, full-parameter | Subject, style, and content consistency |
| Image | DreamBooth | Subject adaptation | image, caption, trigger | LoRA, full-parameter | Subject preservation and generalization |
| Image | Paired-image training | Fusion, restoration, or editing mappings | source, reference, target | Full-parameter, selected modules | Alignment, structure, and detail regression |
| Video | Video fine-tuning | Shots, motion, and style | video, caption, fps, frames | LoRA, full-parameter | Temporal consistency and motion quality |
| Audio | Speech-synthesis fine-tuning | Voice, pronunciation, and prosody | audio, text, speaker | Full-parameter, selected modules | Pronunciation, intelligibility, and audio quality |
| Audio | ASR fine-tuning | Speech recognition | audio, text, language | LoRA, full-parameter | CER/WER, segmentation, and timestamps |
| Audio | Voice-conversion training | Voice conversion | audio, speaker, pitch features | Defined by the model adapter | Content preservation and target voice |
| Audio | Music-generation fine-tuning | Musical style and conditional generation | audio, description, duration | LoRA, full-parameter | Duration, description adherence, and listening quality |

Candidate training libraries include [TRL](https://huggingface.co/docs/trl/index), [PEFT](https://huggingface.co/docs/peft/index), and [MLX-LM](https://github.com/ml-explore/mlx-lm). Choosing these libraries does not automatically validate the entire matrix; versions, model architectures, quantization, and devices still require adapter verification. Rapidly changing training interfaces such as PPO must have separately pinned versions and a retained compatibility layer.

<a id="3-原型模型模板"></a>

## 3. Prototype model templates

The Demo includes Qwen3-4B, Qwen2.5-VL-3B, Qwen Omni multimodal examples, SDXL, FLUX, a custom image-fusion network, a Wan video example, CosyVoice, Whisper, RVC, and MusicGen.

These names are prototype configuration templates and must not directly become a list of models “verified as supported” in the formal product. Formal entries must record repository identifiers, fixed revisions, weight checksums, tokenizer/processor versions, license-file references, supported inputs, and training modules. Descriptive examples such as Qwen Omni must be replaced with a specific downloadable, loadable version before hardware acceptance.

<a id="4-训练配置字段"></a>

## 4. Training configuration fields

| Parameter | Description | Defaults and constraints | Record location |
| --- | --- | --- | --- |
| Task name | User goal and distinguishing purpose | Required; the display name may be changed later, but the task identifier cannot | Task |
| Model version | Fixed source weights and tokenizer | Required; a floating latest must not be used in completion records | ModelVersion |
| Training type | SFT, DPO, etc. | Generated from capability declarations | TrainConfig |
| Update method | LoRA, QLoRA, full-parameter, selected modules | Validated jointly with the model and training engine | TrainConfig |
| Target modules | Adapter layers/vision connector/output layers | Show the resolved module list | TrainConfig |
| Data version | Input samples and processing results | Fix version and splits at submission | DatasetVersion |
| Training steps/epochs | Stopping condition | The formal product allows one primary condition and shows the conversion logic | TrainConfig |
| Learning rate | Update magnitude | Must be finite and positive; range limited by the adapter | TrainConfig |
| Per-device batch size | Single-device micro batch | Positive integer, linked to memory checks | TrainConfig |
| Gradient accumulation | Update after accumulating multiple microbatches | Positive integer; show effective batch size | TrainConfig |
| Maximum sequence length | Training truncation and packing length | Limited by model and memory | TrainConfig |
| Tokenization and supervision recipe | Tokens and boundaries actually participating in loss computation | Versioned template; check actual tokens and labels before submission | TokenizationRecipe |
| Seed | Reproducible inputs for splitting, initialization, etc. | Specify which random processes use this seed | TrainConfig |
| LoRA rank/alpha/dropout | Adapter structure and scaling | rank exists in the Demo; other fields await real implementation | AdapterConfig |
| Optimizer/scheduler | Optimizers such as AdamW and learning-rate policies | Listed from backend capabilities; execution of arbitrary strings is prohibited | OptimizerConfig |
| Warmup/weight decay/gradient clipping | Training stability configuration | Defaults come from versioned templates; actual values are viewable | OptimizerConfig |
| Training precision | FP32, FP16, BF16, etc. | Verified according to hardware, operators, and engine | EnvironmentConfig |
| Gradient checkpointing | Reduce activation memory through recomputation | Show the speed/memory tradeoff | TrainConfig |
| Save/evaluation interval | Intermediate checkpoints and validation frequency | Positive; support an additional save at completion | CheckpointPolicy |
| Output retention policy | Checkpoint count and storage budget | Do not automatically delete referenced artifacts | ArtifactPolicy |

Explain effective batch size as “per-device batch size × gradient accumulation × number of data-parallel devices.” The number of tensor-parallel devices must not be substituted directly into this formula. The executor declares the parallelism used in distributed training.

<a id="41-原型数值不是生产上限"></a>

### 4.1 Prototype values are not production limits

The Demo uses illustrative validation ranges such as 10—10,000 training steps, a 5%—40% validation split, batch sizes of 1—64, and sequence lengths of 128—131,072. The formal product must replace these with joint model, method, and device constraints, documenting their sources in capability records instead of copying these constants as product capability promises.

<a id="42-sft-的分词与监督合同aud-10"></a>

### 4.2 SFT tokenization and supervision contract (AUD-10)

Passing structural validation of `messages` is still insufficient to start training. Training templates must reference an immutable `TokenizationRecipe` that fixes the tokenizer, processor, chat template, supervision scope, EOS/PAD, truncation, and sample concatenation policies; the recipe digest enters the data-check report and execution snapshot. Adapters must not replace any of these with their own defaults. Ordinary users only need to choose a training template; advanced details expose the resolved policies.

The first multi-turn conversation template uses `assistant_only`: supervise only assistant responses and the response-end markers specified by the template; system/user messages and media placeholders/feature positions do not participate in text loss. Other supervision objectives require different recipe versions and renewed checks; `completion_only` or `all_tokens` must not be treated as unconditionally interchangeable. Block combinations where the template cannot generate reliable role masks or where a model has separate media objectives without declared handling.

| Item | Rules that must be fixed | Checks and failure handling |
| --- | --- | --- |
| Tokenization and role masks | tokenizer/processor/template versions, special tokens, supervised roles, end-marker positions, and whether label shifting is the responsibility of the model or data collator | Save representative token/label comparisons and digests to prevent duplicate shifting; do not infer masks from displayed text |
| EOS and PAD | End-marker insertion rules, whether end markers are supervised, PAD position rules, and ignore value `-100` | Every padding position is excluded from loss; when EOS and PAD share an ID, distinguish them by position rather than masking real end markers |
| Overlong samples | The first template excludes overlong samples by default and reports them; an optional template removes only the oldest complete turns while preserving system messages and the complete final supervised response | Exclude samples when a single response is still too long; do not remove all response content while retaining the question for training; users can inspect the effect of exclusions |
| Sample concatenation | Packing is disabled in the first template; enabling it requires declared boundary markers, position IDs, attention isolation, and loss-mask policies | Verify with cross-sample boundary counterexamples; do not enable it unless the declared boundaries can be guaranteed, and do not present a concatenated sequence as one sample |
| Multimodal alignment | Media order, processor version, expanded token/feature positions, text supervision, and non-text objectives | Tokens, labels, and media positions must align; only the corresponding model adapter may explicitly declare non-text losses |

Check reports show input samples, trainable samples, truncated/excluded samples, counts by reason, and the total and distribution of effective supervised tokens. Samples with zero effective supervision must be excluded and identified; reject submission when the entire training set or a required validation set has no effective supervision. Changes to policy, template, media processing, or sequence length invalidate old checks. Multi-turn conversations, overlong responses, empty responses, system-only messages, padding, concatenation boundaries, and media samples all enter actual token-and-label acceptance under AC-04/AC-06; checking JSON field presence alone is insufficient.

Media samples must not continue training after media token/feature ranges have been truncated. Combinations without verified safe truncation retain complete sequences and exclude overlong samples according to resource budgets. This first template is an explicit project choice, not an assumed underlying-library default; the [TRL SFT documentation](https://huggingface.co/docs/trl/sft_trainer) separately defines assistant supervision, completion-only supervision, and packing, and notes that truncating vision samples can remove image tokens.

<a id="5-多媒体训练补充"></a>

## 5. Additional multimedia training requirements

<a id="51-图像"></a>

### 5.1 Images

Data preparation checks image decodability, dimensions, channels, color space, orientation metadata, duplicates, and near duplicates. Cropping, resizing, and annotation changes must produce processing recipes. Paired tasks must specify whether source, reference, and target are pixel-aligned rather than merely checking file existence.

Parameters include model-specific settings such as resolution, cropping policy, augmentation, subject trigger words, whether to train the text encoder, and prior preservation. Loss functions, network modules, and optimizers must be on the adapter's allowlist and cannot be injected through arbitrary script fields.

<a id="52-视频"></a>

### 5.2 Video

Record container, codec, frame rate, frame count, duration, resolution, frame-sampling policy, and subtitles/descriptions. Variable-frame-rate materials must have a defined common time base. Record slice boundaries using both time and frame indices; processed data produces a new version.

Acceptance must include real video decoding and short-clip training; displaying keyframes, moving a still image, or completing a file write does not count as successful video training/generation.

<a id="53-音频"></a>

### 5.3 Audio

Record sample rate, channels, duration, loudness, slices, transcription, speaker, and language. End time must exceed start time and remain within the actual audio duration. Users choose resampling, denoising, silence segmentation, and similar processing, and parameters are retained; untraceable automatic cleaning is not the default.

Speech synthesis, ASR, voice conversion, and music generation use separate data and evaluation adapters. Playable audio only demonstrates that the file can be decoded; it does not replace acceptance of speech quality or training effectiveness.

<a id="6-提交前检查"></a>

## 6. Pre-submission checks

Checks fall into five categories: data, model, environment, configuration, and resources. Results may pass, block, or advise; each result includes a reason, field location, actionable correction, and check version.

Required blockers: missing/corrupt model or data files, incompatible data format, unprepared required components, unreachable device, invalid parameters, an engine that does not support the current method, selected precision unsupported by the actual device, or an unwritable output directory.

Advisories: estimated memory near the limit, few samples, a small validation set, or insufficient experiment-goal description. When a user has not supplied a source declaration, retain “Not provided”; AI cannot turn it into “Authorized,” and a missing declaration must not be disguised as a technical format error.

<a id="7-模型实验室"></a>

## 7. Model lab

| Specialization | Inputs | Required settings | Outputs | Independent acceptance |
| --- | --- | --- | --- | --- |
| Behavior adjustment/abliteration comparison | Source weights, target data, regression set | Heretic/Abliterix version, objective, candidate budget, allowed capability degradation | Candidates and change records for each method | Normal tasks, target behavior, format, and general capabilities |
| Distillation | Teacher, student, data | Teacher sampling, loss/objective, training budget, teacher-output version | Student candidate and teacher provenance | Student quality versus size/speed |
| Merging | Compatible base model and adapters/models | Method, weights, structural validation | New weights or merged adapter | Loadability, capability regression, reproducible configuration |
| Quantization | Source weights, optional calibration set | Format, bit width, groups, calibration policy | Runtime artifact | Correctness, size, speed, and quality changes |
| Conversion | Original model, processor, and sample inputs | Target such as Core ML/ONNX/TorchScript, shapes, precision | Target format and metadata | Numerical consistency and execution on the target device |

<a id="71-行为调整研究边界"></a>

### 7.1 Behavior-adjustment research boundaries

Retain the user-confirmed entry points and the design for independent candidates from two engines; method names do not imply that the product already has the technical capability. In-house research paths remain unlaunchable without an execution adapter. The first step is to verify specific upstream sources, versions, input requirements, and output forms, then compare normal tasks and target behavior.

<a id="72-蒸馏边界"></a>

### 7.2 Distillation boundaries

Distinguish offline distillation from teacher-generated data from online distillation that calls the teacher during training. Explicitly record teacher endpoints, input-transfer scope, cost sources, output caches, and failure retries. If a remote teacher is unavailable, do not silently switch to another teacher.

<a id="73-合并边界"></a>

### 7.3 Merging boundaries

First check architecture, layer count, tokenizer, base-model version, and adapter target modules. Equal dimensions do not imply semantic compatibility. Merging does not overwrite any input; it creates a new version and records the participating weights.

<a id="74-量化转换边界"></a>

### 7.4 Quantization/conversion boundaries

Conversion does not promise higher speed, and quantization does not promise preservation of every capability. Before registering an artifact, complete at least independent loading, fixed-sample comparison, and target runtime-environment checking. ANE acceptance requires actual Core ML artifacts and device execution records.

The converted `ModelVersion.format` and actual file manifest participate in default-engine selection. A candidate may inherit provenance relationships but not incompatible run settings from its source model; both “the engine can read the artifact format” and “the engine permits this model operation” must hold. If a bridging conversion is required, create an independent preparation plan and new version for the user to complete before trial use; do not silently treat Core ML artifacts as PyTorch weights during loading. See the format capability contract in [04](04-runtime-and-hardware.md) for specific rules.

<a id="8-评测与候选登记"></a>

## 8. Evaluation and candidate registration

Freeze the evaluation set before training to avoid repeatedly changing admission criteria in response to the current outputs. Reports retain the baseline, candidate, evaluation configuration, sample version, thresholds, per-sample results, and summary together.

Language tasks cover at least business correctness, format, normal-task regression, and target behavior; images focus on subject and structure; video adds temporal behavior; audio selects CER/WER, intelligibility, sound quality, or listening evaluation according to the task. Items that cannot be quantified automatically are marked for human review rather than assigned a fabricated aggregate score.

Candidate registration requires existing artifacts with matching hashes, independent loadability, and completion of required evaluations in accordance with preset rules. Registration is idempotent; clicking repeatedly on the same candidate does not produce multiple model versions.

<a id="9-完成标准"></a>

## 9. Completion criteria

Every “supported training combination” must have an evidence chain from real data to an independently loaded candidate: input versions, processing recipes, final configuration, device environment, training logs, checkpoints, evaluation reports, artifact hashes, and run results. Lower training loss, a script exiting successfully, or a page displaying completion is insufficient on its own as delivery evidence.

E-03 return-path verification is moved forward to TV-03 in M0: pin a specific NVIDIA training combination, bring the same actual LoRA artifact to the designated Apple trial engine, and record base-model revision, target modules, adapter digest, template, necessary conversions, and fixed-sample results. A separately trained Apple adapter or a merely downloaded demonstration file is not a substitute. The experiment only determines whether that combination is feasible; AC-26 in M3 later covers product entry points, transfer, candidate registration, configuration differences, and failure recovery, without prematurely claiming general compatibility of training artifacts across platforms.
