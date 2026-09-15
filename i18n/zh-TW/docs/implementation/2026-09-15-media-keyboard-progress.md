<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-15-media-keyboard-progress.md) · [繁體中文](2026-09-15-media-keyboard-progress.md) · [English](../../../en/docs/implementation/2026-09-15-media-keyboard-progress.md)
<!-- translation-navigation:end -->

<a id="media-三入口键盘进度e136"></a>

# Media 三入口鍵盤進度：E136

當前固定公司簽名候選仍為 Ver2.4（028）。Media 三個導入入口的源碼修復、56 項相關前端測試及真實 Safari 鍵盤子集已接受，獨審已由根關閉；029 尚未歸檔、打包或原生驗證。容量低於原 40 GiB 門檻，緩存清理仍待用戶確認，沒有執行刪除。028 的既有接受保留，完整 AC 和 M0—M6 不提高。[028 歷史進度](2026-09-15-ver2-4-028-workbench-keyboard-progress.md)

<a id="e136三处属性相关测试与独审"></a>

## E136：三處屬性、相關測試與獨審

相對凍結的 160 項生產來源，僅 `apps/desktop/src/Media.tsx` 改變：為“導入模型”“導入圖片數據”“導入圖片素材”三個原生 button 增加 `tabIndex={0}`。嚴格移除這三處屬性後，整文件逐字節恢復為 028 修前版本；其餘 159 項來源保持。按鈕類型、導入回調、篩選、分支及真實 Workbench fieldset 禁用邏輯未變。[源碼根接受](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-source-acceptance.json)

正式紅例為 8 項中 7 通過、1 失敗，該失敗包含三個入口缺少屬性的斷言；首次 JSDOM 未提供 showModal 的 setup 失敗原件保留。修後新測試保持正式紅例字節，7 文件共 56 項通過，含新增 8 項；類型檢查 exit 0，另有 3 項夾具測試通過，不與 028 的 59 項累加。新增測試驗證四種只讀／禁用狀態下普通點擊不導入、正確導入類型、原稿保持及關閉回焦；單元測試的點擊和模擬 cancel 不代替真實 Safari Enter／Escape。[紅例記錄](../../../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/result.json)、[綠色回執](../../../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/green-result.json)、[測試範圍](../../../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/green-REVIEW.md)

獨審實際查看兩組 12 張關鍵修後截圖，並核對源碼、事件、AX 及 132 項哈希清單；根隨後復核並關閉獨審待辦。源碼接受原件中的 pending=true 保留形成時含義，不是當前仍待獨審，也未改寫原件。[獨立復審](../../../../.artifacts/media-keyboard-ver2-4-next-v1/browser-review-002/review.md)、[獨審根關閉](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-review-closure.json)

<a id="safari-开发组件前后对照"></a>

## Safari 開發組件前後對照

固定回環端口 4328 的頁面直接導入真實 MediaFields 與 ImportDialog，使用圖片訓練和視頻運行兩個空資源分支；沒有控制服務代理或請求回退。觀察器只記錄普通按鍵與焦點，不接管 Tab，不主動聚焦；產品 Dialog 自身保留彈窗與回焦邏輯。Safari 的 AppleKeyboardUIMode 保持 0，未改變系統鍵盤設置。[夾具準備](../../../../.artifacts/media-keyboard-ver2-4-next-v1/browser-preparation.json)

修前兩組共 26 文件，每組 2 次 Tab、2 次 Shift-Tab，啓用的三個源碼入口被跳過；兩組原始記錄與哈希保持。修後重新加載頁面，兩組各 29 文件、38 事件，各有 4 次 Tab、4 次 Shift-Tab、2 次 Enter、2 次 Escape。正反方向均可達兩個入口；圖片訓練打開模型／圖片數據彈窗，視頻運行打開模型／圖片素材彈窗，四次關閉後都回到各自入口，焦點框可見。請求、錯誤、輸入／更改事件及丟棄計數均為 0，沒有文件導入、保存或模型運行。[修前簽收](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-before-acceptance.json)、[修後簽收](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-after-acceptance.json)

