<a id="gcsa-ai-lab-用户操作手册"></a>

# GCSA AI Lab User Guide

[简体中文](../../../docs/USER_GUIDE.zh-CN.md) · [繁體中文](../../zh-TW/docs/USER_GUIDE.zh-CN.md) · [English](USER_GUIDE.zh-CN.md)

This guide corresponds to the current company-signed candidate Ver2.4（033）. You can continue existing tasks, view and edit work revisions, load earlier history, and export an explicitly selected version. Body text and voiceover scripts each support up to 16000 characters, and subtitles support up to 200 entries. Acceptance for 029 covers the limited Media subset of four native instances of the three entries in two existing tasks, forward and reverse Tab, Enter/Escape with focus return, normal exit, and one stopped-state readback (E137); no real import or model run occurred. The existing limited acceptance for the four Workbench buttons in 028 remains in place. See [028 progress](implementation/2026-09-15-ver2-4-028-workbench-keyboard-progress.md), [Media progress](implementation/2026-09-15-media-keyboard-progress.md), and [candidate scope](implementation/2026-09-10-ver2-scope.md).

The fixed company-signed 033 package and native dataset workflow received limited acceptance (E143): three import rejections, 7-row import, source splitting, successful configuration checking followed by length invalidation, and direct draft restoration in the same library. Stopped-state checks found 12 new resources, 3 commands, 0 attempts, and draft revision 5; both normal exits and 47/44 protection restoration passed. No training or model generation occurred; complete M1, M0—M6, and release status do not advance. [033 dataset workflow and limits](implementation/2026-09-16-ver2-4-033-dataset-workflow.md)

The following source-stage, E142, and earlier records retain their state at the time.

032 passed keyboard operation of the subtitle functional flow, continuing/discarding edits, saving v5, and reopening the same library. Only the final cue changed across 200 cues/16000 characters, followed by explicit export of the 5-file historical v4 package. Current v5, historical v4, and the original video remained intact; both normal exits and data restoration passed. Rendering was sampled through container scrolling, and the old 020 cause remains unknown. No rebuild or model execution occurred; full AC and release status do not advance. [Subtitle workflow and limits](implementation/2026-09-16-ver2-4-032-subtitle-workflow.md)

The following E141 and earlier records preserve their state at the time.

032 verified diagnostic-directory selection, saving, and integrity checking. Cancelling the directory chooser returns to a preview that can still be saved; ending that export requires the separate diagnostic-cancellation action. Completion requires the saved-and-integrity-verified message. The diagnostic ZIP excludes this run’s trilingual training text and project/personal paths. Reopening verification covers original project data and preserved stopped-state registrations; the diagnostic dialog has no historical-receipt entry. [Diagnostic regression and limits](implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md)

The following E140 and earlier records preserve their state at the time.

032 verified selection of the original Python symlink path, saving all three environments, reopening the same build and library, and restoring bundled environments. Before saving, confirm that the displayed path matches the selected environment; cancel if it differs. Saving an external environment does not establish complete dependencies or model readiness. External probes failed in this run; restoring bundled environments showed readiness. No model or diagnostic export ran. The original 031 path failure remains in the historical record. [032 progress and limits](implementation/2026-09-16-ver2-4-032-python-path-preservation.md)

The 030 library connection-isolation fix passed source checks, signed-package verification, and two packaged real-control tests. During a switch or restart, ordinary API requests and media reads from the old connection become invalid, and writes are not automatically resent to the new library. Wait until the current connection recovers before continuing. Root acceptance covers the limited native subset of backup, rollback after target-library startup failure, successful switching, separate project saves, and reopening the same build. Asynchronous races in file, directory, and Python environment pickers remain uncovered. [030 progress](implementation/2026-09-16-ver2-4-030-connection-isolation.md)

