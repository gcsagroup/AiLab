# Changelog

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](../fr/CHANGELOG.md) · [Português](../pt/CHANGELOG.md)

## 2026-10-14 · 057 candidate differences and remaining acceptance

Completed file-by-file comparison of the signed 055 and 057 packages and mapped all 27 acceptance gaps. All 49 package-identity tests passed. Older component evidence retains its original-version scope; matching source is not final whole-package acceptance. No product changes, App rebuild or model runs occurred. Full real-device coverage, quality, five users, clean installation and official release remain open.

## 2026-10-14 · 057 controlled dataset market native acceptance

The same company-signed 057 App passed open downloads, restricted requests with waiting, denied and approved responses, invalid-structure rejection, and return to the original training draft. After the local test provider stopped, downloaded data could still be checked, imported and applied; the selection survived reopening. Field-by-field comparison confirmed that only the dataset changed, preserving the name, parameters, project and step. All 31 frontend and 73 control-service tests passed. The original library and source settings were restored, with no training or model runs. This closes controlled-source functional acceptance for AC-05. Synthetic data and operator-set test decisions do not establish external-market authorization, data or model quality, or full M4/M6 completion.

## 2026-10-14 · 057 device and data-management interface checks

The same company-signed 057 App was checked in light and dark appearance at widths of 320, 360, 736 and 1024 on the device page, and at width 320 for backup, restore, storage, diagnostics and execution-target forms. Native keyboard checks covered focus cycling, tab selection, return of focus after closing, the 20-item diagnostics limit, replacing a selection and cancelling a preview. All 40 related interface tests passed. Original data, window size and automatic appearance were restored. No training, model execution or new remote connection occurred. This covers only these interface subsets; full AC-23, real-user acceptance and M6 remain incomplete.

## 2026-10-14 · 057 media workflows and atomic advancement on the same bundle

057 has now completed two image→video→Chinese voiceover workflows in the same company-signed App. All six separate exports passed full decoding and opened or played in external applications. Native checks covered uncertain execution after interruption, exit verification, changed-input retry and downstream invalidation. The bundled service’s public API also handled concurrent advancement requests during real cancellation and natural completion: only one advancement succeeded, and replay preserved the result. All 42 workflow regression tests passed. An initial acceptance-script failure and its cancelled attempt remain recorded. No training was performed. This verifies the specified functional combination, not media quality, full M4/M6, five-user acceptance or release readiness.

## 2026-10-14 · Media failure messages and two workflow checks

056 corrects local execution verification and missing-media messages. The same company-signed candidate completed two image, video and Chinese voiceover workflows, including explicit reuse, input changes, rejection while busy, cancellation and retry after failure. Six media files were separately exported and checked in independent viewers. All 685 frontend tests passed. No training was performed. These results do not establish model quality, full M4/M6 acceptance or release readiness. 057 passes 688 frontend tests and corrects workflow history navigation in the task queue: failed, running and stop-verification entries show the selected attempt. Native checks confirmed an older failure record and return to the current workflow step. The two model workflows were not rerun on 057.

## 2026-10-14 · Local parameter and cancellation checks

The same company-signed Ver2.7 (055) completed two local inference attempts through the native UI: one verified entered parameters, the frozen recipe and a successful result; the other was cancelled during generation with process exit confirmed. All 101 related tests passed. Existing acceptance records and the daily library were preserved. No training or App rebuild occurred. The designated NVIDIA device is currently unreachable, so remote checks remain incomplete. This does not establish full feature-matrix, model-quality or release acceptance.

## 2026-10-14 · Initial technical and selection baseline completed

Consolidated technical evidence for the initial text combination on both devices, desktop lifecycle and the same cross-device adapter, and completed current selection decisions and remaining acceptance planning. Ver2.7 (055) remains a technical preview. This update changes records only; no App rebuild or model execution occurred. Completion of the technical baseline does not establish model quality, full feature-matrix, five-user, clean-install or production-release acceptance, and is not a release-date commitment.

## 2026-10-14 · Desktop lifecycle and recovery validation

The same company-signed Ver2.7 (055) passed native control-service interruption messaging, reconnection, child-process cleanup after forced App-host termination, reopening, cancelled quit and normal quit. Its bundled control service also passed lifecycle, crash/restart and failure-log checks using a path containing Chinese characters and spaces; 13 related tests passed. All acceptance-library business records were preserved, and the original library selection was restored. No model was run or App rebuilt. This desktop technical validation does not replace the complete failure matrix for running tasks, quality, real-user, clean-install or release acceptance.

