# Media 三入口键盘进度：E136—E137

**最新 Media 键盘进展（2026-09-16，E137）**：固定公司签名候选已更新为 Ver2.4（029）。唯一构建、三入口在两个既有任务中的四个原生实例、正反向 Tab、Enter 打开、Escape 关闭回焦、正常退出及一次停机读回的有限子集已获根接受。523 资源／673 事件／3 命令及全部业务记录保持，仅四个预期页面设置叶子变化；没有真实导入或模型运行。028 与 027 的既有有限接受保留，完整 AC、M0—M6、公证及公开发布未完成。

## E137：029 签名包与原生有限接受

### 包与构建证据

本次执行前容量约 117.39 GiB，高于原 40 GiB 门槛；没有清理或降低门槛。028 回滚归档成功，26 项构建门槛合成测试、8 项根验包器测试及 12 项版本同步测试通过。唯一 029 构建耗时 496.86 秒、退出 0，构建自动更新四个版本文件；160 项生产来源、210 项冻结输入、90 项应用输入及 21966 个普通文件／48 个符号链接／4003 个目录一致，7 个公司签名目标通过根复核。正式构建前相对 028 的生产源码变更仅为 Media 三处键盘属性。[028 归档接受](../../.artifacts/integration-ver2-4-029-v1/archive-tool-receipt.json)、[构建门槛测试](../../.artifacts/integration-ver2-4-029-v1/root-script-acceptance.json)、[根验包器测试](../../.artifacts/integration-ver2-4-029-v1/root-verifier-acceptance.json)、[版本同步测试](../../.artifacts/media-keyboard-ver2-4-next-v1/resume-20260916-001/version-tests.json)、[029 包接受](../../.artifacts/integration-ver2-4-029-v1/root-bundle-acceptance.json)

### 原生界面与停机数据证据

同一次 029 App 在两个既有任务中验证四个入口实例：图片训练的模型／图片数据，以及视频运行的模型／图片素材。正向 Tab 与反向 Shift-Tab 均可达，Enter 打开正确弹窗，Escape 关闭并回到同一入口；19 张截图与 19 份 AX 共 38 文件获根接受。Cmd+Q 后 CUA 曾短暂返回 pipe closed，随后重读同一 App 的退出确认框并点击退出；没有重启，唯一启动正常退出 0。[原生焦点接受](../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/root-focus-acceptance.json)、[正常退出记录](../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/run/result.json)

停机后实际仅建立一次 immutable 只读连接，读回退出 0 并关闭连接。523 资源／673 事件／3 命令及全部业务记录严格保持，两个任务草稿版本仍为 2／3，`module_tab=train` 与原文字最近任务保持。差异恰好为四个页面设置叶子：`kind`、`task_id`、`recent_tasks/image:train`、`recent_tasks/video:generate`。库选择已恢复，选择文件内容与 inode 保持但时间变化；旧库、旧导出包和既有远程进程保护保持。[停机读回根接受](../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/root-readback.json)

本次根接受仅覆盖上述有限子集，没有真实文件导入、业务保存或模型运行；独审已接受上述有限子集；截图与 AX 为保存状态，不代替逐键事件日志。[原生独审](../../.artifacts/media-keyboard-ver2-4-next-v1/native-review-001/review.md)。028／027 既有成果保留，完整键盘、完整 AC／M0—M6、NVIDIA、跨端、干净安装、五名首次用户、旧质量失败与预算、旧 020 空白及首显／完整就绪缺口、公证和公开发布均不因此完成。包回执中的“尚未启动原生”及以下旧记录保留形成时含义。

## 2026-09-15 历史准备记录

以下 E136 及更早记录保留 2026-09-15 形成时原文；其中容量不足与尚未构建描述属于历史状态。

当前固定公司签名候选仍为 Ver2.4（028）。Media 三个导入入口的源码修复、56 项相关前端测试及真实 Safari 键盘子集已接受，独审已由根关闭；029 尚未归档、打包或原生验证。容量低于原 40 GiB 门槛，缓存清理仍待用户确认，没有执行删除。028 的既有接受保留，完整 AC 和 M0—M6 不提高。[028 历史进度](2026-09-15-ver2-4-028-workbench-keyboard-progress.md)

## E136：三处属性、相关测试与独审

相对冻结的 160 项生产来源，仅 `apps/desktop/src/Media.tsx` 改变：为“导入模型”“导入图片数据”“导入图片素材”三个原生 button 增加 `tabIndex={0}`。严格移除这三处属性后，整文件逐字节恢复为 028 修前版本；其余 159 项来源保持。按钮类型、导入回调、筛选、分支及真实 Workbench fieldset 禁用逻辑未变。[源码根接受](../../.artifacts/media-keyboard-ver2-4-next-v1/root-source-acceptance.json)

正式红例为 8 项中 7 通过、1 失败，该失败包含三个入口缺少属性的断言；首次 JSDOM 未提供 showModal 的 setup 失败原件保留。修后新测试保持正式红例字节，7 文件共 56 项通过，含新增 8 项；类型检查 exit 0，另有 3 项夹具测试通过，不与 028 的 59 项累加。新增测试验证四种只读／禁用状态下普通点击不导入、正确导入类型、原稿保持及关闭回焦；单元测试的点击和模拟 cancel 不代替真实 Safari Enter／Escape。[红例记录](../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/result.json)、[绿色回执](../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/green-result.json)、[测试范围](../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/green-REVIEW.md)

