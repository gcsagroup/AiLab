<!-- translation-navigation:start -->
[简体中文](../../../../docs/audits/2026-09-09-demo-docs-audit.md) · [繁體中文](../../../zh-TW/docs/audits/2026-09-09-demo-docs-audit.md) · [English](2026-09-09-demo-docs-audit.md)
<!-- translation-navigation:end -->

<a id="最终-demo-与产品开发文档审计"></a>

# Audit of the Final Demo and Product Development Documentation

Date: 2026-09-09 · Scope: the final integrated demo and the 17 Chinese documents in version 1.0.

<a id="1-结论与处理范围"></a>

## 1. Conclusions and Scope of Handling

**The product structure can be retained, and the current documents support M0 technical experiments, but they are not yet suitable for freezing as formal development and acceptance contracts.** This round confirmed 14 issues: 6 demo behavioral errors, 5 technical-contract omissions, and 3 development / acceptance issues. Of these, 4 are P1 and 10 are P2; 5 enhancement suggestions are also proposed. No evidence justifies discarding the four workbench categories, model library, dataset marketplace, or model lab.

P1 identifies workflow-integrity or phase-release issues to fix first; P2 identifies issues to resolve before implementing the relevant module. These priorities serve this audit and are not vulnerability ratings for a real backend that does not exist.

This round adds only an audit report and independent reproduction scripts. It did not modify the original demo, original 17 documents, build scripts, or original tests; install models, drivers, or backends; or deploy services. The suggestions below have not been implemented and must not be read as “issues fixed.”

<a id="11-已有设计中应保留的部分"></a>

### 1.1 Parts of the Existing Design to Preserve

- Training / trials / history across the four categories revolve around the same category, with reasonably clear entry and return locations.
- Training types and parameter-update methods are modeled separately; runtime settings are edited, checked, and applied before user execution.
- Documents already distinguish the prototype, specifications awaiting implementation, proposals, combinations awaiting validation, and real-device evidence, without directly describing simulated success as product support.
- Foundational specifications already exist for project ownership, immutable execution snapshots, data versions, candidate evaluation, and user-controlled AI application.

<a id="12-基线身份"></a>

### 1.2 Baseline Identity

Final prototype: [ailab-unified.html](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-unified.html>).

```text
文件大小：640,532 字节
SHA-256：478e03fa98a66e3b6250d376c6e2b973f7e5f9c5d92aafeb86da8da7074b8aa4
```

Document baseline: [Documentation index](../README.md), [Prototype mapping](../14-prototype-traceability.md), [Previous validation report](../validation-report.md). The prototype and documents were checked again at the start of this audit rather than relying only on previous conclusions.

<a id="2-问题总表"></a>

## 2. Issue Summary

| ID | Priority | Issue | Evidence category | Suggested ownership |
| --- | --- | --- | --- | --- |
| AUD-01 | P1 | New workflow treats previous-round results as current completion | Browser operations, final-HTML counterexample | WP-21, AC-17 |
| AUD-02 | P1 | Workflow advances first and writes the wrong draft when the next category is busy | Browser operations, final-HTML counterexample | WP-21, AC-17 |
| AUD-03 | P2 | Incorrect pairing remains submittable after switching ordinary draft to DFlash | Browser operations, final-HTML counterexample | WP-07, WP-17, AC-11 |
| AUD-04 | P2 | Hidden multimodal task type is not invalidated after changing models | Browser operations, final-HTML counterexample | WP-04, WP-07, AC-06 / 08 |
| AUD-05 | P2 | Core ML conversion candidate defaults to the PyTorch runtime path | Final-HTML counterexample | WP-07, WP-24, AC-13 / 19 |
| AUD-06 | P2 | This attempt selects cloud, but the Send button still shows local | Browser operations, final-HTML counterexample | WP-11, AC-09 / 21 |
| AUD-07 | P1 | Pause / cancellation states lack failure and race exits | Document cross-check, state-diagram counterexample | WP-06, AC-07 / 20 |
| AUD-08 | P2 | Artifact collection failure lacks a collection-only, no-recomputation contract | Document cross-check | WP-06 / 08, AC-18 / 21 |
| AUD-09 | P2 | Minimum multimodal prefix-cache key omits media identity | Documents and official references | WP-16, AC-10 |
| AUD-10 | P2 | SFT does not define which tokens actually participate in training | Documents and official references | WP-12, AC-04 / 06 |
| AUD-11 | P2 | Model-import trust rules omit executable serialization formats | Documents and official references | WP-05 / 08, AC-03 / 21 |
| AUD-12 | P1 | M0 work packages bind acceptance that can only complete in M1 / M6 | Work-package / acceptance cross-check | WP-01 / 02, phase acceptance |
| AUD-13 | P2 | User artifact export has no explicit implementation work package | Requirements, interfaces, and plan cross-check | PRD-019, WP-24 / 29 |
| AUD-14 | P2 | Document checker cannot detect relationship and schedule semantic errors | Two in-memory counterexamples | Document validation, WP-30 |

