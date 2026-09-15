<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/02-user-flows-and-ui.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/02-user-flows-and-ui.md) · [English](02-user-flows-and-ui.md)
<!-- translation-navigation:end -->

<a id="用户流程与交互规格"></a>

# User Flows and Interaction Specification

Version: 1.0 · Date: 2026-09-09 · Status: prototype structure is established; the following real-operation specifications await implementation.

Related documents: [Product requirements](01-product-requirements.md), [Task lifecycle](07-api-and-task-lifecycle.md), [Run configuration](04-runtime-and-hardware.md).

<a id="1-信息架构"></a>

## 1. Information architecture

```text
AiLab
├── 工作台
│   ├── 语言与多模态模型
│   ├── 图片模型
│   ├── 视频模型
│   └── 音频模型
│       各类别：训练／微调 | 运行／试用 | 任务与结果
├── 模型库
│   ├── 模型
│   └── 工作流
├── 数据集市场
│   ├── 发现数据
│   └── 我的数据
├── 模型实验室
│   ├── 行为调整／破甲对照
│   ├── 知识蒸馏
│   ├── 模型合并
│   ├── 模型量化
│   └── 格式转换
├── 作品与素材
├── 设备与环境
└── AI 连接
全局：项目选择 | 任务队列 | AI 辅助
```

The model lab does not duplicate ordinary training entry points. Ordinary training takes place in the four-category workbench; the lab handles specialized tasks that change a model's form, composition, or behavior.

<a id="2-工作台首页"></a>

## 2. Workbench home

<a id="21-页面内容"></a>

### 2.1 Page contents

- Four entry cards show categories, applicable goals, and common methods, with the consistent primary action “Start training/fine-tuning.”
- “Continue recent task” shows the current project's latest task name, identifier, category, state, and next action.
- State-dependent actions use user-facing language: continue configuration, view run, continue evaluation, or view failure reason.
- Secondary entries link to the model library, dataset marketplace, and model lab rather than adding another “Creative Space” navigation system.

<a id="22-继续任务规则"></a>

### 2.2 Rules for continuing tasks

Prefer restoring the last selected draft in this project and category. Create a new task when no draft exists; allow viewing an executing task, but never treat its parameters as an editable draft. Explicitly choosing “New training task” always creates a new ID.

Preserve each project's recent selections, drafts, and history when switching projects. Returning restores the original context; background completion updates the owning project's task without forcing the user away from the current page.

<a id="3-路径-a语言模型-sft--lora"></a>

## 3. Path A: Language-model SFT + LoRA

| Step | User action | Page feedback | Validation/failure handling |
| --- | --- | --- | --- |
| A1 | Select language and multimodal on the workbench | Open the current training draft | Create one if no draft exists |
| A2 | Select a base model | Show input types, version, and training capabilities | Direct unprepared models to the preparation entry |
| A3 | Select SFT and LoRA | Show required data and the adapter artifact | Explain unsupported combinations |
| A4 | Select or import data | Preview actual samples, fields, and versions | Incompatible data cannot be used |
| A5 | Check and decide on cleaning | Show missing data, duplicates, splits, and media issues | Applying cleaning creates a data version and triggers rechecking |
| A6 | Set steps, batch size, learning rate, and environment | Show training parameters and a dependency summary | OOM is only a predicted risk; do not fabricate actual free VRAM |
| A7 | Check and start | Show model, data, device, cost source, and final settings | Unsupported fields or disconnected devices block submission |
| A8 | Execute | Actual logs, progress, and available checkpoints | Preserve failure evidence; retry creates a new attempt |
| A9 | Evaluate | Compare baseline and candidate on fixed samples | Failed candidates cannot be registered as usable |
| A10 | Register and try | Carry the candidate model forward and retain an entry to its source experiment | Model loading failure returns to artifact checking |

“Configuration” has three steps: model and method, data preparation, and parameters and environment. Task-level tabs are configuration, run, evaluation, and artifacts. Configuration becomes read-only after submission; changes use “Copy as new attempt.”

