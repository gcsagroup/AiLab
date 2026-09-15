<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/09-development-roadmap.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/09-development-roadmap.md) · [English](09-development-roadmap.md)
<!-- translation-navigation:end -->

<a id="开发路线里程碑与资源计划"></a>

# Development Roadmap, Milestones, and Resource Plan

Version: 1.0 · Date: 2026-09-09 · Status: proposed schedule based on the final Demo; work has not started and no actual delivery dates exist.

Related documents: [Work packages](10-work-breakdown.md), [Test gates](11-testing-and-acceptance.md), [Risks and decisions](13-decisions-risks-and-questions.md).

<a id="1-实施顺序"></a>

## 1. Implementation Order

Establish real tasks and data persistence before expanding models and hardware; prove one complete combination before adding optimization switches. Keep the four workbench categories and existing auxiliary entry points, integrating backends in phases. Features not yet connected display their actual state rather than all disappearing into an unreviewable “future version.”

The first real path is language-model inference and an SFT + LoRA end-to-end flow. It covers projects, models, data, devices, execution, evaluation, artifacts, trials, recipes, and recovery to validate shared architecture. Media, specialist experiments, and multiple hardware platforms follow, avoiding a separate task system for every module.

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

| Phase | Proposed duration | Main objective | Entry criteria | Exit criteria |
| --- | --- | --- | --- | --- |
| M0 Scope and technical verification | 1—2 weeks | Freeze first-phase combinations; minimal packaging and executor verification | This documentation is reviewable | Selection records, model/device inventory, minimal hardware report |
| M1 Application and data foundation | 2—3 weeks | Productize prototype; persist projects/assets/tasks | M0 contracts and storage direction determined | Draft recovery, import, queue, and event contracts pass |
| M2 Real inference and runtime configuration | 3—4 weeks | Apple local and NVIDIA service inference with real parameters | M1 foundation usable | Real output, parameter readback, recipe reload, and cancellation pass |
| M3 Training and evaluation end-to-end flow | 3—4 weeks | SFT + LoRA, checkpoints, evaluation, candidate trials | M1 data and tasks; M2 trials | Complete real-hardware path from data to candidate |
| M4 Media and data marketplace | 4—6 weeks | Minimal image/video/audio combinations and workflows | Shared tasks, artifacts, and evaluation stable | At least one real combination in each of four categories; marketplace return path passes |
| M5 Specialist experiments and advanced adapters | 4—6 weeks | Distillation and other specialties, multiple hardware platforms, cache scheduling/speculative optimization | Baseline models, evaluation sets, and devices available | Independent report for each item; failing combinations disabled |
| M6 Release and stabilization | 2—3 weeks | Installation, upgrades, recovery, performance, documentation, release bundle | Target feature matrix defined | Complete release acceptance checklist; demo paths isolated from production |

Sequential total is approximately 19—28 weeks, excluding device procurement, major upstream blockers, and requirement changes. Limited overlap of independent modules is allowed, but exit criteria must remain; overlapping schedules must not compress real effort into implausible dates. When specialist and hardware matrices are large, M5 may span multiple later releases instead of being forced into the same release window.

<a id="4-m0形成可执行基线"></a>

## 4. M0: Establish an Executable Baseline

<a id="交付物"></a>

### Deliverables

- Initial model: fixed text-model and tokenizer revisions; training and inference use source versions that can validate each other.
- Initial devices: exact Apple model / memory, NVIDIA model / GPU memory, operating systems, and drivers.
- Desktop-shell and Python-sidecar startup, exit, crash, and restart experiments.
- Run records for one real inference command and one minimal training command; these validate technology selection only, not the product end-to-end flow yet.
- Initial capability declarations, submission snapshot schema, task state machine, and storage layout.
- Selection decisions requiring approval in ADRs and evidence-supported alternatives.

<a id="停止调整条件"></a>

### Stop / Adjustment Conditions

If the target model cannot load, drivers are incompatible, or packaging dependencies cannot be reproduced reliably, adjust that combination first rather than continuing to mark it supported in the frontend. If the Tauri host delays core validation, a local Web interface may temporarily validate contracts; record the desktop-product decision separately.

<a id="5-m1应用和持久化基础"></a>