<a id="3-demo-行为问题"></a>

## 3. Demo Behavioral Issues

<a id="aud-01同一工作流重新开始后旧结果可以直接推进"></a>

### AUD-01: Restarting the Same Workflow Allows Direct Advancement with Old Results

**Location:** [Final HTML line 323](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-unified.html:323>); companion `ailab-unified-ui.js` lines 20, 71, 72.

**Browser reproduction:** Load “Product image → Video → Voice-over” and generate perfume image GEN-41 in the first step. Exit and reload the workflow, change the prompt to “red teapot, plain white background,” and click “Use in next step” without generating a new image. The interface successfully enters step 2 while the reference image still says “From GEN-41.”

An independent counterexample further completed two rounds of the three-step workflow: the second round created 0 new generation tasks yet still saved a complete workflow, with output IDs identical to the first round. The workflow saves only a definition ID, without a current execution ID; empty result selection falls back to the first history item, and the next step checks only the model and workflow definition.

**Impact:** Users believe new inputs have taken effect while subsequent steps actually continue using the old image. Explicit reuse of old results could be a feature, but no such selection or provenance confirmation currently occurs.

**Minimum change:** Give workflow executions, step attempts, and input versions separate IDs; by default, the next step accepts artifacts from the current step of the current execution. Reusing old results requires an explicit action and record. Show the provenance state of old results after input changes.

**Acceptance:** Execute two complete rounds; the second round cannot directly succeed without generation; explicit reuse records provenance; changing the first step invalidates old downstream artifacts.

**Relationship to known gaps:** Document 14 already records “old-input invalidation / rerun” as pending, but does not specifically disclose that a new round can save with zero generation. This is new evidence, not a repeated report of preset-image GAP-03.

<a id="aud-02目标类别有任务时步骤推进不是完整事务"></a>

### AUD-02: Step Advancement Is Not a Complete Transaction When the Target Category Has a Task

**Location:** [Final HTML line 323](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-unified.html:323>); companion `ailab-unified-ui.js` lines 69, 72.

**Trigger:** Generate and pause a video task, then load the product workflow, complete its image, and click “Use in next step.” Code adds the output and increments the step first, then detects the existing video-category task while switching to the video page and rejects the switch. Subsequent code still modifies the current draft.

**Counterexample result:** The workflow is at step 2 while the current category remains image; the image draft's source is set to the ID of its own newly generated image. The interface warns that the category has a task but has already changed the step, leaving continued operation stuck in an inconsistent state.

**Minimum change:** Check whether the target category can be entered first, then commit the step, outputs, and new draft references together. Failure retains the original step and offers explicit actions to view the blocking task, wait, or exit.

**Acceptance:** Test four target-task conditions: running, paused, just completed, just cancelled. On failure, the step, output set, and source draft remain unchanged; after unblocking, one click advances only once.

<a id="aud-03切换推测策略时没有清除不兼容草稿"></a>

### AUD-03: Switching Speculation Strategies Does Not Clear an Incompatible Draft Model

**Location:** [Runtime-state logic line 18](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-runtime-state.js:18>) and line 21; corresponding final-HTML lines 229, 232.

**Browser reproduction:** Qwen3-4B → Cloud GPU / vLLM → Thinking off → Ordinary draft → Select and simulate preparing a draft model → Change only the strategy to DFlash. The interface still says “Demo component prepared” and allows applying, sending, and completing GEN-42.

