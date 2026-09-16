# 038 导出清单身份恢复与原生重开

固定公司签名候选已更新为 Ver2.4（038），包含完整导出清单身份核对修复。包内真实服务的受控登记故障、错误版本拒绝、新导出成功，以及正式恢复库中的原生历史查看与重开通过。此结论仅覆盖本次子集，完整 M6、M0—M6、公证及正式发行仍未完成。

## 候选与修复

签名组织为 Global Cybersecurity Alliance Limited。整包读回核对 21966 个普通文件、48 个符号链接及 7 个公司签名目标；冻结源码与包内控制服务的实际编译内容一致。主程序摘要为 `60c0940798b39a7c9378ffd5f1d4fb544e4a409fb2b52b26403ed0e894be75fc`。[构建核对](../../.artifacts/integration-ver2-4-038-v1/root-frozen-check.json)

此前源码回归共 179 项通过。生产端与恢复核对端共用完整冻结清单，拒绝错误对象或版本、缺项、额外声明、错误类型和非有限数值；合法完整包仍可恢复。修复前失败证据保留。[源码回归](../../.artifacts/export-manifest-identity-source-v1/regression-final.log)

## 包内服务与故障边界

通过实际 HTTP 请求，在全新独立库使用不可运行的合成模型文件夹具。仅对本次导出注入 SQLite 登记拒绝，文件落盘后正常停止服务，移除测试触发器并修改清单中的版本身份，再重启核实。该步骤模拟登记失败，不是操作系统杀进程或真实复制途中崩溃。

错误版本包被拒绝，原记录成为 `EXPORT_INTERRUPTED`，未登记可用路径；原文件与错误包均保留。重新准备后，新导出成功，4 个内容文件及清单通过核对，服务重启后失败和成功记录仍分别保留。随后通过正式产品备份和恢复创建独立原生验收库。[包内结果](../../.artifacts/packaged-export-identity-ver2-4-038-v1/run-001/result.json)

## 原生查看、退出与保护

同一固定 App 两次打开正式恢复库，分别查看既有失败记录与成功记录，并通过原生退出确认正常停止。第一次停机只有界面设置表变化，业务表保持；第二次停机的整个数据库快照与第一次一致。原库选择已恢复，47 项保护记录完成核对，12 个模型源文件及前序验收库保持；没有新增模型执行或连接原用户库进行 SQL 查询。[最终核对](../../.artifacts/packaged-export-identity-ver2-4-038-v1/root-readback.json)

两次宿主完整就绪分别为 4522.186 和 4580.050 毫秒，外部观察分别为 4650.026 和 4732.063 毫秒。它们不测量窗口初显，也不满足 20 次初显验收的证据要求。[首次启动](../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-001/startup/report.json) [重开启动](../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/startup/report.json)

原生操作仅查看 HTTP 阶段已经形成的导出结果，没有在界面触发本次故障或重新导出。[重开失败记录](../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/01-failed.jpg) [重开成功记录](../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/02-success.jpg)

## 容量处理与未完成事项

构建前后的容量不足记录保留。仅将可再生构建缓存归档并核对全部内容、硬链接及属性后移除原缓存，归档和拒绝覆盖的恢复工具均保留；未删除用户资料、模型或历史失败。首次辅助脚本异常、低效只读核验中断及构建后容量门槛失败均保留，未降低门槛。[缓存归档](../../.artifacts/build-cache-recovery-038-v1/result.json) [暂存归档](../../.artifacts/build-cache-recovery-038-v1/staging/result.json) [容量失败记录](../../.artifacts/integration-ver2-4-038-v1/root-verify.log)

本轮不提供模型质量、指定 NVIDIA 跨端、全部真实对象导出、干净安装、五名首次用户、长任务或网络故障的新通过证据。完整 AC27、M6、M0—M6 和发行状态保持待验；037 及更早记录保留形成时结论。
