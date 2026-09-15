<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md) · [繁體中文](2026-09-16-ver2-4-032-diagnostic-directory-regression.md) · [English](../../../en/docs/implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md)
<!-- translation-navigation:end -->

<a id="ver24032诊断目录原生回归e141"></a>

# Ver2.4（032）診斷目錄原生迴歸：E141

固定 032 公司簽章 App 的診斷目錄完整流程已獲根接受：三語資料匯入、目錄取消與整次診斷取消、中文空格目錄儲存、ZIP 完整性與脫敏、同庫重新開啟及原資料恢復通過。本輪為選擇器改動後的迴歸，不是首次診斷成功；E61、E88、E120、E122 歷史成功及 E140 Python 路徑記錄保持原文。診斷 ZIP 不替代完整產物匯出 AC27，也不提高完整 AC22、M0—M6 或發布狀態。

<a id="固定候选与分层验证"></a>

## 固定候選與分層驗證

本輪原始碼基線為提交 `2d4d07745745e4221557a47addfa4055bb466925`，沒有重新建置或變更版本。實際固定包仍為 Ver2.4（032），複核 21966 檔案、48 連結、4003 目錄及 7 個 Global Cybersecurity Alliance Limited 公司簽章目標通過。[套件複查](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/root-preflight.json)

95 項控制測試、14 項前端測試通過；控制測試保留 2 項警告。準備腳本 19 項合成測試與啟動門檻 25 項合成測試分別通過，只驗證各自合同，不替代真實 UI。準備驗收器已收緊非頁面設定預設值；啟動測試首次因中間版本新增階段欄位而失敗，修正測試樣本後通過，未改生產或降低門檻。[相關測試](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/focused-tests.json)、[準備驗證](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-preparation-001/preparation-check.json)、[啟動門檻](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/launcher-review-001/gate-tests.json)

<a id="真实导入取消与保存"></a>

## 真實匯入、取消與儲存

僅使用新 A 獨立庫，真實選擇並匯入簡體、繁體、英文共 3 條 SFT 樣本、650 位元組。停機資源恰為 1 個 ready 資料集和 1 個匯入計畫；來源檔案、實際副本和資源摘要一致。02 初次在父目錄輸入檔名誤選 seed，未開啟；改用完整路徑後 02b 精確選中，實際只匯入一次。[正確選擇](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/02b-dataset-selected-correct.ax.txt)、[匯入結果](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/04-dataset-imported.ax.txt)

第一個診斷預覽 ready 後，取消原生目錄選擇，返回仍為 ready，目標目錄為空，沒有成功提示；再明確取消整次診斷，記錄變為 cancelled。重新選擇範圍並產生第二個預覽後，實際選擇 `診斷 輸出` 目錄並確認儲存，UI 顯示“诊断 ZIP 已保存，文件完整性已核对。”兩種取消不是同一動作，不能以目錄為空替代取消狀態證據。[目錄取消後](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/07-directory-cancelled-ready.ax.txt)、[整次取消](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/08-preview-one-cancelled.ax.txt)、[目錄確認](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/11-output-directory-confirmed.ax.txt)、[儲存及完整性](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/12-diagnostic-saved.ax.txt)

輸出目錄恰有 9316 位元組 ZIP，包含 `diagnostics.json` 和 `manifest.json` 兩個成員，CRC、整體及成員摘要／大小、清單 complete 和應用版本全部吻合。解碼內容中不含三語訓練原文、測試敏感標記、專案名／ID、資料檔名或個人絕對路徑；整體 SHA 為 `d57e4eb0eb26089f5e15c8ec9f88712194b68c6be3225ce91f101a8471ec73ba`。[首次停機檢查](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/exported-check.json)

<a id="重开保护恢复与边界"></a>

## 重新開啟、保護恢復與邊界

同一固定 App、同一 A 兩次正常退出均為 0。重新開啟直接恢復原資料頁，專案與 3 條樣本可見；停機全部資料庫表、原始資料庫位元組和 ZIP 位元組前後嚴格相同。命令恰為 5 項：1 次匯入、2 個診斷預覽（取消／成功各一）、1 次診斷取消、1 次匯出；資源 2 項、執行事件 0 項。診斷 UI 沒有歷史入口，原診斷登記由停機全表與原 ZIP 證明，不聲稱重開介面讀取歷史回執。[重開資料頁](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/15-second-restored-dataset.ax.txt)、[重開後檢查](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/reopened-check.json)、[兩次退出與根讀回](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-readback.json)

原 selector 位元組、inode 與權限恢復，ctime 差異保留；47 項保護記錄中 44 項嚴格不變，包含缺席項和重複路徑，兩份 startup 日誌允許本輪更新。App、控制與守衛均已停止，恢復及釋放回執齊全，不承諾守衛永不中斷。[恢復](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/selector-guard/restored.json)、[釋放](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/selector-guard/released.json)、[根接受](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

診斷記錄包含 3 項 probe 觀察與 8 項 environment 觀察；App 工作階段自動探測實際發生，不能稱零探測，但沒有新增模型任務。原生儲存 17 組 AX 與圖像、34 個檔案；16 第二次退出圖像異常縮小，保留原 AX 與退出 0。目錄面板欄位截圖未顯示末級列，路徑由頂部 Where、完整 AX 與傳回確認共同核對，不誇稱該截圖單獨顯示末級目錄。[根限制記錄](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-readback.json)

獨立原生審查通過本輪診斷目錄迴歸，保留截圖及能力範圍限制。 [獨立審查](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/independent-native-review.md)

本輪診斷成功不關閉其他產物匯出 AC27、乾淨安裝和完整 AC22、指定 NVIDIA 同份 LoRA 回程、品質准入、媒體人工評審、原生跨庫競態、公證及完整 M0—M6。E140 Python 路徑有限接受與 031 失敗保持。[Python 進度](2026-09-16-ver2-4-032-python-path-preservation.md)、[交付矩陣](2026-09-10-current-delivery-matrix.md)

本頁 `.artifacts` 連結為本機證據，不隨 GitHub 原始碼上傳。全部正式文件繼續提供簡體、繁體、英文版本。
