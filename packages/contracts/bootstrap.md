# 第一批集成合同

此文件是第一批开发集成约定，完整语义以 docs/05、07 为准。实现偏差必须汇报总负责人并同步调用端。

## 控制服务

Python 包 `ailab_control` 位于 `services/control`。开发启动：`python -m ailab_control --data-dir DIR --port 0`。绑定 127.0.0.1，生成随机会话 Bearer token，启动成功后 stdout 首行输出 JSON `{"port":12345,"token":"...","pid":123}`；日志全部 stderr。可选 `--token-file PATH` 只用于本机开发桥接，文件权限 0600。禁止日志暴露 token。

所有业务接口在 `/api/v1`，均校验 Bearer token；无认证健康检查只暴露服务存活，不返回目录／token。Tauri 宿主使用 Rust HTTP 代理，不把 token 返回前端。开发模式 Vite 只绑定回环，从 token 文件读取认证并代理到已核实本机控制端。

前端调用统一返回 `Promise<T>`，响应对象为资源原本 JSON；集合采用 `{"items":[]}`，错误 `{"error":{"code":"...","message":"中文","details":{}}}`。创建与编辑返回完整对象；ID 为服务端生成。

优先接口：GET/POST /projects；GET /models；POST /models/import-plans、/models/imports；GET /datasets；POST /datasets/import-plans、/datasets/imports；GET /devices；GET /capabilities；POST /tasks；GET /tasks?project_id=；PATCH /tasks/{id}/draft；POST /tasks/{id}/preflight；POST /tasks/{id}/attempts；GET /attempts/{id}；GET /attempts/{id}/events（分页 JSON 或 SSE 明确参数）；POST /attempts/{id}/cancel；GET /works?project_id=。其它接口按实际交付扩展，不返回伪造成功。

草稿至少：kind=text/image/video/audio，operation=generate/train，model_id，dataset_id 可空，input={prompt,...}，runtime={engine,device_id,max_tokens,temperature,top_p,seed,...}。第一次实现只开放已接入真实能力，其它类别保留入口与具体准备说明。创建任务输入含 project_id、kind、operation、name；编辑含 draft 与 expected_revision。提交含 preflight_id、expected_revision 与 Idempotency-Key 请求头。

## 执行器

独立 Python 进程通过输入快照文件和输出目录运行：`python workers/mlx_worker.py --snapshot FILE --output-dir DIR`。stdout 为逐行 JSON 事件：phase、token、metric、completed、error。completed 带 artifacts（path、sha256、media_type）及 effective_config；引擎日志 stderr。快照含 attempt_id、operation、model_path、input、runtime；训练额外 dataset_path。工作进程不修改控制数据库，SIGTERM 请求取消，控制器等待真实退出后确认停止。

本地 MLX 环境使用显式绝对 Python 路径配置，和控制服务环境分开。运行命令参数数组，禁止 shell 拼接。没有执行器或模型时提交前检查阻断。