## 2026-10-14 · Apple and NVIDIA technical evidence review

Verified historical four-step Apple and two-step NVIDIA LoRA training, real generation and 26 output files for the specified Qwen2.5-0.5B-Instruct, with matching base, tokenizer files and template identities; 49 related regression tests passed. The minimal training/inference technical trial passed; model quality remains unevaluated. No new training or generation, remote connection or App rebuild occurred. Remaining desktop lifecycle evidence, full milestone acceptance and production release are still pending.

## 2026-10-14 · Cross-device adapter identity and rejection checks

The 055 bundled preflight passed 1 matching case and rejected 7 mismatch cases covering the base model, template, training provenance, modules, tensor names, disguised format and missing base; 56 related regression tests passed. The existing NVIDIA→Apple artifact chain was verified across 9 files and 4 elementwise matrix transposes, completing the technical trial for the same adapter. No new training or generation ran, and the App was not rebuilt. Model quality, the full cross-device candidate-admission flow and release acceptance remain incomplete.

## 2026-10-13 · Additional native UI checks

The same company-signed Ver2.7 (055) passed checks for recovery from data-import errors with Chinese paths, long names, empty states, dialog focus return, and rejection of subtitles extending beyond the video duration. Evidence includes 11 native screenshots and 98 passing related frontend tests. No product code changed, the app was not rebuilt, and no training or inference ran. System appearance, window size, and the daily library were restored. These checks cover selected pages and states; full UI, domain quality, five real users, and release acceptance remain incomplete.

## 2026-10-13 · Quality records and test maintenance

Quality update, 2026-10-13: the existing Qwen2.5-7B-Instruct completed a baseline and two prompt trials on 50 synthetic operations records through standalone local inference, without training. The new prompts improved some fields but still omitted facts and misclassified states; the revised prompt also followed a misleading source annotation and fabricated an action and recovery. Neither prompt was adopted. These samples have been used for development and lack independent domain review, so they are not evidence of a blind test or production-quality acceptance.

Documented the failed standalone 7B prompt trials; neither prompt became an application default. Updated the data-market retry test to wait for the download button before interacting. Only tests and documentation changed; the App was not rebuilt and the signed candidate remains Ver2.7 (055). Full quality, five real-user trials and release acceptance remain pending.

## Ver2.7 (055) · 2026-10-10

Fixed remote upload disconnections being reported as control-service crashes. The actual error is retained and reconciliation does not resubmit computation. Native App testing confirmed interruption, reconciliation, reconnection and a new successful transfer, with matching returned file contents and the original record preserved.

055 corrects upload-disconnection and terminal-state messages. Native App checks covered interruption, reconciliation and a new successful transfer; the full 054 cross-device model workflow was not repeated.

Additional 055 verification: the same experimental adapter trained earlier on AGX was exported through the native UI, then independently loaded from an export copy using the bundled MLX runtime on Apple GPU. Generation succeeded, the adapter hash matched, the base model and exported files remained unchanged, and the process exited naturally. No new training was performed; quality qualification and full cross-device release acceptance remain incomplete.

Additional internal-trial checks passed for historical backup recovery, failed-migration rollback, the 054→055 package update and package rollback. All 64 content files across twelve restored export types were verified; base and quantized models and text/image adapters loaded from independent copies. A native keyboard-operated task, image/video/speech generation with the current package and cancellation after real computation were verified. These technical checks do not establish model quality, clean-install acceptance or release readiness.

## Ver2.7 (054) · 2026-10-10

Current version: **Ver2.7 (054), technical preview**. The native App has been tested through an SSH tunnel with Qwen2.5-0.5B-Instruct: Jetson Orin generation, two-step LoRA training, artifact collection and execution of the same adapter on Apple GPU. This covers only the specified model and environment and does not establish quality improvement. Direct HTTPS deployment, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet.

2026-10-07: Publish documentation in seven languages, remove internal development and acceptance logs, and rewrite user instructions. Documentation only; the App was not rebuilt.

## Ver2.6 (053)

Current version: **Ver2.6 (053), technical preview**. Selected models have been tested for inference and fine-tuning on Apple Silicon. NVIDIA cross-device workflows, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet.

- Keep keyboard focus visible after loading another page, and retain the completion indicator on the last page.
- Show field-specific numeric errors and reject invalid text-generation settings; temperature and Top-p accept valid decimals.
- Add experimental support for a fixed 7B model and block 7B quantized KV-cache combinations that failed quality checks.
- Provide content-version exports, backup and recovery, output recollection and diagnostic summaries. Full release and business-quality acceptance remain incomplete.
