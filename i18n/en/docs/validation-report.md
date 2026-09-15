<!-- translation-navigation:start -->
[简体中文](../../../docs/validation-report.md) · [繁體中文](../../zh-TW/docs/validation-report.md) · [English](validation-report.md)
<!-- translation-navigation:end -->

<a id="文档与原型基线验证报告"></a>

# Documentation and prototype baseline validation report

Validation date: 2026-09-09 · Documentation version: 1.1 · Conclusion: audit recommendations are incorporated into specifications, work packages, and acceptance; documentation checks passed, while product implementation and Demo fixes remain to be executed.

<a id="1-验证范围"></a>

## 1. Validation scope

This round updated the Chinese specifications and development plan listed in the [documentation center](README.md), addressing the 14 issues and 5 enhancement proposals from the [historical audit](audits/2026-09-09-demo-docs-audit.md). Checks covered current document structure, direct requirement relationships, stage dependencies, example JSON, archive digests, and the final prototype's existing tests and known-issue counterexamples.

The original 17 Markdown files from 1.0 are retained unchanged in the [archive](archive/v1.0-2026-09-09/README.md), with per-file identities in the [archive manifest](../../../docs/archive/v1.0-2026-09-09/manifest.json). The historical audit and checker are retained. Their identifiers, counts, line numbers, and conclusions apply only to that baseline, not to 1.1 acceptance.

<a id="2-当前文档检查"></a>

## 2. Current documentation checks

| Check | Result and evidence boundary |
| --- | --- |
| Current documents | README, 16 specialist documents, and this report: 18 total. Archives and audits are separate; a fixed top-level file count is not a quality gate |
| Structure and references | One top-level heading, closed code fences, table column counts, local targets, and line-specific links all passed |
| JSON | 9 design examples parse successfully; they are not actual responses from the current API |
| Requirements and tasks | Direct coverage relationships passed for 20 PRD items, 30 top-level work packages, 9 stage subdeliverables, and 27 final AC items |
| Stages and dependencies | 3 M0 technical experiments and 6 subsequent stage gates; no dependency cycles or inverted stage dependencies; cross-stage packages reference specific subdeliverables |
| Remediation traceability | 14 AUD items and 5 enhancements have specifications, responsible packages, acceptance, and implementation state; document completion was not marked as product fixes |
| Export responsibility | Implementation packages explicitly cover models, adapters, works, and reports; M3 basics include text works, M4 media, M5 selected conversion formats, and M6 full regression after installation/upgrades |
| Schedule | Actual stage-table sums are compared with prose; 19—28 weeks is only historical 1.0 scope, and new 1.1 costs must be reassessed in M0 |
| Historical preservation | The 17 original 1.0 documents match archive-manifest digests; historical audit material was not rewritten |
| Official references | 18 sources are included. This round rechecked new vLLM media-cache, TRL supervision, and PyTorch model-loading references; others retain their original verification dates. This does not establish integration |

Automated checks reported no errors. The commands below produce actual link/table counts rather than treating fixed counts as coverage. The [16 traceability table](16-audit-remediation-plan.md) governs requirement, work-package, and acceptance definitions and relationships.

Run from the project root:

```sh
python3 docs/tools/validate_docs.py --check-archive --json
python3 docs/tools/test_validate_docs.py
```

The [checker](../../../docs/tools/validate_docs.py) and [representative tests](../../../docs/tools/test_validate_docs.py) use the Python standard library without depending on the formal application or models. Current rules check Markdown fences, tables, and recognizable links; they are not a complete Markdown renderer and cannot automatically determine whether every natural-language contract is sufficient.

<a id="3-文档工具的代表性测试"></a>

## 3. Representative documentation-tool tests

**All 21 tests passed.** A normal baseline and an additional valid document should pass; other counterexamples should be rejected with corresponding errors. All mutations occur in temporary copies, and original document digests are checked before and after.

