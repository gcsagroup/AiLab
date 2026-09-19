<a id="039-真实对象十二项原生导出验收"></a>

# 039 native acceptance of twelve real-object exports

The same company-signed 039 candidate reopened the original 12-export library and added 1 export of an existing controlled dataset split, followed by reopening. Both of the 2 libraries and their export packages remained byte-identical across reopening. The 4 original/revision audio and video files played to the end in an independent player, and the image opened independently. No new model ran; full AC27, M6, and release remain incomplete.

The initial-round record below retains its original state; subsequent results appear at the end.

On 2026-09-20, the same fixed company-signed **Ver2.4（039）** candidate completed 12 native exports of existing real objects. UI completion records, the stopped database, and every file agree. This is limited acceptance of export integrity; full AC27, M6, M0—M6, and formal release remain incomplete. No new training, generation, evaluation, or quantization ran.

<a id="候选与恢复来源"></a>

## Candidate and restoration source

The fixed App is signed by Global Cybersecurity Alliance Limited. Executable and control-service hashes remain unchanged, and complete signature verification passed after shutdown. The source commit was `f7066c99ad248fb1ca6b5b6290e405135e940cc2`; this round did not rebuild or modify product source.

The actual 039 packaged restoration API restored a historical complete backup into a new independent library. The backup contains 733 content files totaling 9345059951 bytes, with all hashes matching before and after restoration; no SQL connection was made to original libraries. The new library initially contained 507 resources and 31 terminal attempts, including existing real models, adapters, works, and a failed quality report. [Formal restoration record](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/run-001/result.json)

Native startup migrated the new library from schema version 3 to 4. The formal migration backup had a different byte hash from the prelaunch database, so the first independent audit refused to continue instead of assuming equivalence. A stopped, read-only connection was then made only to the migration backup inside this round's new library. Its structure and every table matched the complete prelaunch version 3 business contents. The migration receipt and actual backup hash were also verified, and the final audit passed. The initial failure log remains preserved. [Initial rejection](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/audit-initial.log) [Migration backup verification](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/migration-snapshot.log)

<a id="原生导出范围"></a>

## Native export scope

| Object | Exports | Content files |
| --- | --- | --- |
| Original and 4-bit models | 2 | 10 + 13 |
| Text and image LoRA adapters | 2 | 3 + 3 |
| Original text, image, video, and speech works | 4 | 3 + 3 + 3 + 3 |
| Text, speech-script, and video-subtitle revision 2 | 3 | 4 + 4 + 4 |
| Existing evaluation execution report | 1 | 11 |

The total is 12 exports, 64 content files, and 12 manifests. Each scope was checked in the native UI before explicitly starting export and saving the completed screen; all used the same independent acceptance directory. Adapter packages exclude base models, with exact-base and MLX／Diffusers environment requirements retained in the UI. Original works export original outputs, revisions remain fixed to the selected revision, script edits do not change speech audio, and video subtitles remain separate files. [UI and object verification](../../../../.artifacts/m6-export039-native-ui-review-20260920-v1/review.json)

Independent UI review passed 147 checks. The 24 scope/completion records map to unique new exports. The UI does not directly expose every complete version identifier; review followed each completion ID to its persisted plan to verify project, object, and version. The stopped snapshot contains 48 new resources: 12 each of plans, exports, tasks, and attempts. New model attempts total 0. The original 507 resources, projects, commands, and events remain unchanged; first-launch UI setting changes are recorded separately. [Complete independent audit](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/audit-final.json)

<a id="文件可读性与质量边界"></a>

## File readability and quality boundaries

Independent audit checked the complete file set, regular-file types, sizes, individual SHA hashes, manifest identity, object versions, recipes, and external dependencies. The original backup and 732 original asset payloads remain unchanged. The auditor passed 20 miniature tests, including corrupt files, extra model attempts, and rejection of SQL/process/network calls. Those tests use temporary fixtures; actual-object auditing was performed separately. [Auditor tests](../../../../.artifacts/m6-export039-independent-audit-20260920-v1/selftest-result.json)

The 7 work packages passed independent text reading and complete image/audio/video decoding. Revised text and subtitles are readable, and original media remain unchanged. Media checks use ffprobe and ffmpeg decoding; they do not establish actual player playback, human listening, or semantic quality acceptance. The original report remains `failed`, `eligible=false`, and `prospective_plan_bound=false`; successful export does not improve the candidate's quality conclusion. [Reading and decoding](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/media-readback.json)

<a id="停机保护与剩余工作"></a>

## Shutdown protection and remaining work

The App exited normally through its native quit menu and confirmation dialog. Both launcher and guard exited with code 0; the App's own exit code was not independently obtained and remains unknown. Original library selection was restored. The 47 protected records, 12 model source files, and the previous 039 independent library remain unchanged against this round's frozen starting state. No SQL connection was made to original user libraries. [Root verification and protection](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/root-readback.json)

Host full readiness took approximately 16.81 seconds, with an external observation of 17.06 seconds. This does not measure initial main-window visibility or prove the 20-launch, 3-second target. This round's newly exported records have not yet been reopened in the same library; earlier reopening evidence from other restored libraries cannot replace this result. [Startup and normal-exit receipt](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/native-001/startup/report.json)

