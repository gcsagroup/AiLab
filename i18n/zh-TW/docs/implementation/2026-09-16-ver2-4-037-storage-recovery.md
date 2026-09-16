<a id="037-磁盘满拒绝报告恢复与重开"></a>

# 037 磁碟滿拒絕、報告恢復與重開

固定公司簽名候選 Ver2.4（037）完成有限儲存故障驗收：獨立測試卷實際耗盡空間後，原生計畫拒絕匯出；有效計畫形成後再次耗盡空間，執行以磁碟滿失敗；釋放測試佔位後重新檢查並成功匯出，重開仍分別保留失敗與成功。完整 M6、M0—M6 與發行未通過。

<a id="候选与独立测试资料"></a>

## 候選與獨立測試資料

沿用 Global Cybersecurity Alliance Limited 簽名的固定 App，沒有重新構建或修改產品。二進位摘要保持 `59ce9d899488da868af0935f6dcb7f09749623deab250d55eeda7def4f0b2ce0`。[整包回執](../../../../.artifacts/integration-ver2-4-037-v1/root-frozen-check.json)

複用先前 E22 離線凍結檔案副本，透過 037 包內服務的實際 HTTP 恢復到新獨立庫。輸入含 91 個檔案、1868874298 位元組，不是本輪呼叫產品備份介面生成的備份；沒有連接原庫 SQL。恢復庫首次啟動執行正式架構 3→4 遷移，成功回執與遷移備份摘要均已核對，備份全部表內容等於啟動前快照。[恢復回執](../../../../.artifacts/native-storage-ver2-4-037-v1/restore-001/result.json) [停機核驗](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/root-readback.json)

新建 64 MiB HFS+ 磁碟映像，只在核對裝置、卷身分與容量後寫入專用測試佔位檔案。獨立檔案系統容量為 67067904 位元組；實際寫入返回 `ENOSPC / errno 28`，兩次故障現場可用空間均為 0。系統磁碟沒有被填滿。[首次零空間](../../../../.artifacts/native-storage-ver2-4-037-v1/storage-001/fill-tail-001.json) [再次零空間](../../../../.artifacts/native-storage-ver2-4-037-v1/storage-001/fill-002.json)

<a id="原生拒绝恢复与重开"></a>

## 原生拒絕、恢復與重開

透過原生目錄選擇器選中測試卷。首次檢查因空間不足而停用開始匯出，沒有建立匯出執行記錄。釋放佔位並重新選擇同一目錄後，檢查允許匯出；此時再次填滿測試卷，再點擊開始，產生 `DISK_FULL` 失敗。失敗發生在複製前，目標目錄沒有完整包或暫存包。[計畫拒絕畫面](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/01-full-plan-blocked.png) [執行失敗畫面](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/03-ready-then-full-failed.png) [故障檔案現場](../../../../.artifacts/native-storage-ver2-4-037-v1/storage-001/failed-export-filesystem.json)

再次釋放專用佔位檔案，透過重新檢查匯出、檢查範圍、開始匯出完成恢復。成功包包含 11 個內容檔案、60884 位元組，另有完整性清單；其中 7 個 JSON 報告與原封存產物完全一致。全部內容的摘要和大小均通過核對。失敗記錄為 `export-c8757316996843f6842c0199fac95184`，新成功記錄為 `export-7ee97c109d2f4230811d12734096dae1`。[完成畫面](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/04-recovered-export.png) [檔案核對](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/export-after-first.json)

正常退出並重開同一候選與獨立庫，分別開啟原失敗和新成功記錄，狀態及輸出身分保持，隨後再次正常退出。全部業務表和匯出檔案保持；設定僅因返回工作台清空所選任務，資料庫位元組並非完全相同。[重開失敗記錄](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/05-reopen-failed.png) [重開成功記錄](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/06-reopen-success.png)

<a id="核对测试与收尾"></a>

## 核對、測試與收尾

原 52 項資源全部不變，新增 9 項資源後共 61 項，包含 3 個計畫、2 個匯出、2 個任務及2 個匯出執行記錄；共 2 條命令、93 條事件。模型執行與評測新增均為 0，原品質失敗保留，候選登記數為 0。原 E22 庫、先前 5 個驗收庫、12 個模型來源檔案及凍結輸入保持。原選擇檔案已恢復，守衛已釋放鎖，App 與控制程序均已停止。[根核驗回執](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/root-readback.json)

