<a id="039-真实对象十二项原生导出验收"></a>

# 039 native acceptance of twelve real-object exports

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
