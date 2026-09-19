<a id="冷启动备份恢复入口源码进度"></a>

# Source progress for cold-start backup recovery

When cold startup leaves no healthy control service, users can explicitly enter an independent backup recovery workspace. Source implementation and isolated tests are complete; the fixed company-signed App remains Ver2.4（039） and has not been rebuilt or replaced. The planned Ver2.5（040） signed bundle and native acceptance remain pending, with no promotion of full AC-22, M6, or formal release status.

<a id="行为与原资料保护"></a>

## Behavior and protection of original data

Recovery mode allows only formal portable-backup inspection, independent restoration, result verification, and explicit switching. The host rejects ordinary project, model, execution-environment, and credential operations. The recovery workspace does not connect to or rewrite the original failed library's database, assets, or failure evidence. The application data directory gains an independent recovery session, so its entire tree cannot be described as unchanged. Recovery destinations must be outside the original failed library and application data directory.

Before retrying or reconnecting after failure, the host checks the recovery directory's identity, permissions, and session receipt. Entry captures either the absence or the regular-file identity of the original library selection, which is checked again before switching and after the new service starts. Recovery mode clears only after the new library starts and its selection is saved. Migration or persistence failure returns to the same recovery workspace; the original failed library is recorded as the previous library. Selection checking and file renaming are not an atomic cross-process compare-and-swap operation and do not claim protection against malicious concurrent replacement.

During copying, the interface prevents closing and rejects exit preparation; the host also rejects switching or restarting. Even after a request times out, exit requires the control service to confirm that background work is idle and freeze writes. Exiting without explicitly switching preserves the original library selection. Re-entering creates a new session while keeping earlier restored directories. A directory containing only a migration database and receipt still cannot be used directly as a portable backup.

<a id="验证与证据"></a>

## Validation and evidence

All 648 frontend tests and type checks passed. Rust had 84 passing tests; 3 tests requiring an explicit environment were not run. The passing tests include 11 recovery-identity tests and 7 host recovery-flow tests added in this change. Backup/migration tests had 51 passes and 2 existing warnings. The initial Rust compilation failed while collaborative code was incomplete; after integration, the repository's designated toolchain passed. Relevant logs are retained. [Frontend](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/frontend-tests.log) [Host](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/rust-final.log) [Backup and migration](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/control-tests.log)

Computer Use exercised the actual frontend source in a browser fixture: entry into recovery, backup and destination selection, scope inspection, exit rejection during copying, exit acknowledgment after completion, and entry into the ordinary workspace only after an explicit switch. Page screenshots were also inspected. IPC, file pickers, copying, and library switching were simulated. No native App was launched, original user database connected, or model run. This verifies only the interface contract. [Interface readback](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/browser/readback.json)

The review findings about recovery-directory identity and replacement of the original selection were fixed, and a wiring review found no new blockers. The actual signed candidate still needs cold-start failure, recovery-failure reconnection, healthy portable-backup switching, exit, and reopening validation. Clean installation, old-App rollback, failed upgrades containing business data, and the remaining stage gates are incomplete. Prototypes, research assets, and failure evidence are retained. [Code review](../../../../.artifacts/cold-start-recovery-ver2-5-040-v1/design-review/code-review-002.json)
