<a id="数据划分读取与人工补收修复构建前源码记录"></a>

# Dataset Read and Manual Collection Fixes: Pre-build Source Record

This page records source fixes and separate validation layers. The fixed company-signed App remains Ver2.4（032）; 033 has not been built, and this round’s native dataset workflow has not run. Browser component fixtures and temporary-database tests do not replace operation of the fixed App. E142 and earlier history remain intact; full AC, M0—M6, and release status do not advance.

<a id="旧预览读取不再清除操作错误"></a>

## Old Preview Reads Preserve Operation Errors

An old ready render in `DatasetSplitDialog` could start its read late, capture the generation of a subsequent apply operation, and clear that operation’s identity-mismatch error after a successful read. Reads now bind their generation during rendering and reject stale starts before the effect runs. Existing callback checks still reject previously issued stale requests. Identity checks, visible errors, retries using the original idempotency key, and rejection of invalid result updates remain intact.

The initial parallel regression lost the error message while isolated reruns passed; the original failure is retained. The 2 new controlled-order tests cover late effect starts and late responses to existing requests. The unchanged independent component counterexample passes after the fix. Passed 109 related frontend tests and type checking. Controlled scheduling verifies the callback contract; it does not claim native App reproduction. [Independent contract and red/green results](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/contracts-review.md), [initial regression](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/frontend-tests-result.json)

A real browser exercised the production component with in-memory HTTP fixtures: preview, a visible error for an inconsistent apply response, retry using the original key, and selection of the training subset. Readback confirmed 2 apply write requests with the same nonempty idempotency key, selection of `dataset-train`, 2 change notifications, and empty runtime-error and console records. This did not connect to a real control service, import data, create an actual split, or run a model. [Browser readback](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/browser-001/readback.json), [downloaded result](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/browser-001/result.json), [visible error](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/browser-001/rejected-apply-visible.png)

<a id="补收登记回滚后仍可恢复"></a>

## Recovery After Collection Registration Rollback

Manual collection first persisted `collecting`; if the subsequent artifact-registration transaction failed, it previously lacked its own cleanup and rejected later requests as still collecting. The fix records failure and releases that state only while this collection’s state and version still match, preserving the original exception for the caller. A cancellation that commits first is respected. Previously terminated computations retain their original terminal state and sealed files, without recomputation or partial successful artifact registration.

The precise failure matrix had 4 passes and 1 failure before the fix, then 6 passes after it, including cancellation committing first after rollback. Tests use real temporary SQLite databases and files, an explicit fake executor, and injected failures. They cover cancellation/registration ordering, copy-space errors, initial and manual collection registration rollback, recovery retries, idempotent replay, saving work, and closing/reopening. They run neither a real model nor the native App. Disk errors are injected rather than produced by exhausting host storage. [Pre-fix matrix](../../../../.artifacts/m1-exit-audit-ver2-4-032-v1/collection-matrix-red-review.md), [Post-fix matrix](../../../../.artifacts/m1-exit-audit-ver2-4-032-v1/collection-fixed.xml)

Independent review also found that the remote wrapper reclassified exceptions rethrown after local compensation as transfer failures, duplicating collection records and overwriting the original terminal reason. Local registration delegation now sits outside transfer exception handling; failed retransfers set a terminal reason only for nonterminal attempts. All 3 temporary-database/loopback counterexamples failed before the fix and passed afterward, covering original exceptions, terminal-state preservation, recovery collection, and same-key replay. Loopback tests do not establish external-device acceptance. [Final fix review](../../../../.artifacts/m1-exit-audit-ver2-4-032-v1/collection-fix-review.md)

Compensating writes require a writable database. Persistent faults still propagate the original registration exception rather than falsely reporting durable cleanup. This run does not establish recovery from permanent storage damage, process crashes between the transactions, or power loss, and does not sign off complete M1.

The final combined control regression passed 73 tests with 0 failures and 0 skips, retaining 4 existing dependency warnings. The initial full frontend run passed 618 tests while 2 exceeded 5 seconds, in category resumption and work-revision tests. Without changing assertions or timeouts, a rerun using 2 workers passed all 620 tests across 57 files. Original timeouts and act warnings remain recorded; this does not establish a fix for slow concurrent tests. The related 109 frontend tests and type checking also passed separately; these layers are not added together. [Control summary](../../../../.artifacts/m1-exit-audit-ver2-4-032-v1/collection-fix-summary.json), [Both frontend runs and type checking](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/frontend-validation-result.json)

<a id="后续门槛"></a>

## Remaining Gates

Both fixes must next enter an incremented build at the same path with the same company signature, followed by protected native acceptance in a new library. Import, source-group splitting, training-draft checks and reopening, and packaged collection-failure behavior each require their own evidence. Source and fixture passes do not close complete stages.