Use Tab, Shift-Tab, Return, and Escape on the covered keyboard paths. Keyboard-only export of an original text work and reopening the same record in 027, and the four native Workbench button paths in 028, are limited acceptance results; they do not establish keyboard acceptance for every page and task. In 011, dialog focus was checked after enabling macOS Keyboard Navigation, and the original setting was restored. That condition belongs only to the [011 historical record](implementation/2026-09-13-ver2-2-011-progress.md).

Narrow-screen behavior, the independent empty library, hiding/reopening, and initial-visibility timing in 011 retain their historical attribution and are not reported as 028 performance results. Once the interface appears, wait for the applicable checks to finish before execution. The long-list blank display seen in 020 remains undiagnosed. Full acceptance for specified devices, cross-host execution, clean installation, passing quality, and five first-time users is still incomplete; see the [delivery matrix](implementation/2026-09-10-current-delivery-matrix.md).

Source-group splitting is available starting with candidate Ver2.2（006）; 005 does not include it. The related steps below passed the [specified native workflow acceptance (E72)](implementation/2026-09-10-current-delivery-matrix.md) using seven original lines and a real tokenizer, including continuation of the original preview after full backup and restore. No model was loaded for training in that run; it does not establish model quality or validation-loss acceptance.

<a id="1-获得第一个结果"></a>

## 1. Obtain your first result

1. Open the App and create a project. Each project keeps its own models, tasks, data, and works.
2. In first-use guidance, select “Prepare official language model.” Review the source, license, pinned revision, and download list before starting. The current fixed language model is approximately 953.3 MB; the interface recommends reserving approximately 2 GiB.
3. After an interrupted download, open the same record under “Model library → Model preparation records” and continue. Valid downloaded files are retained. Once the files are complete, you must still select “Add to the current project's model library.”
4. Select “Start a trial with this model,” or create a sample draft from the guidance. The sample is ordinary editable text input.
5. Select “Check configuration” to verify the model, device, and configuration. After the check passes, select “Start execution.” Downloading, registering, and saving a draft do not automatically run a model.
6. When output is complete, select “Save work.” The task and original recipe are retained automatically; the work can be viewed and exported under “Works and materials.”

You can also use “Import model” and select an existing complete model directory without downloading first. Only an exact combination that passes checks can run; complete files do not establish answer quality.

<a id="2-修改任务与运行设置"></a>

## 2. Modify tasks and execution settings

1. Select a category in the workbench, then choose “Continue last execution” or “Continue last training.” You can also open a specified task from “Tasks and results” or the top-right “Task queue.” Use “New trial” or “New training” to create another task. “Load more tasks” at the end of the list loads older records.
2. Modify the input or expand “Execution settings.” Drafts save automatically. If saving fails, select “Save draft” to retry and confirm “Draft saved” before continuing. Old results still correspond to the model and parameters used in their original execution.
3. To use a preset, select an “Execution preset,” choose “Preview preset differences,” then confirm “Apply to draft.” Applying changes configuration only; it does not run the model.
4. Select “Check configuration,” then explicitly select “Start execution” or “Start training” after it passes. Configuration remains read-only during execution, pausing, or verification of an uncertain stop state. Resolve the original execution before editing further.

Language generation supports maximum output, temperature, Top-p, seed, total context budget, stop sequences, and streaming display. The context budget includes the template, input, and reserved maximum output. Over-budget execution is rejected while retaining input. Only a single input is currently provided; conversation history is not trimmed, and the fixed Qwen2.5 combination has no thinking switch.

Use one stop sequence per line, with at most 8 sequences and 128 characters per sequence. Empty lines are ignored; leading and trailing spaces are retained. A match stops generation and is excluded from display. Disabling streaming changes display timing only; the final result, execution state, and stop operation remain available.

Prefer the default configuration when establishing a baseline. Low-memory presets may increase time to the first token; low-latency effects depend on the input and device. Existing quality verification for 4-bit KV cache failed, so it cannot currently be selected. KV-cache quantization and model-weight quantization are different features.

<a id="3-微调与评测"></a>

## 3. Fine-tuning and evaluation