<a id="4-路径-b从模型库直接运行"></a>

## 4. Path B: Run directly from the model library

1. Filter the model library by category and format, and inspect the model's provenance, version, and run requirements.
2. If components are missing, start a download/preparation task; users may leave the page and view progress in the queue.
3. Once preparation completes, click Run to enter the corresponding category's run/trial page with that model selected.
4. Enter a question or prompt; select and preview materials when media is required.
5. Open “Run parameters and optimization,” edit the grouped draft, and click “Check and apply.”
6. Return to the main form, check the summary, and then choose Send, Generate, Start transcription, or the applicable action.
7. Results appear on the current page and enter the current project's history; users may save, compare, inspect recipes, or load them for further editing.

A downloaded model is not necessarily loadable by the engine. The real application distinguishes “Files complete,” “Format compatible,” “Loaded,” and “Run passed” in the model list. Clicking Run requires a loading check.

<a id="5-路径-c运行参数与优化"></a>

## 5. Path C: Run parameters and optimization

<a id="51-入口和分组"></a>

### 5.1 Entry points and groups

The main input area persistently displays a “Run parameters and optimization” summary with key parameters such as engine, hardware backend, context, and output limits. Provide shortcuts for “Full settings,” “Devices and engines,” and “Caching and acceleration.”

Language and multimodal settings have five groups: generation and context, KV Cache, Prefill/Decode, speculative decoding, and devices and engines. Media-model settings are generation and acceleration, and devices and engines; language parameters unrelated to that model are not shown.

<a id="52-编辑交互"></a>

### 5.2 Editing interactions

- Opening the dialog copies the current configuration into an independent editing draft; Cancel, Close, and Escape all discard unapplied changes.
- Changing a device or engine recalculates applicable settings, preserves generation parameters that retain the same meaning, and displays a summary of optimization changes.
- Inapplicable options show reasons and preparation actions; selected-but-ignored states are not allowed.
- “Check and apply” returns field errors and correctable causes; success closes the dialog and refreshes the summary without immediately generating anything.
- During execution, the submitted configuration is read-only; users may create a separate run draft but cannot rewrite the submitted snapshot.

<a id="53-关键异常"></a>

### 5.3 Key exceptions

| Condition | Message and handling |
| --- | --- |
| Input plus output exceeds context | Show the actual token budget; reject or truncate according to the user's choice, explaining retained/deleted content |
| Model does not support disabling thinking | Disable the toggle and explain template/model restrictions; hiding tags is not equivalent to disabling thinking |
| MTP lacks its matching prediction component | Explain the missing model capability and available engines; do not allow submission of this optimization |
| DFlash draft is not prepared | Direct users to preparation of a matching draft and preserve existing configuration |
| Original weights selected for ANE | Explain the requirement for a Core ML converted artifact; do not claim ANE acceleration of the original weights |
| Engine change invalidates KV format | Show before and after values and require the user to apply the new draft |
| Remote service disconnects | Preserve the draft and received results; enter connection checking/task reconnection |

<a id="6-路径-d图像--视频--配音工作流"></a>

## 6. Path D: Image → video → narration workflow

Open the model library's workflow page and select “Product image → video → narration.” Details show the three steps, required models, and preparation state. Missing dependencies may be prepared, but the workflow cannot be loaded directly for execution.

The first step generates a product image, which remains an image-task artifact. When the user sends it to the next step, the video task references the image's asset identifier rather than copying a temporary file without provenance. Narration is generated after the video completes; each step can be checked, redone, or paused and continued. Final saving stores the workflow record and references to every selected artifact.

The first real workflow uses step-by-step confirmation, not automatic background sequencing. Failure at any step retains earlier successful results; after redoing a step, old downstream results display “Based on old input” and must not automatically become the new version. Composited audiovisual export is an additional capability; separate video and audio files do not mean a final finished video has been produced.

<a id="7-路径-e数据市场与原任务返回"></a>

