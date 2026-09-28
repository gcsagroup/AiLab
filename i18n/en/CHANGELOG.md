<a id="更新记录"></a>

# Changelog

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](CHANGELOG.md)

This record distinguishes source changes, local signed candidates, and formal releases. The versions below are development candidates or historical development records. They do not establish public release, notarization, or complete M0—M6 acceptance. Refer to the corresponding stage documents for detailed procedures, failures, and evidence boundaries.

<a id="未发布"></a>

## Unreleased

**049 local delivery acceptance summary (2026-09-29)**: This update changes acceptance records and documentation only; product code, the signed build and its build number are unchanged.

**Current M6 status (2026-09-29)**: The fixed company-signed candidate is **Ver2.6 (049)**. Full M0—M6 remains incomplete, and no formal release has been completed. Native tooling recovered after the directory move; the working root is `/Users/lazy/Projects/GCSA-AiLab`.

- Local evidence now covers historical-library restoration, migration and failed-migration rollback; normal native exports of 12 fixed objects; independent language-model/adapter loading, image-adapter generation, report reading and media playback; packaged missing-file, digest-change, real disk-full, cancellation and service-process-interruption tests with native history presentation; and diagnostic preview, export and redaction.
- Quality remains unqualified: the 7B LoRA scored 31/32 and failed the format gate, with no qualified candidate registered. Image structure defects remain, and subjective audio review is missing. Execution, file integrity and completed playback do not replace quality qualification.
- Remaining work includes clean installation and full upgrade acceptance of the same candidate, the complete UI and optimization matrices, the same qualified artifact chain from designated NVIDIA training to Apple, 5 real users, and notarization/distribution acceptance. Passing local subitems does not change these gates.

[Current candidate evidence and remaining work](docs/implementation/2026-09-23-m6-business-recovery.md)

The following entries retain conclusions from their original dates. Older candidate numbers, tooling blocks and next-step plans are not the current status.

**Apple configuration regression completed (2026-09-29)**: With the same Ver2.6 (049) candidate, the original 7B weights and ordinary KV cache completed 18 public-question tests across the default, 512-block, and low-latency settings. Arithmetic, extraction, structured output, and extraction from the beginning, middle, and end of long inputs were correct: 6/6 for each setting, with no additional regression found. Independent audit verified raw answers, scoring, empty caches, the complete bundle, and protected data; owned workers exited. The earlier performance matrix completed across two segments with 136 successful model computations and 45 device-busy rejections, while retaining 2 expired-check rejections caused by sleep. This does not establish uninterrupted or exclusive-host stability or acceleration from every configuration. Public-question regression does not replace business holdouts; the LoRA result of 31/32 still fails the requirement for perfect format correctness. Full AC24, native UI acceptance, and M6 remain incomplete.

[Configuration quality audit (local evidence)](../../.artifacts/apple-preset-quality049-20260928/root-readback.json)

