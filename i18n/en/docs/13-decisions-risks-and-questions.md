<!-- translation-navigation:start -->
[简体中文](../../../docs/13-decisions-risks-and-questions.md) · [繁體中文](../../zh-TW/docs/13-decisions-risks-and-questions.md) · [English](13-decisions-risks-and-questions.md)
<!-- translation-navigation:end -->

<a id="技术决策风险与待定事项"></a>

# Technical Decisions, Risks, and Open Questions

Version: 1.1 · Date: 2026-09-09 · Status: Audit conclusions converted into design decisions and implementation gates; unfinished implementations are not marked fixed.

Related documents: [Product requirements](01-product-requirements.md), [Architecture](06-architecture-and-adapters.md), [Roadmap](09-development-roadmap.md).

<a id="1-已固定的产品决定"></a>

## 1. Fixed Product Decisions

| Decision | Basis | Subsequent constraints |
| --- | --- | --- |
| Four workbench categories | Final demo: language and multimodal, image, video, audio | Do not add an overlapping top-level creation area |
| Training / running / results within categories | User requested merging two versions while preserving a continuous workflow | Training candidates can directly enter corresponding trials |
| Preserve model library, dataset marketplace, and lab | Final integration scope | Do not remove entries merely to build the minimum loop first |
| Separate SFT and LoRA layers | Training type and parameter-update method distinguished | Model data and backend constraints separately |
| Complete runtime settings | Last prototype added thinking, context, KV, scheduling, speculation, and hardware | Do not regress to a few unexplained switches |
| AI suggestion mode | User explicitly prohibited intervention and judgments made on their behalf | Application, execution, admission, and publishing are separate user decisions |
| Reuse AI Beauty capabilities | User wants training / runtime / quantization / conversion capabilities extracted | Do not create a business entry for “connect the AI Beauty project” |
| Save documentation in Chinese Markdown | Explicit requirement for this round | Chinese body text and explanations; necessary technical identifiers retain their original form |

<a id="2-建议技术决策记录"></a>

## 2. Proposed Architecture Decision Records

<a id="adr-001采用模块化控制服务与独立执行器"></a>

### ADR-001: Modular Control Service with Independent Executors

Status: recommended, to be validated in M0.

Reason: the product needs reliable task, version, and result relationships, while engines have widely differing dependencies. A control service maintains shared contracts and independent executors perform computation, preventing one model-environment crash from taking down the whole application.

Alternatives: doing everything in the frontend is unsuitable for real training; starting with many microservices increases deployment cost. Use a monolithic domain service first and split it later only when real scale requires it.

Validation: submit a minimum task from the interface through artifact persistence; after terminating the executor, the control service still responds and recovers state.

<a id="adr-002建议-reacttypescript--tauri--python"></a>

### ADR-002: Recommend React / TypeScript + Tauri + Python

Status: candidate technology stack; versions not yet locked.

Reason: reuses Web interface capabilities and stays close to the Python model ecosystem. Risks include cross-platform packaging, sidecars, and native-dependency size, requiring M0 validation. If the desktop shell becomes a blocker, a local Web host can first validate business contracts; this does not change the production product's desktop goal.

<a id="adr-003sqlite-元数据与文件资产分离"></a>

### ADR-003: Separate SQLite Metadata from File Assets

Status: recommended.

Reason: local single-user task indexes suit a transactional metadata database, while large models and media suit file storage. The risk is consistency between transactions and file commits, addressed through temporary writes, digest validation, atomic registration, and recovery scans.

<a id="adr-004能力声明驱动配置"></a>

### ADR-004: Capability-declaration-driven Configuration

Status: product requirement with a proposed technical structure.

Reason: runtime parameters depend jointly on models, engines, hardware, and versions. Frontend controls and backend validation share schemas, but the backend must revalidate. The risk is a capability table becoming static marketing material; source records, detection results, and real-device reports are required.

<a id="adr-005先实现已配置远程资源"></a>

### ADR-005: Implement Already-configured Remote Resources First

Status: recommended.

Reason: the initial focus is the runtime and training loop, without also building cloud purchasing and billing. Cloud-instance creation, budgets, and destruction are later independent capabilities; initially integrate only users' existing servers or instances.

<a id="adr-006ai-无执行权限"></a>

### ADR-006: AI Has No Execution Permission

Status: fixed product boundary.

Reason: users require real-time suggestions without intervention. Applying suggestions is a restricted configuration change that accepts no arbitrary commands; execution and external actions use separate user entries. Natural-language tool calls could bypass the boundary, so server allowlists and contract tests must prevent this.

<a id="adr-007实验产物采用不可变版本"></a>

### ADR-007: Immutable Versions for Experiment Artifacts

Status: recommended, consistent with traceability goals.

