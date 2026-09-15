<!-- translation-navigation:start -->
[简体中文](../../../../packages/contracts/bootstrap.md) · [繁體中文](bootstrap.md) · [English](../../../en/packages/contracts/bootstrap.md)
<!-- translation-navigation:end -->

<a id="第一批集成合同"></a>

# 第一批集成合同

此文件是第一批開發集成約定，完整語義以 docs/05、07 為準。實現偏差必須彙報總負責人並同步調用端。

<a id="控制服务"></a>

## 控制服務

Python 包 `ailab_control` 位於 `services/control`。開發啓動：`python -m ailab_control --data-dir DIR --port 0`。綁定 127.0.0.1，生成隨機會話 Bearer token，啓動成功後 stdout 首行輸出 JSON `{"port":12345,"token":"...","pid":123}`；日誌全部 stderr。可選 `--token-file PATH` 只用於本機開發橋接，文件權限 0600。禁止日誌暴露 token。

所有業務接口在 `/api/v1`，均校驗 Bearer token；無認證健康檢查只暴露服務存活，不返回目錄／token。Tauri 宿主使用 Rust HTTP 代理，不把 token 返回前端。開發模式 Vite 只綁定回環，從 token 文件讀取認證並代理到已覈實本機控制端。

前端調用統一返回 `Promise<T>`，響應對象為資源原本 JSON；集合採用 `{"items":[]}`，錯誤 `{"error":{"code":"...","message":"中文","details":{}}}`。創建與編輯返回完整對象；ID 為服務端生成。

優先接口：GET/POST /projects；GET /models；POST /models/import-plans、/models/imports；GET /datasets；POST /datasets/import-plans、/datasets/imports；GET /devices；GET /capabilities；POST /tasks；GET /tasks?project_id=；PATCH /tasks/{id}/draft；POST /tasks/{id}/preflight；POST /tasks/{id}/attempts；GET /attempts/{id}；GET /attempts/{id}/events（分頁 JSON 或 SSE 明確參數）；POST /attempts/{id}/cancel；GET /works?project_id=。其它接口按實際交付擴展，不返回偽造成功。

草稿至少：kind=text/image/video/audio，operation=generate/train，model_id，dataset_id 可空，input={prompt,...}，runtime={engine,device_id,max_tokens,temperature,top_p,seed,...}。第一次實現只開放已接入真實能力，其它類別保留入口與具體準備說明。創建任務輸入含 project_id、kind、operation、name；編輯含 draft 與 expected_revision。提交含 preflight_id、expected_revision 與 Idempotency-Key 請求頭。

<a id="执行器"></a>

## 執行器

獨立 Python 進程通過輸入快照文件和輸出目錄運行：`python workers/mlx_worker.py --snapshot FILE --output-dir DIR`。stdout 為逐行 JSON 事件：phase、token、metric、completed、error。completed 帶 artifacts（path、sha256、media_type）及 effective_config；引擎日誌 stderr。快照含 attempt_id、operation、model_path、input、runtime；訓練額外 dataset_path。工作進程不修改控制數據庫，SIGTERM 請求取消，控制器等待真實退出後確認停止。

本地 MLX 環境使用顯式絕對 Python 路徑配置，和控制服務環境分開。運行命令參數數組，禁止 shell 拼接。沒有執行器或模型時提交前檢查阻斷。
