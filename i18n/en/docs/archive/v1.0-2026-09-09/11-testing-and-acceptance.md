<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/11-testing-and-acceptance.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/11-testing-and-acceptance.md) · [English](11-testing-and-acceptance.md)
<!-- translation-navigation:end -->

<a id="测试策略与验收标准"></a>

# Testing Strategy and Acceptance Criteria

Version: 1.0 · Date: 2026-09-09 · Status: prototype tests rerun; real product tests remain a plan awaiting execution.

Related documents: [Requirements](01-product-requirements.md), [Work packages](10-work-breakdown.md), [Release](12-operations-and-release.md), [Prototype evidence](14-prototype-traceability.md).

<a id="1-证据层级"></a>

## 1. Evidence Levels

| Level | What it proves | What it does not prove |
| --- | --- | --- |
| Documentation and static checks | Requirements, links, examples, and fields are consistent | The application actually runs |
| Prototype state tests | Simulated states, some validation and interaction intent | Real execution, persistence, or performance |
| Unit / contract tests | Rules, interfaces, states, parameter mappings | Actual drivers, model loading, or final experience |
| Integration tests | Database, process, file, and service interactions | Universal support for all hardware and models |
| Real-device tests | Real execution and metrics for specified combinations | Untested versions and other devices |
| User end-to-end acceptance | A complete task from the actual entry point to final artifacts | Unexecuted workflows such as external publishing or upgrades |
| Release acceptance | A specific installer and support matrix are deliverable | Future versions automatically inherit a pass |

Test reports must identify level, inputs, environment, versions, execution time, results, and limitations. Prototype tests and simulated execution must not enter real performance statistics.

<a id="2-已有基线"></a>

## 2. Existing Baseline

This round reran prototype `test-ailab-unified.cjs`, reporting 42 representative validation groups passed, and `test-ailab-runtime.cjs`, reporting 17 runtime-optimization validation groups passed. Prototype script syntax, HTML-fragment structure, and size below 1 MB checks passed.

These 59 groups are test groups reported by prototype scripts, not 59 real model/hardware combinations. Major-page clicking and dark/light/narrow-screen checks were completed in the preceding round; this documentation round does not claim that all browser flows or real hardware tests were rerun.

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

<a id="ac-03模型准备与独立加载"></a>

### AC-03: Model preparation and independent loading

Use a fixed model revision to download, pause/resume where supported, cancel, retry, and include a corrupt file. Expected: integrity failure cannot display preparation success; an independent process loads after completion; adapters requiring a base identify that dependency. Covers PRD-003.

<a id="ac-04数据导入检查与版本"></a>

### AC-04: Data import, checks, and versions

Import valid JSONL and four categories of negative cases; check line numbers, media, duplicates, and splits. After applying exclusion/resampling, verify original hashes remain unchanged and the new version is traceable; data changes invalidate old checks. Covers PRD-004.

<a id="ac-05市场访问与返回原任务"></a>

### AC-05: Marketplace Access and Return to the Original Task

Enter the marketplace from an existing training draft and complete open download, restricted application, denial, approval, download, and data selection respectively. Expected: incorrect schemas cannot be used; the original name, parameters, project, and step remain after returning; access approval does not display a label that judges authorization for the user. Covers PRD-005.

<a id="ac-06训练方法与更新方式"></a>

### AC-06: Training methods and update methods

Run minimal real training for each exposed combination, including at least first-phase SFT + LoRA. Verify target modules, data schema, optimization steps, and weight changes; the server rejects unsupported QLoRA/precision/device combinations. Add cases individually for new methods. Covers PRD-006.

<a id="ac-07任务生命周期"></a>

### AC-07: Task lifecycle

Cover queuing, preparation, running, cancellation, failure, checkpoints, and pause/resume where available. Expected: no terminal state without confirmation; failed retries create new attempts; old logs remain; recovery must not merely load weights while falsely claiming continuation of the original trajectory. Covers PRD-007.

<a id="ac-08真实运行与结果"></a>

### AC-08: Real execution and results

Actually execute text generation, image generation, video generation, TTS/ASR, and other exposed capabilities. Expected: inputs are used, output files are independently readable, and final results agree with history; preset images or audio cannot serve as real artifacts. Covers PRD-008.

<a id="ac-09运行参数真正生效"></a>

### AC-09: Runtime parameters actually take effect

Test disabling thinking, context, output limits, sampling, stop words, and streaming. Compare requested configuration, actual backend parameters, and observed results; over-budget rejection/truncation follows the user’s choice. Canceling an edit dialog preserves original values; running snapshots cannot be changed. Covers PRD-009.

<a id="ac-10缓存prefill-与-decode"></a>

### AC-10: Caching, Prefill, and Decode

With fixed models and inputs, verify cache isolation, invalidation, KV dtype, chunking, batching, concurrency, and CUDA Graph. Reject unsupported engine fields without dropping parameters. Block disaggregated deployment without connectors; once implemented, inject transfer and model-version mismatches. Covers PRD-010.

<a id="ac-11推测解码配对"></a>

### AC-11: Speculative Decoding Pairing

Test valid and mismatched inputs separately for ordinary draft, MTP, and DFlash. Reject missing MTP components and mismatched DFlash target, draft, template, or thinking conditions; after paired preparation, measure correctness, acceptance rate, and latency. Covers PRD-011.

