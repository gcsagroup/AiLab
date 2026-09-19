<a id="gcsa-ailab-文档中心"></a>

# GCSA-AiLab Documentation Center

[简体中文](../../../docs/README.md) · [繁體中文](../../zh-TW/docs/README.md) · [English](README.md)

The same company-signed 039 candidate completed controlled empty-library native migration rollback, healthy legacy-backup restoration, and reopening. Healthy A retained 8 resources; the repaired library passed migration 1→2→3→4 and test-project reopening. All 51 migration/backup tests passed, with no model runs. Cold-start offline restoration, failed upgrade with business data, and full AC-22/M6 remain pending. [Migration recovery acceptance](implementation/2026-09-20-ver2-4-039-migration-recovery.md)

The same company-signed 039 candidate reopened the original 12-export library and added 1 export of an existing controlled dataset split, followed by reopening. Both of the 2 libraries and their export packages remained byte-identical across reopening. The 4 original/revision audio and video files played to the end in an independent player, and the image opened independently. No new model ran; full AC27, M6, and release remain incomplete. [Twelve-export acceptance](implementation/2026-09-20-ver2-4-039-twelve-exports.md)

The fixed company-signed 039 candidate includes the export directory-entry fix. Its actual packaged service rejected 4 invalid entry types, recovered a valid interrupted package, and completed a fresh export. Native inspection of failed and successful records, normal exit, and reopening of the formally restored library passed. No new models ran; full AC27, M6, M0—M6, and release remain incomplete. [039 acceptance and boundaries](implementation/2026-09-16-export-tree-integrity.md)

The following records retain their state when written.

Subsequent source fix: the actual packaged 038 service still incorrectly accepts a symbolic link for the manifest; negative evidence is retained. Source now rejects manifest links, dangling links, directory links, and special files, with 186 related regressions passing. This is not yet included in a new signed candidate; full M6 and release status do not advance. [Directory-entry fix and negative evidence](implementation/2026-09-16-export-tree-integrity.md)

The fixed company-signed 038 candidate includes the complete export manifest identity fix. Rejection of an incorrect version after controlled registration failure and a successful new export passed in the packaged service, followed by native inspection, normal exit, and reopening of the formally restored library; the database was entirely unchanged after the second shutdown. No new model runs occurred; full M6, M0—M6, and release remain incomplete. [038 acceptance and boundaries](implementation/2026-09-16-ver2-4-038-export-identity.md)

The following records retain their state when written.

037 verified native disk-full rejection before copying and recovery, plus preservation of failure and recovery export after actual mid-copy volume exhaustion in the packaged service. Native history inspection and reopening after formal backup and restoration also passed; original failed and successful records and files remain unchanged, with no new model runs. The mid-copy fault was still triggered through HTTP, and the synthetic fixture does not establish model capability. Full M6, M0—M6, and release remain unpassed. [037 disk-full recovery acceptance](implementation/2026-09-16-ver2-4-037-storage-recovery.md)

The same signed 037 candidate completed actual admission rejection, native report export, and reopening for an existing failed evaluation. All 11 payload files and 60884 bytes passed individual checks; 52 original resources remain, with 4 export resources added and 0 new model runs or evaluations. The quality failure remains; full M5, M0—M6, and release remain unpassed. [037 quality report acceptance](implementation/2026-09-16-ver2-4-037-quality-export.md)

The fixed company-signed 037 candidate passed native offline registration and application of downloaded data: a real 292-byte download containing 2 rows was registered and applied to the original task after the provider stopped and the market reopened. Draft revision changed from 2→3, only the dataset changed, and seed 817 was preserved. Normal exit, stopped-library readback, and original-data restoration passed; full M4, M0—M6, and release remain unpassed. [037 native offline acceptance](implementation/2026-09-16-market-offline-downloads.md)

The following source-stage records retain their state when written.

Source progress: when the market catalog is unavailable, users can explicitly view completed local downloads, verify and register them, and apply them to the original draft. The 31 frontend, 63 backend, and targeted host tests passed, as did the real HTTP browser flow. The fixed App remains 036 and does not contain this fix; native acceptance and full M4 remain pending. [Offline download entry](implementation/2026-09-16-market-offline-downloads.md)

