<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md) · [繁體中文](2026-09-16-ver2-4-030-connection-isolation.md) · [English](../../../en/docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md)
<!-- translation-navigation:end -->

<a id="ver24030工作库连接隔离e138"></a>

# Ver2.4（030）工作庫連線隔離：E138

目前固定路徑公司簽章候選為 Ver2.4（030）。原始碼測試、唯一建置、根整包複核和包內兩項真實控制服務測試已完成；原生完整備份、目標庫啟動失敗復原、成功切庫、分別儲存專案及同號重新開啟的有限子集已獲根接受，正常退出、停機讀回與原庫選擇恢復通過。029／E137 與更早歷史保留，不提高完整 AC 或 M0—M6 狀態。

<a id="修复范围与源码验证"></a>

## 修復範圍與原始碼驗證

一般 API 請求及媒體讀取在呼叫時綁定非憑證連線身分。宿主在傳送前和完成後複核該身分；切庫、復原或重新啟動會拒絕舊請求和延遲回應，寫入不會自動使用新庫身分重送。同一連線的啟動通知保留有效讀取，真正重新連線則使舊環境檢查失效，等待宿主操作完成後再讀取狀態。

574 項前端測試、52 項一般宿主測試及型別檢查通過。宿主臨時 HTTP 服務驗證舊庫請求沒有到達新庫；對應紅例和初始化通知競態的修前失敗保留。一般宿主測試中的 3 項現場測試未被計作通過，後續另執行其中兩項，結果見下節。[前端迴歸](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/frontend-tests-001/regression-delivery.log)、[宿主測試目錄](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/rust-tests-001)

原生檔案、目錄及 Python 環境選擇器等待期間跨庫的非同步競態未涵蓋；本次不能解釋為所有非同步命令已隔離。沒有新增模型能力或訓練預算。

<a id="唯一构建与签名复核"></a>

## 唯一建置與簽章複核

建置前可用容量 109.523 GiB，高於原 40 GiB 門檻；保留 029 歸檔，沒有清理或降低門檻。唯一正式建置耗時 529.041263 秒、結束碼 0，自動更新四個版本檔案。根複核對應提交 `8cb19da3e2f99a4a433d70e8d139cf8f800c3336`，615 項追蹤輸入、161 項生產來源、211 項凍結檔案及 91 項應用輸入一致。[建置回執](../../../../.artifacts/integration-ver2-4-030-v1/build-process-final.json)、[根整包複核](../../../../.artifacts/integration-ver2-4-030-v1/root-frozen-check.json)

整包包含 21966 個一般檔案、48 個符號連結和 4003 個目錄。7 個目標均由 Global Cybersecurity Alliance Limited 簽章，團隊 `R3JK7R29AC`，憑證 SHA1 為 `7C33B517942161311A087CE893D2F1CE9B204B44`。建置階段 47 項保護記錄保持，029 歸檔整包保持；該階段未啟動 App、未連接業務 SQL，也未追加模型探測。[簽章報告](../../../../.artifacts/integration-ver2-4-030-v1/bundle-verification.json)、[凍結來源](../../../../.artifacts/integration-ver2-4-030-v1/source-build-manifest.json)

建置後以目前包內控制服務真實執行重新啟動驗證與遷移失敗復原兩項測試：2 通過、0 失敗。測試使用臨時庫，不表示原生介面已經重現遷移失敗；鑰匙圈現場測試仍未執行。12 項版本同步測試通過。[真實控制測試](../../../../.artifacts/integration-ver2-4-030-v1/real-control-tests.stdout.log)、[版本測試](../../../../.artifacts/integration-ver2-4-030-v1/version-tests.log)

<a id="原生有限接受与停机读回"></a>

## 原生有限接受與停機讀回

生產介面在本次新建的測試庫 A 完成完整備份，顯示 1 個檔案、56.0 KB；還原到新目錄 B 後顯示檔案已校驗。測試鎖占用 B，使目標控制服務啟動失敗；介面原文為 `服务启动响应格式无效。 已恢复连接原工作库。`，A 控制程序由 32356 變為 51024，隨後成功儲存 A 的新專案。[備份介面](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/02-A-backup.txt)、[還原校驗](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/03-B-restored.txt)、[失敗復原介面](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/04-switch-failed-rollback.txt)、[失敗後讀回](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/failed-switch-readback.json)

釋放 B 鎖後，同一 App 成功切入 B，控制程序為 51729；B 起初僅有共同專案，沒有 A 復原後新建的專案，並成功儲存 B 的新專案。第二次從同一固定路徑啟動同號 App，App／控制程序為 52923／52928，B 新專案仍在。兩次均正常退出，結束碼均為 0。[切入 B](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/B-connected.json)、[B 儲存後介面](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/07-B-saved-after-navigation.txt)、[重新開啟程序](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/B-reopened-processes.json)、[重新開啟專案選單](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/ui/09-B-reopened-project-menu.txt)、[首次退出](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/launch-001/exit.json)、[再次退出](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/launch-002/exit.json)

停機讀回確認 A／B 保留同一編號的共同專案，各自新增專案只在本庫；B 重新開啟前後全部資料表內容及資料庫摘要相同，資源／事件／命令數均為 0。44 項既有保護記錄（含不存在項及重複路徑）的摘要與中繼資料不變，原選擇檔案位元組、inode 和模式恢復；重新命名造成的 ctime 變化明確保留。App、控制服務、恢復保護守衛及 B 測試鎖程序均已停止。[根停機讀回](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/root-readback.json)

現場續接發現原保護守衛 32132 已退出，App 仍執行於本次測試庫，原選擇檔案保留；後來重新取得原庫保護鎖，恢復守衛 41356 與 B 鎖程序 50865 已正常收尾。中斷原因及精確時長未知，檔案讀回保持不能證明保護鎖全程連續；此事件不被後續通過覆蓋。[守衛恢復記錄](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/selector-guard/guard-recovery.json)、[恢復時保護讀回](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/selector-guard/recovery-readback.json)

獨審及根回執接受上述有限子集，同時保留採集缺口：06 的選單未展開，不能獨立證明 B 新建前完整專案清單；09 只有展開選單 AX 文字，沒有對應截圖。A 新建後的獨立截圖與退出確認截圖未儲存，A 寫入由停機快照及復原程序記錄支持，兩次正常退出由退出回執支持；這些證據不能獨立還原每次點擊或退出框視覺內容。介面錯誤文案泛化，目錄被占用的具體原因來自底層日誌，不能寫成介面直接顯示該原因。[原生獨審](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/independent-readback-review.md)、[根有限接受](../../../../.artifacts/host-connection-scope-ver2-4-next-v1/native-run-001/root-native-acceptance.json)

本次原生證據是目標庫因鎖占用而啟動失敗後的復原，不是原生遷移失敗驗收，也未在現場確定性重現排隊舊 IPC 競態。遷移失敗復原有前述包內真實控制測試，舊請求隔離有宿主 HTTP 測試；兩者與本次原生介面證據分別記錄。

<a id="保留的验收边界"></a>

## 保留的驗收邊界

原生選擇器非同步競態、指定 NVIDIA Linux 裝置與跨主機回傳、媒體人工品質、乾淨安裝、五名首次使用者、公證及正式分發仍未完成。既有品質失敗、預算、020 長清單空白及效能證據缺口不因本次簽章或測試通過而關閉。[目前交付矩陣](2026-09-10-current-delivery-matrix.md)

本頁的 `.artifacts` 連結僅指本機證據，不隨 GitHub 原始碼發布；原始碼、文件、簽章建置、原生局部驗收與正式發布分別記錄。
