<!-- translation-navigation:start -->
[简体中文](../../../docs/05-data-model-and-assets.md) · [繁體中文](../../zh-TW/docs/05-data-model-and-assets.md) · [English](05-data-model-and-assets.md)
<!-- translation-navigation:end -->

<a id="数据模型作品与版本管理"></a>

# Data, Models, Works, and Version Management

Version: 1.1 · Date: 2026-09-09 · Status: Data specification revised following the audit; both the prototype's in-memory objects and the new contracts remain to be implemented.

Related documents: [Training](03-training-and-model-lab.md), [Interfaces](07-api-and-task-lifecycle.md), [AI and declaration boundaries](08-ai-assistance-and-data-boundaries.md).

<a id="1-领域对象与关联"></a>

## 1. Domain Objects and Relationships

| Object | Display name | Key fields | Relationships / invariants |
| --- | --- | --- | --- |
| Project | Project | id, name, created_at, archived_at | Tasks and evaluations belong to a project; the display name can change |
| Model | Logical model entry | id, name, family, modality | Contains multiple fixed ModelVersion objects |
| ModelVersion | Model version | revision, artifact_ids, format, tokenizer, processor, base_id, load_policy_ref | Once complete, the referenced weights and loading trust record cannot change |
| ModelImportPlan | Model import plan | id, manifest_digest, detected_format, loader, trust_class, execution_scope, decision_ref | Can be analyzed without executing the files to be imported; changes to files or the loading method require a new decision |
| Dataset | Dataset entry | id, name, provider, source_record | Contains data versions and independent declaration records |
| DatasetVersion | Data version | manifest, schema, hash, split, transform_recipe | Training references a fixed version |
| TokenizationRecipe | Tokenization and supervision recipe | id, version, tokenizer, processor, template, loss_scope, eos_pad, truncation, packing, digest | Training checks and snapshots fix the same digest; adapters must not substitute defaults |
| Artifact | File asset | id, sha256, size, mime, storage_uri, status | Content-addressed; cannot be deleted directly while references exist |
| Task | User task | id, project_id, kind, name, draft_revision | Describes a goal and multiple attempts |
| RunAttempt | Execution attempt | id, task_id, snapshot, state, state_version, source_attempt_id, compute_outcome, collection_state, collection_version, output_manifest_ref | Snapshots and terminal states cannot be rewritten; collection recovery has separate records and does not rerun computation |
| ArtifactCollection | Artifact collection record | id, attempt_id, manifest_digest, state, collection_version, error, registered_artifact_ids | Idempotently retries collection from the original manifest; success does not change the original attempt's terminal state or evaluation conclusions |
| Checkpoint | Checkpoint | attempt_id, step, optimizer_state, rng_state, artifacts | Declares whether resumption is possible; integrity can be verified |
| Evaluation | Evaluation report | baseline, candidate, dataset_version, metrics, thresholds | Fixes inputs and rules; reports cannot be rewritten in place |
| Candidate | Model candidate | model_version, source_attempt, evaluation_ids, status | Must pass admission checks before registration as usable |
| Recipe | Recipe | schema_version, requested_config, effective_config, input_refs | Can be copied to a new draft; the original record is immutable |
| WorkflowRun | Workflow run | id, project_id, definition_version, revision, current_step, step_attempts, accepted_outputs | Creates a new id for every start; advancement atomically validates the source and whether the target can be entered |
| WorkflowStepAttempt | Step attempt | id, workflow_run_id, step_id, input_revision, input_digest, run_attempt_id, output_refs, reuse_source | Input versions are immutable; old results can become inputs only through an explicit reuse record |
| Work | Work | project_id, artifact_id, source_attempt, current_revision_id, favorite | Favorite is an attribute; saving means files have been persisted |
| WorkRevision | Work revision | id, work_id, parent_revision_id, artifact_id, changes, editor, created_at | Saves manual revisions such as subtitles without changing the original output, execution snapshot, or generation recipe |
| ExportPlan | Artifact export plan | id, digest, object_versions, dependency_manifest, target_format, estimated_bytes, validation_rules | Fixes source versions and dependencies; rechecks before execution and publishes the local export directory only after integrity validation passes |
| Device | Execution device | id, endpoint_ref, detected_facts, last_seen | Stores only references to credentials |
| Environment | Runtime environment | engine, version, dependencies, driver, digest | Each attempt fixes a version snapshot |