報告全部 12 個檔案（含清單）複製到本輪保留目錄並逐項核對，隨後正常卸載已核實身分的測試映像。保留目錄只是驗收檔案副本，不算新增產品匯出。映像檔案及摘要保留，測試卷已不再掛載。[保留副本回執](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/export-preservation.json) [卸載與完成回執](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/completion.json)

匯出前端 28 項、控制服務 52 項測試通過，控制測試保留 2 項警告；原生啟動守衛 7 項與卷身分輔助測試 3 項通過。[前端日誌](../../../../.artifacts/native-storage-ver2-4-037-v1/frontend-tests-corrected.log) [控制日誌](../../../../.artifacts/native-storage-ver2-4-037-v1/control-tests.log)

準備過程保留失敗證據：建立映像時初次參數無效；首次大塊填充遇到真實空間不足後仍剩 90112 位元組，隨後只補齊尾部至零空間；前端測試首次在錯誤目錄執行。停機核驗初次錯誤假定架構版本不變，核對正式遷移回執及備份後修正驗證器並通過，沒有修改資料庫或執行記錄。[架構假設失敗](../../../../.artifacts/native-storage-ver2-4-037-v1/native-001/readback-initial-schema-assumption.log)

以上原生階段只驗證真實卷滿條件下的計畫阻斷、複製前檢查、釋放空間後的重新匯出及重開持久化。沒有驗證複製途中空間耗盡、系統碟滿、備份失敗、媒體遺失、乾淨安裝、跨裝置、完整遷移回滾或公證發行，也沒有重新執行凍結品質方案。本頁本機證據連結不隨原始碼倉庫上傳。

<a id="后续包内服务复制途中真实卷满"></a>

## 後續：包內服務複製途中真實卷滿

後續使用同一 037 公司簽名 App 內的原控制服務，透過實際 HTTP 完成複製途中故障、釋放空間後的新匯出和服務重啟讀回。沒有修改生產程式碼或重新構建，深層嚴格簽名檢查再次通過；包內服務摘要為 `ee6bc8f2c95937ecb28ca22c22334720aa18387316a26f0271bdc14d6b458f4a`。本階段沒有啟動原生 App 介面。[執行回執](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/result.json)

新獨立庫透過產品匯入介面登記僅供檔案匯出的合成權重夾具，張量負載為 32 MiB；它不是可執行模型，不提供品質或推理證據。測試目標是新的 64 MiB HFS+ 映像；原工作庫不連接 SQL，來源模型檔案、先前驗收庫與原選擇設定均保持。[夾具身分](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/source-fixture.json)

觀察到實際權重檔案已複製 4194304 位元組後，僅向本次自建控制服務傳送 `SIGSTOP`，確認停止狀態。此時來源張量負載為 33554432 位元組，尚無最終包；隨後向該測試卷寫入專用佔位檔案，實際寫入返回 `ENOSPC / errno 28`，可用空間為 0，再用 `SIGCONT` 恢復同一程序。沒有替換產品函式或偽造空間查詢。[故障現場](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/mid-copy-fill.json)

產品隨後返回 `EXPORT_INCOMPLETE` 失敗，已驗證路徑為空，沒有發布最終包或完整清單。部分目錄保留設定檔案與部分權重，共 4194427 位元組。釋放專用佔位後重新檢查，另建成功匯出，包含 4 個內容檔案、33555039 位元組及清單，逐項大小與摘要核對通過；失敗部分檔案未刪除或改變。[失敗記錄](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/failed-export.json) [部分檔案](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/partial-files.json) [成功檔案核驗](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/verified-export-files.json)

服務正常退出並重啟後，原失敗與新成功記錄逐欄位保持；再次正常退出後，資料庫位元組及全部表內容相同。獨立庫有 10 項資源、3 條命令、14 條事件及 2 個僅匯出執行記錄，新增模型執行與評測均為 0。失敗部分目錄和成功包均已保留校驗副本，測試映像正常卸載，兩次服務退出碼均為 0。[根核驗回執](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/root-readback.json) [卸載回執](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/run-001/detach.json)

