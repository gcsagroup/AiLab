# 数据、模型、作品与版本管理

版本：1.1 · 日期：2026-09-09 · 状态：已按审计修订的数据规范，原型中的内存对象与新增合同均待实现。

相关文档：[训练](03-training-and-model-lab.md)、[接口](07-api-and-task-lifecycle.md)、[AI 与声明边界](08-ai-assistance-and-data-boundaries.md)。

## 1. 领域对象与关联

| 对象 | 中文名称 | 关键字段 | 关系／不变量 |
| --- | --- | --- | --- |
| Project | 项目 | id、name、created_at、archived_at | 任务和评测归属项目，显示名可变 |
| Model | 模型逻辑条目 | id、name、family、modality | 包含多个固定 ModelVersion |
| ModelVersion | 模型版本 | revision、artifact_ids、format、tokenizer、processor、base_id、load_policy_ref | 完成后不可改变指向的权重或加载信任记录 |
| ModelImportPlan | 模型导入计划 | id、manifest_digest、detected_format、loader、trust_class、execution_scope、decision_ref | 不执行待导入文件即可分析；文件或加载方式改变后重新决定 |
| Dataset | 数据集条目 | id、name、provider、source_record | 包含数据版本与独立声明记录 |
| DatasetVersion | 数据版本 | manifest、schema、hash、split、transform_recipe | 训练引用固定版本 |
| TokenizationRecipe | 分词与监督配方 | id、version、tokenizer、processor、template、loss_scope、eos_pad、truncation、packing、digest | 训练检查与快照固定同一摘要，适配器不得改用默认值 |
| Artifact | 文件资产 | id、sha256、size、mime、storage_uri、status | 内容寻址；引用存在时不可直接删除 |
| Task | 用户任务 | id、project_id、kind、name、draft_revision | 描述目标及多个尝试 |
| RunAttempt | 执行尝试 | id、task_id、snapshot、state、state_version、source_attempt_id、compute_outcome、collection_state、collection_version、output_manifest_ref | 快照和终态不可改写；收集恢复另记记录，不重跑计算 |
| ArtifactCollection | 产物收集记录 | id、attempt_id、manifest_digest、state、collection_version、error、registered_artifact_ids | 幂等补收原清单；成功不改原尝试终态和原评测结论 |
| Checkpoint | 检查点 | attempt_id、step、optimizer_state、rng_state、artifacts | 声明能否恢复，完整性可验证 |
| Evaluation | 评测报告 | baseline、candidate、dataset_version、metrics、thresholds | 固定输入和规则，报告不可就地改写 |
| Candidate | 模型候选 | model_version、source_attempt、evaluation_ids、status | 登记可用前通过准入检查 |
| Recipe | 配方 | schema_version、requested_config、effective_config、input_refs | 可复制成新草稿，原记录不可变 |
| WorkflowRun | 工作流运行 | id、project_id、definition_version、revision、current_step、step_attempts、accepted_outputs | 每次开始新建 id；推进原子校验来源和目标可进入性 |
| WorkflowStepAttempt | 步骤尝试 | id、workflow_run_id、step_id、input_revision、input_digest、run_attempt_id、output_refs、reuse_source | 输入版本不可变；旧结果只能经明确复用记录成为输入 |
| Work | 作品 | project_id、artifact_id、source_attempt、current_revision_id、favorite | 收藏是属性，保存意味着文件已持久化 |
| WorkRevision | 作品修订 | id、work_id、parent_revision_id、artifact_id、changes、editor、created_at | 保存字幕等人工修订，不改原输出、执行快照或生成配方 |
| ExportPlan | 产物导出计划 | id、digest、object_versions、dependency_manifest、target_format、estimated_bytes、validation_rules | 固定源版本与依赖；执行前复核，完整性通过后发布本地导出目录 |
| Device | 执行设备 | id、endpoint_ref、detected_facts、last_seen | 凭证只保存引用 |
| Environment | 运行环境 | engine、version、dependencies、driver、digest | 每次尝试固定版本快照 |

任务、执行尝试和产物必须分开。用户重命名任务不影响产物身份；重新执行产生新尝试；同一文件可以被多个作品或模型引用。

