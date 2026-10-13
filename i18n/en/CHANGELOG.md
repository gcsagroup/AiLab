# Changelog

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](../fr/CHANGELOG.md) · [Português](../pt/CHANGELOG.md)

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
