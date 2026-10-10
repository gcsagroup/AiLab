# Changelog

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](../fr/CHANGELOG.md) · [Português](../pt/CHANGELOG.md)

## Ver2.7 (054) · 2026-10-10

Current version: **Ver2.7 (054), technical preview**. The native App has been tested through an SSH tunnel with Qwen2.5-0.5B-Instruct: Jetson Orin generation, two-step LoRA training, artifact collection and execution of the same adapter on Apple GPU. This covers only the specified model and environment and does not establish quality improvement. Direct HTTPS deployment, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet.

2026-10-07: Publish documentation in seven languages, remove internal development and acceptance logs, and rewrite user instructions. Documentation only; the App was not rebuilt.

## Ver2.6 (053)

Current version: **Ver2.6 (053), technical preview**. Selected models have been tested for inference and fine-tuning on Apple Silicon. NVIDIA cross-device workflows, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet.

- Keep keyboard focus visible after loading another page, and retain the completion indicator on the last page.
- Show field-specific numeric errors and reject invalid text-generation settings; temperature and Top-p accept valid decimals.
- Add experimental support for a fixed 7B model and block 7B quantized KV-cache combinations that failed quality checks.
- Provide content-version exports, backup and recovery, output recollection and diagnostic summaries. Full release and business-quality acceptance remain incomplete.
