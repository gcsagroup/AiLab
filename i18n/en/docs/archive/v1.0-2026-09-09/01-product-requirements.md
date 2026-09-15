<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/01-product-requirements.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/01-product-requirements.md) · [English](01-product-requirements.md)
<!-- translation-navigation:end -->

<a id="产品需求规格"></a>

# Product Requirements Specification

Version: 1.0 · Date: 2026-09-09 · Status: product design and unimplemented requirements based on the final Demo.

Related documents: [Interaction flows](02-user-flows-and-ui.md), [Development roadmap](09-development-roadmap.md), [Prototype evidence](14-prototype-traceability.md).

<a id="1-产品定位"></a>

## 1. Product positioning

GCSA-AiLab is a local-first workbench for model training, post-training, and execution. Users organize models, data, execution environments, experiments, evaluations, and artifacts around a practical goal, completing a continuous task from preparation to trial use instead of moving files between unrelated tool pages.

The product covers language and multimodal models, image models, video models, and audio models. Training and generation are not two disconnected products: users can try existing models directly or obtain candidates through training and compare their results using the same inputs and recipes. The model library provides selection, preparation, and run entry points; the workbench handles the current task; the model lab handles specialized processing; works and materials support content reuse.

<a id="2-目标用户与关键任务"></a>

## 2. Target users and key tasks

| User | Current difficulty | Task this product must support | Observable successful outcome |
| --- | --- | --- | --- |
| Local model user | Parameters and backends are scattered, and the suitability of combinations is unclear | Select a model and device, adjust context, thinking, and caching, then run | Actual settings for this run are explainable; results retain inputs and recipes |
| Model fine-tuning developer | Data, training, evaluation, and adapter provenance are easily confused | Complete fine-tuning, evaluation, registration, and trial use with explicit data versions | Candidates can be traced to the source model, data, and execution environment |
| Multimedia creator | It is difficult to connect images, video, and sound | Generate images from materials, then generate shots and narration | Each step has an independent result and the workflow provenance chain is complete |
| Algorithm researcher | Experiments cannot be compared fairly, and failure records are easily lost | Compare distillation, merging, quantization, conversion, or behavior adjustment | Each candidate is executed and evaluated independently, and failures are reproducible |
| Owner-operated compute maintainer | Driver and engine capabilities across hardware environments are opaque | Manage local machines, servers, and cloud instances; check supported combinations | Connectivity, loadability, executability, and acceptance status can be distinguished |

<a id="21-核心用户故事"></a>

### 2.1 Core user stories

- As a fine-tuning developer, I want to select the task objective and data before confirming a combination such as SFT + LoRA, so that method names are not treated as mutually exclusive categories.
- As a local user, I want to see the parameters that actually take effect after disabling thinking and limiting context, rather than merely hiding thinking text in the interface.
- As a multimedia user, I want to pass a saved image directly into video generation and find the source image from the video result.
- As a researcher, I want original failed experiments to be retained and new attempts to have independent identifiers, so that a “successful retry” cannot overwrite them.
- As a device maintainer, I want the interface to explain what an optimization lacks instead of showing every option as available.
- As a data user, I want to record sources and permitted use myself; AI may organize materials but must not make authorization decisions for me.

<a id="3-产品目标与不纳入首期的范围"></a>

## 3. Product goals and scope excluded from the first phase

<a id="31-必须实现的目标"></a>

### 3.1 Required goals

1. Complete task flow: prepare → execute → check → save; training additionally supports evaluation → candidate registration → trial use.
2. Traceable recipes: record inputs, model versions, training or run parameters, data versions, environments, and results.
3. Local-first operation: prepared local models can still complete applicable local tasks without a remote service.
4. Explainable hardware support: device, engine, format, and version restrictions are visible, with capabilities shown according to verification records.
5. Human control: AI suggestions must be previewed first and only modify state after the user applies them; execution requires a separate user action.
6. Incremental integration: retain the four-category product structure while implementing genuinely deliverable model and device combinations in stages.

<a id="32-不纳入首个内测闭环"></a>

### 3.2 Excluded from the first internal test workflow

- Pretraining general-purpose large models from scratch and large-scale distributed training platforms.
- Autonomous experiment agents without human confirmation, automatic cloud instance purchasing, or automatic external publication.
- A self-operated data marketplace settlement, order payment, revenue-sharing, or contract-signing system.
- Complete organizational collaboration, fine-grained organizational permissions, or enterprise SSO.
- Promises that arbitrary combinations of all models, hardware, precisions, and acceleration methods can run.

