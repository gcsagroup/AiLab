<!-- translation-navigation:start -->
[简体中文](../../../docs/09-development-roadmap.md) · [繁體中文](../../zh-TW/docs/09-development-roadmap.md) · [English](09-development-roadmap.md)
<!-- translation-navigation:end -->

<a id="开发路线里程碑与资源计划"></a>

# Development Roadmap, Milestones, and Resource Plan

Version: 1.1 · Date: 2026-09-09 · Status: Scope and phase gates revised following the audit; real development has not started, and timelines await reassessment after technical experiments.

Related documents: [Work packages](10-work-breakdown.md), [Testing gates](11-testing-and-acceptance.md), [Risks and decisions](13-decisions-risks-and-questions.md), [Audit remediation plan](16-audit-remediation-plan.md).

<a id="1-实施顺序"></a>

## 1. Implementation Order

Establish real tasks and data persistence before expanding models and hardware; prove one complete combination before adding optimization switches. Keep the four workbench categories and existing auxiliary entry points, integrating backends in phases. Features not yet connected display their actual state rather than all disappearing into an unreviewable “future version.”

The first real path is language-model inference and an SFT + LoRA loop. It covers projects, models, data, devices, execution, evaluation, artifacts, trials, recipes, and recovery, validating the shared architecture. Bring forward the risk of loading the same LoRA artifact on the target trial device into M0 technical experiments; M3 then validates the complete product path. Expand media, specialized experiments, and hardware afterward to avoid separate task systems for each module.

This version includes the required remediation for AUD-01—AUD-14 and adopts E-01—E-05 at minimum scope: first-time user path, three runtime presets, cross-device artifact validation, result revision versions, and rerunnable audit assets. This revision completes specifications and plans only; it does not mean prototype issues have been fixed or real capabilities have passed acceptance.

<a id="2-资源假设"></a>

## 2. Resource Assumptions

| Role | Suggested allocation | Responsibilities |
| --- | --- | --- |
| Product / interaction | 0.5 person | Requirement tradeoffs, workflow acceptance, copy, usability |
| Frontend / desktop | 1 person | Pages, forms, desktop host, state recovery |
| Backend / platform | 1 person | Control service, metadata, files, tasks, remote execution |
| ML training / inference | 2 people | Training, inference, media, quantization, adapter validation |
| Testing / quality | 0.5—1 person | Automation, real devices, regression, release evidence |

The estimate assumes sustained staffing of approximately 5—5.5 people and access to Apple Silicon, an NVIDIA Linux server, and later AMD / Intel test devices. It is not a one-person execution estimate. When devices, data, or adapter license / version validation are unavailable, the corresponding phase is delayed separately; simulated results do not replace delivery.

<a id="3-阶段总览"></a>

## 3. Phase Overview

| Phase | Reference duration for 1.0 scope | Main goal | Entry conditions | Exit conditions |
| --- | --- | --- | --- | --- |
| M0 Scope and technical validation | 1—2 weeks | Converge documents; test exact combinations, shell sidecar, and the same LoRA across devices | Remediation contracts and experiment scope defined | TV-01, TV-02, TV-03; selection records and reassessment list |
| M1 Application and data foundations | 2—3 weeks | Productionize the prototype; persist projects / assets / tasks | M0 contracts and storage direction determined | GATE-M1: persistence, trust plans, complete fake-executor state and collection-retry contracts |
| M2 Real inference and runtime configuration | 3—4 weeks | Apple local and NVIDIA service inference with real parameters | M1 foundations usable | GATE-M2: real output, configuration consistency, pairing rejection, presets, cancellation, collection retries |
| M3 Training and evaluation loop | 3—4 weeks | SFT + LoRA, checkpoints, evaluation, candidate trials, export | M1 data and tasks; M2 trials | GATE-M3: supervised tokens, target trials with the same artifact, model / adapter / report export |
| M4 Media and dataset marketplace | 4—6 weeks | Minimum image / video / audio combinations and workflows | Shared tasks, artifacts, and evaluation stable | GATE-M4: minimum combinations for all four categories, workflow execution identity and atomic advancement, media export |
| M5 Specialized experiments and advanced adapters | 4—6 weeks | Distillation and other specialized work, multiple hardware backends, caching / scheduling / speculative optimization | Baseline models, evaluation sets, and devices available | GATE-M5: independent reports for each item, bidirectional format / engine validation, combinations below threshold disabled |
| M6 Release and stabilization | 2—3 weeks | Installation, upgrades, recovery, performance, documentation, release packages | Target feature matrix defined | GATE-M6: candidate package, final AC-01—AC-27 matrix, and first-time user acceptance passed |

