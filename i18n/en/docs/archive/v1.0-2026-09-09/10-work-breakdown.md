<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/10-work-breakdown.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/10-work-breakdown.md) · [English](10-work-breakdown.md)
<!-- translation-navigation:end -->

<a id="开发工作包与交付清单"></a>

# Development Work Packages and Deliverables

Version: 1.0 · Date: 2026-09-09 · Status: development baseline transferable to a task management system; all real implementation work has yet to begin.

Related documents: [Phase plan](09-development-roadmap.md), [Requirement IDs](01-product-requirements.md), [Acceptance cases](11-testing-and-acceptance.md).

<a id="1-工作包使用规则"></a>

## 1. Work Package Rules

Each work package requires a named owner, input version, delivery branch, test records, and review result. Responsibilities below suggest roles, not assigned people. Sizes use S/M/L: S approximately 2—4 person-days, M approximately 5—8, L approximately 9—15; hardware or algorithm validation may exceed these and should be split after technical experiments.

These sizes compare task scale only; summing all rows does not produce a project commitment. Adapter work packages may expand repeatedly by model, device, and version.

<a id="2-基础与控制层"></a>

## 2. Foundations and Control Layer

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| WP-01 First-phase combinations and environment experiments | M0 | ML + platform / M | PRD-012 | Exact model, device, environment locks, and minimal hardware records | None | AC-12 |
| WP-02 Desktop shell and sidecar experiments | M0 | Frontend + platform / M | PRD-018 | Startup/shutdown, crash, restart, and packaging experiments | None | AC-01, AC-22 |
| WP-03 Domain contracts and database | M1 | Backend / L | PRD-001, PRD-018 | schema, migrations, version objects, transaction APIs | WP-01 | AC-01, AC-18 |
| WP-04 Formal interface and interaction components | M1 | Frontend / L | PRD-002, PRD-020 | Four workbenches, tabs, forms, focus, and empty states | WP-02, WP-03 | AC-02, AC-23 |
| WP-05 Assets and importers | M1 | Backend / L | PRD-003, PRD-004, PRD-016 | Real files, verification, manifests, references, temporary-file handling | WP-03 | AC-03, AC-04, AC-16 |
| WP-06 Tasks, queues, and events | M1 | Backend / L | PRD-007, PRD-018 | Idempotent submission, state machine, SSE, reconnection, cancellation | WP-03 | AC-07, AC-18, AC-20 |
| WP-07 Capability queries and field contracts | M1—M2 | ML + backend / L | PRD-006, PRD-009, PRD-012 | Adapter schema, version conditions, actual parameter mappings | WP-01, WP-03 | AC-06, AC-09, AC-12 |
| WP-08 Environment preparation and remote execution | M2 | Platform / L | PRD-012, PRD-018 | Isolated environments, remote identity, transfer, log recovery | WP-05, WP-06, WP-07 | AC-12, AC-18, AC-21 |

<a id="3-推理训练与-ai"></a>

## 3. Inference, Training, and AI

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| WP-09 Apple text runtime adapter | M2 | ML / L | PRD-008, PRD-009 | Loading, generation, cancellation, and actual parameters for MLX or selected engine | WP-05—WP-07 | AC-08, AC-09 |
| WP-10 NVIDIA service runtime adapter | M2 | ML + platform / L | PRD-008, PRD-009, PRD-012 | Service lifecycle, model loading, streaming, resource release | WP-07, WP-08 | AC-08, AC-12, AC-21 |
| WP-11 Runtime forms and recipe end-to-end flow | M2 | Frontend + backend / M | PRD-009, PRD-016 | Five settings groups, staged application, cancellation, snapshots, reuse | WP-07, WP-09 | AC-09, AC-16 |
| WP-12 Data checks and SFT + LoRA | M3 | ML + backend / L | PRD-004, PRD-006, PRD-007 | Real data processing, training, checkpoints, recovery | WP-05—WP-08 | AC-04, AC-06, AC-07 |
| WP-13 AI suggestions and control isolation | M3 | Backend + frontend / M | PRD-017 | Local/remote connections, structured suggestions, preview/apply/undo | WP-03, WP-04, WP-07 | AC-15 |
| WP-14 Evaluation and candidate registration | M3 | ML + backend / L | PRD-014 | Fixed evaluation sets, reports, admission, provenance, candidate trials | WP-09, WP-12 | AC-14 |
| WP-15 Training-method extensions | M3—M5 | ML / L per combination | PRD-006 | Individual adapters for QLoRA, full-parameter, CPT, DPO, GRPO, PPO | WP-12, WP-14 | AC-06, AC-14 |
| WP-16 Cache and scheduling optimization | M2 baseline, M5 extensions | ML / L | PRD-010 | KV/prefix/Prefill/Decode/graph-capture mappings and reports | WP-09, WP-10 | AC-10, AC-24 |
| WP-17 Speculative decoding | M5 | ML / L per strategy | PRD-011 | Paired preparation, validation, and comparisons for ordinary draft, MTP, DFlash | WP-14, WP-16 | AC-11, AC-24 |

<a id="4-媒体市场和专项"></a>