<a id="ac-12设备与引擎适配"></a>

### AC-12: Device and Engine Adaptation

Register real devices individually and validate separation of reachability, detection, dependencies, loading, and running states. Save separate reports for NVIDIA, Apple, AMD, Intel, and CPU; different operating systems within the same brand do not automatically inherit support. Covers PRD-012.

<a id="ac-13媒体参数与-core-mlane"></a>

### AC-13: Media Parameters and Core ML / ANE

For images, check scheduler, CFG, VAE, and offloading; for video, frame rate, frame count, duration, and slicing; for audio, sample rate, slicing, streaming chunks, and transcription. Reject Core ML source-weight mismatches and execute converted artifacts independently; claim ANE use only with allocation evidence. Covers PRD-008, PRD-012, PRD-013.

<a id="ac-14评测与候选准入"></a>

### AC-14: Evaluation and Candidate Admission

Use fixed data and rules for baseline and candidate, and inject one below-threshold candidate and one corrupted artifact. Expected: neither can be registered as usable; passing candidates can be independently loaded for trials and return to their source experiments; repeated registration is idempotent. Covers PRD-014.

<a id="ac-15ai-建议模式"></a>

### AC-15: AI Suggestion Mode

Check that generating suggestions changes nothing, applying them modifies only allowlisted fields, expired revisions are rejected, undo does not overwrite later edits, submitted tasks are read-only, and malicious materials have no execution authority. Check remote-request scope and response boundaries for source questions. Covers PRD-017.

<a id="ac-16作品配方与来源"></a>

### AC-16: Works, recipes, and provenance

After saving artifacts, close the application, reopen, and load the recipe; check difference prompts after changing model version/device. Expected: inputs, artifacts, base/adapter, parameters, and provenance are all findable; favorites are not confused with saved files. Covers PRD-016.

<a id="ac-17完整媒体工作流"></a>

### AC-17: Complete media workflow

Actually complete image → video → voiceover, injecting a failure midway. Expected: preceding results remain, reruns mark old downstream results with source-version prompts, and all final artifacts open independently. Without composition capability, do not call it a final composed video. Covers PRD-015.

<a id="ac-18故障与恢复"></a>

### AC-18: Failure and recovery

Terminate processes during running, file writing, transaction commit, and event delivery; simulate full disk and remote disconnection. After restart, there are no duplicate executions, lost committed records, or partial files marked complete; unknown task states trigger reconnection and verification. Covers PRD-018.

<a id="ac-19模型实验室"></a>

### AC-19: Model lab

Execute merging, distillation, quantization, conversion, and behavioral comparisons individually. Check input compatibility, candidate independence, artifact hashes, quality regressions, and provenance chains. Unimplemented in-house entry points cannot start. Covers PRD-013.

<a id="ac-20幂等与竞争"></a>

### AC-20: Idempotency and Races

Double-click submission, resend the same idempotency key, reuse a key with different content, race cancellation with completion and AI with manual edits, and duplicate terminal events. Expected: one legal execution, explicit conflicts, and database/interface consistency. Covers PRD-007, PRD-018.

<a id="ac-21远程执行与输入边界"></a>

### AC-21: Remote execution and input boundaries

Test remote identity mismatches, invalid credentials, interrupted uploads, same-file deduplication, disconnection during execution, and log replay. Expected: no silent sending to another address, duplicate starts under unknown state, or plaintext secrets in diagnostics. Covers PRD-012, PRD-018.

<a id="ac-22安装升级备份与导出"></a>

### AC-22: Installation, upgrades, backups, and export

Install a specific candidate bundle in a clean environment, upgrade an old version containing task history, roll back a failed migration, and restore a backup. After export, load files in an independent process. Expected: consistent identity and data; uninstalling does not mean deleting model data. Covers PRD-018, PRD-019.

<a id="ac-23界面键盘与外观"></a>

### AC-23: Interface, Keyboard, and Appearance

Check dark/light layouts at 1024, 736, and 360 px and a minimum of 320 px, form labels, focus, dialogs, error associations, long names, Chinese paths, empty states, and large lists. Complete one task using the keyboard; static screenshots cannot replace key interactions. Covers PRD-002, PRD-020.

<a id="ac-24性能与质量对照"></a>

### AC-24: Performance and Quality Comparisons

For each advertised optimization, compare disabled / enabled operation with fixed workload, precision, and environment, recording cold / warm runs, concurrency, memory, and quality. Include cases with no benefit or slowdowns instead of selecting the best samples as a general conclusion. Covers PRD-010, PRD-011, PRD-012.

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

- Unit layer: parameter schema, versions, data splits, state transitions, suggestion application, and cache keys.
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

M1 passes persistence and task contracts; M2 real inference and parameters; M3 the training-to-candidate flow; M4 media and marketplace; M5 accepts each new combination independently; M6 passes installation, upgrades, recovery, and full regression. Every phase retains failed cases as later regression inputs.

<a id="10-报告模板"></a>

## 10. Report Template

Every report must include report ID, corresponding requirements / work packages, code commit, application-package identity, model and data versions, environment digest, operation steps, expected results, actual results, log / artifact references, pass / fail / untested status, limitations, and retest results.

Release acceptance must use the same installer and runtime dependencies that will be delivered. Repackaging or changing signatures, drivers, or model versions invalidates related acceptance and requires retesting according to impact.
