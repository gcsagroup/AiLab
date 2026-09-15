# Ver2.4（026）完整导出包登记恢复

本轮沿用固定路径的 026 公司签名包，没有产品源码修改或重新构建。一次原生会话将已有文字修订版 3 导出；完整文件包发布后，精确登记故障使界面进入“待核实”。移除本批触发器后，点击“核实原导出”，同一记录成功完成。根已接受本次原生与保护有限子集，完整阶段签署仍保持。

## E130：登记故障测试与合法独立恢复

5 项后端相关测试通过，其中新增 1 项使用独立 SQLite 连接和真实 UPSERT 登记失败，覆盖另一计划不受影响、完整包保留及原号核实／幂等重放；另外 4 项为已有相关用例。登记观察器 30 项、恢复准备 7 项、监督器 6 项合成测试分别通过，不合并为产品或原生测试数量。[后端测试](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/source-tests-001/process.json)、[后端用例审阅](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/test-review.md)、[登记观察器测试](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/tests-001/green-002/process.json)、[准备测试](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/restoration-preparation-001/tests-002/process.json)、[监督器测试](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/supervisor-tests-001/process.json)

正式恢复建立新的独立库，后续 App 直接使用该根，没有再次克隆。61 个连接均在新准备范围内并已关闭，原源库 SQL 为 0；已有文字／配音／字幕当前版为 3／3／4。此过程不是 `Backup.create` 产品界面验收。[准备接受](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/restoration-preparation-001/root-acceptance.json)、[实际准备执行](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/restoration-preparation-001/execution-001/process.json)

观察器同号校验的红例与修正保留；首次测试命令误选基础解释器、未执行测试的失败另存。DROP 独立于 pending 观察成功；正常流程须先移除触发器才核实、退出。异常退出后的离线 DROP 只能清理本批新库，不补签正常验收。[登记脚本审阅与失败原件](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/registration-review.md)

## E131：原生完整包待核实到同号成功

当前文字修订版 3／父版 2进入导出，计划显示 4 项负载；实际包为 4 项负载加 manifest，共 5 个文件。08 的说明正文为“导出结果待核实。核实会检查原文件包并更新这条记录。”；下方红色提示为“导出结果尚未确认，请核实原导出；不会重新运行模型。”，并提供“核实原导出”。09 显示已完成，保持同一 export 编号和原目标目录；根从真实导出文件、修订记录及准备时当前 v3 核对正文完全相等，共 16000 个 Unicode 字符；原包通过完整性核对。[UI审阅](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/ui-review.md)、[核实结果](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/sql-final/result.json)

07 虽预命名 pending，实际只是初始运行状态，08 才证明待核实出现。目录粘贴超时后使用支持字段 setValue 完成选择，属于目录准备恢复，不是导出重试。10 份 AX、10 张 JPEG 为关键界面证据；清单未展开，截图不证明四个文件名或长正文全文。没有从任务队列重开，不能记为完整键盘任务。

本轮 1 次 App、1 次导出、1 次 UI 核实，0 模型、0 保存、0 额外 probe 或系统设置变更；启动自带环境检查照常发生。4 个额外 SQL 连接依次为安装触发器、读取 pending、移除触发器、退出后 final 读回，均属本批新库。[正常退出结果](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/run/result.json)

退出后 final 的 mode=ro 连接关闭后仍留下 0 字节 WAL 和 32768 字节 SHM。根观察到两者时间落在该读连接窗口，lsof 无持有者，数据库完整文件事实与正常退出后相等；这两文件原样保留，不能声称新库无旁路。首次根读回因“必须无旁路”的断言退出 1，保留负例，后续只纠正核对口径；另一处根读回把正文误设为 10000 字符的断言也保留原失败，已确认应为 16000，并非文件内容不一致。原生、UI 和 final SQL 无重跑。[首次读回失败及旁路事实](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-readback-first-failure.json)、[计数口径纠正](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-readback-correction-001/reason.json)

根最终读回通过，原受保护文件按约定字段保持，选择器原字节、inode 和权限身份恢复，其时间随选择和恢复变化；三个锁重新取得后释放，产品进程已停止。[根最终读回](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-readback.json) [独立逻辑审阅](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/independent-review-001/REVIEW.md)、[独审结果](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/independent-review-001/result.json)、[根原生接受](../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-native-acceptance.json)

## 剩余范围

只接受本次文字修订完整包登记恢复子集，不关闭 AC-27 的全部对象和全部故障，也不提高 AC-23 或 M0—M6。旧 017 故障窗口漏命中与耗尽预算、旧 020 空白、指定 NVIDIA、跨主机、五名首次用户、干净安装及公证等缺口保持。E128／E129 与之前 026 记录保留原句；本轮单次启动也不替代 20 次主窗口初显验收。[026既有进度](2026-09-14-ver2-4-026-progress.md)、[017历史记录](2026-09-13-ver2-4-017-progress.md)、[026既有包接受](../../.artifacts/integration-ver2-4-026-v1/root-bundle-acceptance.json)
