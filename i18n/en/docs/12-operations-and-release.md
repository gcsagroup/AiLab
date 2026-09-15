<!-- translation-navigation:start -->
[简体中文](../../../docs/12-operations-and-release.md) · [繁體中文](../../zh-TW/docs/12-operations-and-release.md) · [English](12-operations-and-release.md)
<!-- translation-navigation:end -->

<a id="安装运行维护与发布计划"></a>

# Installation, Operations, and Release Plan

Version: 1.1 · Date: 2026-09-09 · Status: Operational specification revised following the audit and awaiting implementation; no installer, background service, or production deployment currently exists.

Related documents: [Development roadmap](09-development-roadmap.md), [Task contracts](07-api-and-task-lifecycle.md), [Testing](11-testing-and-acceptance.md).

<a id="1-交付单元"></a>

## 1. Delivery Units

Distinguish the desktop client, control service, executors, environment packages, model files, data, works, and reports. Application upgrades do not redownload all models by default or automatically upgrade training environments in use.

The release manifest includes application version, commit hash, build platform, package digest, signing identity, base dependencies, optional environments, database schema, support matrix, known issues, and rollback instructions.

<a id="2-首次安装与环境准备"></a>

## 2. First Installation and Environment Preparation

1. Install the application and check basic storage permissions and available space.
2. The user selects the data root and model-cache location.
3. Detect devices read-only and display actual models, memory, drivers, and available backends.
4. The user selects runtime / training environments to prepare and reviews dependency sources, space, and operation scope.
5. Create an independent environment and run a minimum self-check; register the environment digest on success.
6. Prepare the model and complete download-integrity and loading checks.
7. Execute a real example task and save its result and recipe.

First-use acceptance AC-25 begins in a clean environment and permits direct trials within a category, recording the complete path through model preparation, device checks, first result, and continuation after exit. Recent-task entries must find both generation and training records, not training history alone. Completion, duration, and blockers for five target users provide usability evidence; skilled developer operation cannot substitute. (E-01)

If drivers are missing, explain the required steps. Driver installation, system-permission changes, and remote-service deployment are not part of ordinary connection checks. Cancelling preparation leaves existing environments and data usable.

<a id="3-运行模式"></a>

## 3. Operating Modes

| Mode | Network and execution | Display rules |
| --- | --- | --- |
| Demo mode | Preset data and simulated execution, with no promise of real computation | Prominent global marking; results identify their demo source |
| Local mode | Models and execution environments prepared on this machine | Displays actual devices, parameters, and artifacts |
| Remote mode | User-specified servers or configured cloud instances | Shows content to be sent and the destination before submission |

Demo and real data directories are separate; simulated and real metrics cannot be mixed in one task. Production release packages may retain a demo experience, but mode boundaries must be clear, and simulated success records must not enter official support reports.

<a id="4-日常运行与资源管理"></a>

## 4. Daily Operation and Resource Management

Model instances are identified by model version, adapter, engine, precision, and loading parameters. Share only when reuse conditions match; otherwise create a new instance or explicitly unload and reload. Users can view resident models, occupancy sources, and tasks using them.

Define closing a window, exiting the application, and stopping an executor separately: closing a window may retain background tasks; before exiting, show options for handling local running tasks. Remote tasks should reconnect after reopening even if the control side exits. If persistent remote execution is unavailable, its limitations must be stated.

<a id="5-日志与指标"></a>

## 5. Logs and Metrics

Logs have four layers—application, control service, executor, and task—with consistent task_id / attempt_id / environment_id. The user interface shows phases and Chinese summaries, with expandable original technical errors.

Default logs do not save complete datasets, plaintext credentials, or unrelated file contents. Task inputs and outputs are saved as project assets; access and cleanup follow project rules. Diagnostic export first generates a previewable manifest and exports only after the user selects scope.

Metrics must declare their sources and collection intervals. GPU / ANE utilization, cache-hit rates, or inference-phase timings unavailable from the system or engine display unmeasured; they must not be inferred from progress bars.

<a id="6-常见故障处理"></a>

## 6. Common Failure Handling

