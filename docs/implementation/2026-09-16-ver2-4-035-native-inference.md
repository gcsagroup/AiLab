# Ver2.4（035）本机真实推理与重开：E145

固定公司签名 035 候选的本机真实推理与同库重开已获根有限接受：1 次真实 attempt、0 次训练，保存作品并建立未执行的配方草稿，两次 App 正常退出。原守卫失败与被拒绝的启动请求保留；M2、完整 AC、M0、M2—M6、公证及正式发布状态不提高。

本次实测设备为 Apple M5 Max，只关闭已实证的本机参数／预设回归子集。12 项版本测试及版本检查通过，不与源码或其他夹具测试合并计数。[根有限接受](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-native-acceptance.json)

## 构建与来源

构建基线为 `c6d2e0886e1274b653179c4d8512194cdcffce25`，自动版本投影为 035，唯一构建退出 0。根与独审核对 656 跟踪来源、162 生产／212 冻结／92 应用输入、21966 文件／48 链接／4003 目录及 7 个公司签名目标；034 归档与构建保护保持。控制包内实际代码匹配加载边界修复。[根验包](../../.artifacts/integration-ver2-4-035-v1/root-frozen-check.json)、[构建独审](../../.artifacts/integration-ver2-4-035-v1/independent-build-review.json)

## 真实界面与实际参数

在全新独立库经原生界面导入冻结的 Qwen 4bit 模型，确认前可见加载信任与权限说明。离线加载选项、凭证环境白名单和独立进程不等于操作系统沙箱；自定义模型代码仍不开放。原模型源 12 个文件单独受保护。[界面记录](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui-review-first.json)

根另行核对原生 import-plan 与 model 均持久化正确的 7 字段 `execution_boundary`，并绑定导入确认 AX／截图；本项包含数据事实，不只有界面文案。[原生边界核对](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/model-boundary-native-check.json)

低延迟与低内存预览分别取消，均保留原 auto／2048；再次应用低内存后为 auto／512。固定提示词为 `订单编号为 7391，金额为 82。只回答订单编号数字。`；实际温度 0、Top-p 1、种子 0、上下文 128、停止序列 `39`、stream=false。50＋79＝129 在检查阶段拒绝，无对应 attempt；仅改最大输出后 50＋78＝128 允许运行。没有裁剪输入。[拒绝界面](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui/09-over-budget-rejected.txt)、[通过界面](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui/10-boundary-preflight-allowed.txt)

唯一真实推理成功，非流式正文为 `7`，token 事件为 0；保存一次作品，查看原配方，再新建来源草稿但未检查或运行。首轮 App 正常退出 0。停机核对 15 资源、4 命令、13 事件、6 产物，关联模型、检查、snapshot、实际参数、产物副本及作品配方；不是仅比较数量。[首轮检查](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/first-check.json)

## 守卫失败与已确认恢复

守卫解析 ps 输出时发生 `UnicodeDecodeError`，退出 1；finally 已在 App 停止后恢复原 selector。未产生正常 released 回执，根另行确认原守卫已退出，并实际重新取得、释放原库锁。47 项保护中 44 项严格不变；selector 原身份与字节恢复，ctime 变化及启动日志保留。不能宣称全程连续持锁。[失败原记录](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/guard-failure-001.json)、[根恢复读回](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-readback-after-first.json)

第二次启动请求退出 1，原因是守卫已进入恢复；没有创建第二个 App 进程。此拒绝不等于重开验收通过，也不撤销已完成的首轮推理证据。原失败、首轮快照及根接受绑定保持原样。

## 同库重开与最终保护

经独立恢复方案与门禁审核后，同一 035 包在同一新库实际第二次启动：界面恢复未执行配方草稿，作品与原任务均显示正文 `7`。没有新增运行或保存，两次 App 退出均为 0；新守卫恢复 selector、释放锁后退出 0。[最终界面记录](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui-review.json)、[第二次停机检查](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/second-check.json)

两次停机的业务表相同，仅允许 UI 上下文变化；原始数据库 SHA 实际改变，不声称数据库字节相同。15 资源、4 命令、13 事件、1 attempt／0 训练／6 产物保持，31 份模型／运行／产物文件摘要不变。最终 47 项保护中 44 项严格不变，selector 原 inode／字节恢复，12 个模型源文件不变；持锁中断历史仍保留。[根最终读回](../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-readback.json)

界面证据为关键检查点 AX 与截图，不是连续录像。数字框可显示前导零，停机记录确认数值；完成截图停在页底，保存作品截图完整显示短正文。短输入与单个固定模型的结果不代表通用质量或性能，也不是 NVIDIA、训练、首次用户预演或完整 M2 验收。既有 M1 阶段接受保持；源码阶段“035 未构建”原文作为历史记录保留。

5 名首次用户的完整干净安装验收属于 M6 独立门槛，不作为 M2 的完成条件；M2 仍需其自身指定设备、执行位置、异常流程与首次语言试用阶段预演的对应证据。

首轮与最终独审分开保存，原失败不覆写。恢复辅助夹具 46 项通过；该组不是真实模型测试，不与其他数量合计。[首轮独审](../../.artifacts/native-m2-inference-ver2-4-035-v1/independent-first-review.md)、[最终独审](../../.artifacts/native-m2-inference-ver2-4-035-v1/independent-native-review.md)、[恢复夹具测试](../../.artifacts/native-m2-inference-ver2-4-035-v1/reopen-tests-final-v2.log)、[版本测试](../../.artifacts/native-m2-inference-ver2-4-035-v1/version-tests.log)
