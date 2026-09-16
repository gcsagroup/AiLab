<a id="更新记录"></a>

# Changelog

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](CHANGELOG.md)

This record distinguishes source changes, local signed candidates, and formal releases. The versions below are development candidates or historical development records. They do not establish public release, notarization, or complete M0—M6 acceptance. Refer to the corresponding stage documents for detailed procedures, failures, and evidence boundaries.

<a id="未发布"></a>

## Unreleased

037 completed native disk-full rejection before copying and recovery, and added evidence of actual volume exhaustion during copying in the packaged service: no partial package was published, a new export succeeded after freeing space, and the old failure and restart state persisted. The latter used a synthetic storage fixture with 0 new model runs or evaluations and no native-interface acceptance of this fault. Full M6, M0—M6, and release remain unpassed. [037 disk-full recovery acceptance](docs/implementation/2026-09-16-ver2-4-037-storage-recovery.md)

The same signed 037 candidate completed actual admission rejection, native report export, and reopening for an existing failed evaluation. All 11 payload files and 60884 bytes passed individual checks; 52 original resources remain, with 4 export resources added and 0 new model runs or evaluations. The quality failure remains; full M5, M0—M6, and release remain unpassed. [037 quality report acceptance](docs/implementation/2026-09-16-ver2-4-037-quality-export.md)

The same signed 037 candidate completed explicit workflow reuse, saving all three works, invalidation after upstream changes, and same-library reopening. The original 507 resources were preserved, with 14 new resources and 9 commands; model attempts and training runs were both 0. A subsequent controlled-occupancy fixture verified unchanged contents in all six tables after native rejection, followed by formal reconciliation, one advancement, and persistence across reopening; real execution races, quality, and full M4 acceptance remain pending. [037 workflow acceptance](docs/implementation/2026-09-16-ver2-4-037-workflow-reuse.md)

The fixed company-signed 037 candidate passed native offline registration and application of downloaded data: a real 292-byte download containing 2 rows was registered and applied to the original task after the provider stopped and the market reopened. Draft revision changed from 2→3, only the dataset changed, and seed 817 was preserved. Normal exit, stopped-library readback, and original-data restoration passed; full M4, M0—M6, and release remain unpassed. [037 native offline acceptance](docs/implementation/2026-09-16-market-offline-downloads.md)

The following source-stage records retain their state when written.

Source progress: when the market catalog is unavailable, users can explicitly view completed local downloads, verify and register them, and apply them to the original draft. The 31 frontend, 63 backend, and targeted host tests passed, as did the real HTTP browser flow. The fixed App remains 036 and does not contain this fix; native acceptance and full M4 remain pending. [Offline download entry](docs/implementation/2026-09-16-market-offline-downloads.md)

The fixed company-signed 036 candidate includes the official-model runtime-boundary fix. Package checks and limited native notice acceptance passed: official-catalog and local-inspection explanations were visible, with 1 project/1 import plan and no download, import confirmation, or model execution. Normal exit and original-data protection/restoration passed; full M2 and release remain unpassed. [036 notice acceptance](docs/implementation/2026-09-16-official-model-runtime-boundary.md)

The following source-stage and earlier-candidate records retain their state when written.

Source progress: official model preparation now shows runtime boundaries consistent with manual import, and newly registered models retain fields from actual verification. Missing/unknown notices add no download or registration gate. Related tests passed; the fixed signed App remains 035 and does not contain this fix. Full M2 and release status are not advanced. [Official model preparation boundary](docs/implementation/2026-09-16-official-model-runtime-boundary.md)

The 035 packaged worker completed one real generation under process network denial, producing `7`; the rejection matrix for unsupported media/cache requests is published (E146). This does not establish physical disconnection, a product OS sandbox, or cache-hit performance. Real HTTP cancellation and subsequent generation recovery through the packaged control service also passed, without App UI acceptance in this round; M2 and release status are not advanced. [Runtime boundaries and evidence](docs/implementation/2026-09-16-ver2-4-035-runtime-boundaries.md)

<a id="未开放媒体与缓存请求的拒绝测试--2026-09-16"></a>

