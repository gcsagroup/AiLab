# Ver2.4（034）原生补收恢复与 M1 证据：E144

固定公司签名 034 包及全新假执行器库的中断恢复→只补收→保存作品→同库重开已获根有限接受。资源从 7 增至 10，新增收集、产物、作品各 1，命令 2、事件 3，无新 attempt 或模型运行；原失败终态四字段保持。两次正常退出、47 项保护中 44 项严格不变及 selector 恢复通过。

## M1 阶段判定

根已单独接受 M1 应用与数据基础阶段，七行合同及界面子集均获接受。完整 AC、M0、M2—M6、公证及正式发布仍未通过。原生单场景回执的 M1_complete=false 保留原样，其范围声明不替代本次单独阶段判断；历史记录不倒填。[根 M1 阶段回执](../../.artifacts/integration-ver2-4-034-v1/m1-stage-acceptance.md)、[原生与七行独审](../../.artifacts/native-collection-recovery-ver2-4-034-v1/independent-native-review.md)

| M1 子项 | 本次阶段接受依据 |
| --- | --- |
| 项目／草稿持久化与隔离 | 221 控制／上下文回归、E143 同草稿重开与本轮作品归属保持。[原生历史](2026-09-16-ver2-4-033-dataset-workflow.md) |
| 入口、键盘／空态 | 既有有限原生证据与本轮 18 项组件合同、034 只补收及保存入口通过。[组件结果](../../.artifacts/integration-ver2-4-034-v1/m1-workbench-contracts.log) |
| 固定原型／测试清单 | 原固定清单、摘要与复跑命令保持，复用资产整理证据；不倒填 M6 新成员验收。[固定资产](../../prototype/reference-2026-09-09/README.md) |
| 真实文件／manifest 与导入信任 | E143 导入拒绝与文件证据、本轮原 manifest／输出及 8 个 runs 文件保持。[独审](../../.artifacts/native-collection-recovery-ver2-4-034-v1/independent-native-review.md) |
| 假执行器状态与只补收 | 221 中生命周期 10／恢复 11 项及本次真实中断原生闭环关闭原主要缺口。[控制独审](../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-and-recovery-final-review.md) |
| 能力联动拒绝 | 本轮 64 项能力合同、E143 长度失效和当前可用动作满足阶段范围。[能力结果](../../.artifacts/integration-ver2-4-034-v1/m1-capability-contracts.log) |
| 事务与备份基础 | 221 中备份 36／迁移 15 项及新库恢复、业务持久化、原资料保护通过。[阶段根判定](../../.artifacts/integration-ver2-4-034-v1/m1-stage-acceptance.md) |

## 唯一构建与分层测试

以提交 `fe5de1a08e174d1016bf3bdcf0574f107cc35b67` 的 033 源码为基线，唯一构建自动修改四项版本文件为 034，退出 0。根核对 648 跟踪来源、162 生产／212 冻结／92 应用输入、21966 文件／48 链接／4003 目录及 7 个公司签名目标通过；签名组织保持 Global Cybersecurity Alliance Limited。包内控制 PYZ 对应修复代码，033 归档及 47 项构建保护保持。[根验包](../../.artifacts/integration-ver2-4-034-v1/root-frozen-check.json)、[构建记录](../../.artifacts/integration-ver2-4-034-v1/build-process.json)

源码整合 221 项通过，117 项来源前后绑定一致；另有 64 项能力合同和 18 项工作台组件测试通过。它们分别覆盖临时真实文件／数据库／进程、验证器和浏览器组件，不合并为阶段通过数。历史 36／73／134 与部分新回归重叠；原 SIGKILL 红例、生命周期红例、测试准备错误、209＋2／219＋2 及较早 CLI 超时原因未明均保留。回环测试代理隔离不修改产品或系统代理。[源码进展](2026-09-16-collection-recovery-source-progress.md)、[221 独审](../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-221-v2-independent-review.md)、[64 项](../../.artifacts/integration-ver2-4-034-v1/m1-capability-contracts.log)、[18 项](../../.artifacts/integration-ver2-4-034-v1/m1-workbench-contracts.log)

## 原生准备与实际操作

新库明确标为非模型结果，显式假执行器只运行 1 次、resume 为 0；一次受控 ENOSPC 留下计算成功但收集失败的原尝试。备份／恢复后，子进程在只补收的复制边界被真实 SIGKILL，退出 -9，留下 collecting；之后没有用 Service 提前恢复新 A。准备回执记录 70 次 SQL 连接关闭、原库 SQL 为 0；被杀子进程由操作系统关闭连接，不冒称正常 Service.close。[准备结果](../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/setup-result.json)、[中断边界](../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/crash-checkpoint.json)

第一次实际启动 034 后，界面保留原执行失败并提供 `只补收已有产物`。根点击一次后，界面显示已补收且原中断或取消记录仍保留；再点击保存作品一次，作品与素材的文本卡显示已保存、原 attempt 编号及完整短正文。没有另开编辑器或修改文字。第二次同号同库启动直接恢复作品页，再返回原任务，正文、原失败与已补收提示均保持，没有再次补收或保存。[原生界面与边界](../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/ui-review.json)

停机确认资源 7→10，仅新增 collection／artifact／work 各 1；新增 2 命令、3 事件，无新 attempt、训练或模型生成。收集版本从 3 到 6，最终有 3 条收集记录；原 state、state_version、terminal_reason、finished_at 四字段和原计算清单／输出摘要保持。精确 `COLLECTION_INTERRUPTED` 原因来自收集记录及停机事件，界面没有显示该代码。[首次读回](../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/first-check.json)、[重开读回](../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/second-check.json)

两次 App 正常退出 0；重开前后业务表与作品实物保持，允许 UI 上下文改变，不声称原始数据库或整个快照字节相同。47 项既有保护记录中 44 项严格不变，selector 原字节／inode／权限等恢复，ctime 变化保留，两项启动日志允许更新；守卫恢复并释放。[根读回](../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/root-readback.json)、[原生有限接受](../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/root-native-acceptance.json)

## 失败历史与证据限制

首次启动请求在 Popen 前因合法相对守卫路径被拒绝，尚未创建 App。启动器仅修精确路径与工作目录识别，9 项代表测试通过，原文件和失败回执保留；根随后显式重试，实际 App 总共启动两次，无自动重试或产品修改。退出后 AX 返回 App quit，由记录器的退出 0 补足。[启动器修正与原失败](../../.artifacts/native-collection-recovery-ver2-4-034-v1/launch-path-fix-001/REVIEW.md)

本轮保存 5 组 AX 与截图，证明关键界面状态，不是连续录像。短正文在卡片中完整显示，不扩大为编辑器验收；假执行器结果不等于模型质量或真实训练。M1 使用假执行器的合同与界面子集，不把 M2—M6、NVIDIA 实机或新成员安装验收添加为 M1 门槛；原生顺序流程也不替代全部源码竞态负例。E143 及此前源码阶段原文与失败保持。

部分模型名在截图中被截短，完整名称由 AX 核对；关键检查点不证明 HTTP 请求总数，也不声称零环境探测。