**Per-sample evaluation termination and token recording fix（2026-09-23）**：9 new observation tests first reproduced the gaps. After the fix, all 290 MLX tests and 48 relevant control-service tests passed. Two short technical generations used the fixed Qwen2.5-0.5B on Apple GPU: both returned `Apple`; a 1-token limit produced `length`, while a 16-token limit produced 2 tokens including the end marker and `stop`. Collected text exactly matched the original stream, and model file hashes were preserved. No training or historical holdout rerun occurred, and no new quality pass is claimed. At source verification time, the fixed App was 044 and did not include the change; subsequent packaged and native results for 045 follow below. [M6](docs/implementation/2026-09-23-m6-business-recovery.md#评测逐题结束原因与词元记录修复)

**Apple larger-base quality experiment (2026-09-28)**: Using the same Ver2.6 (049) candidate, the 7B LoRA completed 192 training steps. On 32 newly frozen questions, the base passed 5/32 and the adapter 31/32: business 0/8→8/8, format 0/8→7/8, regression 5/8→8/8, and behavior 0/8→8/8. The sole failure changed order ID `C5-fo-02-04` to `C5-fo-002-04`. Business improvement passed, but format requires all answers to pass, so no qualified candidate was registered, no extra training was added, and the held-out questions were not retried. These are author-visible synthetic contract samples, not a blind evaluation; full business quality, native UI acceptance, and M6 remain incomplete.

**Apple signed candidate update (2026-09-28)**: The fixed App path now contains Ver2.6 (049), including experimental 7B support. The packaged production API completed empty-library restoration, import, source splitting, 2-step LoRA training, generation, and export. The exported adapter also generated independently of the control service using the external pinned base model. These are execution-path checks, not business-quality qualification. Native UI inspection was not performed because the Computer Use runtime could not start; full M6, clean installation, notarization, and distribution remain incomplete.

**Apple production API adaptation (2026-09-28)**: Added complete geometry fields to 7B model imports, control-service model checks, and source-group splitting support, while continuing to reject unverified quantization combinations. The isolated library accepted 8 source groups, split into 6 training and 2 validation samples; one technical training run completed with 2 steps, 28 layers, and rank 4. The saved experimental adapter generated `接口验收` as requested, followed by export of 3 content files. Independent read-only checks confirmed preservation of prior records, exactly one training, generation, and export attempt each, correct export hashes, and worker exit. Two earlier preparation failures resulted from omitted geometry fields and an unconfigured launch script; both ended before training and their records remain preserved. This proves only the source-level production API execution path, not business quality or independent use of this export. The standalone control-service dependency issue is included in regression fixes; the fixed 046 App remains unchanged and its complete rollback copy has been verified and saved. Next comes a new company-signed candidate followed by packaged and native acceptance; full M6 remains incomplete.

**Apple 7B source adaptation and training recovery (2026-09-28)**: fixed model profiles now determine LoRA tensor checks and cache layer counts. The Apple training contract permits up to 28 layers; 0.5B remains limited to 24 layers, and NVIDIA retains its existing scope. The official 7B preparation script pins the commit and all weight-shard hashes. The source executor used a 28-layer LoRA and a 4-step technical budget to complete continuous training, in-process pause/resume, checkpointed exit, and independent recovery. Both recovered runs had a maximum parameter difference of 0 from continuous training, with exactly matching losses and unchanged source model and data. After strict reload of the real adapter, ordinary KV cache produced the expected text, while q4 KV cache produced repeated text. The original output was retained, this mode was explicitly blocked before submission for 7B, and ordinary-cache generation was verified again. Successful processes for both cache modes do not imply quality acceptance. The 350 MLX regression tests and 4 weight-verification tests passed, along with all 1151 control-service tests, 18 follow-up training-contract tests, and 42 frontend training-field tests; existing dependency warnings remain. An old fixture missing the model layer count was corrected, and its initial failure log retained. The preparation script also performed actual read-only verification of both local base models. This is source and standalone-executor acceptance; the installed 046 App was neither rebuilt nor replaced. The full formal API chain, a newly company-signed candidate, native UI, business quality, and M6 remain pending.

**Apple larger-base readiness check (2026-09-28)**: official Qwen2.5-7B-Instruct commit `a09a35458c702b33eeacc393d103063234e8bc28` was pinned, with 13 files totaling 15242805751 bytes downloaded and individually verified. After a connection interruption, the original third-shard transfer remained slow. This run’s own download process was stopped, preserving completed shards, the old prefix, and logs. Exact byte ranges completed the shard, which passed the official full-weight hash. All tokenizer files match the existing allowlist, and 4 real tokenization cases matched. The first test environment lacked MLX dependencies; all 35 related tests then passed in the existing MLX environment. A separate process loaded the model on Apple GPU, with an observed cache of 28 layers, 4 KV heads, and 128 dimensions per head. All 3 pre-fixed short-output, multiplication, and inventory-decision probes matched exactly. Observed MLX peak memory was about 14.24 GiB, an observation from this run rather than performance acceptance. Model files were unchanged, and the process exited. No training, formal business evaluation, candidate qualification, or App modification or rebuild occurred; 7B product support is not enabled. Model restrictions, LoRA tensors, cache geometry, and training contracts still need adaptation, followed by real training, recovery, quality, and signed-candidate acceptance. Full M6 remains incomplete.

**Apple export used independently (2026-09-28)**: the same 046 package exported the LoRA and its fixed base from the v5 experiment database, totaling 12 content files. A pre-operation database snapshot was saved, and the export was copied to an independent directory containing Chinese characters and a space. After the control service stopped, a separate process using only MLX-LM loaded the included base and adapter. All 96 adapter tensors matched the exported weights, one generation completed, and file hashes stayed unchanged. The prompt requested only “验收”, but the output was “验收成功”. This proves independent loading and generation only; exact instruction matching failed, and the previous failed quality verdict remains. The experiment database retained its existing 40 resources, 229 events, 10 commands, and project, adding only the 4 resources for one export, with no new controlled training or evaluation. The control service exited normally, its listener and temporary connection token disappeared, and the independent generation process exited. All 75 export tests passed with 2 existing dependency warnings. The initially selected packaging environment lacked the test tool; testing then completed in the project test environment. This used the existing local MLX environment, without clean-account, native UI, or installation acceptance, and without rebuilding the App. Full AC27 and M6 remain incomplete.

**Apple new source-coverage experiment (2026-09-28)**: new data-generation and rule tests produced 128 synthetic fact groups with two introductory wordings each, totaling 256 samples. The formal source-group split yielded 192 training and 64 validation samples. Training covers all 32 task families; validation still lacks 9 families, so its coverage must not be overstated. The first draft contained a held-out question with the same core wording as a training question. That draft was retained, the sample corrected, and a duplicate check excluding introductory wording added; 43 data-rule and coverage tests passed. A single 192-step budget was frozen, and the same 046 package completed import, splitting, training, pre-training evaluation-plan binding, and report export in an independent control database. On the new 32 questions, the base scored 4/32 and the candidate 25/32: business 0/8→3/8, format 0/8→7/8, normal regression 4/8→7/8, and behavior 0/8→8/8. Business gain meets the original additional threshold, but absolute business accuracy, format, and regression still fail; no qualified candidate was registered. Errors include amounts, inventory/status decisions, booleans, and sorting. Training and evaluation materials are author-visible synthetic examples using the same templates with different facts, not a blind evaluation. The question sets differ across rounds, so their totals are not directly compared. After normal shutdown, all 29 protected files that existed at this round’s start, base-model hashes, frozen inputs, and 11 exported content files passed readback, as did independent-database integrity. The App was neither modified nor rebuilt, and no native UI acceptance was added; full M6 remains incomplete.

**Apple training-coverage audit**: the new read-only tool `tests/mlx/audit_training_coverage.py` counts categories and task families after the actual source-group split. Its 9 tests cover entire-family holdout, identical family names across categories, missing sources, and duplicate identifiers. Actual training and validation rows exactly matched the index and assignments: of 32 original families, only 24 occur in training and 8 occur exclusively in validation. Training counts for business, format, normal regression, and behavior are 14, 10, 10, and 14 respectively. Source isolation remains valid, but full coverage in the original data does not establish full training coverage. This finding alone does not prove the cause of quality failure. Family labels are author-supplied; the tool does not verify their semantic truth. New data must add independent factual examples within each family, keep paraphrases of the same facts in one group, and check coverage after splitting. Merely changing old source identifiers is not a valid way to remove the gap. Existing data, splits, quality questions, and failure results remain unchanged; no new training or generation occurred in this round.

**Apple-first progress (2026-09-28)**: the project moved to `/Users/lazy/Projects/GCSA-AiLab`. Apple local development and acceptance continue first; NVIDIA availability is no longer a prerequisite for local work. Full M6 cross-device, real-user, and distribution gates remain. The current Apple M5 Max MLX environment is operational, and 35 real-tokenizer and evaluation-observation tests passed. A read-only diagnostic used the existing LoRA with the original 48 training and 16 validation samples: 128 sample forward passes, with 453 and 183 supervised assistant tokens respectively. Token-weighted mean negative log-likelihood changed from 1.566950→0.028700 on training data and 1.256711→0.592857 on validation data. The training improvement was larger; this does not establish generalization quality or justify simply adding training steps. No training, regeneration of old quality-question answers, or candidate registration occurred. Weight and data hashes were preserved, and the old quality failure remains. The first script mixed two manifest digest types and was rejected before model loading; separate checks corrected that mistake and the diagnostic completed. The App was not modified, rebuilt, or launched natively. Next, improve training data and validation design, freeze a new experiment and independent quality criteria, then complete the Apple final-candidate workflow.

**Current M6 progress (2026-09-23)**: the fixed company-signed candidate is Ver2.5(046). Using the formal source-group workflow, the earlier quality run trained once on 48 samples with 24 LoRA layers for 192 steps, then independently compared the base and candidate on 32 newly frozen questions: total passes rose from 3/32 to 17/32 and business passes from 0/8 to 3/8. All four category thresholds still failed; no qualified candidate was registered. Per-sample observations, report export, shutdown, and original-data protection checks passed, along with 77 relevant tests. Qualifying quality, NVIDIA, 5 real users, clean installation, and distribution remain open. M6 is incomplete. [Business recovery and delivery progress](docs/implementation/2026-09-23-m6-business-recovery.md)

**045 additional local-runtime acceptance**: 20 complete native launch/quit samples passed. A separate run completed 362 formal packaged-service requests: 272 generations succeeded and 90 returned device busy. All owned processes exited normally, and original data and the fixed package were preserved. The low-memory preset traded slower first tokens for lower medium/long-input peaks; the low-latency preset did not improve every metric. In 75 open-ended outputs, token sequences differed from the same-weight default; repeats within each configuration were consistent. Those performance inputs do not establish semantic quality acceptance. Clean installation, full AC-23/AC-24, and M6 remain open.

**045 public preset regression**: a separate run completed 36 generations through the formal packaged service. On the existing 6 fixed questions, every preset scored 4/6 with original weights and 5/6 with quantized weights. All three presets produced identical token sequences for the same weight/question, with no additional regression. Existing arithmetic and bare-JSON errors remain. This passes only the public fixed-question subset, not training quality, quantization quality, or full M6 acceptance.

**046 native theme fix**: removing the fixed light window background restored readable dark-mode titles. Dark→light→dark switching within the same process passed and an independent screenshot was checked. The first round remains failed after an acceptance-session interruption and monitor timeout; a separate short round passed after data recovery. The historical database, model source files, and complete App were preserved, and the original selector and automatic appearance were restored. This closes only the local title defect; full AC-23/M6 remain incomplete.

**046 full automated regression**: all 662 frontend tests passed. The first control-service run had 1150 passes and 1 failure, with 5 warnings retained. Its error log confirmed that the test fixture read an empty exit-code file before writing had finished. Only fixture exit-code publication changed to an atomic operation; strict assertions for exit codes, checkpoints, and stop status remain. After the fix, all 10 lifecycle tests and 1151 full control-service tests passed, with 5 warnings still present. The source change affects tests only, and the fixed App was not rebuilt. Readback confirmed original data, model source files, the isolated business database, and the complete package were preserved. Automated tests do not replace remaining native, cross-hardware, quality, or real-user acceptance.

**046 four-width appearance and long-subtitle recheck**: one native process completed light and dark workbench checks at widths 1024, 736, 360, 320 and height 640, with every screenshot dimension read back; titles and navigation were readable. At width 320, the settings dialog scrolled to the bottom in both appearances, and Escape returned focus to its trigger. The existing revision containing 200 subtitles and 16000 characters showed its beginning, middle, and final entry in both narrow-window appearances without reproducing blank content; the historical blank-screen root cause remains unresolved. Width-adjustment observations were retained, and the attempt to restore the original window size before exit did not succeed. Automatic system appearance and the original selector were restored; after normal exit, original data, model sources, the business database, and the complete package were preserved. No new model runs or business commands occurred, and this round did not modify or rebuild the App. This adds only partial local AC-23 evidence; full M6 remains incomplete.

The company-signed Ver2.5（040） candidate passed native cold-start recovery with controlled empty libraries: failed switching returned to the recovery workspace, and healthy-backup migration, project persistence, and same-library reopening passed with the database and migration receipts preserved. The initial reopen process-monitor failure is retained; revalidation with the improved tool passed. No new models ran. Subsequent native checks confirmed that exiting without switching and reopening kept the original failed library selected, created a new recovery session, and preserved restored directories. Monitor and guard contract failures remain retained; independent stopped-state auditing passed. Failed upgrades containing business data, full AC-22／M6, notarization, and formal release remain incomplete. [Cold-start recovery acceptance](docs/implementation/2026-09-20-cold-start-recovery-source-progress.md)

The same company-signed 039 candidate completed controlled empty-library native migration rollback, healthy legacy-backup restoration, and reopening. Healthy A retained 8 resources; the repaired library passed migration 1→2→3→4 and test-project reopening. All 51 migration/backup tests passed, with no model runs. Cold-start offline restoration, failed upgrade with business data, and full AC-22/M6 remain pending. [Migration recovery acceptance](docs/implementation/2026-09-20-ver2-4-039-migration-recovery.md)

The same company-signed 039 candidate reopened the original 12-export library and added 1 export of an existing controlled dataset split, followed by reopening. Both of the 2 libraries and their export packages remained byte-identical across reopening. The 4 original/revision audio and video files played to the end in an independent player, and the image opened independently. No new model ran; full AC27, M6, and release remain incomplete. [Twelve-export acceptance](docs/implementation/2026-09-20-ver2-4-039-twelve-exports.md)

The fixed company-signed 039 candidate includes the export directory-entry fix. Its actual packaged service rejected 4 invalid entry types, recovered a valid interrupted package, and completed a fresh export. Native inspection of failed and successful records, normal exit, and reopening of the formally restored library passed. No new models ran; full AC27, M6, M0—M6, and release remain incomplete. [039 acceptance and boundaries](docs/implementation/2026-09-16-export-tree-integrity.md)

The following records retain their state when written.

Subsequent source fix: the actual packaged 038 service still incorrectly accepts a symbolic link for the manifest; negative evidence is retained. Source now rejects manifest links, dangling links, directory links, and special files, with 186 related regressions passing. This is not yet included in a new signed candidate; full M6 and release status do not advance. [Directory-entry fix and negative evidence](docs/implementation/2026-09-16-export-tree-integrity.md)

The fixed company-signed 038 candidate includes the complete export manifest identity fix. Rejection of an incorrect version after controlled registration failure and a successful new export passed in the packaged service, followed by native inspection, normal exit, and reopening of the formally restored library; the database was entirely unchanged after the second shutdown. No new model runs occurred; full M6, M0—M6, and release remain incomplete. [038 acceptance and boundaries](docs/implementation/2026-09-16-ver2-4-038-export-identity.md)

The following records retain their state when written.

Fixed source-level export recovery accepting changed manifest identity: verification now checks the complete frozen manifest and rejects incorrect objects or versions, missing fields, extra claims, and incorrect types. All 179 regression tests passed. The fix is not yet included in the fixed signed 037 App; native interruption recovery remains pending.

Native revalidation of the startup tool’s system-launch and shutdown-sidecar fixes is complete. For the fixed 037 candidate, one round recorded host full readiness at 4.933 seconds and external observation at 5.029 seconds. Native Quit, operator acknowledgement, process disappearance, and the stopped snapshot passed; original library protection was restored, with no new model execution. The first-round sidecar failure remains preserved, and all 50 measurement tests passed. The 20 initial-visibility measurements and full-stage acceptance remain incomplete. [Native tool revalidation](scripts/desktop/README.md#同一候选的启动测量).

The following source-stage records retain their status when written; the native revalidation result above takes precedence.

Native tool review found that ordinary read-only inspection after shutdown left database sidecars, so the strict snapshot check refused to proceed. Inspection now holds the control-service lock and confirms that no sidecars exist before reading the main database. The old sidecars were preserved unchanged, and the database and all tables matched. All 50 measurement-tool tests passed; native revalidation of the fix is pending.

The startup measurement tool now uses foreground system launch and checks the new App path, PID, start identity, and owned control process. It records the launcher exit code separately from the unknown App exit code and requires confirmation of normal native exit. Duplicate instances, identity changes, timeouts, and unconfirmed exits retain a failed round and stop subsequent launches. All 44 tests passed; the fixed signed App remains 037, and native acceptance of this tool change is pending.

037 completed a native comparison of launch methods using the same independent library: direct execution incurred a long hidden wait, while normal system launch produced a full-readiness receipt of 5.943 seconds. Data protection and exit checks passed, with no new model execution. This does not pass initial-visibility performance or all stages; system-launch support in the startup acceptance tool remains pending. [Comparison evidence and limits](scripts/desktop/README.md#同一候选的启动测量).

The startup acceptance script distinguishes full readiness from initial window visibility: it retains the 20-round, 3000-millisecond statistic and all failures, uses an explicit readiness field, and marks the initial-visibility verdict as unmeasured; historical reports are not rewritten. Only acceptance tooling and tests changed. The fixed company-signed App remains 037, with no new native performance results or model execution. See [startup measurement guidance](scripts/desktop/README.md#同一候选的启动测量).

037 verified native disk-full rejection before copying and recovery, plus preservation of failure and recovery export after actual mid-copy volume exhaustion in the packaged service. Native history inspection and reopening after formal backup and restoration also passed; original failed and successful records and files remain unchanged, with no new model runs. The mid-copy fault was still triggered through HTTP, and the synthetic fixture does not establish model capability. Full M6, M0—M6, and release remain unpassed. [037 disk-full recovery acceptance](docs/implementation/2026-09-16-ver2-4-037-storage-recovery.md)

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
