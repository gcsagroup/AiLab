<!-- translation-navigation:start -->
[简体中文](../../../docs/14-prototype-traceability.md) · [繁體中文](../../zh-TW/docs/14-prototype-traceability.md) · [English](14-prototype-traceability.md)
<!-- translation-navigation:end -->

<a id="最终-demo-对照实现差距与证据"></a>

# Final Demo Mapping, Implementation Gaps, and Evidence

Version: 1.1 · Date: 2026-09-09 · Status: Documentation revised following the audit; prototype identity is unchanged, and identified demo issues have not yet been fixed.

Related documents: [Product requirements](01-product-requirements.md), [Task breakdown](10-work-breakdown.md), [Testing and acceptance](11-testing-and-acceptance.md).

<a id="1-基线身份"></a>

## 1. Baseline Identity

This document set is based on `ailab-unified.html`, which includes runtime parameters, optimizations, and multiple-hardware settings, not the earlier `ailab-next.html` or older prototypes.

| Item | Verified result |
| --- | --- |
| Prototype file | `/Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162/ailab-unified.html` |
| File size | 640,532 bytes |
| SHA-256 | `478e03fa98a66e3b6250d376c6e2b973f7e5f9c5d92aafeb86da8da7074b8aa4` |
| Verification date | 2026-09-09 |
| Project code status | No production application code was present in the project directory when documentation began |
| Prototype operation | HTML fragment and in-memory state; simulated execution without real model-service calls |
| Test results | 42 main-workflow groups + 17 runtime-optimization groups, rerun and passed |
| Negative-case evidence | 6 confirmed behavioral issues and 1 recipe-semantic observation; cannot count toward product passes |

The prototype resides in a separate directory on this machine. This round did not copy it into the project's source directory; readers on other machines must obtain the prototype and companion files separately rather than assuming the absolute path exists.

<a id="2-配套文件"></a>

## 2. Companion Files

All files below reside in the same directory as the prototype above.

| File | Purpose | Mapping focus |
| --- | --- | --- |
| `ailab-unified-state.js` | Prototype domain state | Model / data templates, tasks, snapshots, evaluations, AI suggestions |
| `ailab-unified-ui.js` | Main interface and interaction | Four entry categories, runs, marketplace, lab, materials, devices, AI |
| `ailab-runtime-state.js` | Runtime optimization state | Parameter defaults, device templates, engine options, conditional validation, application |
| `ailab-runtime-ui.js` | Runtime settings interface | Five language-parameter groups, media optimization, global hardware catalog |
| `ailab-unified-extra.css` | Integrated interface styles | Responsive behavior, runtime-configuration layout, dark / light modes |
| `build-ailab-unified.py` | Fragment build | Embeds scripts, styles, and example materials; validates size |
| `test-ailab-unified.cjs` | Main-workflow state tests | 42 representative validation groups |
| `test-ailab-runtime.cjs` | Runtime optimization tests | 17 representative validation groups |

Example images and audio are preview materials, not evidence of model-generation quality. When file identity changes, regenerate this page's digest and rerun affected checks.

<a id="3-产品功能逐项对照"></a>

## 3. Feature-by-feature Product Mapping

| Requirement | Prototype behavior | Production implementation gap | Corresponding document / work package |
| --- | --- | --- | --- |
| PRD-001 | Personal workspace, project switching, background attribution | Database persistence, restart recovery | 05 / WP-03 |
| PRD-002 | Four entry categories, in-category training / trials / history | Production components, direct trials and recent runs, keyboard and state recovery | 02 / WP-04 |
| PRD-003 | Model list, simulated download, import markers, run entry | Real files, revisions, validation, loading | 05 / WP-05 |
| PRD-004 | 14 schemas, examples, pasted JSONL, technical checks | Real file decoding, complete field checks, versions, splits | 05 / WP-05, WP-12 |
| PRD-005 | Marketplace filtering, access applications, demo provider handling, download, return | Actual connectors and provider states | 05 / WP-22 |
| PRD-006 | Method / update-method interactions, three-step configuration | Training adaptation, parameter types, device conditions | 03 / WP-07, WP-12, WP-15 |
| PRD-007 | Progress, pause / resume, cancel, simulated OOM, independent retries | Real processes, checkpoints, events, recovery, resource release | 07 / WP-06, WP-12 |
| PRD-008 | Text, image, video, audio, understanding trials | Real engines and media artifacts | 04 / WP-09, WP-10, WP-18—WP-20 |
| PRD-009 | Thinking, context, sampling, configuration drafts, recipes | Actual tokenization, template switches, parameter mapping and readback | 04 / WP-11 |
| PRD-010 | KV, prefix, Prefill, Decode, Attention, Graph, disaggregation configuration | Engine-version validation, actual hits, performance | 04 / WP-16, WP-27 |
| PRD-011 | Draft-model, MTP, DFlash configuration and some prerequisites | Native components, real pairing, acceptance rate, quality | 04 / WP-17 |
| PRD-012 | Apple, NVIDIA, AMD, Intel, CPU device templates | Hardware detection, drivers, formats, per-combination execution | 04 / WP-01, WP-08, WP-26 |
| PRD-013 | Five specialized entries and candidate workflows | Real implementation and independent evaluation for each | 03 / WP-23—WP-25 |
| PRD-014 | Preset baseline / candidates, manually selected evaluation scenarios, registration | Fixed evaluators, reports, backend admission | 03 / WP-14 |
| PRD-015 | Three-step media workflow, understanding workflow, FLUX dependencies | Workflow execution identity, atomic advancement, real artifact transfer, stale-input invalidation, reruns | 02 / WP-21 |
| PRD-016 | Save works, history, comparison, JSON recipes, reuse | File persistence, content digests, manual-edit versions separate from original recipes | 05 / WP-05, WP-11 |
| PRD-017 | Step-specific suggestions, allowlisted application, undo, refusal to judge for users | Real AI service, transmission scope, structured parsing | 08 / WP-13 |
| PRD-018 | In-session state, some background-task relationships | Crashes, disconnections, backups, migrations | 07 / WP-06, WP-28 |
| PRD-019 | Format selection, source recipes, runtime-artifact concepts | WP-29 owns ordinary artifact export; WP-24 owns format conversion and target adaptation; both require independent-use validation | 12 / WP-24, WP-29 |
| PRD-020 | Home entries, step explanations, error copy, settings shortcuts | Guidance for first real-environment preparation, help, usability testing | 02 / WP-04, WP-30 |

