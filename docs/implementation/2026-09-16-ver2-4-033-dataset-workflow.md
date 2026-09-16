# Ver2.4（033）数据导入、来源划分与草稿重开：E143

固定路径公司签名 033 包、原生数据导入→来源划分→配置检查→长度失效→同库重开的有限流程已获根接受。两次正常退出，新增 12 项资源／3 条命令／0 次运行，最终草稿修订为 5；47 项保护记录中 44 项严格不变，原 selector 恢复，守卫释放。没有训练或模型生成，不签署完整 M1、M0—M6、全部 AC、公证或发布就绪。

## 构建与源码证据

以提交 `8d98c674a72c2e4bba6a3e80f87c031222b6e8ef` 为 032 源码基线，唯一正式构建自动修改四项版本文件为 033，退出 0；639 项跟踪来源、162 项生产来源、212 项冻结文件、92 项应用输入与投影一致。根整包核对 21966 文件、48 链接、4003 目录及 7 个公司签名目标通过，签名组织保持 Global Cybersecurity Alliance Limited；032 归档保留。[根验包](../../.artifacts/integration-ver2-4-033-v1/root-frozen-check.json)、[构建独审](../../.artifacts/integration-ver2-4-033-v1/independent-build-review.md)、[032 归档](../../.artifacts/integration-ver2-4-033-v1/archive-032-result.json)

首次根核验器错误假定控制报告含两项后端源码字段而失败，原日志保留；修正后用真实控制二进制 PYZ 的完整模块代码对象比对冻结源码，仅归一化文件路径，再完成根核验。核验器代表测试 12 项、版本测试 12 项通过。这是核验器修正，不是首次验包全绿，也不表示发生第二次构建。[原失败](../../.artifacts/integration-ver2-4-033-v1/root-verify-001.log)、[实际 PYZ 独审](../../.artifacts/integration-ver2-4-033-v1/control-pyz-independent-readback.json)

来源已有 620 项前端及 73 项收尾控制回归通过；前端首次两项超时、降低并发后的复跑条件、警告与补收原红例均保留在[构建前源码记录](2026-09-16-dataset-and-collection-source-fixes.md)。另有 134 项核心控制测试通过、无跳过，覆盖上下文、CLI 中断／停止未知、备份恢复与迁移；CLI 含依赖及 Metal 探测，没有模型运行。它们不替代本次原生证据，也不等于补收故障已在原生界面复现。[核心回归](../../.artifacts/integration-ver2-4-033-v1/m1-core-regression-result.json)

## 原生数据与配置流程

正式恢复历史备份的 737 文件至独立新 A，50 次 SQL 连接全部关闭，原工作库 SQL 为 0；准备未预置导入、划分或草稿。实际界面先分别拒绝空回答、仅 system、非法 JSON，再一次导入结构合法的 7 条／13628 字节主文件；三个拒绝计划保留，超长样本并未在导入阶段删除。[恢复结果](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/setup-result.json)、[界面审核](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui-review.json)

使用原 Qwen 模型、最大长度 512、种子 7、验证比例 25% 完成包内 CPU 分词：6 条有效、1 条超长排除、5 个来源组，训练 5 条／4 组、验证 1 条／1 组，实际验证样本比例 16.67%，监督与移位监督各 40。展开分词证据后明确应用一次，保留原件、两独立子集及来源证明；验证子集训练入口禁用。随后从训练侧读取已应用记录并选择`使用训练子集`，没有再次准备或应用。[分词预览](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/008-split_cpu_ready.txt)、[应用结果](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/010-split_applied.txt)

新建训练草稿后手选同一原模型，使用本机 Apple GPU、长度 512、步数 7。真实配置检查通过，显示 5 条可训练、监督 34 和未绑定冻结评测计划警告；没有点击开始训练。长度改为 256 后旧成功检查立即失效，再检查仅被 `DATASET_SPLIT_CHECK_EXPIRED` 阻断；原划分仍为 512。第二次启动直接恢复同一草稿，显示步数 7／长度 256，没有经过首页继续，也未再次检查或编辑。[正检查](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/013-training_512_passed.txt)、[失效与负检查](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/015-training_256_blocked.txt)、[重开草稿](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/017-reopened_same_draft.txt)

## 停机持久化与保护

停机精确新增 4 个导入计划、3 个数据集、1 个划分计划、1 个划分记录、1 个训练任务、2 个 preflight，共 12 项资源；导入、准备、应用各 1 条命令，共 3 条，新增 attempt 为 0。最终草稿修订 5，正负检查分别绑定对应修订与配置；生产证明校验核对原行、来源组、子集字节及模型／分词身份。两次停机业务、六个数据／证明文件摘要及原始数据库 SHA 均相同；没有把恢复库中的既有历史运行说成零。[首次停机](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/first-check.json)、[第二次停机](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/second-check.json)

两次 App 均正常退出 0，47 项既有保护记录中 44 项严格保持；原 selector 字节、inode、权限等恢复，ctime 变化保留，两项启动日志按原合同允许更新。守卫已恢复并释放，不声称锁永不中断。最终根回执接受本次有限数据流程。[根读回](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/root-readback.json)、[根接受](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

## 操作限制与未完成范围

独立原生审查接受上述有限范围，原始操作偏差及证据限制保留；它不替代尚未覆盖的完整阶段。[原生独审](../../.artifacts/dataset-workflow-ver2-4-032-v1/independent-native-review.md)

保留实际操作偏差：首个文件 GoTo 粘贴超时，重读后用完整路径修正；第二文件 AX 点击未选中，改用 GoTo 并核对 URL；辅助按钮匹配误计焦点说明行而拒绝，修正为只匹配数字节点。数值输入首轮显示 07／0256，但有效配方、停机数据及重开界面为 7／256。首次确认退出后 AX 返回 App quit，实际退出码为 0。没有额外持久业务记录；不推定无 HTTP 请求。证据为逐步 AX 与截图、长页分图，不是连续录像。[操作与观察边界](../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui-review.json)

真实 CPU tokenizer 与配置检查不加载模型进行训练或生成，但会执行环境探测、读取分词资料及模型清单摘要。来源组隔离不等于语义去重、验证损失或质量通过；重开没有复用旧 preflight 宣称仍可提交。既有 E64—E72 来源组成功、E142 及源码阶段失败保留，不称首次能力；迟到读取竞态和补收故障的原生现场复现、永久存储故障、完整阶段与发布门槛仍未完成。