Select “Training / fine-tuning” in the language or image workbench. Import the base model and data, check samples and parameters, then explicitly start. Language training currently uses fixed SFT + LoRA; image training uses Tiny-SD LoRA. Video and audio training are not available.

The language training form verified in candidate 005 reads parameter ranges from the recipe for the current execution location and displays the default source, fixed batch size, and step-based stopping condition. Reading a recipe does not check the device, connect remotely, or overwrite entered values. If reading fails or existing values exceed the current range, correct them or reload the recipe before checking configuration. Both the current local and NVIDIA combinations allow at most 200 steps, a per-device batch size of 1, gradient accumulation of 1, and a single data-parallel device. The NVIDIA learning rate must be at least 0.000001, and LoRA Alpha must be an integer. The local combination retains its own ranges; switching location does not silently reduce incompatible values.

For language-quality acceptance, create and freeze an evaluation plan before training and bind it to the training draft. Keep evaluation and training sets separate, with questions covering business behavior, format, normal capabilities, and target behavior. Completed training only means that an independent adapter was produced; an artifact that misses the standard remains an experimental adapter.

Evaluation loads the baseline and candidate separately and displays each output and judgment. An ad hoc post-training comparison may support analysis, but cannot replace the predetermined admission plan. Use a candidate as “quality passed” only after it meets the predetermined thresholds and is explicitly registered; that conclusion applies only to the corresponding model, evaluation set, and device.

For training that supports pause, wait until the interface confirms it is paused before continuing. After stopping, a recovery task can be created if a usable checkpoint exists; it retains provenance and the fixed training configuration. If the stop state needs verification, first verify or collect the original execution to avoid starting duplicate computation.

<a id="31-按来源组准备语言训练数据006-候选新增"></a>

### 3.1 Prepare language-training data by source group (added in candidate 006)

Original data uses UTF-8 JSONL, with only `source_id` and `messages` on each line. `source_id` is a nonempty source identifier. Different questions and answers derived from the same original record must use the same value; do not invent a different source for every variation merely to obtain a split. All valid samples from one source group remain together on either the training or validation side. The three lines below show two variations from the same source and one independent source:

```jsonl
{"source_id":"订单-001","messages":[{"role":"user","content":"订单001什么时候发货？"},{"role":"assistant","content":"订单001将在周五发货。"}]}
{"source_id":"订单-001","messages":[{"role":"user","content":"请确认001号订单的发货日。"},{"role":"assistant","content":"发货日是周五。"}]}
{"source_id":"订单-002","messages":[{"role":"user","content":"订单002可以修改地址吗？"},{"role":"assistant","content":"订单002尚未发货，可以修改地址。"}]}
```

1. Under “Dataset market → My data,” select “Import language data” and choose the original file, then select “Split training and validation” on its card. The same entry point is available after selecting the original in a training draft.
2. Select the model for tokenization checks, maximum sequence length, fixed split seed, and validation ratio. Currently supported tokenization material is from the fixed original Qwen2.5-0.5B-Instruct weights. The length must match the later training configuration.
3. Select “Check and preview split.” This tokenizes on the CPU and checks supervision scope without loading model weights or training. Review valid and excluded samples, source-group and sample counts on both sides, requested and actual validation ratios, exclusion reasons, and the scope of new files. Expand up to three token/supervision-label evidence items if needed.
4. Once there are no blockers, select “Apply split and generate new versions.” This registers independent training and validation subsets and a provenance proof, while retaining the original. The training draft has not yet changed automatically.
5. In the training draft's split dialog, select “Use training subset,” or select “Use for training” on the training-subset data card. Save the draft, then “Check configuration,” and finally start training explicitly. Other entered parameters remain unchanged and must still satisfy the ranges for the current model and execution location.

New language SFT training must use the training subset (`train`) of an applied split. The original, validation subset, and unapplied preview cannot be submitted directly for new training. If model tokenization material or maximum sequence length changes, check and split again from the original. Existing historical checkpoints resume only under their originally frozen configuration and do not gain source-group isolation proof through this feature.

