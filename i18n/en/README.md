# GCSA AI Lab

[简体中文](../../README.md) · [繁體中文](../zh-TW/README.md) · [English](README.md) · [日本語](../ja/README.md) · [한국어](../ko/README.md) · [Français](../fr/README.md) · [Português](../pt/README.md)

GCSA AI Lab is a desktop workspace for local model inference, LoRA fine-tuning, evaluation and generated content. Each project keeps its models, data, tasks and outputs together so you can resume work and trace results.

Current version: **Ver2.7 (057), technical preview**. Ver2.7 (054) was tested in the native App through an SSH tunnel with Qwen2.5-0.5B-Instruct: Jetson Orin generation, two-step LoRA training, artifact collection and execution of the same adapter on Apple GPU. This covers only the specified model and environment and does not establish quality improvement. Direct HTTPS deployment, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet. 055 corrects upload-disconnection and terminal-state messages. Native App checks covered interruption, reconciliation and a new successful transfer; the full 054 cross-device model workflow was not repeated.

056 corrects local execution verification and missing-media messages. The same company-signed candidate completed two image, video and Chinese voiceover workflows, including explicit reuse, input changes, rejection while busy, cancellation and retry after failure. Six media files were separately exported and checked in independent viewers. All 685 frontend tests passed. No training was performed. These results do not establish model quality, full M4/M6 acceptance or release readiness. 057 passes 688 frontend tests and corrects workflow history navigation in the task queue: failed, running and stop-verification entries show the selected attempt. Native checks confirmed an older failure record and return to the current workflow step. The two model workflows were not rerun on 057.

Work continues as an internal trial. Additional 055 checks cover historical backup recovery, package updates and rollback, independent use of exports, a keyboard-operated task and specified media generation. Business-material review and testing by five real users remain pending; simulated results have not replaced them.

Quality update, 2026-10-13: the existing Qwen2.5-7B-Instruct completed a baseline and two prompt trials on 50 synthetic operations records through standalone local inference, without training. The new prompts improved some fields but still omitted facts and misclassified states; the revised prompt also followed a misleading source annotation and fabricated an action and recovery. Neither prompt was adopted. These samples have been used for development and lack independent domain review, so they are not evidence of a blind test or production-quality acceptance.

- Text generation, SFT + LoRA fine-tuning, and baseline/candidate evaluation.
- Image generation and experimental image LoRA, with video generation, speech synthesis and transcription entry points. Video and audio training are not available.
- Data import, splitting by source group, task history, content revisions, export, backup and recovery.

Support depends on the exact model, device, engine and precision. Check the configuration before starting. Existing quality experiments still have failures; completing training does not establish acceptable quality. Documentation is available in seven languages; the application UI is not thereby available in all seven.

[User guide](docs/USER_GUIDE.md) · [Changelog](CHANGELOG.md) · [GitHub](https://github.com/gcsagroup/AiLab)
