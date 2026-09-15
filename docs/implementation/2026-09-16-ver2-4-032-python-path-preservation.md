# Ver2.4（032）Python 路径保留与环境恢复：E140

032 固定路径公司签名包通过根整包复核。真实原生面板保留 venv Python 符号链接原路径，三环境保存、同号同库重开、恢复内置、两次正常退出与原资料保护恢复的有限子集已获根接受。外部 venv 依赖探测失败保留；没有执行模型，也不提高完整 AC、M0—M6 或发布状态。031 路径失败及原验收门槛保持历史原文。

## 源码与签名包

macOS Python helper 显式设置 `setResolvesAliases(false)`，在主线程使用原生面板并保留返回的文件 URL 路径；原连接身份校验与用户确认保持。66 项宿主测试通过，3 项既有现场测试忽略；新增 5 项 Foundation／临时文件测试不创建面板，不能单独证明原生选择效果。[源码回执](../../.artifacts/python-picker-symlink-ver2-4-032-v1/source-fix-001/run-summary.json)

唯一正式构建退出 0，根复核以提交 `819c35dab2c621e90e79725aae8090ac0d291841` 为基线，加上 4 项构建自动更新为 032 的版本文件；该提交自身仍为 031。624 项跟踪来源、162 项生产来源、212 项冻结文件与 92 项应用输入核对一致；整包 21966 个普通文件、48 个链接、4003 个目录及 7 个公司签名目标通过。签名组织 Global Cybersecurity Alliance Limited，团队 `R3JK7R29AC`；031 归档和构建阶段 47 项保护记录保持。[构建回执](../../.artifacts/integration-ver2-4-032-v1/build-process-final.json)、[根整包复核](../../.artifacts/integration-ver2-4-032-v1/root-frozen-check.json)

## 原生选择、保存与重开

本轮只用新 A 独立库与同一固定 App。先取消文件面板，再选精确 `services/control/.venv/bin/python`，确认框保持该原路径并取消；随后普通文件对照选择解析后的基础 Python，确认显示同一普通路径后取消，未保存对照路径。正式 worker、media、audio 选择各保留面板 URL 和确认框记录。[符号链接选择](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/04-venv-selected-before-cancel.ax.txt)、[取消前确认](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/05-venv-confirm-before-cancel.ax.txt)、[普通文件选择](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/07-ordinary-python-selected.ax.txt)、[普通文件确认](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/08-ordinary-python-confirm.ax.txt)

三环境分别明确确认保存后，首次正常退出 0；停机读回 `worker_python`、`media_python`、`audio_python` 均精确等于原始 venv 绝对路径，revision 为 4，资源／事件／命令均为 0。取消和普通文件对照未增加环境 revision。[external 检查](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/external-check.json)、[首轮快照](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/a-after-first.json)、[首次退出](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/app-first/exit.json)

第二次启动绑定同一 App、同一 A 和首轮数据库摘要。设置界面不显示精确字段，因此持久化依据首轮停机字段、重开前摘要绑定、实际同库重开及第二轮读回共同成立，不仅凭按钮判断。依次恢复三个内置环境后正常退出 0；三字段均为显式 null，revision 为 7，资源／事件／命令仍为 0，原 4／7 门槛未降低。[重开状态](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/23-second-external-status.ax.txt)、[bundled 检查](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/bundled-check.json)、[第二轮快照](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/a-after-second.json)、[第二次退出](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/app-second/exit.json)

## 保护恢复、失败与证据限制

守卫跨两次运行持有，最终恢复与释放回执完成；App、控制与守卫均已停止。47 项保护记录中 44 项严格不变，含不存在项和重复路径，并非 44 个不同现存文件；selector 原字节、inode 与权限恢复，ctime 差异保留，两份 startup 日志允许实际更新。根读回及接受仅覆盖本页有限子集。独立审查亦通过该限定路径子集。 [独立审查](../../.artifacts/python-picker-symlink-ver2-4-032-v1/independent-native-review.md) [恢复](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/selector-guard/restored.json)、[释放](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/selector-guard/released.json)、[根读回](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/root-readback.json)、[根有限接受](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

外部 venv 的四类自动依赖探测失败，重开时仍显示失败；恢复内置后四类界面均显示环境已准备。这只证明相应依赖状态变化，不是模型运行或质量通过。本轮没有安装依赖、执行模型、导入数据或导出诊断 ZIP。[外部状态](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/20-all-external-save-status.ax.txt)、[内置状态](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/26-all-bundled-status.ax.txt)

原生证据保存 28 组、56 个 AX 与截图文件；截图后缀为 PNG，实际字节为 JPEG／JFIF，原件保留不改写。19 及 19b 音频确认截图异常缩小，路径结论依据原始 AX、实际确认与停机字段。根读回脚本前两次因普通文件 AX 属性顺序及 `@` 的 URL 编码差异失败；改为提取 selected 行的文件 URL 并严格核对解码路径后通过，原失败和原 4／7 门槛保持。worker 曾误选其他行，打开前已纠正到精确 Python，未保存错误路径；首个截图帮助函数参数错误亦保留。[音频确认 AX](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/19-audio-python-confirm.ax.txt)、[原异常截图](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/19-audio-python-confirm.png)、[根记录](../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/root-readback.json)

本轮没有复现原生跨库竞态，也未关闭诊断目录导出、指定 NVIDIA／HTTPS 跨机、同份 LoRA 回程、既有质量失败、媒体人工评审、干净安装、五名首次用户、公证和发布门槛。031 及更早阶段继续按原版本归属。[031 失败记录](2026-09-16-ver2-4-031-native-picker-progress.md)、[交付矩阵](2026-09-10-current-delivery-matrix.md)

本页 `.artifacts` 链接为本机证据，不随 GitHub 源码上传。全部正式文档和历史记录继续提供简体、繁体、英文三语版本。