Samples with zero supervision, excessive length, or unsupported media/tool content are excluded first. An overlong sample is excluded in full rather than shortened and mixed into training. At least two independent source groups containing valid samples are required, and both sides must be nonempty. Splitting is group-based, so the actual sample ratio may differ from the request. Identical normalized user prompts on both sides block application. Semantic near-duplicate removal has not been checked; the person preparing the data must still verify the source identifiers.

The validation subset currently supports holdout isolation and checking. Validation loss has not been computed, and the subset does not replace independent quality evaluation or prove model quality. Default NVIDIA training uploads include only the training subset; the split proof is pinned with the training configuration.

<a id="32-找回预览与处理检查中断"></a>

### 3.2 Recover previews and handle interrupted checks

Once a preview is ready, the dialog may be closed. Open “Split training and validation” again from the original and load its record under “Existing checks and previews.” Continue there after restarting or restoring a library as well; reading a record does not tokenize again, apply a split, or train.

To stop a check, select “Cancel this check and preview” and wait for confirmation. If the interface says “The previous check was interrupted,” cancel the old plan and verify its result first. Select “Keep parameters and preview again” only when a new check is needed. After a connection interruption, reread the original record or select “Retry the last operation” rather than repeatedly creating new records. If an applied result reports remaining temporary files, use “Retry temporary cleanup.” The formal subsets are already registered; this does not create a second split.

<a id="4-图片视频配音与工作流"></a>

## 4. Images, video, voice-over, and workflows

Generate images from text descriptions. Video uses an imported PNG image, or a saved image assigned to a video task. The current fixed video combination produces an approximately two-second clip; existing samples show weak motion. Chinese voice-over uses the fixed Xiaobei voice. Generated files can be played and exported, but their content and pronunciation still require review.

The product workflow executes image, video, and voice-over steps separately. Check each step before starting and accept that run's result before proceeding. Reusing an old result requires explicit selection and source confirmation. Changing an upstream step marks downstream steps stale and requires rechecking. Saving the whole workflow saves three separate works; composing a single finished video with voice-over is not currently available.

<a id="5-修订与导出"></a>

## 5. Revisions and export

1. On a work card in “Works and materials,” select “Text revision,” “Voice-over script revision,” or “Subtitle revision.” The dialog opens on the current version. Use “View work version” to select the original or a loaded revision and view its content, parent version, and differences from the parent.
2. Initially, at most 100 recent revisions are listed. Select “Load earlier versions” for older records; the version being viewed stays selected. Repeat until the required record is available. If a newer revision is reported, select “Reload work versions,” then select the version to view again.
3. To edit, select the current version and then “Edit current version.” Focus moves to the first editable field, or “Add subtitle” when there are no subtitles. Choose “Save independent revision” when finished. To discard the edits, choose “Cancel this edit”; focus returns to the edit button, and Return can reopen editing immediately. Saving adds an independent version while retaining the original and earlier revisions. If saving reports another revision, entered content is retained; only after deciding it is no longer needed should you choose “Discard this edit and read the current version.”
4. Escape during editing displays an exit confirmation and focuses “Continue checking.” Return goes back to the previous input if it remains available. Select “Discard unsaved edits and close” only when explicitly discarding.

| Content | Limit |
| --- | --- |
| Text body, voice-over script | 16000 characters each |
| One subtitle cue | 500 characters |
| All subtitles in one work | At most 200 cues, with at most 16000 characters in total |

Check the count displayed in the interface. The supplementary Chinese character “𠮷” counts as one character. Over-limit input is not truncated early, but must be reduced to the limit before saving. Subtitle start and end times use seconds, must be chronological and nonoverlapping, and must stay within the original video's duration.

Long subtitles can be scrolled page by page, and “Differences from parent version” can be collapsed to shorten the content. In 021, page-wise, large, and boundary scrolling with differences expanded/collapsed were checked: the background works page stayed in place, and remained scrollable after the dialog closed. The cause of the two blank frames in 020 is still unknown. If it recurs, try ordinary one-page up/down scrolling and retain an issue record; recovery does not establish that the issue is fixed.