独审实际查看两组 12 张关键修后截图，并核对源码、事件、AX 及 132 项哈希清单；根随后复核并关闭独审待办。源码接受原件中的 pending=true 保留形成时含义，不是当前仍待独审，也未改写原件。[独立复审](../../.artifacts/media-keyboard-ver2-4-next-v1/browser-review-002/review.md)、[独审根关闭](../../.artifacts/media-keyboard-ver2-4-next-v1/root-review-closure.json)

## Safari 开发组件前后对照

固定回环端口 4328 的页面直接导入真实 MediaFields 与 ImportDialog，使用图片训练和视频运行两个空资源分支；没有控制服务代理或请求回退。观察器只记录普通按键与焦点，不接管 Tab，不主动聚焦；产品 Dialog 自身保留弹窗与回焦逻辑。Safari 的 AppleKeyboardUIMode 保持 0，未改变系统键盘设置。[夹具准备](../../.artifacts/media-keyboard-ver2-4-next-v1/browser-preparation.json)

修前两组共 26 文件，每组 2 次 Tab、2 次 Shift-Tab，启用的三个源码入口被跳过；两组原始记录与哈希保持。修后重新加载页面，两组各 29 文件、38 事件，各有 4 次 Tab、4 次 Shift-Tab、2 次 Enter、2 次 Escape。正反方向均可达两个入口；图片训练打开模型／图片数据弹窗，视频运行打开模型／图片素材弹窗，四次关闭后都回到各自入口，焦点框可见。请求、错误、输入／更改事件及丢弃计数均为 0，没有文件导入、保存或模型运行。[修前签收](../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-before-acceptance.json)、[修后签收](../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-after-acceptance.json)

开始导航时 typeText 丢失 URL 标点而进入搜索页，粘贴曾报超时；确认正确本机地址后才进入夹具。该前置导航问题保留，不计入夹具零 API 请求范围。末两份 AX 未单列 focused 行，最终回到开始锚点由 focusin 与 report.active 证明；不把 AX 缺行写成无焦点。专用 Safari 窗口已关闭，夹具服务已停止，4328 无监听。[修后与停止回执](../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-after-acceptance.json)

## 029 仍待容量、打包与原生验证

当前 App 仍使用固定 028 公司签名包；此次没有更新版本或构建新包。029 继续沿用同一路径及既有归档、保护和构建门槛，不能把源码与 Safari 通过写成 029 包或原生通过。[整合准备](../../.artifacts/media-keyboard-ver2-4-next-v1/integration-preparation-001/plan.md)

容量只读记录在 9 月 15 日北京时间 07:06:10 为 34.084 GiB，低于原 40 GiB 门槛；该数字属于当时观测，执行前仍需重新测量。唯一拟提请确认的范围是本项目 `apps/desktop/src-tauri/target/debug` 调试／测试缓存，目录记账约 8.190 GiB；这是建议，未获清理确认，也未删除。APFS 共享块与快照可能影响实际释放量，不能把记账量算成已可用空间，更不能降低门槛。固定 028 App、release、历史归档、工作库、模型和证据均不在该建议范围。[容量与清理建议](../../.artifacts/media-keyboard-ver2-4-next-v1/integration-preparation-001/capacity-options.md)

本次不新增模型能力，不签真实文件导入、签名 App 的 Media 路径、完整键盘、完整 AC 或 M0—M6。指定 NVIDIA、跨端同份产物、干净安装／公证发布、五名首次用户、旧质量失败及已用预算、旧 020 空白和初显／完整就绪历史缺口保持。[当前交付矩阵](2026-09-10-current-delivery-matrix.md)

## 原生脚本准备：已完成，尚未启动

监督器、停机读回和数据比较脚本已准备并接受独立审查。监督器 10 项、读回 13 项、比较器 12 项合成测试全部通过；正式 Python 3.13 环境也通过这 35 项，其中读回／比较的兼容性复跑不重复计数。读回首次有一个负例没有实际改变输入，修正测试后通过，原失败日志和回执保留，读回规则未放宽。两份独审均未发现阻断项；继承的进程退出逻辑只作静态复核，本轮未重新启动真实 App。[脚本根接受](../../.artifacts/media-keyboard-ver2-4-next-v1/root-native-preparation-acceptance.json)、[监督器独审](../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/supervisor-review.md)、[读回与比较独审](../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/reader-review.md)

后续原生范围限定为两个既有任务中的四个入口实例，只用 Enter 打开、Escape 关闭并检查回焦。比较脚本要求完整业务数据保持，仅允许四个页面选择设置叶子变化；这些是待执行标准，尚无真实读回结果。当前没有建立运行绑定、连接工作库或启动 029 App，缺少正式 029 包及同次界面／退出证据时脚本拒绝继续。[任务范围](../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/task-scope.json)、[监督器脚本接受](../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/root-supervisor-review.json)

9 月 15 日北京时间 07:49:30 的最终只读核对确认：160 项生产来源、029 五份构建准备输入以及固定 028 包七个锚点保持，29 个指定真实执行输出均不存在。该时刻磁盘可用约 28.86 GiB，仍低于 40 GiB；即使把此前 debug 目录约 8.19 GiB 的记账量全部计入，也不足 40 GiB，实际执行前必须重新确认容量。原清理确认尚未收到，未清理或扩大范围，当前版本仍为 028。[状态记录](../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/final-state-001.json)
