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

本輪只驗證真實卷滿條件下的計畫阻斷、複製前檢查、釋放空間後的重新匯出及重開持久化。沒有驗證複製途中空間耗盡、系統碟滿、備份失敗、媒體遺失、乾淨安裝、跨裝置、完整遷移回滾或公證發行，也沒有重新執行凍結品質方案。本頁本機證據連結不隨原始碼倉庫上傳。