補強既有匯出回歸測試：原用例在建立實際檔案前直接拋錯，不能證明部分檔案保留。新用例分別在寫入、刷新和同步階段注入空間不足與 I/O 錯誤，共 6 種情況，核對部分內容不發布、恢復匯出、原失敗不變、來源資產不變及重啟後無模型執行。最終匯出測試 57 項通過，保留 2 項既有警告；故障工具邊界測試 7 項通過。[回歸用例](../../../../tests/control/test_delivery.py) [最終測試日誌](../../../../.artifacts/packaged-export-enospc-ver2-4-037-v1/control-tests-final.log)

該後續階段補足包內服務在真實複製途中卷滿時的檔案與狀態證據。它不等於該故障的原生介面驗收、真實模型載入、備份故障、升級後全部物件匯出或完整 M6；沒有修改凍結品質方案、裝置要求或原驗收門檻。

<a id="后续产品备份恢复与原生历史查看"></a>

## 後續：產品備份恢復與原生歷史檢視

沿用同一固定公司簽名 037 App。先以包內控制服務對上一階段合成驗收庫呼叫正式備份介面，再正式檢查並恢復到新獨立庫；本次不是離線檔案副本冒充產品備份。備份包含資料庫及已登記資產，共 4 個檔案、33640669 位元組，另有清單。來源資料庫位元組與業務表不變，來源目錄只新增備份和恢復回執。[正式備份恢復回執](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/restore-001/result.json)

原匯出目錄在庫外，失敗部分包和成功包仍由原故障映像保留，不屬於上述備份檔案。原映像按原路徑唯讀掛載，核對卷身分、全部部分檔案及成功檔案摘要後，才啟動 App 查看歷史；檢視完成後正常卸載，映像摘要不變。[唯讀卷身分](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/mount-001/identity.json) [卸載回執](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/mount-001/detach.json)

原生工作台分別開啟原失敗與成功記錄。失敗頁顯示執行失敗、檢查儲存後重新準備的提示及重新檢查入口；成功頁顯示全部檔案已寫入並通過校驗、原儲存路徑及相同記錄編號。關閉對話框並正常退出，再次啟動同一 App 與恢復庫，兩份記錄仍分別保持失敗與成功。[首次失敗畫面](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/native-001/01-failed.jpg) [首次成功畫面](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/native-001/02-success.jpg) [重開失敗畫面](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/native-001/03-reopen-failed.jpg) [重開成功畫面](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/native-001/04-reopen-success.jpg)

正式恢復按產品規則清除原 3 條冪等命令，保留 10 項資源、14 條事件與原匯出身分。原生階段未改變這些業務表，新增匯出、執行、模型執行與評測均為 0。首次啟動僅建立 1 行介面設定；兩次原生退出碼均為 0，兩次停機資料庫位元組及全部表內容完全一致。[停機根核驗](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/native-001/root-readback.json)

原工作庫選擇已恢復，守衛釋放鎖，App 與控制程序均已停止。原 E22 庫、準備完成後凍結的先前 7 個驗收庫及 12 個模型來源檔案保持；本輪沒有連接原使用者庫 SQL。備份恢復回歸 36 項通過，保留 2 項既有警告；原生啟動守衛測試 7 項通過。[完成回執](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/native-001/completion.json) [備份恢復測試](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/backup-tests.log)

輔助過程保留負例：首次用系統 Python 執行工具因缺少依賴而停止，改用專案虛擬環境後通過；退出確認尚未完成時，快照守衛拒絕連接資料庫；核驗器初次把實際 JPEG 截圖誤認為 PNG，核對檔案頭後只修正副檔名與格式檢查，影像位元組未改變。[執行環境失敗](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/helper-tests-wrong-runtime.log) [截圖格式假設失敗](../../../../.artifacts/native-midcopy-records-ver2-4-037-v1/native-001/readback-initial-image-format.log)

本次接受正式備份恢復後的原生歷史展示及重開保持。複製途中故障和恢復匯出的觸發仍來自上一階段包內服務 HTTP 路徑；本次沒有透過原生按鈕再次觸發故障或新匯出，也不證明合成夾具能夠推理、全部物件升級匯出或完整 M6。
