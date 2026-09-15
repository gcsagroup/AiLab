# Ver2.4（028）Workbench 四按钮键盘修复

固定公司签名候选已更新为 028。四按钮的最小源码修复、59 项相关前端测试与真实 Safari 子集通过；028 唯一构建、已有任务的原生正反向焦点、正常退出及停机数据子集已获根接受。027 原文字作品纯键盘导出和同号重开的有限接受保留；完整 AC 和 M0—M6 不提高。

## E134：源码与 Safari 组件子集

正式构建前，160 项生产输入相对 027 仅 Workbench.tsx 变化：为“工作台”返回、导入模型、导入数据、新建评测方案四按钮增加 `tabIndex={0}`，保留回调、fieldset 禁用与返回先 save 的逻辑。新增回归修前 1 个用例失败、包含四按钮断言，另 8 个通过；修后 6 文件共 59 项相关测试及类型检查通过，不与 027 的 75 项累计。[源码接受](../../.artifacts/workbench-keyboard-ver2-4-next-v1/root-source-acceptance.json)、[独立审查补充接受](../../.artifacts/workbench-keyboard-ver2-4-next-v1/root-review-acceptance.json)

真实 Safari 组件中，8 次 Tab、7 次 Shift-Tab 后四按钮正反可达，44 条被动记录、2 次 GET，业务写、回调与页面错误均为 0；没有激活入口或改变系统设置。该组件不含原生已有的“划分训练与验证”，不能套用两者的按键数和顺序。[Safari 修后接受](../../.artifacts/workbench-keyboard-ver2-4-next-v1/browser-after-readback.json)

保存 helper 误写旧 ui-before 目录，导致 4 份修前快照哈希变化，部分字节相同的 AX 也被重写；修前正向截图／AX、完整按键和被动日志仍匹配原哈希，覆盖前独审保留，8 份修后原字节另存 ui-after。不能称整套修前快照原封保全，也没有伪造或重跑修前界面抵消错误。[保存事故](../../.artifacts/workbench-keyboard-ver2-4-next-v1/snapshot-save-incident.json)

## E135：028 包、原生焦点与停机读回

9 月 15 日北京时间，唯一 028 构建退出 0，构建自动更新四个版本文件。根整包复核通过：160 项生产来源、210 项冻结输入、90 项应用输入一致，包内 21966 个普通文件、48 个符号链接、4003 个目录及 7 个公司签名目标获接受。固定 App 仍在 `apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app`，签名为 `Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)`；未公证或发布。源码原件的待独审、包原件的尚未启动原生均保留形成时含义，后续接受分别关闭对应待办。[028 包接受](../../.artifacts/integration-ver2-4-028-v1/root-bundle-acceptance.json)

原生打开已有 `task-6fe6ed2f8cbd4a909d93d27e3a9b785c`／“模型微调 · 05:01”，草稿 revision 4、训练步数 64、最近运行 cancelled；界面 50／64 属于旧运行。旧 AX 编号 227 被拒后，fresh 状态中的编号 37 成功打开同一任务，没有错点。实际 9 次 Tab、7 次 Shift-Tab，含前导“AI 辅助”和已有“划分训练与验证”，四目标按钮正反焦点可见且未激活，没有编辑、保存草稿或训练。[原生根接受](../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/root-native-acceptance.json)

保存集为 19 份 AX、19 张 JPEG 加 1 份观察，共 39 文件，集合及摘要已核；前导“AI 辅助”焦点无独立截图，04—18 的 15 份逐项观察不等于每键截图或逐键时钟。系统退出确认仍聚焦 sheet，正常退出由进程回执证明，不称退出按钮已聚焦。[保存证据独审](../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-review-001/review.md)、[运行回执](../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/run/result.json)

唯一原生执行退出 0，1 次 App、0 模型，锁已释放。随后唯一 `mode=ro&immutable=1` 停机连接读取成功并在 finally 关闭，根复核额外 SQL 为 0。523 资源／673 事件／3 命令、项目、schema version 及全部业务记录严格不变，草稿 revision 4 保持；仅当前项目三项 settings 页面选择变化：page 从 assets 到 home，recent_tasks 从不存在到 text:train 指向上述同一任务，task_id 从 null 到同一任务 ID。[停机根接受](../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/root-readback.json)

工作库 SHA 从 `02ed3063…` 变为 `e40dc70d…`，不能声称 App 启动前后库字节或全部 settings 不变；停机读回期间 DB／三旁路文件事实保持，三旁路均不存在。23 项保护中 selector 内容、inode 与权限身份恢复，mtime／ctime 随切换恢复变化；原 020 全树、旧库、既有远程 PID 30114、旧五文件与 027 四文件导出包均保持。[逻辑结果](../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/readback-001/result.json)、[保护明细](../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/root-readback.json)

027 原文字作品完整纯键盘导出、队列同号重开与停机接受不撤回；新增 4 资源／8 事件／1 命令和四文件包仍归 027，不在本轮重复计数。[027 进度原文](2026-09-15-ver2-4-027-keyboard-progress.md)

本轮未验四按钮激活及弹窗业务效果、原生 busy／running／checkpoint 禁用组合或其它完整键盘任务；“工作台”返回会先 save，不能当只读返回。完整 AC-23／AC-27 及其它完整 AC、AC-25 五名首次用户、AC-26 指定跨端同份产物、M0—M6 均不提高。指定 NVIDIA、设备差异、旧质量失败与既用模型预算、干净安装／公证发布、旧 020 偶发空白及冷启动初显／完整就绪的历史缺口保持原状态。
