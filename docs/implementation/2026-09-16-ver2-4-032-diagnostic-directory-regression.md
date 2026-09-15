# Ver2.4（032）诊断目录原生回归：E141

固定 032 公司签名 App 的诊断目录完整流程已获根接受：三语数据导入、目录取消与整次诊断取消、中文空格目录保存、ZIP 完整性与脱敏、同库重开及原资料恢复通过。本轮为选择器改动后的回归，不是首次诊断成功；E61、E88、E120、E122 历史成功及 E140 Python 路径记录保持原文。诊断 ZIP 不替代完整产物导出 AC27，也不提高完整 AC22、M0—M6 或发布状态。

## 固定候选与分层验证

本轮源码基线为提交 `2d4d07745745e4221557a47addfa4055bb466925`，没有重建或改变版本。实际固定包仍为 Ver2.4（032），复核 21966 文件、48 链接、4003 目录及 7 个 Global Cybersecurity Alliance Limited 公司签名目标通过。[包复查](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/root-preflight.json)

95 项控制测试、14 项前端测试通过；控制测试保留 2 项警告。准备脚本 19 项合成测试与启动门禁 25 项合成测试分别通过，只验证各自合同，不替代真实 UI。准备验收器已收紧非页面设置默认值；启动测试首次因中间版本新增阶段字段而失败，修正测试样本后通过，未改生产或降低门槛。[相关测试](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/focused-tests.json)、[准备验证](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-preparation-001/preparation-check.json)、[启动门禁](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/launcher-review-001/gate-tests.json)

## 真实导入、取消与保存

仅使用新 A 独立库，真实选择并导入简体、繁体、英文共 3 条 SFT 样本、650 字节。停机资源恰为 1 个 ready 数据集和 1 个导入计划；源文件、实际副本和资源摘要一致。02 初次在父目录键入文件名误选 seed，未打开；改用完整路径后 02b 精确选中，实际只导入一次。[正确选择](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/02b-dataset-selected-correct.ax.txt)、[导入结果](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/04-dataset-imported.ax.txt)

第一个诊断预览 ready 后，取消原生目录选择，返回仍为 ready，目标目录为空，没有成功提示；再明确取消整次诊断，记录变为 cancelled。重新选择范围并生成第二个预览后，实际选择 `診斷 輸出` 目录并确认保存，UI 显示“诊断 ZIP 已保存，文件完整性已核对。”两种取消不是同一动作，不能以目录为空替代取消状态证据。[目录取消后](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/07-directory-cancelled-ready.ax.txt)、[整次取消](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/08-preview-one-cancelled.ax.txt)、[目录确认](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/11-output-directory-confirmed.ax.txt)、[保存及完整性](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/12-diagnostic-saved.ax.txt)

输出目录恰有 9316 字节 ZIP，包含 `diagnostics.json` 和 `manifest.json` 两个成员，CRC、整体及成员摘要／大小、清单 complete 和应用版本全部吻合。解码内容中不含三语训练原文、测试敏感标记、项目名／ID、数据文件名或个人绝对路径；整体 SHA 为 `d57e4eb0eb26089f5e15c8ec9f88712194b68c6be3225ce91f101a8471ec73ba`。[首次停机检查](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/exported-check.json)

## 重开、保护恢复与边界

同一固定 App、同一 A 两次正常退出均为 0。重开直接恢复原数据页，项目与 3 条样本可见；停机全部数据库表、原始数据库字节和 ZIP 字节前后严格相同。命令恰为 5 项：1 次导入、2 个诊断预览（取消／成功各一）、1 次诊断取消、1 次导出；资源 2 项、执行事件 0 项。诊断 UI 没有历史入口，原诊断登记由停机全表与原 ZIP 证明，不声称重开界面读取历史回执。[重开数据页](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/15-second-restored-dataset.ax.txt)、[重开后检查](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/reopened-check.json)、[两次退出与根读回](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-readback.json)

原 selector 字节、inode 与权限恢复，ctime 差异保留；47 项保护记录中 44 项严格不变，包含缺席项和重复路径，两份 startup 日志允许本轮更新。App、控制与守卫均已停止，恢复及释放回执齐全，不承诺守卫永不中断。[恢复](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/selector-guard/restored.json)、[释放](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/selector-guard/released.json)、[根接受](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

诊断记录包含 3 项 probe 观察与 8 项 environment 观察；App 会话自动探测实际发生，不能称零探测，但没有新增模型任务。原生保存 17 组 AX 与图像、34 个文件；16 第二次退出图像异常缩小，保留原 AX 与退出 0。目录面板列截图未显示末级行，路径由顶部 Where、完整 AX 与返回确认共同核对，不夸称该截图单独显示末级目录。[根限制记录](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-readback.json)

独立原生审查通过本轮诊断目录回归，保留截图及能力范围限制。 [独立审查](../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/independent-native-review.md)

本轮诊断成功不关闭其他产物导出 AC27、干净安装和完整 AC22、指定 NVIDIA 同份 LoRA 回程、质量准入、媒体人工评审、原生跨库竞态、公证及完整 M0—M6。E140 Python 路径有限接受与 031 失败保持。[Python 进度](2026-09-16-ver2-4-032-python-path-preservation.md)、[交付矩阵](2026-09-10-current-delivery-matrix.md)

本页 `.artifacts` 链接为本机证据，不随 GitHub 源码上传。全部正式文档继续提供简体、繁体、英文版本。
