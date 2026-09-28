# 桌面宿主开发与本机候选构建

应用身份固定为 `org.gcsa.ailab`，签名使用 `Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)`。这是本机候选签名；尚未完成 Developer ID 签名、公证或独立机器发布验收。

当前候选仅面向 Apple Silicon / macOS 26 及以上：本机 Python 3.13 框架的 Mach-O 最低系统版本为 26.0。不能将桌面壳自身可支持的旧系统版本当作整包兼容证据；后续需要更低版本支持时，应替换为相应构建的 Python 运行时并在目标系统验证。

## 启动

App 开发、运行、原生测试和交付共用 `apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app`。完整构建使用 `scripts/desktop/build.sh`，随后用 `scripts/desktop/run.sh` 启动；`dev.sh` 也调用同一入口，避免另开 debug App。`run.sh` 先核对版本和冻结清单中的身份，旧包不会被误当作当前候选。网页热更新仍可单独运行 `npm run dev`，但网页检查不能替代 App 原生验收。开发控制服务需要已准备的 `services/control/.venv`，可用 `AILAB_DATA_DIR` 指定独立测试目录、`AILAB_WORKER_PYTHON` 指定独立 MLX 环境；生产包不接受这些开发覆盖值。

关闭窗口保留本机后台任务；点击 Dock 图标重新打开窗口。退出应用先显示本机任务停止提示，确认后先请求控制服务退出并回收执行器。宿主只管理自己启动的进程句柄，未使用进程名称扫描或全局终止。

## 前端合同

- `invoke('api_request', {request:{method,path,body?,idempotency_key?}})`：成功返回业务 JSON，失败返回标准错误结构。
- `invoke('api_media', {artifactId})`：只读取已登记产物的受认证内容接口，限定 PNG、MP4、WAV 与 64 MiB，返回 `{media_type,base64}`；界面生成临时 Blob URL 预览并在离开时释放。
- `invoke('host_status')`：返回服务状态、中文说明、可用时的 PID、端口，以及宿主受控来源设置 `market_fixture_origin`（默认 `null`）。
- `invoke('restart_control')`：已运行时直接返回当前状态；服务退出后启动新进程，不自动重跑任务。
- `invoke('pick_import_path', {kind:'model'|'dataset'|'image-dataset'|'material'|'backup'})`：打开原生选择器，取消返回 `null`，选取后返回 `{path,grant_id}`。图片数据选择目录，素材选择 PNG 文件；导入或恢复计划携带此授权编号。
- `invoke('pick_worker_python')`：选择已有 Python 环境并在原生确认框中应用，返回完整设置；取消返回 `null`。前端不能通过通用代理替换执行程序。
- `invoke('pick_media_python', {engine:'diffusers'|'kokoro'})`：选择图片/视频或中文配音的独立 Python 环境，使用相同原生确认和设置版本核对，分别更新 `media_python` 或 `audio_python`；其他环境保持原值。
- `invoke('use_bundled_worker')`：无参数切回内置 MLX，检查内置执行器存在后清除外部 Python 选择，并返回完整设置。
- `invoke('use_bundled_media', {engine:'diffusers'|'kokoro'})`：检查对应内置执行器存在后，只清除该类外部 Python 选择，并返回完整设置。
- `invoke('pick_export_directory')`：选择已有导出目录，取消返回 `null`，选取后返回 `{path,grant_id}`；这是当前会话的导出写入授权，与导入读取授权分开。
- `invoke('use_restored_library', {restoreId})`：仅接受已完成的恢复记录。宿主向控制服务现场验证完整文件，以独立宿主凭据冻结新写入，停止旧服务后启动新目录；健康检查成功才保存选库设置，失败会重新连接原工作库。
- `invoke('configure_market_fixture', {origin})`：显式设置 `http://127.0.0.1:端口`，或传 `null` 关闭夹具来源。只登记固定 `fixture-provider`，不启动提供方。宿主先申请无活跃写入、下载或执行器的重配置门禁，再在同一工作库重启；健康检查和独立 `host-settings.json` 持久化成功后返回 `{market_fixture_origin,status}`，启动或保存失败会恢复原配置。该设置不写进工作库备份，也不从环境变量隐式注入。
- 事件 `host-status` 通知控制服务状态变化；前端也可以读取状态完成首次同步。

