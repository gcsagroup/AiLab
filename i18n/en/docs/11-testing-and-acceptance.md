<!-- translation-navigation:start -->
[简体中文](../../../docs/11-testing-and-acceptance.md) · [繁體中文](../../zh-TW/docs/11-testing-and-acceptance.md) · [English](11-testing-and-acceptance.md)
<!-- translation-navigation:end -->

<a id="测试策略与验收标准"></a>

# Testing Strategy and Acceptance Criteria

Version: 1.1 · Date: 2026-09-09 · Status: Negative cases, technical experiments, and phased acceptance supplemented following the audit; real product testing remains a plan awaiting execution.

Related documents: [Requirements](01-product-requirements.md), [Work packages](10-work-breakdown.md), [Release](12-operations-and-release.md), [Prototype evidence](14-prototype-traceability.md), [Remediation tracking](16-audit-remediation-plan.md).

<a id="1-证据层级"></a>

## 1. Evidence Levels

| Level | What it proves | What it does not prove |
| --- | --- | --- |
| Documentation and static checks | Links, examples, identifier structure; parseable relationships, phase dependencies, and specified negative cases | The application actually runs, or all natural-language semantics are correct |
| Prototype state tests | Simulated states, some validation and interaction intent | Real execution, persistence, or performance |
| Unit / contract tests | Rules, interfaces, states, parameter mappings | Actual drivers, model loading, or final experience |
| Integration tests | Database, process, file, and service interactions | Universal support for all hardware and models |
| Real-device tests | Real execution and metrics for specified combinations | Untested versions and other devices |
| User end-to-end acceptance | A complete task from the actual entry point to final artifacts | Unexecuted workflows such as external publishing or upgrades |
| Release acceptance | A specific installer and support matrix are deliverable | Future versions automatically inherit a pass |

Test reports must identify level, inputs, environment, versions, execution time, results, and limitations. Prototype tests and simulated execution must not enter real performance statistics.

<a id="2-已有基线"></a>

## 2. Existing Baseline

During 1.0 document validation, the prototype `test-ailab-unified.cjs` ran and reported 42 representative validation groups passed; `test-ailab-runtime.cjs` reported 17 runtime-optimization validation groups passed. Prototype script syntax, HTML-fragment structure, and the under-1 MB check passed.

These 59 groups are test groups reported by prototype scripts, not 59 real model / hardware combinations. The subsequent audit reproduced behavioral errors AUD-01—AUD-06 while the original tests still passed, and also found E-04's result-recipe semantic issue. Passing audit-script assertions means the issues were successfully reproduced, not that the product was fixed.

See the [validation report](validation-report.md) for actual execution results of the 1.1 document revision. The TV, GATE, and AC items added here are acceptance contracts awaiting execution; passing document checks cannot mark product acceptance passed.

<a id="3-测试环境与数据"></a>

## 3. Test Environments and Data

<a id="31-最小设备池"></a>

### 3.1 Minimum Device Pool

- One Apple Silicon Mac with a specified model and unified-memory capacity.
- One NVIDIA Linux machine with specified GPU, GPU-memory capacity, operating system, and driver versions.
- Specified AMD GPU and Intel GPU / NPU devices for M5 expansion.
- One clean installation / upgrade test environment; a separate user account or virtual machine may be used, but GPU feature acceptance requires an actual applicable device.

Each report saves CPU, GPU / NPU, memory, operating system, driver, engine, model, precision, storage, network, and power state. Unavailable devices are marked untested rather than replaced by machines from another vendor.

<a id="32-数据夹具"></a>

### 3.2 Data Fixtures

Prepare small publicly shareable text, image, short-video, and audio examples with source records. Manage normal data and negative cases separately. Negative cases include missing fields, corrupted files, empty content, duplicates, overlong inputs, out-of-bounds slices, wrong sample rates, variable frame rates, and model incompatibility.

Small functional samples check the pipeline; quality evaluation sets check results, and the two are separate. Training samples must not be used directly as an independent test set. Fix and save near-duplicate grouping information and split seeds.

<a id="4-核心验收用例"></a>

## 4. Core Acceptance Cases

