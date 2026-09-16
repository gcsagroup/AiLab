<a id="ver24035本机真实推理与重开e145"></a>

# Ver2.4（035）本機真實推論與重開：E145

固定公司簽章 035 候選的本機真實推論與同庫重開已獲根有限接受：1 次真實 attempt、0 次訓練，儲存作品並建立未執行的配方草稿，兩次 App 正常退出。原守衛失敗與被拒絕的啟動請求保留；M2、完整 AC、M0、M2—M6、公證及正式發佈狀態不提高。

本次實測裝置為 Apple M5 Max，只關閉已實證的本機參數／預設回歸子集。12 項版本測試與版本檢查通過，不與原始碼或其他夾具測試合併計數。[根有限接受](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-native-acceptance.json)

<a id="构建与来源"></a>

## 建置與來源

建置基線為 `c6d2e0886e1274b653179c4d8512194cdcffce25`，自動版本投影為 035，唯一建置退出 0。根與獨審核對 656 追蹤來源、162 生產／212 凍結／92 應用輸入、21966 檔案／48 連結／4003 目錄及 7 個公司簽章目標；034 封存與建置保護保持。控制套件內實際程式碼符合載入邊界修復。[根驗包](../../../../.artifacts/integration-ver2-4-035-v1/root-frozen-check.json)、[建置獨審](../../../../.artifacts/integration-ver2-4-035-v1/independent-build-review.json)

<a id="真实界面与实际参数"></a>

## 真實介面與實際參數

在全新獨立庫經原生介面匯入凍結的 Qwen 4bit 模型，確認前可見載入信任與權限說明。離線載入選項、憑證環境白名單與獨立程序不等於作業系統沙箱；自訂模型程式碼仍未開放。原模型源 12 個檔案另受保護。[介面記錄](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui-review-first.json)

根另行核對原生 import-plan 與 model 均持久化正確的 7 欄位 `execution_boundary`，並綁定匯入確認 AX／截圖；本項包含資料事實，不只有介面文案。[原生邊界核對](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/model-boundary-native-check.json)

低延遲與低記憶體預覽分別取消，均保留原 auto／2048；再次套用低記憶體後為 auto／512。固定提示詞為 `订单编号为 7391，金额为 82。只回答订单编号数字。`；實際溫度 0、Top-p 1、種子 0、上下文 128、停止序列 `39`、stream=false。50＋79＝129 在檢查階段拒絕，無對應 attempt；僅改最大輸出後 50＋78＝128 允許執行。沒有裁剪輸入。[拒絕介面](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui/09-over-budget-rejected.txt)、[通過介面](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui/10-boundary-preflight-allowed.txt)

唯一真實推論成功，非串流正文為 `7`，token 事件為 0；儲存一次作品，查看原配方，再建立來源草稿但未檢查或執行。首輪 App 正常退出 0。停機核對 15 資源、4 命令、13 事件、6 產物，關聯模型、檢查、snapshot、實際參數、產物副本及作品配方；不只比較數量。[首輪檢查](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/first-check.json)

<a id="守卫失败与已确认恢复"></a>

## 守衛失敗與已確認復原

守衛解析 ps 輸出時發生 `UnicodeDecodeError`，退出 1；finally 已在 App 停止後復原原 selector。未產生正常 released 回執，根另行確認原守衛已退出，並實際重新取得、釋放原庫鎖。47 項保護中 44 項嚴格不變；selector 原身份與位元組復原，ctime 變化與啟動日誌保留。不能宣稱全程連續持鎖。[失敗原記錄](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/guard-failure-001.json)、[根復原讀回](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-readback-after-first.json)

第二次啟動請求退出 1，原因是守衛已進入復原；沒有建立第二個 App 程序。此拒絕不等於重開驗收通過，也不撤銷已完成的首輪推論證據。原失敗、首輪快照與根接受綁定保持原樣。

<a id="同库重开与最终保护"></a>

## 同庫重開與最終保護

經獨立復原方案與門檻審核後，同一 035 套件在同一新庫實際第二次啟動：介面恢復未執行配方草稿，作品與原任務均顯示正文 `7`。沒有新增執行或儲存，兩次 App 退出均為 0；新守衛復原 selector、釋放鎖後退出 0。[最終介面記錄](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui-review.json)、[第二次停機檢查](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/second-check.json)

兩次停機的業務表相同，僅允許 UI 上下文變化；原始資料庫 SHA 實際改變，不宣稱資料庫位元組相同。15 資源、4 命令、13 事件、1 attempt／0 訓練／6 產物保持，31 份模型／執行／產物檔案摘要不變。最終 47 項保護中 44 項嚴格不變，selector 原 inode／位元組復原，12 個模型源檔案不變；持鎖中斷歷史仍保留。[根最終讀回](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-readback.json)

介面證據為關鍵檢查點 AX 與截圖，不是連續錄影。數字框可顯示前導零，停機記錄確認數值；完成截圖停在頁底，儲存作品截圖完整顯示短正文。短輸入與單個固定模型的結果不代表通用品質或效能，也不是 NVIDIA、訓練、首次使用者預演或完整 M2 驗收。既有 M1 階段接受保持；原始碼階段「035 未建置」原文作為歷史記錄保留。

5 名首次使用者的完整乾淨安裝驗收屬於 M6 獨立門檻，不作為 M2 的完成條件；M2 仍需其自身指定裝置、執行位置、異常流程與首次語言試用階段預演的對應證據。

首輪與最終獨審分開儲存，原失敗不覆寫。復原輔助夾具 46 項通過；該組不是真實模型測試，不與其他數量合計。[首輪獨審](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/independent-first-review.md)、[最終獨審](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/independent-native-review.md)、[復原夾具測試](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/reopen-tests-final-v2.log)、[版本測試](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/version-tests.log)