认证令牌保存在 Rust 内存中；WebView 不持有控制服务令牌。切换工作库和重配置另用仅从 stdout 握手发给 Rust 的宿主凭据，不写入开发桥接的令牌文件。代理只访问固定回环地址、固定接口前缀和已登记业务资源，拒绝重定向、路径穿越、额外认证头、前端自行创建导入授权以及直接调用工作库激活或宿主重配置接口。

完整备份以短数据库锁冻结 SQLite，再按不可变引用复制模型、数据、适配器、冻结评测与原运行证据。恢复先检查完整闭包、数据库结构、文件摘要、读取授权及独立目标授权，随后恢复到已有目标目录下的新子目录。macOS 无覆盖原子重命名保证发布时不会替换已存在目录。计划与命令回执保存在原库的 `backups/.commands`，不写原业务数据库；同一命令在服务重启后仍可核实原恢复结果。原始快照和产物文件保持原字节，数据库中的迁移引用明确记录原快照、原摘要及路径映射。恢复清除原机器外部 Python 选择与旧幂等响应，新运行默认使用本包内置执行器。

当前数据库版本为 4；新库直接创建当前结构。旧库按 v1→v2→v3→v4 逐步迁移：前两步新增分页及按任务查询最近执行的索引，v4 标记来源组划分及成对数据资源语义，保持原表结构和业务正文。每一步都先在 `migrations` 保存包含 WAL 的一致副本、SHA 和持久回执，再事务更新版本；失败回滚并禁止初始化运行器，未知未来版本只读拒绝。初始回执完成前的临时目录不会妨碍中断后重试。完整备份支持数据库版本 1、2、3、4，清单版本必须与实际数据库一致；单库不超过 1 GiB，数据库与最多 50000 个引用文件合计不超过 32 GiB。资源检查使用可重复的只读迭代，恢复按 512 行迁移引用，避免百万条元信息全部驻留内存。

集合接口每页只从 SQLite 读取限定行数。任务、作品、工作流与执行历史默认最新在前，降序游标带 `desc:`，旧升序游标不能混用。任务列表返回概要和最近执行的状态摘要，草稿在单任务接口读取；单任务附首 100 条执行摘要及下一页游标，完整快照、正文和产物只在单执行接口读取。前端显式加载下一页，不在后台自动拉完整集合。

存储清理先生成包含精确路径、字节数、文件摘要和理由的计划。用户明确执行后，只把当前库 `assets` 中没有项目、运行、检查点、备份或恢复引用的不可变资产移到本库 `trash`，保留原始清单并支持恢复；没有永久删除接口。原运行证据、项目外下载与缓存不在清理范围内。计划后引用或文件变化、存在运行/切库/备份操作时均拒绝移动；恢复时原位置被占用也拒绝覆盖。同一命令可在中断后核实并继续，清理期间仍可读取已有内容。

## 构建与验证

`scripts/desktop/version.json` 是唯一版本源。小修改递增括号内构建编号，新增功能调整功能版本，大范围变化调整主版本；例如版本 `2.2.0`、构建 `7` 显示为 `Ver2.2(007)`。`build=0` 只表示该功能版本尚未产生候选包。每次实际完整候选构建开始时，`app_version.py begin` 只递增一次，并同步 package／Cargo／Tauri／控制层／前端版本；内部执行器打包和测试不另占编号。`CFBundleShortVersionString` 保存功能版本，`CFBundleVersion` 保存构建编号，界面和诊断读取生成常量，“技术预览”等验收状态独立显示。不要手工编辑生成字段。

