<!-- translation-navigation:start -->
[简体中文](../../../docs/08-ai-assistance-and-data-boundaries.md) · [繁體中文](../../zh-TW/docs/08-ai-assistance-and-data-boundaries.md) · [English](08-ai-assistance-and-data-boundaries.md)
<!-- translation-navigation:end -->

<a id="ai-辅助用户控制与数据边界"></a>

# AI Assistance, User Control, and Data Boundaries

Version: 1.1 · Date: 2026-09-09 · Status: Preserves the confirmed suggestion mode and adds audit constraints; real model connections remain to be implemented.

Related documents: [Product requirements](01-product-requirements.md), [Interfaces](07-api-and-task-lifecycle.md), [Data management](05-data-model-and-assets.md).

<a id="1-ai-的职责"></a>

## 1. AI Responsibilities

AI acts as an explanation and suggestion assistant within the current workflow, helping users understand models, training types, data issues, parameter tradeoffs, error logs, and evaluation differences. AI has no task-execution authority, does not judge data authorization or legality for users, and does not automatically apply suggestions to configurations.

The default message is “Suggestion mode · You decide.” The AI panel is separate from the main task workflow; collapsing it does not affect execution, and the main workflow remains usable when the connection is unavailable.

<a id="2-场景范围"></a>

## 2. Scenario Scope

| Scenario | Permitted assistance | User action | Prohibited automatic execution |
| --- | --- | --- | --- |
| Models and methods | Explain SFT / LoRA and identify unsupported combinations | Select models and methods | Automatically switch models or alter weights |
| Data preparation | Explain field, duplication, missing-data, and split issues | Review processing impact and apply | Automatically delete samples or modify originals |
| Training parameters | Suggest smaller batches, sequences, or step counts | Preview, apply, check again | Automatically start or retry training |
| Runtime optimization | Explain KV, context, MTP, DFlash, and device conditions | Prepare dependencies and apply configuration personally | Automatically restart engines or download draft models |
| Execution failure | Explain logs and list verifiable causes | Create an attempt / cancel / resume | Automatically kill processes or clear files |
| Evaluation results | Summarize baseline / candidate differences and identify untested items | Decide whether to register a candidate | Modify reports or change failures to passes |
| Data sources | Display provider materials, user declarations, and missing information | Check and complete declarations personally | Conclude “authorized” or “legally usable” |

<a id="3-建议对象"></a>

## 3. Suggestion Object

Suggestions must be structured, restricted objects; natural-language explanations must not be interpreted directly as commands. They include a suggestion ID, target object, target revision, old and new field values, reasons, impact description, and context digest.

```json
{
  "proposal_id": "proposal-001",
  "target_type": "task_draft",
  "target_id": "task-001",
  "expected_revision": 7,
  "title": "先用较小批量验证训练流程",
  "changes": [
    {
      "field": "training.micro_batch_size",
      "from": 2,
      "to": 1,
      "reason": "减少单步激活内存，先检查数据和产物链路。"
    }
  ],
  "requires_preflight": true,
  "execution_actions": []
}
```

`execution_actions` must be empty. The real implementation may omit this field from the AI-facing interface and enforce the absence of execution actions on the server.

<a id="4-预览应用和撤销"></a>

## 4. Preview, Apply, and Undo

1. Generating a suggestion does not modify the task.
2. Preview shows each field's old value, new value, reason, impact, and requirement to check again.
3. When the user clicks Apply, the server checks the target, revision, field allowlist, old values, and types.
4. Apply atomically only if all checks pass; if any fails, apply nothing and explain why.
5. After application, create an audit record and invalidate related technical checks; do not submit the task automatically.
6. Undo is allowed only if these fields have not been modified subsequently and the task remains editable.
7. If the user has already changed the same field or submitted the task, reject direct overwriting; a reviewable reverse-suggestion draft may be offered.

After switching projects or tasks, old suggestions do not automatically follow the new object. Background task completion, device changes, and new data versions also require checking whether suggestion context has expired.

After changes to the model, task mode, artifact format, speculation strategy, or execution device, suggestions must not automatically inherit dependency-preparation states. Applying suggestions and applying manual configuration use the same capability validation, field invalidation, and difference preview. The AI channel must not write old values no longer available in the current interface. Common presets are versioned configuration templates; AI can explain them or suggest a choice but cannot bypass the user's Apply action.