`RunAttempt.state` 的成功／失败／取消终态不可变。`compute_outcome` 单独说明计算是否完成，`collection_state` 汇总最新已持久化收集记录；补收可将收集状态从失败变为成功，但原尝试仍保留“计算完成、收集曾失败，现已补收”的事实。原产物清单必须由执行器封存，包含文件相对路径、大小、摘要、用途、完整标记和保留位置。没有完整清单或计算未完成时不能把重算包装成补收，具体控制合同见 [07](07-api-and-task-lifecycle.md)。（AUD-08）

## 2. 数据生命周期

发现／选择来源 → 获取访问 → 下载／导入 → 文件完整性检查 → 解析与预览 → 技术检查 → 用户选择处理 → 新版本 → 训练／评测引用 → 归档或解除引用。

处理中间文件写入临时目录，完整性检查通过后原子登记到资产存储。下载取消保留可续传的临时信息，但不能将部分文件标记为完整。校验失败保留可诊断记录并允许重新下载，不覆盖已经被任务引用的旧版本。

## 3. 数据集市场

### 3.1 详情字段

名称、描述、模态、schema、版本、样本数量、文件大小、格式、提供方、来源链接、更新时间、提供方原文、访问方式、原始许可文件引用、用户使用范围声明、下载完整性信息。

字段未知时显示未知，不自动补成开放授权。提供方更新数据时产生新版本；旧实验仍指向旧版本。

### 3.2 访问状态

| 状态 | 用户可执行操作 | 转移条件 |
| --- | --- | --- |
| 开放下载 | 下载、查看详情 | 提供方公开访问 |
| 需要申请 | 填写用途、提交申请 | 用户主动提交 |
| 等待处理 | 查看、撤回申请（如提供方支持） | 提供方处理 |
| 访问获准 | 下载、查看原文和有效期 | 提供方授予访问 |
| 访问拒绝 | 查看原因、重新申请（如允许） | 提供方返回结果 |
| 访问到期／撤销 | 查看已保存记录、重新申请 | 提供方变更条件 |

访问状态只描述提供方访问控制。用户声明与许可材料独立存储，AI 不将任何一种访问状态改写成合法性结论。

### 3.3 首期接入方式

先使用一个官方／公开资源连接器或受控测试目录验证浏览、版本、下载和哈希；受限申请使用受控测试服务，不假设任意市场都有同样 API。每个连接器明确支持的字段与操作，缺失字段保留空值。

## 4. 数据格式合同

| Schema | 必需结构 | 附加信息 | 检查重点 |
| --- | --- | --- | --- |
| `sft` | messages 中包含 role、content | source_id、语言、任务标签 | 角色序列、空回答、聊天模板兼容 |
| `cpt` | text、source_id | 文档分段信息 | 空文、编码、文档边界 |
| `dpo` | prompt、chosen、rejected | 媒体或对话结构由适配器扩展 | chosen 与 rejected 不能完全相同 |
| `grpo` | prompt、answer | 验证器标识与版本 | 答案可验证、奖励函数输入匹配 |
| `ppo` | prompt | 奖励模型、参考策略由任务配置指定 | 提示词有效、奖励模型可准备 |
| `vision` | messages、media | 媒体类型、帧采样参数 | 文件可读、顺序与对话引用一致 |
| `vision-dpo` | media、prompt、chosen、rejected | 图文布局 | 回答必须基于同一媒体输入 |
| `image` | image、caption | trigger、尺寸、裁剪 | 解码、方向、重复、标注 |
| `paired` | source、reference、target | 对齐方式、掩码 | 三者对应及空间／语义关系 |
| `video` | video、caption、fps、frames | duration、切片边界 | 解码、时间基准、元数据一致 |
| `tts` | audio、text、speaker | language、情绪 | 实际时长、转写和说话人 |
| `asr` | audio、text、language | 句级时间戳 | 文本规范和音频对应 |
| `vc` | audio、speaker | pitch、特征文件 | 特征提取版本与录音关系 |
| `music` | audio、description、duration | 节奏、风格 | 时长、声道和描述 |