These boundaries do not remove product entry points shown in the Demo. Real capabilities that are not implemented must clearly display “Pending integration” or “Pending verification” and offer a path for continuing the task.

<a id="4-功能需求总表"></a>

## 4. Functional requirements overview

Priorities: P0 is essential to the first real end-to-end workflow; P1 is important for expanded internal testing; P2 is a later controlled extension. Priority does not indicate current implementation status.

| ID | Function | Detailed requirements | Priority | Completion evidence |
| --- | --- | --- | --- | --- |
| PRD-001 | Workspaces and projects | Default personal workspace; tasks and results isolated by project; switching projects does not change background ownership | P0 | State restored after restart; cross-project cases pass |
| PRD-002 | Four workbenches | Fix the four entry points and training, running, and history structure within each category; each has an explicit return path | P0 | Entry points and task continuation actually work |
| PRD-003 | Model library | View format, version, origin, capabilities, and size; expose preparation, running, and training entry points according to status | P0 | Real file verification and loading succeed |
| PRD-004 | Dataset management | Import, checking, preview, splits, versions, and use-scope records; no overwriting of original data | P0 | Real data enters a reproducible task |
| PRD-005 | Dataset marketplace | Browsing and filtering, details, access requests, downloads, My Data, and return to the original task | P1 | Complete workflow through a connector or controlled test service |
| PRD-006 | Training configuration | Model, training type, update method, data, parameters, and device linked step by step | P0 | Verified combinations can be submitted; errors identify fields |
| PRD-007 | Training execution | Queue, logs, progress, checkpoints, cancellation, pause/resume where available, and independent retries | P0 | Real training-task lifecycle acceptance |
| PRD-008 | Running and trial use | Inputs, reference materials, model, generation, results, history, recipes, and comparisons form a continuous flow on one page | P0 | Real inference and artifact readback |
| PRD-009 | Runtime parameters | Verify that thinking, context, output, sampling, stop words, streaming, and other settings take effect | P0 | Adapter returns a summary of actual parameters |
| PRD-010 | Caching and scheduling optimization | KV, prefix caching, Prefill, Decode, Attention, and graph capture enabled according to capabilities | P1 | Correctness and comparative performance reports |
| PRD-011 | Speculative decoding | Independent support for ordinary draft models, MTP, and DFlash, with complete pair preparation and verification | P2 | Compatible target models and measured acceptance rates |
| PRD-012 | Devices and runtimes | Local machines, servers, and cloud; capability records for Apple, NVIDIA, AMD, Intel, and CPU | P0/P1 | Specific first-phase combinations meet criteria; others are labeled accurately |
| PRD-013 | Model lab | Behavior-adjustment comparisons, distillation, merging, quantization, and conversion, retaining independent candidates | P1/P2 | Each specialization accepted separately; no blanket support claim |
| PRD-014 | Evaluation and candidate registration | Fixed evaluation sets comparing baselines and candidates; failed candidates cannot become usable candidates | P0 | Reports, thresholds, provenance, and artifacts are consistent |
| PRD-015 | Workflows | Chain image, video, voiceover, or understanding tasks, passing results and recipes between steps | P1 | Acceptance of real results and dependency transfer |
| PRD-016 | Works and materials | Save, preview, view recipes, bring into new tasks, track ownership and reference counts | P0 | Files exist and provenance is traceable |
| PRD-017 | AI assistance | Step-specific suggestions, preview before manual application, and undo; no autonomous execution | P0 | Tests for stale suggestions, unauthorized fields, and execution isolation |
| PRD-018 | Persistence and recovery | Draft autosave, task reconstruction after disconnection, index recovery, and retention of failure records | P0 | Process termination and restart recovery tests |
| PRD-019 | Export and release preparation | Export models, adapters, works, and reports; check formats, dependencies, and target devices | P1 | Independent loading after export does not mean release is complete |
| PRD-020 | Guidance and discoverability | Explain model/data/device relationships on first use; provide routes from errors to corrections | P0 | Users complete core tasks without reading developer documentation |

<a id="5-通用业务规则"></a>

## 5. General business rules

<a id="51-对象归属"></a>

### 5.1 Object ownership

