<a id="037-磁盘满拒绝报告恢复与重开"></a>

# 037 disk-full rejection, report recovery, and reopening

The fixed company-signed Ver2.4（037） candidate passed a bounded storage-failure check. When an independent test volume actually ran out of space, the native plan rejected export. Filling it again after a valid plan caused execution to fail with disk full. Releasing the test filler, rechecking, and exporting succeeded; reopening preserved the separate failed and successful records. Full M6, M0—M6, and release remain unpassed.

<a id="候选与独立测试资料"></a>

## Candidate and independent test data

The fixed App signed by Global Cybersecurity Alliance Limited was reused without rebuilding or changing the product. Its binary digest remains `59ce9d899488da868af0935f6dcb7f09749623deab250d55eeda7def4f0b2ce0`. [Package receipt](../../../../.artifacts/integration-ver2-4-037-v1/root-frozen-check.json)

The previously frozen offline E22 file copy was restored to a new independent library through actual HTTP requests to the packaged 037 service. The input contains 91 files and 1868874298 bytes; it was not created by calling the product backup API in this round. No SQL connection was made to the original library. First startup formally migrated schema 3→4. The successful receipt and migration-backup hash were verified, and every backup table matches the prelaunch snapshot. [Restore receipt](../../../../.artifacts/native-storage-ver2-4-037-v1/restore-001/result.json) [Stopped-state verification](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/root-readback.json)

A new 64 MiB HFS+ disk image was created. Only a dedicated test filler was written, after checking the device, volume identity, and capacity. The independent filesystem has 67067904 bytes of capacity; actual writes returned `ENOSPC / errno 28`, and both failure states had 0 bytes available. The system disk was not filled. [First zero-space state](../../../../.artifacts/native-storage-ver2-4-037-v1/storage-001/fill-tail-001.json) [Second zero-space state](../../../../.artifacts/native-storage-ver2-4-037-v1/storage-001/fill-002.json)

<a id="原生拒绝恢复与重开"></a>

## Native rejection, recovery, and reopening

The test volume was selected through the native directory picker. The initial check disabled export because space was insufficient, without creating an export attempt. After releasing the filler and selecting the same directory again, the check allowed export. The volume was filled again before clicking start, producing a `DISK_FULL` failure. Rejection occurred before copying; the destination contained neither a final nor a partial package. [Rejected-plan screen](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/01-full-plan-blocked.png) [Failed-execution screen](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/03-ready-then-full-failed.png) [Failure filesystem evidence](../../../../.artifacts/native-storage-ver2-4-037-v1/storage-001/failed-export-filesystem.json)

After releasing the dedicated filler again, recovery completed through rechecking the export, checking its scope, and starting export. The successful package contains 11 payload files and 60884 bytes, plus an integrity manifest; 7 JSON reports exactly match the original sealed artifacts. Every payload hash and size was verified. The failed record is `export-c8757316996843f6842c0199fac95184`, and the new successful record is `export-7ee97c109d2f4230811d12734096dae1`. [Completion screen](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/04-recovered-export.png) [File verification](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/export-after-first.json)

After normal exit, the same candidate and independent library were reopened. Opening the original failed record and the new successful record confirmed that their states and output identities persisted; the App then exited normally again. All business tables and exported files remained unchanged. Only the selected task in settings was cleared by returning to the workbench, so database bytes are not identical. [Reopened failure](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/05-reopen-failed.png) [Reopened success](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/06-reopen-success.png)

<a id="核对测试与收尾"></a>

## Verification, tests, and cleanup

All 52 original resources are unchanged. Adding 9 resources gives 61 in total: 3 plans, 2 exports, 2 tasks, and 2 export attempts, with 2 commands and 93 events. New model runs and evaluations both total 0, the original quality failure remains, and candidate registration count is 0. The original E22 library, the previous 5 acceptance libraries, 12 model source files, and frozen input remain unchanged. The original selector was restored, the guard released its locks, and all App and control processes stopped. [Root verification receipt](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/root-readback.json)

All 12 report files, including the manifest, were copied into this round’s preservation directory and individually verified. The identity-checked test image was then detached normally. The preserved directory is an acceptance file copy, not another product export. The image file and its hash are retained; the test volume is no longer mounted. [Preservation receipt](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/export-preservation.json) [Detach and completion receipt](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/completion.json)

Export tests passed: 28 frontend tests and 52 control-service tests, with 2 control warnings retained. The native launch guard passed 7 tests and the volume-identity helper passed 3 tests. [Frontend log](../../../../.artifacts/native-storage-ver2-4-037-v1/frontend-tests-corrected.log) [Control log](../../../../.artifacts/native-storage-ver2-4-037-v1/control-tests.log)

Preparation failures are retained: the first image-creation argument was invalid; the initial large-block fill reached actual insufficient space but left 90112 bytes, so only the tail was subsequently filled to zero; the first frontend test command used the wrong directory. The stopped-state verifier initially assumed the schema version would not change. After checking the formal migration receipt and backup, the verifier was corrected and passed without modifying the database or execution records. [Failed schema assumption](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/readback-initial-schema-assumption.log)

This round verifies only plan rejection with an actually full volume, the check before copying, re-export after freeing space, and persistence across reopening. It does not verify space exhaustion during copying, a full system disk, backup failure, storage loss, clean installation, cross-device use, complete migration rollback, or notarized release. The frozen quality plan was not rerun. Local evidence linked from this page is not uploaded with the source repository.