完整候选构建使用互斥目录保护固定输出。每次编号和开始、成功或失败记录保存在 `.artifacts/desktop/version-history/build-NNNN.json`，失败不回收编号；进程被强制杀死留下的 `building` 和互斥目录须在确认无构建进程后处理。结束时版本脚本核对固定路径的 `Info.plist`、冻结版本摘要及当前源码；成功记录同时固定完整包验证报告摘要。旧 `0.1.0` 证据保留原版号。可运行 `services/control/.venv/bin/python scripts/desktop/app_version.py check` 做只读同步检查。

`scripts/desktop/build.sh` 将控制服务、执行器与配方源码暂存到同一份 `.artifacts/desktop/source-*`，使用独立打包环境制作自包含控制层、MLX、Diffusers 与 Kokoro 执行器，再执行前端构建、Tauri 构建及签名检查。所有执行器的依赖许可随包携带；模型权重和用户数据由用户导入，不进入安装包。`scripts/desktop/toolchain.sh` 只为本次命令选择本机已有的独立 Rust 1.95 工具链。

媒体运行时分别使用已验证的 Python 3.13.9 与 3.10.19，不能合并到同一个依赖环境。`runtime-*.lock.txt` 与对应 `sources.json` 固定版本、官方下载地址及 SHA；构建只安装通过摘要验证的缓存。`package_media.py` 收集动态模块、冻结依赖的数据文件、真实源码和 metadata，并生成许可索引与完整文件清单。所有数据来源汇合后，使用 PyInstaller 自带展开器解析目录与 glob，仅排除最终目标 `torch/include/` 下的 `.h`、`.hpp`、`.cuh` 开发头文件；预编译运行库、元数据、许可和其他路径保持。该规则有两固定打包环境的专门测试；改过收集范围的包仍须通过实际媒体配方复验才能交付。媒体脚本与受限解析依赖也保持原目录关系，从同一快照复制到资源中的 `workers`、`adapters/media` 和 `services/control`，使运行时身份可逐文件对齐。显式外部 Python 选择优先；无选择时使用宿主传入的包内执行器，不自动查找开发目录。

冻结媒体入口只允许完整匹配的标准库资源追踪调用，检查当前解释器生成的完整选项和继承的只读管道，再直接调用固定函数；不会执行传入的 Python 文本。探测会实际启动同参数子进程并要求自然退出成功。视频验收同时拒绝追踪器异常、入口执行失败及资源泄漏警告。

`package_media_tools.py` 将 FFmpeg/FFprobe 的实际动态库闭包复制到包内，重写非系统加载路径、保留许可和构建信息，并逐个签名。当前来源为启用 GPL 的本机 FFmpeg 8.1.1，最终分发需按该组合履行相应许可义务；构建成功只证明本机候选，不能替代独立机器或发布验收。

Tauri 资源通配拷贝会展开符号链接，因此 `seal_runtime.py` 先还原各自包含运行时的包内链接布局，使 MLX 能从动态库的真实目录找到 Metal 资源。最终签名会改变嵌套二进制，脚本在嵌套代码完成签名后重算全部运行时清单，再签外层 App。`verify_bundle.py` 检查外层及所有入口的证书指纹、包内链接、动态库路径和运行时完整性，并将控制清单中的执行器、配方、入口和依赖锁摘要逐项与内置运行时对齐。

真实运行验收使用 `verify_mlx_runtime.py`：将整份内置运行时复制到带空格的新路径，以仅包含 `/usr/bin:/bin` 的 PATH 和空工作目录启动，执行探测、预检查与持久登记后的授权生成。加上 `--evaluation-snapshot` 会继续用固定计划启动两个独立进程，分别加载基线与候选，保留质量报告，不把执行成功当作评测达标。示例：

