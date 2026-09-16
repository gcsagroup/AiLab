<a id="人工补收中断恢复与生命周期修复源码进展"></a>

# 人工補收中斷恢復與生命週期修復：原始碼進展

本輪修復人工補收在程序中斷後一直處於 collecting，以及控制命令與計算完成、失敗退出、停止訊號異常的邊界。原始碼和臨時程序合同的最終 221 項整合回歸通過。固定公司簽章 App 仍為 Ver2.4（033），不包含本輪修改；034 未建置，完整 M1、M0—M6、全部 AC 與發布狀態不提高。

<a id="人工补收恢复"></a>

## 人工補收恢復

原 attempt 已 failed／cancelled、計算結果已成功時，人工只補收先提交 collecting，再複製或登記。此時真實 SIGKILL 使舊啟動恢復跳過終態，重新開啟仍 collecting 並拒絕再次補收。複製／登記與兩種終態組合的 4 項修前失敗、已登記完成的 2 項通過均保留；首輪修後連既有本機 6／遠端 3，共 15 項通過。[原紅例](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-red.log)、[首輪回歸](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-green.log)

啟動取得庫獨占鎖後，只恢復同 attempt／project／manifest 的唯一活動補收：將收集記為 `COLLECTION_INTERRUPTED`，增加收集版本與事件，保留原終態、終態版本、原因、結束時間、計算清單和已登記結果。不自動 run／resume／collect；遠端任務進入本機登記階段也適用，但不存取遠端、不改變遠端計算狀態。歸屬或清單不符、多活動記錄均不猜選。

擴展恢復 11 項通過，含登記與補償都寫盤失敗後恢復可寫並重新啟動、遠端身分本機登記及歸屬防護。wrong_project 兩輪前置設定錯誤先違反外鍵、再使用無效專案資源；最終改用正式專案建立介面，原失敗保留，不歸類為產品缺陷。恢復交易仍要求儲存可寫，不承諾永久儲存損壞恢復。[最終恢復測試](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-recovery-final.log)、[準備錯誤原件](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-recovery-expanded.log)、[第二輪錯誤](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/recollection-recovery-expanded-fixed.log)

<a id="生命周期边界"></a>

## 生命週期邊界

計算搶先完成時，將尚未確認的 pause／resume 裁決為 `not_applicable`／`COMPUTE_COMPLETED`；失敗收尾保存實際 `process.poll` 退出碼與時間。傳送停止訊號發生 `OSError` 時，保留 cancelling 與 unknown，命令記失敗、裝置保持占用，可用新冪等鍵重試；不把訊號傳送失敗冒充已取消或程序已退出。

原生命週期 8 項為 5 通過／3 失敗；該組修後與恢復 11、檢查點 14 合計 33 通過，耗時 6.47 秒。它們使用確定性狀態合同、臨時庫／檔案和明確測試程序，不是原生 App 或真實模型驗收。後續加強矩陣與整合結果見下文，不重複相加為階段完成數。[生命週期紅例](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-confirmed-red.log)、[修後有限回歸](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-recovery-fixed.log)

<a id="整合验证与剩余范围"></a>

## 整合驗證與剩餘範圍

擴大回歸首次 211 項中 209 通過、2 失敗：舊最簡 cancelled 恢復記錄缺少 compute_outcome，新守衛直接索引引發 KeyError，已改為可缺省讀取；CLI after_spawn 的 10 秒逾時原因未確認，原臨時目錄已輪替。原用例單跑及備份回歸 2 項通過，不能據此宣稱逾時根因已修復。CLI 測試只加強非 200 回應診斷，不改變逾時或重試。[擴大回歸原結果](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/recovery-regression.log)、[限定複查](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/regression-two-failures-recheck.log)

隨後凍結來源的 221 項整合為 219 通過／2 失敗，均為 CLI before_spawn／after_spawn 提交收到空白 503，服務庫沒有新增 attempt。現場系統代理解析顯示回環請求預設經 HTTP 代理；測試的健康檢查和回環客戶端現明確 `trust_env=False`，不更改系統或產品代理、不增加重試或延長逾時。原較早 10 秒逾時缺直接回應證據，只能說可能相關，不能宣稱已證明同一原因。修後 CLI 和整合重跑結果見下文。[凍結整合原結果](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-result.json)、[原失敗日誌](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression.log)

最終控制與恢復獨審單獨執行 36 項，全部通過，執行前後 8 項來源摘要一致；覆蓋生命週期 10、恢復 11、檢查點 14、歷史欄位備份恢復 1。它接受四處實際合同缺陷的修復，但不包含 CLI，也不替代根後續擴大回歸。較早 v2 審查執行期間同檔案仍有平行修改，整合綁定以本次凍結前後核對為準，不將重疊數字相加。[最終整合獨審](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-and-recovery-final-review.md)

根最終整合 221 項全部通過，無失敗／錯誤／略過，48.50 秒，保留 3 項既有警告；控制服務及控制測試全部來源在執行前後摘要一致。CLI 回環直連 11 項另行通過，9.99 秒、1 項警告。獨立路由診斷只建立客戶端而不傳送請求，確認預設 HTTPProxy 與直連 ConnectionPool 的差異；不據此倒推早期逾時全因果。各輪測試範圍重疊，不相加。[最終整合回執](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-v2-result.json)、[來源輸入](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-v2-input.json)、[完整日誌](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-regression-v2.log)、[CLI 直連](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/cli-direct.log)、[唯讀路由診斷](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/independent-httpx-route.json)

最終獨立讀回實際解析 221 條 JUnit 記錄，確認 117 項控制服務／測試來源與凍結輸入及目前檔案一致；沒有重新執行這組測試。本輪命名夾具程序已退出，既有遠端測試服務未動。[最終回歸獨審](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-221-v2-independent-review.md)、[CLI 隔離獨審](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/cli-proxy-isolation-independent-review.md)、[程序收尾](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/controlled-process-readback.json)

最終原始碼回歸與獨審均已收口，限定接受本輪控制合同修復。歷史 73／134 項結果僅按來源重用，E143 原生資料流程、先前建置前記錄與原失敗保持；不將唯讀證據複核當作業務重跑。零模型執行不等於零相依或 Metal 探測，本輪臨時控制合同不能替代新套件與原生驗收，也不自動完成完整 M1。[階段缺口審核](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/independent-gap-review.md)、[舊證據綁定](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/evidence-bindings.json)