### Rejection Tests for Unsupported Media and Cache Requests — 2026-09-16

- Added [MLX entry-point tests](../../tests/mlx/test_media_cache_boundary.py) and [control-service tests](../../tests/control/test_media_cache_http.py). With the text input held constant, 10 cases cover media identity, media order, processor revisions, preprocessing dimensions, and cache reuse requests. Production code is unchanged.
- The 30 tests of MLX validation, preflight, and execution entry points confirm explicit rejection before loading or computation. The 20 control-service tests use in-process TestClient requests to verify that draft updates return 422 and submission after a failed legacy-draft preflight returns 409, without creating runs or artifacts. Legacy-draft tests replace subprocess dispatch with the production preflight function; they do not establish real network or native UI acceptance.
- All 50 new rejection tests passed, along with 139 related MLX regression tests and 50 control regression tests. These suites overlap and are not added together. Tests use temporary files, temporary libraries, and fixtures, without real model computation.
- README, CHANGELOG, user guides, design specifications, implementation records, and historical records all continue to be available in Simplified Chinese, Traditional Chinese, and English. The fixed App remains 035 and was not rebuilt. These tests do not establish media cache hits, invalidation, performance, or offline inference, and do not advance M2 or formal release status.

<a id="模型导入信任与权限说明源码验证"></a>

### Model Import Trust and Permission Explanations (Source Validation)

The following source and candidate paragraphs retain their state when written; “035 not built” does not describe the current candidate.

Source progress: model import now explains loading trust and permissions, including fixed loaders, rejection of custom code, and limits of a same-user process. Offline options and credential environment allowlists do not provide operating-system isolation. The backend passed 40 tests and the frontend 46, with type checking passing. The fixed App remains 034 without these changes; 035 is not built and native acceptance is pending. [Model import trust boundaries](docs/implementation/2026-09-16-model-import-trust-boundary.md)

<a id="人工补收恢复与生命周期修复构建前源码记录"></a>

### Collection Recovery and Lifecycle Fixes (Pre-build Source Record)

Source progress: fixes recover manual collection stuck in collecting after interruption and cover computation finishing first, failed-exit records, and stop-signal errors. The final integrated regression passed 221 tests. The fixed signed App remains 033 and does not contain these changes; no 034 build has occurred, and complete M1 and release status do not advance. [Collection recovery and source limits](docs/implementation/2026-09-16-collection-recovery-source-progress.md)

<a id="数据划分读取与人工补收修复构建前源码记录"></a>

### Dataset Read and Manual Collection Fixes (Pre-build Source Record)

Pre-build source progress: stale dataset-split reads no longer clear apply errors, and failed manual-collection registration can preserve the computation result and allow retries after recovery. Related source tests and browser component fixture checks passed. The fixed App remains 032; 033 has not been built, and this round’s native dataset workflow has not run. [Source fixes and limits](docs/implementation/2026-09-16-dataset-and-collection-source-fixes.md)

<a id="python-环境路径保留修复构建前源码记录"></a>

### Python Environment Path Preservation Fix (Pre-build Source Record)

- The macOS Python picker explicitly sets `setResolvesAliases(false)` and preserves the user-selected symlink path from the original file URL. Existing connection-identity checks and the “Use this environment” confirmation gate remain intact.
- Passed 66 host tests; 3 existing onsite tests remain ignored. The 5 new Foundation and temporary-file tests cover symlinks, Chinese characters and spaces, ordinary files, cancellation, errors, non-file URLs, and the wrong thread, without creating or displaying a real native panel.
- The company-signed App at the fixed path remains Ver2.4（031）; 032 has not been built. Real panel results, confirmation paths, saving all three environments, reopening, and restoring bundled environments await acceptance of the next candidate. The 031 failure and original evidence remain preserved, with no advancement in full AC, M0—M6, notarization, or public-release status.

<a id="原生选择器连接隔离构建前源码记录"></a>

### Native Picker Connection Isolation (Pre-build Source Record)

