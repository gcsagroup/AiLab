<!-- translation-navigation:start -->
[简体中文](../../../docs/10-work-breakdown.md) · [繁體中文](../../zh-TW/docs/10-work-breakdown.md) · [English](10-work-breakdown.md)
<!-- translation-navigation:end -->

<a id="开发工作包与交付清单"></a>

# Development Work Packages and Deliverables

Version: 1.1 · Date: 2026-09-09 · Status: Deliverables, phase subitems, and acceptance relationships supplemented following the audit; real product development has not started.

Related documents: [Phase plan](09-development-roadmap.md), [Requirement IDs](01-product-requirements.md), [Acceptance cases](11-testing-and-acceptance.md), [Audit remediation plan](16-audit-remediation-plan.md).

<a id="1-工作包使用规则"></a>

## 1. Work Package Rules

Every work package must have a named owner, input versions, delivery branch, test records, and review results. Responsibilities in the tables are suggested roles, not assigned staff. Sizes retain the 1.0 relative S / M / L scale; the original references were approximately 2—4 person-days for S, 5—8 for M, and 9—15 for L. Costs of new 1.1 exception recovery, export, cross-device work, and negative cases await reassessment after M0 measurements; the old sizes must not be treated as commitments already covering the additions.

Retain WP-01—WP-30 at the top level. Schedule work spanning phases independently using the subitems in Section 6; these split existing work packages rather than adding top-level modules. The phase-validation column states gates executable in the current phase; the final-AC column tracks complete product acceptance only and **does not require early work packages to complete every part of a final AC in advance**. Phase task cards must list the subset of [phase gates in 11](11-testing-and-acceptance.md) corresponding to that row's deliverables and its execution conditions.

Completion evidence for each work package applies only to the validated models, devices, versions, and feature scope. Combinations not enabled are marked untested or deferred; phase subsets must not be used to mark complete ACs passed. All sizes below await reassessment, and adapters still need expansion by actual combination.

<a id="2-基础与控制层"></a>

## 2. Foundations and Control Layer

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Phase validation | Final AC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WP-01 Initial combinations and environment experiments | M0 | ML + platform / M, reassessment pending | PRD-006, PRD-008, PRD-012, PRD-014 | Exact models, devices, and environments locked; minimum training and return of the same LoRA to the target device for a trial | None | TV-01, TV-03 | AC-06, AC-08, AC-12, AC-26 |
| WP-02 Desktop shell and sidecar experiments | M0 | Frontend + platform / M, reassessment pending | PRD-018 | Startup / shutdown, crashes, restarts, paths, and logs in minimum packaging | None | TV-02 | AC-01, AC-22 |
| WP-03 Domain contracts and database | M1 | Backend / L, reassessment pending | PRD-001, PRD-018 | schema, migrations, version objects, transactional interfaces, attempt / collection records | WP-01 | GATE-M1: project and transaction subset | AC-01, AC-18 |
| WP-04 Production interface and interaction components | M1 | Frontend / L, reassessment pending | PRD-002, PRD-020 | Four workbench categories, direct trials / continuation within categories, forms, focus, empty states; organize prototype / test manifests and fixed locations while preserving old assets | WP-02, WP-03 | GATE-M1: interface subset | AC-02, AC-23, AC-25 |
| WP-05 Assets and importers | M1 | Backend / L, reassessment pending | PRD-003, PRD-004, PRD-016 | Files, validation, manifests, references; model-loading methods and trust plans, rejection after restricted-loading failure | WP-03 | GATE-M1: files and import-plan subset | AC-03, AC-04, AC-16 |
| WP-06 Tasks, queues, and events | M1 | Backend / L, reassessment pending | PRD-007, PRD-018 | Idempotent submission, state machine, event reconnection; pause / cancel exceptions, force-stop, collection-only retry contracts | WP-03 | GATE-M1: fake-executor control and collection-retry subset | AC-07, AC-18, AC-20, AC-21 |
| WP-07 Capability queries and field contracts | M1—M2 | ML + backend / L, reassessment pending | PRD-006, PRD-008, PRD-009, PRD-011, PRD-012 | Model / mode / media / strategy-component / artifact-format interactions, schemas, actual parameter mappings | See WP-07a, WP-07b | GATE-M1, GATE-M2: validate by subitem | AC-06, AC-08, AC-09, AC-11, AC-12, AC-13 |
| WP-08 Environment preparation and remote execution | M2 | Platform / L, reassessment pending | PRD-003, PRD-012, PRD-018 | Execution-permission isolation, remote identity, transfer, log recovery, idempotent collection retries from original artifact manifests | WP-05, WP-06, WP-07b | GATE-M2: environment and remote subset | AC-03, AC-12, AC-18, AC-21 |