The result recipe actually records:

```json
{"speculation":"dflash","draftModel":"qwen4-draft","draftReady":true}
```

The current DFlash option corresponds to `qwen4-dflash`. Whether preparation is real is not central here; the existing static pairing itself is inconsistent.

**Minimum change:** Clear mismatched draft models and preparation states on strategy changes. Both application and submission revalidate the target model, strategy, component ID, and engine. Preparation state should belong to an exact combination rather than an independent boolean switch.

**Acceptance:** Switch both ways between ordinary draft and DFlash, change models / engines before and after preparation, and submit stale configuration directly; block all mismatched combinations.

<a id="aud-04模型切换后界面显示与实际任务类型不同"></a>

### AUD-04: After Model Switching, the Interface and Actual Task Type Differ

**Location:** [Interface events line 89](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-unified-ui.js:89>), line 24, and `ailab-unified-state.js` line 35.

**Browser reproduction:** Prepare Qwen Omni and select audio understanding with an example material, then switch to Qwen2.5-VL-3B. The dropdown shows “Image question answering,” with no audio-understanding option left; sending directly nevertheless completes GEN-44 and displays “Transcription: Welcome to the audio workbench.”

The independent counterexample confirms that the submitted value remains `mode=audio` while the model is `qwen-vl`. The prototype's own model list declares only text, image, and video inputs for this model.

**Minimum change:** After model changes, revalidate task type, material type, and output mode. Explicitly reset invalid items and display the changes. Submission validation must not depend on currently visible dropdown options.

**Acceptance:** Switch from audio-capable to vision-only models and back; switch with reference videos, images, and recordings; interface selections and submission snapshots match field by field.

<a id="aud-05转换后的格式没有参与默认运行引擎选择"></a>

### AUD-05: Converted Format Does Not Participate in Default Runtime-engine Selection

**Location:** [Runtime defaults line 14](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-runtime-state.js:14>), and lines 15, 19.

**Counterexample:** Convert an image-fusion network to “Runtime model · Core ML FP16,” register it, and run the candidate directly. Defaults are `pytorch / metal`, validation reports no error, and the generation task is accepted.

The current check only prevents the Core ML engine from using non-Core-ML artifacts; it does not check whether other engines support converted artifacts in the reverse direction. This does not establish a real loading failure. It proves that the demo contract accepts a combination for which it has not established a valid loading path.

**Minimum change:** Include artifact format in default-engine selection and final loading-capability checks. Candidates inheriting source information must not inherit runtime configuration that no longer applies. If bridging is needed, list it as an independent preparation action.

**Acceptance:** Converted artifacts go through the complete selection chain from “Candidate → Run”; correct formats and engines pass, and both incorrect directions are blocked. Testing only “original weights cannot use ANE” is insufficient.

<a id="aud-06执行位置提示与已应用配置来自不同来源"></a>

### AUD-06: Execution-location Notice and Applied Configuration Use Different Sources

**Location:** [Trial form line 24](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-unified-ui.js:24>); final HTML line 275.

**Browser reproduction:** Keep the global local default, select Cloud GPU in per-run settings, and apply. The parameter summary shows vLLM / NVIDIA CUDA, while the Send button still says “Local Apple Silicon · Demo execution.” The result recipe has device `cloud` and environment name “Cloud GPU instance.”

**Impact:** The current demo misleads users about execution location; in a real product, this notice also identifies the data destination. There is no real service, so no data was sent externally this round.

**Minimum change:** This attempt's execution summary, button notice, transmission scope, and submission snapshot all read the applied configuration. Global defaults initialize new drafts only.

**Acceptance:** Local default / one cloud run, cloud default / one local run, and recipe reloads all show execution locations consistent with snapshots.

<a id="4-技术合同遗漏"></a>

## 4. Technical-contract Omissions

<a id="aud-07暂停和取消中途出现异常时没有闭合处理"></a>

### AUD-07: Exceptions during Pause and Cancellation Lack Complete Handling

**Location:** [07 Task state machine](../07-api-and-task-lifecycle.md) lines 129—144; control interfaces lines 44—47; cancellation explanation line 174.