Text revisions do not change the original generation recipe. Voice-over script revisions do not change the audio. Subtitles are saved as a separate VTT file and are not burned into the video. The dialog's player always plays the original media.

To export a revision, first select the original or a specific revision under “View work version,” then choose “Export selected original” or “Export selected revision N.” “Export original work” on the work card always exports the original. Choose a destination, check the file scope, and finally select “Start export.” Completion and the saved location appear only after all files are written and verified. Exporting an older revision does not silently switch to the current version. Revision exports retain the original media, independent text/subtitles, and version records.

Models, adapters, and evaluation reports have separate export entry points. Adapter packages identify the exact base model they require and do not include base weights by default. Prepare compatible engines and dependencies according to the manifest before using them in other tools. Temporary or incomplete directories are not complete export packages.

In 006 and later candidates, training/validation subset cards offer “Export split,” and the split dialog offers “Export original, subsets, and proof.” Review the preview before explicitly exporting. The data package includes the original, both subsets, source-group/checking proof, and object descriptions; original text and source identifiers are exported together. Exporting does not split again or train. Ordinary training reports and adapter packages carry only the pinned split identity and list the complete data package as an external dependency. They do not attach originals or validation data by default, and contain no validation-loss result.

<a id="6-数据市场与-ai-辅助"></a>

## 6. Dataset market and AI assistance

Open the dataset market from a training draft to review provider entries, versions, and access conditions. Entries requiring access approval must wait for the provider. After approval, download and check the data, then return to the original draft to use it. Other task parameters are preserved; selecting data does not start training.

Only a controlled test provider was verified in this batch. That does not establish connection to a commercial data market. Downloaded files, usage declarations, and provider authorization are retained separately and do not substitute for one another.

AI assistance only proposes suggestions. Review their differences from the draft before deciding to apply them; after application, checking and starting the task remain manual. A failed suggestion or invalid response format leaves the original draft intact. Actual verification currently covers local-model suggestions; unopened remote connections do not inherit that conclusion.

<a id="7-备份恢复与故障处理"></a>

## 7. Backup, restore, and failure handling

Create a full backup from “Devices and environment → Backup and restore.” Finish executions or stop downloads first. Backups include the database, referenced assets, original execution records, and download cache after stopping. Copying large models takes time.

To restore, select a backup and destination directory, review the checks, and choose “Restore to a new directory.” Completion does not automatically replace the current library. After confirming its use, select “Switch to the restored library.” The original library is retained; new executions in the restored library use this App's bundled environment.

006 and later candidates use library v4. Full backups include source-group originals, both subsets, proofs, and their relationships. Ready previews that have not been applied are also retained. After restoring to a new directory, the original preview can be read and explicitly applied without tokenizing again or training. Resolve records that are checking, cancelling, or awaiting stop confirmation before backup or cleanup. Missing files or inconsistent split relationships block backup/restore.

Storage cleanup lists the exact files and sizes before explicit execution. It currently moves only unreferenced assets within the library and provides a restore entry point. Original execution evidence and downloads outside the library are outside the cleanup scope.

After installing or restoring an environment, select “Refresh environment” under “Devices and environment” to probe again. The button is disabled while waiting; a failed probe shows the reason and can be retried. The current project and unsaved input are retained.

After a service interruption, reconnect and inspect the original task first. If state verification or artifact collection is pending, verify and collect through that task; collection does not rerun training or inference. For diagnostics, preview the included and excluded scope under “Devices and environment → Export diagnostic summary,” then choose a destination. Diagnostics contain only a limited status summary, without task content, raw logs, credentials, or local paths.