The fixed company-signed 036 candidate includes the official-model runtime-boundary fix. Package checks and limited native notice acceptance passed: official-catalog and local-inspection explanations were visible, with 1 project/1 import plan and no download, import confirmation, or model execution. Normal exit and original-data protection/restoration passed; full M2 and release remain unpassed. [036 notice acceptance](implementation/2026-09-16-official-model-runtime-boundary.md)

The following source-stage and earlier-candidate records retain their state when written.

Source progress: official model preparation now shows runtime boundaries consistent with manual import, and newly registered models retain fields from actual verification. Missing/unknown notices add no download or registration gate. Related tests passed; the fixed signed App remains 035 and does not contain this fix. Full M2 and release status are not advanced. [Official model preparation boundary](implementation/2026-09-16-official-model-runtime-boundary.md)

The 035 packaged worker completed one real generation under process network denial, producing `7`; the rejection matrix for unsupported media/cache requests is published (E146). This does not establish physical disconnection, a product OS sandbox, or cache-hit performance. Real HTTP cancellation and subsequent generation recovery through the packaged control service also passed, without App UI acceptance in this round; M2 and release status are not advanced. [Runtime boundaries and evidence](implementation/2026-09-16-ver2-4-035-runtime-boundaries.md)

The fixed company-signed 035 candidate received limited acceptance for real local inference and same-library reopening on Apple M5 Max (E145): import trust and persisted boundaries, preset cancellation/application, rejected50+79/allowed50+78 budgets, auto512/stop39/stream=false→text7, saved work, and an unexecuted recipe draft are evidenced. There was 1 attempt and 0 training; 15 resources/4 commands/13 events/6 artifacts and31 file hashes remained unchanged, both App exits were normal, and47/44 protection records plus12 source-model files passed restoration checks. The original guard exit1, rejected launch, and interrupted locking remain recorded; M2, full AC, M0, M2—M6 and release status are not advanced. [035 inference and reopening evidence](implementation/2026-09-16-ver2-4-035-native-inference.md)

The following source and candidate paragraphs retain their state when written; “035 not built” does not describe the current candidate.

The fixed company-signed 034 package and native collection roundtrip received limited acceptance (E144): recovery after a real interruption in a new fixture-executor library, collection-only retry, saving a short text work, and same-library reopening. The original failure remains, with no new attempt or model execution. Resources 7→10, 2 commands/3 events, both normal exits, and 47/44 protection restoration passed. The M1 application and data foundations stage passed (contract and UI subsets); full AC, M0, M2—M6, and release remain unpassed. [034 collection recovery and stage evidence](implementation/2026-09-16-ver2-4-034-collection-recovery.md)

The following source-stage, E143, and earlier records retain their state at the time.

Source progress: fixes recover manual collection stuck in collecting after interruption and cover computation finishing first, failed-exit records, and stop-signal errors. The final integrated regression passed 221 tests. The fixed signed App remains 033 and does not contain these changes; no 034 build has occurred, and complete M1 and release status do not advance. [Collection recovery and source limits](implementation/2026-09-16-collection-recovery-source-progress.md)

The fixed company-signed 033 package and native dataset workflow received limited acceptance (E143): three import rejections, 7-row import, source splitting, successful configuration checking followed by length invalidation, and direct draft restoration in the same library. Stopped-state checks found 12 new resources, 3 commands, 0 attempts, and draft revision 5; both normal exits and 47/44 protection restoration passed. No training or model generation occurred; complete M1, M0—M6, and release status do not advance. [033 dataset workflow and limits](implementation/2026-09-16-ver2-4-033-dataset-workflow.md)

The following source-stage, E142, and earlier records retain their state at the time.

Pre-build source progress: stale dataset-split reads no longer clear apply errors, and failed manual-collection registration can preserve the computation result and allow retries after recovery. Related source tests and browser component fixture checks passed. The fixed App remains 032; 033 has not been built, and this round’s native dataset workflow has not run. [Source fixes and limits](implementation/2026-09-16-dataset-and-collection-source-fixes.md)

**032 Subtitle Workflow Acceptance (2026-09-16, E142)**: The fixed signed App was not rebuilt. Keyboard operation of the functional flow, container-scroll sampling, continuing/discarding temporary edits, one v5 save, and same-library reopening passed. Only the final cue changed across 200 cues/16000 characters. Explicit historical v4 selection produced a 5-file export while current v5 and historical v4 remained intact. Root accepted both normal exits, 44 of 47 protection records strictly unchanged, and selector restoration. No model ran. The old 020 root cause remains unknown; full AC22, AC27, M0—M6, and release status do not advance. [Subtitle workflow and limits](implementation/2026-09-16-ver2-4-032-subtitle-workflow.md)