<a id="ac-01项目与草稿持久化"></a>

### AC-01: Project and Draft Persistence

Preconditions: two projects, each with language and image drafts. Actions: edit, switch projects, close the application, restart. Expected: task IDs, fields, selected objects, and history recover by project; background results belong to the original project. Evidence: database records, application-operation video or screenshots, and relevant events. Covers PRD-001, PRD-018.

<a id="ac-02四类入口与继续任务"></a>

### AC-02: Four Entry Categories and Task Continuation

Enter each category from the home page, restore drafts, create tasks, view runs and evaluations, then return home. Expected: clear entry points and state buttons leading to the next step, without duplicate training entries or wrong categories. Checking that routes exist is insufficient. Covers PRD-002, PRD-020.

<a id="ac-03模型准备信任与独立加载"></a>

### AC-03: Model Preparation, Trust, and Independent Loading

Using a fixed model revision, download, pause / resume where supported, cancel, and retry. Include corrupted files, disguised formats, restricted-loading failures, untrusted pickle / checkpoints, TorchScript, and models requiring custom code. Check the format, loading method, trust class, dependencies, and isolation boundary declared in ModelImportPlan. Expected: integrity validation does not replace a trust decision; restricted-loading failure must not automatically fall back to arbitrary deserialization. Required execution capabilities restrict files, networks, and credentials according to an explicit decision, with recorded isolation effectiveness. After completion, load in an independent process using the declared method; if an adapter lacks its base model, identify the exact dependency. Test with harmless controlled fixtures, without executing malicious models of unknown origin. Covers PRD-003. Corresponds to AUD-11.

<a id="ac-04数据导入检查与监督配方"></a>

### AC-04: Data Import, Checks, and Supervision Recipes

Import normal JSONL and four categories of negative cases; check line numbers, media, duplication, and splits. After applying exclusion / resampling, original digests remain unchanged and the new version is traceable. Output final tokens / labels for multi-turn, overlong-answer, empty-answer, system-only, padding, packing-boundary, and multimodal samples; check tokenizer / processor / template, assistant-only or completion-only, EOS / PAD, truncation, and boundary policies. Expected: effective supervised-token, truncation, and discarded-sample statistics are explainable; zero-supervision samples must be excluded, and the task is blocked if filtering leaves no effective supervision in training or a required validation set. Changes to data or supervision-recipe versions invalidate old checks. Covers PRD-004. Corresponds to AUD-10.

<a id="ac-05市场访问与返回原任务"></a>

### AC-05: Marketplace Access and Return to the Original Task

Enter the marketplace from an existing training draft and complete open download, restricted application, denial, approval, download, and data selection respectively. Expected: incorrect schemas cannot be used; the original name, parameters, project, and step remain after returning; access approval does not display a label that judges authorization for the user. Covers PRD-005.

<a id="ac-06训练方法更新方式与监督目标"></a>

### AC-06: Training Methods, Update Methods, and Supervision Targets

Run minimum real training for every enabled combination, including at least the initial SFT + LoRA. Verify target modules, data schemas, supervision recipes, final tokens / labels, optimizer step counts, and weight changes. For adapters supporting the same recipe, check equivalent supervision scope without relying on library defaults. Model / task-mode changes invalidate incompatible training inputs or old checks; the server rejects forged modes, unsupported QLoRA / precision / devices, and data with zero effective supervision. Add cases individually for new training methods. Covers PRD-006. Corresponds to AUD-04, AUD-10.

<a id="ac-07任务生命周期与异常出口"></a>

### AC-07: Task Lifecycle and Exception Exits

Execute the [state table in 07](07-api-and-task-lifecycle.md) row by row, covering queued, preparing, running, collecting, cancelling, failed, checkpoints, and pause / resume where available. Inject pause-checkpoint failure, cancellation while pausing, executor crash while cancelling, collection cancellation while finalizing, control timeout, and force-stop failure; check states, allowed actions, errors, recovery entries, and events. Without stop evidence, `stop_status=unknown`; the interface must not claim execution stopped or can safely restart. Retrying a failure creates a new computation attempt while retaining old records. Resumption includes the agreed training state; merely loading weights must not be falsely described as continuing the original trajectory. Covers PRD-007. Corresponds to AUD-07, AUD-08.