Tasks, execution attempts, and artifacts must be separate. Renaming a task does not affect artifact identity; rerunning creates a new attempt; the same file can be referenced by multiple works or models.

The succeeded / failed / cancelled terminal states of `RunAttempt.state` are immutable. `compute_outcome` separately describes whether computation finished, while `collection_state` summarizes the latest persisted collection record. A collection retry can change the collection state from failed to succeeded, but the original attempt still preserves the fact that “computation completed, collection failed at the time, and collection has now been recovered.” The executor must seal the original artifact manifest, including relative file paths, sizes, digests, purposes, completeness markers, and retention locations. Without a complete manifest, or when computation has not completed, recomputation must not be presented as a collection retry. See [07](07-api-and-task-lifecycle.md) for the control contract. (AUD-08)

<a id="2-数据生命周期"></a>

## 2. Data Lifecycle

Discover / select a source → obtain access → download / import → check file integrity → parse and preview → technical checks → user selects processing → new version → training / evaluation references → archive or remove references.

Intermediate processing files are written to a temporary directory and registered atomically in asset storage after integrity checks pass. Cancelling a download retains resumable temporary information, but partial files cannot be marked complete. Validation failures retain diagnostic records and allow downloading again without overwriting old versions already referenced by tasks.

<a id="3-数据集市场"></a>

## 3. Dataset Marketplace

<a id="31-详情字段"></a>

### 3.1 Detail Fields

Name, description, modality, schema, version, sample count, file size, format, provider, source link, update time, original provider text, access method, reference to the original license file, the user's declaration of intended use, and download integrity information.

Unknown fields are displayed as unknown, not automatically filled in as an open license. Provider data updates create new versions; old experiments continue to reference old versions.

<a id="32-访问状态"></a>

### 3.2 Access States

| State | Available user actions | Transition condition |
| --- | --- | --- |
| Open download | Download, view details | The provider allows public access |
| Application required | Enter intended use, submit an application | The user actively submits |
| Awaiting processing | View, withdraw the application (if supported by the provider) | The provider processes the application |
| Access granted | Download, view the original terms and validity period | The provider grants access |
| Access denied | View the reason, reapply (if allowed) | The provider returns a result |
| Access expired / revoked | View saved records, reapply | The provider changes the conditions |

Access states describe only the provider's access controls. User declarations and license materials are stored independently; AI must not rewrite any access state as a conclusion about legality.

<a id="33-首期接入方式"></a>

### 3.3 Initial Integration Method

First use one official / public resource connector or a controlled test catalog to validate browsing, versions, downloads, and hashes. Restricted-access applications use a controlled test service; do not assume every marketplace has the same API. Each connector specifies its supported fields and operations; missing fields remain null.

<a id="4-数据格式合同"></a>

## 4. Data Format Contracts