The sequential total of 19—28 weeks in the table is a reference for the 1.0 scope, retained to identify scope changes; it is **not a 1.1 delivery commitment**. It originally assumed only a minimum combination per category, explicit M5 scope cuts, and sustained staffing of approximately 5—5.5 people. It excludes device procurement, upstream blockers, additional hardware / training methods, and separate effort for the work added in this revision. New abnormal-state handling, collection-only retries, exporters, negative cases, first use, and cross-device validation do not yet have measured person-day estimates and must not be treated as zero-cost additions.

At M0 exit, re-estimate phase ranges from the subtasks of all 30 work packages, device availability, and validation costs. State the added-scope delta, critical path, and deferrable combinations before committing dates. Limited overlap among independent modules is allowed, but exit conditions must remain. If the specialized-work and hardware matrix is too large, split M5 into later versions; complete user paths already in scope cannot preserve the old timeline merely by compressing testing.

<a id="4-m0形成可执行基线"></a>

## 4. M0: Establish an Executable Baseline

<a id="先收敛文档合同"></a>

### Converge Document Contracts First

Before technical experiments, unify workflow identity, configuration interactions, task-control exceptions, collection retries, supervision recipes, model trust, and export ownership. Relationship checks should detect mismatches and reversed phase dependencies. Documents must be implementable here; **M0 is not required to complete the product backends for these modules**. Implementation fixes for prototype AUD-01—AUD-06 belong to the corresponding work packages; retain known-issue markers until complete.

<a id="交付物"></a>

### Deliverables

- Initial model: fixed text-model and tokenizer revisions; training and inference use source versions that can validate each other.
- Initial devices: exact Apple model / memory, NVIDIA model / GPU memory, operating systems, and drivers.
- Desktop-shell and Python-sidecar startup, exit, crash, and restart experiments.
- TV-01: record real inference, minimum training, and environment reproduction for exact model, engine, and device combinations.
- TV-02: shell and sidecar startup / shutdown, crashes, restarts, paths, and logs in a minimum packaging experiment; does not depend on a project database, production signing, or complete upgrades.
- TV-03: take the same actual LoRA artifact produced by TV-01 from the NVIDIA training environment to the specified Apple trial device, fixing the base-model revision, template, and target engine, and load it independently. If conversion is needed, save input / output digests and conversion steps. Command-line execution is sufficient; this is not yet the product loop.
- Initial capability declarations, submission snapshot schema, task state machine, and storage layout.
- Selection decisions requiring resolution in ADRs and evidence-backed alternatives; 1.1 scope reassessment table.

Exit requires only TV-01—TV-03 and the document records above. AC-01, AC-12, AC-22, AC-26, and others track later complete acceptance and must not block completion of M0 experiment work packages in reverse. If the cross-device path is infeasible, adjust the target combination and rerun TV-03; do not mark support first and wait for M3 to supply evidence.

<a id="停止调整条件"></a>

### Stop / Adjustment Conditions

If the target model cannot load, drivers are incompatible, or packaging dependencies cannot be reproduced reliably, adjust that combination first rather than continuing to mark it supported in the frontend. If the Tauri host delays core validation, a local Web interface may temporarily validate contracts; record the desktop-product decision separately.

<a id="5-m1应用和持久化基础"></a>

## 5. M1: Application and Persistence Foundations

Convert the final demo into production components, preserving the four entry categories, model library, dataset marketplace, lab, and AI panel. Establish database structures for projects, tasks, data, models, and works; support safe file selection, import, metadata, and draft saving. In M1, WP-04 organizes fixed project locations, manifests, digests, and rerun commands for the prototype and tests, preserving old assets. In M6, WP-30 validates rerunning by a new team member.