In the state diagram, `pausing` can enter only `paused`, without exits for checkpoint-write failure or cancellation while pausing; `cancelling` has only the successful exit after executor stop confirmation. The prose mentions a force-termination entry without the corresponding command, result, and state contract.

Representative sequence checks of the state diagram confirm that `pausing→failed`, `pausing→cancelling`, and `cancelling→failed` are not expressed. Actual design may choose alternatives such as returning to running or retaining an unconfirmed state; the key is an explicit result for every event, not mechanically adding these three edges and calling it fixed.

**Minimum change:** Add a state-transition table and available actions covering pause failure, cancellation during pausing, crashes during cancelling, timeout force termination, and unknown stop outcomes. Unify version checks, idempotency, and error feedback for control commands.

**Acceptance:** Event-by-event table-driven checks plus cancellation / completion races, repeated controls, and retrieval after disconnection; no stopped display without executor evidence.

**Existing coverage:** Document 07 already defines safe points, cancellation confirmation, and separation of connection and run states; 11 already has general failure tests. The issue is incomplete exception branches within these rules, not “no recovery design at all.”

<a id="aud-08产物补收与计算重试混在一起"></a>

### AUD-08: Artifact Collection Recovery and Computation Retries Are Mixed

**Location:** [12 Operations](../12-operations-and-release.md) lines 57, 62; [07 Interfaces](../07-api-and-task-lifecycle.md) lines 47, 137—143, 178; [06 Adapters](../06-architecture-and-adapters.md) line 92.

The operations document permits “retry collection” after disk-full conditions, and executors already have `collect`. However, the state contract classifies collection / registration failure as an execution-failed terminal state, while the public retry action only creates a new computation-attempt draft. There is no action to transfer remaining files, validate, and register without computation.

**Impact:** When training is complete and remote files intact but only local writing failed, the team lacks an explicit implementation path to recover results without retraining.

**Minimum change:** Separate computation outcomes and collection states, or add an idempotent collection-retry operation referencing the original artifact manifest. Preserve original attempt records without disguising recovered collection as recomputation.

**Acceptance:** Disk full, interrupted transfer, and registration-transaction failure after computation completes; recovery does not increase computation calls, file digests match, and assets register once.

<a id="aud-09多模态前缀缓存缺媒体身份条件"></a>

### AUD-09: Multimodal Prefix Caching Lacks Media-identity Conditions

**Location:** [04 Cache specification](../04-runtime-and-hardware.md) line 69.

