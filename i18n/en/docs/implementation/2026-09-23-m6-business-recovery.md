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

<a id="固定路径实际更新与旧包回退"></a>

## Actual updates and old-package rollback at the fixed path

Complete company-signed archives of 040 and 042 were retained, and 040→042→040→042 was actually exercised at the same fixed App path. Preparing the old installation first preserved the current 042 object, then placed a fully verified 040 clone at that path; this is acceptance setup, not product rollback. The subsequent two upgrades and intervening rollback used the unmodified production update tool, without bypassing signature, plan digest, version, or database compatibility checks.

The four native launches displayed 040, 042, 040, and 042 respectively. Each read the original failed evaluation and the existing 12-export history, then exited normally through native confirmation. After every shutdown, database bytes and all business rows matched the initial state: 559 resources and 44 historical attempts were retained, with 0 new attempts. The fixed path ended on 042, with its main executable, control executable, and full package matching the frozen candidate; the original current package, archives, and packages retained by update transactions were preserved.

Both transaction database backups passed integrity, schema-version, and complete business-row checks, and their file hashes matched their receipts. These backups contain the database and library selection, excluding payload files. Separately, all 733 original full-backup files, 732 restored payload files, and the existing 12 export packages remained unchanged. This round only inspected existing exports; it did not re-execute every export after updating, and package replacement on the same machine is not clean-machine installation.

All 27 update contract tests passed, as did 45 tests for each of the 040 and 042 monitors. The initial preparation script compared all version-object fields too strictly and passed after correction. The first monitor rejected a guard launched with a relative script path before starting the App; that failure is retained. The original guard was released normally, and a separate round used an absolute path. The subsequent four process monitors completed, proving only each round's process lifecycle, without claiming App exit codes or continuous locking.

Finally, the original library selector object and bytes were restored, 47 protected records remained fully unchanged, and 14 lock-release probes passed. Model sources and the existing fault library were unchanged, with no new recovery sessions, model executions, or SQL connections to original user libraries. Actual local updating and compatible old-package rollback are complete as subitems; clean installation, distribution-channel acceptance, and full AC-22／M6 remain incomplete. [Update, rollback, and protection verification](../../../../.artifacts/m6-20260923-v1/update042/root-readback.json)

<a id="更新后重新导出与独立使用"></a>

## Post-update exports and independent use

After the actual updates and rollback above, the same fixed 042 package and healthy restored library exported the same 12 historical objects again through the ordinary native interface. Independent checks verified versions, sources, dependencies, recipes, and hashes for 64 payload files and 12 manifests. Resources increased from 559 to 607 and historical attempts from 44 to 56, with every addition belonging to exports. Original projects, resources, events, idempotency records, and quality failures were preserved; exports were not counted as model runs.

With the App stopped, the new export mapping, complete 042 package, and exact base dependencies were frozen. Execution outside the library was limited to 3 short text generations and 1 image generation, without training or rerunning quality evaluations. The original model, MLX 4-bit model, and old text LoRA each loaded independently and actually used the Apple GPU. Each returned `4` for the fixed short question, generated 2 tokens, and exited normally. This establishes loading and generation for these 3 exports only; it does not overturn the previous quality failures.

The image LoRA used its exported adapter and the exact TinySD base explicitly excluded from the package. It generated at 512×512 with MPS and 20 steps, and the main process exited with code 0. The image and execution-recipe hashes could be verified. However, the acceptance helper observed a remaining process in the group and sent SIGTERM for cleanup. No forced kill was needed; the PID and process group were ultimately absent. The strict exit check therefore failed, and the original receipt is retained. No model was rerun to replace the failure; subsequent work only read back the existing image, parameters, loading identity, unchanged inputs, and released processes. The cause is not asserted to be either a product defect or a harmless race, and this image independent-use case is not marked as an overall pass.

Text, revisions, and subtitles from 7 work packages were independently readable, and images, audio, and video passed complete decoding. QuickTime actually played 4 audio/video files from original and revision packages, with playback states and endpoints of 2 seconds／8.05 seconds observed. The original and newly generated images were viewed. Revised text, voice scripts, and external subtitles remain separate; original media was not regenerated. Playback does not establish human listening quality, motion quality, or external-subtitle rendering acceptance. Export manifests retain their original `independent_use=not_verified` declaration.

After independent execution, reopening 042 showed all 12 new exports. The old evaluation still failed and candidate registration remained unavailable. Database bytes and business rows matched across both shutdowns, and both export trees were unchanged. The complete 042 package, new exports, and exact model dependencies were also preserved. Finally, the original selector object and bytes were restored, 47 protected records remained fully unchanged, and 14 lock-release probes passed. Model sources, the fault library, and recovery sessions were unchanged. The independent-use helper made no database connections; shutdown readback accessed only the isolated restored copy.

All 19 positive/negative file-auditor cases and 45 process-monitor tests passed; generation stayed within this round's fixed count. Post-update re-export, independent loading of 3 text exports, and media playback subitems are complete. Image process exit, full AC-22／AC-27, and M6 remain open. [Post-update exports and protection](../../../../.artifacts/m6-20260923-v1/postupdate042/root-readback.json) [Independent use and retained failure](../../../../.artifacts/m6-20260923-v1/postupdate042/independent-001/readback.json) [Native media playback](../../../../.artifacts/m6-20260923-v1/postupdate042/playback.json)