- Connection-identity checks now cover `pick_import_path`, `pick_export_directory`, `pick_worker_python`, `pick_media_python`, `use_bundled_worker`, and `use_bundled_media` at selection start and completion, HTTP dispatch, and returned results, preventing old operations from granting path access or changing the Python environment in a new library.
- Import and evaluation-plan dialogs invalidate old callbacks after a project switch or unmount, preventing late selections, checks, or save results from affecting the new project.
- Passed 618 frontend tests, 61 host tests, and type checking. The 3 existing onsite tests remain ignored and are not counted as passing. Corresponding pre-fix failures and post-fix regression evidence are preserved.
- The current company-signed candidate at the fixed path remains Ver2.4（030）; 031 has not been built, and this round's signed-package and native hands-on verification are incomplete. The historical 030／E138 acceptance boundaries remain preserved, with no advancement in full AC, M0—M6, notarization, or public-release status.

<a id="工作库连接隔离构建前源码记录"></a>

### Library Connection Isolation (Pre-build Source Record)

- Ordinary API requests and media reads bind to the connection identity acquired for the call. Library switches, rollbacks, and restarts reject old requests and late responses; writes are never automatically resent using the new library identity.
- Startup notifications for the same connection preserve valid reads. An actual reconnection invalidates old environment checks and waits for the host operation to finish before reading the new state.
- Passed 574 frontend tests, 52 host tests, and type checking; 3 existing onsite tests remain ignored. Host tests use temporary HTTP services to verify that old-library requests do not reach the new library.
- This is source verification; the signed App at the fixed path remains 029. Repackaging and native UI acceptance of this fix are pending. Asynchronous native file, directory, and Python environment picker operations are outside this isolation coverage.

<a id="media-键盘修复2026-09-15-准备记录"></a>

### Media Keyboard Fix (Preparation Record, 2026-09-15)

- Added explicit keyboard-focus attributes to the model, image-dataset, and image-material import entry points.
- Passed 56 related frontend tests, type checking, and the real Safari subset covering forward/reverse Tab, opening with Enter, closing with Escape, and returning focus.
- Prepared the 029 native supervisor, stopped-state readback, and comparison scripts; completed 35 synthetic tests and two independent reviews.
- 029 has not been archived, built, or accepted through native testing; the current App remains 028.

[Media progress](docs/implementation/2026-09-15-media-keyboard-progress.md)

<a id="仓库与文档"></a>

### Repository and documentation

- Organized product source, tests, build scripts, and formal documentation in one repository while retaining the prototype and historical design archive.
- Added Simplified Chinese, Traditional Chinese, and English documentation and changelogs, stating candidate status and the scope of local evidence links.
- Completed ignore rules for generated runtimes and build files; source commits do not contain models, user libraries, or credentials.

<a id="ver24035本机推理与重开--2026-09-16"></a>

## Ver2.4（035） Native Inference and Reopening — 2026-09-16

The fixed company-signed 035 candidate received limited acceptance for real local inference and same-library reopening on Apple M5 Max (E145): import trust and persisted boundaries, preset cancellation/application, rejected50+79/allowed50+78 budgets, auto512/stop39/stream=false→text7, saved work, and an unexecuted recipe draft are evidenced. There was 1 attempt and 0 training; 15 resources/4 commands/13 events/6 artifacts and31 file hashes remained unchanged, both App exits were normal, and47/44 protection records plus12 source-model files passed restoration checks. The original guard exit1, rejected launch, and interrupted locking remain recorded; M2, full AC, M0, M2—M6 and release status are not advanced. [035 inference and reopening evidence](docs/implementation/2026-09-16-ver2-4-035-native-inference.md)

<a id="ver24034补收恢复验收--2026-09-16"></a>

## Ver2.4（034） Collection Recovery Acceptance — 2026-09-16

The fixed company-signed 034 package and native collection roundtrip received limited acceptance (E144): recovery after a real interruption in a new fixture-executor library, collection-only retry, saving a short text work, and same-library reopening. The original failure remains, with no new attempt or model execution. Resources 7→10, 2 commands/3 events, both normal exits, and 47/44 protection restoration passed. The M1 application and data foundations stage passed (contract and UI subsets); full AC, M0, M2—M6, and release remain unpassed. [034 collection recovery and stage evidence](docs/implementation/2026-09-16-ver2-4-034-collection-recovery.md)