<a id="ac-08真实运行模型模式与结果"></a>

### AC-08: Real Execution, Model Modes, and Results

Actually execute text generation, image generation, video generation, and TTS / ASR according to enabled capabilities. Test switching from an audio-capable model to a vision-only model and back, and switching models with images / video / recordings present. Interface selections, applied modes, media inputs, and submission snapshots agree; incompatible items are explicitly reset with explanations, and the server rejects forged stale-mode requests. Real inputs must be used, output files must be independently readable, and final results must agree with history; preset media cannot replace real artifacts. Covers PRD-008. Corresponds to AUD-04.

<a id="ac-09运行参数执行位置与预设"></a>

### AC-09: Runtime Parameters, Execution Location, and Presets

Test thinking off, context, output limits, sampling, stop words, and streaming, comparing the interface, applied configuration, request snapshot, actual backend parameters, and observed results. Over-budget rejection / truncation follows the user's choice. Cover local default / cloud for this attempt, cloud default / local for this attempt, and recipe reloads. The location beside the button, parameter summary, and transmission scope all derive from the configuration applied for this attempt. Use “Model defaults,” “Low memory,” and “Low latency” presets individually; actual field differences are visible before applying and cancellation changes nothing. After model / device changes, invalidated values and reload requirements are explained; no acceleration is claimed without measurements. Snapshots cannot change during execution. Covers PRD-009. Corresponds to AUD-06, E-02.

<a id="ac-10缓存prefill-与-decode"></a>

### AC-10: Caching, Prefill, and Decode

Fix the model and inputs, then validate cache isolation, invalidation, KV dtype, chunking, batching, concurrency, and CUDA Graph. The same text with different images / video / audio, or the same media with changes to ordering, cropping, frame extraction, sampling, or processor version, must not produce incorrect cache hits. Save identity conditions for media-content or encoded digests, processors, and preprocessing parameters. When delegating caching to the underlying engine, verify that the adapter actually guarantees these conditions rather than adding a weaker application cache; unknown combinations remain disabled. Reject unsupported engine fields without dropping parameters. Block disaggregated deployment if its connector is missing; once implemented, inject transfer failures and model-version mismatches. Covers PRD-010. Corresponds to AUD-09.

<a id="ac-11推测解码配对"></a>

### AC-11: Speculative Decoding Pairing

Test normal and mismatched inputs for ordinary draft models, MTP, and DFlash separately. Cover switching both ways between ordinary draft models and DFlash, changing models / engines / templates / thinking conditions before and after preparation, and directly submitting old configuration. Preparation state belongs to an exact combination of target model, strategy, components, and engine. Mismatches clear it and block preparation / application / submission; an independent `draftReady` boolean cannot be inherited. Reject missing MTP components and mismatched DFlash companions; measure correctness, acceptance rate, and latency for correct combinations. Covers PRD-011. Corresponds to AUD-03.

<a id="ac-12设备与引擎适配"></a>

### AC-12: Device and Engine Adaptation

Register real devices individually and validate separation of reachability, detection, dependencies, loading, and running states. Save separate reports for NVIDIA, Apple, AMD, Intel, and CPU; different operating systems within the same brand do not automatically inherit support. Covers PRD-012.

<a id="ac-13媒体参数与-core-mlane"></a>

### AC-13: Media Parameters and Core ML / ANE

For images, check scheduler, CFG, VAE, and offloading; for video, frame rate, frame count, duration, and slicing; for audio, sample rate, slicing, streaming chunks, and transcription. Complete the default-configuration and loading path from a converted candidate's “Run” entry. Format participates in engine selection, and invalid source configuration must not be inherited. Reject both original weights → unsupported Core ML engine and Core ML artifact → PyTorch path that does not support that format. Bridging conversions must be explicit preparation steps with a digest chain. Claim ANE use only with actual allocation evidence. Covers PRD-008, PRD-012, PRD-013. Corresponds to AUD-05.

<a id="ac-14评测与候选准入"></a>

### AC-14: Evaluation and Candidate Admission

