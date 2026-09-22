<a id="gcsa-ai-lab"></a>

# GCSA AI Lab

[简体中文](../../README.md) · [繁體中文](../zh-TW/README.md) · [English](README.md)

A local-first desktop workbench for model training and inference. Organize models, data, training tasks, evaluations, and works by project, with workflows for language, images, video, and voice-over.

<a id="当前状态"></a>

## Current status

The current fixed company-signed candidate is **Ver2.5（042）**, signed by **Global Cybersecurity Alliance Limited**. It is a development candidate; full M0—M6, clean installation, notarization, and formal distribution acceptance remain incomplete.

The current company-signed candidate is Ver2.5（042）, with fixes for error retention and quitting after failed cold starts. Historical-library recovery, fixed-path 040→042→040→042 update/rollback, 12 post-update exports, and reopen checks are complete; the restored library retains 607 resources and 56 historical attempts. Independent generation succeeded for 3 text exports and the image LoRA in their respective runs, and 4 audio/video files played to their endpoints. The first image exit-check failure is retained; a separate run with improved observation exited naturally. Full M6, NVIDIA, model quality, 5-user acceptance, clean installation, and distribution acceptance remain incomplete. [Business recovery and delivery progress](docs/implementation/2026-09-23-m6-business-recovery.md)

The company-signed Ver2.5（040） candidate passed native cold-start recovery with controlled empty libraries: failed switching returned to the recovery workspace, and healthy-backup migration, project persistence, and same-library reopening passed with the database and migration receipts preserved. The initial reopen process-monitor failure is retained; revalidation with the improved tool passed. No new models ran. Subsequent native checks confirmed that exiting without switching and reopening kept the original failed library selected, created a new recovery session, and preserved restored directories. Monitor and guard contract failures remain retained; independent stopped-state auditing passed. Failed upgrades containing business data, full AC-22／M6, notarization, and formal release remain incomplete. [Cold-start recovery acceptance](docs/implementation/2026-09-20-cold-start-recovery-source-progress.md)

The same company-signed 039 candidate completed controlled empty-library native migration rollback, healthy legacy-backup restoration, and reopening. Healthy A retained 8 resources; the repaired library passed migration 1→2→3→4 and test-project reopening. All 51 migration/backup tests passed, with no model runs. Cold-start offline restoration, failed upgrade with business data, and full AC-22/M6 remain pending. [Migration recovery acceptance](docs/implementation/2026-09-20-ver2-4-039-migration-recovery.md)

The same company-signed 039 candidate reopened the original 12-export library and added 1 export of an existing controlled dataset split, followed by reopening. Both of the 2 libraries and their export packages remained byte-identical across reopening. The 4 original/revision audio and video files played to the end in an independent player, and the image opened independently. No new model ran; full AC27, M6, and release remain incomplete. [Twelve-export acceptance](docs/implementation/2026-09-20-ver2-4-039-twelve-exports.md)

The fixed company-signed 039 candidate includes the export directory-entry fix. Its actual packaged service rejected 4 invalid entry types, recovered a valid interrupted package, and completed a fresh export. Native inspection of failed and successful records, normal exit, and reopening of the formally restored library passed. No new models ran; full AC27, M6, M0—M6, and release remain incomplete. [039 acceptance and boundaries](docs/implementation/2026-09-16-export-tree-integrity.md)

The following records retain their state when written.

Subsequent source fix: the actual packaged 038 service still incorrectly accepts a symbolic link for the manifest; negative evidence is retained. Source now rejects manifest links, dangling links, directory links, and special files, with 186 related regressions passing. This is not yet included in a new signed candidate; full M6 and release status do not advance. [Directory-entry fix and negative evidence](docs/implementation/2026-09-16-export-tree-integrity.md)

