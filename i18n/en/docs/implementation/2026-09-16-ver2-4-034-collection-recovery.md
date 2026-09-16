<a id="ver24034原生补收恢复与-m1-证据e144"></a>

# Ver2.4（034） Native Collection Recovery and M1 Evidence: E144

Root accepted the limited flow in the fixed company-signed 034 package and a new fixture-executor library: interrupted collection recovery, explicit collection-only retry, work saving, and same-library reopening. Resources increased from 7 to 10, adding 1 collection, artifact, and work each, with 2 commands and 3 events, no new attempt or model execution, and the original four terminal-failure fields preserved. Both normal exits, 44 strictly unchanged records out of 47 protection records, and selector restoration passed.

<a id="m1-阶段判定"></a>

## M1 Stage Decision

Root separately accepted the M1 application and data foundations stage, covering all seven contract/UI subsets. Full AC, M0, M2—M6, notarization, and formal release remain unpassed. The native single-scenario receipt retains M1_complete=false as its original scope statement; this does not replace the separate stage decision, and historical records are not rewritten. [Root M1 stage receipt](../../../../.artifacts/integration-ver2-4-034-v1/m1-stage-acceptance.md), [native and seven-row independent review](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/independent-native-review.md)

| M1 subset | Basis for this stage acceptance |
| --- | --- |
| Project/draft persistence and isolation | The 221-test control/context regression, E143 same-draft reopening, and current work ownership remain valid. [Native history](2026-09-16-ver2-4-033-dataset-workflow.md) |
| Entry points, keyboard/empty states | Earlier bounded native evidence, this round’s 18 component tests, and 034 collection-only/save actions passed. [Component results](../../../../.artifacts/integration-ver2-4-034-v1/m1-workbench-contracts.log) |
| Fixed prototype/test inventory | Fixed manifests, hashes, and rerun commands remain intact; asset-organization evidence is reused without retroactively claiming M6 new-member acceptance. [Fixed assets](../../prototype/reference-2026-09-09/README.md) |
| Real files/manifest and import trust | E143 import rejections/file evidence and this round’s original manifest/output plus 8 runs files remain intact. [Independent review](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/independent-native-review.md) |
| Fixture-executor lifecycle and collection-only retry | The 221-test run includes 10 lifecycle/11 recovery cases; the native roundtrip after a real interruption closes the main previous gap. [Control review](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-and-recovery-final-review.md) |
| Capability-dependent rejection | This round’s 64 capability tests, E143 length invalidation, and current allowed actions meet the stage scope. [Capability results](../../../../.artifacts/integration-ver2-4-034-v1/m1-capability-contracts.log) |
| Transactions and backup foundations | The 221-test run includes 36 backup/15 migration cases; new-library restoration, persistence, and original-data protection passed. [Root stage decision](../../../../.artifacts/integration-ver2-4-034-v1/m1-stage-acceptance.md) |

<a id="唯一构建与分层测试"></a>

## Single Build and Layered Tests

The 033 source at commit `fe5de1a08e174d1016bf3bdcf0574f107cc35b67` is the baseline; the single build automatically changed four version files to 034 and exited 0. Root verification passed for 648 tracked sources, 162 production/212 frozen/92 application inputs, 21966 files/48 links/4003 directories, and 7 company-signed targets, retaining Global Cybersecurity Alliance Limited. The packaged control PYZ matches the repaired code; the 033 archive and 47 build-protection records remain intact. [Root package verification](../../../../.artifacts/integration-ver2-4-034-v1/root-frozen-check.json), [build record](../../../../.artifacts/integration-ver2-4-034-v1/build-process.json)

The integrated source run passed 221 tests with 117 source inputs bound consistently before and after execution. Separately, 64 capability-contract and 18 workbench-component tests passed. These cover temporary real files/databases/processes, validators, and browser components at distinct layers, not a combined stage-pass count. Historical 36/73/134-test groups overlap newer runs. Original SIGKILL and lifecycle failures, setup errors, 209+2/219+2 runs, and the unexplained earlier CLI timeout remain recorded. Loopback-test proxy isolation changes neither product nor system proxy settings. [Source progress](2026-09-16-collection-recovery-source-progress.md), [221-test independent review](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-221-v2-independent-review.md), [64 tests](../../../../.artifacts/integration-ver2-4-034-v1/m1-capability-contracts.log), [18 tests](../../../../.artifacts/integration-ver2-4-034-v1/m1-workbench-contracts.log)

<a id="原生准备与实际操作"></a>

## Native Preparation and Actual Operation

The new library explicitly labels the result as non-model fixture output. The fixture executor ran 1 time with 0 resumes; a controlled ENOSPC left the original attempt with successful computation but failed collection. After backup/restoration, a child was actually SIGKILLed at the collection-only copy boundary, exiting -9 and leaving collecting. Service was not used to recover new A in advance. The preparation receipt records 70 closed SQL connections and 0 connections to the original library. The killed child’s connections were closed by the operating system, not a normal Service.close. [Preparation result](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/setup-result.json), [interruption boundary](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/crash-checkpoint.json)

On the first actual 034 launch, the UI retained the original failed execution and offered `只补收已有产物`. One click completed collection while retaining the original interruption/cancellation record. One save-work action then produced a saved text card showing the original attempt ID and the entire short text. No separate editor was opened and no text was changed. The second launch of the same version/library directly restored the works page; returning to the original task retained the text, original failure, and collected-result notice, without collecting or saving again. [Native UI and limits](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/ui-review.json)

Stopped-state readback confirmed resources increasing 7→10, adding only 1 collection/artifact/work each, 2 commands, and 3 events, with no new attempt, training, or model generation. Collection version advanced from 3 to 6, leaving 3 collection records. The original state, state_version, terminal_reason, and finished_at fields, computation manifest, and output hash remained intact. The exact `COLLECTION_INTERRUPTED` cause comes from collection records and stopped-state events; the UI did not display that code. [First readback](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/first-check.json), [reopening readback](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/second-check.json)

Both App runs exited normally with code 0. Business tables and the work files remained unchanged across reopening, while UI context could change; neither raw database nor whole-snapshot byte equality is claimed. Of 47 existing protection records, 44 remained strictly unchanged. Original selector bytes/inode/permissions and other identity fields were restored, retaining the ctime change; two startup logs were allowed to update. The guard restored and released protection. [Root readback](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/root-readback.json), [limited native acceptance](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/root-native-acceptance.json)

<a id="失败历史与证据限制"></a>

## Failure History and Evidence Limits

The first launch request was rejected before Popen because the guard used a valid relative path; no App process had been created. The launcher only corrected exact path and working-directory recognition, passing 9 representative tests and preserving original files and the failure receipt. Root explicitly retried; actual App launches totaled two, with no automatic retry or product change. AX returned App quit after exit, supplemented by the recorder’s exit code 0. [Launcher correction and original failure](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/launch-path-fix-001/REVIEW.md)

This round preserves 5 AX/screenshot pairs demonstrating key UI states, not continuous video. The full short text was visible in a card, which is not editor acceptance; fixture output establishes neither model quality nor real training. M1 uses fixture-executor contract and UI subsets, without adding M2—M6, physical NVIDIA hardware, or new-member installation acceptance as M1 prerequisites. This sequential native flow also does not replace all source-level race tests. E143 and earlier source-stage records and failures remain intact.

Some model names are truncated in screenshots, with full names verified through AX. Key checkpoints do not establish the total HTTP request count or imply zero environment probes.