The following E141 and earlier records preserve their state at the time.

**032 Diagnostic Directory Regression (2026-09-16, E141)**: The fixed company-signed App was not rebuilt. Actual import covered 3 trilingual samples totaling 650 bytes; directory-chooser cancellation and whole-diagnostic cancellation were verified separately. Saving to a directory with Chinese characters and a space produced a 9316-byte ZIP that passed manifest, CRC, hash, and redaction checks. After reopening the same build and library, all tables, raw database bytes, and ZIP bytes were unchanged. Both normal exits and original-data restoration passed. Automatic environment probing was nonzero; no model ran. Diagnostic success does not replace full AC27, AC22, M0—M6, or release acceptance. [Diagnostic regression and limits](implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md)

The following E140 and earlier records preserve their state at the time.

**032 Python Path Progress (2026-09-16, E140)**: The fixed company-signed candidate is now Ver2.4（032）. Source tests, the single build, and root complete-bundle verification passed. Root acceptance covers the limited native subset of original symlink-path selection, cancellation and an ordinary-file control, saving all three environments, reopening the same build and library, restoring bundled environments, two normal exits, and protection restoration. Stopped-state revisions are 4/7: all three fields first preserve the exact original path, then explicitly return to null. External dependency-probe failures remain recorded; no model ran. Full AC, native races, M0—M6, and release status do not advance. [032 progress and limits](implementation/2026-09-16-ver2-4-032-python-path-preservation.md)

The following 031 and earlier records preserve their state at the time.

**031 native-picker progress (2026-09-16, E139)**: The fixed company-signed candidate is now Ver2.4（031）; source tests, the single build, and root complete-bundle verification passed. The native UI imported 3 JSONL samples totaling 509 bytes and exercised file-selection and Python-confirmation cancellation. However, selecting the venv Python made the confirmation display the base interpreter path, so it was cancelled without saving environment settings. Saving all three environments, reopening, restoring bundled environments, and diagnostic export remain incomplete; native race coverage, full AC, M0—M6, and release status do not advance. [031 progress and failure record](implementation/2026-09-16-ver2-4-031-native-picker-progress.md)

The 030 and earlier records below retain their status at the time of recording.

**Latest connection-isolation progress (2026-09-16, E138)**: The fixed company-signed candidate is now Ver2.4（030）. Source regressions, the single signed build, root verification of the complete bundle, and two packaged real-control tests covering restart authentication and migration-failure rollback passed. Root acceptance covers the limited native subset of full backup, rollback after target-library startup failure, successful switching, separate project saves, and reopening the same build. Stopped-state readback and restoration of the original-library selection passed. Asynchronous races in native file, directory, and Python environment pickers remain outside this scope; full AC, M0—M6, notarization, and public release are incomplete. [030 progress and boundaries](implementation/2026-09-16-ver2-4-030-connection-isolation.md)

The historical snapshots below retain their status at the time of recording; they do not mean that the current candidate remains on an older version.

**Latest Media keyboard progress (2026-09-16, E137)**: The fixed company-signed candidate is now Ver2.4（029）. Root acceptance covers the single build and the limited native subset: four instances of the three entries across two existing tasks, forward and reverse Tab, Enter to open, Escape to close and return focus, normal exit, and one stopped-state readback. The 523 resources, 673 events, 3 commands, and all business records remain unchanged; only four expected page-setting leaves changed. No real import or model run occurred. The existing limited acceptances for 028 and 027 remain in place; full AC, M0—M6, notarization, and public release remain incomplete.[Progress for this change](implementation/2026-09-15-media-keyboard-progress.md)

The E136 and earlier records below retain their original wording from 2026-09-15; insufficient capacity and the unbuilt candidate describe the historical state.

**Latest Media keyboard progress (2026-09-15)**: the current fixed-path company-signed candidate remains Ver2.4（028）. The minimal attribute fixes for the Media model/image-dataset/image-material import entry points, 56 related frontend tests, type checking, and the real Safari subset covering forward/reverse focus and Enter/Escape focus return have been accepted; independent-review follow-ups are closed (E136). 029 has not been archived, built, or verified natively. Capacity is below the original 40 GiB threshold; debug-cache cleanup awaits user confirmation and has not run. Full AC and M0—M6 status is unchanged. [Current progress](implementation/2026-09-15-media-keyboard-progress.md)