<a id="3-推理训练与-ai"></a>

## 3. Inference, Training, and AI

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Phase validation | Final AC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WP-09 Apple text runtime adapter | M2 | ML / L, reassessment pending | PRD-008, PRD-009 | Real loading, generation, cancellation, actual parameters, and loadable adapters for the selected engine | WP-05, WP-06, WP-07b | GATE-M2: Apple runtime subset | AC-08, AC-09, AC-26 |
| WP-10 NVIDIA service runtime adapter | M2 | ML + platform / L, reassessment pending | PRD-008, PRD-009, PRD-012 | Service lifecycle, model loading, streaming, resource release | WP-07b, WP-08 | GATE-M2: NVIDIA runtime subset | AC-08, AC-12, AC-21 |
| WP-11 Runtime forms and recipe loop | M2 | Frontend + backend / M, reassessment pending | PRD-009, PRD-012, PRD-016, PRD-020 | Apply settings, snapshots, reuse; consistent execution location / transmission scope, three presets, actual field differences | WP-04, WP-07b, WP-09, WP-10 | GATE-M2: forms, presets, and first-trial subset | AC-09, AC-16, AC-21, AC-25 |
| WP-12 Data checks and SFT + LoRA | M3 | ML + backend / L, reassessment pending | PRD-004, PRD-006, PRD-007 | Fixed supervision recipes, tokens / labels checks, real training, checkpoints, resumption | WP-05, WP-06, WP-07b, WP-08 | GATE-M3: data and training subset | AC-04, AC-06, AC-07, AC-26 |
| WP-13 AI suggestions and control isolation | M3 | Backend + frontend / M, reassessment pending | PRD-017 | Local / remote connections, structured suggestions, preview, apply, undo | WP-03, WP-04, WP-07b | GATE-M3: AI subset | AC-15 |
| WP-14 Evaluation and candidate registration | M3 | ML + backend / L, reassessment pending | PRD-014 | Fixed evaluation sets, reports, admission, provenance, and trial of the same training artifact on the target device | WP-09, WP-12 | GATE-M3: evaluation, candidate, and target-trial subset | AC-14, AC-26 |
| WP-15 Training-method extensions | M5 | ML / L per combination, reassessment pending | PRD-006, PRD-014 | Adapt version-selected combinations of QLoRA, full-parameter training, CPT, DPO, GRPO, and PPO | WP-12, WP-14 | GATE-M5: training-combination subset for this version | AC-06, AC-14 |
| WP-16 Cache and scheduling optimization | M2 baseline, M5 extensions | ML / L, reassessment pending | PRD-010 | KV / prefix / Prefill / Decode / graph capture; media-identity and preprocessing-invalidation negative cases | See WP-16a, WP-16b | GATE-M2, GATE-M5: validate by subitem | AC-10, AC-24 |
| WP-17 Speculative decoding | M5 | ML / L per strategy, reassessment pending | PRD-011 | Combination-level preparation, switch invalidation, submission rechecks, and comparisons for ordinary draft models, MTP, and DFlash | WP-07b, WP-14, WP-16a | GATE-M5: speculative-strategy subset for this version | AC-11, AC-24 |

<a id="4-媒体市场和专项"></a>

