<a id="039-原生迁移失败回滚与健康备份恢复"></a>

# 039 native migration rollback and healthy-backup restoration

The same fixed company-signed **Ver2.4（039）** completed a controlled empty-library migration failure, automatic reconnection to the healthy library, restoration of a healthy legacy backup, and reopening of the restored library. Actual failure receipts, database bytes, native screens, and stopped readback agree. This is a limited AC-22 subset; full AC-22, M6, M0—M6, and formal release remain incomplete.

<a id="候选输入与范围"></a>

## Candidate, inputs, and scope

The fixed App is signed by Global Cybersecurity Alliance Limited and passed complete signature verification. Executable and packaged control-program hashes remain unchanged. The source commit was `a06aa56715dfe993d5228868d26ad8d94dd2ac4d`; neither the App nor product source was rebuilt or modified.

The actual 039 packaged restoration API first restored the E71 backup into independent healthy library A, containing 8 original resources and 0 attempts. Failure and repair inputs reuse the preserved 006 controlled empty-library backups. Each has schema version 1, 1 database file, 57344 bytes, and 0 referenced assets. The failure package has a conflicting index name; that conflict was previously removed in the repair package's separate copy. Neither input was changed this round, and no old-candidate execution result is reused. This is not a complete failed-upgrade exercise containing historical business tasks. [Preparation result](../../../../.artifacts/m6-migration-ver2-4-039-v1/run-001/result.json) [Input and scope review](../../../../.artifacts/m6-migration039-review-20260920-v1/review.json)

<a id="原生失败回滚及恢复"></a>

## Native failure, rollback, and restoration

The native picker selected the failure backup and this round's independent destination. Restoration completed before an explicit library switch. The actual packaged migration failed because of the index conflict; the UI reported migration failure and reconnection to the original library. The failed library retained schema version 1, with database bytes, business rows, and indexes identical to their preswitch state. Its receipt records `failed_rolled_back` and `committed=false`; the migration backup's hash and original contents were verified. Success was not fabricated, packaged migration code was not replaced, and no model ran. [Stopped failure verification](../../../../.artifacts/m6-migration-ver2-4-039-v1/native-001/fault-readback.json)

The same native restoration entry then selected the healthy legacy backup. Reconnection after failure invalidated the previous destination grant, and the UI requested reselection. Selecting the same directory again allowed inspection, copying, and switching to succeed. The healthy library completed migrations 1→2, 2→3, and 3→4, each with a successful committed receipt and a verified premigration backup hash. Healthy A retained its 8 original resources and original project, commands, and events.

The repaired library then created a single test project through the UI, named “039 遷移回復驗收”. No model, resource, or attempt record was created. Project creation writes directly to the project table and does not register a command. After normal exit, reopening in the same App showed the project again. Database bytes, every table, and the entire migration-backup/receipt tree remained identical. [First-session audit](../../../../.artifacts/m6-migration-ver2-4-039-v1/audit-final.json) [Reopening verification](../../../../.artifacts/m6-migration-ver2-4-039-v1/native-reopen-002/readback.json)

<a id="验证及保留的异常"></a>

## Validation and preserved exceptions

All 51 migration/backup tests passed, with 2 existing warnings. The 50 protected original-data records passed their defined checks: 47 complete records remained unchanged, only selector ctime changed, and 2 startup records updated for this round. The 12 model source files remained unchanged. Both native exits were followed by restoration of the original library selection. Launch monitors and guards exited with code 0; App exit codes remain unknown, and the guard's continuous-lock guarantee remains false. No SQL connection was made to original user databases, and no new training, generation, evaluation, or quantization ran. [Test record](../../../../.artifacts/m6-migration-ver2-4-039-v1/migration-backup-tests.log) [Final protection and signature verification](../../../../.artifacts/m6-migration-ver2-4-039-v1/root-readback.json)

The initial launch check rejected a relative path in the guard command before the App started. The same live guard's command and actual working directory were verified before continuing, without a duplicate guard. A stale UI-element click was rejected; fresh accessibility state was read before submitting. The first audit incorrectly expected project creation to add a command record. Correcting that expectation against the actual API passed. Independent review also retained an initial rejection caused by incorrectly requiring startup records to remain identical, then passed under the predefined allowed-change rules. Original audit scripts and failure logs remain preserved. [Launch rejection](../../../../.artifacts/m6-migration-ver2-4-039-v1/native-launch-rejected.json) [Initial audit failure](../../../../.artifacts/m6-migration-ver2-4-039-v1/audit-initial.log)

<a id="尚未完成"></a>

## Remaining work

Cold-start migration failure still lacks an offline backup-restoration entry. A migration backup containing only a database and receipt cannot be used directly by the current portable-backup restoration UI. This empty-library conflict does not establish failed migration with business data, rollback to an older App, clean-machine installation, or complete capability regression after upgrade. Those gaps, real-device and user acceptance, quality failures, notarization, and formal release remain open. All prototypes, research, and failure evidence are retained; local evidence directories are not uploaded with source.