Reason: retries after failure, quantization, conversion, and merging all create new experiment branches. Overwriting the same path damages evidence chains. Increased disk usage is handled through content deduplication, references, and explicit cleanup rather than overwriting old artifacts.

<a id="adr-008工作流执行身份与步骤推进原子化"></a>

### ADR-008: Workflow Execution Identity and Atomic Step Advancement

Status: included in the specification, implementation pending; addresses AUD-01, AUD-02.

Workflow definitions may be reused, but every execution and step attempt must have an independent ID and bind an input version. Check target availability before entering the next step, then save state atomically. Old-result reuse is explicit. One domain transaction is sufficient; do not introduce a separate distributed workflow platform in the initial phase.

<a id="adr-009不可变计算尝试与可补收产物分开"></a>

### ADR-009: Separate Immutable Computation Attempts from Recoverable Artifact Collection

Status: included in the specification, implementation pending; addresses AUD-07, AUD-08.

Controls such as pause / cancel are decided from executor evidence and state versions; unknown stop outcomes cannot masquerade as success. Original execution-attempt terminal states are not rewritten. Artifact collection recovery uses separate records to transfer, validate, and register existing files only, without retraining. Documents 05 and 07 govern specific fields and exceptions.

<a id="adr-010阶段验证和最终产品验收分开"></a>

### ADR-010: Separate Phase Validation from Final Product Acceptance

Status: included in the plan; addresses AUD-12.

M0 uses TV-01—TV-03 for combination, sidecar, and minimum LoRA return-path experiments; M1—M6 use explicit phase gates. Work-package final-AC columns track ownership; only the subset required for phase acceptance affects phase completion, and M0 must not depend on an M6 installer. After M0 passes, models, devices, staffing, and versions still need to be locked; the complete product cannot immediately be declared deliverable.

<a id="adr-011监督配方加载信任和缓存身份显式化"></a>

### ADR-011: Explicit Supervision Recipes, Loading Trust, and Cache Identity

Status: included in the specification, adapter validation pending; addresses AUD-09—AUD-11.

SFT fixes tokenization and loss-computation policies; media participates in cache identity; model import plans record specific formats, loading methods, and trust classes. These rules belong to adapter contracts. Ordinary users can use explained templates without filling in every underlying field.

<a id="adr-012常用预设和首次路径采用小范围增强"></a>

### ADR-012: Limited Enhancements for Common Presets and the First-use Path

Status: included in the plan; addresses E-01—E-05.

Preserve the four-category structure and add direct trials and recent runs. Common presets are limited to model defaults, low memory, and low latency, with effects requiring validation. Move the actual LoRA return-path experiment into M0; separate result revisions from generation recipes. WP-04 schedules placement of prototypes and tests in fixed team directories; migration first checks manifests and digests and preserves old assets. This round archives documents only and does not move or delete the prototype.

<a id="3-风险登记"></a>

## 3. Risk Register

| Risk | Impact | Early signal | Mitigation | Responsibility / phase |
| --- | --- | --- | --- | --- |
| Too many combinations | Uncontrolled schedules, false interface support | More new switches than real reports | Track by model × engine × device and limit phase targets | Product + ML / throughout |
| Upstream interface changes | Training / inference failures | Same configuration behaves differently after upgrades | Lock versions, adapt contracts, preserve old environments | ML / M0—M6 |
| Dependency conflicts | Unstable installation and execution | Upgrading one environment breaks another | Independent environments and digests, no arbitrary global dependencies | Platform / M1—M2 |
| Media workflows become form only | Users cannot obtain real artifacts | Only preset images / audio or file metadata | Real decoding, real generation, independent playback, quality acceptance | ML + testing / M4 |
| Simulated states enter production | False completion and benchmarks | Connection means success, timers mean completion | Isolate demonstrations and prohibit simulated-success functions in production paths | Backend + testing / M1—M6 |
| Data or version overwrites | Untraceable results | Old tasks reference changing files | Immutable versions, digests, transactions, references | Backend / M1 |
| Checkpoints cannot actually resume | Long-task loss | Only weights saved while “continue training” is displayed | Declare resumption scope and save optimizer and random state | ML / M3 |
| Optimization improves speed without quality guarantees | Model degradation | Only tokens/s reported | Compare quality, memory, acceptance rate, total latency together | ML + testing / M5 |
| ANE / NPU use overstated | Misleading compatibility claims | Selecting a backend displays hardware as used | Distinguish allowed compute units from actual execution evidence | Platform / M5 |
| Remote disconnection causes duplicate execution | Duplicate resource consumption | Timeout immediately causes resubmission | Idempotency keys, persistent remote state, query before retry | Backend / M2 |
| AI overwrites user settings | Violates control boundaries | Fields change without clicking Apply | Suggestion drafts, old-value checks, atomic application | AI + testing / M3 |
| Large files exhaust disk space | Unusable application, corrupted artifacts | Caches and works share space without quotas | Space prechecks, categorized usage, recoverable cleanup | Platform / M1—M6 |
| Unclear research-method sources | Cannot adapt or publish | Method names without fixed project versions | Check code, dependencies, inputs, and license materials individually | ML / M5 |
| Old selections affect new tasks | Visible controls differ from submitted content | Old values remain effective after strategy, model, or format changes | Downstream invalidation, difference previews, server-side bidirectional validation; atomic workflow advancement | Frontend + backend / M1—M5 |
| Uncertain supervision targets | Same data trains different targets | Only JSON checked, no effective-label statistics | Versioned supervision recipes, overlong and empty-supervision negative cases | ML / M3 |
| Collection recovery becomes recomputation | Repeated compute expense | Failed file transfer requires retraining | Independent collection, same-source manifest, computation-count acceptance | Backend + platform / M1—M3 |
| Checker reports false consistency | Complete IDs but omitted work | Mismatched relationships and durations still pass | Direct requirement-coverage matrix, actual-number and dependency checks, semantic negative cases | Testing + product / from this round |

