# Ver2.4（035）运行边界验收（E146）

固定 035 包内执行器的单次进程网络拒绝推理已获有限接受；未开放媒体与缓存请求的拒绝测试已发布于 `b96514c`。本轮不重建 App，不提高 M2、完整 AC 或发布状态；原生操作与重开证据仍见 [E145](2026-09-16-ver2-4-035-native-inference.md)。包内控制服务的真实取消与恢复也已通过下述有限子集。

## 进程网络拒绝下的真实生成

普通对照 PID 36199 对新建 IPv4／IPv6 回环端点连接成功；PID 36200 对同端点在 connect 阶段收到 `EPERM`，随后同 PID exec 进入固定包内 worker。一次真实生成正常退出，正文 `7`，6 份产物、0 个 token 增量事件；24 层 KV 初始为空且无跨请求复用。配置保持提示 50／输出预留 78／上下文 128、auto KV、prefill 512、停止序列 `39` 和 `stream=false`。[执行回执](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/result.json)、[原始输出](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/worker.stdout.jsonl)

47 项原保护记录、12 个模型源文件、31 个原生文件及原生数据库摘要前后保持；执行器与对照进程已退出，监听器关闭。没有启动 App UI、连接 SQL 或改变系统网络设置。[根接受](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/root-acceptance.json)、[独立读回](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-independent-result.md)

准备阶段补齐所属进程清理与自然退出竞态处理，并收紧精确产物、配置及缓存核对；早期探针补充操作字段以区分 socket 创建和 connect 拒绝，原记录保留。执行准备的 8 项合成测试及独审重复验证不相加；此前零模型探针的 8 项测试属于另一层，不能当作真实故障注入。[准备审查](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-execution-preparation-001/independent-review.md)、[早期探针记录](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-preparation-001/REVIEW.md)

此处采用验收专用进程网络拒绝策略，实测范围是 IPv4／IPv6 回环 TCP connect；没有逐一探测 DNS、UDP 或外网，不代表物理断网，也不是产品默认 OS 沙箱。同用户文件读取权限仍在；单个短输入不覆盖完整离线工作流程。

## 未开放媒体与缓存请求

保持文字不变，替换媒体身份、交换媒体顺序、改变处理器修订或预处理尺寸，并请求前缀／媒体缓存复用。生产 MLX 校验、预检与执行入口在加载或计算前拒绝；控制服务草稿更新返回 422，旧草稿预检失败后提交返回 409，没有新运行或产物。本轮未发现这些输入位置静默忽略，也没有修改生产代码或实现缓存复用。[入口合同与测试](../../.artifacts/m2-cache-contract-ver2-4-035-v1/review.md)、[独立审查](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cache-contract-independent-review.md)

控制测试的 TestClient 是进程内请求；旧草稿使用正式预检函数替代子进程派发，不代表实际网络或原生界面验收。

新增拒绝矩阵 50 项通过；相关 MLX 回归 139 项、控制回归 50 项通过，包含重复覆盖，不相加。新增负例使用临时文件／数据库和计数拒绝桩，模型加载、计算及缓存创建为零；既有正例的 CPU 缓存数组和夹具生成器不是语言模型实算。这些证据不证明媒体缓存命中、失效或性能。[测试摘要](../../.artifacts/m2-cache-contract-ver2-4-035-v1/result.json)

## 真实取消与恢复

在 sequence 8 阶段消息 `提示词已处理，正在生成` 之后，通过正式回环 HTTP 向固定包内控制服务 PID 37558 提交一次正常取消。worker PID 37568 退出 130，产生 `CANCELLED` 警告；状态、计算结果和收集状态均为 `cancelled`，停止已确认，原因 `USER_CANCELLED`，没有成功产物或作品。该进程组消失后，恢复 worker PID 37583 正常退出并生成正文 `7`、24 层新空 KV 和 6 份产物。[实际运行](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-run-001/result.json)

本轮共 2 次 attempt、1 次取消、0 训练、0 自动重试。 停机只读新库核对 4 条命令、25 条事件、6 份登记产物、0 作品，持久化与 API 一致，读回未改变数据库字节。控制服务正常退出，没有强制清理信号；相关进程及组均已消失，原保护保持。这证明停止后新进程可再次分配并生成，不证明旧 GPU 内存逐字节归零，也不是本轮 App UI 验收。[根接受](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-run-001/root-cancel-acceptance.json)、[独立读回](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-independent-result.md)

准备历史保留：早期脚本收口的 SyntaxError 修复后 44 项测试通过；首次根预检把既有闲置远端协议服务 PID 30114 误判为本地控制服务，在新服务或模型启动前拒绝。改为精确模块匹配后 50 项纯测试通过，175 项来源、47 项保护与 12 个模型源预检通过；旧服务未停止。阶段测试不相加，准备失败不是产品取消失败。[准备记录](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-execution-preparation-001/test-summary.json)、[预检失败](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-preflight-failure-001.json)、[修正后预检](../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-execution-preparation-002/root-preflight.json)