<a id="ver24033数据流程验收--2026-09-16"></a>

## Ver2.4（033） Dataset Workflow Acceptance — 2026-09-16

The fixed company-signed 033 package and native dataset workflow received limited acceptance (E143): three import rejections, 7-row import, source splitting, successful configuration checking followed by length invalidation, and direct draft restoration in the same library. Stopped-state checks found 12 new resources, 3 commands, 0 attempts, and draft revision 5; both normal exits and 47/44 protection restoration passed. No training or model generation occurred; complete M1, M0—M6, and release status do not advance. [033 dataset workflow and limits](docs/implementation/2026-09-16-ver2-4-033-dataset-workflow.md)

<a id="ver24032字幕流程进展--2026-09-16"></a>

## Ver2.4（032） Subtitle Workflow Progress — 2026-09-16

- Real keyboard operation of the functional flow, container-scroll sampling, continuing/discarding temporary edits, one v5 save, and same-library reopening passed (E142). The fixed App was not rebuilt, and no model ran.
- Stopped-state checks confirmed that only the final cue changed across 200 cues/16000 characters, with 1 new revision, subtitle artifact, and command. Explicit historical v4 export then produced a 5-file package while current v5 and historical v4 remained intact.
- Root accepted both normal exits and protection restoration, with 44 of 47 protection records strictly unchanged. Recorder filename conflicts, directory-input corrections, screenshot limits, and the unknown old 020 cause remain recorded; full AC22, AC27, M0—M6, and release status do not advance.

[Subtitle workflow and limits](docs/implementation/2026-09-16-ver2-4-032-subtitle-workflow.md)

<a id="ver24032诊断目录回归--2026-09-16"></a>

## Ver2.4（032） Diagnostic Directory Regression — 2026-09-16

- Reused the fixed company-signed 032 App without rebuilding. Actual import covered 3 trilingual samples totaling 650 bytes; directory-chooser cancellation and whole-diagnostic cancellation were verified separately (E141).
- Saving to a directory with Chinese characters and a space produced a 9316-byte ZIP. CRC, manifest, hash, and redaction checks passed for its 2 members. All tables, raw database bytes, and ZIP bytes remained identical after reopening the same build and library.
- Both normal exits and original-selector restoration completed; 44 of 47 protection records were strictly unchanged. Environment records contain 3 probe and 8 environment observations, so probing was nonzero. No model ran.
- Selection corrections and screenshot limitations remain recorded; historical diagnostic successes and Python-path records remain unchanged. Full AC27, AC22, M0—M6, and public-release status do not advance.

[Diagnostic regression and limits](docs/implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md)

<a id="ver24032-2026-09-16"></a>

## Ver2.4（032）— 2026-09-16

- The Python symlink-path preservation fix is included in the company-signed package at the fixed path. Passed 66 host tests; 3 existing onsite tests remain ignored. The single build and root complete-bundle verification passed (E140).
- Root acceptance covers the limited subset of native panel selection, cancellation and an ordinary-file control, exact saving of all three environments, reopening the same build and library, and restoring bundled environments. Stopped-state revisions are 4/7, with all three fields first holding the original venv path and then explicit null. Both normal exits and protection restoration passed.
- External dependency-probe failures remain recorded; all four categories showed readiness after restoring bundled environments. No model ran. Screenshot-format and size anomalies, two root-readback parsing failures, and their corrections remain recorded without lowering the original gates.
- The 031 path failure and historical text remain preserved. Native cross-library races, diagnostic export, full AC, M0—M6, notarization, and public release remain incomplete.

[032 progress and limits](docs/implementation/2026-09-16-ver2-4-032-python-path-preservation.md)

<a id="ver24031-2026-09-16"></a>

## Ver2.4（031）— 2026-09-16