- Retaining identifiers while changing WP-14 to an incorrect requirement/acceptance relationship must produce an error.
- Changing M1 duration while retaining the old total must produce an error; using a final AC as an M0 prerequisite must also fail.
- Missing remediation mappings, replacing ordinary exports with diagnostics, missing direct requirement coverage, and fabricated product-fix claims must fail.
- Cycles, references to nonexistent subdeliverables, early tasks depending on later tasks, and compound dependencies without a specific subdeliverable must fail.
- Broken links, out-of-range line references, malformed JSON, incorrect table columns, unclosed fences, and modified archives must fail.

This addresses original AUD-14 blind spots where identifiers existed but relationships were wrong, or duration changed while checks still passed. The tool reports rule consistency; formal changes still require human semantic review. Repeating the same mistake across several tables cannot replace product judgment.

<a id="4-合同与计划交叉复核"></a>

## 4. Cross-checking contracts and plans

The following cross-document relationships were reviewed, with implementation work packages and acceptance assigned to each revision objective:

- Workflow runs, steps, and input versions are bound; target occupancy and advancement are atomic; old results require explicit reuse.
- Changes invalidate dependent model, task mode, input media, artifact format, engine, and speculative-component combinations; displayed and submitted configuration share a source.
- Pause failure, cancellation while pausing, crashes during cancellation, and cancellation during collection have explicit handling; unknown state must not be falsely reported as stopped.
- Computation results, attempt terminal states, and independent collection records are separate; collection must not recompute, and original failure/cancellation facts and old evaluations remain.
- SFT tokenization/template/supervision scope, EOS/PAD, truncation, and packing versions are pinned; effective labels are a pre-training check.
- Model import identifies actual loading methods and trust categories; failure of restricted loading does not automatically fall back to executing unknown code.
- Manual work revisions retain independent versions; ordinary artifact export and diagnostic packages are implemented and accepted separately.
- M0 technical experiments do not depend on the M3 training product or M6 release; the same-LoRA cross-platform experiment, first-user workflow, and formal exports have independent acceptance.

Text checks passed for 7 critical exceptional transitions and 3 removed-edge counterexamples in state diagrams; 5 execution-control interfaces specify versioning and idempotency. The two Mermaid diagrams underwent only textual structure and contract review, not visual-rendering acceptance. These checks are not real-executor fault injection.

<a id="5-原型复测与未修问题"></a>

## 5. Prototype retests and unresolved issues

The two existing test suites were rerun in the final Demo's original directory:

```text
42 组代表性验证通过
脚本语法、片段结构与体积通过
17 组运行优化专项验证通过
```

A total of 59 prototype state/configuration test groups passed. The original audit counterexample script was also copied to a temporary directory and rerun against the same final HTML using an independent VM, a minimal DOM substitute, and manual timers. The 6 confirmed behavioral issues and 1 subtitle-recipe semantic observation remained reproducible. Temporary testing did not rewrite the prototype or historical audit JSON. A passing counterexample assertion means the issue still exists, not that it was fixed.

The prototype remains 640,532 bytes with unchanged SHA-256:

```text
478e03fa98a66e3b6250d376c6e2b973f7e5f9c5d92aafeb86da8da7074b8aa4
```

Original files, companion scripts, rerun commands, and issue mappings are in [14 Prototype evidence](14-prototype-traceability.md). Organizing the prototype and tests as team assets is assigned to E-05/WP-04/WP-30; this round did not move or delete those assets.

<a id="6-验证限制与交付结论"></a>

## 6. Validation limitations and delivery conclusion

This round did not modify UI or product code or operate the browser again. Real-page observations from historical audits retain their original dates and scope. No formal API service, database implementation, desktop installation package, real training/inference, device acceleration, or deployment was started.

The 1.1 documentation and development-plan revision is complete and can support review and bounded M0 technical experiments. Exact model/device combinations, responsible personnel, experiment results, and additional person-days remain recorded under [decisions and open questions](13-decisions-risks-and-questions.md). Product support, defect closure, and release must be established by the corresponding implementation and real-device acceptance.
