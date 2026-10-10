# Changelog

[简体中文](../../CHANGELOG.md) · [繁體中文](../zh-TW/CHANGELOG.md) · [English](CHANGELOG.md) · [日本語](../ja/CHANGELOG.md) · [한국어](../ko/CHANGELOG.md) · [Français](../fr/CHANGELOG.md) · [Português](../pt/CHANGELOG.md)

2026-10-10 (source update, not yet packaged): Added a fixed Jetson Orin environment and corrected CUDA workspace cleanup. Qwen2.5-0.5B-Instruct passed generation, two LoRA training steps and independent loading of the same exported adapter on an Apple GPU. These checks do not establish improved model quality or acceptance of the complete cross-device App workflow.

2026-10-07: Publish documentation in seven languages, remove internal development and acceptance logs, and rewrite user instructions. Documentation only; the App was not rebuilt.

## Ver2.6 (053)

Current version: **Ver2.6 (053), technical preview**. Selected models have been tested for inference and fine-tuning on Apple Silicon. NVIDIA cross-device workflows, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet.

- Keep keyboard focus visible after loading another page, and retain the completion indicator on the last page.
- Show field-specific numeric errors and reject invalid text-generation settings; temperature and Top-p accept valid decimals.
- Add experimental support for a fixed 7B model and block 7B quantized KV-cache combinations that failed quality checks.
- Provide content-version exports, backup and recovery, output recollection and diagnostic summaries. Full release and business-quality acceptance remain incomplete.