E134/E135 and earlier records below retain their original wording and historical context.

**Latest Workbench keyboard progress (2026-09-15)**: the fixed-path company-signed candidate was updated to Ver2.4（028）. Minimal keyboard-attribute fixes for the Workbench back, import-model, import-data, and new-evaluation-plan buttons, 59 related frontend tests, type checking, and a real Safari subset passed (E134); the snapshot-saving error and evidence scope are recorded. The root accepted the single 028 build, native forward/reverse focus for four buttons, normal exit, and a stopped-state data subset (E135): 523 resources / 673 events / 3 commands and all business records were strictly unchanged, with only three page-selection changes. Limited acceptance of keyboard-only export of an original text work and reopening the same identifier in 027 is retained. Full AC and M0—M6 status is unchanged. [Current progress](implementation/2026-09-15-ver2-4-028-workbench-keyboard-progress.md)

E132/E133 and earlier records below retain their original wording and historical context.

**Latest keyboard-task progress (2026-09-15)**: the fixed-path company-signed candidate was Ver2.4（027）. Minimal keyboard-attribute fixes, 75 frontend regressions, and a Safari component subset have evidence (E132). The native original text work exported successfully and the same record was reopened from the queue; the root accepted stopped-state readback and this native keyboard-task subset (E133). Full AC-23/AC-25/AC-26 and M0—M6 status is unchanged. [Current progress](implementation/2026-09-15-ver2-4-027-keyboard-progress.md)

E130/E131 and earlier records below retain their original wording and historical context.

**Latest export-recovery progress (2026-09-14)**: the fixed-path company-signed candidate remained Ver2.4（026）, with no product changes or rebuild in that round. Registration-failure tests and a valid independent restore were completed (E130). A complete text revision 3 export package succeeded under the same identifier after verification; the native and protection subsets were accepted (E131). Full AC-23/AC-27 and M0—M6 status is unchanged. [Current progress](implementation/2026-09-14-ver2-4-026-export-recovery-progress.md)

E128/E129 and earlier records below retain their original wording and historical context.

**Latest implementation entry (2026-09-14)**: the fixed-path company-signed candidate was updated to Ver2.4（026）. First-read focus recovery for revisions, 41 related regressions, Safari comparison, and the single signed package were accepted (E128). A limited subset covering native first-open/reopen focus in the same package, closing back to the entry point, reading saved subtitles, and exit protection was accepted (E129). Full keyboard acceptance, the historical 020 blank display, and all WP/AC/M-stage statuses remain unchanged. [026 execution progress](implementation/2026-09-14-ver2-4-026-progress.md)

Startup terminology: the 1.1 3-second target concerns initial visibility of the main window in an installed environment with a normal data scale, measured with 20 independent cold starts and excluding the first model download. Full readiness is a separate observation. A single 024/025 full-readiness run exceeding 3 seconds does not directly establish an initial-visibility failure. The 011 initial-visibility 20/20 result and historical full-readiness variation remain separate; this round adds no new 20-run initial-visibility acceptance. [Original requirement at line 118](01-product-requirements.md)

E127 and earlier entries below retain their original wording and historical context; comparisons between full readiness and 3 seconds must be read under the distinction above.

**Latest implementation entry (2026-09-14)**: the fixed-path company-signed candidate remained Ver2.4（025）. A directly usable new independent library was created through formal restore (E126). In the same native package, a limited subset established reading current subtitle version 4 / parent version 3, 200 cues / 16000 characters, closing back to the entry point, reopening with Enter, and continuing review or explicitly discarding temporary edits (E127). The first E125 source failure is retained. Full keyboard acceptance, the 020 blank display, and complete AC/M0—M6 status are unchanged. Host full readiness in that run was approximately 5.450 seconds, still above 3 seconds. [025 execution progress](implementation/2026-09-14-ver2-4-025-progress.md)

E124/E125 entries below retain their original wording and historical context.

Version: 1.1 · Revised: 2026-09-09 · Requirements baseline: the final integrated Demo plus 14 audit-remediation items and 5 enhancement decisions.