- The native-picker connection-isolation fix is included in the company-signed package at the fixed path. Passed 618 frontend tests, 61 host tests, and type checking; 3 existing onsite tests remain ignored. The single build and root complete-bundle verification passed (E139).
- The native UI imported 3 JSONL samples totaling 509 bytes and exercised cancellation of dataset selection, Python file selection, and Python confirmation. One normal exit returned 0; the original selector was restored, with 44 existing protection records strictly unchanged.
- Selecting the venv Python made the confirmation display the base interpreter path, so it was cancelled without saving. The three-field check failed because environment setup was incomplete, and that original failure is preserved. Saving all three environments, reopening, restoring bundled environments, diagnostic export, and native connection-race verification remain incomplete.
- The root-cause chain for the path returned by NSOpenPanel has been identified, but a subsequent fix has not been implemented or accepted. Source-helper tests with injected paths do not exercise the real native panel. Full AC, M0—M6, notarization, and release status do not advance.

[031 progress and failure evidence](docs/implementation/2026-09-16-ver2-4-031-native-picker-progress.md)

<a id="ver24030-2026-09-16"></a>

## Ver2.4（030）— 2026-09-16

- The library connection-isolation fix is included in the company-signed package at the fixed path. The single build, complete-bundle review, and checks of 7 signed targets passed (E138).
- Passed 574 frontend tests, 52 ordinary host tests, and type checking. Two additional tests actually used the current packaged control service to verify restart authentication and migration-failure rollback; both passed. The onsite Keychain test remains unexecuted.
- Root acceptance covers the limited native subset of full backup, rollback after target-library startup failure, successful switching, separate project saves, and reopening the same build. Both normal exits and stopped-state readback passed. Migration failure and queued old-request races were not reproduced in the native UI.
- The 029 archive and existing acceptances remain preserved. Asynchronous native-picker races, full AC, M0—M6, notarization, and public release remain incomplete.

[030 connection-isolation progress](docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md)

<a id="ver24029-2026-09-16"></a>

## Ver2.4（029）— 2026-09-16

- The fix for the three Media entries is included in the company-signed package at the fixed path; the single build and root verification of the full package passed (E137).
- All four entry instances in two existing tasks passed forward and reverse Tab, Enter to open, and Escape to close and return focus, followed by normal exit; no real import or model run occurred.
- One stopped-state readback confirmed that the 523 resources, 673 events, 3 commands, and all business records remain unchanged; only four expected page-setting leaves changed.
- The 028 archive is retained; no cleanup occurred and the capacity threshold was not lowered. Full AC, M0—M6, notarization, and public release remain incomplete.

[029 Media progress](docs/implementation/2026-09-15-media-keyboard-progress.md)

<a id="ver24028-2026-09-15"></a>

## Ver2.4（028）— 2026-09-15

- Fixed keyboard focus for the Workbench back, import-model, import-data, and new-evaluation-plan buttons.
- Passed 59 related frontend tests, type checking, and Safari component verification.
- Accepted the fixed-path company-signed package, forward/reverse native focus for the four buttons, normal exit, and a stopped-state data subset; business records were unchanged, with only three page-selection changes.
- Full keyboard paths, all AC items, and M0—M6 have not been signed off.

[028 progress](docs/implementation/2026-09-15-ver2-4-028-workbench-keyboard-progress.md)

<a id="ver24027-2026-09-15"></a>

## Ver2.4（027）— 2026-09-15

- Added keyboard-focus attributes for task-related buttons; 75 related frontend tests and a Safari subset passed.
- Exported an original text work using only the keyboard in the native App, then reopened the same record from the queue; stopped-state readback accepted the corresponding limited subset.

[027 progress](docs/implementation/2026-09-15-ver2-4-027-keyboard-progress.md)

<a id="ver24026-2026-09-14"></a>

## Ver2.4（026）— 2026-09-14

- Fixed focus on the first read of work revisions; 41 related regression tests, a Safari comparison, and the company-signed package passed.
- Accepted a limited native subset covering first-open/reopen focus, return to the entry point on close, and reading saved subtitles.
- A complete export package for existing text revision 3 displayed a neutral pending-verification state after registration failed, then registered successfully under the same identifier after verification.

[026 progress](docs/implementation/2026-09-14-ver2-4-026-progress.md) · [Export recovery](docs/implementation/2026-09-14-ver2-4-026-export-recovery-progress.md)

