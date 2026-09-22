<a id="m6-业务库恢复与冷启动错误修复"></a>

# M6 business-library recovery and cold-start error fix

This round advances M6 and updates the fixed company-signed candidate to **Ver2.5（042）**. Failed migration with historical business records, restoration, text re-export, and reopening were exercised on 040. Candidate 042 preserves the original cold-start error when fallback also fails and separately passed native message verification. Full AC-22, M6, and formal release remain incomplete.

<a id="历史业务恢复实机证据"></a>

## Native historical-business recovery evidence

An existing complete schema-version 3 portable backup was restored to an isolated directory through the actual 040 packaged API. The input contains 2 projects, 507 resources, 31 historical attempts, and 733 backup files. This round executed no new models and made no SQL connections to original user libraries.

Only the isolated restored copy received `CHECK(version<=3)` on its version table, causing the actual 3→4 migration to fail. Business rows remained intact, the receipt reports `failed_rolled_back` without committing, and database bytes match the post-injection baseline. This is a controlled constraint fault, not observed customer corruption or a modified product migration implementation.

The native UI selected the same healthy backup, restored it into another new directory, and explicitly switched libraries. Confirming Quit through the native menu while restoration was busy was rejected and restoration continued. Historical projects and works became visible afterward. Stopped readback verified 732 original payload files against backup hashes and preserved existing business rows.

Re-exporting an existing text work through its ordinary UI added 4 resources, including only 1 export attempt. After normal exit, reopening, and another exit, the restored database and export files remained identical. The original library selector object and bytes were restored; 47 of 50 protected records remained fully unchanged, allowing selector rename metadata and updates to 2 startup receipts.

The first process monitor retains its failure from a guard heartbeat time check; the second reopening monitor completed. Stopped data and selector restoration were checked separately. The failed monitor is not relabeled as successful, and neither continuous locking nor a known App exit code is claimed. [040 business recovery evidence](../../../../.artifacts/m6-20260923-v1/business-001/root-readback.json)

<a id="冷启动错误修复与候选"></a>

## Cold-start error fix and candidate

Previously, after the selected library failed migration, the default library could not start because the acceptance guard held its lock; the UI showed only the later invalid-startup-response error. The fix retains both migration and fallback causes consistently in command responses and polled status. A healthy selected library does not trigger fallback, and the same directory is not started twice. This default-library lock conflict was caused by data protection and does not establish default-library corruption.

Before the fix, all 648 frontend tests, 1147 backend tests, and 84 host tests passed; 5 backend warnings remain. The fix adds 3 host regressions: afterward 87 host tests passed and 3 environment-dependent tests were skipped. An explicitly enabled host migration-rollback test using the actual packaged control service also passed, 1 test. An initial new-test field mismatch caused compilation failure and was corrected. Repository-wide formatting checks also reported existing formatting differences; unrelated files were left unchanged.

The 041 native check confirmed both error causes but direct Quit was incorrectly blocked: it tried to save selections although the library had never loaded. That failure remains recorded; normal exit required first entering an idle recovery session. Version 042 skips empty saves only for failed cold starts without loaded projects, selections, or tasks; disconnection after loading a project remains protected. There are 2 new regressions, with all 650 frontend tests and 16 targeted tests passing.

Verified rollback archives preserve both 040 and 041. Candidate 042 completed a unique build at the fixed path, frozen-source verification, and company-signature checks. The 042 native cold start displayed migration and fallback failure causes and exited normally without entering recovery. Stopped readback checked fault-library business records, the original selector, and protected data. This did not rerun the entire business restoration or quality evaluation. [042 package verification](../../../../.artifacts/integration-ver2-5-042-v1/root-frozen-check.json) [042 native verification](../../../../.artifacts/m6-20260923-v1/native042/root-readback.json)

The first 042 monitor observed a second App instance after Quit and retains `failed_preserved`. Rounds are not combined, and unverified short-lived processes are not treated as verified. After stopping the current instance, a separate round checked only processes after Quit; monitoring completed with no new recovery session. The trigger for the second instance was not independently established; the first failure remains a failure.

<a id="042-恢复库十二项重新导出"></a>

## Twelve re-exports from the restored library on 042

The same company-signed 042 package selected and exported 12 historical objects through ordinary native entries in the healthy restored library: original text, image, video, and audio works; text, video, and audio revisions; the original model and MLX 4-bit quantized model; text and image LoRAs; and the original evaluation report. This round did not migrate again: the library remained at version 4, with no new model training, inference, or evaluation.

Object versions, source recipes, dependencies, export plans, and frozen snapshots were checked individually, along with all 64 payload files and 12 manifests. Resources increased from 511 to 559, adding exactly 12 plans, 12 tasks, 12 export attempts, and 12 export records; existing projects, resources, events, and idempotency records were preserved. Sizes and hashes matched for all 733 original backup files and 732 restored payload files.

Text and subtitles in 7 work packages were independently readable, and images, audio, and video passed complete decoding; the evaluation report retained its quality failure. This step did not perform playback or human quality assessment, nor independently run models or adapters. Adapter packages explicitly exclude their base models, and the two adapter types require matching MLX／Diffusers environments respectively; the manifest field `independent_use=not_verified` remains unchanged.

After normal exit and reopening the same library, the UI showed all 12 exports complete, while the failed evaluation remained failed and candidate registration unavailable. After another exit, database bytes, all business rows, and the export tree were identical to the first shutdown. Both separate process monitors completed, establishing only process lifecycle; neither a known App exit code nor continuous locking is claimed. The original selector object and bytes were restored, 47 protected records remained fully unchanged, and 14 lock-release probes passed. The existing fault library and model sources were unchanged, with no new recovery session.

The independent file auditor passed 19 positive and negative tests, and the process monitor passed 45 tests; the actual export packages from this round were also verified. Auditing makes no SQL connections and launches no App or model; stopped-database readback runs separately under a lock in the isolated restored library. Preparation initially required full path fields to match a different restored library; this was corrected to verify fixed object identities first and then freeze this library's complete records. The reopening closeout script initially used an incorrect monitor-report filename and passed after correction. These two tooling errors are not product failures and do not erase earlier acceptance failures. [042 twelve-export and protection verification](../../../../.artifacts/m6-20260923-v1/exports042/root-readback.json) [Export content audit](../../../../.artifacts/m6-20260923-v1/exports042/first-export-audit.json) [Reading and decoding](../../../../.artifacts/m6-20260923-v1/exports042/media-readback.json)

<a id="m6-仍需关闭的条件"></a>

## Remaining M6 gates

- Complete clean installation, update and old-App rollback, every applicable export after upgrade/restoration, long-task and network-fault checks, and UI/performance regression on the same final candidate.
- Validate actual NVIDIA Linux hardware and the same LoRA through NVIDIA→Apple; existing training, quantization, and media quality failures remain.
- Have 5 actual target users complete their first result, save it, and resume after restart from zero resources; participants and device details are still pending.
- Confirm the distribution channel and complete its signing, notarization, and independent-installation acceptance; a company signature is not notarized release evidence.

This round did not lower acceptance criteria or count developer operations as target-user tests. All prototypes, research, failure evidence, and old candidates remain preserved; local evidence is not uploaded with source.
