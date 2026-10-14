# User guide

[简体中文](../../../docs/USER_GUIDE.md) · [繁體中文](../../zh-TW/docs/USER_GUIDE.md) · [English](USER_GUIDE.md) · [日本語](../../ja/docs/USER_GUIDE.md) · [한국어](../../ko/docs/USER_GUIDE.md) · [Français](../../fr/docs/USER_GUIDE.md) · [Português](../../pt/docs/USER_GUIDE.md)

Current version: **Ver2.7 (058), technical preview**. Ver2.7 (054) was tested in the native App through an SSH tunnel with Qwen2.5-0.5B-Instruct: Jetson Orin generation, two-step LoRA training, artifact collection and execution of the same adapter on Apple GPU. This covers only the specified model and environment and does not establish quality improvement. Direct HTTPS deployment, clean installation, first-user testing and release acceptance remain incomplete. There is no qualified public installer or automatic update channel yet. 055 corrects upload-disconnection and terminal-state messages. Native App checks covered interruption, reconciliation and a new successful transfer; the full 054 cross-device model workflow was not repeated.

Fixed the false empty-task message when matching tasks are still on later pages. Loading more reveals existing evaluations; an empty state is shown only after all tasks have loaded. All 76 relevant frontend tests passed. The same company-signed 058 App verified reopening text/image drafts in two projects, four category entries and return from existing results, plus image-result ownership when switching projects during execution. The original library was restored; no training occurred. Earlier failed quality results remain unchanged. Full device coverage, five users, clean installation and release acceptance remain incomplete.

057 has now completed two image→video→Chinese voiceover workflows in the same company-signed App. All six separate exports passed full decoding and opened or played in external applications. Native checks covered uncertain execution after interruption, exit verification, changed-input retry and downstream invalidation. The bundled service’s public API also handled concurrent advancement requests during real cancellation and natural completion: only one advancement succeeded, and replay preserved the result. All 42 workflow regression tests passed. An initial acceptance-script failure and its cancelled attempt remain recorded. No training was performed. This verifies the specified functional combination, not media quality, full M4/M6, five-user acceptance or release readiness.

Work continues as an internal trial. Additional 055 checks cover historical backup recovery, package updates and rollback, independent use of exports, a keyboard-operated task and specified media generation. Business-material review and testing by five real users remain pending; simulated results have not replaced them.

Support depends on the exact model, device, engine and precision. Check the configuration before starting. Existing quality experiments still have failures; completing training does not establish acceptable quality. Documentation is available in seven languages; the application UI is not thereby available in all seven.

## Current validation scope (2026-10-13)

| Use | Combination with real-device evidence | Limits |
| --- | --- | --- |
| Local text | Qwen2.5-0.5B-Instruct · MLX · Apple GPU | Generation, SFT + LoRA, recovery and export have technical evidence; training and quantization quality still have failures. |
| Remote text | Qwen2.5-0.5B-Instruct · Jetson Orin · SSH tunnel | 054 verified returning the same LoRA to Apple; 055 added upload recovery and loading after export, without rerunning the full cross-device chain. |
| Images | Tiny-SD · Diffusers / MPS · 512×512 | Generation and image LoRA are experimental, with known structural quality issues. |
| Video | SVD image-to-video · 14 frames · 7 FPS | Execution evidence exists for clips of about 2 seconds; motion quality remains limited. Video training is outside this scope. |
| Speech | Kokoro-82M · Chinese Xiaobei voice · CPU · 24 kHz WAV | Speech files were generated; human listening review remains incomplete. |
| Weight quantization | Qwen2.5-0.5B-Instruct · MLX 4-bit / group 64 / affine | Conversion, loading and export have evidence; candidates failing quality gates cannot be registered as qualified. |

This table lists only fixed combinations with evidence, not automatic compatibility for related models, other precisions or devices. ASR, audio/video training, merging, distillation, speculative decoding, Core ML/ANE and AMD/Intel extensions are outside the accepted scope. An entry point or installed dependency does not establish availability. No delivery candidate has passed independent domain-quality acceptance.

## 1. Getting started

Create a project in an App with its runtime already prepared, then choose text inference. You can prepare an official language model after reviewing its source, license and download manifest. After downloading, add it to the current project’s model library; alternatively, import a complete local model directory. Select the model, enter a prompt and check the configuration before starting. Save the output to find it in the content library. Downloading, importing and saving a draft do not start the model.

## 2. Tasks and parameters

