# 官方模型准备入口的运行边界说明

本轮修复官方模型准备页缺少运行权限说明、登记模型遗漏相同字段的问题。源码与相关测试已通过；固定公司签名 App 仍为 035，未重新构建，不包含本轮修复。完整 M2、原生验收及发行状态不提高。[此前手工导入边界](2026-09-16-model-import-trust-boundary.md)

## 行为与兼容边界

官方目录增加通用 `execution_boundary`，保留 `loader=safetensors` 的下载格式含义；新模型登记从文件复核后实际 `model_manifest` 报告保存相同字段，不把目录声明冒充已检查或已运行。已有模型与历史幂等回执不补写、不迁移。[设计审查](../../.artifacts/official-model-boundary-next-v1/design-review.md)

共享 `ModelExecutionNotice` 复用手工导入的七字段识别与说明：固定加载器、不支持自定义代码、独立同用户进程而非 OS 沙箱；离线加载选项不等于网络阻断，凭证环境白名单不等于禁止读取凭证文件。官方页缺失或未知字段显示无法确认的提示，不新增下载、停止、续传、登记或交给试用草稿的门禁；手工导入原确认门禁保持，建立试用草稿不会自动运行。[独立审查](../../.artifacts/official-model-boundary-next-v1/independent-review.md)

## 验证与限制

后端 2 项精确负例先失败，修复后 67 项相关测试通过，保留 2 项既有依赖警告；前端 4 项新增负例先失败，修复后 27 项相关测试通过，类型检查通过。后端控制 API 使用进程内 TestClient，下载夹具使用真实回环 HTTP 与临时文件／数据库，没有模型执行或原库 SQL。[后端回执](../../.artifacts/official-model-boundary-next-v1/backend/result.json)、[前端回归](../../.artifacts/official-model-boundary-next-v1/frontend/green.log)

组件浏览器验收通过：1280×720 下，真实生产组件与内存 API 响应显示已知说明且只读不写；明确开始后仅 1 次下载创建请求，显示 1024/1024 和登记按钮。未知字段显示无法确认，停止与续传仍可操作；长对话框滚动后登记按钮可见且可用。未连接真实控制服务、模型或 SQL，不代表官方下载或原生 App 验收。[浏览器回执](../../.artifacts/official-model-boundary-next-v1/browser-001/result.json)

保留两项夹具问题：首次临时 Vite 配置重复 React 导致 hook 错误与空白，修正验收配置后通过，产品依赖未改；早期完成记录为 256/1024，修正为 1024/1024 后重验已知说明和开始路径。控制台保留首次 4 项错误／警告，修正后没有新增；未验证移动视口。