Use fixed data and rules for baseline and candidate, and inject one below-threshold candidate and one corrupted artifact. Expected: neither can be registered as usable; passing candidates can be independently loaded for trials and return to their source experiments; repeated registration is idempotent. Covers PRD-014.

<a id="ac-15ai-建议模式"></a>

### AC-15: AI Suggestion Mode

Check that generating suggestions changes nothing, applying them modifies only allowlisted fields, expired revisions are rejected, undo does not overwrite later edits, submitted tasks are read-only, and malicious materials have no execution authority. Check remote-request scope and response boundaries for source questions. Covers PRD-017.

<a id="ac-16作品生成配方与结果修订"></a>

### AC-16: Works, Generation Recipes, and Result Revisions

After saving artifacts, close and reopen the application, reload recipes, and check difference notices after changing model versions / devices. Inputs, artifacts, base models / adapters, parameters, and provenance are all findable; favorites and file saving are distinct. Editing transcriptions / subtitles creates WorkRevision records with viewable originals, revisions, parent versions, and differences; job.snapshot, the original generation recipe, and original output remain unchanged. Regeneration reuses generation parameters only without implicitly applying manual revisions; export explicitly selects the original or revised version. Covers PRD-016. Corresponds to E-04.

<a id="ac-17完整媒体工作流与原子推进"></a>

### AC-17: Complete Media Workflow and Atomic Advancement

Actually execute two rounds of image → video → voice-over, saving WorkflowRun id / revision, step attempt, and input revision. After changing inputs in the second round with zero generation, advancement must not use the previous round's results by default. Explicit reuse requires user selection and a source execution / artifact record; upstream changes invalidate old downstream results.

Advance while the target category is running, paused, just completed, and just cancelled respectively. If target-occupancy checks fail, the step, output set, and source draft remain unchanged; viewing the blocking task, waiting, or exiting remain available. Once unblocked, one click advances only once. Inject a mid-workflow failure and redo the stage, preserving earlier artifacts and complete input / provenance versions; final media opens independently. Without compositing capability, do not call it a finished film. Covers PRD-015. Corresponds to AUD-01, AUD-02.

<a id="ac-18故障恢复与只补收"></a>

### AC-18: Failure Recovery and Collection-only Retries

Terminate processes during execution, file writing, transaction submission, and event sending; simulate disk-full conditions and remote disconnection. After restart, there is no duplicate computation, no loss of committed records, and no marking partial files complete; unknown task state is reconciled by reconnection. Separately, after computation finishes and remote artifacts are complete, inject local disk-full conditions, transfer interruption, and asset-registration transaction failure, then retry collection only through `POST /attempts/{id}/collections`: reuse the original manifest, do not increase `run` / `resume` call counts, retain identical file digests, and register assets only once. Preserve the original RunAttempt's failed terminal state and computation outcome; new collection records document the recovery and state without disguising it as successful recomputation. Covers PRD-018. Corresponds to AUD-07, AUD-08.

<a id="ac-19模型实验室与转换候选试用"></a>

### AC-19: Model Lab and Converted-candidate Trials

Execute each enabled merging, distillation, quantization, conversion, and behavior-comparison operation; check input compatibility, candidate independence, artifact digests, quality regression, and provenance chains. Converted candidates select a format-compatible engine from the actual entry point before running independently. An incompatible original engine must be invalidated; both directions of format mismatch and missing bridging steps are blocked. Converted-artifact export is handled by WP-29's generic exporter; conversion tests do not replace export acceptance. Unimplemented custom-research entries cannot start. Covers PRD-013. Corresponds to AUD-05.

<a id="ac-20幂等与竞争"></a>

### AC-20: Idempotency and Races

Cover double-click submission, resending the same idempotency key, reusing a key with different content, stale state versions, repeated pause / cancel / resume / force-stop, cancellation / completion races, AI / manual-edit races, duplicate terminal events, and retrieval of missed events after disconnection. Workflow advancement, target-occupancy changes, repeated advance, and stale input revisions must also be decided atomically. Expected: one legal execution, explicit conflicts for stale requests, no half-advancement from failed transactions, and database / interface agreement. Unknown stop confirmation cannot be decided as stopped. Repeated collection-retry requests produce only the agreed collection records and one asset registration. Covers PRD-007, PRD-015, PRD-018. Corresponds to AUD-02, AUD-07, AUD-08.