## 4. Media, Marketplace, and Specialized Work

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Phase validation | Final AC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WP-18 Image adaptation and optimization | M4 | ML + frontend / L, reassessment pending | PRD-006, PRD-008 | Image data, fine-tuning, generation, VAE / offloading, real images | WP-11, WP-12, WP-14 | GATE-M4: image-combination subset | AC-06, AC-08, AC-13 |
| WP-19 Video adaptation and timing | M4 | ML + frontend / L, reassessment pending | PRD-006, PRD-008 | Video decoding, slicing, training / generation, timing metadata | WP-05, WP-18 | GATE-M4: video-combination subset | AC-06, AC-08, AC-13 |
| WP-20 Audio task adaptation | M4 | ML + frontend / L per task, reassessment pending | PRD-006, PRD-008, PRD-016 | At least one voice-over TTS combination; ASR and others added by matrix, sampling / slicing and artifacts; WorkRevision separate from original transcription / generation recipes | WP-05, WP-11, WP-12 | GATE-M4: audio and result-revision subset | AC-06, AC-08, AC-13, AC-16 |
| WP-21 Workflows and material continuation | M4 | Backend + frontend / M, reassessment pending | PRD-015, PRD-016 | WorkflowRun identity, step attempts / input versions; atomic target-occupancy checks and advancement, explicit reuse of old results | WP-18, WP-19, WP-20 | GATE-M4: workflow and race subset | AC-16, AC-17, AC-20 |
| WP-22 Dataset marketplace connector | M4 | Backend + frontend / L, reassessment pending | PRD-005 | Source catalog, versions, access applications, downloads, return to original task | WP-05, WP-08 | GATE-M4: marketplace subset | AC-05 |
| WP-23 Model merging and distillation | M5 | ML / L per method, reassessment pending | PRD-013 | Input compatibility validation, teacher-output versions, independent artifacts, evaluation | WP-12, WP-14 | GATE-M5: selected merging / distillation subset | AC-19 |
| WP-24 Quantization, conversion, and ANE | M5 | ML + platform / L per format, reassessment pending | PRD-013, PRD-019 | Format artifacts, numerical comparisons, candidate default engines and bidirectional loading validation, Core ML / ANE evidence | WP-07b, WP-14, WP-18, WP-29a | GATE-M5: selected quantization / conversion subset | AC-13, AC-19, AC-27 |
| WP-25 Heretic / Abliterix comparisons | M5 | ML / L, reassessment pending | PRD-013 | Source-version checks, independent execution, ordinary-capability and target comparisons | WP-12, WP-14 | GATE-M5: behavior-comparison subset for this version | AC-19 |
| WP-26 AMD / Intel / CPU adaptation | M5 | ML + platform / L per combination, reassessment pending | PRD-012 | ROCm / HIP, SYCL, OpenVINO, CPU validation matrix | WP-07b, WP-08, WP-16a | GATE-M5: device-combination subset for this version | AC-12, AC-24 |
| WP-27 Disaggregated Prefill / Decode | M5, independently deferrable | Platform + ML / L, reassessment pending | PRD-010, PRD-012, PRD-018 | Two services, KV connector, failure recovery, performance evidence | WP-10, WP-16a | GATE-M5: selected disaggregated-deployment subset | AC-10, AC-21, AC-24 |

<a id="5-导出发布与稳定化"></a>

## 5. Export, Release, and Stabilization

| Work package | Phase | Responsible roles / size | Requirements | Deliverables | Dependencies | Phase validation | Final AC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WP-28 Backup, migration, and cleanup | M1 foundations, M6 acceptance | Backend + platform / L, reassessment pending | PRD-018, PRD-016 | Consistent backups, migration rollback, reference checks, recoverable cleanup | See WP-28a, WP-28b | GATE-M1, GATE-M6: validate by subitem | AC-18, AC-22 |
| WP-29 User artifact export, installation, and updates | M3 foundations, M4 media, M6 release | Backend + platform + frontend / L, reassessment pending | PRD-018, PRD-019 | Model / adapter / work / report exporters; installation, identity, signing, updates, diagnostic packages | See WP-29a, WP-29b, WP-29c | GATE-M3, GATE-M4, GATE-M6: validate by subitem | AC-22, AC-26, AC-27 |
| WP-30 Regression and user acceptance | M6; check assets maintained throughout phases | Testing + product / L, reassessment pending | PRD-001—PRD-020 | Real-device matrix, first-time user path, relationship negative tests, fixed audit assets, known limitations, release checklist | All target work packages for this version, excluding this work package | GATE-M6: final matrix and document-relationship checks | AC-01—AC-27 |

<a id="6-跨阶段子项与依赖"></a>

## 6. Cross-phase Subitems and Dependencies

The subitem rows below are authoritative for phase dependencies. A dependency on a parent work package requires that parent to be single-phase; references to cross-phase packages must name specific subitems. Expanding WP-30's “all targets” excludes itself, formally deferred items, and combinations outside this version's matrix; deferred scope is explicitly recorded in the release checklist.