| Schema | Required structure | Additional information | Check focus |
| --- | --- | --- | --- |
| `sft` | messages containing role and content | source_id, language, task labels | Role sequence, empty answers, chat-template compatibility |
| `cpt` | text, source_id | Document segmentation information | Empty text, encoding, document boundaries |
| `dpo` | prompt, chosen, rejected | Adapters extend media or conversation structures | chosen and rejected must not be identical |
| `grpo` | prompt, answer | Verifier identifier and version | Verifiable answers, matching reward-function inputs |
| `ppo` | prompt | Reward model and reference policy are specified in task configuration | Valid prompts, reward model can be prepared |
| `vision` | messages, media | Media types, frame-sampling parameters | Readable files, ordering consistent with conversation references |
| `vision-dpo` | media, prompt, chosen, rejected | Image-text layout | Answers must be based on the same media input |
| `image` | image, caption | trigger, dimensions, cropping | Decoding, orientation, duplicates, annotations |
| `paired` | source, reference, target | Alignment method, masks | Correspondence among all three and their spatial / semantic relationships |
| `video` | video, caption, fps, frames | duration, slice boundaries | Decoding, time base, metadata consistency |
| `tts` | audio, text, speaker | language, emotion | Actual duration, transcription, speaker |
| `asr` | audio, text, language | Sentence-level timestamps | Text conventions and correspondence with audio |
| `vc` | audio, speaker | pitch, feature files | Feature-extraction version and relationship to recordings |
| `music` | audio, description, duration | Rhythm, style | Duration, channels, description |

All paths are resolved through the workspace asset layer; arbitrary relative paths that can escape authorized directories are not accepted directly. Remote URLs are handled only by the downloader. Trainers read registered local or execution-device asset references.

<a id="41-可解析的最小示例"></a>

### 4.1 Minimal Parseable Examples

The following JSON examples illustrate structure. They do not contain actual media files and are not datasets ready for quality acceptance.

```json
{
  "schema": "sft",
  "samples": [
    {
      "source_id": "售后示例-001",
      "messages": [
        {"role": "user", "content": "申请退货前需要准备哪些信息？"},
        {"role": "assistant", "content": "先准备订单编号、商品信息和购买渠道，再核对适用政策。"}
      ]
    },
    {
      "source_id": "售后示例-002",
      "messages": [
        {"role": "user", "content": "不知道购买日期怎么办？"},
        {"role": "assistant", "content": "可先查订单记录或付款凭证，确认日期后再核对期限。"}
      ]
    }
  ]
}
```

```json
{
  "schema": "video",
  "sample": {
    "video": "artifact:video-001",
    "caption": "镜头缓慢推近商品，主体保持居中。",
    "fps": 16,
    "frames": 80,
    "duration": 5
  },
  "provenance": {
    "source_record": "用户导入的示例素材",
    "user_statement": "由用户填写",
    "technical_check_status": "未检查"
  }
}
```

When JSONL is officially supported, each line contains one independent sample object. After identifying the schema, the importer displays field mappings rather than automatically treating an arbitrary array as messages. Import reports include valid, failed, and skipped sample counts and specific line numbers.

<a id="42-分词与监督配方"></a>

### 4.2 Tokenization and Supervision Recipes

SFT uses the [supervision contract in 03](03-training-and-model-lab.md), with the data version, recipe digest, and adapter version forming the check identity. The following is a design example for the first text-dialogue template. All identifiers are placeholders; actual versions must be resolved from the selected model and must not be submitted directly as engine configuration.

```json
{
  "id": "tokenization-dialogue-001",
  "version": 1,
  "tokenizer_ref": "固定分词器版本",
  "processor_ref": null,
  "chat_template_ref": "固定模板版本",
  "loss_scope": "assistant_only",
  "label_shift_owner": "model",
  "supervise_turn_end": true,
  "padding_label": -100,
  "eos_pad_policy": "按位置区分真实结束标记与补齐位置",
  "max_sequence_tokens": 2048,
  "truncation": {"strategy": "exclude_overlong", "report_excluded": true},
  "packing": {"enabled": false},
  "zero_supervision": "exclude_sample_and_reject_empty_split",
  "digest": "示例摘要，实际按规范化配置计算"
}
```

Check artifacts include count reports, comparisons of `input_ids` / `attention_mask` / `labels` for representative samples, and media-position mappings where applicable. These are training evidence within the project and are not included in ordinary diagnostic packages. Changes to masking rules must create a new recipe and new checks; they must not merely update a mutable “training-template default.”

<a id="5-技术检查和数据处理"></a>

