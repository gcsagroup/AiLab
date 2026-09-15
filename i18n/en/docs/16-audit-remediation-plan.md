<!-- translation-navigation:start -->
[简体中文](../../../docs/16-audit-remediation-plan.md) · [繁體中文](../../zh-TW/docs/16-audit-remediation-plan.md) · [English](16-audit-remediation-plan.md)
<!-- translation-navigation:end -->

<a id="审计整改需求追踪与完成门槛"></a>

# Audit Remediation, Requirement Tracking, and Completion Gates

Version: 1.1 · Date: 2026-09-09 · Status: 14 issues and 5 enhancements have entered documentation and planning; product implementation and demo-fix status are recorded separately.

Related documents: [Product requirements](01-product-requirements.md), [Work packages](10-work-breakdown.md), [Testing and acceptance](11-testing-and-acceptance.md), [Historical audit](audits/2026-09-09-demo-docs-audit.md).

<a id="1-本次修订的范围和状态"></a>

## 1. Scope and Status of This Revision

This round turns audit suggestions into executable specifications: workflow execution and input versions, configuration interactions, stop exceptions, artifact collection recovery, media-cache identity, SFT supervision, model trust, ordinary artifact export, and relationships between phase validation and final acceptance. Product structure and human control over AI remain.

The original 17 documents from 1.0 are preserved unchanged in the [archive directory](archive/v1.0-2026-09-09/README.md), with per-file digests in the [manifest](../../../docs/archive/v1.0-2026-09-09/manifest.json). Line numbers and conclusions in the historical audit refer to archived versions. Current same-name documents are revised 1.1 versions; updated line numbers cannot be used to infer old evidence.

This round does not modify the demo, models, or device configuration, or start product-backend development. Document remediation, document tools, and product implementation are accepted separately; “handled in documentation” does not mean prototype defects disappeared. See [14](14-prototype-traceability.md) for current prototype identity and unfixed behavior.

<a id="2-需求到工作包和最终验收的追踪"></a>

## 2. Requirements to Work Packages and Final Acceptance

Implementation work packages in this table follow direct responsibilities defined in 10, excluding WP-30's global acceptance consolidation. Final acceptance follows the direct “Covers PRD” relationships of individual ACs in 11, without automatically copying every AC of a multi-requirement work package onto each requirement. Changes on either side require checking the other side.

| Requirement | Implementation work packages | Final acceptance |
| --- | --- | --- |
| PRD-001 | WP-03 | AC-01 |
| PRD-002 | WP-04 | AC-02, AC-23, AC-25 |
| PRD-003 | WP-05, WP-08 | AC-03 |
| PRD-004 | WP-05, WP-12 | AC-04 |
| PRD-005 | WP-22 | AC-05 |
| PRD-006 | WP-01, WP-07, WP-12, WP-15, WP-18, WP-19, WP-20 | AC-06, AC-26 |
| PRD-007 | WP-06, WP-12 | AC-07, AC-20 |
| PRD-008 | WP-01, WP-07, WP-09, WP-10, WP-18, WP-19, WP-20 | AC-08, AC-13, AC-26 |
| PRD-009 | WP-07, WP-09, WP-10, WP-11 | AC-09 |
| PRD-010 | WP-16, WP-27 | AC-10, AC-24 |
| PRD-011 | WP-07, WP-17 | AC-11, AC-24 |
| PRD-012 | WP-01, WP-07, WP-08, WP-10, WP-11, WP-26, WP-27 | AC-12, AC-13, AC-21, AC-24, AC-26 |
| PRD-013 | WP-23, WP-24, WP-25 | AC-13, AC-19 |
| PRD-014 | WP-01, WP-14, WP-15 | AC-14, AC-26 |
| PRD-015 | WP-21 | AC-17, AC-20 |
| PRD-016 | WP-05, WP-11, WP-20, WP-21, WP-28 | AC-16 |
| PRD-017 | WP-13 | AC-15 |
| PRD-018 | WP-02, WP-03, WP-06, WP-08, WP-27, WP-28, WP-29 | AC-01, AC-18, AC-20, AC-21, AC-22 |
| PRD-019 | WP-24, WP-29 | AC-22, AC-26, AC-27 |
| PRD-020 | WP-04, WP-11 | AC-02, AC-23, AC-25 |

<a id="3-审计问题处理表"></a>

## 3. Audit Issue Handling Table

Final ACs below provide complete tracking; phase validation still follows each work package's TVs and phase gates, without requiring early tasks to complete all later ACs. See Section 5 and 09 for specific priorities and effort boundaries.

