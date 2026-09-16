# 官方模型准备入口的运行边界说明

当前固定公司签名候选为 036，已包含本页源码修复；官方准备与本地模型检查的原生权限告知获得有限接受。没有执行官方下载、确认导入或模型计算，完整 M2 和发行状态不提高。下方源码阶段记录保留当时状态，最新结果见末节。

本轮修复官方模型准备页缺少运行权限说明、登记模型遗漏相同字段的问题。源码与相关测试已通过；固定公司签名 App 仍为 035，未重新构建，不包含本轮修复。完整 M2、原生验收及发行状态不提高。[此前手工导入边界](2026-09-16-model-import-trust-boundary.md)

## 行为与兼容边界

官方目录增加通用 `execution_boundary`，保留 `loader=safetensors` 的下载格式含义；新模型登记从文件复核后实际 `model_manifest` 报告保存相同字段，不把目录声明冒充已检查或已运行。已有模型与历史幂等回执不补写、不迁移。[设计审查](../../.artifacts/official-model-boundary-next-v1/design-review.md)

共享 `ModelExecutionNotice` 复用手工导入的七字段识别与说明：固定加载器、不支持自定义代码、独立同用户进程而非 OS 沙箱；离线加载选项不等于网络阻断，凭证环境白名单不等于禁止读取凭证文件。官方页缺失或未知字段显示无法确认的提示，不新增下载、停止、续传、登记或交给试用草稿的门禁；手工导入原确认门禁保持，建立试用草稿不会自动运行。[独立审查](../../.artifacts/official-model-boundary-next-v1/independent-review.md)

## 验证与限制

后端 2 项精确负例先失败，修复后 67 项相关测试通过，保留 2 项既有依赖警告；前端 4 项新增负例先失败，修复后 27 项相关测试通过，类型检查通过。后端控制 API 使用进程内 TestClient，下载夹具使用真实回环 HTTP 与临时文件／数据库，没有模型执行或原库 SQL。[后端回执](../../.artifacts/official-model-boundary-next-v1/backend/result.json)、[前端回归](../../.artifacts/official-model-boundary-next-v1/frontend/green.log)

组件浏览器验收通过：1280×720 下，真实生产组件与内存 API 响应显示已知说明且只读不写；明确开始后仅 1 次下载创建请求，显示 1024/1024 和登记按钮。未知字段显示无法确认，停止与续传仍可操作；长对话框滚动后登记按钮可见且可用。未连接真实控制服务、模型或 SQL，不代表官方下载或原生 App 验收。[浏览器回执](../../.artifacts/official-model-boundary-next-v1/browser-001/result.json)

保留两项夹具问题：首次临时 Vite 配置重复 React 导致 hook 错误与空白，修正验收配置后通过，产品依赖未改；早期完成记录为 256/1024，修正为 1024/1024 后重验已知说明和开始路径。控制台保留首次 4 项错误／警告，修正后没有新增；未验证移动视口。

## 036 签名包与原生告知验收

以源码提交 `d24338a` 为基线，加构建自动版本更新得到 036；固定 App 的 Global Cybersecurity Alliance Limited 公司签名 7 个目标及根整包／冻结来源核对通过。本轮单次原生启动，在独立空库创建项目 `036运行权限告知验收`。[根验包](../../.artifacts/integration-ver2-4-036-v1/root-frozen-check.json)

官方目录、9 文件清单与完整权限告知可见，没有点击下载。本地 12 文件的 4-bit 模型经真实目录面板选择并检查，界面显示 `受限权重 · 本机 MLX 加载器` 及权限语义说明；关闭窗口，没有确认导入。停机只有 1 项目与 1 导入计划、0 命令／事件、0 模型／下载／任务／运行，停机计划中的 `trust_class=restricted_weights`、`loader=mlx_lm.local_restricted` 和七字段正确；没有模型计算或导入文件复制。[原生根读回](../../.artifacts/official-model-boundary-next-v1/native-run-001/root-readback.json)

App 正常退出 0；守卫恢复原 selector 对象、释放锁并退出 0。原保护 44 项严格不变，selector 仅 ctime 例外，2 份启动记录保留；035 原生库的 35 文件／20 目录及 12 个模型源文件保持。一次旧界面元素编号失效已保留，没有副作用。本次只接受告知与检查计划，不代表真实官方下载登记、网络隔离、完整 M2 或发行通过。