Starting in 005, the latest 32 environment probes in the current control-service session record results, durations, exit codes, and completion times, distinguishing timeout, launch failure, abnormal exit, and invalid output. In 023, waiting, identity checks, and cache results during service environment checks are also recorded to locate elapsed time. Diagnostic preview reads existing records without probing again; records may reflect old configuration and are cleared on service restart. They explain why a previous check failed but do not establish current device readiness.

<a id="8-执行目标与文件传输"></a>

## 8. Execution targets and file transfer

Under “Devices and environment → Execution targets,” register an already running independent execution service with its target name, connection address, executor identifier, and access credential. An HTTPS address contains only the host and optional port, for example `https://执行服务主机:端口`; the existing `http://127.0.0.1:端口` loopback mode remains available. The address and identifier jointly pin target identity. The native App stores target credentials in the system keychain; the development browser retains them temporarily in the control service, requiring re-entry after service restart. Clearing credentials retains the target record; reconnecting requires configuration again.

An HTTPS service needs a separate execution directory and explicit bind IP, certificate chain, and private key; see the [execution-service preparation example](implementation/2026-09-10-remote-nvidia-evidence.md#执行服务准备示例). The certificate must validate against the public CA bundle shipped with the runtime, match the registered host, and remain within its validity period. Verification failure displays a reason and sends no project files.

“HTTPS protocol connection verified” or “Loopback protocol connection verified” means identity and the transfer protocol are available. Local TLS protocol verification has been completed, HTTPS is included in the signed 005 package, and native certificate rejection and the target interface have been verified. Trusted certificates across hosts and real NVIDIA hardware still require acceptance. NVIDIA tasks also need actual device and model checks; submission is blocked when no usable device is available.

“Default location for new text tasks” affects only text-generation and training drafts subsequently created in this project. Existing drafts retain their original location; change it separately under a task's “Execution location” if needed, and recheck after every change. The initial remote combination uses fixed original Qwen2.5-0.5B-Instruct weights, Transformers, CUDA, and BF16. Input can be retained before checks, while unsupported adapter/checkpoint combinations are explicitly rejected.

Review the target, files to send, total size, and SHA digests in the check results before selecting “Confirm sending and start execution/training.” Checking does not upload models automatically. Only an explicit start transfers the listed files and this execution's input. Execution records and recipes retain the actual target; credentials do not enter recipes.

To verify only the connection and files, select “Verify file transfer” for a target, choose data or material already imported into the current project, select “Check sending scope,” then “Start transfer verification.” This saves a copy and verifies received content without model computation. “View transfer records” and “Load earlier transfer records” let you continue checking the same target's history.

After disconnection or certificate failure, the displayed state is the last obtained state and does not prove that the remote execution stopped. Repair the connection and choose “Reconnect and verify original execution” on the same record. Cancellation also uses the original identifier; execution is stopped only after remote process exit is confirmed. If computation finished but reception failed, use “Collect existing artifacts only” to retrieve and verify files against the original sealed manifest without rerunning the model.

<a id="9-安装与更新状态"></a>

## 9. Installation and update status

Development, native testing, and execution in this batch use one App path. Every full candidate build increments the number in parentheses. “Technical preview” describes acceptance status rather than the feature version. Apple Silicon / macOS 26 and later is the current system scope awaiting final-candidate verification.

The local candidate update tool first creates a plan covering both versions, signatures, files, and the current database, then requires explicit replacement. The old package and database backup are retained. See [desktop build and update instructions](../scripts/desktop/README.md). That database backup does not contain models or other assets and does not replace the full backup under “Backup and restore.”

005 uses library v3. 006 and later candidates upgrade libraries to v4, saving a consistent database copy before migration. 005 refuses to open v4, so replacing the App with the old version cannot directly downgrade the library. To return to an older version, use the compatible library and full backup retained before upgrading. A migration copy contains only the database and is not an asset backup. The earlier 0.1.0 package likewise cannot read v3 libraries directly.

Real installation, upgrade, and failed-update rollback results for the final candidate will accompany the corresponding signed package. There is currently no automatic-update release channel. This guide does not establish acceptance for installation on an independent machine or formal distribution.