| Failure | Automatic handling | User options | Must preserve |
| --- | --- | --- | --- |
| Interrupted model download | Save download cursor and verified blocks | Resume, redownload, cancel | Source revision, temporary-file state |
| File validation failure | Isolate incomplete files without registering success | Delete that temporary download and retry | Validation digests and error |
| Device connection interruption | Rate-limited reconnection and state queries | Modify connection, wait, cancel local waiting | Known attempt_id and event cursor |
| OOM | Record the error and release releasable resources | Reduce parameters, create an attempt, or resume | Original parameters, logs, available checkpoints |
| Disk full / artifact transfer or registration failure | Seal the original manifest, mark collection failed, preserve computation outcome | Retry collection only after restoring space / connection, or explicitly create a computation-retry draft | Original attempt terminal state, original artifact digests, collection records, incomplete markers |
| Engine process crash | Keep the control service usable | View logs, retry, use a new environment | Exit information and snapshot |
| Pause-checkpoint failure | Query whether the executor continues computation, exited abnormally, or is unknown; respond under the state contract | View the reason, cancel, use supported force-stop; retry pause later if still running is confirmed | Original control command, checkpoint integrity, execution evidence |
| Cancellation timeout / unknown stop outcome | Retain cancelling, continue limited state queries, do not display stopped | Wait, view the remote task, use supported force-stop | Task ownership, process-tree evidence, last confirmed state |
| Database migration failure | Stop new-version writes and preserve backups | Roll back application / restore database | Old database, migration version, logs |
| Evaluation failure | Preserve candidate research records and prohibit admission | View samples, create an experiment after adjustments | Fixed evaluation rules and per-sample results |

Do not conceal failures by automatically rerunning expensive training repeatedly, or delete users' original data to “automatically repair” disk problems.

<a id="61-计算结束后的补收aud-08"></a>

### 6.1 Collection Recovery after Computation (AUD-08)

Computation completion and work / model usability are two separate checkpoints. Once the remote executor seals a complete manifest and retains files, transfer, validation, or local registration failures can use the [collections interface in 07](07-api-and-task-lifecycle.md). Recovery reads original files only and does not load the model for computation again. Missing manifests, corrupted source files, or expired retention display that collection cannot be recovered and list missing items; retraining cannot replace this operation.

Collection records separately save failures, retries, cancellation, and success; the original failed / cancelled attempt and reason remain unchanged. After successful recovery, display “Computation completed; artifacts collected through recovery,” preserving the original failure / cancellation notice and allowing per-file digests and registration results to be viewed. Candidates still need independent loading and evaluation; previously failed evaluations do not automatically pass. Acceptance injects disk-full conditions, interrupted transfers, and registration-transaction failure, confirming no increase in computation starts across recovery and exactly one asset registration.

<a id="7-备份与恢复"></a>

## 7. Backup and Recovery

Backup scope: consistent metadata-database snapshot, asset manifests, models / data / works to retain, task snapshots, environment lockfiles, checkpoints, and reports. Credentials retain only reconnection instructions or secure-storage references, without plaintext export.

Allowing users to choose complete backups or metadata / recipe backups is recommended. The latter must explain that missing large files need to be reacquired and must not claim offline restoration of all artifacts.

Recovery first validates schema and file digests, creates a new recovery directory, and switches the current workspace only after validation. Failed recovery does not overwrite a still-usable original workspace. Before every production release, rehearse restoring a representative project from an actual backup at least once.

<a id="8-清理与空间治理"></a>

## 8. Cleanup and Space Management

Display space by category: models, original data, processed versions, checkpoints, works, runtime caches, temporary downloads, and logs. List paths, sizes, references, and reasons before performing user-selected cleanup.

Prefer recoverable methods. Referenced files cannot be deleted merely because they “have not been opened for a long time”; training checkpoints referenced by recovery tasks must remain. After cleanup, verify indexes, references, and remaining space, allowing undo where needed.

Uninstalling the client does not delete the user's data root by default. Deleting a model, removing a model entry, and clearing engine caches are different actions; copy must explain their actual effects.

<a id="9-更新与回滚"></a>

## 9. Updates and Rollback

Application updates first check for local tasks and database migrations. If interruption is required, let the user choose a suitable time; do not automatically restart sidecars during training. Validate downloaded package digests and signatures before switching versions.

Database migrations use versioned scripts and backups; irreversible migrations must retain backup copies readable by the old application. Environment upgrades create new environments alongside old ones, so old tasks can still locate original dependencies. Model updates create new ModelVersion objects and must not alter files in existing versions.

After rollback, verify project lists, task snapshots, artifact reads, and new task execution. Successful application rollback does not mean every training environment rolled back successfully; report them separately.

<a id="10-导出与对外发布"></a>

## 10. Export and External Publishing

<a id="101-用户产物导出器的范围aud-13"></a>

### 10.1 User Artifact Exporter Scope (AUD-13)

WP-29 explicitly owns ordinary artifact export: M3 delivers basic model / adapter / text-work / report exports; M4 expands image / video / audio and subtitle revisions; M6 consolidates AC-27 acceptance for four object categories in the installer and independent environments. For new M5 conversion formats, WP-24 supplies artifacts and compatibility conditions to the existing exporter and expands corresponding acceptance; WP-24 does not replace the generic exporter. Diagnostic packages serve log troubleshooting and cannot count as delivery of model and work exports.

