<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md) · [繁體中文](../../../zh-TW/docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md) · [English](2026-09-16-ver2-4-030-connection-isolation.md)
<!-- translation-navigation:end -->

<a id="ver24030工作库连接隔离e138"></a>

# Ver2.4（030） Library Connection Isolation: E138

The current company-signed candidate at the fixed path is Ver2.4（030）. Source tests, the single build, root verification of the complete bundle, and two packaged real-control tests are complete. Root acceptance covers the limited native subset of full backup, rollback after target-library startup failure, successful switching, separate project saves, and reopening the same build. Normal exits, stopped-state readback, and restoration of the original-library selection passed. The 029／E137 and earlier records remain preserved; full AC and M0—M6 status does not advance.

<a id="修复范围与源码验证"></a>

## Fix Scope and Source Verification

Ordinary API requests and media reads bind at invocation to a connection identity that is not a credential. The host rechecks this identity before dispatch and after completion. Switching, rollback, or restart rejects old requests and late responses; writes are not automatically resent with a new library identity. Startup notifications for the same connection preserve valid reads. An actual reconnection invalidates old environment checks and waits for the host operation to finish before reading state.

Passed 574 frontend tests, 52 ordinary host tests, and type checking. Temporary HTTP services verify that old-library requests do not reach the new library; the corresponding red case and pre-fix initialization-notification race failures are preserved. The 3 onsite tests ignored by the ordinary host run were not counted as passing. Two were later executed separately, as described below. [Frontend regression](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/frontend-tests-001/regression-delivery.log), [host test directory](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/rust-tests-001)

Cross-library asynchronous races while native file, directory, or Python environment pickers are pending remain uncovered. This change does not establish isolation of every asynchronous command. No model capability or training budget was added.

<a id="唯一构建与签名复核"></a>

## Single Build and Signature Verification

Available capacity before building was 109.523 GiB, above the original 40 GiB threshold. The 029 archive was preserved without cleanup or lowering the threshold. The single formal build took 529.041263 seconds and exited 0, automatically updating four version files. Root verification corresponds to commit `8cb19da3e2f99a4a433d70e8d139cf8f800c3336`; 615 tracked inputs, 161 production sources, 211 frozen files, and 91 application inputs matched. [Build receipt](../../../../.artifacts/integration-ver2-4-030-v1/build-process-final.json), [root complete-bundle verification](../../../../.artifacts/integration-ver2-4-030-v1/root-frozen-check.json)

The bundle contains 21966 regular files, 48 symlinks, and 4003 directories. All 7 targets are signed by Global Cybersecurity Alliance Limited, team `R3JK7R29AC`, certificate SHA1 `7C33B517942161311A087CE893D2F1CE9B204B44`. The 47 protection records and complete 029 archive remained unchanged during the build stage. That stage launched no App, connected to no business SQL, and added no model probes. [Signature report](../../../../.artifacts/integration-ver2-4-030-v1/bundle-verification.json), [frozen sources](../../../../.artifacts/integration-ver2-4-030-v1/source-build-manifest.json)

After building, two tests actually used the current packaged control service for restart authentication and migration-failure rollback: 2 passed and 0 failed. They used temporary libraries and do not establish a native UI reproduction of migration failure. The onsite Keychain test remains unexecuted. All 12 version-synchronization tests passed. [Real-control tests](../../../../.artifacts/integration-ver2-4-030-v1/real-control-tests.stdout.log), [version tests](../../../../.artifacts/integration-ver2-4-030-v1/version-tests.log)

<a id="原生有限接受与停机读回"></a>

## Limited Native Acceptance and Stopped-state Readback

The production UI completed a full backup in newly created test library A, showing 1 file and 56.0 KB. Restoration to a new directory B then showed that files were verified. A test lock occupied B and caused its control service to fail at startup. The UI showed the original text `服务启动响应格式无效。 已恢复连接原工作库。`; A's control process changed from 32356 to 51024, and a new project was then successfully saved in A. [Backup UI](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/02-A-backup.txt), [restoration verification](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/03-B-restored.txt), [failed-switch rollback UI](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/04-switch-failed-rollback.txt), [post-failure readback](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/failed-switch-readback.json)

After releasing B's lock, the same App successfully switched into B with control process 51729. B initially contained only the shared project, without the project added to A after rollback, and successfully saved its own new project. A second launch of the same build from the same fixed path used App/control processes 52923／52928, and B's new project persisted. Both launches exited normally with exit code 0. [Connection to B](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/B-connected.json), [UI after saving in B](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/07-B-saved-after-navigation.txt), [reopened processes](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/B-reopened-processes.json), [project menu after reopening](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/09-B-reopened-project-menu.txt), [first exit](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/launch-001/exit.json), [second exit](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/launch-002/exit.json)

Stopped-state readback confirmed the shared project with the same ID in A and B, while each new project existed only in its own library. All table contents and the database digest in B were identical before and after reopening; resource, event, and command counts were all 0. Digests and metadata for 44 existing protection records, including absent entries and duplicate paths, were unchanged. The original selector bytes, inode, and mode were restored, with the ctime change caused by renaming explicitly retained. All App, control, recovered protection-guard, and B test-lock processes stopped. [Root stopped-state readback](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/root-readback.json)

On continuation, original protection guard 32132 was found to have exited. The App was still in this run's test library, and the original selector file was preserved. Original-library protection locks were later reacquired; recovery guard 41356 and B lock process 50865 have now been closed normally. The interruption cause and exact duration remain unknown. Unchanged file readbacks do not establish continuous lock protection, and later success does not overwrite this incident. [Guard recovery record](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/selector-guard/guard-recovery.json), [protection readback at recovery](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/selector-guard/recovery-readback.json)

Independent review and the root receipt accept this limited subset while retaining capture gaps. The menu in 06 is not expanded and cannot independently establish the complete project list before B's new project was created. Record 09 contains expanded-menu AX text only, without a matching screenshot. No independent screenshot was saved after creating A's project or of the exit confirmations. A's write is supported by stopped-state snapshots and rollback process records; both normal exits are supported by exit receipts. These records cannot independently reconstruct every click or the visual content of the exit dialog. The UI error is generic: the specific occupied-directory cause comes from the underlying log and must not be described as directly shown by the UI. [Native independent review](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/independent-readback-review.md), [root limited acceptance](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/root-native-acceptance.json)

This native evidence covers rollback after a target library failed to start because its lock was occupied. It does not establish native migration-failure acceptance or a deterministic onsite reproduction of queued old IPC races. Migration-failure rollback is covered by the packaged real-control tests above; old-request isolation is covered by host HTTP tests. Those evidence layers are recorded separately from this native UI workflow.

<a id="保留的验收边界"></a>

## Remaining Acceptance Boundaries

Asynchronous native-picker races, the specified NVIDIA Linux device and cross-host return path, human media-quality assessment, clean installation, five first-time users, notarization, and formal distribution remain incomplete. Existing quality failures, budgets, the 020 long-list blank display, and performance-evidence gaps are not closed by this signature or passing tests. [Current delivery matrix](2026-09-10-current-delivery-matrix.md)

The `.artifacts` links on this page refer only to local evidence and are not published with the GitHub source. Source code, documentation, signed builds, limited native acceptance, and formal release are recorded separately.