| ID | Specification location | Requirements | Implementation work packages | Final acceptance | Document handling | Implementation status |
| --- | --- | --- | --- | --- | --- | --- |
| AUD-01 | [02 Workflows](02-user-flows-and-ui.md), [05 Identity](05-data-model-and-assets.md), [07 Advancement](07-api-and-task-lifecycle.md) | PRD-015 | WP-21 | AC-17 | Added current-run execution, step, input-version, and explicit-reuse rules | Demo fix pending; product implementation pending |
| AUD-02 | [02 Blocked interaction](02-user-flows-and-ui.md), [07 Atomic advancement](07-api-and-task-lifecycle.md) | PRD-015 | WP-21 | AC-17 | Added target-occupancy checks, unchanged-on-failure rules, and idempotent advancement | Demo fix pending; product implementation pending |
| AUD-03 | [04 Pairing](04-runtime-and-hardware.md), [02 Difference preview](02-user-flows-and-ui.md) | PRD-011 | WP-07, WP-17 | AC-11 | Requires invalidation of mismatched components and preparation state when strategies switch | Demo fix pending; product implementation pending |
| AUD-04 | [02 Model switching](02-user-flows-and-ui.md), [04 Capabilities](04-runtime-and-hardware.md) | PRD-002, PRD-006, PRD-008 | WP-04, WP-07 | AC-02, AC-06, AC-08 | Added mode, material, and model interactions, with submission-side revalidation | Demo fix pending; product implementation pending |
| AUD-05 | [04 Formats and engines](04-runtime-and-hardware.md), [06 Capabilities](06-architecture-and-adapters.md) | PRD-008, PRD-012, PRD-013 | WP-07, WP-24 | AC-08, AC-12, AC-13, AC-19 | Added artifact formats to default-engine selection and bidirectional loading checks | Demo fix pending; product implementation pending |
| AUD-06 | [02 This attempt's execution summary](02-user-flows-and-ui.md), [04 Effective configuration](04-runtime-and-hardware.md) | PRD-009, PRD-012 | WP-08, WP-11 | AC-09, AC-21 | Unified data sources for devices, location, transmission scope, and snapshots | Demo fix pending; product implementation pending |
| AUD-07 | [07 Control state machine](07-api-and-task-lifecycle.md), [12 Failure handling](12-operations-and-release.md) | PRD-007, PRD-018 | WP-06 | AC-07, AC-20 | Added pause failure, cancellation during pausing, force-stop, unknown-state, and race contracts | Implementation and real-device acceptance pending |
| AUD-08 | [05 Collection objects](05-data-model-and-assets.md), [07 Collection-retry interface](07-api-and-task-lifecycle.md), [12 Recovery](12-operations-and-release.md) | PRD-007, PRD-018 | WP-06, WP-08 | AC-18, AC-21 | Requires independent collection-retry records, unchanged original terminal states, and no recomputation during collection recovery | Implementation and real-device acceptance pending |
| AUD-09 | [04 Media-cache keys](04-runtime-and-hardware.md) | PRD-010 | WP-16 | AC-10, AC-24 | Includes media identity, order, processors, preprocessing parameters | Implementation and real-device acceptance pending |
| AUD-10 | [03 Supervision recipes](03-training-and-model-lab.md), [05 Data checks](05-data-model-and-assets.md) | PRD-004, PRD-006 | WP-12 | AC-04, AC-06 | Requires supervision masks, EOS/PAD, truncation, packing, effective-label statistics | Implementation and real-device acceptance pending |
| AUD-11 | [05 Import plans](05-data-model-and-assets.md), [06 Loading trust](06-architecture-and-adapters.md) | PRD-003 | WP-05, WP-08 | AC-03, AC-21 | Requires format detection, loading methods, trust classes, and no unsafe fallback | Implementation and real-device acceptance pending |
| AUD-12 | [09 M0](09-development-roadmap.md), [10 Phase subitems](10-work-breakdown.md), [11 TV](11-testing-and-acceptance.md) | PRD-012, PRD-018 | WP-01, WP-02 | AC-12, AC-22 | Separated TV-01—TV-03, phase gates, and final ACs; revised phase dependencies | Plan revised; delivery awaits execution |
| AUD-13 | [10 WP-29](10-work-breakdown.md), [12 Export](12-operations-and-release.md), [11 AC-27](11-testing-and-acceptance.md) | PRD-019 | WP-29 | AC-27 | Clarified ordinary artifact-export ownership, phased delivery, and independent-use acceptance | Plan revised; delivery awaits execution |
| AUD-14 | [11 Document evidence](11-testing-and-acceptance.md), [Document checker](../../../docs/tools/validate_docs.py), [Negative-case tests](../../../docs/tools/test_validate_docs.py) | PRD-020 | WP-30 | AC-23, AC-25 | Updated structure, relationship, duration, and phase checks; see the report for validation records | Document tools updated; product acceptance awaits execution |

<a id="4-增强建议的决定与限定范围"></a>

## 4. Enhancement Decisions and Limited Scope

All five are adopted as development targets within limited scope: no new top-level feature area, no promises of unverified optimization benefits, and no automatic deployment or prototype migration / cleanup. Document archiving and future prototype-asset organization are recorded separately.

| ID | Decision | Specification location | Implementation work packages | Final acceptance | Implementation status |
| --- | --- | --- | --- | --- | --- |
| E-01 | Adopt: direct trials, recent runs, first-use path in a clean environment | [01 Target users](01-product-requirements.md), [02 Guidance](02-user-flows-and-ui.md), [11 First-use acceptance](11-testing-and-acceptance.md) | WP-04, WP-11, WP-30 | AC-02, AC-23, AC-25 | Included in the plan; implementation and target-user acceptance pending |
| E-02 | Adopt: three verifiable presets—model defaults, low memory, low latency—while retaining complete settings | [02 Difference preview](02-user-flows-and-ui.md), [04 Runtime configuration](04-runtime-and-hardware.md) | WP-11 | AC-09, AC-16 | Included in M2; parameters and benefits await specified-combination validation |
| E-03 | Adopt: M0 technical return path and M3 production return path for the same LoRA | [03 Artifacts](03-training-and-model-lab.md), [09 TV-03](09-development-roadmap.md), [11 AC-26](11-testing-and-acceptance.md) | WP-01, WP-09, WP-12, WP-14, WP-29 | AC-26, AC-27 | Included in the plan; actual-artifact and device acceptance pending |
| E-04 | Adopt: save manual revisions such as subtitles as independent work versions, preserving generation recipes | [05 Work versions](05-data-model-and-assets.md), [02 Comparison](02-user-flows-and-ui.md), [12 Export](12-operations-and-release.md) | WP-05, WP-11, WP-20, WP-29 | AC-16, AC-27 | Specification supplemented; implementation pending |
| E-05 | Adopt: confirmed prototype / test manifests at a fixed team location, preserving old assets during migration | [10 WP-04](10-work-breakdown.md), [14 Baseline](14-prototype-traceability.md) | WP-04, WP-30 | AC-23, AC-25 | Documentation 1.0 archived; prototype and test organization awaits execution |

<a id="5-实施顺序和关闭条件"></a>

## 5. Implementation Order and Closure Conditions

| Order | Work to perform | What a pass permits | What still cannot be claimed |
| --- | --- | --- | --- |
| This document revision | Specialized contracts, phase dependencies, responsibilities, direct requirement tracking; positive and negative document-tool cases | Bounded technical experiments using the 1.1 specification | Demo issues fixed or product development complete |
| M0 | TV-01 combinations, TV-02 shell sidecar, TV-03 same-LoRA return path; reassess added effort | Lock initial combinations and next-phase task cards | M3 training product or M6 release acceptance passed |
| M1—M2 | Workflow-object foundations, state / collection-retry contracts, model trust, parameter interactions, consistent execution location | Real inference and recovery acceptance for specified combinations | Unintegrated media or speculative strategies supported |
| M3 | Supervision recipes, checkpoints, candidate return path, model / adapter / text-work / report exports | A limited-scope private Alpha | Every method and device can train |
| M4—M5 | Atomic workflow advancement, media editing / export, conversion and speculation combinations | Enable validated extensions individually | Visible controls alone count as hardware or optimization acceptance |
| M6 | Same-candidate-package complete workflows, first-time users, upgrades / recovery, final ACs | Release preparation within frozen scope | Unexecuted external publishing complete |

P1 workflow and state rules enter contracts and regression design first; specific UI fixes follow their corresponding product work packages, with known issues retained until then. Fixing demo timers does not require a temporary backend maintained in parallel with the production product.

Closing an implementation item requires a specific modified version, relevant model / data / environment identities, expected-behavior regressions, representative negative cases, artifact or log evidence, owner, and acceptance date. Documentation-only items may close their documentation status after relationship checks and content review; items requiring execution evidence remain awaiting implementation / testing.

<a id="6-文档维护与验证"></a>

## 6. Document Maintenance and Validation

The definitions and tracking tables in this document set govern 20 requirements, 30 top-level work packages, 27 final ACs, 3 M0 technical experiments, 14 issues, and 5 enhancements. Top-level document count is not a quality gate; historical archives and audit materials are outside current requirement-ID constraints.

Document checks cover links, tables, code blocks, JSON, IDs and ranges, direct coverage relationships, actual phase figures, dependencies, and remediation states; human judgment is still needed on implementability and test sufficiency. Negative cases deliberately damage mappings, durations, phases, and links to verify clear tool errors without changing current documents.

See the [validation report](validation-report.md) for this round's results. Later changes to artifact formats, model versions, phases, or responsibilities should update specialized documents, 10, 11, this page, and affected tests together. Preserve the original audit as historical evidence; assertions that originally passed by showing “the issue exists” are not passes for fix acceptance.