The fixed company-signed 038 candidate includes the complete export manifest identity fix. Rejection of an incorrect version after controlled registration failure and a successful new export passed in the packaged service, followed by native inspection, normal exit, and reopening of the formally restored library; the database was entirely unchanged after the second shutdown. No new model runs occurred; full M6, M0—M6, and release remain incomplete. [038 acceptance and boundaries](docs/implementation/2026-09-16-ver2-4-038-export-identity.md)

The following records retain their state when written.

037 verified native disk-full rejection before copying and recovery, plus preservation of failure and recovery export after actual mid-copy volume exhaustion in the packaged service. Native history inspection and reopening after formal backup and restoration also passed; original failed and successful records and files remain unchanged, with no new model runs. The mid-copy fault was still triggered through HTTP, and the synthetic fixture does not establish model capability. Full M6, M0—M6, and release remain unpassed. [037 disk-full recovery acceptance](docs/implementation/2026-09-16-ver2-4-037-storage-recovery.md)

The same signed 037 candidate completed actual admission rejection, native report export, and reopening for an existing failed evaluation. All 11 payload files and 60884 bytes passed individual checks; 52 original resources remain, with 4 export resources added and 0 new model runs or evaluations. The quality failure remains; full M5, M0—M6, and release remain unpassed. [037 quality report acceptance](docs/implementation/2026-09-16-ver2-4-037-quality-export.md)

The same signed 037 candidate completed explicit workflow reuse, saving all three works, invalidation after upstream changes, and same-library reopening. The original 507 resources were preserved, with 14 new resources and 9 commands; model attempts and training runs were both 0. A subsequent controlled-occupancy fixture verified unchanged contents in all six tables after native rejection, followed by formal reconciliation, one advancement, and persistence across reopening; real execution races, quality, and full M4 acceptance remain pending. [037 workflow acceptance](docs/implementation/2026-09-16-ver2-4-037-workflow-reuse.md)

The fixed company-signed 037 candidate passed native offline registration and application of downloaded data: a real 292-byte download containing 2 rows was registered and applied to the original task after the provider stopped and the market reopened. Draft revision changed from 2→3, only the dataset changed, and seed 817 was preserved. Normal exit, stopped-library readback, and original-data restoration passed; full M4, M0—M6, and release remain unpassed. [037 native offline acceptance](docs/implementation/2026-09-16-market-offline-downloads.md)

The following source-stage records retain their state when written.

The fixed company-signed 036 candidate includes the official-model runtime-boundary fix. Package checks and limited native notice acceptance passed: official-catalog and local-inspection explanations were visible, with 1 project/1 import plan and no download, import confirmation, or model execution. Normal exit and original-data protection/restoration passed; full M2 and release remain unpassed. [036 notice acceptance](docs/implementation/2026-09-16-official-model-runtime-boundary.md)

The following source-stage and earlier-candidate records retain their state when written.

The 035 packaged worker completed one real generation under process network denial, producing `7`; the rejection matrix for unsupported media/cache requests is published (E146). This does not establish physical disconnection, a product OS sandbox, or cache-hit performance. Real HTTP cancellation and subsequent generation recovery through the packaged control service also passed, without App UI acceptance in this round; M2 and release status are not advanced. [Runtime boundaries and evidence](docs/implementation/2026-09-16-ver2-4-035-runtime-boundaries.md)

The fixed company-signed 035 candidate received limited acceptance for real local inference and same-library reopening on Apple M5 Max (E145): import trust and persisted boundaries, preset cancellation/application, rejected50+79/allowed50+78 budgets, auto512/stop39/stream=false→text7, saved work, and an unexecuted recipe draft are evidenced. There was 1 attempt and 0 training; 15 resources/4 commands/13 events/6 artifacts and31 file hashes remained unchanged, both App exits were normal, and47/44 protection records plus12 source-model files passed restoration checks. The original guard exit1, rejected launch, and interrupted locking remain recorded; M2, full AC, M0, M2—M6 and release status are not advanced. [035 inference and reopening evidence](docs/implementation/2026-09-16-ver2-4-035-native-inference.md)