<a id="ac-21远程执行目的地与输入边界"></a>

### AC-21: Remote Execution, Destinations, and Input Boundaries

Test remote identity mismatch, expired credentials, interrupted uploads, identical-file deduplication, run disconnection, and missed-log retrieval. For local default / one cloud attempt, cloud default / one local attempt, and recipe reloads, the summary, location beside the button, transmission scope, and actual destination agree, without silent address changes. Uploading and model loading follow the decided trust scope; restricted-loading failure does not expand execution permissions. Losing contact after cancellation preserves an unknown stop outcome and does not restart execution. If computation completed but collection failed, only transfer, validation, and registration are retried, without recomputation. Diagnostic data has no plaintext keys. Covers PRD-012, PRD-018. Corresponds to AUD-06, AUD-08, AUD-11.

<a id="ac-22安装升级备份与导出回归"></a>

### AC-22: Installation, Upgrades, Backup, and Export Regression

Install the specific candidate package in a clean environment, upgrade an old version containing historical tasks, roll back one failed migration, and restore a backup. Check installer identity, dependency versions, old tasks, and original artifacts. After upgrade / recovery, export again under AC-27 and validate files independently; diagnostic-package redaction is checked separately. Uninstalling does not mean deleting model data. Earlier M3 / M4 export-subitem passes do not mean candidate-package upgrade acceptance passed; this case is not a prerequisite for the M0 shell-sidecar experiment. Covers PRD-018, PRD-019. Corresponds to AUD-12, AUD-13.

<a id="ac-23界面键盘与外观"></a>

### AC-23: Interface, Keyboard, and Appearance

Check 1024, 736, and 360 px in dark and light modes, with a minimum of 320 px, along with form labels, focus, dialogs, error associations, long names, Chinese paths, empty states, and large lists. Complete one task with the keyboard; static screenshots cannot replace key interactions. Also verify the confirmed versions and digests of the demo, tests, and checkers against the manifest at the fixed project location. A new team member following rerun instructions can open the same interface, run specified checks, and understand known issues. Organize assets in M1 and validate from a new-member perspective in M6, preserving historical files. Covers PRD-002, PRD-020. Corresponds to E-05.

<a id="ac-24性能与质量对照"></a>

### AC-24: Performance and Quality Comparisons

For each advertised optimization, compare disabled / enabled operation with fixed workload, precision, and environment, recording cold / warm runs, concurrency, memory, and quality. Include cases with no benefit or slowdowns instead of selecting the best samples as a general conclusion. Covers PRD-010, PRD-011, PRD-012.

<a id="ac-25首次用户零资源到首次结果"></a>

### AC-25: First-time Users from Zero Resources to a First Result

Have 5 target users each use a clean installation with no preset models / projects / data / history. From the home page, they select “Direct trial” within a category, create a project, select an initially supported model, prepare dependencies, check the device, enter a sample, generate a first real result, save it, and continue after restarting. In-product help is allowed, but not dependence on development documents or developers filling in steps. Record each person's success / failure, blockers, human assistance, time, and artifacts. Pass only if all 5 complete the path with no blocking issues; do not generalize this small sample to usability for all users. Offline operation or insufficient resources must offer understandable recovery entries; preset resources cannot masquerade as a zero-resource path. Complete acceptance uses the M6 candidate package; M2 is only a phase rehearsal of the first integrated language path. Covers PRD-002, PRD-020. Corresponds to E-01.

<a id="ac-26同一-lora-产物跨端试用"></a>

### AC-26: Cross-device Trial of the Same LoRA Artifact

