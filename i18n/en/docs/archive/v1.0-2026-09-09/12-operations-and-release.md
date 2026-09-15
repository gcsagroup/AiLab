<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/12-operations-and-release.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/12-operations-and-release.md) · [English](12-operations-and-release.md)
<!-- translation-navigation:end -->

<a id="安装运行维护与发布计划"></a>

# Installation, Operations, and Release Plan

Version: 1.0 · Date: 2026-09-09 · Status: operating specifications for an unimplemented product; no installer, background service, or production deployment currently exists.

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
| Full disk | Stop new writes and report recoverable scope | Select storage, clear caches, retry collection | Complete artifacts and incomplete markers |
| Engine process crash | Keep the control service usable | View logs, retry, use a new environment | Exit information and snapshot |
| Database migration failure | Stop new-version writes and preserve backups | Roll back application / restore database | Old database, migration version, logs |
| Evaluation failure | Preserve candidate research records and prohibit admission | View samples, create an experiment after adjustments | Fixed evaluation rules and per-sample results |

Do not conceal failures by automatically rerunning expensive training repeatedly, or delete users' original data to “automatically repair” disk problems.

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

Export bundles include selected artifacts, recipes, provenance relationships, required processors/tokenizers, compatibility conditions, and reports. Users can select models, adapters, works, or evaluation reports; adapter exports explicitly list base dependencies.

After export, verify readability/loadability in an independent environment. External uploads, model-repository publication, server deployment, and cloud-resource creation are independent actions, never triggered automatically by the export button.

Before publication, record distribution dependencies and the scope of model / data materials. List only materials that can actually be checked; AI does not generate authorization conclusions. This document contains no specific legal conclusions and does not substitute source descriptions for the user's actual publication decision.

<a id="11-发布验收清单"></a>

## 11. Release Acceptance Checklist

| Category | Required evidence |
| --- | --- |
| Identity | Installer version, digest, signature, build provenance, and commit agree |
| Installation | Clean-machine installation, first launch, basic environment checks |
| Main workflow | Real training / inference / evaluation / saving loop within the declared scope |
| Data | Historical-project upgrade, backup recovery, reference integrity |
| Devices | Corresponding reports for every combination in the release matrix |
| Parameters | Actual mappings and necessary tests for all public controls |
| Failures | Cancellation, disconnection, OOM, full disk, and process crashes are explainable and recoverable |
| AI | No autonomous execution, suggestion conflict handling, explicit transmission scope |
| Appearance | Chinese, keyboard, dark / light modes, representative window-width checks |
| Documentation | User guide, support scope, known issues, rollback methods |

Any data loss, incorrect project attribution, silently ignored parameters, false success, or credential leakage blocks release. Unvalidated hardware must not be listed as supported.

<a id="12-当前边界"></a>

## 12. Current Boundary

This round contains only Markdown documentation and the existing interactive prototype. No installer has been created, production service started, device permissions changed, or publication performed. This chapter provides rules for later implementation and acceptance; it is not a completed-deployment record.