**Current implementation entry (2026-09-14)**: the fixed-path company-signed candidate was updated to Ver2.4（025）. One fix for focus returning to the manual-revision entry point, 36 related tests, Safari before/after comparison, and the single company-signed package were accepted (E124). This native run did not reach subtitle content or editing because “the original revision snapshot lacked a complete restore source.” Only focus return after closing the error dialog, reopening with Enter, and exit protection were established (E125), not complete native acceptance. Host full readiness in one run was approximately 5.055 seconds, still above 3 seconds. Full AC/M0—M6, the 020 blank display, and complete keyboard behavior remain unverified. [025 execution progress](implementation/2026-09-14-ver2-4-025-progress.md)

The 024 entry and E123 record below retain their original wording and historical context; “current candidate” refers to that version at that time.

**Implementation entry (2026-09-14)**: the current fixed-path company-signed candidate was Ver2.4（024）. The static import index, related tests, and single company-signed package were accepted (E121). One limited native diagnostics and protection-restoration subset was accepted (E122), with full readiness of 3.938 seconds, still above 3 seconds. A reduced median for offline imports does not establish stable complete-startup improvement or explain the historical 011 tail of 45 seconds. The intermittent 020 blank display, full keyboard coverage, and complete AC/M0—M6 remain unverified. See [024 execution progress](implementation/2026-09-14-ver2-4-024-progress.md). [023 phase records](implementation/2026-09-14-ver2-4-023-progress.md), [022 focus records](implementation/2026-09-14-ver2-4-022-progress.md), and earlier results retain their historical attribution; AC-22 status is unchanged.

Subsequently, E123 established that the original 020 action was clicking the differences section and then scrolling 160 pages in one action. Neither separate nor consecutive Safari comparisons reproduced the blank display, and the original issue remained open. The 6 fixture tests, complete image/text records, and production-file preservation checks passed, with no product modification or new App build; the candidate remained 024. [Long-subtitle diagnosis](implementation/2026-09-14-subtitle-scroll-diagnosis.md)

E109 clicked 70 milliseconds after the 15-second fault window. The watcher exited with 3 and 0 mkdir operations. The pending/reconciled observations remain null: 1 ordinary export, 0 verifications, 0 model runs. The 25 pure window-decision tests establish preparation only; this round does not retry or add budget. [E109 scope and originals](implementation/2026-09-13-ver2-4-017-progress.md)

