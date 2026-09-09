# 数据、模型、作品与版本管理

版本：1.0 · 日期：2026-09-09 · 状态：真实产品的数据规范建议，原型中的内存对象需迁移实现。

相关文档：[训练](03-training-and-model-lab.md)、[接口](07-api-and-task-lifecycle.md)、[AI 与声明边界](08-ai-assistance-and-data-boundaries.md)。

## 1. 领域对象与关联

| 对象 | 中文名称 | 关键字段 | 关系／不变量 |
| --- | --- | --- | --- |
| Project | 项目 | id、name、created_at、archived_at | 任务和评测归属项目，显示名可变 |
| Model | 模型逻辑条目 | id、name、family、modality | 包含多个固定 ModelVersion |
| ModelVersion | 模型版本 | revision、artifact_ids、format、tokenizer、processor、base_id | 完成后不可改变指向的权重 |
| Dataset | 数据集条目 | id、name、provider、source_record | 包含数据版本与独立声明记录 |
| DatasetVersion | 数据版本 | manifest、schema、hash、split、transform_recipe | 训练引用固定版本 |
| Artifact | 文件资产 | id、sha256、size、mime、storage_uri、status | 内容寻址；引用存在时不可直接删除 |
| Task | 用户任务 | id、project_id、kind、name、draft_revision | 描述目标及多个尝试 |
| RunAttempt | 执行尝试 | id、task_id、snapshot、state、source_attempt_id | 提交后快照不可变，失败不覆盖 |
| Checkpoint | 检查点 | attempt_id、step、optimizer_state、rng_state、artifacts | 声明能否恢复，完整性可验证 |
| Evaluation | 评测报告 | baseline、candidate、dataset_version、metrics、thresholds | 固定输入和规则，报告不可就地改写 |
| Candidate | 模型候选 | model_version、source_attempt、evaluation_ids、status | 登记可用前通过准入检查 |
| Recipe | 配方 | schema_version、requested_config、effective_config、input_refs | 可复制成新草稿，原记录不可变 |
| WorkflowRun | 工作流运行 | definition_version、nodes、edges、outputs | 每个节点引用独立尝试与产物 |
| Work | 作品 | project_id、artifact_id、source_attempt、favorite | 收藏是属性，保存意味着文件已持久化 |
| Device | 执行设备 | id、endpoint_ref、detected_facts、last_seen | 凭证只保存引用 |
| Environment | 运行环境 | engine、version、dependencies、driver、digest | 每次尝试固定版本快照 |

任务、执行尝试和产物必须分开。用户重命名任务不影响产物身份；重新执行产生新尝试；同一文件可以被多个作品或模型引用。

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

## 5. 技术检查和数据处理

### 5.1 检查分层

1. 容器：文件存在、大小、编码、哈希、解压限制。
2. 结构：必需字段、类型、角色、引用、空值。
3. 媒体：实际解码、采样率、尺寸、帧率、时长和边界。
4. 重复：内容哈希、近重复候选、训练／验证重叠。
5. 任务适配：模板可渲染、序列预算、配对关系、奖励规则可调用。

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

LoRA 适配器必须绑定基座版本、目标模块和参数配置。仅有适配器文件时，不显示为独立完整模型。试用入口自动检查基座是否准备，并明确是“基座 + 适配器”还是已合并权重。

量化模型、Core ML、ONNX、GGUF 等产物保留源版本关系。后续操作由转换／训练适配器声明：不能从文件扩展名或原型的 `runtimeOnly` 字段推断所有能力。

## 8. 作品与配方

保存作品意味着产物文件已验证和持久化，收藏仅用于筛选。输入素材、生成结果和中间产物分别记录，用户可从结果查看原任务、原模型和输入来源。

配方至少保存：schema 版本、任务种类、项目引用、模型与适配器版本、输入资产与文本、请求配置、实际配置、环境、随机种子、工作流节点、产物和时间。载入配方创建可编辑副本；如果旧引擎或模型不可用，先列出差异，不直接以新版本冒充相同环境。

## 9. 数据库与一致性要求

- 所有可编辑草稿有 revision，避免 AI 建议和用户手工修改相互覆盖。
- 固定版本对象使用唯一标识和内容摘要，禁止就地改变已被执行快照引用的内容。
- 运行状态变更和事件写入使用同一事务或可靠 outbox，避免前端看到完成但没有产物。
- 数据库迁移前备份；迁移失败不启动运行器，不删除旧库。
- 备份必须包含数据库、一致的文件 manifest 和密钥引用说明；不把明文凭证打包。

## 10. 验收标准

导入真实文本、图片、视频和音频样本，检查失败定位；执行处理后原文件哈希不变；任务重启后仍能找到相同版本；跨项目后台结果归属正确；配方重载保留模型和输入；删除被引用资产受到约束。详细用例见 [11](11-testing-and-acceptance.md)。