所有路径都经工作区资产层解析，不直接接受可越出授权目录的任意相对路径。远程 URL 仅由下载器处理，训练器读取已经登记的本地或执行设备资产引用。

### 4.1 可解析的最小示例

以下 JSON 是结构示例，不包含实际媒体文件，也不是可直接用于质量验收的数据集。

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

正式支持 JSONL 时每行一个独立样本对象。导入器识别 schema 后展示字段映射，不把任意数组自动当成 messages。导入报告包含有效、失败、跳过样本数量和具体行号。

### 4.2 分词与监督配方

SFT 使用 [03 的监督合同](03-training-and-model-lab.md)，以数据版本、配方摘要、适配器版本形成检查身份。以下是首个文本对话模板的设计示例；编号均为占位，实际版本必须由选定模型解析，不能直接作为引擎配置提交。

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

检查产物包括计数报告、代表样本的 `input_ids`／`attention_mask`／`labels` 对照和媒体位置映射（如适用）；这些是项目内训练证据，不进入普通诊断包。掩码规则变更必须创建新配方及新检查，不能只更新一份可变的“训练模板默认”。

## 5. 技术检查和数据处理

### 5.1 检查分层

1. 容器：文件存在、大小、编码、哈希、解压限制。
2. 结构：必需字段、类型、角色、引用、空值。
3. 媒体：实际解码、采样率、尺寸、帧率、时长和边界。
4. 重复：内容哈希、近重复候选、训练／验证重叠。
5. 任务适配：模板可渲染、实际 token／labels 与监督范围、序列预算、配对关系、奖励规则可调用。

报告中的检查结论必须区分已运行与未运行。示例“字段完整”不能表示媒体文件已被读取。

### 5.2 处理不覆盖原件

去重、排除、裁剪、切片、重采样、补充标注等操作先显示影响范围，用户应用后生成新数据版本。处理记录包含操作、参数、工具版本、输入版本和输出 manifest。原始数据仍可查看、撤销引用或重新派生。

### 5.3 划分与泄漏

固定划分随机种子；按文档、说话人、视频、主体或来源组划分，避免同一实体的近似样本跨训练和验证。测试集不能因模型表现而回流训练。用户调整划分后旧技术检查与评测缓存失效。

Demo 中“至少两个有效样本”仅用于模拟流程校验，真实质量验收必须有任务匹配的样本量和统计解释。

## 6. 文件与版本策略

建议逻辑布局：元数据库、内容寻址文件、任务目录、环境目录、临时下载、缓存、日志、导出包分别存储。最终物理根目录由用户选择并记录，不能默默写入其他项目。

数据库保存索引和关系，大文件保存在文件系统。写入采用临时文件、校验、原子移动、事务登记；应用启动时回收未完成登记的孤立临时文件前先给出清单。内容相同的文件可以去重，记录仍按项目与版本分别存在。

删除使用引用检查和可恢复区。已被实验、模型、作品或报告引用的文件先解除引用或归档，不能直接清空。缓存可单独清理，但正在使用的缓存需要等待使用完成或取消请求。

## 7. 模型和适配器

模型版本要记录权重文件列表、格式、大小、精度、模型配置、tokenizer、处理器、聊天模板、来源 revision、许可证文件引用和完整性状态。

模型导入计划另记录实际识别格式、固定加载器及版本、受限加载选项、信任类别、允许访问的文件／网络／凭证范围、用户对所需执行能力的决定及执行隔离证据。信任类别为受限权重、需要代码执行、未知／不支持；摘要匹配只证明文件一致，不能把可执行序列化文件变成安全权重。未知格式、伪装格式或受限加载失败都不自动降级到任意反序列化，规则详见 [06](06-architecture-and-adapters.md)。（AUD-11）

LoRA 适配器必须绑定基座版本、目标模块和参数配置。仅有适配器文件时，不显示为独立完整模型。试用入口自动检查基座是否准备，并明确是“基座 + 适配器”还是已合并权重。

量化模型、Core ML、ONNX、GGUF 等产物保留源版本关系。后续操作由转换／训练适配器声明：不能从文件扩展名或原型的 `runtimeOnly` 字段推断所有能力。