<a id="ver24025-2026-09-14"></a>

## Ver2.4（025）— 2026-09-14

- Fixed focus returning to the manual-revision entry point after closing.
- Retained the first restore-source error; a subsequent formal independent restore enabled limited native verification of existing subtitle version 4 / parent version 3, 200 cues / 16000 characters, and exit from temporary editing.

[025 progress](docs/implementation/2026-09-14-ver2-4-025-progress.md)

<a id="ver24024-2026-09-14"></a>

## Ver2.4（024）— 2026-09-14

- Added a static import index for startup dependencies while retaining integrity and environment checks.
- Related tests, the signed package, and one native diagnostics subset passed; a single full-readiness duration is not treated as a 20-run initial-visibility acceptance result.
- The Safari long-subtitle comparison did not reproduce the historical 020 blank display; the original issue remains open.

[024 progress](docs/implementation/2026-09-14-ver2-4-024-progress.md) · [Long-subtitle diagnosis](docs/implementation/2026-09-14-subtitle-scroll-diagnosis.md)

<a id="ver24014023-2026-09-13-至-2026-09-14"></a>

## Ver2.4（014—023）— 2026-09-13 to 2026-09-14

- Improved work-recipe viewing/loading, existing revision layout, historical-version pagination, preservation of the selected revision during export, and neutral recovery messages.
- Added Chinese-character and subtitle-limit checks, scroll-boundary isolation, local focus fixes, and startup-phase diagnostics.
- Actual saving, playback, export, and project-switching subsets remain attributed to their respective versions; later limited passes do not close the intermittent 020 blank display or uncovered paths.

[Complete per-version records](docs/implementation/2026-09-10-execution-board.md)

<a id="ver23013-2026-09-13"></a>

## Ver2.3（013）— 2026-09-13

- Improved continuation within a category, reopening a specified historical task, project ownership, and draft restoration.
- Limited native verification covered continuation through six entry points in the same library and ownership of a newly saved generation; missing running-stage samples and remaining checks are retained.

[013 progress](docs/implementation/2026-09-13-ver2-3-013-progress.md)

<a id="ver22006012-2026-09-11-至-2026-09-13"></a>

## Ver2.2（006—012）— 2026-09-11 to 2026-09-13

- Added source-group checking, preview, and explicit application of training/validation splits, together with backup, restore, and export relationships for v4 libraries.
- Improved native restore, reconnection after failure, diagnostics, and continuation of drafts across projects.
- In 011, initial main-window visibility met the target in 20/20 runs with an existing environment and representative data scale; variation in full readiness remains a separate historical result.

[006 source-group workflow](docs/USER_GUIDE.zh-CN.md) · [011 progress](docs/implementation/2026-09-13-ver2-2-011-progress.md) · [012 progress](docs/implementation/2026-09-13-ver2-2-012-progress.md)

<a id="ver20ver21001005-2026-09-10-至-2026-09-11"></a>

## Ver2.0／Ver2.1（001—005）— 2026-09-10 to 2026-09-11

- Established fixed-path desktop candidates, company signing, self-contained runtimes, local candidate update and rollback, full backup/restore, and object exports.
- Integrated language and media execution, evaluation admission, the independent execution protocol, and the HTTPS-target interface.
- Actual training, quantization, and rejection gates produced independent evidence; historical quality failures remain failures, and loopback/CPU component verification does not establish NVIDIA or cross-host acceptance.

[Historical delivery and evidence matrix](docs/implementation/2026-09-10-current-delivery-matrix.md)

<a id="设计基线-11--2026-09-09"></a>

## Design baseline 1.1 — 2026-09-09

- Fixed requirements, interaction, architecture, M0—M6, work breakdown, and acceptance relationships.
- Retained the 1.0 documentation archive and prototype reference; added 14 audit-remediation items and 5 enhancement decisions.
- Recorded design delivery, prototype behavior, and subsequent real product implementation separately.

[Design baseline](docs/README.md) · [1.0 archive](docs/archive/v1.0-2026-09-09/README.md)