Remaining work includes dataset-split export, reopening this library, actual independent use of model packages, media playback, and other frozen acceptance items. No new model ran, and historical 003 independent-use results are not counted as 039 results. The complete installation/upgrade/failed-migration rollback chain, clean-account acceptance, notarization, and formal distribution remain pending. Full AC27 and M6 remain unaccepted.

This record and all formal documentation are available in Simplified Chinese, Traditional Chinese, and English. Raw evidence, model weights, and databases remain local; evidence links do not mean these files were uploaded to GitHub with the source.

<a id="后续同库重开数据划分与独立媒体"></a>

## Follow-up: reopening, dataset-split export, and independent media

The initial-round status above is retained. The same fixed company-signed 039 App subsequently reopened the twelve-export library. Native history showed all 12 completed exports, and the original report-export details opened. After normal exit, database bytes, every table, settings, and the export directory were identical to the first shutdown, with no new attempts. [Twelve-export reopening verification](../../../../.artifacts/m6-all-exports-ver2-4-039-v1/native-reopen-002/readback.json)

The actual 039 packaged API also restored the E71 formal backup into a separate new library. All hashes of its 13 content files totaling 11593895 bytes remained unchanged. The new library had schema version 4, 8 original resources, and 0 original attempts. This case uses controlled 7-line data previously checked by an actual CPU tokenizer. Its accompanying model is only a 92-byte file containing a 4-byte tensor fixture and cannot run; the model is excluded from export. This round did not repeat tokenization, splitting, application, or training. [Restoration record](../../../../.artifacts/m6-split-export-ver2-4-039-v1/run-001/result.json)

The existing split was inspected in the dataset market, then explicitly exported after native scope preview. Its 7 content files total 21880 bytes, plus 1 manifest, covering the original, training/validation subsets, check report, per-line evidence, split manifest, and object description. Of the original 7 records, 6 are accepted and 1 excluded. Training contains 5 records in 4 groups; validation contains 1 record in 1 group. Seed 7 and maximum length 512 remain fixed. Per-line content and order are preserved, with no source group crossing subsets. Semantic near-duplicates remain unchecked, validation loss has not run, and repeating tokenization requires the original fixed tokenizer. The file-only auditor passed 12 representative tests and actual-file checks. Its initial miniature test rejected a symbolic-link ancestor in the temporary path; rerunning with the resolved real temporary path passed, retaining the initial log. [File and source verification](../../../../.artifacts/m6-split-export-ver2-4-039-v1/file-audit.json) [Independent review](../../../../.artifacts/m6-split039-review-20260920-v1/review.json)

The first round added only 4 resources: a plan, export, task, and 1 successful export attempt. The 8 original resources, original project, commands, and events remained unchanged. Independent business/UI review passed 53 checks. Reopening the split library with the same candidate displayed the original export ID, path, and successful state. Database bytes, every table, and the export package remained identical; independent reopening review passed 12 checks. [Business review](../../../../.artifacts/m6-split039-review-20260920-v1/actual-native-review.json) [Reopening review](../../../../.artifacts/m6-split039-review-20260920-v1/actual-reopen-review.json)

Original library selection was restored after each session. The 48 protected records, 12 model source files, 12 restored asset payloads, formal backup, and previous independent libraries remain unchanged. Launchers and guards exited with code 0; App exit codes remain unknown. Guard receipts retain a false continuous-lock guarantee, so uninterrupted locking is not claimed. After clicking the native quit confirmation in the first split session, the UI tool connection closed. A subsequent native App inventory showed the App stopped, and the launch monitor and process query confirmed both App and control service had stopped. The error and follow-up observations remain preserved. [Root protection verification](../../../../.artifacts/m6-split-export-ver2-4-039-v1/root-readback.json) [Quit-tool record](../../../../.artifacts/m6-split-export-ver2-4-039-v1/native-001/quit-tool-error.json)

Independent media validation used the files actually exported in this round. The original video and video inside the subtitle-revision package each advanced from playing to the 2-second endpoint in QuickTime. Original speech and audio inside the script-revision package each reached the 8.05-second endpoint. All 4 files have exact-path, playing, and ended receipts. The image opened independently in Preview, visibly showing a blue cup, with its file hash unchanged. The media receipt checker passed 4 representative checks. Tool observations of not-yet-enabled file-selection buttons, no window after closing Preview, and an Open dialog after a quit request are retained. Fresh inspection and closure followed; the final process check found no QuickTime, AiLab, or control-service process. [Independent media results](../../../../.artifacts/m6-media-native039-v1/readback.json)

These player observations do not establish human listening, semantic quality, or subtitle-overlay acceptance, and do not change historical quality failures. Host/external full readiness for the twelve-export reopening was approximately 8.23／8.48 seconds. The split sessions took approximately 4.12／4.17 and 4.15／4.33 seconds; none establishes initial-visibility performance. Independent loading of model packages, the complete installation/upgrade/failed-migration rollback chain, clean environments, and other frozen gates remain pending. Full AC27, M6, M0—M6, and release status are not advanced.