<a id="4-当前运行参数完整范围"></a>

## 4. Complete Current Runtime-parameter Scope

Language settings: thinking mode, context, maximum output, over-limit handling, temperature, Top P, Top K, Min P, repetition penalty, stop words, streaming. Random seed remains in the main run form.

Caching and scheduling: KV precision, token capacity / window, prefix cache, isolation scope, Prefill chunks, chunk scheduling, batch tokens, Decode concurrency, Attention, CUDA Graph, Prefill / Decode disaggregation and addresses.

Speculative decoding: off, ordinary draft model, MTP, DFlash; companion draft selection, simulated preparation, speculation length / block size, draft precision.

Hardware loading: device, hardware backend, engine, weight computation precision, memory limit, CPU threads, tensor parallelism, GPU offloaded layers, Core ML compute units.

Media settings: sampling scheduler, steps, CFG, VAE Tiling / Slicing, CPU offloading, compilation, frame count, frame rate, output sample rate, audio chunking, streamed audio, speaking rate.

These controls and their saving behavior are within prototype scope; they are not currently sent to a real model engine.

<a id="5-不得照搬的关键差距"></a>

## 5. Key Gaps That Must Not Be Copied

| Gap | Current prototype state | Production handling | Priority work package |
| --- | --- | --- | --- |
| GAP-01 In-memory state only | Refresh / new session resets state | Database, files, recovery contracts | WP-03, WP-06 |
| GAP-02 Simulated progress | Timer increases percentage | Executor reports real phases / unknown progress | WP-06 |
| GAP-03 Preset outputs | Images reuse one material, videos show illustrative changes, audio uses built-in examples | Actual inference and media decoding | WP-09, WP-18—WP-20 |
| GAP-04 Evaluation from demo choices | Pass / fail scenarios can be switched manually | Fixed evaluation sets, real reports, server-side admission | WP-14 |
| GAP-05 Simulated connections and draft preparation | Buttons set ready true | Separate detection, download, validation, loading, and pairing phases | WP-08, WP-17 |
| GAP-06 Static combination table | Brand / engine templates stand for capabilities | Dynamic decisions from hardware, drivers, models, versions | WP-07, WP-26 |
| GAP-07 Simplified training-device checks | QLoRA, for example, mainly restricts local paths without fully checking added devices | Independent training-method capability tables and server validation | WP-07, WP-15 |
| GAP-08 Static context and KV validation | Fixed prototype limits without real tokenization or caches | Tokenizer / processor budgets and engine mappings | WP-11, WP-16 |
| GAP-09 Some parameters only saved | Streaming, stop words, media optimization, etc. do not change model computation | Actual mappings and behavioral validation for every item | WP-11, WP-18—WP-20 |
| GAP-10 Independently settable video timing parameters | Duration, frames, and frame rate lack a real unified timeline | Pre-submission conversion, validation, artifact readback | WP-19 |
| GAP-11 Example-oriented data checks | Some missing / duplicate cases are injected scenarios | Complete checks on actual files and samples | WP-05, WP-12 |
| GAP-12 Coarse runtime-artifact restrictions | runtimeOnly simplifies training / conversion conditions | Operation chains defined by artifact formats and adapters | WP-07, WP-24 |
| GAP-13 Settings reconstruction lacks a formal difference contract | Engine changes rebuild optimization drafts and show notices | Field-level changes, restart requirements, final values | WP-11 |
| GAP-14 No actual metrics | Metric explanations exist without real tokens/s / GPU memory | Unmeasurable values remain unknown; adapters provide attributable metrics | WP-16, WP-30 |
| GAP-15 Simulated marketplace approval | Users can demonstrate provider approval / denial | Actual provider states; no user self-approval in production mode | WP-22 |