```sh
.artifacts/desktop/package-venv/bin/python scripts/desktop/verify_mlx_runtime.py \
  'apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app/Contents/Resources/resources/mlx/ailab-mlx' \
  --snapshot .artifacts/m0-mlx/evaluation-20260910-01/candidate-evaluation.snapshot.json \
  --evaluation-snapshot .artifacts/m0-mlx/evaluation-20260910-01/candidate-evaluation.snapshot.json \
  --output .artifacts/desktop/bundled-runtime-acceptance
```

`verify_media_runtime.py` 接受 `--image-snapshot`、`--train-snapshot`、`--video-snapshot` 和 `--audio-snapshot`。它将所需运行时和媒体工具一起复制到带空格目录，使用全新 HOME、空 cwd 和最小 PATH 完成真实预检查与两阶段授权执行；训练后重新加载新适配器生成图片，视频用包内 FFprobe/FFmpeg 独立读取并解码 14 帧，配音检查完整 24 kHz 单声道 WAV。`--cancel-video` 在实际完成第一个去噪步后取消，要求没有完成事件且同组进程自然回收。原验收快照只读保留，每次按搬迁后的实际环境重新冻结执行配方。该脚本报告须与最终 App 的源码清单和签名一同核对，不能用中间运行时报告替代最终原生 App 验收。

Rust 代表性测试：`cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib`，覆盖归属回收、无关进程保留、身份错误、启动超时、崩溃重启、代理路径与请求边界。已准备控制环境后显式运行 `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib real_control_handshake_authentication_and_restart -- --ignored`，检查真实健康响应、认证、崩溃重启、会话令牌更新和退出端口关闭。设置 `AILAB_TEST_CONTROL_BINARY` 可用相同测试验证自包含控制程序。完整应用仍需实际打开，验证真实业务请求、退出与签名身份。

## 同一候选的启动测量

`verify_startup.py` 默认通过 macOS `open -W -n` 前台启动固定路径 App 20 次。每轮核对新App的完整可执行路径、PID和启动身份，并验证回执中的控制进程属于该App；回执须在项目资源与环境加载完毕、界面经过两次呈现调度后由原生宿主写入。脚本等待App及控制服务停止，再要求操作者输入 `已确认退出`，确认已通过原生菜单和确认框正常退出；不能确认或输入结束则保留失败轮，不继续启动。启动器退出码与未知的App退出码分开记录，不用启动器成功替代正常退出证据。

```sh
services/control/.venv/bin/python scripts/desktop/verify_startup.py \
  --output .artifacts/desktop/startup-acceptance-v1 --rounds 20
```

输出目录必须不存在，每轮单独保存回执、外部耗时和退出结果。报告版本为 `schema_version: 3`；原 `twenty_launch_target_passed` 字段改为 `twenty_full_readiness_under_3000_ms`，仍统计完整20轮是否全部不超过3000毫秒。该值只描述完整就绪；`initial_visibility_target_passed` 保持 `null`，`initial_visibility_evidence` 为 `not_measured`，初显目标仍须独立的20次真实界面测量。失败轮、慢样本及旧批次保留，不回写历史报告。这是独立进程启动测量，保留操作系统文件缓存，不代表系统重启或干净安装。启动前会拒绝版本或签名不符、已有App进程、未结束任务、恢复待处理和活动下载。

停机前后检查会先持有工作库的控制服务排他锁，并拒绝任何已有数据库旁路，再以 `mode=ro&immutable=1` 读取主库，避免检查本身生成WAL或SHM。活库只读逻辑仍使用 `mode=ro`，不会忽略已提交的WAL。首次原生工具验证暴露的旁路文件已单独保留；修复后的原生复验已完成，停机后没有新旁路，数据库及全部表保持不变。

系统启动器、App标准输出和错误分别保存，文件权限为 `0600`。约100毫秒轮询核对进程和回执；外部耗时包含系统启动、进程检查及文件写入，宿主回执耗时另行保留。出现重复App、身份变化、错误控制进程或超时就停止本批次；不强制退出、不自动重启，仍在运行的启动器PID保留供现场处理。