## 4. Media, Marketplace, and Specialized Work

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| WP-18 Image adaptation and optimization | M4 | ML + frontend / L | PRD-006, PRD-008 | Image data, fine-tuning, generation, VAE/offloading, real images | WP-11, WP-12, WP-14 | AC-06, AC-08, AC-13 |
| WP-19 Video adaptation and timing | M4 | ML + frontend / L | PRD-006, PRD-008 | Video decoding, slicing, training/generation, temporal metadata | WP-05, WP-18 | AC-08, AC-13 |
| WP-20 Audio task adapters | M4 | ML + frontend / L per task | PRD-006, PRD-008 | TTS/ASR first, VC/music later, sampling/slicing and artifacts | WP-05, WP-11, WP-12 | AC-08, AC-13 |
| WP-21 Workflows and material continuation | M4 | Backend + frontend / M | PRD-015, PRD-016 | Node artifact transfer, failure retention, stale-input markers, saving | WP-18—WP-20 | AC-17 |
| WP-22 Data marketplace connectors | M4 | Backend + frontend / L | PRD-005 | Source catalog, versions, access requests, downloads, return to original task | WP-05, WP-08 | AC-05 |
| WP-23 Model merging and distillation | M5 | ML / L per method | PRD-013 | Input compatibility checks, teacher-output versions, independent artifacts, evaluation | WP-12, WP-14 | AC-19 |
| WP-24 Quantization, conversion, and ANE | M5 | ML + platform / L per format | PRD-013, PRD-019 | Format artifacts, numerical comparisons, Core ML/ANE hardware evidence | WP-14, WP-18 | AC-13, AC-19 |
| WP-25 Heretic/Abliterix comparisons | M5 | ML / L | PRD-013 | Source-version checks, independent execution, normal-capability and target comparisons | WP-12, WP-14 | AC-19 |
| WP-26 AMD/Intel/CPU adaptation | M5 | ML + platform / L per combination | PRD-012 | ROCm/HIP, SYCL, OpenVINO, CPU validation matrix | WP-07, WP-08, WP-16 | AC-12, AC-24 |
| WP-27 Disaggregated Prefill/Decode | M5, independently deferrable | Platform + ML / L | PRD-010 | Two services, KV connectors, failure recovery, performance evidence | WP-10, WP-16, WP-21 | AC-10, AC-21, AC-24 |

<a id="5-发布与稳定化"></a>

## 5. Release and stabilization

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| WP-28 Backup, migration, and cleanup | M1 foundation, M6 acceptance | Backend + platform / L | PRD-018, PRD-016 | Consistent backups, rollback, reference checks, recoverable cleanup | WP-03, WP-05, WP-06 | AC-18, AC-22 |
| WP-29 Installers and updates | M6 | Platform + frontend / L | PRD-018, PRD-019 | Installation, identity, signing, updates, diagnostic export | WP-02, WP-08, WP-28 | AC-22 |
| WP-30 Regression and user acceptance | M6 | Testing + product / L | PRD-001—PRD-020 | Hardware matrix, user paths, performance, known limitations, release checklist | All target work packages for this version | AC-01—AC-24 |

<a id="6-重点工作包的可执行拆分"></a>

## 6. Executable breakdowns of key work packages

<a id="wp-07-能力查询"></a>

### WP-07 Capability queries

1. Define parameter schema: types, units, default sources, allowed values, conflicts, restart requirements.
2. Define device facts and version digests, supporting probe failures/unknown values.
3. Implement capability mappings for the first two engines.
4. Generate available frontend options from the schema, retaining Chinese explanations.
5. Independently enforce the same constraints on submission and return actual parameters.
6. Write tests for unsupported combinations and silently dropped parameters.

Completion criteria: at least one control changes with model/engine/device; the backend rejects forged requests; actual execution records match the form.

<a id="wp-12-训练闭环"></a>

### WP-12 Training end-to-end flow

1. Parse real JSONL into a fixed data version and generate a check report.
2. Split training and validation by source groups with a fixed seed.
3. Map SFT + LoRA parameters to the specified training-library version.
4. Write steps, loss, checkpoints, and failures as durable events.
5. Verify cancellation, failure, new attempts, and checkpoint recovery.
6. Output independent adapter files and load them in a clean process.

Completion criteria: optimization steps actually update target parameters, artifacts load, and original model/data hashes remain unchanged; exit code 0 cannot substitute for these checks.

<a id="wp-17-推测解码"></a>

### WP-17 Speculative decoding

Split into three strategy-specific subtasks, each selecting its own target model and components. Measure standard decoding first, then the enabled strategy; fix model, precision, input length, output length, and concurrency. Save acceptance rate, total latency, and quality comparisons; if there is no benefit, “not recommended by default” is a valid conclusion.

<a id="wp-24-转换与-ane"></a>

### WP-24 Conversion and ANE

First confirm input format and shapes and establish numerical comparison cases; after conversion, load independently and run on the target device. Save Core ML compute-unit policy separately from actual execution allocation. Without ANE allocation evidence, the report may state only that Core ML execution passed.

<a id="7-每张开发任务卡必须包含"></a>

## 7. Every development task card must include

Objective, requirement IDs, input material, precise implementation scope, explicitly excluded adjacent work, dependencies, delivery files, error cases, automated tests, real operation steps, performance/data boundaries, completion evidence, and reviewer.

Task states are not started, in progress, awaiting review, awaiting acceptance, complete, and blocked. Enter complete only when tests and required hardware evidence are complete. Deferred features retain their requirements and reasons; tracking IDs are not deleted.

<a id="8-第一批可启动任务"></a>

## 8. First tasks that can start

Schedule technical experiments for WP-01 and WP-02 first, then complete WP-03, WP-06, and WP-07 contracts based on their results; WP-04 and WP-05 may overlap after contracts stabilize. Do not integrate every model library simultaneously before task, version, and capability models are settled.

This round created no development branch, installed no environment, and ran no real training. These work packages form the complete task baseline for subsequent implementation.