## 5. M1: Application and Persistence Foundations

Convert the final Demo into formal components while preserving the four category entry points, model library, data marketplace, lab, and AI panel. Establish database structures for projects, tasks, data, models, and works; support safe file selection, import, metadata, and draft saving.

Implement task states, event streams, idempotent submission, and a fake executor. The fake executor is for development and tests only, requires an explicit mode, and is not evidence of real model support.

Exit acceptance: after killing and restarting the control service, drafts and indexes remain; long-running task state is recoverable; errors are locatable; background results from other projects do not leak into the current project; file corruption and insufficient disk space have recoverable handling.

<a id="6-m2真实推理与参数生效"></a>

## 6. M2: Real Inference and Effective Parameters

First complete one Apple local text-inference adapter and one NVIDIA service-inference adapter. Implement model preparation, loading, unloading, input processing, streamed output, cancellation, result saving, actual parameter recording, and recipe reloading.

Expose verified thinking toggles, context, output limits, and sampling parameters; begin KV, prefix caching, and scheduling with a small set of measurable combinations. Keep explanations and unverified status for remaining advanced options instead of rushing to expose everything.

Exit acceptance: input/output token budgets are correct; the backend actually uses the configuration; recipe reload explains environment differences; offline local inference, remote interruption, and resource cleanup after cancellation pass.

<a id="7-m3训练与评测闭环"></a>

## 7. M3: Training and Evaluation Loop

Implement SFT + LoRA data checks, training, checkpoints, recovery, independent evaluation, candidate registration, and direct trials. Before adding QLoRA or full-parameter paths, fix the backend and hardware; “LoRA runs” does not establish completion of other update methods.

Connect AI assistance to a real suggestion model, exposing only defined fields and completing preview, apply, undo, and conflict tests. The first internal test version is formed here, limited to accepted language tasks and devices.

Exit acceptance: real data → weight updates → independent artifacts → evaluation → candidate trials; failed retries retain original tasks; checkpoint resumption has consistency records; AI has no execution authority.

<a id="8-m4媒体和工作流"></a>

## 8. M4: Media and Workflows

Select one image generation/fine-tuning combination, one short-video combination, and one speech or ASR combination, then gradually add other audio tasks. Each category must verify real file reads, real artifacts, and task-specific parameters; copied text-task pages are not substitutes.

Implement result transfer for “product image → video → voiceover,” stale-result markers, stage reruns, and saving the whole workflow. Integrate at least one controlled data-marketplace source and verify restricted access, versioning, downloads, and return to the original task.

Exit acceptance: all three steps have complete real-artifact provenance; image, video, and audio metrics and manual checks have corresponding reports; downloaded data remains usable when marketplace APIs are unavailable.

<a id="9-m5专项和多硬件"></a>

## 9. M5: Specialized Work and Multiple Hardware Backends

Advance quantization, conversion, merging, distillation, and behavior adjustment independently according to maturity. Start with smaller models and repeatable evaluation sets, defining each operation's input formats and artifacts rather than building a shared empty shell and claiming everything complete.

Add AMD / ROCm, Intel / SYCL, OpenVINO / NPU, and Core ML / ANE to the device matrix individually. MTP and DFlash use matched target models, components, and versions, with optimization-on / off comparisons. If deployment conditions for Prefill / Decode separation are unavailable, defer it as an independent work package without blocking other optimizations.

Exit acceptance: each exposed combination has support scope, limitations, test samples, and a report; unverifiable combinations remain unverified or unsupported.

<a id="10-m6稳定化与发布"></a>

## 10. M6: Stabilization and Release

After freezing the candidate version, test clean-machine installation, upgrade / rollback, database migration, backup recovery, long tasks, disk-full conditions, and network faults. Real mode contains no preset success reports, simulated-connection shortcuts, or fabricated progress.

Write the user manual and release notes from the actual support matrix, including installer identity, dependency versions, known issues, recovery methods, and compatibility list. Accept release actions separately from release-bundle preparation.

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

This plan has no confirmed team schedule, device budget, or formal launch window. Reestimate after M0 starts using actual loading, training, packaging, and test results. A solo implementer cannot directly adopt the calendar durations above; reduce parallel work and make staged commitments around complete end-to-end flows.