Complete real SFT + LoRA on the specified NVIDIA training combination, evaluate and register it, then send the same adapter to the specified Apple target engine for trial. Record the base-model revision, target modules, adapter digest, tokenizer / template, precision, engine, and hardware. Without conversion, digests remain identical; if conversion is required, preserve input / output digests and a rerunnable conversion chain rather than training a similar model separately. Validate specified samples through both the product candidate entry and independent loading, comparing without-adapter / with-adapter results against compatibility and quality criteria defined in advance; the path must also reproduce from the export package. Wrong base models, missing dependencies, incorrect formats, and mismatched modules must be blocked. M0 TV-03 proves only the selected technical path; this case first exercises the complete product path in M3, with M6 regression for frozen release combinations. Covers PRD-006, PRD-008, PRD-012, PRD-014, PRD-019. Corresponds to E-03.

<a id="ac-27模型适配器作品与报告导出"></a>

### AC-27: Model, Adapter, Work, and Report Export

Select real objects in each category: a model, LoRA adapter, image / video / audio works, and an evaluation report. From the ordinary user entry, choose scope / version and destination, checking dependency resolution, manifests, digests, complete persistence, and independent use. Adapter packages record exact base-model dependencies and missing-dependency notices without bundling base models lacking redistribution rights by default. Media opens independently, revisions are distinguishable from original generation recipes, and reports trace models, data, evaluation rules, and results.

Inject missing files, disk-full conditions, cancellation, digest mismatches, and interruption recovery. Temporary / partial packages must not show success; publish the final package only after integrity passes. Recovery does not trigger training or inference recomputation, and source assets remain unchanged. M3 validates models / adapters / text works / reports; M4 adds media; M5 adds this version's converted formats; M6 regresses all applicable objects on the same candidate package after upgrade / recovery. Diagnostic packages cannot replace this case. Covers PRD-019. Corresponds to AUD-13, E-04.

<a id="5-性能测试方法"></a>

## 5. Performance Testing Method

<a id="51-基准条件"></a>

### 5.1 Benchmark Conditions

Each configuration includes at least short, medium, and long inputs and both single-request / multiple-request workload groups. Formal input lengths are determined by the reference model's capabilities, with exact token counts recorded. Separate cold loading from warm runs; stability testing uses at least 30 fixed requests, repeated for 3 rounds when needed. Time first-run compilation and model downloading separately.

Sampling parameters, output-length limits, stop conditions, seeds, cache-hit conditions, and concurrency must match. Comparisons across quantization levels or precision explicitly state the changed computation conditions and report quality alongside performance.

<a id="52-指标口径"></a>

### 5.2 Metric Definitions

| Metric | Definition |
| --- | --- |
| End-to-end latency | Client submission to completion of the final result, including transfer and queueing |
| Time to first token | Submission to the first output token; separately state whether model loading is included |
| Prefill speed | Input token count / actual Prefill duration; report only when the engine can attribute it explicitly |
| Decode speed | Generated token count after the first token / corresponding generation duration; not calculated for a 1-token output |
| Total throughput | Tokens or requests actually completed in the test window / window duration |
| Peak memory | Peak recorded by measurement tools; list GPU / unified / process memory separately |
| Cache hits | Actual engine hit statistics; unknown if no observation interface exists |
| Draft acceptance rate | Accepted draft tokens / proposed draft tokens, aligned with the engine's reporting definition |
| Quality change | Candidate / baseline differences under fixed samples and rules |

Do not present character counts as token counts, an early first response chunk as proof of faster complete inference, or a single best run instead of median and p95.

<a id="6-训练质量验收"></a>

## 6. Training Quality Acceptance

Report functional acceptance separately from model quality acceptance. Functional acceptance requires parameter updates, complete checkpoints, resumability, and loadable artifacts; quality acceptance requires fixed business / regression samples, reasonable thresholds, sample sizes, and human review.

Set thresholds before testing and define them by task. Where no uniform automated score is possible, retain per-sample results and review explanations rather than concealing differences behind an unsourced score. Falling loss or rising rewards alone do not constitute a pass.

<a id="7-自动化分层"></a>

## 7. Automation Layers