The following source and candidate paragraphs retain their state when written; “035 not built” does not describe the current candidate.

Source progress: model import now explains loading trust and permissions, including fixed loaders, rejection of custom code, and limits of a same-user process. Offline options and credential environment allowlists do not provide operating-system isolation. The backend passed 40 tests and the frontend 46, with type checking passing. The fixed App remains 034 without these changes; 035 is not built and native acceptance is pending. [Model import trust boundaries](docs/implementation/2026-09-16-model-import-trust-boundary.md)

The fixed company-signed 034 package and native collection roundtrip received limited acceptance (E144): recovery after a real interruption in a new fixture-executor library, collection-only retry, saving a short text work, and same-library reopening. The original failure remains, with no new attempt or model execution. Resources 7→10, 2 commands/3 events, both normal exits, and 47/44 protection restoration passed. The M1 application and data foundations stage passed (contract and UI subsets); full AC, M0, M2—M6, and release remain unpassed. [034 collection recovery and stage evidence](docs/implementation/2026-09-16-ver2-4-034-collection-recovery.md)

The following source-stage, E143, and earlier records retain their state at the time.

Source progress: fixes recover manual collection stuck in collecting after interruption and cover computation finishing first, failed-exit records, and stop-signal errors. The final integrated regression passed 221 tests. The fixed signed App remains 033 and does not contain these changes; no 034 build has occurred, and complete M1 and release status do not advance. [Collection recovery and source limits](docs/implementation/2026-09-16-collection-recovery-source-progress.md)

The fixed company-signed 033 package and native dataset workflow received limited acceptance (E143): three import rejections, 7-row import, source splitting, successful configuration checking followed by length invalidation, and direct draft restoration in the same library. Stopped-state checks found 12 new resources, 3 commands, 0 attempts, and draft revision 5; both normal exits and 47/44 protection restoration passed. No training or model generation occurred; complete M1, M0—M6, and release status do not advance. [033 dataset workflow and limits](docs/implementation/2026-09-16-ver2-4-033-dataset-workflow.md)

The following source-stage, E142, and earlier records retain their state at the time.

Pre-build source progress: stale dataset-split reads no longer clear apply errors, and failed manual-collection registration can preserve the computation result and allow retries after recovery. Related source tests and browser component fixture checks passed. The fixed App remains 032; 033 has not been built, and this round’s native dataset workflow has not run. [Source fixes and limits](docs/implementation/2026-09-16-dataset-and-collection-source-fixes.md)

032 passed keyboard operation of the subtitle functional flow, continuing/discarding edits, saving v5, and reopening the same library. Only the final cue changed across 200 cues/16000 characters, followed by explicit export of the 5-file historical v4 package. Current v5, historical v4, and the original video remained intact; both normal exits and data restoration passed. Rendering was sampled through container scrolling, and the old 020 cause remains unknown. No rebuild or model execution occurred; full AC and release status do not advance. [Subtitle workflow and limits](docs/implementation/2026-09-16-ver2-4-032-subtitle-workflow.md)

The following E141 and earlier records preserve their state at the time.

032 passed complete diagnostic-directory regression: actual trilingual data import, both cancellation actions, ZIP saving to a directory with Chinese characters and a space, and integrity/redaction verification. Database and ZIP bytes remained unchanged after reopening the same build and library. Both normal exits and data restoration passed. Automatic probing was nonzero; no model ran. This diagnostic success does not replace complete artifact-export or release acceptance. [Diagnostic regression and limits](docs/implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md)

The following E140 and earlier records preserve their state at the time.

032 passed limited native acceptance for selecting the original Python symlink path, saving all three environments, reopening the same build and library, and restoring bundled environments. Both stopped-state readbacks and original-data protection restoration passed. External venv dependency-probe failures remain recorded; bundled-environment readiness does not establish model execution. Native cross-library races and diagnostic export remain uncovered. [032 progress and limits](docs/implementation/2026-09-16-ver2-4-032-python-path-preservation.md)