| Subitem | Phase | Deliverables | Dependencies | Phase validation | Final AC |
| --- | --- | --- | --- | --- | --- |
| WP-07a | M1 | Capability schema, combination identity, interaction rejection, fake-executor contracts | WP-01, WP-03 | GATE-M1: capability-contract subset | AC-06, AC-08, AC-09, AC-11, AC-12, AC-13 |
| WP-07b | M2 | Initial real-engine mappings, parameter readback, submission validation | WP-07a | GATE-M2: real-capability subset | AC-06, AC-08, AC-09, AC-11, AC-12, AC-13 |
| WP-16a | M2 | Initial cache / scheduling baseline, media-cache identity contracts and negative cases | WP-09, WP-10 | GATE-M2: cache-baseline subset | AC-10, AC-24 |
| WP-16b | M5 | Extended scheduling, graph capture, and media-engine cache measurements for this version | WP-16a | GATE-M5: extended-cache subset | AC-10, AC-24 |
| WP-28a | M1 | Single-host consistent-backup foundations, transaction / reference checks, recovery-interface contracts | WP-03, WP-05, WP-06 | GATE-M1: backup-foundation subset | AC-18, AC-22 |
| WP-28b | M6 | Migration rollback, backup recovery, and recoverable cleanup for specific historical data | WP-28a | GATE-M6: recovery subset | AC-18, AC-22 |
| WP-29a | M3 | Model / adapter / text-work / report export, dependency manifests, digests, cancellation recovery, independent loading / opening | WP-05, WP-06, WP-14 | GATE-M3: basic artifact-export subset | AC-26, AC-27 |
| WP-29b | M4 | Image / video / audio works and revision exports, independent opening | WP-29a, WP-18, WP-19, WP-20 | GATE-M4: media-export subset | AC-27 |
| WP-29c | M6 | Candidate installer, signed updates, diagnostic packages, all export regressions after upgrading | WP-02, WP-08, WP-28b, WP-29a, WP-29b | GATE-M6: installation / update and export-regression subset | AC-22, AC-27 |

WP-29a does not depend on WP-28b or WP-29c and does not wait for complete installation / upgrade acceptance; WP-24 depends only on M3 export foundations. WP-27 depends only on inference and cache foundations; media workflows are not a technical prerequisite for disaggregated Prefill / Decode. Additional training methods in WP-15 are uniformly selected M5 scope; M3 commits only to initial SFT + LoRA, reducing unnecessary cross-scheduling.

<a id="7-重点工作包的可执行拆分"></a>

## 7. Executable Breakdown of Key Work Packages

<a id="wp-06状态控制与只补收"></a>

### WP-06: State Control and Collection-only Retries

1. Generate normal, failure, timeout, and race tests row by row from the state table in [07](07-api-and-task-lifecycle.md); pause-checkpoint failure, cancellation during pausing, crashes during cancelling, and cancellation during finalizing all have exits.
2. Pause / resume / cancel / force-stop use state versions and idempotency keys; repeated events are decided only once. Without stop evidence, retain `stop_status=unknown` rather than falsely reporting released resources.
3. Computation outcomes and collection records are independent. Collection retries reference the original attempt's artifact manifest; validation, transfer, and registration are all idempotent, must not invoke `run` / `resume`, and must not change the original RunAttempt terminal state.
4. In M1, use fake executors with real files / databases for contract fault tests. In M2 / M3, rerun the corresponding branches after real adapters are integrated.

<a id="wp-07能力与配置一致"></a>

### WP-07: Capability and Configuration Consistency

1. Define parameter types, units, default sources, allowed values, conflicts, restart requirements, and combination versions.
2. Bind models, base models / adapters, strategy components, engines, devices, formats, task modes, and input-media capabilities; preparation state belongs to an exact combination.
3. Recalculate validity when any dependency changes, showing fields that must be cleared / reset; cancellation does not change applied settings.
4. The frontend and submission side validate independently, covering bidirectional switching between ordinary draft models and DFlash, Omni audio to vision models, and forged submissions of Core ML formats to unsupported engines.
5. Read actual parameters back through adapters; default configuration may initialize new drafts only, and execution summaries and the location beside the button use the applied snapshot.

Completion condition: the interface, applied configuration, request snapshot, and actual backend values agree; unknown combinations cannot be prepared or executed. Passing M1 contracts does not mean every M5 strategy has real-device support.

<a id="wp-12监督目标与训练闭环"></a>

### WP-12: Supervision Targets and Training Loop

1. Parse real JSONL and fix the data version; split training / validation by source groups with a fixed seed.
2. Save tokenizer, processor, template, and supervision-recipe versions, fixing assistant-only / completion-only, EOS / PAD, truncation, and packing-boundary policies.
3. Check final tokens / labels for multi-turn, overlong, empty-answer, system-only, padding, concatenated, and multimodal inputs; count effective supervised tokens and truncation / exclusions. Reject zero-supervision samples from data splits; block the task if filtering leaves no effective supervision in training or a required validation split.
4. Map SFT + LoRA to a specified training-library version and record actual optimizer steps, loss, checkpoints, and failure events.
5. Validate cancellation, new attempts after failure, checkpoint resumption, and collection-only retries; load the independent adapter from a clean process, then complete the target-device trial.

