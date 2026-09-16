<a id="038-导出清单身份恢复与原生重开"></a>

# 038 匯出清單身分恢復與原生重開

固定公司簽名候選已更新為 Ver2.4（038），包含完整匯出清單身分核對修復。包內真實服務的受控登記故障、錯誤版本拒絕、新匯出成功，以及正式恢復庫中的原生歷史查看與重開通過。此結論僅涵蓋本次子集，完整 M6、M0—M6、公證及正式發行仍未完成。

<a id="候选与修复"></a>

## 候選與修復

簽名組織為 Global Cybersecurity Alliance Limited。整包讀回核對 21966 個一般檔案、48 個符號連結及 7 個公司簽名目標；凍結原始碼與包內控制服務的實際編譯內容一致。主程式摘要為 `60c0940798b39a7c9378ffd5f1d4fb544e4a409fb2b52b26403ed0e894be75fc`。[構建核對](../../../../.artifacts/integration-ver2-4-038-v1/root-frozen-check.json)

此前原始碼回歸共 179 項通過。產生端與恢復核對端共用完整凍結清單，拒絕錯誤物件或版本、缺項、額外聲明、錯誤類型和非有限數值；合法完整包仍可恢復。修復前失敗證據保留。[原始碼回歸](../../../../.artifacts/export-manifest-identity-source-v1/regression-final.log)

<a id="包内服务与故障边界"></a>

## 包內服務與故障邊界

透過實際 HTTP 請求，在全新獨立庫使用不可執行的合成模型檔案夾具。僅對本次匯出注入 SQLite 登記拒絕，檔案寫入後正常停止服務，移除測試觸發器並修改清單中的版本身分，再重啟核實。該步驟模擬登記失敗，不是作業系統終止程序或真實複製途中崩潰。

錯誤版本包被拒絕，原記錄成為 `EXPORT_INTERRUPTED`，未登記可用路徑；原檔案與錯誤包均保留。重新準備後，新匯出成功，4 個內容檔案及清單通過核對，服務重啟後失敗和成功記錄仍分別保留。隨後透過正式產品備份和恢復建立獨立原生驗收庫。[包內結果](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/run-001/result.json)

<a id="原生查看退出与保护"></a>

## 原生查看、退出與保護

同一固定 App 兩次開啟正式恢復庫，分別查看既有失敗記錄與成功記錄，並透過原生退出確認正常停止。第一次停機只有介面設定表變化，業務表保持；第二次停機的整個資料庫快照與第一次一致。原庫選擇已恢復，47 項保護記錄完成核對，12 個模型來源檔案及前序驗收庫保持；沒有新增模型執行或連接原使用者庫進行 SQL 查詢。[最終核對](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/root-readback.json)

兩次宿主完整就緒分別為 4522.186 和 4580.050 毫秒，外部觀察分別為 4650.026 和 4732.063 毫秒。它們不測量視窗初顯，也不滿足 20 次初顯驗收的證據要求。[首次啟動](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-001/startup/report.json) [重開啟動](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/startup/report.json)

原生操作僅查看 HTTP 階段已經形成的匯出結果，沒有在介面觸發本次故障或重新匯出。[重開失敗記錄](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/01-failed.jpg) [重開成功記錄](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/02-success.jpg)

<a id="容量处理与未完成事项"></a>

## 容量處理與未完成事項

構建前後的容量不足記錄保留。僅將可再生構建快取歸檔並核對全部內容、硬連結及屬性後移除原快取，歸檔和拒絕覆寫的恢復工具均保留；未刪除使用者資料、模型或歷史失敗。首次輔助腳本異常、低效唯讀核驗中斷及構建後容量門檻失敗均保留，未降低門檻。[快取歸檔](../../../../.artifacts/build-cache-recovery-038-v1/result.json) [暫存歸檔](../../../../.artifacts/build-cache-recovery-038-v1/staging/result.json) [容量失敗記錄](../../../../.artifacts/integration-ver2-4-038-v1/root-verify.log)

本輪不提供模型品質、指定 NVIDIA 跨端、全部真實物件匯出、乾淨安裝、五名首次使用者、長任務或網路故障的新通過證據。完整 AC27、M6、M0—M6 和發行狀態保持待驗；037 及更早記錄保留形成時結論。
