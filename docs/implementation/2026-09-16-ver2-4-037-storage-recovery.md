# 037 磁盘满拒绝、报告恢复与重开

固定公司签名候选 Ver2.4（037）完成有限存储故障验收：独立测试卷实际耗尽空间后，原生计划拒绝导出；有效计划形成后再次耗尽空间，执行以磁盘满失败；释放测试占位后重新检查并成功导出，重开仍分别保留失败与成功。完整 M6、M0—M6 与发行未通过。

## 候选与独立测试资料

沿用 Global Cybersecurity Alliance Limited 签名的固定 App，没有重新构建或修改产品。二进制摘要保持 `59ce9d899488da868af0935f6dcb7f09749623deab250d55eeda7def4f0b2ce0`。[整包回执](../../.artifacts/integration-ver2-4-037-v1/root-frozen-check.json)

复用先前 E22 离线冻结文件副本，通过 037 包内服务的实际 HTTP 恢复到新独立库。输入含 91 个文件、1868874298 字节，不是本轮调用产品备份接口生成的备份；没有连接原库 SQL。恢复库首次启动执行正式架构 3→4 迁移，成功回执与迁移备份摘要均已核对，备份全部表内容等于启动前快照。[恢复回执](../../.artifacts/native-storage-ver2-4-037-v1/restore-001/result.json) [停机核验](../../.artifacts/native-storage-ver2-4-037-v1/native-001/root-readback.json)

新建 64 MiB HFS+ 磁盘映像，只在核对设备、卷身份与容量后写入专用测试占位文件。独立文件系统容量为 67067904 字节；实际写入返回 `ENOSPC / errno 28`，两次故障现场可用空间均为 0。系统磁盘没有被填满。[首次零空间](../../.artifacts/native-storage-ver2-4-037-v1/storage-001/fill-tail-001.json) [再次零空间](../../.artifacts/native-storage-ver2-4-037-v1/storage-001/fill-002.json)

## 原生拒绝、恢复与重开

通过原生目录选择器选中测试卷。首次检查因空间不足而停用开始导出，没有创建导出执行记录。释放占位并重新选择同一目录后，检查允许导出；此时再次填满测试卷，再点击开始，产生 `DISK_FULL` 失败。失败发生在复制前，目标目录没有完整包或临时包。[计划拒绝画面](../../.artifacts/native-storage-ver2-4-037-v1/native-001/01-full-plan-blocked.png) [执行失败画面](../../.artifacts/native-storage-ver2-4-037-v1/native-001/03-ready-then-full-failed.png) [故障文件现场](../../.artifacts/native-storage-ver2-4-037-v1/storage-001/failed-export-filesystem.json)

再次释放专用占位文件，通过重新检查导出、检查范围、开始导出完成恢复。成功包包含 11 个内容文件、60884 字节，另有完整性清单；其中 7 个 JSON 报告与原封存产物完全一致。全部内容的摘要和大小均通过核对。失败记录为 `export-c8757316996843f6842c0199fac95184`，新成功记录为 `export-7ee97c109d2f4230811d12734096dae1`。[完成画面](../../.artifacts/native-storage-ver2-4-037-v1/native-001/04-recovered-export.png) [文件核对](../../.artifacts/native-storage-ver2-4-037-v1/native-001/export-after-first.json)

正常退出并重开同一候选与独立库，分别打开原失败和新成功记录，状态及输出身份保持，随后再次正常退出。全部业务表和导出文件保持；设置仅因返回工作台清空所选任务，数据库字节并非完全相同。[重开失败记录](../../.artifacts/native-storage-ver2-4-037-v1/native-001/05-reopen-failed.png) [重开成功记录](../../.artifacts/native-storage-ver2-4-037-v1/native-001/06-reopen-success.png)

## 核对、测试与收尾

原 52 项资源全部不变，新增 9 项资源后共 61 项，包含 3 个计划、2 个导出、2 个任务及2 个导出执行记录；共 2 条命令、93 条事件。模型运行与评测新增均为 0，原质量失败保留，候选登记数为 0。原 E22 库、先前 5 个验收库、12 个模型源文件及冻结输入保持。原选择文件已恢复，守卫已释放锁，App 与控制进程均已停止。[根核验回执](../../.artifacts/native-storage-ver2-4-037-v1/native-001/root-readback.json)

报告全部 12 个文件（含清单）复制到本轮保留目录并逐项核对，随后正常卸载已核实身份的测试映像。保留目录只是验收文件副本，不算新增产品导出。映像文件及摘要保留，测试卷已不再挂载。[保留副本回执](../../.artifacts/native-storage-ver2-4-037-v1/native-001/export-preservation.json) [卸载与完成回执](../../.artifacts/native-storage-ver2-4-037-v1/native-001/completion.json)

导出前端 28 项、控制服务 52 项测试通过，控制测试保留 2 项警告；原生启动守卫 7 项与卷身份辅助测试 3 项通过。[前端日志](../../.artifacts/native-storage-ver2-4-037-v1/frontend-tests-corrected.log) [控制日志](../../.artifacts/native-storage-ver2-4-037-v1/control-tests.log)

准备过程保留失败证据：创建映像时初次参数无效；首次大块填充遇到真实空间不足后仍剩 90112 字节，随后只补齐尾部至零空间；前端测试首次在错误目录执行。停机核验初次错误假定架构版本不变，核对正式迁移回执及备份后修正验证器并通过，没有修改数据库或运行记录。[架构假设失败](../../.artifacts/native-storage-ver2-4-037-v1/native-001/readback-initial-schema-assumption.log)

本轮只验证真实卷满条件下的计划阻断、复制前检查、释放空间后的重新导出及重开持久化。没有验证复制途中空间耗尽、系统盘满、备份失败、介质丢失、干净安装、跨设备、完整迁移回滚或公证发行，也没有重新执行冻结质量方案。本页本机证据链接不随源码仓库上传。