## 5. Technical Checks and Data Processing

<a id="51-检查分层"></a>

### 5.1 Check Layers

1. Container: file existence, size, encoding, hashes, and extraction limits.
2. Structure: required fields, types, roles, references, and null values.
3. Media: actual decoding, sample rate, dimensions, frame rate, duration, and boundaries.
4. Duplication: content hashes, near-duplicate candidates, and training / validation overlap.
5. Task suitability: renderable templates, actual tokens / labels and supervision scope, sequence budgets, pairing relationships, and callable reward rules.

Report conclusions must distinguish checks that ran from those that did not. For example, “fields complete” cannot mean media files have been read.

<a id="52-处理不覆盖原件"></a>

### 5.2 Processing Does Not Overwrite Originals

Operations such as deduplication, exclusion, cropping, slicing, resampling, and supplementary annotation first show their impact. Applying them creates a new data version. Processing records include the operation, parameters, tool version, input version, and output manifest. Original data remains available for viewing, removal of references, or further derivation.

<a id="53-划分与泄漏"></a>

### 5.3 Splits and Leakage

Fix the split random seed. Split by document, speaker, video, subject, or source group to keep similar samples of the same entity from appearing across training and validation. Test data must not feed back into training based on model performance. User changes to splits invalidate old technical checks and evaluation caches.

The demo's “at least two valid samples” is only a simulated workflow check. Real quality acceptance requires a task-appropriate sample size and statistical interpretation.

<a id="6-文件与版本策略"></a>

## 6. File and Version Strategy

Suggested logical layout: store the metadata database, content-addressed files, task directories, environment directories, temporary downloads, caches, logs, and export packages separately. The user chooses the final physical root directory, which is recorded; the application must not silently write into another project.

The database stores indexes and relationships; large files are stored in the file system. Writes use temporary files, validation, atomic moves, and transactional registration. Before reclaiming orphaned temporary files whose registration was not completed, application startup must first present a list. Files with identical content can be deduplicated, while records still exist separately by project and version.

Deletion uses reference checks and a recoverable area. Files referenced by experiments, models, works, or reports must first have references removed or be archived; they cannot be emptied directly. Caches can be cleared separately, but caches in use must wait until use finishes or the request is cancelled.

<a id="7-模型和适配器"></a>

## 7. Models and Adapters

A model version records the weight-file list, format, size, precision, model configuration, tokenizer, processor, chat template, source revision, license-file reference, and integrity state.

The model import plan separately records the detected format, fixed loader and version, restricted-loading options, trust class, permitted file / network / credential access scope, the user's decision on required execution capabilities, and execution-isolation evidence. Trust classes are restricted weights, code execution required, and unknown / unsupported. Matching digests prove file consistency only; they cannot turn executable serialization files into safe weights. Unknown formats, disguised formats, and restricted-loading failures must never automatically fall back to arbitrary deserialization. See [06](06-architecture-and-adapters.md) for the rules. (AUD-11)

LoRA adapters must bind the base-model version, target modules, and parameter configuration. An adapter file alone must not be displayed as an independent complete model. The trial entry automatically checks whether the base model is prepared and clearly identifies “base model + adapter” versus merged weights.

Artifacts such as quantized models, Core ML, ONNX, and GGUF preserve their source-version relationships. Subsequent operations are declared by conversion / training adapters; all capabilities cannot be inferred from a file extension or the prototype's `runtimeOnly` field.

Cross-device LoRA trials also fix the training-side artifact digest, source base-model revision, target modules and parameters, target engine / template, and conversion records. If conversion produces an artifact, preserve bidirectional provenance between the original LoRA and the new artifact. Candidates can be marked usable only for target combinations actually validated; they must not inherit all device capabilities of the source model. (E-03, AUD-05)

<a id="8-作品与配方"></a>

## 8. Works and Recipes

Saving a work means its artifact files have been validated and persisted; favorites are only for filtering. Input materials, generated results, and intermediate artifacts are recorded separately. Users can view the original task, model, and input sources from a result.

