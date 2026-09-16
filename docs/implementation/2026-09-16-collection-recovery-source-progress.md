# 人工补收中断恢复与生命周期修复：源码进展

本轮修复人工补收在进程中断后一直处于 collecting，以及控制命令与计算完成、失败退出、停止信号异常的边界。源码和临时进程合同的最终 221 项整合回归通过。固定公司签名 App 仍为 Ver2.4（033），不包含本轮修改；034 未构建，完整 M1、M0—M6、全部 AC 与发布状态不提高。

## 人工补收恢复

原 attempt 已 failed／cancelled、计算结果已成功时，人工只补收先提交 collecting，再复制或登记。此时真实 SIGKILL 使旧启动恢复跳过终态，重开仍 collecting 并拒绝再次补收。复制／登记与两种终态组合的 4 项修前失败、已登记完成的 2 项通过均保留；首轮修后连既有本地 6／远端 3，共 15 项通过。[原红例](../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-red.log)、[首轮回归](../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-green.log)

启动取得库独占锁后，只恢复同 attempt／project／manifest 的唯一活动补收：将收集记为 `COLLECTION_INTERRUPTED`，增加收集版本与事件，保留原终态、终态版本、原因、结束时间、计算清单和已登记结果。不自动 run／resume／collect；远端任务进入本地登记阶段也适用，但不访问远端、不改变远端计算状态。归属或清单不符、多活动记录均不猜选。

扩展恢复 11 项通过，含登记与补偿都写盘失败后恢复可写并重启、远端身份本地登记及归属防护。wrong_project 两轮前置设置错误先违反外键、再使用无效项目资源；最终改用正式项目创建接口，原失败保留，不归类为产品缺陷。恢复事务仍要求存储可写，不承诺永久存储损坏恢复。[最终恢复测试](../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-recovery-final.log)、[准备错误原件](../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-recovery-expanded.log)、[第二轮错误](../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-recovery-expanded-fixed.log)

## 生命周期边界

计算抢先完成时，将尚未确认的 pause／resume 裁决为 `not_applicable`／`COMPUTE_COMPLETED`；失败收尾保存实际 `process.poll` 退出码与时间。发送停止信号发生 `OSError` 时，保留 cancelling 与 unknown，命令记失败、设备保持占用，可用新幂等键重试；不把信号发送失败冒充已取消或进程已退出。

原生命周期 8 项为 5 通过／3 失败；该组修后与恢复 11、检查点 14 合计 33 通过，耗时 6.47 秒。它们使用确定性状态合同、临时库／文件和显式测试进程，不是原生 App 或真实模型验收。后续加强矩阵与整合结果见下文，不重复相加为阶段完成数。[生命周期红例](../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-confirmed-red.log)、[修后有限回归](../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-recovery-fixed.log)

## 整合验证与剩余范围

扩大回归首次 211 项中 209 通过、2 失败：旧最简 cancelled 恢复记录缺少 compute_outcome，新守卫直接索引引发 KeyError，已改为可缺省读取；CLI after_spawn 的 10 秒超时原因未确认，原临时目录已轮转。原用例单跑及备份回归 2 项通过，不能据此声称超时根因已修复。CLI 测试只增强非 200 响应诊断，不改变超时或重试。[扩大回归原结果](../../.artifacts/m1-exit-audit-ver2-4-033-v1/recovery-regression.log)、[限定复查](../../.artifacts/m1-exit-audit-ver2-4-033-v1/regression-two-failures-recheck.log)

随后冻结来源的 221 项整合为 219 通过／2 失败，均为 CLI before_spawn／after_spawn 提交收到空白 503，服务库没有新增 attempt。现场系统代理解析显示回环请求默认经 HTTP 代理；测试的健康检查和回环客户端现显式 `trust_env=False`，不更改系统或产品代理、不增加重试或延长超时。原较早 10 秒超时缺直接响应证据，只能说可能相关，不能宣称已证明同一原因。修后 CLI 和整合复跑结果见下文。[冻结整合原结果](../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-result.json)、[原失败日志](../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression.log)

最终控制与恢复独审单独运行 36 项，全部通过，运行前后 8 项来源摘要一致；覆盖生命周期 10、恢复 11、检查点 14、历史字段备份恢复 1。它接受四处实际合同缺陷的修复，但不包含 CLI，也不替代根后续扩大回归。较早 v2 审查运行期间同文件仍有并行修改，整合绑定以本次冻结前后核对为准，不将重叠数字相加。[最终整合独审](../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-and-recovery-final-review.md)

根最终整合 221 项全部通过，无失败／错误／跳过，48.50 秒，保留 3 项既有警告；控制服务及控制测试全部来源在运行前后摘要一致。CLI 回环直连 11 项另行通过，9.99 秒、1 项警告。独立路由诊断只构造客户端而不发送请求，确认默认 HTTPProxy 与直连 ConnectionPool 的差异；不据此倒推早期超时全因果。各轮测试范围重叠，不相加。[最终整合回执](../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-v2-result.json)、[来源输入](../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-v2-input.json)、[完整日志](../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-v2.log)、[CLI 直连](../../.artifacts/m1-exit-audit-ver2-4-033-v1/cli-direct.log)、[只读路由诊断](../../.artifacts/m1-exit-audit-ver2-4-033-v1/independent-httpx-route.json)

最终独立读回实际解析 221 条 JUnit 记录，确认 117 项控制服务／测试来源与冻结输入及当前文件一致；没有重新执行这组测试。本轮命名夹具进程已退出，既有远端测试服务未动。[最终回归独审](../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-221-v2-independent-review.md)、[CLI 隔离独审](../../.artifacts/m1-exit-audit-ver2-4-033-v1/cli-proxy-isolation-independent-review.md)、[进程收尾](../../.artifacts/m1-exit-audit-ver2-4-033-v1/controlled-process-readback.json)

最终源码回归与独审均已收口，限定接受本轮控制合同修复。历史 73／134 项结果仅按来源复用，E143 原生数据流程、先前构建前记录与原失败保持；不将只读证据复核当作业务重跑。零模型执行不等于零依赖或 Metal 探测，本轮临时控制合同不能替代新包与原生验收，也不自动完成完整 M1。[阶段缺口审核](../../.artifacts/m1-exit-audit-ver2-4-033-v1/independent-gap-review.md)、[旧证据绑定](../../.artifacts/m1-exit-audit-ver2-4-033-v1/evidence-bindings.json)
