<a id="ver24035运行边界验收e146"></a>

# Ver2.4（035）執行邊界驗收（E146）

固定 035 包內執行器的單次進程網路拒絕推理已獲有限接受；未開放媒體與快取請求的拒絕測試已發布於 `b96514c`。本輪不重新建置 App，不提高 M2、完整 AC 或發布狀態；原生操作與重開證據仍見 [E145](2026-09-16-ver2-4-035-native-inference.md)。包內控制服務的真實取消與恢復也已通過下述有限子集。

<a id="进程网络拒绝下的真实生成"></a>

## 進程網路拒絕下的真實生成

普通對照 PID 36199 對新建 IPv4／IPv6 回環端點連線成功；PID 36200 對同端點在 connect 階段收到 `EPERM`，隨後同 PID exec 進入固定包內 worker。一次真實生成正常退出，正文 `7`，6 份產物、0 個 token 增量事件；24 層 KV 初始為空且無跨請求重用。設定保持提示 50／輸出預留 78／上下文 128、auto KV、prefill 512、停止序列 `39` 和 `stream=false`。[執行回執](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/result.json)、[原始輸出](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/worker.stdout.jsonl)

47 項原保護記錄、12 個模型來源檔案、31 個原生檔案及原生資料庫摘要前後保持；執行器與對照進程已退出，監聽器關閉。沒有啟動 App UI、連接 SQL 或改變系統網路設定。[根接受](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/root-acceptance.json)、[獨立讀回](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-independent-result.md)

準備階段補齊所屬進程清理與自然退出競態處理，並收緊精確產物、設定及快取核對；早期探針補充操作欄位以區分 socket 建立和 connect 拒絕，原記錄保留。執行準備的 8 項合成測試及獨審重複驗證不相加；此前零模型探針的 8 項測試屬於另一層，不能當作真實故障注入。[準備審查](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-execution-preparation-001/independent-review.md)、[早期探針記錄](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-preparation-001/REVIEW.md)

此處採用驗收專用進程網路拒絕策略，實測範圍是 IPv4／IPv6 回環 TCP connect；沒有逐一探測 DNS、UDP 或外網，不代表實體斷網，也不是產品預設 OS 沙箱。同使用者檔案讀取權限仍在；單個短輸入不涵蓋完整離線工作流程。

<a id="未开放媒体与缓存请求"></a>

## 未開放媒體與快取請求

保持文字不變，替換媒體身分、交換媒體順序、改變處理器修訂或預處理尺寸，並請求前綴／媒體快取重用。生產 MLX 校驗、預檢與執行入口在載入或計算前拒絕；控制服務草稿更新回傳 422，舊草稿預檢失敗後提交回傳 409，沒有新執行或產物。本輪未發現這些輸入位置靜默忽略，也沒有修改生產程式碼或實作快取重用。[入口合同與測試](../../../../.artifacts/m2-cache-contract-ver2-4-035-v1/review.md)、[獨立審查](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cache-contract-independent-review.md)

控制測試的 TestClient 是進程內請求；舊草稿使用正式預檢函式替代子進程派發，不代表實際網路或原生介面驗收。

新增拒絕矩陣 50 項通過；相關 MLX 回歸 139 項、控制回歸 50 項通過，包含重複涵蓋，不相加。新增負例使用暫存檔案／資料庫和計數拒絕樁，模型載入、計算及快取建立為零；既有正例的 CPU 快取陣列和夾具生成器不是語言模型實算。這些證據不證明媒體快取命中、失效或效能。[測試摘要](../../../../.artifacts/m2-cache-contract-ver2-4-035-v1/result.json)

<a id="真实取消与恢复"></a>

## 真實取消與恢復

在 sequence 8 階段訊息 `提示词已处理，正在生成` 之後，透過正式回環 HTTP 向固定包內控制服務 PID 37558 提交一次正常取消。worker PID 37568 退出 130，產生 `CANCELLED` 警告；狀態、計算結果和收集狀態均為 `cancelled`，停止已確認，原因 `USER_CANCELLED`，沒有成功產物或作品。該進程組消失後，恢復 worker PID 37583 正常退出並生成正文 `7`、24 層新空 KV 和 6 份產物。[實際執行](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-run-001/result.json)

本輪共 2 次 attempt、1 次取消、0 訓練、0 自動重試。 停機唯讀新庫核對 4 條命令、25 條事件、6 份登記產物、0 作品，持久化與 API 一致，讀回未改變資料庫位元組。控制服務正常退出，沒有強制清理訊號；相關進程及組均已消失，原保護保持。這證明停止後新進程可再次分配並生成，不證明舊 GPU 記憶體逐位元組歸零，也不是本輪 App UI 驗收。[根接受](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-run-001/root-cancel-acceptance.json)、[獨立讀回](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-independent-result.md)

準備歷史保留：早期腳本收口的 SyntaxError 修復後 44 項測試通過；首次根預檢把既有閒置遠端協定服務 PID 30114 誤判為本地控制服務，在新服務或模型啟動前拒絕。改為精確模組匹配後 50 項純測試通過，175 項來源、47 項保護與 12 個模型來源預檢通過；舊服務未停止。階段測試不相加，準備失敗不是產品取消失敗。[準備記錄](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-execution-preparation-001/test-summary.json)、[預檢失敗](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-preflight-failure-001.json)、[修正後預檢](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-execution-preparation-002/root-preflight.json)