固定037已通过修复后的正式命令单轮原生验证：新App和所属控制进程核对通过，宿主完整就绪4.933秒、外部观察5.029秒；实际执行原生退出确认后，操作者才确认退出，工具正常结束。原库选择与保护项恢复，没有新模型执行；50项测量测试通过。单轮与完整就绪均不替代20次初显验收。[工具修复和原生停机核对](../../.artifacts/startup-launchservices-tool-ver2-4-037-v1/root-readback.json)。

037 原生对照发现：直接运行包内可执行文件时，数据及环境在前端约5.546秒就绪，但页面报告 `hidden`，直到退出流程附近才生成518.761秒的完整就绪回执。同一独立库使用 macOS `open` 正常启动，完整就绪为5.943秒，阶段记录没有 `hidden`。这是单次启动方式对照，不证明全部历史长尾的原因，也不替代20次初显验收。对照形成时 `verify_startup.py` 仍直接运行可执行文件；现已按上方说明修正，工具的原生验收仍须单独记录。

两次均经原生退出确认，App和控制服务已停止；系统启动只观察到 `open` 退出码，未取得App退出码。新库第一次只更新界面选择，第二次数据库及全部表完全不变；原库选择及保护项已恢复，没有新增模型执行。原始记录、工具超时和复核运行环境错误均保留。[原生对照与停机核对](../../.artifacts/native-startup-diagnosis-ver2-4-037-v1/root-readback.json)。

## 本地候选更新与恢复

`candidate_update.py` 只更新本项目固定 App 路径。先对本地已签名新候选生成计划，再用计划SHA执行替换；双方必须属于本项目组织证书，新候选版本必须更高。计划固定双方完整目录摘要、选中工作库与数据库内容，执行前再次核实静止状态。新包暂存并校验后才移动旧包；旧包、新候选来源和回执全部保留。该工具不联网，不自动启动App。

```sh
services/control/.venv/bin/python scripts/desktop/candidate_update.py plan \
  --source '.artifacts/desktop/candidates/GCSA AI Lab.app' \
  --output .artifacts/desktop/candidate-updates/update-v1
```

检查生成的 `plan.json` 后，执行 `apply --plan <计划绝对路径> --sha256 <计划SHA>`。中断时对同一计划执行 `recover`，完整替换后需要回退时执行 `rollback`。每个计划只应用一次，完成或中断后不重复apply。恢复按磁盘上的实际包摘要判断，遇到未知包或已占用位置会停止并保留现场。

替换前的 `database-backup` 保存包含WAL的一致数据库和库选择设置，**不包含模型、素材等资产**。旧0.1.0包只支持schema1；新版运行升级到schema3后，工具拒绝旧包回退，也不降级数据库。此时必须使用已有完整备份恢复流程。脚本测试通过仍不替代真实旧包升级、失败回滚和新版原生验收。

## 验收保护与文件句柄耗尽

`guard_file_limits.py` 供持有资料库锁的验收脚本使用。`wait_for_guard_exit` 在退出标记、进程探测或心跳遇到 `EMFILE/ENFILE` 时继续等待，保留锁和故障计数；恢复后重新探测进程，不能沿用等待前的停止状态。`retry_file_limit` 只适用于可安全重复的读取、原子心跳写入及幂等恢复，不得包裹模型执行或追加业务记录。其他错误仍向上报告；调用者必须负责锁、选择器恢复和最终证据保存。

11 项测试通过，包括自有子进程降低文件描述符上限、真实触发 `EMFILE`、父进程确认故障期间锁不可取得，以及释放句柄后恢复。测试不修改系统限制或访问用户资料。此工具不补回观察缺口，也不修复系统句柄耗尽的来源；051 历史中断仍不计完整验收通过。