Implement task states, event streams, idempotent submission, and fake executors. Cover pause-checkpoint failure, cancellation while pausing, cancellation / completion races, force-stop, and unknown stop status. Separate computation results from collection records; fake-executor tests ensure collection retries do not invoke run / resume and do not change the original attempt's terminal state. Model import plans also save loading methods and trust classes; restricted-loading failures must not automatically relax execution capabilities. Fake executors are only for development and testing, with an explicit mode, and are not evidence of real model support.

Exit acceptance follows GATE-M1: after killing and restarting the control service, drafts and indexes remain; development-executor states recover, and negative control / collection-retry contract cases pass; cross-project background results do not enter the current project; file corruption and insufficient disk space have recoverable handling. This accepts only the M1 subset and does not require completion of real models, training candidates, M4 media, or M6 installation / upgrades.

<a id="6-m2真实推理与参数生效"></a>

## 6. M2: Real Inference and Effective Parameters

First complete one Apple local text-inference adapter and one NVIDIA service-inference adapter. Implement model preparation, loading, unloading, input processing, streamed output, cancellation, result saving, actual parameter recording, and recipe reloading.

Enable validated thinking switches, context, output limits, and sampling parameters. Start with a small number of measurable KV, prefix-cache, and scheduling combinations. Other advanced options retain explanations and unverified status rather than being opened all at once. Changes to the model / strategy / engine / artifact format revalidate task mode, materials, and companion components; the submission side rejects stale configuration. Parameter summaries, execution location beside the button, and transmission scope all derive from the configuration applied for this attempt.

Add three explainable presets—“Model defaults,” “Low memory,” and “Low latency”—bound to validated combinations. Show actual field differences before applying; cancellation leaves values unchanged, and unmeasured benefits are not claimed. Prefix-cache tests include media identity, order, processors, and preprocessing parameters; unknown combinations remain disabled. First-use guidance establishes an operable language-trial path in this phase.

Exit acceptance follows GATE-M2: correct input / output token budgets; agreement among the interface, applied configuration, request snapshot, actual backend parameters, and execution location; recipes / presets explain invalidated items; offline local inference, remote interruption, resource release after cancellation, and collection retries without recomputation pass.

<a id="7-m3训练与评测闭环"></a>

## 7. M3: Training and Evaluation Loop

Implement SFT + LoRA data checks, versioned tokenization and supervision recipes, training, checkpoints, resumption, independent evaluation, candidate registration, and direct trials. Check final tokens / labels for multi-turn, overlong, empty-answer, EOS / PAD, and packing boundaries; count effective supervised tokens and reject zero-supervision samples. Lock the backend and hardware before adding QLoRA or full-parameter paths; “LoRA runs” does not complete other update methods.

Connect AI assistance to a real suggestion model, exposing only defined fields and completing preview, apply, undo, and conflict tests. The first internal test version is formed here, limited to accepted language tasks and devices.

WP-29's model / adapter / text-work / report export subitems are delivered in M3, jointly owned by backend and frontend: object selection, dependency resolution, manifests, integrity, persistence, cancellation / failure recovery, and use in an independent environment. This does not depend on M6 installation and update work.

Exit acceptance follows GATE-M3: real data → weight updates → independent artifacts → evaluation → trial of the same artifact on the target device and export; failed retries preserve original tasks, collection failures retry collection only; checkpoint resumption has consistency records; AI has no execution authority.

<a id="8-m4媒体和工作流"></a>

## 8. M4: Media and Workflows

Select one image generation / fine-tuning combination, one short-video combination, and one TTS combination capable of voice-over. Add ASR, voice conversion, and music according to the frozen matrix. Integrating ASR alone cannot satisfy the voice-over output of the three-step workflow. Each category must validate real file reads, real artifacts, and task-specific parameters; copied text-task pages are not substitutes.

Implement result transfer, stale-result markers, stage reruns, and overall saving for “Product image → Video → Voice-over.” Each execution, step attempt, and input version has a separate ID. By default, only artifacts from the current step of this run are usable; explicit reuse of old artifacts must record provenance. Validate target occupancy before committing advancement atomically; failure does not change the step, outputs, or source draft, and repeated clicks advance only once.

WP-29 adds image, video, and audio work exports. Manual subtitle / transcription edits create WorkRevision records, preserving original results and generation recipes; regeneration does not implicitly apply manual revisions. The dataset marketplace integrates at least one controlled source to validate restricted-access flows, versions, downloads, and return to the original task.

