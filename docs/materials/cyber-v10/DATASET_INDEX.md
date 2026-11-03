# v10 数据索引与使用边界

数据正文单独交接，本目录只保存 [机器可读索引](assets_index.json)。以下路径均相对于完整包的 `当前材料_v10/`。全部数据仍为候选，未获得人类专家批准或商业使用批准。

## 数据族、划分与视图

| 数据族 | 路径 | 行数 | 用途与关系 |
| --- | --- | --- | --- |
| QA | `datasets/qa_current/train.jsonl` | 43,376 | QA 训练候选 |
| QA | `datasets/qa_current/validation.jsonl` | 2,392 | 验证候选，不能合入训练 |
| QA | `datasets/qa_current/test.jsonl` | 2,371 | 保留测试候选，不能用于调参或训练 |
| 漏洞方向 | `datasets/vulnerability_focus/train.jsonl` | 2,150 | 对应 QA train 的子集 |
| 漏洞方向 | `datasets/vulnerability_focus/validation.jsonl` | 115 | 对应 QA validation 的子集 |
| 漏洞方向 | `datasets/vulnerability_focus/test.jsonl` | 135 | 对应 QA test 的子集 |
| QA smoke | `datasets/qa_current/smoke_32.jsonl` | 32 | QA train 的视图，供后续读取和模板验收 |
| QA pilot | `datasets/qa_current/pilot_train_1000.jsonl` | 1,000 | QA train 的视图 |
| 方向 smoke | `datasets/vulnerability_focus/focus_smoke_32.jsonl` | 32 | 方向 train 的视图 |
| 方向 pilot | `datasets/vulnerability_focus/focus_pilot_200.jsonl` | 200 | 方向 train 的视图 |
| 代码种子 | `datasets/verified_code/all_28_development_sft.jsonl` | 28 | development_only，不当作独立保留测试集 |

QA 三个正式划分合计 **48,139** 条，漏洞方向三个划分合计 **2,400** 条。方向集已包含于 QA；smoke 和 pilot 已包含于各自 train。不能把这些行数相加当作独立样本总量，也不能合并视图造成重复训练。

代码种子覆盖 4 个项目，含 9 条修复、18 条识别和 1 条历史反例。9 组参考修复对有有限范围检查证据，不能扩写为全项目正确性、真实 Agent 修复通过或全量专家验收。

## 文件结构

JSONL 使用 UTF-8，每个非空行是一个 JSON 对象。对话内容位于 `messages` 数组；`role` 使用 `system`、`user`、`assistant`，`content` 为文本。记录标识、来源与划分信息应原样保留，便于追溯。本次发布索引不包含任何真实问答正文。

以下仅为人工编写的结构示意，不属于交付数据，不作为额外训练样本：

```jsonl
{"messages":[{"role":"user","content":"请说明漏洞修复需要保留哪些验证证据。"},{"role":"assistant","content":"保留基线复现、补丁、安全测试和正常功能回归结果。"}]}
```

`assets_index.json` 中每项的 `path`、`rows`、`bytes`、`sha256` 用于核对收到的文件；`subset_of` 表示子集或视图关系；`quality_status` 表示候选或有限检查状态；`platform_imported=false` 表示尚无实际平台导入结果。原索引的专家与商用批准字段保持 `null`。

## 质量与暂缓策略

原 v9 有 49,439 条 QA 候选。此次对 658 组同题异答、1,332 份回答做全文初审与交叉复核后，新增暂缓 1,300 条唯一 QA 记录，派生出本轮 48,139 条候选，原 v9 不改写。原 v9 已排除的 14 条继续保持排除，不能再次从 49,439 中重复扣减。

完整包分别保存已确认错误、实质冲突、条件不足的冲突候选、需确认内容、应答取向差异和其他差异。最终初审含 674 个已确认错误条目、10 个实质冲突条目、7 个冲突候选条目；这些是问题条目，可能重叠，不是独立样本数或错误率。拒答与讲解取向不同不自动认定为事实冲突。

暂缓仅应用于新的候选视图，原文和出处保存在完整包的 `全文审核证据_v10/` 与 `当前材料_v10/review_decisions/`。658 组以外的 QA 未经过本轮全面事实审核，剩余候选不能标记为金标准或已全量审核。人类复核人和决定仍为空。

## 后续在当前 Studio 中验收时的选取方式

本节根据当前分支的 [文件选择逻辑](../../../services/control/ailab_studio/workers/sft.py) 和 [资源扫描逻辑](../../../services/control/ailab_studio/catalog.py) 静态读取整理，不代表实际接入或模型验收已完成。

1. 先另行取得并校验完整包，选择 QA 或漏洞方向中的一个数据族。
2. 首次验收选择一个确切的 smoke JSONL 文件，不选择包根目录、`assets_index.json` 或审核证据目录。
3. 后续需要配套验证集时，另建只含所选数据族 `train.jsonl` 与 `validation.jsonl` 的干净目录，再交给训练负责人配置；`test.jsonl` 单独保留评测。
4. 不要直接选择带有 smoke、pilot、另一数据族和元数据的原始数据目录。当前训练器会递归收集目录内 JSON / JSONL / Parquet，未识别为测试或验证的文件会进入训练候选，可能重复加载视图或误读索引。显式选择单个测试文件也不能依赖目录排除规则自动保护。
5. 由后续负责人确认目标 tokenizer、chat template、`max_length` 与 `loss_scope`。已有长度统计基于固定 Qwen2.5 模板，换模型或模板需重新核对；当前执行器可能因超长或 assistant 掩码前缀不稳定而拒绝样本。

原 v9 JSONL 曾通过固定旧版 AI Lab 校验函数的离线格式检查；v10 保留原完整行，仅按记录 ID 筛选。该证据不能替代当前 Studio 的数据加载、聊天模板、监督掩码、训练和验证验收。本次不执行上述后续步骤，不生成新的划分或训练记录。
