<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/README.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/README.md) · [English](README.md)
<!-- translation-navigation:end -->

<a id="gcsa-ailab-文档中心"></a>

# GCSA-AiLab Documentation Center

Version: 1.0 · Written: 2026-09-09 · Requirements baseline: the final integrated Demo, including runtime optimization and multi-hardware configuration.

<a id="1-文档用途与当前结论"></a>

## 1. Purpose and current conclusion

These documents turn the confirmed product prototype into a development baseline that can be implemented, assigned, and accepted. They cover product scope, interaction flows, training and inference, hardware adaptation, data and assets, architecture, interfaces, AI assistance, development scheduling, testing, and release.

**The current delivery is complete design and planning documentation, not an implemented client or model service.** At writing time the project directory contained no application code; the final Demo was stored in a separate prototype directory. The prototype’s 42 main-flow test groups and 17 runtime-optimization test groups were rerun and passed during this writing. They establish that demonstration states and some input validation work, not completion of real training, inference, downloads, hardware detection, or acceleration gains.

The following states must remain distinct in subsequent reviews and development:

| State | Meaning | May it be presented externally as supported? |
| --- | --- | --- |
| Demonstrated in prototype | The Demo has a corresponding page, configuration, or simulated flow | Only as a prototype feature |
| Specification awaiting implementation | Explicitly required here, but not implemented in the real application | No |
| Proposed technical approach | A development technology or structure proposal, subject to technical validation | No |
| Combination awaiting verification | Upstream capabilities exist, but this project has not verified the full combination | No |
| Real-device acceptance passed | Evidence identifies the exact device, model, version, parameters, and report | Only within the report's scope |

<a id="2-阅读顺序"></a>

## 2. Reading order

| Document | Content | Main readers |
| --- | --- | --- |
| [01 Product requirements](01-product-requirements.md) | Positioning, users, scope, feature identifiers, nonfunctional targets | Product, design, all developers |
| [02 User flows and interaction](02-user-flows-and-ui.md) | Information architecture, full task paths, page behavior, exceptions, return paths | Product, design, frontend, testing |
| [03 Training and model laboratory](03-training-and-model-lab.md) | Training types, update methods, parameters, experiments, evaluations, candidates | Algorithms, training backend, testing |
| [04 Runtime parameters and hardware](04-runtime-and-hardware.md) | Thinking, context, KV, Prefill, Decode, MTP, DFlash, hardware | Inference backend, platform, frontend |
| [05 Data model and asset management](05-data-model-and-assets.md) | Data formats, versions, market, models, works, recipes, storage | Data, backend, algorithms |
| [06 Architecture and adapters](06-architecture-and-adapters.md) | Client, control service, executors, environment isolation, capability declarations | Architecture, backend, platform |
| [07 Interfaces and task lifecycle](07-api-and-task-lifecycle.md) | Interface drafts, submission contracts, events, state machines, recovery, idempotency | Frontend/backend, executors, testing |
| [08 AI assistance and data boundaries](08-ai-assistance-and-data-boundaries.md) | Suggestions, preview, application, undo, external services, user control | Product, AI, backend, testing |
| [09 Development roadmap and milestones](09-development-roadmap.md) | Stage scope, team assumptions, dependencies, effort, exit criteria | Project lead, all developers |
| [10 Work breakdown](10-work-breakdown.md) | Work packages, responsible roles, deliverables, dependencies, test mapping | Project lead, developers |
| [11 Testing and acceptance](11-testing-and-acceptance.md) | Test layers, real tasks, matrices, performance, release gates | Testing, development, product |
| [12 Operations and release](12-operations-and-release.md) | Installation, environments, logs, recovery, upgrades, release, rollback | Platform, release, support |
| [13 Decisions, risks, and open questions](13-decisions-risks-and-questions.md) | Fixed directions, proposed choices, risks, decision deadlines | Product lead, technical lead |
| [14 Prototype mapping and evidence](14-prototype-traceability.md) | Prototype-file identity, feature mapping, 59 test groups, known gaps | Review, testing, all developers |
| [15 Sources and glossary](15-sources-and-glossary.md) | Official references, verification dates, Chinese explanations | All members |
| [Documentation validation report](validation-report.md) | Document, link, example, and prototype-test results for this round | Delivery acceptance reviewers |

For product review, read 01, 02, and 14 first; for development startup, read 06, 07, 09, and 10 first; when implementing a module, read its corresponding specialist document and 11.

<a id="3-产品不变的骨架"></a>

## 3. Stable product structure

1. The workbench organizes tasks into four model categories: language and multimodal, images, video, and audio.
2. Each category provides training/fine-tuning, execution/trial, and tasks/results, preserving a path to continue within that category.
3. Model library, workflows, dataset market, model laboratory, works/materials, and device/environment areas remain.
4. Training type and parameter-update method are expressed separately, for example SFT + LoRA.
5. Runtime configuration must reflect the capabilities of the model, engine, device, and version combination.
6. AI only suggests; the user decides modifications, execution, registration, and external actions.
7. Provenance records, provider access controls, and user declarations are stored separately. AI does not adjudicate data authorization or legality.

<a id="4-文档之间如何保持一致"></a>

## 4. Keeping documents consistent

- Feature-requirement identifiers use `PRD-xxx`, defined in 01; work packages use `WP-xx`, defined in 10; acceptance cases use `AC-xx`, defined in 11.
- 04 governs runtime-parameter semantics; 03 governs training; 05 governs objects and versions; 07 governs task state.
- When real product behavior differs from the Demo, record the gap in 14 and assign a corrective work package in 10. Do not copy simplified Demo implementations directly into product specifications.
- Stages are consistently M0—M6, with definitions governed by 09. Estimates are plans under resource assumptions, not committed release dates.
- Before adding a top-level entry point or changing AI-action boundaries, update product requirements and interaction, then implementation tasks.
- Model names, engine versions, precision support, and performance conclusions change. Update them through capability records and measurements rather than relying on a fixed “supported” checkmark in a document.

<a id="5-范围说明"></a>

## 5. Scope statement

This round saved only Markdown documents in `docs`; it did not start formal product development, install models or drivers, or deploy services. The technology stack, schedule, compatibility verification, and team allocation are proposed development baselines; the confirmed Demo information architecture and operation boundaries are product inputs.