030 includes the library connection-isolation fix in the signed package. Source regressions, complete-bundle verification, and two packaged real-control tests passed; root acceptance covers the limited native subset of backup, rollback after target-library startup failure, successful switching, and reopening the same build, with stopped-state readback passed. Old requests after a switch, rollback, or restart are not automatically resent with the new library identity. Asynchronous native-picker races remain uncovered. [030 progress](docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md)

Evidence covers the source fix for the three Media import entries, related tests, and Safari verification. Root acceptance now covers the 029 company-signed package and the limited subset of four native entry instances in two existing tasks, normal exit, and one stopped-state readback (E137). No real import or model run occurred. The existing limited acceptances for the four Workbench buttons in 028 and keyboard-only original-text export and reopening the same task in 027 remain in place. See the [current delivery matrix](docs/implementation/2026-09-10-current-delivery-matrix.md) and [changelog](CHANGELOG.md).

<a id="功能与范围"></a>

## Features and scope

- **Language models**: generation, SFT + LoRA, checkpoints, evaluation, and candidate admission for the fixed Qwen2.5-0.5B-Instruct / Apple MLX combination.
- **Media workflows**: image generation and Tiny-SD LoRA, fixed SVD video generation, Kokoro Chinese voice-over, step-by-step saving, and explicitly selected reuse.
- **Projects and data**: task drafts, source-group training/validation splits, version records, work revisions, export, full backup, and restore.
- **Execution management**: local execution, an independent execution-service protocol, transfer verification, and recovery from interruptions. The specified NVIDIA system and use of the same artifact across platforms still require real-device acceptance.

Video and audio training are not available. Media workflows save separate works and do not yet compose a finished video with voice-over. Existing LoRA and quantized-candidate quality failures remain recorded; completed training or readable files do not establish acceptable quality. See the [candidate scope](docs/implementation/2026-09-10-ver2-scope.md) for exact combinations and unavailable capabilities.

<a id="开发与验证"></a>

## Development and verification

The frontend uses React / TypeScript, the desktop host uses Tauri / Rust, and the local control service uses Python. Dependency versions are pinned in the repository's lock files.

    npm ci
    npm test
    npm run check:docs
    npm run test:docs

TypeScript checking and control-service tests:

    ./node_modules/.bin/tsc --noEmit -p apps/desktop/tsconfig.json
    services/control/.venv/bin/python -B -m pytest tests/control -q

The control-service command requires the corresponding Python 3.13 environment and dependencies to be prepared first. See [desktop development and build instructions](scripts/desktop/README.md) for full builds, runtime environments, signing, and startup. The current candidate targets Apple Silicon / macOS 26 and later, subject to verification of the final candidate.

Development, native testing, and local candidate execution share this path:

    apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app

Every actual App build increments the build number. Committing source or editing documentation does not produce a new App version.

<a id="文档"></a>

## Documentation

- [User guide](docs/USER_GUIDE.zh-CN.md)
- [Documentation center and the 1.1 design baseline](docs/README.md)
- [Complete trilingual documentation index](../README.md)
- [Changelog](CHANGELOG.md)
- [Prototype reference](prototype/reference-2026-09-09/README.md)

The repository contains source, tests, build scripts, user guides, design specifications, and historical acceptance records. Links to .artifacts/ refer to local evidence and require a workspace retaining those directories; conclusions and scope descriptions can be read directly on GitHub. Runtimes, App build outputs, models, user libraries, and local credentials are managed by their respective environments.

<a id="交付边界"></a>

## Delivery limitations

Full delivery still requires evidence for the specified NVIDIA system, trusted HTTPS across hosts, the same artifact across platforms, clean installation, five first-time users, passing quality, and human review. The historical intermittent blank display in long subtitle lists and other uncovered native paths remain unverified. The prototype, historical failures, and design baseline retain the conclusions reached when they were recorded.