| Export object | Contents and dependencies | Independent-use validation |
| --- | --- | --- |
| Complete model / runtime model | Fixed weights or converted artifacts, configuration, required tokenizer / processor / template, provenance, compatible combinations | Load and run fixed samples in the declared independent environment without relying on undeclared caches from the original application |
| Adapter | Adapter files, target modules / parameters, fixed base-model revision and digest, template, required processors | Load the adapter with the declared base model; the base model may be included or external, but acquisition and verification methods must be explicit |
| Work | User-selected original or WorkRevision, media files / text, generation recipe, provenance, revision records | Readable text, decodable images, independently playable video / audio, subtitles timed consistently with media |
| Evaluation report | Baseline and candidate references, fixed data / rule versions, summary and selected per-sample results, artifact digests | Conclusions traceable from the included report; omitted original samples and models labeled external dependencies rather than falsely claiming a complete reevaluation package |

Subtitle revisions and generation recipes export separately, with the manifest fixing the work version. Selecting “Original output” does not include later manual corrections; selecting “Revision” still preserves revision provenance. Export cannot change existing report thresholds or conclusions. (E-04)

<a id="102-计划落盘与失败恢复"></a>

### 10.2 Planning, Persistence, and Failure Recovery

1. The user selects objects, fixed versions, target format, and directory; format conversion requires a separate conversion task to complete first. Resolve included files and external dependencies and show the manifest, estimated space, source materials, and compatibility conditions.
2. `/exports/prepare` generates an immutable ExportPlan and digest. Missing required included files, incomplete assets, unreadable versions, or unresolved dependencies block the plan. An adapter may export when its external base model is explicitly listed, but the interface must state that the base model is required for use.
3. When the user executes the plan, recheck source digests, space, destination, and that the plan is unchanged. Create an independent kind=export task attempt using a temporary directory on the same file system, without overwriting an existing complete export package.
4. Write selected files, `manifest.json`, recipes, provenance / revision records, necessary instructions, and per-file checksums. The manifest includes schema, object versions, relative paths, sizes, digests, included / external dependencies, and compatibility conditions; absolute private paths, plaintext credentials, and escaping symbolic links must not enter it.
5. Only after file-digest, manifest-reference, and readability checks complete may the directory be atomically renamed to the official export directory and completion recorded. Independent loading / playback results are recorded separately as use validation; file integrity and use validation are displayed separately. “Independently usable” requires corresponding evidence; otherwise display unverified.
6. Disk-full conditions, transfer interruption, changed source files, user cancellation, and validation failure retain explicit temporary states and errors without producing a package that could be mistaken for complete. Retry only repeats export packaging or continues from verified files, without retraining / regenerating; changed source digests require a new preparation plan.

The same idempotency key returns the same export task; repeated clicks do not package multiple times. Cancellation and completion follow the task-state contract: a package already registered atomically as successful returns complete; if cancellation commits first, temporary files are not published as a complete package. Before clearing residual temporary directories, show associated tasks, sizes, and recoverability. AC-27 includes four representative object categories, missing files, external base models, subtitle versions, cancellation, disk-full conditions, and independent-environment use, retaining specific files and digests in results.

<a id="103-对外发布"></a>

### 10.3 External Publishing

External uploads, model-repository publication, server deployment, and cloud-resource creation are independent actions and are not automatically triggered by Export.

Before publication, record distribution dependencies and the scope of model / data materials. List only materials that can actually be checked; AI does not generate authorization conclusions. This document contains no specific legal conclusions and does not substitute source descriptions for the user's actual publication decision.

<a id="11-发布验收清单"></a>

## 11. Release Acceptance Checklist

| Category | Required evidence |
| --- | --- |
| Identity | Installer version, digest, signature, build provenance, and commit agree |
| Installation | Clean-machine installation, first launch, basic environment checks |
| Main workflow | Real training / inference / evaluation / saving loop within the declared scope |
| Data | Historical-project upgrade, backup recovery, reference integrity |
| Export | WP-29 ordinary artifact exports for four object categories and independent-use checks, with explicit integrity and external dependencies; diagnostic packages accepted separately |
| Devices | Corresponding reports for every combination in the release matrix |
| Parameters | Actual mappings and necessary tests for all public controls |
| Failures | Explainable and recoverable pause failures, cancellation races, unknown stop states, disconnections, OOM, disk-full conditions, process crashes, and collection-only retries |
| AI | No autonomous execution, suggestion conflict handling, explicit transmission scope |
| Appearance | Chinese, keyboard, dark / light modes, representative window-width checks |
| Documentation | User guide, support scope, known issues, rollback methods |

Any data loss, incorrect project attribution, silently ignored parameters, false success, or credential leakage blocks release. Unvalidated hardware must not be listed as supported.

<a id="12-当前边界"></a>

## 12. Current Boundary

This round contains only Markdown documentation and the existing interactive prototype. No installer has been created, production service started, device permissions changed, or publication performed. This chapter provides rules for later implementation and acceptance; it is not a completed-deployment record.