- Documentation: parse actual PRD → work package → AC relationships, deliverable objects, phase and subitem dependencies, reference durations, and audit mappings; report structural checks separately from natural-language content review.
- Unit: parameter schemas, versions, data splits, supervision tokens / labels, state transitions, WorkflowRun identity and input versions, suggestion application, and cache keys including media identity.
- Contract: requests / responses, error codes, idempotency, event ordering, executor capabilities.
- Integration: real SQLite, temporary directories, processes, file validation, and controlled remote services.
- Model: real small-model / small-sample execution, checking weights and outputs without filling routine CI with large models.
- Device: labeled dedicated machines execute the scheduled matrix, with artifacts and reports linked to the commit version.
- End-to-end: actual browser / desktop operations complete user paths.

<a id="8-缺陷等级与放行"></a>

## 8. Defect Severity and Release Decisions

| Severity | Examples | Release principle |
| --- | --- | --- |
| Blocking | Data loss, duplicate expensive execution, wrong project attribution, false success, credential leakage | This version must not be released |
| High | Main workflow cannot complete, ignored parameters, bypassed candidate admission, ineffective cancellation displayed as successful | Must fix and retest |
| Medium | Clear errors outside the main path, interaction issues with workarounds that still affect use | Assess scope and disclose limitations; normally fix |
| Low | Noncritical copy, local spacing, unclear auxiliary information | Record for subsequent correction |

Unsupported hardware is not a defect; falsely claiming support or allowing unexecutable combinations is. Untested capabilities remain untested in the release matrix; disabling tests cannot erase failure records.

<a id="9-阶段门槛"></a>

## 9. Phase Gates

Record phase validation separately from complete ACs. Work packages complete the subset of deliverables declared for their phase; M1 fake executors must not be required to already support M3 real training or M6 installation / upgrades. Likewise, a phase pass cannot be copied into a complete-AC pass. Preserve failed cases in each phase and rerun corresponding subsets when real adapters are integrated later.

<a id="91-m0-独立技术试验"></a>

### 9.1 Independent M0 Technical Experiments

Technical experiments may use command-line tools and a minimum shell, depending only on this phase's fixed inputs, devices, and scripts, not final ACs or the production control service. Before entry, converge the remediation-contract documents and run relationship checks; this does not complete the product backend.

| ID | Responsible work package | Fixed inputs and operations | Pass conditions | Later acceptance not required beforehand |
| --- | --- | --- | --- | --- |
| TV-01 | WP-01 | Fixed model / base-model revisions, tokenizer / template, training-library / inference-engine versions, exact Apple and NVIDIA devices; run minimum real inference and SFT + LoRA | Reproducible environment, recorded parameter updates and real output, unchanged original model digest, explainable incorrect combinations | Complete AC-06, AC-08, AC-12 |
| TV-02 | WP-02 | Minimum desktop-shell and sidecar packaging; startup, normal exit, sidecar crash, host exit, restart, Chinese / space-containing paths, log retrieval | No orphan processes, locatable failures, runnable after restart, clear experiment-package / dependency identities | Project database AC-01, production installation / upgrades AC-22 |
| TV-03 | WP-01 | Send the same actual LoRA from TV-01's NVIDIA training environment to the specified Apple target engine; fix base model, template, modules, and digests, then load independently and try it | Rerunnable same-artifact chain; necessary conversion has input / output digests and steps; matching combination passes and wrong base models / formats are blocked | Product candidate registration AC-14, production exporter AC-27, complete AC-26 |

If TV-03 fails, adjust the selected combination and rerun; another independently trained artifact cannot substitute. Exit is allowed once all three pass and M0 documentation / reassessment records are complete, without waiting for M1—M6.

<a id="92-产品阶段门槛"></a>

### 9.2 Product Phase Gates