## 7. Path E: Dataset marketplace and return to the original task

1. Open the marketplace from the training data step, recording the original project, task, category, and configuration step.
2. Open details to inspect format, samples, version, provider text, access conditions, and user declarations.
3. Open data can be downloaded; restricted data first requires an intended-use request for the provider to process.
4. After downloading, choose “Use in current task”; disable this action for incompatible formats and explain the required format.
5. Return to the original task, preserving its name, configured parameters, and location; new data invalidates old technical checks.
6. If the user instead chooses new training, explicitly create a new task without overwriting the original.

Provider approval to download changes only the access state; it does not create an “AI-confirmed authorization” label. After importing JSONL, switch the list to the new data's type and highlight the imported result so that imported data does not become invisible.

<a id="8-路径-f模型实验室与候选"></a>

## 8. Path F: Model lab and candidates

Specialized entry points first explain inputs, methods, and artifacts. Behavior adjustment may select Heretic, Abliterix, or a comparison; distillation selects teacher and student; merging selects compatible inputs and weights; quantization selects format and calibration scheme; conversion selects target format and compute environment.

After execution, all enter evaluation and artifacts. Each candidate independently displays state and provenance. Original models and candidates use the same sample set; a candidate below threshold may retain a report and start a new attempt after adjustment, but changing its displayed state alone cannot make it eligible for registration.

Converted/quantized artifacts can be used for execution; further training returns to source weights. Adapters declare subsequent conversion chains allowed by the real product; the Demo's simplified `runtimeOnly` restriction must not be generalized into a permanent ban on converting all runtime artifacts.

<a id="9-全局交互规则"></a>

## 9. Global interaction rules

<a id="91-空态加载和错误"></a>

### 9.1 Empty states, loading, and errors

Empty states explain what is missing and provide one primary action. Downloads, checking, preprocessing, loading, and generation use distinct state text. Long operations show whether they can be cancelled and their current stage; continuously increasing fake progress must not replace unknown progress. Errors first identify correctable fields while retaining expandable technical details.

<a id="92-表单与持久化"></a>

### 9.2 Forms and persistence

Units immediately follow labels, such as token, seconds, Hz, and GB; 0, automatic, unlimited, and unspecified have different meanings. Option changes must not cause users to lose focus while typing. Draft saving shows the latest save state; leaving the page prompts for action only when persistence of changes has failed.

<a id="93-弹窗与响应式"></a>

### 9.3 Dialogs and responsive layout

Global settings belong to the application, while run parameters belong to the current task. Dialogs have clear titles, Close, Cancel, and primary actions; real clients need focus containment and focus restoration after closing. Narrow layouts use a single column and wrapping tabs, with primary actions not hidden by overflow; multi-column comparison tables may scroll horizontally within their own area, but the overall page must not overflow horizontally.

<a id="94-结果比较"></a>

### 9.4 Result comparisons

Comparisons show at least the model, version, input, seed, key run settings, and result. Different inputs or quantization methods require prominent labels and must not be presented as strictly fair comparisons. Image comparisons retain size and crop conditions; audio comparisons support independent playback; video comparisons retain frame rate, duration, and provenance.

<a id="10-首次使用引导"></a>

## 10. First-use guidance

On first launch, provide three actionable steps: prepare a model, check the device, and complete a sample task. Users may skip them and browse the interface. Sample tasks must identify sample data and simulated/real mode; real mode with missing dependencies points to preparation steps.

Provide brief explanations beside training methods; context, KV, Prefill, and other settings show units, effects, and applicable scope. Detailed technical material belongs in expandable help and must not force users to read API fields or environment commands to complete basic operations.

<a id="11-交互验收"></a>

## 11. Interaction acceptance

Interaction acceptance means more than “buttons can navigate.” Complete a real user task from an explicit entry point and verify the final result, saved data, provenance chain, and reopening. Key paths map to [AC-01—AC-24](11-testing-and-acceptance.md); gaps between prototype and product appear in [14](14-prototype-traceability.md).