The first valid project-A image in E108 was delayed by 9.445 seconds, missing the 3-second target. The 20.610/28.223-second sampling gaps remain and do not prove continuous observation. A decodable PNG does not establish quality; 23 new artifact records do not mean 23 new physical files. [E108 scope and originals](implementation/2026-09-13-ver2-4-017-progress.md#e108图片生成与项目切换有限子集)

The first 017 source review exited with 1 because the control-service environment lacked PyInstaller, before reading source/PYZ. Selecting the existing packaging environment allowed a supplementary run of the identical verifier to pass, without installing dependencies; the first failure original is retained. [E107 evidence and environment correction](implementation/2026-09-13-ver2-4-017-progress.md#e107源码测试与唯一签名包). The 016 A/B export-recovery subsets still belong to [016 historical progress](implementation/2026-09-13-ver2-4-016-progress.md): E106's first SQL exit 1 from a projection omission, 7 tests and offline correction, and the missing screenshot for menu 05 remain recorded. Actual native neutral-message behavior, successful registration repair for a complete published package, complete AC-16/27, and M0—M6 were not complete at that point.

Existing revision layout and one ordinary image completion/save in 015 retain their [historical acceptance](implementation/2026-09-13-ver2-4-015-progress.md). The image batch missed the running window; four native observations remain null, with no AC-01/02 timing or image-quality acceptance. Recipe/ordinary-draft reuse, model differences, and reopening favorites in 014 remain attributed to the [014 record](implementation/2026-09-13-ver2-4-014-progress.md). The 011 initial-visibility 20/20 result, visible by 3 seconds at the latest, and full-readiness median 8.197 seconds, p95 16.435 seconds, maximum 45.102 seconds are historical results, not new 017 measurements. The specified NVIDIA device, actual cross-host operation, device differences, clean installation, native late-old-request handling, five first-time users, and full-stage sign-off remain outstanding; old quality failures and both consumed budgets remain. See the [delivery matrix](implementation/2026-09-10-current-delivery-matrix.md) for scope, the [Chinese user guide](USER_GUIDE.zh-CN.md) for operation, and the [Ver2 combination](implementation/2026-09-10-ver2-scope.md) for the selected version scope.

The body below preserves the 1.1 design baseline of 2026-09-09. “Current delivery,” “still to be executed,” and “development has not started” refer to the design delivery at that time, not the latest implementation entries above.

<a id="1-文档用途与当前结论"></a>

## 1. Purpose and current conclusion

These documents turn the confirmed product prototype into a development baseline that can be implemented, assigned, and accepted. They cover product scope, interaction flows, training and inference, hardware adaptation, data and assets, architecture, interfaces, AI assistance, development scheduling, testing, and release.

**The current delivery is the audit-revised design and development plan; Demo fixes and real product implementation remain to be executed.** Version 1.1 adds workflow identity, parameter dependencies, exceptional controls, artifact collection, media caching, SFT supervision, model-loading trust, and export contracts, separating stage validation from final acceptance. Bounded M0 technical experiments may now begin; exact models, devices, personnel, and dates still need to be fixed using measurements.

The prototype's 42 main-flow and 17 runtime-optimization test groups establish only the demonstrated behavior they cover. Updating documents did not remove the 6 behavioral issues found by the audit. See [16 Audit remediation and requirements traceability](16-audit-remediation-plan.md) for implementation status and the [validation report](validation-report.md) for current validation evidence.

The following states must remain distinct in subsequent reviews and development:

| State | Meaning | May it be presented externally as supported? |
| --- | --- | --- |
| Demonstrated in prototype | The Demo has a corresponding page, configuration, or simulated flow | Only as a prototype feature |
| Specification awaiting implementation | Explicitly required here, but not implemented in the real application | No |
| Proposed technical approach | A development technology or structure proposal, subject to technical validation | No |
| Combination awaiting verification | Upstream capabilities exist, but this project has not verified the full combination | No |
| Real-device acceptance passed | Evidence identifies the exact device, model, version, parameters, and report | Only within the report's scope |
| Documentation work complete | Specification, responsibility, and acceptance were updated; implementation state is recorded separately | Not grounds for claiming a feature fixed |

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
| [16 Audit remediation and requirements traceability](16-audit-remediation-plan.md) | 20 requirement relationships, 14 remediation items, 5 enhancements, implementation status, closure gates | Project lead, development, testing |
| [Documentation validation report](validation-report.md) | Document, link, example, and prototype-test results for this round | Delivery acceptance reviewers |

Read 16 first for the changes in this round, then by role: product should read 01, 02, 14; development kickoff should read 06, 07, 09, 10; module implementation should also check its specialist documents and 11. Historical references include the [audit report](audits/2026-09-09-demo-docs-audit.md) and [1.0 documentation archive](archive/v1.0-2026-09-09/README.md).

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
- M0 uses TV-01—TV-03; M1—M6 use explicit stage gates. A work package's final AC is for complete acceptance traceability, not a late-stage prerequisite for an early experiment.
- Requirement definitions, work-package responsibilities, and direct AC coverage must be bidirectionally consistent with 16. Record structural checks separately from human semantic review; the presence of an identifier does not establish semantic consistency.
- Before adding a top-level entry point or changing AI-action boundaries, update product requirements and interaction, then implementation tasks.
- Model names, engine versions, precision support, and performance conclusions change. Update them through capability records and measurements rather than relying on a fixed “supported” checkmark in a document.

<a id="5-范围说明"></a>

## 5. Scope statement

This round updated the Chinese Markdown specifications and plans, added documentation validation and negative tests under `docs/tools`, and archived the original 1.0 documents. It did not modify the Demo or start product-backend development. Technology choices, scheduling, compatibility verification, and team effort are a proposed development baseline; confirmed Demo information architecture and action boundaries are product inputs.

<a id="6-本地验证入口"></a>

## 6. Local validation entry points

Run from the project root:

```sh
python3 docs/tools/validate_docs.py
python3 docs/tools/test_validate_docs.py
```

The first command checks current document structure, references, requirements traceability, and stage relationships. The second tests the tool with representative counterexamples such as wrong mappings, wrong durations, missing remediation, and inverted stage dependencies. The tools do not execute models or change product state. See the validation report for final counts and what the checks cannot prove.