開始導航時 typeText 丟失 URL 標點而進入搜索頁，粘貼曾報超時；確認正確本機地址後才進入夾具。該前置導航問題保留，不計入夾具零 API 請求範圍。末兩份 AX 未單列 focused 行，最終回到開始錨點由 focusin 與 report.active 證明；不把 AX 缺行寫成無焦點。專用 Safari 窗口已關閉，夾具服務已停止，4328 無監聽。[修後與停止回執](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-after-acceptance.json)

<a id="029-仍待容量打包与原生验证"></a>

## 029 仍待容量、打包與原生驗證

當前 App 仍使用固定 028 公司簽名包；此次沒有更新版本或構建新包。029 繼續沿用同一路徑及既有歸檔、保護和構建門檻，不能把源碼與 Safari 通過寫成 029 包或原生通過。[整合準備](../../../../.artifacts/media-keyboard-ver2-4-next-v1/integration-preparation-001/plan.md)

容量只讀記錄在 9 月 15 日北京時間 07:06:10 為 34.084 GiB，低於原 40 GiB 門檻；該數字屬於當時觀測，執行前仍需重新測量。唯一擬提請確認的範圍是本項目 `apps/desktop/src-tauri/target/debug` 調試／測試緩存，目錄記賬約 8.190 GiB；這是建議，未獲清理確認，也未刪除。APFS 共享塊與快照可能影響實際釋放量，不能把記賬量算成已可用空間，更不能降低門檻。固定 028 App、release、歷史歸檔、工作庫、模型和證據均不在該建議範圍。[容量與清理建議](../../../../.artifacts/media-keyboard-ver2-4-next-v1/integration-preparation-001/capacity-options.md)

本次不新增模型能力，不簽真實文件導入、簽名 App 的 Media 路徑、完整鍵盤、完整 AC 或 M0—M6。指定 NVIDIA、跨端同份產物、乾淨安裝／公證發佈、五名首次用戶、舊質量失敗及已用預算、舊 020 空白和初顯／完整就緒歷史缺口保持。[當前交付矩陣](2026-09-10-current-delivery-matrix.md)

<a id="原生脚本准备已完成尚未启动"></a>

## 原生腳本準備：已完成，尚未啓動

監督器、停機讀回和數據比較腳本已準備並接受獨立審查。監督器 10 項、讀回 13 項、比較器 12 項合成測試全部通過；正式 Python 3.13 環境也通過這 35 項，其中讀回／比較的兼容性復跑不重復計數。讀回首次有一個負例沒有實際改變輸入，修正測試後通過，原失敗日誌和回執保留，讀回規則未放寬。兩份獨審均未發現阻斷項；繼承的進程退出邏輯只作靜態復核，本輪未重新啓動真實 App。[腳本根接受](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-native-preparation-acceptance.json)、[監督器獨審](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/supervisor-review.md)、[讀回與比較獨審](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/reader-review.md)

後續原生範圍限定為兩個既有任務中的四個入口實例，只用 Enter 打開、Escape 關閉並檢查回焦。比較腳本要求完整業務數據保持，僅允許四個頁面選擇設置葉子變化；這些是待執行標準，尚無真實讀回結果。當前沒有建立運行綁定、連接工作庫或啓動 029 App，缺少正式 029 包及同次界面／退出證據時腳本拒絕繼續。[任務範圍](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/task-scope.json)、[監督器腳本接受](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/root-supervisor-review.json)

9 月 15 日北京時間 07:49:30 的最終只讀核對確認：160 項生產來源、029 五份構建準備輸入以及固定 028 包七個錨點保持，29 個指定真實執行輸出均不存在。該時刻磁盤可用約 28.86 GiB，仍低於 40 GiB；即使把此前 debug 目錄約 8.19 GiB 的記賬量全部計入，也不足 40 GiB，實際執行前必須重新確認容量。原清理確認尚未收到，未清理或擴大範圍，當前版本仍為 028。[狀態記錄](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/final-state-001.json)