Resume tasks from the workspace or task queue. Drafts save automatically; retry a failed save and confirm it succeeded. Previous results retain their original model and settings. Preview preset changes before applying them, then check again. Text settings include output limit, temperature, Top-p, seed, context budget, stop sequences and streaming. The context budget includes the template, input and reserved output; requests exceeding it are rejected. Use one stop sequence per line, up to 8 sequences of 128 characters each. Low-memory settings may be slower. 4-bit KV cache is currently blocked and is separate from model-weight quantization. Load older tasks at the end of the list; a completion indicator remains on the last page.

Smaller prompt chunks are not guaranteed to be faster and may change the output. To reproduce a result, keep the chunk limit, model, precision, sampling parameters and seed fixed.

## 3. Training and data

Language fine-tuning uses a fixed SFT + LoRA recipe; image LoRA is experimental. Check the imported format and valid supervised samples. Split training and validation data by source group to avoid leakage, preview the split and apply it; originals remain intact. Changes to data, model or parameters require another check. Freeze an evaluation plan before training and keep evaluation samples separate. Compare the base model and adapter. Results below the thresholds remain experimental adapters and cannot be registered as quality-approved candidates. Pause and resume only as confirmed by the UI and available checkpoints.

Quality update, 2026-10-13: the existing Qwen2.5-7B-Instruct completed a baseline and two prompt trials on 50 synthetic operations records through standalone local inference, without training. The new prompts improved some fields but still omitted facts and misclassified states; the revised prompt also followed a misleading source annotation and fabricated an action and recovery. Neither prompt was adopted. These samples have been used for development and lack independent domain review, so they are not evidence of a blind test or production-quality acceptance.

Valid JSON does not establish factual accuracy when summarizing business records. Check services and nodes, timestamps, completed actions, later updates and recovery evidence separately. Suggestions, negations and instruction-like source annotations must not become completed actions. The synthetic operations-record trials of 2026-10-13 did not meet adoption criteria, and their outputs still require human review; these trials were not native App quality acceptance.

## 4. Media workflows

This media scope covers image generation, short video generation and speech synthesis using the models and runtimes listed above. The image → video → speech workflow retains each step’s inputs and results. Changing an upstream input marks older downstream results as outdated. Select reuse explicitly; it is not a new generation. Current samples have quality limitations, so inspect the images, sound and video yourself.

## 5. Revisions and exports

Text and narration revisions each allow 16000 characters. Subtitles allow 200 cues, 16000 characters in total and 500 per cue. Times are in seconds, ordered, non-overlapping and within the original video duration. Text edits do not alter generation settings; narration edits do not synthesize new audio. Subtitles export as a separate VTT file, not burned into video. Select the original or a specific revision before exporting; the original-export action on a content card always exports the original. Choose a directory and review the scope. Export completes only after all files are written and verified. Adapter packages identify the exact base-model dependency without including its weights by default. Split-data exports include source text and identifiers; review the scope first.

## 6. Data market and AI assistance

Download according to the provider’s access rules. Approval does not replace integrity checks or permission to use the data. Fully downloaded versions can be checked and imported from the downloaded-data list, then explicitly selected for the task. Full commercial-market integration has not been verified. AI assistance proposes changes and shows differences; you decide whether to apply them. Applying a suggestion does not execute the task.

## 7. Backup and recovery

Create a full backup in device and environment settings after resolving running tasks, downloads and unconfirmed stops. It contains the database and referenced assets; large models need extra disk space. Restore into a new directory, then explicitly switch to that library. The original remains. A database-only migration copy is not a full backup. Older Apps may not read newer libraries; downgrade only with a compatible library and pre-upgrade backup. Storage cleanup previews its scope, handles only unreferenced assets in the current library and offers recovery.

## 8. Remote execution

Register a service address, executor ID and credentials. HTTPS certificates must be valid and match the host. A working connection does not establish GPU or model readiness. The project default affects only new text tasks; existing drafts keep their destination. Review the destination, files and total size, then explicitly confirm sending. Configuration checks do not upload files. The native App stores credentials in the system keychain; the development browser keeps them only in the current control-service session. The specified Jetson Orin workflow was tested through an SSH tunnel: generate, train, collect, save the experimental adapter, then select local Apple GPU for trial use. Direct HTTPS deployment remains unqualified; two training steps establish workflow operation only.

## 9. Troubleshooting

After a service interruption, reconnect and verify the original task. A disconnected remote task is not necessarily stopped; do not start it again. If computation finished but transfer failed, collect the existing outputs without recomputing. Partial directories from failed or cancelled exports are not complete packages. Preview the diagnostic summary in device settings before saving it. It excludes task bodies, raw logs, credentials and local paths. Report the version, reproduction steps and reviewed diagnostics without private data.

[GCSA AI Lab](../README.md)
