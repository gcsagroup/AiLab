# Ver2.4（030）工作库连接隔离：E138

当前固定路径公司签名候选为 Ver2.4（030）。源码测试、唯一构建、根整包复核和包内两项真实控制服务测试已完成；原生完整备份、目标库启动失败回滚、成功切库、分别保存项目及同号重开的有限子集已获根接受，正常退出、停机读回与原库选择恢复通过。029／E137 与更早历史保留，不提高完整 AC 或 M0—M6 状态。

## 修复范围与源码验证

普通 API 请求及媒体读取在调用时绑定非凭据连接身份。宿主在发送前和完成后复核该身份；切库、回滚或重启会拒绝旧请求和迟到响应，写入不会自动使用新库身份重发。同一连接的启动通知保留有效读取，真正重连则作废旧环境检查，等待宿主操作完成后再读取状态。

574 项前端测试、52 项普通宿主测试及类型检查通过。宿主临时 HTTP 服务验证旧库请求没有到达新库；对应红例和初始化通知竞态的修前失败保留。普通宿主测试中的 3 项现场测试未被计作通过，后续另执行其中两项，结果见下节。[前端回归](../../.artifacts/host-connection-scope-ver2-4-next-v1/frontend-tests-001/regression-delivery.log)、[宿主测试目录](../../.artifacts/host-connection-scope-ver2-4-next-v1/rust-tests-001)

原生文件、目录及 Python 环境选择器等待期间跨库的异步竞态未覆盖；本次不能解释为所有异步命令已隔离。没有新增模型能力或训练预算。

## 唯一构建与签名复核

构建前可用容量 109.523 GiB，高于原 40 GiB 门槛；保留 029 归档，没有清理或降低门槛。唯一正式构建耗时 529.041263 秒、退出 0，自动更新四个版本文件。根复核对应提交 `8cb19da3e2f99a4a433d70e8d139cf8f800c3336`，615 项跟踪输入、161 项生产来源、211 项冻结文件及 91 项应用输入一致。[构建回执](../../.artifacts/integration-ver2-4-030-v1/build-process-final.json)、[根整包复核](../../.artifacts/integration-ver2-4-030-v1/root-frozen-check.json)

整包包含 21966 个普通文件、48 个符号链接和 4003 个目录。7 个目标均由 Global Cybersecurity Alliance Limited 签名，团队 `R3JK7R29AC`，证书 SHA1 为 `7C33B517942161311A087CE893D2F1CE9B204B44`。构建阶段 47 项保护记录保持，029 归档整包保持；该阶段未启动 App、未连接业务 SQL，也未追加模型探测。[签名报告](../../.artifacts/integration-ver2-4-030-v1/bundle-verification.json)、[冻结来源](../../.artifacts/integration-ver2-4-030-v1/source-build-manifest.json)

构建后以当前包内控制服务真实执行重启认证与迁移失败回滚两项测试：2 通过、0 失败。测试使用临时库，不表示原生界面已经重现迁移失败；钥匙串现场测试仍未执行。12 项版本同步测试通过。[真实控制测试](../../.artifacts/integration-ver2-4-030-v1/real-control-tests.stdout.log)、[版本测试](../../.artifacts/integration-ver2-4-030-v1/version-tests.log)

## 原生有限接受与停机读回

生产界面在本次新建的测试库 A 完成完整备份，显示 1 个文件、56.0 KB；恢复到新目录 B 后显示文件已校验。测试锁占用 B，使目标控制服务启动失败；界面原话为 `服务启动响应格式无效。 已恢复连接原工作库。`，A 控制进程由 32356 变为 51024，随后成功保存 A 的新项目。[备份界面](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/02-A-backup.txt)、[恢复校验](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/03-B-restored.txt)、[失败回滚界面](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/04-switch-failed-rollback.txt)、[失败后读回](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/failed-switch-readback.json)

释放 B 锁后，同一 App 成功切入 B，控制进程为 51729；B 起初仅有共同项目，没有 A 回滚后新建的项目，并成功保存 B 的新项目。第二次从同一固定路径启动同号 App，App／控制进程为 52923／52928，B 新项目仍在。两次均正常退出，退出码均为 0。[切入 B](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/B-connected.json)、[B 保存后界面](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/07-B-saved-after-navigation.txt)、[重开进程](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/B-reopened-processes.json)、[重开项目菜单](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/09-B-reopened-project-menu.txt)、[首次退出](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/launch-001/exit.json)、[再次退出](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/launch-002/exit.json)

停机读回确认 A／B 保留同一编号的共同项目，各自新增项目只在本库；B 重开前后全部表内容及数据库摘要相同，资源／事件／命令数均为 0。44 项既有保护记录（含不存在项和重复路径）的摘要与元数据不变，原选择文件字节、inode 和模式恢复；重命名导致的 ctime 变化明确保留。App、控制服务、恢复保护守卫及 B 测试锁进程均已停止。[根停机读回](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/root-readback.json)

现场续接发现原保护守卫 32132 已退出，App 仍运行在本次测试库，原选择文件保留；后来重新取得原库保护锁，恢复守卫 41356 与 B 锁进程 50865 已正常收尾。中断原因及精确时长未知，文件读回保持不能证明保护锁全程连续；此事件不被后续通过覆盖。[守卫恢复记录](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/selector-guard/guard-recovery.json)、[恢复时保护读回](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/selector-guard/recovery-readback.json)

独审及根回执接受上述有限子集，同时保留采集缺口：06 的菜单未展开，不能独立证明 B 新建前完整项目列表；09 只有展开菜单 AX 文本，没有对应截图。A 新建后的独立截图与退出确认截图未保存，A 写入由停机快照及回滚进程记录支持，两次正常退出由退出回执支持；这些证据不能独立还原每次点击或退出框视觉内容。界面错误文案泛化，目录被占用的具体原因来自底层日志，不能写成界面直接显示该原因。[原生独审](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/independent-readback-review.md)、[根有限接受](../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/root-native-acceptance.json)

本次原生证据是目标库因锁占用而启动失败后的回滚，不是原生迁移失败验收，也未在现场确定性重现排队旧 IPC 竞态。迁移失败回滚有前述包内真实控制测试，旧请求隔离有宿主 HTTP 测试；两者与本次原生界面证据分别记录。

## 保留的验收边界

原生选择器异步竞态、指定 NVIDIA Linux 设备与跨主机回传、媒体人工质量、干净安装、五名首次用户、公证及正式分发仍未完成。既有质量失败、预算、020 长列表空白及性能证据缺口不因本次签名或测试通过而关闭。[当前交付矩阵](2026-09-10-current-delivery-matrix.md)

本页的 `.artifacts` 链接仅指本机证据，不随 GitHub 源码发布；源码、文档、签名构建、原生局部验收与正式发布分别记录。