A recipe saves at least the schema version, task kind, project reference, model and adapter versions, input assets and text, requested configuration, effective configuration, environment, random seed, workflow nodes, artifacts, and time. Loading a recipe creates an editable copy. If the old engine or model is unavailable, list the differences first rather than presenting a new version as the same environment.

<a id="81-工作流的执行身份与失效"></a>

### 8.1 Workflow Execution Identity and Invalidation

A workflow definition is a template. Every “Start” must create a new `WorkflowRun.id`; results must not be located solely by template ID. Modifying step inputs creates a new `input_revision` and digest. Run submission binds the corresponding `WorkflowStepAttempt.id`. Accepting input for the next step must verify the current run, step, input version, and complete artifacts. If this run has no result, remain waiting instead of falling back to the first image in history. (AUD-01)

After the user explicitly selects “Reuse existing result,” create a reuse record for the current step that saves the source attempt, artifact digest, source input version, selection action, and time, and display differences between the input and the old result. Reuse does not count as new computation. Changes to upstream inputs mark downstream results referencing the original input version as stale, while old assets and history remain. A stale chain cannot be saved as the current complete workflow until it is rerun or its source is explicitly accepted again.

“Use in next step” checks the run revision, step input version, selected artifact, and occupancy of the target category in one transaction, then commits the current artifact acceptance record, target draft reference, and step position together. If the target cannot be entered or a version conflict occurs, all three remain unchanged; the client changes pages only on a successful response. The control service re-evaluates occupancy at submission time rather than relying only on an earlier check. Advancement can happen only once even when the target task has just completed / been cancelled. (AUD-02)

<a id="82-字幕与其他人工修订"></a>

### 8.2 Subtitles and Other Manual Revisions

Original transcription / generation results and the generation `Recipe` remain immutable. Subtitle corrections create a new `WorkRevision`, saving the original version, revised file, text / timestamp differences, and editing information. A work can switch between the original output and individual revisions. The interface displays “Generation settings” and “Manual revisions” separately; edited transcriptions must not be written back into a recipe claimed to be “fixed at submission.” (E-04)

Rerunning the original generation recipe does not implicitly apply manual corrections. Using corrected text for further generation requires explicitly selecting the revision and recording it in the new attempt's inputs. Exports likewise fix the original or revised version selected by the user and must not change with the current interface selection.

<a id="83-用户产物导出"></a>

### 8.3 User Artifact Export

An export plan fixes the object versions of models, adapters, work revisions, or reports and resolves all included files and external dependencies. An adapter's base-model dependency must have an exact revision / digest and acquisition instructions; it may be bundled or explicitly declared as an external dependency. “Package complete” does not mean “runs independently without a base model.” See [12](12-operations-and-release.md) for the export manifest, integrity, persistence, and failure-recovery contracts. WP-29 owns ordinary artifact export; diagnostic export cannot replace it. (AUD-13)

<a id="9-数据库与一致性要求"></a>

## 9. Database and Consistency Requirements

- All editable drafts have a revision to prevent AI suggestions and manual user changes from overwriting each other.
- Fixed-version objects use unique identifiers and content digests; content already referenced by an execution snapshot must not change in place.
- Runtime state changes and event writes use the same transaction or a reliable outbox to prevent the frontend from showing completion without artifacts.
- Back up before database migration; a failed migration must not start runners or delete the old database.
- Backups must include the database, a consistent file manifest, and instructions for key references; plaintext credentials must not be packaged.

<a id="10-验收标准"></a>

## 10. Acceptance Criteria

Import real text, image, video, and audio samples and verify failure localization; original file hashes remain unchanged after processing; the same versions remain findable after restarting tasks; background results are attributed to the correct project across project switches; recipe reloads preserve models and inputs; deletion of referenced assets is constrained. See [11](11-testing-and-acceptance.md) for detailed cases.
