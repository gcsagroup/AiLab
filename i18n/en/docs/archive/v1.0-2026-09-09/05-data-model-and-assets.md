<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/05-data-model-and-assets.md) · [繁體中文](../../../../zh-TW/docs/archive/v1.0-2026-09-09/05-data-model-and-assets.md) · [English](05-data-model-and-assets.md)
<!-- translation-navigation:end -->

<a id="数据模型作品与版本管理"></a>

# Data, Models, Works, and Version Management

Version: 1.0 · Date: 2026-09-09 · Status: proposed data specifications for the real product; prototype in-memory objects require migration and implementation.

Related documents: [Training](03-training-and-model-lab.md), [Interfaces](07-api-and-task-lifecycle.md), [AI and declaration boundaries](08-ai-assistance-and-data-boundaries.md).

<a id="1-领域对象与关联"></a>

## 1. Domain Objects and Relationships

| Object | Display name | Key fields | Relationships / invariants |
| --- | --- | --- | --- |
| Project | Project | id, name, created_at, archived_at | Tasks and evaluations belong to a project; the display name can change |
| Model | Logical model entry | id, name, family, modality | Contains multiple fixed ModelVersion objects |
| ModelVersion | Model version | revision, artifact_ids, format, tokenizer, processor, base_id | Referenced weights cannot change after completion |
| Dataset | Dataset entry | id, name, provider, source_record | Contains data versions and independent declaration records |
| DatasetVersion | Data version | manifest, schema, hash, split, transform_recipe | Training references a fixed version |
| Artifact | File asset | id, sha256, size, mime, storage_uri, status | Content-addressed; cannot be deleted directly while references exist |
| Task | User task | id, project_id, kind, name, draft_revision | Describes a goal and multiple attempts |
| RunAttempt | Execution attempt | id, task_id, snapshot, state, source_attempt_id | Snapshot is immutable after submission; failures are not overwritten |
| Checkpoint | Checkpoint | attempt_id, step, optimizer_state, rng_state, artifacts | Declares whether resumption is possible; integrity can be verified |
| Evaluation | Evaluation report | baseline, candidate, dataset_version, metrics, thresholds | Fixes inputs and rules; reports cannot be rewritten in place |
| Candidate | Model candidate | model_version, source_attempt, evaluation_ids, status | Must pass admission checks before registration as usable |
| Recipe | Recipe | schema_version, requested_config, effective_config, input_refs | Can be copied to a new draft; the original record is immutable |
| WorkflowRun | Workflow run | definition_version, nodes, edges, outputs | Each node references independent attempts and artifacts |
| Work | Work | project_id, artifact_id, source_attempt, favorite | Favorite is an attribute; saved means the file is durable |
| Device | Execution device | id, endpoint_ref, detected_facts, last_seen | Stores only references to credentials |
| Environment | Runtime environment | engine, version, dependencies, driver, digest | Each attempt fixes a version snapshot |

Tasks, execution attempts, and artifacts must be separate. Renaming a task does not affect artifact identity; rerunning creates a new attempt; the same file can be referenced by multiple works or models.

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

<a id="5-技术检查和数据处理"></a>

## 5. Technical Checks and Data Processing

<a id="51-检查分层"></a>

### 5.1 Check Layers

1. Container: file existence, size, encoding, hashes, and extraction limits.
2. Structure: required fields, types, roles, references, and null values.
3. Media: actual decoding, sample rate, dimensions, frame rate, duration, and boundaries.
4. Duplication: content hashes, near-duplicate candidates, and training / validation overlap.
5. Task suitability: template renders, sequence budget, pairing relationships, and callable reward rules.

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

LoRA adapters must bind the base-model version, target modules, and parameter configuration. An adapter file alone must not be displayed as an independent complete model. The trial entry automatically checks whether the base model is prepared and clearly identifies “base model + adapter” versus merged weights.

Artifacts such as quantized models, Core ML, ONNX, and GGUF preserve their source-version relationships. Subsequent operations are declared by conversion / training adapters; all capabilities cannot be inferred from a file extension or the prototype's `runtimeOnly` field.

<a id="8-作品与配方"></a>

## 8. Works and Recipes

Saving a work means its artifact files have been validated and persisted; favorites are only for filtering. Input materials, generated results, and intermediate artifacts are recorded separately. Users can view the original task, model, and input sources from a result.

A recipe saves at least the schema version, task kind, project reference, model and adapter versions, input assets and text, requested configuration, effective configuration, environment, random seed, workflow nodes, artifacts, and time. Loading a recipe creates an editable copy. If the old engine or model is unavailable, list the differences first rather than presenting a new version as the same environment.

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
