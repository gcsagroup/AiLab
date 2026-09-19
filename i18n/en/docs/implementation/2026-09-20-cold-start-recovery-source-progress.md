<a id="冷启动备份恢复入口源码进度"></a>

# Source progress for cold-start backup recovery

When cold startup leaves no healthy control service, users can explicitly enter an independent backup recovery workspace. The fixed company-signed App Ver2.5（040） passed bundle checks and native restoration, failure reconnection, healthy switching, and same-library reopening with controlled empty libraries. Full AC-22, M6, and formal release remain incomplete.

040 was built at the fixed path, and all 7 signed targets passed strict verification. The embedded frontend and control service match the frozen source. The 039 rollback copy, 50 original-data protection records, 4 old libraries, and 12 model source files remained unchanged; all 15 version and rollback-tool tests passed. No models ran or original user databases were queried, and notarization has not been performed. The source-stage records below retain their original test scope. [Build and protection](../../../../.artifacts/integration-ver2-5-040-v1/completed.json) [Bundle verification](../../../../.artifacts/integration-ver2-5-040-v1/root-frozen-check.json)

<a id="行为与原资料保护"></a>

## Behavior and protection of original data

Recovery mode allows only formal portable-backup inspection, independent restoration, result verification, and explicit switching. The host rejects ordinary project, model, execution-environment, and credential operations. The recovery workspace does not connect to or rewrite the original failed library's database, assets, or failure evidence. The application data directory gains an independent recovery session, so its entire tree cannot be described as unchanged. Recovery destinations must be outside the original failed library and application data directory.

Before retrying or reconnecting after failure, the host checks the recovery directory's identity, permissions, and session receipt. Entry captures either the absence or the regular-file identity of the original library selection, which is checked again before switching and after the new service starts. Recovery mode clears only after the new library starts and its selection is saved. Migration or persistence failure returns to the same recovery workspace; the original failed library is recorded as the previous library. Selection checking and file renaming are not an atomic cross-process compare-and-swap operation and do not claim protection against malicious concurrent replacement.

During copying, the interface prevents closing and rejects exit preparation; the host also rejects switching or restarting. Even after a request times out, exit requires the control service to confirm that background work is idle and freeze writes. Exiting without explicitly switching preserves the original library selection. Re-entering creates a new session while keeping earlier restored directories. A directory containing only a migration database and receipt still cannot be used directly as a portable backup.

<a id="验证与证据"></a>

## Validation and evidence

All 648 frontend tests and type checks passed. Rust had 84 passing tests; 3 tests requiring an explicit environment were not run. The passing tests include 11 recovery-identity tests and 7 host recovery-flow tests added in this change. Backup/migration tests had 51 passes and 2 existing warnings. The initial Rust compilation failed while collaborative code was incomplete; after integration, the repository's designated toolchain passed. Relevant logs are retained. [Frontend](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/frontend-tests.log) [Host](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/rust-final.log) [Backup and migration](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/control-tests.log)

Computer Use exercised the actual frontend source in a browser fixture: entry into recovery, backup and destination selection, scope inspection, exit rejection during copying, exit acknowledgment after completion, and entry into the ordinary workspace only after an explicit switch. Page screenshots were also inspected. IPC, file pickers, copying, and library switching were simulated. No native App was launched, original user database connected, or model run. This verifies only the interface contract. [Interface readback](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/browser/readback.json)

The review findings about recovery-directory identity and replacement of the original selection were fixed, and a wiring review found no new blockers. At the time of the source review, the actual signed candidate still needed cold-start failure, recovery-failure reconnection, healthy portable-backup switching, exit, and reopening validation; the subsequent native results are in the next section. Clean installation, old-App rollback, failed upgrades containing business data, and the remaining stage gates are incomplete. Prototypes, research assets, and failure evidence are retained. [Code review](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/design-review/code-review-002.json)

<a id="040-原生验收与范围"></a>

## 040 native acceptance and scope

The fixed company-signed 040 native interface completed entry into recovery after cold-start failure, formal backup selection and verification, return to the same recovery workspace after a failed library switch, healthy-backup switching, and test-project persistence and reopening. Both the original fault library and the newly restored fault library retained their database bytes, covering 2 databases. The healthy library completed migration 1→2→3→4 and retained 1 test project and 0 resources; its database and all tables were exactly unchanged after reopening.

Existing locks protected original user libraries, and no original user databases were queried. Of 50 protection records, 47 were fully unchanged; the original selection file's object and bytes were restored, allowing rename-related metadata changes and updates to 2 startup receipts. All 4 old libraries and 12 model source files were preserved, with 0 model executions. Only preservation of the default log's original prefix was verified. Newly created recovery sessions are explicitly retained, so the entire application data directory is not claimed to be unchanged.

The initial reopen interface and normal quit were observed, but the process monitor reported an identity change without saving the process rows that caused rejection; the cause remains unproven. That failure is fully retained. The new tool records process status and relevant raw rows, waits for same-identity zombie processes to disappear, and still rejects actual identity changes. All 26 monitor tests, 8 first-session guard tests, and 8 reopen-guard tests passed. Reopening, normal quit, process disappearance, and stopped-state readback then passed with the same candidate. Launcher and guard exit codes were 0; the App exit code is unknown, and no independent proof of continuously held locks is claimed.

This round covers only controlled empty libraries and small portable backups, with no new model computation. Exit rejection during copying still has only source-test and browser-fixture evidence. Large-file copying races, failed upgrades containing business data, clean installation, old-App rollback, full AC-22／M6, notarization, and formal release remain pending.

[Final readback](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/root-readback.json) [Retained monitor failure](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/native-reopen-002/monitor/report.json) [Reopen revalidation](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/native-reopen-003/readback.json) [Recovery interface](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/native-001/06-failed-switch-returned.jpg)