Completion condition: target parameters actually update, original model / data digests remain unchanged, actual artifacts load, and the evidence chain is complete. Neither exit code 0 nor falling loss alone replaces these checks.

<a id="wp-17wp-24组合与产物适配"></a>

### WP-17, WP-24: Combination and Artifact Adaptation

Split speculative decoding into strategy subtasks for ordinary draft models, MTP, and DFlash. Fix target, components, template, thinking conditions, precision, and concurrency, and compare against a standard baseline. Switching invalidates mismatched preparation; recheck before and after preparation and at submission. Save acceptance rate, total latency, and quality; if there is no benefit, “not recommended by default” is an acceptable conclusion.

Quantization / conversion first validates input formats and shapes and establishes numerical comparisons. Conversion candidates select default engines from their actual formats and must not inherit inapplicable source configurations. Load independently from the candidate entry and block both incorrect format / engine directions. Save Core ML policy and actual allocation separately; without ANE evidence, only Core ML execution can be called passed.

<a id="wp-21每轮工作流和原子推进"></a>

### WP-21: Per-run Workflows and Atomic Advancement

Fix IDs for every WorkflowRun, step attempt, and input version. By default, accept only artifacts for the current run, step, and input; reusing old results requires an explicit action and provenance record. Changes to upstream input invalidate old downstream artifacts. Target-category entry checks, step advancement, output references, and target-draft writes share one deciding transaction; any failed check leaves everything unchanged.

Retest two complete rounds, zero generation in the second round, upstream changes, a target that is running / paused / just completed / just cancelled, and double-click advancement. Failure offers viewing the blocking task, waiting, or exiting; once unblocked, advancement occurs only once.

<a id="wp-29用户导出与发布分工"></a>

### WP-29: User Export and Release Responsibilities

The backend owns object-selection plans, dependency resolution, manifests, digests, partial files, and registration transactions. The frontend owns scope / size / dependency notices, save locations, progress, cancellation, and recovery. The platform owns target paths, permissions, and M6 installation / updates. When staffing is formally assigned, each item has one owner; collaborating roles do not replace ownership.

Models, adapters, works, and reports each have real examples. Adapters include fixed base-model dependencies and missing-dependency notices; base models without redistribution rights are not bundled by default. Media opens independently; reports reference models, data, rules, results, and versions; result revisions preserve original generation recipes. Missing files, disk-full conditions, cancellation, and validation failure must not produce falsely complete packages. Recovery handles export only and does not trigger model recomputation. Diagnostic packages and ordinary user artifact packages are different export types.

<a id="8-每张开发任务卡必须包含"></a>

## 8. Every Development Task Card Must Include

Goal, PRD / AUD / E relationships, input versions, implementation scope, dependency subitems, delivered files, phase-validation subset, final-AC tracking, error cases, automated tests, real-operation steps, performance / data boundaries, completion evidence, and reviewer.

Task states are not started, in progress, awaiting review, awaiting acceptance, complete, and blocked. Phase completion requires all agreed tests and real-device evidence for that phase; final ACs are signed separately after execution across the full applicable scope. Deferred features retain their requirements, combinations, and reasons rather than losing tracking IDs.

WP-30 maintains document-relationship checks and negative tests throughout the phases, consolidating user acceptance in M6. Check specific PRD → work package → AC row relationships, missing deliverable objects, summed reference durations, dependency subitems, and reversed phase dependencies. Audit assets have fixed manifests / digests / rerun commands and preserve historical sources; “successfully reproduced a known issue” is not a passed product test.

<a id="9-第一批可启动任务"></a>

## 9. First Tasks That Can Start

First converge the [remediation contracts in 16](16-audit-remediation-plan.md), then schedule WP-01 and WP-02 with independent exits under TV-01—TV-03. Schedule WP-03, WP-06, and WP-07a based on experiment results; WP-04 and WP-05 may overlap once contracts are stable. M0 does not need to wait for M3 exporters or M6 installation, upgrades, and complete hardware acceptance.

This round updates specifications and plans; it does not mean the product implementations above are complete. Execute each subsequent phase gate and retain evidence.