The minimum cache key lists model, adapter, tokenizer, template, token prefix, precision, and isolation scope, but omits media-content digests, processors, and preprocessing parameters. The same question with different images may have identical media placeholder tokens. vLLM specifically uses image hashes to distinguish this case. [Official explanation](https://docs.vllm.ai/en/latest/design/prefix_caching/)

**Minimum change:** Include media content or encoded results, media order, processor versions, and cropping / frame-extraction parameters in cache identity. If the underlying engine manages this, require the adapter to confirm these conditions rather than building a weaker application cache. Unknown combinations stay disabled.

**Acceptance:** The same text with different images / video / audio must not hit incorrectly; the same media with changed cropping, order, or processor version invalidates correctly.

**Boundary:** The project has no real cache implementation yet; this is a design omission affecting correctness. Document 04 already specifies media-token budgets and project isolation.

<a id="aud-10sft-数据通过结构检查不代表监督目标已确定"></a>

### AUD-10: Structural Validation of SFT Data Does Not Define the Supervision Target

**Location:** [03 Training parameters](../03-training-and-model-lab.md) line 53; [05 Data examples and checks](../05-data-model-and-assets.md) lines 65, 136, 160.

Documents save messages, templates, and tokenizer versions, but do not fix which tokens contribute to loss, EOS / PAD, truncation direction, sample concatenation, or boundary policies. Different adapters may train different targets from the same data; overlong samples may retain a question while discarding its answer.

TRL defines assistant-only, completion-only, and packing separately and places specific requirements on chat templates. [Official explanation](https://huggingface.co/docs/trl/sft_trainer)

**Minimum change:** Add versioned tokenization and supervision recipes. Usable training templates can fix policies without making every item a parameter ordinary users must fill in. Show effective supervised-token, truncation, and discarded-sample statistics.

**Acceptance:** Multi-turn conversations, overlong answers, empty answers, system-only messages, padding, concatenation boundaries, and multimodal samples; check final tokens and labels, and reject training samples with zero effective supervision.

<a id="aud-11模型格式的执行风险没有进入导入合同"></a>

### AUD-11: Model-format Execution Risks Are Missing from the Import Contract

**Location:** [06 Environment and trust boundaries](../06-architecture-and-adapters.md) lines 127, 131; [07 Model import plans](../07-api-and-task-lifecycle.md) line 25; [05 Model versions](../05-data-model-and-assets.md) line 160.

Documents already treat custom repository-code execution as a separate trust decision, but do not cover loading third-party pickle, TorchScript, or checkpoints. Correct hashes and no repository-script execution do not mean loading model files has no execution risk. PyTorch explicitly requires treating unknown TorchScript as executable code and distinguishes risks among serialization formats. [Official policy](https://github.com/pytorch/pytorch/security/policy)

**Minimum change:** Import plans record loading methods and trust classes. Ordinary weights use allowed formats and restricted loading, with no automatic fallback to arbitrary deserialization on failure. Formats requiring code execution receive separate decisions and restrictions on accessible files, networks, and credentials.

**Acceptance:** Restricted-loading failures, disguised formats, untrusted checkpoints, and models requiring custom code; validate rejection, explicit notices, and isolation. Dependency-environment isolation does not replace execution-permission isolation.

**Boundary:** This is a design-contract audit. No malicious model was executed, and no real code-execution vulnerability in the current application was demonstrated.

<a id="5-开发与验收问题"></a>

## 5. Development and Acceptance Issues

<a id="aud-12m0-技术试验绑定了后期产品验收"></a>

### AUD-12: M0 Technical Experiments Bind Later Product Acceptance

**Location:** [10 Work packages](../10-work-breakdown.md) lines 17—20, 59—61, 99; [11 Acceptance](../11-testing-and-acceptance.md) lines 48, 92, 132.

WP-02 belongs to M0 and delivers desktop-shell and sidecar experiments, yet requires AC-01 and AC-22. AC-01 includes restart recovery of database drafts / history across two projects, while main storage is not built until M1. AC-22 includes a candidate installer, upgrades, migration rollback, backup recovery, and export, whose work packages are in M6. WP-04 also depends on WP-02, and work-package completion requires all related tests.

**Impact:** Following the task cards gives M0 no independently decidable exit gate. Teams may prematurely check off final acceptance or be unable to advance while waiting for later work. WP-01's reference to complete hardware AC-12 also requires a phased interpretation.

**Minimum change:** Establish technical-experiment acceptance for M0, or explicitly split ACs into phase subitems, distinguishing “this phase's experiment passed” from “complete product acceptance passed.” Final acceptance remains consolidated in the corresponding delivery phase.

**Acceptance:** Each M0 work package completes using only that phase's deliverables; the dependency graph has no reversed phase dependencies, and acceptance subitems have explicit execution conditions.

<a id="aud-13普通产物导出没有明确负责人和交付物"></a>

### AUD-13: Ordinary Artifact Export Lacks an Explicit Owner and Deliverables

**Location:** [01 PRD-019](../01-product-requirements.md) line 77; [07 Export preparation interface](../07-api-and-task-lifecycle.md) line 52; [12 Export packages](../12-operations-and-release.md) line 90; [14 Mapping](../14-prototype-traceability.md) line 62; [10 Work packages](../10-work-breakdown.md) lines 50, 60.

Requirements call for model, adapter, work, and report exports, and the mapping points to WP-24 / 29. However, the former delivers conversion and ANE, and the latter installation, updates, and diagnostic export; neither explicitly owns the user artifact exporter. Diagnostic packages cannot replace users' model and work exports.

**Minimum change:** Specify the owner, phase, and exporter scope within existing work packages: object selection, dependency resolution, manifests, packaging to disk, integrity, failure recovery, and independent-environment use. There is no need to create another large module merely for an ID.

**Acceptance:** Examples exist for all four export categories; adapters include base-model dependencies; media opens independently; evaluation reports are traceable; missing files or cancellation do not produce falsely complete packages.

<a id="aud-14自动检查证明的范围比需求一致性窄"></a>

### AUD-14: Automated Checks Prove Less than Requirement Consistency

**Location:** [Document checker line 56](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/validate-ailab-docs.py:56>) through line 69; [11 Test layers](../11-testing-and-acceptance.md) line 11; [Original validation report](../validation-report.md) line 18.

The checker validates ID sets, keywords, links, JSON, and other structure. It sums phase durations using hardcoded constants rather than extracting actual schedules. It does not validate semantic PRD → work package → AC correspondence.

Neither of two independent in-memory negative tests was detected:

1. Changing WP-14's PRD-014 / AC-14 to PRD-010 / AC-22 still passed.
2. Changing M1 from 2—3 weeks to 20—30 weeks while retaining the old total still passed.

Original files were unchanged. This does not negate the previous round's separate manual review, but demonstrates that automated checks cannot prove semantic consistency.

**Minimum change:** Validation reports explicitly separate structural checking from manual content audit; add parseable relationship matrices, phase figures, dependencies, and negative tests. Relationship checks must do more than detect whether an ID appears somewhere in the document.

**Acceptance:** Requirement mismatches, AC mismatches, missing deliverable objects, inconsistent durations, and reversed dependencies are located to specific lines; the normal baseline continues to pass.

<a id="6-建议增强的五个方向"></a>

## 6. Five Suggested Enhancement Directions

These suggestions are not included in the confirmed-defect count. Select them according to cost and product goals rather than expanding the initial scope indefinitely.

| Suggestion | Problem addressed | Minimum implementation | Verifiable result |
| --- | --- | --- | --- |
| E-01 Complete first-use path and continuation entries | Home favors training; first runs and recent generation tasks are insufficiently direct, and existing ACs do not fully cover zero resources to a first result | Preserve the four entries, add direct trials / continue last run within categories, and define a separate first-time user case | 5 target users prepare models, check devices, and obtain first results from clean environments without reading development documents; record blockers and durations |
| E-02 Common runtime presets and configuration differences | Many parameters already exist, and ordinary users struggle to decide what to change | Provide a few verifiable templates—“Model defaults,” “Low memory,” “Low latency”—while retaining complete advanced settings; show actual field changes before application | Cancellation leaves values unchanged; device changes explain invalidated values and reload needs; no fabricated performance benefits |
| E-03 Bring forward validation of returning training artifacts to the target device | NVIDIA training and Apple trials may break across artifact formats, modules, and engines | In M0, validate a specified trial path using the same actual LoRA artifact; explicitly state conversion steps if needed | Base revision, adapter, template, target engine, and trial results form one evidence chain |
| E-04 Separate edited results from generation recipes | Subtitle edits write into result recipes, while dialogs still call them fixed-at-submission settings | Preserve original output; subtitle corrections become result versions or post-processing records, with generation parameters and edits displayed separately | Original transcription and revision differences are viewable; rerunning generation does not implicitly reuse manual corrections; task snapshots remain immutable |
| E-05 Turn the audit baseline into rerunnable team assets | Demo, sources, and tests reside in a personal session directory, and document links depend on local absolute paths | After a project-organization decision, place confirmed prototypes and checkers at fixed project locations with manifests and digests | A new member obtains the demo, tests, and documents from the same version and reruns with an explicit command; preserve old assets without deleting under the guise of migration |

E-04 already observed `result.recipe.transcript` changing with subtitle edits while `job.snapshot` remained unchanged. The issue to clarify is recipe semantics and display, not a claim that “execution snapshots can be tampered with.”

<a id="7-建议修订顺序与完成门槛"></a>

## 7. Recommended Revision Order and Completion Gates

| Order | Specific action | Completion gate |
| --- | --- | --- |
| 1 | Fix AUD-01 / 02 workflow execution identity and failed switching; fix AUD-06 execution location | Browser regressions pass for reopening, input changes, busy targets, unblocking, and local / remote switching |
| 2 | Fix AUD-03 / 04 / 05 strategy, mode, and format interactions | From real entries, interface, applied configuration, and submission snapshots agree; incorrect combinations cannot submit |
| 3 | Fix AUD-07 / 08 / 12 / 13 and freeze state, collection-retry, phase, and export ownership | Every action has success / failure / race outcomes; every phase can be accepted independently; export has an owner and real examples |
| 4 | Add AUD-09 / 10 / 11 cache, supervision, and import rules | Corresponding schemas, negative cases, and adapter acceptance are explicit; underlying defaults are not treated as shared cross-engine specifications |
| 5 | Fix AUD-14 and select E-01—E-05 for implementation | Add semantic negative tests to original structural checks and revalidate complete task paths after revision |

Adding more runtime switches is not recommended as a substitute for these revisions. Existing settings need consistent meaning, dependencies, provenance, and final behavior. Bounded M0 technical experiments may continue before these gates complete, but formal contract freezing and a conclusion of “development readiness complete” should wait.

<a id="8-本轮实际验证与证据边界"></a>

## 8. Actual Validation and Evidence Boundaries This Round

<a id="81-验证结果"></a>

### 8.1 Validation Results

| Check | This round's result | Proven scope |
| --- | --- | --- |
| Original main-workflow tests | 42 groups passed | Simulated states and validation covered by original tests |
| Original runtime-optimization tests | 17 groups passed | Runtime-configuration conditions covered by original tests |
| Original document checker | 17 documents, 71 links, 8 JSON examples, 20 PRDs, 30 WPs, 24 ACs, 5 checker samples passed | Structure, ID existence, established baseline; does not prove semantic completeness |
| New final-HTML counterexamples | Reproduced 6 behavioral errors and 1 recipe-semantic observation | Direct execution of final inline scripts using minimal DOM substitutes and manually advanced timers |
| Document semantic negative tests | Original checker still allowed 2 errors | Demonstrates current blind spots; original files unchanged |
| Representative state-diagram sequences | 3 categories of exceptional events have no specified diagram exit | Document-contract omissions, not backend fault injection |
| Actual browser interaction | Checked workflow reopening / blocking, DFlash strategy switching, model-mode switching, device notices, and other items individually | User-visible behavior of the current demo |
| Layout and keyboard spot checks | Representative pages at 1024 dark, 736 light, 360 dark / light; Escape successfully discards drafts | Observed pages have no overall horizontal overflow; does not establish complete accessibility acceptance |

**Passing assertions in the new counterexample scripts means “successfully reproduced the issue” and cannot be added to product acceptance pass counts.**

Browser spot checks measured root-container / content widths of 992 / 992, 704 / 704, and 328 / 328 pixels respectively. No new blocking overflow was found in the representative layouts. Narrow-screen checks are not a commitment to a separate mobile product.

<a id="82-独立证据文件"></a>

### 8.2 Independent Evidence Files

- [Final-HTML counterexample script](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/audit-prototype-counterexamples.cjs>), [Result JSON](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/audit-prototype-counterexamples.json>).
- [Document semantic counterexample script](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/audit-docs-counterexamples.py>), [Result JSON and original-file digests](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/audit-docs-counterexamples.json>).
- [State-contract counterexample script](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/audit-lifecycle-counterexamples.py>), [Result JSON](</Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/audit-lifecycle-counterexamples.json>).

```sh
cd '/Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162'
node test-ailab-unified.cjs
node test-ailab-runtime.cjs
python3 validate-ailab-docs.py
node audit-prototype-counterexamples.cjs
python3 audit-docs-counterexamples.py
python3 audit-lifecycle-counterexamples.py
```

Rerunning the last three commands writes only their respective audit-result JSON files, without changing the baseline. The original document checker requires exactly 17 top-level Markdown files, so this report is in `docs/audits` and outside the old validation scope. Its links, structure, and JSON examples are checked separately.

<a id="83-不在本轮证明范围内"></a>

### 8.3 Outside This Round's Proven Scope

No real training / inference engines ran; ANE, CUDA, ROCm, and oneAPI performance or device capabilities were not actually validated. Real remote authorization, data uploads, malicious model-file payloads, installer signing, and production recovery were not tested. Previously disclosed prototype timers, preset outputs, session memory, and simulated approval remain original GAPs and are not counted again as new issues.

The report's final status is: **Audit complete, issues awaiting revision; retain the existing product structure, first complete consistency and acceptance loops, then expand real adaptation scope.**