<a id="5-字段白名单与禁止项"></a>

## 5. Field Allowlist and Prohibited Items

The prototype allowlist includes only step counts, batch sizes, candidate budgets, input text, and a small number of data-processing choices. The production implementation may expand it incrementally by feature, but every new field requires a type, range, explanation, and undo rules.

AI suggestion objects cannot directly modify credentials, device trust, service addresses, model files, data-source declarations, original license text, access permissions, project ownership, evaluation results, candidate admission states, publication states, system settings, deletion policies, or execution-control states.

Model-file loading trust classes, workflow run / step identities, component-preparation credentials, stop confirmations, and artifact-collection conclusions are likewise determined by production services and user actions. AI cannot change collection failure to success, automatically start collection recovery or force-stop, or designate an old result as completion of this workflow run. These operations use the [dedicated contracts in 07](07-api-and-task-lifecycle.md).

Even when users ask how to configure a remote device, AI may provide only explanations and a plan to fill in manually; it must not use suggestion application to write service addresses or secret credentials.

<a id="6-本地与远程-ai-连接"></a>

## 6. Local and Remote AI Connections

Configuration includes the service source, address, model, connection state, and credential reference. Connection tests send only minimal synthetic test content, not the current dataset, media, or logs by default.

Before using a remote service, display the context scope to be sent: the question, necessary parameter summaries, redacted error excerpts, and samples explicitly selected by the user. Do not send full datasets, original media, credentials, unrelated file-system paths, or other projects' content by default.

Users can review / narrow context before sending. Local services must also display the actual connection address; an address and service-identity check cannot be skipped merely because a label says “local.” Network failure must not silently forward content to another model service.

<a id="7-数据来源与提供方访问"></a>

## 7. Data Sources and Provider Access

The system stores three independent categories of information: original descriptions published by providers, provider access-control states, and user declarations of intended use. Technical-check reports describe only file readability, field compatibility, and data-processing results.

AI may point out “no source link found,” “intended use not entered,” or “the provider has not enabled downloads,” but must not summarize any of these as a legal conclusion. An empty user declaration may be displayed as empty; inferred text such as “agreed” or “commercial use permitted” must not be inserted.

If an actual connector requires an access token or provider approval to download, the connector enforces that restriction; this is separate from whether the platform judges authorization. Download access does not automatically complete model or data publication checks.

<a id="8-不可信内容处理"></a>

## 8. Handling Untrusted Content

Data samples, model cards, READMEs, logs, webpages, and external-service responses may contain instruction-like text. They are material to analyze only and cannot change AI execution permissions or bypass field allowlists.

Commands, scripts, or “please run automatically” text in model output are not automatically executed. If the user actually wants additional work performed, it must use a separate explicit product action and checking workflow; the AI suggestion channel does not carry arbitrary tool calls.

<a id="9-审计与隐私"></a>

## 9. Audit and Privacy

Record suggestion targets, digests, model-service identifiers, field changes, user apply / undo actions, times, and results. Do not save plaintext credentials or complete sensitive samples in ordinary logs. Suggestion bodies may be retained in the project at the user's choice, with scope review available before diagnostic export.

Save raw AI responses separately from the structured changes actually applied, so “what the model suggested” can be distinguished from “what the user ultimately did.” Product quality statistics are recorded only within the user-selected scope; telemetry is not uploaded by default.

<a id="10-验收用例"></a>

## 10. Acceptance Cases

- Merely opening or requesting suggestions leaves task configuration entirely unchanged.
- Applying a suggestion changes only listed fields; unlisted source declarations remain unchanged.
- If the user edits a field before applying an old suggestion, a conflict is returned instead of overwriting it.
- If the user manually changes the same field after applying a suggestion, undo must not overwrite the latest user content.
- After task submission, its snapshot cannot be changed and AI cannot restart the task.
- Source / license questions receive organized materials and boundary explanations, not judgments made for the user.
- When a malicious sample asks to execute commands, the suggestion parser rejects execution actions.
- Remote connection tests do not send real data from the current project.
- Applying an old suggestion after changing the model or speculation strategy rejects invalid combinations without partially writing the original draft.
- An AI suggestion to use the cloud provides explanations only and does not change execution location; the actual outgoing summary matches the configuration applied by the user.

See [WP-13](10-work-breakdown.md) for the corresponding work package and [AC-15](11-testing-and-acceptance.md) for acceptance.