These are gaps between the prototype and real implementation, not reasons to modify the demo without a request in this round. This round only incorporates them into development and acceptance baselines.

<a id="51-审计补充的原型行为差距"></a>

### 5.1 Prototype Behavioral Gaps Added by the Audit

The following issues reproduce within the prototype itself and cannot be explained by “no real engine.” Current files are unchanged. Where specifications and demo behavior differ, the specifications are the future implementation target, with unresolved markers retained.

| ID | Current demo behavior | 1.1 specification requirement | Implementation status |
| --- | --- | --- | --- |
| AUD-01 | A new workflow round accepts previous results and advances without generation | Bind execution / step / input versions; explicitly reuse old results | Demo fix pending |
| AUD-02 | When the video category is busy, the step changes first while the page stays on image and writes the wrong draft | Atomic target checking and step advancement; no writes on failure | Demo fix pending |
| AUD-03 | Switching ordinary draft to DFlash retains incorrect components and preparation state | Strategy changes clear mismatched dependencies, with both application and submission validation | Demo fix pending |
| AUD-04 | After switching to a vision model, the hidden task mode remains audio | Validate model, mode, and materials together; explicitly reset invalid items | Demo fix pending |
| AUD-05 | A Core ML candidate can submit through the PyTorch path by default | Artifact format participates in defaults and bidirectional loading checks | Demo fix pending |
| AUD-06 | A cloud configuration for this attempt still displays the transmission location as local | All execution notices derive from the configuration applied for this attempt | Demo fix pending |
| E-04 | Subtitle edits write back into the result recipe while the original task snapshot is unchanged | Independent manual-edit versions; generation recipes and editing records displayed separately | Semantic revision awaiting implementation |

Other audit issues concern omitted document contracts or plans. This round rewrote the corresponding specifications and tracking; that does not prove the prototype fixed. See [16](16-audit-remediation-plan.md) for the complete mapping.

<a id="6-本次重新执行的原型测试"></a>

## 6. Prototype Tests Rerun This Round

Execution used the prototype directory in Section 1.

```sh
cd '/Users/lazy/.codex/visualizations/2026/09/07/01a07c7f-b284-7b41-9a2e-0f2282b08162'
node test-ailab-unified.cjs
node test-ailab-runtime.cjs
shasum -a 256 ailab-unified.html
```

Actual output summary:

```text
42 组代表性验证通过
脚本语法、片段结构与体积通过
17 组运行优化专项验证通过
478e03fa98a66e3b6250d376c6e2b973f7e5f9c5d92aafeb86da8da7074b8aa4  ailab-unified.html
```

Main-workflow tests cover training templates and candidates, data formats, AI apply / undo and unauthorized fields, execution snapshots, new attempts after failure, download states, five trial categories, and cross-project background attribution. Runtime tests cover default configuration, draft cancellation, context / numeric errors, MTP prerequisites, DFlash pairing, Core ML formats, AMD / Intel paths, hardware mismatches, CUDA budgets, blocked disaggregated deployment, snapshots, and recipe reuse.

These tests do not cover every UI event or cross-step combination. The independent `audit-prototype-counterexamples.cjs` reads the final HTML directly and currently reproduces the table's issues. Fixes should convert corresponding negative cases into regressions asserting correct behavior; passing the old 59 groups cannot close new issues. The old document checker and two document negative cases are evidence from the 1.0 point in time; current documents use the project's [document checker](../../../docs/tools/validate_docs.py) and [its tests](../../../docs/tools/test_validate_docs.py).

<a id="7-上一轮已观察的界面证据"></a>

## 7. Interface Evidence Observed in the Previous Round

During the previous prototype changes, actual clicks checked thinking-off / context conflicts, KV configuration application, missing-MTP-component notices, DFlash draft pairing and result recipes, CUDA scheduling, AMD / Intel selection, cancellation preserving old parameters, ANE format restrictions, and media optimization. Representative pages were checked at 1024 px, 736 px, and 360 px in dark and light layouts; the console had no warnings / errors.

The audit round further reproduced workflow reopening / blocking, DFlash switching, multimodal mode switching, and cloud-notice differences through actual operations; see the [audit report](audits/2026-09-09-demo-docs-audit.md). This round revised documentation only, without interface changes or a complete browser-flow rerun. There are no conclusions about real hardware acceleration, real training, or real video generation.

<a id="8-文档与后续开发的关系"></a>

## 8. Relationship between Documentation and Subsequent Development

This specification set builds on the final demo's interaction structure and supplies contracts, storage, and validation requirements essential to a real product but simplified in the prototype. The technology stack, schedule, and device combinations are recommendations; later implementation locks them in M0 and adjusts through actual experiments. Changes should first update specialized documents and this mapping table, preserving visibility of prototype / product differences.

The original 1.0 documents were archived according to the audited digests at `docs/archive/v1.0-2026-09-09`, with per-file SHA-256 values in the manifest. The prototype and old tests remain in their original locations; E-05's organization into a fixed team directory is planned and has not yet been executed.
