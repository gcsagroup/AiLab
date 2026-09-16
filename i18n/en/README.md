<a id="gcsa-ai-lab"></a>

# GCSA AI Lab

[简体中文](../../README.md) · [繁體中文](../zh-TW/README.md) · [English](README.md)

A local-first desktop workbench for model training and inference. Organize models, data, training tasks, evaluations, and works by project, with workflows for language, images, video, and voice-over.

<a id="当前状态"></a>

## Current status

The current fixed company-signed candidate is **Ver2.4（033）**, signed by **Global Cybersecurity Alliance Limited**. It is a development candidate; full M0—M6, clean installation, notarization, and formal distribution acceptance remain incomplete.

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