<a id="图片退出观察器修正后的独立复验"></a>

## Independent image rerun after correcting exit observation

The previous helper checked and cleaned up same-group children immediately after the main process exited, without a natural-exit observation window. The revised observer waits at most 2 seconds and records group members. It passes only when the main process succeeds, the group disappears naturally, and no cleanup signal is sent. Persistent processes, timeouts, and nonzero exits still fail; disappearance after cleanup is not counted as natural exit. All 5 real-subprocess tests passed without loading models.

A separate no-model pipe probe used the fixed 042 bundled resource tracker. Its child remained briefly after the parent exited, then disappeared naturally after approximately 0.113 seconds without cleanup signals. This demonstrates that an immediate check can be premature. The previous image run did not record member identities, so this experiment cannot establish that run's cause or rewrite its failed receipt.

A separate, single-image rerun then froze the same complete 042 package, new export, exact TinySD dependency, and script hashes, with a budget of 1 generation, 0 training runs, and 0 quality reevaluations. The image LoRA generated with the same MPS, 512×512, 20-step recipe. This run's main process exited with code 0, its group was already absent at main-process exit, and neither SIGTERM nor forced termination was used. The image was fully decoded and viewed. Models, adapter, exports, database, and original protected records remained unchanged. This new independent-use run passed while the old failure remains retained. The product package was neither modified nor rebuilt, and model quality, full AC-22／AC-27, and M6 are not promoted. [Single-image rerun](../../../../.artifacts/m6-20260923-v1/image-exit042/image-001/report.json) [No-model process observation](../../../../.artifacts/m6-20260923-v1/image-exit042/tracker-probe/tracker.process.json)

<a id="042-包内导出异常路径回归"></a>

## Export failure-path regression in the 042 package

To avoid inheriting conclusions from packages 037—039, this round actually launched the same fixed 042 packaged control service for HTTP regression in isolated synthetic-file libraries. The complete candidate, main executable, and control executable were verified first. No models ran, no SQL connected to original user libraries, and the product package was unchanged. Synthetic files establish file-export behavior only; they are not runnable-model or model-quality evidence.

A controlled database rejection targeted only final registration of the selected export, producing files on disk without successful registration. After stopping the service, separate cases introduced a manifest symlink, dangling link, directory symlink, named pipe, missing payload, same-size content mutation, and wrong object version. All 7 negative cases failed reconciliation after restart; 1 unchanged-file control recovered registration successfully. A fresh export then passed file-set and hash checks. Records for the 9 attempts survived restart and formal backup/restore. Mutated packages and removed original files were retained. This injected a registration failure, not an operating-system process crash.

Cancellation used a 512 MiB synthetic payload. After 4 MiB had actually copied, the official cancellation endpoint received the request. The service confirmed cancellation, retained the partial package, and published no final package; a newly prepared export then succeeded. Disk exhaustion used an isolated 64 MiB volume and 32 MiB synthetic payload. After 4 MiB copied, this round's owned service was paused, the test volume was filled, and copying resumed. The operating system returned ENOSPC and the partial package remained failed. Releasing only the test filler allowed a new export to succeed. Both failed and successful packages were copied out and verified, and the test volume detached normally. Each group contained 2 accepted attempts, with database and export records preserved after restart. The three groups totaled 13 accepted export attempts and 0 new model runs.

The first two cancellation-tool rounds failed before sending cancellation: one read a field absent from the public response, and the other assumed the wrong temporary-directory name. Their records and test files are retained and are not counted as cancellation passes. After using two actual public responses, 8 path-identity positive/negative cases passed, and cancellation was verified in a separate round. The disk-full helper initially failed to import because it calculated directory depth incorrectly, before any service or volume was created. After correction, 7 tool-boundary tests and the real-volume test passed. The directory-entry helper also ran self-checks with real links, pipes, removed files, and byte mutations.

Final independent checks verified all mutated, partial, and successful packages. Original protected records, model sources, and the historical restored business database were unchanged. All 14 lock-release probes passed and this round's services stopped. These results close packaged HTTP failure-regression subitems for 042 only. This round did not trigger the failures through native UI or repeat every fault combination for every real historical object type; it does not establish full AC-27, AC-22, or M6. [042 export-failure verification](../../../../.artifacts/m6-20260923-v1/export-faults042/root-readback.json)

<a id="m6-仍需关闭的条件"></a>

## Remaining M6 gates

- Complete clean-machine installation and update/rollback on the same final candidate, then finish all applicable post-upgrade exports, independent use, long-task and network-fault checks, and UI/performance regression.
- Validate actual NVIDIA Linux hardware and the same LoRA through NVIDIA→Apple; existing training, quantization, and media quality failures remain.
- Have 5 actual target users complete their first result, save it, and resume after restart from zero resources; participants and device details are still pending.
- Confirm the distribution channel and complete its signing, notarization, and independent-installation acceptance; a company signature is not notarized release evidence.

This round did not lower acceptance criteria or count developer operations as target-user tests. All prototypes, research, failure evidence, and old candidates remain preserved; local evidence is not uploaded with source.