Exit acceptance follows GATE-M4: two rounds of the real three-step workflow and target-busy negative cases pass; provenance chains, media exports, and editing differences are complete; images, video, and audio each have reports; downloaded data remains usable when marketplace interfaces are unavailable.

<a id="9-m5专项和多硬件"></a>

## 9. M5: Specialized Work and Multiple Hardware Backends

Advance quantization, conversion, merging, distillation, and behavior adjustment independently according to maturity. Start with smaller models and repeatable evaluation sets, defining each operation's input formats and artifacts rather than building a shared empty shell and claiming everything complete.

Add AMD / ROCm, Intel / SYCL, OpenVINO / NPU, and Core ML / ANE to the device matrix individually. MTP and DFlash use matched target models, components, and versions, with optimization-on / off comparisons. If deployment conditions for Prefill / Decode separation are unavailable, defer it as an independent work package without blocking other optimizations.

Exit acceptance follows GATE-M5: every enabled combination has a support scope, limitations, test samples, and report; conversion candidates such as Core ML select a loadable engine from the “Candidate → Run” entry, rejecting incorrect formats / engines in both directions; switching speculative strategies invalidates mismatched preparation states; combinations that cannot be validated remain unverified or unsupported.

<a id="10-m6稳定化与发布"></a>

## 10. M6: Stabilization and Release

After freezing the candidate version, test clean-machine installation, upgrade / rollback, database migration, backup recovery, long tasks, disk-full conditions, and network faults. Real mode contains no preset success reports, simulated-connection shortcuts, or fabricated progress.

Write user manuals and release notes from the actual support matrix, including installer identity, dependency versions, known issues, recovery methods, and compatibility lists. Publishing and preparing a release package are accepted separately. GATE-M6 consolidates AC-01—AC-27 within the frozen scope; the same candidate package is used for 5 target users' journey from zero resources to a first result, artifact export after upgrading, cross-device artifact chains, and recovery regression.

Audit assets are placed in fixed versioned locations under E-05 with manifests, digests, and rerun commands, preserving original assets. This document revision cannot mark still-reproducible demo errors as completed product fixes.

<a id="11-版本建议"></a>

## 11. Version Recommendations

| Version | Phase gate | Scope |
| --- | --- | --- |
| Technical preview | M0—M2 end-to-end validation complete | Internal validation; cannot be called a complete product |
| Private Alpha | M3 | Language training / trial loop on limited hardware |
| Feature Beta | M4 + selected M5 work packages | Media workflows, some specialized work, and expanded adapters |
| First production release | M6, with evidence for the entire target matrix | Release within accepted scope and clearly list incomplete items |

<a id="12-依赖与关键路径"></a>

## 12. Dependencies and Critical Path

The critical path is: capability and snapshot contracts → assets / database → task execution and recovery → real inference → training and artifacts → independent evaluation → candidate trials → release acceptance.

Work that may overlap: data importers and frontend forms, remote executors and local inference, media decoding and specialized model-source checks. Dependencies that cannot be skipped: fixed data versions before fair evaluation; real parameter mappings before optimization benchmarks; artifact integrity before candidate registration; exact device identities before claiming ANE / ROCm / oneAPI acceptance.

<a id="13-进度管理与变更控制"></a>

## 13. Progress Management and Change Control

Update each work package weekly with completed evidence, work in progress, blockers, and next week's deliverables, rather than reporting percentages alone. End each phase with an actual task demonstration and test-report review.

Every new model or optimization switch requires a capability card and corresponding testing cost. Requirement changes update PRD IDs, work packages, acceptance cases, and the support matrix together. A simpler implementation that satisfies the goal may replace the plan, but it must not remove complete workflows already confirmed by the user.

<a id="14-估算边界"></a>

## 14. Estimation Boundaries

This plan has no confirmed team schedule, device budget, or official launch window. After M0 begins, reassess using actual loading, training, packaging, cross-device artifacts, and test results, listing effort for each added remediation and enhancement. Until reassessment is complete, the 1.0 estimate of 19—28 weeks is historical comparison only. A single-person implementation cannot directly use the calendar ranges above; reduce parallel work and make successive commitments in units of complete loops.