Projects contain tasks, recipes, evaluations, and references to works. Model files and public data files may be deduplicated in physical storage, but deduplication must not automatically expand project visibility, provenance declarations, or cache scope. Background task ownership is fixed at submission; results must not be assigned according to the project currently displayed when the task completes.

<a id="52-修改与执行分离"></a>

### 5.2 Separate editing from execution

Editing a form is not execution. The run-settings dialog first saves an edited draft; “Check and apply” only writes configuration to the current task, while “Start training” or “Send/Generate” submits execution. Configuration changes must not implicitly purchase resources, download new components, or replace a model that is running.

<a id="53-有效参数不能只停留在表单"></a>

### 5.3 Effective parameters must go beyond the form

The server validates and returns `effective_config` (the actual execution configuration). If the engine does not support a requested setting, it must reject the setting or explicitly ask the user to choose an alternative, never silently ignore it. Automatic engine values must be resolved or explicitly marked “Determined dynamically by the engine.”

<a id="54-失败是可保留结果"></a>

### 5.4 Failure is a retainable result

Failed tasks must retain inputs, configuration, environment, logs, error classifications, and the most recent usable checkpoint. A retry creates a new attempt linked to the original task by default; checkpoint recovery clearly shows the step from which it resumes. Failed candidates may be retained as research records, but must not enter the normal model library through “Register usable candidate.”

<a id="55-评测和发布分别决定"></a>

### 5.5 Evaluation and publication are separate decisions

Completed training only means execution has ended; passed evaluation only means the specified evaluation scope meets its criteria; candidate registration only means the candidate can proceed to trial use. Successful export, successful loading on the target device, and completed publication are three additional states, each requiring its own evidence.

<a id="6-非功能目标"></a>

## 6. Nonfunctional goals

The following are proposed acceptance targets, to be calibrated in M0 using reference devices and representative data; no actual performance measurements are currently available.

| Category | Target | Verification method |
| --- | --- | --- |
| Usability | First-time users can follow the interface from model preparation to their first result; errors identify a location and recovery entry point | 5 target users complete representative tasks; record blockers |
| Interaction response | p95 for routine local operations excluding model computation does not exceed 300 ms | Record interaction times on the reference machine; make long operations asynchronous |
| Initial visibility | Target cold start of the main window within 3 seconds in an installed environment with a normal data volume | 20 independent launches; exclude the initial model download |
| Data scale | First round covers an index of 10,000 tasks and 1,000,000 data metadata entries; lists are read in pages | Generate test data and check memory consumption and query times |
| Stability | Runner exit does not lose frontend drafts; duplicate submissions do not execute twice | Fault injection and idempotency tests |
| Traceability | Completed tasks must include a model version, data version or input digest, environment, recipe, and artifact manifest | Full structural validation |
| Accessibility | Key tasks can be completed by keyboard; labels, focus, and error associations are clear | Automated checks plus manual keyboard paths |
| Appearance adaptation | Light and dark themes; desktop 1024 px, medium 736 px, narrow 360 px; no horizontal overflow at a minimum of 320 px | Real browser/application checks |
| Offline capability | Local inference with prepared resources does not require a network connection; missing resources are explained clearly | Offline execution and cache-hit tests |
| Honest performance reporting | Do not display unmeasured tokens/s, VRAM usage, ANE usage, or speedup factors | Check metric provenance; show missing values as unmeasured |

<a id="7-成功指标与质量度量"></a>

## 7. Success metrics and quality measurement

Internal product testing first measures task completion: core-path completion rate, time to first result, task recovery success rate, number of error corrections, and recipe reuse success rate. Business evaluation then measures model quality and resource cost; download counts or training counts must not substitute for success rates.

Metrics must include sample counts, test conditions, and exclusions. For example, time to first result separately records environment preparation, downloading, model loading, Prefill, and Decode; training time separately records preprocessing, loading, optimization steps, checkpoint writing, and evaluation. Hardware must not be ranked directly using different inputs or quantization methods.

<a id="8-第一版真实闭环的放行定义"></a>

## 8. Release criteria for the first real end-to-end workflow

The first internal test version must complete the following on at least one specified Apple local inference combination and one specified NVIDIA training combination: real data import, real model loading, small-sample SFT + LoRA training, independent evaluation, candidate registration, candidate trial use, recipe saving, and recovery after application restart. Other categories and hardware retain their product structure, but their status must match the acceptance matrix.

For the staged goals covering the final Demo in full, see [09](09-development-roadmap.md); for specific cases, see [11](11-testing-and-acceptance.md).