| Gate | Phase | Scope that must be validated in this phase | Complete-AC tracking and later boundaries |
| --- | --- | --- | --- |
| GATE-M1 | M1 | Project / draft persistence and cross-project isolation; interface entries, keyboard / empty states, fixed prototype / test asset manifests; real files / manifests and import trust plans; fake-executor states, idempotency, pause / cancel exceptions, unknown stop status, and collection-only retries; capability-interaction rejection; database transactions and backup foundations | Contract or interface subsets of AC-01—AC-04, AC-06—AC-09, AC-11—AC-13, AC-16, AC-18, AC-20—AC-23, AC-25; does not require real models, training, media, installers, or every device |
| GATE-M2 | M2 | Specified Apple / NVIDIA text inference; independent model loading and permission boundaries, remote identity / transfer; interface → snapshot → actual parameters and execution-location consistency; stale mode / companion configuration rejection; preset differences, recipe reloads; enabled cache baselines and media-identity contract negative cases; cancellation, disconnection, collection-only retries; first-language-trial rehearsal | Subsets of AC-03, AC-08—AC-13, AC-16, AC-18, AC-21, AC-24, AC-25 for integrated inference combinations; real multimodal-cache tests wait for corresponding media integrations, and complete first-time user acceptance remains in M6 |
| GATE-M3 | M3 | Fixed supervision recipes and tokens / labels; real SFT + LoRA, checkpoints, resumption; independent evaluation, candidate admission, target-device trial of the same artifact; AI allowlists / conflicts; independent loading / opening after model, adapter, text-work, and report export | Language-training and basic-artifact subsets of AC-04, AC-06, AC-07, AC-14, AC-15, AC-18, AC-26, AC-27; does not require media exports or production installation / upgrades |
| GATE-M4 | M4 | This version's selected image / video / audio training and trials, including at least one TTS for voice-over output; media parameters and real measurements of enabled cache identities; marketplace return; two workflow rounds, explicit old-result reuse, atomic target-busy failure and races; result-revision separation; independently openable media exports | Media and marketplace subsets of AC-02, AC-05, AC-06, AC-08, AC-10, AC-13, AC-16, AC-17, AC-20, AC-27; unselected audio tasks are not falsely reported passed |
| GATE-M5 | M5 | Individual real-device validation of frozen additional training / experiment / hardware / cache / speculation combinations; bidirectional rejection of converted-candidate format / engine mismatches; optimization-on / off comparisons; required bridging and new-format exports | AC-06, AC-10—AC-14, AC-19, AC-21, AC-24, AC-27 expanded by selected combination; deferred disaggregated deployments and similar items remain explicitly unavailable |
| GATE-M6 | M6 | Frozen candidate-package installation, upgrades, migration rollback, backup recovery; regression of every enabled capability in the release matrix; 5 target users from zero resources to a first result; cross-device artifact chains and all export regressions; rerunnable audit assets and document-relationship negative tests | Complete execution of AC-01—AC-27 according to the release matrix; out-of-scope unavailable combinations are listed as not applicable with reasons, without omitting initial main workflows or changing failures to not applicable |

Every task card must also identify the specific subset of the selected GATE, inputs, device / executor type, normal and failure cases, and evidence. “GATE-M1 tested” is not a substitute for actual file-import or state-control test records.

<a id="93-文档关系和审计资产负测"></a>

### 9.3 Document-relationship and Audit-asset Negative Tests

In temporary copies or memory, independently inject a WP-14 requirement mismatch, AC mismatch, removal of ordinary artifact-export objects from WP-29, changing M1 to 20—30 weeks while retaining the old total, an early subitem depending on an M6 subitem, a dependency cycle, missing audit mappings, or missing AC coverage relationships. The checker should reject and identify the specific file / line and relationship while the normal baseline still passes. Do not modify production source documents for negative tests. Duration checks read actual tables and narrative totals, distinguish historical references from current commitments, and do not hardcode duration constants.

E-05 asset acceptance requires obtaining confirmed versions, file manifests, digests, demo / tests / checkers, and explicit rerun commands from a fixed project location. A new team member rerunning the commands obtains results with their meaning stated. Preserve historical sources and report known-issue reproduction separately from fix regression. WP-04 organizes the fixed location and manifests in M1; WP-30 maintains relationship checks and negative tests throughout phases and consolidates acceptance in M6. These do not replace browser operations or manual content review.

<a id="10-报告模板"></a>

## 10. Report Template

Every report must include report ID, corresponding requirements / work packages, code commit, application-package identity, model and data versions, environment digest, operation steps, expected results, actual results, log / artifact references, pass / fail / untested status, limitations, and retest results.

Release acceptance must use the same installer and runtime dependencies that will be delivered. Repackaging or changing signatures, drivers, or model versions invalidates related acceptance and requires retesting according to impact.