跨设备 LoRA 试用同时固定训练端产物摘要、源基座 revision、目标模块和参数、目标引擎／模板及转换记录。若产生转换产物，保留原 LoRA 和新产物的双向来源关系；候选只能对实际验证的目标组合标为可用，不能继承源模型全部设备能力。（E-03、AUD-05）

## 8. 作品与配方

保存作品意味着产物文件已验证和持久化，收藏仅用于筛选。输入素材、生成结果和中间产物分别记录，用户可从结果查看原任务、原模型和输入来源。

配方至少保存：schema 版本、任务种类、项目引用、模型与适配器版本、输入资产与文本、请求配置、实际配置、环境、随机种子、工作流节点、产物和时间。载入配方创建可编辑副本；如果旧引擎或模型不可用，先列出差异，不直接以新版本冒充相同环境。

### 8.1 工作流的执行身份与失效

工作流定义是模板；每次“开始”必须新建 `WorkflowRun.id`，不能仅以模板编号寻找结果。步骤输入修改产生新的 `input_revision` 和摘要，运行提交时绑定对应 `WorkflowStepAttempt.id`；接受下一步输入时必须核对本次运行、本步骤、本输入版本和完整产物。没有本轮结果时保持等待，不从历史列表第一项回退取图。（AUD-01）

用户明确选择“复用已有结果”后，新建当前步骤的复用记录，保存源尝试、产物摘要、来源输入版本、选择动作和时间，并显示输入与旧结果的差异。复用不算新计算。上游输入修改后，下游引用原输入版本的结果标为过期，旧资产和历史仍保留；重做或再次明确接受来源之前不能将过期链保存为当前完整工作流。

“带入下一步”在一个事务中检查运行 revision、步骤输入版本、选中产物和目标类别占用状态，再一起提交当前产物接受记录、目标草稿引用与步骤位置。目标不可进入或版本冲突时这三者全部不变；客户端只按成功响应切页。占用状态由控制服务在提交时重新判断，不能仅依靠提前检查；目标任务刚完成／刚取消时也只能推进一次。（AUD-02）

### 8.2 字幕与其他人工修订

原转写／生成结果及生成 `Recipe` 保持不可变。字幕校正写新的 `WorkRevision`，保存原版本、修订文件、文字／时间戳差异和编辑信息；作品可切换查看原输出与各次修订。界面分别展示“生成设置”和“人工修订”，禁止把编辑后的转写写回声称“提交时固定”的配方。（E-04）

重跑原生成配方不隐含套用人工校正。使用校正文案继续生成须显式选定修订版本并写入新尝试的输入；导出时同样固定用户选择的原版或修订版，不能随当前界面选择变化。

### 8.3 用户产物导出

导出计划固定模型、适配器、作品修订或报告的对象版本，解析所有内含文件与外部依赖。适配器的基座依赖必须有确切 revision／摘要及获取说明，可选择一并打包或明确作为外部依赖；“包完整”不等于“无需基座即可独立运行”。导出清单、完整性、落盘和失败恢复合同见 [12](12-operations-and-release.md)，WP-29 负责普通产物导出，诊断导出不能代替它。（AUD-13）

## 9. 数据库与一致性要求

- 所有可编辑草稿有 revision，避免 AI 建议和用户手工修改相互覆盖。
- 固定版本对象使用唯一标识和内容摘要，禁止就地改变已被执行快照引用的内容。
- 运行状态变更和事件写入使用同一事务或可靠 outbox，避免前端看到完成但没有产物。
- 数据库迁移前备份；迁移失败不启动运行器，不删除旧库。
- 备份必须包含数据库、一致的文件 manifest 和密钥引用说明；不把明文凭证打包。

## 10. 验收标准

导入真实文本、图片、视频和音频样本，检查失败定位；执行处理后原文件哈希不变；任务重启后仍能找到相同版本；跨项目后台结果归属正确；配方重载保留模型和输入；删除被引用资产受到约束。详细用例见 [11](11-testing-and-acceptance.md)。
