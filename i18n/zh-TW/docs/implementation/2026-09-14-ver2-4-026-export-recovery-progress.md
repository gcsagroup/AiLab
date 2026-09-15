<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-14-ver2-4-026-export-recovery-progress.md) · [繁體中文](2026-09-14-ver2-4-026-export-recovery-progress.md) · [English](../../../en/docs/implementation/2026-09-14-ver2-4-026-export-recovery-progress.md)
<!-- translation-navigation:end -->

<a id="ver24026完整导出包登记恢复"></a>

# Ver2.4（026）完整導出包登記恢復

本輪沿用固定路徑的 026 公司簽名包，沒有產品源碼修改或重新構建。一次原生會話將已有文字修訂版 3 導出；完整文件包發佈後，精確登記故障使界面進入“待覈實”。移除本批觸發器後，點擊“覈實原導出”，同一記錄成功完成。根已接受本次原生與保護有限子集，完整階段簽署仍保持。

<a id="e130登记故障测试与合法独立恢复"></a>

## E130：登記故障測試與合法獨立恢復

5 項後端相關測試通過，其中新增 1 項使用獨立 SQLite 連接和真實 UPSERT 登記失敗，覆蓋另一計劃不受影響、完整包保留及原號覈實／冪等重放；另外 4 項為已有相關用例。登記觀察器 30 項、恢復準備 7 項、監督器 6 項合成測試分別通過，不合併為產品或原生測試數量。[後端測試](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/source-tests-001/process.json)、[後端用例審閱](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/test-review.md)、[登記觀察器測試](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/tests-001/green-002/process.json)、[準備測試](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/restoration-preparation-001/tests-002/process.json)、[監督器測試](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/supervisor-tests-001/process.json)

正式恢復建立新的獨立庫，後續 App 直接使用該根，沒有再次克隆。61 個連接均在新準備範圍內並已關閉，原源庫 SQL 為 0；已有文字／配音／字幕當前版為 3／3／4。此過程不是 `Backup.create` 產品界面驗收。[準備接受](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/restoration-preparation-001/root-acceptance.json)、[實際準備執行](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/restoration-preparation-001/execution-001/process.json)

觀察器同號校驗的紅例與修正保留；首次測試命令誤選基礎解釋器、未執行測試的失敗另存。DROP 獨立於 pending 觀察成功；正常流程須先移除觸發器才覈實、退出。異常退出後的離線 DROP 只能清理本批新庫，不補簽正常驗收。[登記腳本審閱與失敗原件](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/registration-review.md)

<a id="e131原生完整包待核实到同号成功"></a>

## E131：原生完整包待覈實到同號成功

當前文字修訂版 3／父版 2進入導出，計劃顯示 4 項負載；實際包為 4 項負載加 manifest，共 5 個文件。08 的說明正文為“導出結果待覈實。覈實會檢查原文件包並更新這條記錄。”；下方紅色提示為“導出結果尚未確認，請覈實原導出；不會重新運行模型。”，並提供“覈實原導出”。09 顯示已完成，保持同一 export 編號和原目標目錄；根從真實導出文件、修訂記錄及準備時當前 v3 核對正文完全相等，共 16000 個 Unicode 字符；原包通過完整性核對。[UI審閱](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/ui-review.md)、[覈實結果](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/sql-final/result.json)

07 雖預命名 pending，實際只是初始運行狀態，08 才證明待覈實出現。目錄粘貼超時後使用支持字段 setValue 完成選擇，屬於目錄準備恢復，不是導出重試。10 份 AX、10 張 JPEG 為關鍵界面證據；清單未展開，截圖不證明四個文件名或長正文全文。沒有從任務隊列重開，不能記為完整鍵盤任務。

本輪 1 次 App、1 次導出、1 次 UI 覈實，0 模型、0 保存、0 額外 probe 或系統設置變更；啓動自帶環境檢查照常發生。4 個額外 SQL 連接依次為安裝觸發器、讀取 pending、移除觸發器、退出後 final 讀回，均屬本批新庫。[正常退出結果](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/run/result.json)

退出後 final 的 mode=ro 連接關閉後仍留下 0 字節 WAL 和 32768 字節 SHM。根觀察到兩者時間落在該讀連接窗口，lsof 無持有者，數據庫完整文件事實與正常退出後相等；這兩文件原樣保留，不能聲稱新庫無旁路。首次根讀回因“必須無旁路”的斷言退出 1，保留負例，後續只糾正核對口徑；另一處根讀回把正文誤設為 10000 字符的斷言也保留原失敗，已確認應為 16000，並非文件內容不一致。原生、UI 和 final SQL 無重跑。[首次讀回失敗及旁路事實](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-readback-first-failure.json)、[計數口徑糾正](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-readback-correction-001/reason.json)

根最終讀回通過，原受保護文件按約定字段保持，選擇器原字節、inode 和權限身份恢復，其時間隨選擇和恢復變化；三個鎖重新取得後釋放，產品進程已停止。[根最終讀回](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-readback.json) [獨立邏輯審閱](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/independent-review-001/REVIEW.md)、[獨審結果](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/independent-review-001/result.json)、[根原生接受](../../../../.artifacts/export-registration-sqlite-ver2-4-026-v1/native-run-001/root-native-acceptance.json)

<a id="剩余范围"></a>

## 剩餘範圍

只接受本次文字修訂完整包登記恢復子集，不關閉 AC-27 的全部對象和全部故障，也不提高 AC-23 或 M0—M6。舊 017 故障窗口漏命中與耗盡預算、舊 020 空白、指定 NVIDIA、跨主機、五名首次用戶、乾淨安裝及公證等缺口保持。E128／E129 與之前 026 記錄保留原句；本輪單次啓動也不替代 20 次主窗口初顯驗收。[026既有進度](2026-09-14-ver2-4-026-progress.md)、[017歷史記錄](2026-09-13-ver2-4-017-progress.md)、[026既有包接受](../../../../.artifacts/integration-ver2-4-026-v1/root-bundle-acceptance.json)
