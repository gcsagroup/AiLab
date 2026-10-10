# GCSA AI Lab

[简体中文](../../README.md) · [繁體中文](../zh-TW/README.md) · [English](README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md) · [Français](../fr/README.md) · [Português](../pt/README.md)

GCSA AI Lab is a desktop workspace for local model inference, LoRA fine-tuning, evaluation and generated content. Each project keeps its models, data, tasks and outputs together so you can resume work and trace results.

Current version: **Ver2.7 (055), technical preview**. Ver2.7 (054) was tested in the native App through an SSH tunnel with Qwen2.5-0.5B-Instruct: Jetson Orin generation, two-step LoRA training, artifact collection and execution of the same adapter on Apple GPU. This covers only the specified model and environment and does not establish quality improvement. Direct HTTPS deployment, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet. 055 corrects upload-disconnection and terminal-state messages. Native App checks covered interruption, reconciliation and a new successful transfer; the full 054 cross-device model workflow was not repeated.

- Text generation, SFT + LoRA fine-tuning, and baseline/candidate evaluation.
- Image generation and experimental image LoRA, with video generation, speech synthesis and transcription entry points. Video and audio training are not available.
- Data import, splitting by source group, task history, content revisions, export, backup and recovery.

Support depends on the exact model, device, engine and precision. Check the configuration before starting. Existing quality experiments still have failures; completing training does not establish acceptable quality. Documentation is available in seven languages; the application UI is not thereby available in all seven.

[User guide](docs/USER_GUIDE.md) · [Changelog](CHANGELOG.md) · [GitHub](https://github.com/gcsagroup/AiLab)