<a id="4-待定事项与建议默认"></a>

## 4. Open Questions and Recommended Defaults

These questions do not block completion of this document set. Start later M0 experiments using the recommended defaults; owners decide commitments involving resources, release dates, or product scope.

| ID | Open question | Recommended default | Latest decision point | Decision impact |
| --- | --- | --- | --- | --- |
| Q-01 | Initial operating systems | macOS desktop + Linux NVIDIA executor | M0 | Packaging, device pool, test scope |
| Q-02 | Desktop host | Use Tauri if its experiment passes; retain local Web validation | M0 | Release size, signing, sidecars |
| Q-03 | Exact initial model version | Choose a manageable-size Qwen text model and lock its revision | M0 | Parameters, training, evaluation samples |
| Q-04 | Team and device budget | Estimate with the resource assumptions in 09, without automatic purchasing | M0 | Timeline and parallel capacity |
| Q-05 | Real dataset marketplace source | First integrate one public catalog and a controlled access-test service | Before M4 | Connector and access workflows |
| Q-06 | Reuse scope for custom image networks | First review reusable runtime / training / conversion modules and dependencies | Before M4 | Code reuse and adaptation cost |
| Q-07 | Specific Heretic / Abliterix upstream projects | Check project addresses, versions, method inputs, and outputs individually | Before M5 | Whether an executable adaptation foundation exists |
| Q-08 | First MTP / DFlash pairing | Use combinations explicitly supported upstream at the time and within device capacity | Before M5 | Model downloads, GPU memory, performance conditions |
| Q-09 | Marketplace payments / transactions | No payments in the first release; retain acquisition and access management | Before expanding commercial features | Orders, settlement, external systems |
| Q-10 | Which model repositories to publish to | Support local export first; define external publishing separately | Before M6 | Credentials, materials, interfaces, user actions |
| Q-11 | Organization collaboration | Single-user first release with multiple-project isolation | Later-version planning | Permissions, service deployment, data synchronization |
| Q-12 | First usable cross-device LoRA path | TV-03 uses the same actual artifact and explicitly records required conversions; no default cross-engine compatibility | M0 | Bridging needs, M3 trial path, workload |
| Q-13 | Initial runtime-preset parameters | Measure the initial fixed combination before enabling low-memory / low-latency templates | M2 | Template defaults and difference notices; complete-settings entry remains |
| Q-14 | Scheduling added audit work | Reassess in M0 from actual experiments using the revised estimates and phase scope in 09 | End of M0 | Resources, calendar duration, frozen target matrix |

<a id="5-不应继续沿用的原型简化"></a>

## 5. Prototype Simplifications That Must Not Continue

Fixed progress bars, preset model outputs, a single image material, simulated access approval, connection buttons directly setting ready, manually chosen evaluation passes, all fields in one untyped object, static hardware-vendor templates, and the same sampler for arbitrary models.

These simplifications suit interface demonstrations, not production execution. See [14](14-prototype-traceability.md) for specific gaps and work packages. When a gap is found, prioritize execution semantics rather than expanding the information architecture again.

<a id="6-决策维护"></a>

## 6. Decision Maintenance

New decisions record the problem, options, recommendation rationale, experiment results, conclusion, owner, and date. Superseded decisions retain history and reasons. Product-requirement changes update related work packages and acceptance; upstream-version upgrades alone update environments, capabilities, and affected tests without changing product scope by default.

See [16 Audit remediation and requirement tracking](16-audit-remediation-plan.md) for this round's issue handling. Completed documentation cannot close implementation risks; implementation status becomes complete only when corresponding code or workflow changes, regression evidence, and acceptance records are all present. Historical basis remains in the [1.0 archive](archive/v1.0-2026-09-09/README.md) and audit report.
