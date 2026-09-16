<a id="ver24033数据导入来源划分与草稿重开e143"></a>

# Ver2.4（033）資料匯入、來源劃分與草稿重新開啟：E143

固定路徑公司簽章 033 套件、原生資料匯入→來源劃分→配置檢查→長度失效→同庫重新開啟的有限流程已獲根接受。兩次正常退出，新增 12 項資源／3 條命令／0 次執行，最終草稿修訂為 5；47 項保護記錄中 44 項嚴格不變，原 selector 恢復，守衛釋放。沒有訓練或模型生成，不簽署完整 M1、M0—M6、全部 AC、公證或發布就緒。

<a id="构建与源码证据"></a>

## 建置與原始碼證據

以提交 `8d98c674a72c2e4bba6a3e80f87c031222b6e8ef` 為 032 原始碼基線，唯一正式建置自動修改四項版本檔案為 033，退出 0；639 項追蹤來源、162 項生產來源、212 項凍結檔案、92 項應用輸入與投影一致。根整包核對 21966 檔案、48 連結、4003 目錄及 7 個公司簽章目標通過，簽章組織保持 Global Cybersecurity Alliance Limited；032 歸檔保留。[根驗包](../../../../.artifacts/integration-ver2-4-033-v1/root-frozen-check.json)、[建置獨審](../../../../.artifacts/integration-ver2-4-033-v1/independent-build-review.md)、[032 歸檔](../../../../.artifacts/integration-ver2-4-033-v1/archive-032-result.json)

首次根核驗器錯誤假定控制報告含兩項後端原始碼欄位而失敗，原日誌保留；修正後用真實控制二進位 PYZ 的完整模組程式碼物件比對凍結原始碼，僅正規化檔案路徑，再完成根核驗。核驗器代表測試 12 項、版本測試 12 項通過。這是核驗器修正，不是首次驗包全綠，也不表示發生第二次建置。[原失敗](../../../../.artifacts/integration-ver2-4-033-v1/root-verify-001.log)、[實際 PYZ 獨審](../../../../.artifacts/integration-ver2-4-033-v1/control-pyz-independent-readback.json)

來源已有 620 項前端及 73 項收尾控制回歸通過；前端首次兩項逾時、降低平行度後的重跑條件、警告與補收原紅例均保留在[建置前原始碼記錄](2026-09-16-dataset-and-collection-source-fixes.md)。另有 134 項核心控制測試通過、無跳過，覆蓋上下文、CLI 中斷／停止未知、備份恢復與遷移；CLI 含相依及 Metal 探測，沒有模型執行。它們不替代本次原生證據，也不等於補收故障已在原生介面重現。[核心回歸](../../../../.artifacts/integration-ver2-4-033-v1/m1-core-regression-result.json)

<a id="原生数据与配置流程"></a>

## 原生資料與配置流程

正式恢復歷史備份的 737 檔案至獨立新 A，50 次 SQL 連接全部關閉，原工作庫 SQL 為 0；準備未預置匯入、劃分或草稿。實際介面先分別拒絕空回答、僅 system、非法 JSON，再一次匯入結構合法的 7 條／13628 位元組主檔案；三個拒絕計畫保留，超長樣本並未在匯入階段刪除。[恢復結果](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/setup-result.json)、[介面審核](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui-review.json)

使用原 Qwen 模型、最大長度 512、種子 7、驗證比例 25% 完成套件內 CPU 分詞：6 條有效、1 條超長排除、5 個來源組，訓練 5 條／4 組、驗證 1 條／1 組，實際驗證樣本比例 16.67%，監督與移位監督各 40。展開分詞證據後明確套用一次，保留原件、兩獨立子集及來源證明；驗證子集訓練入口停用。隨後從訓練側讀取已套用記錄並選擇`使用训练子集`，沒有再次準備或套用。[分詞預覽](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/008-split_cpu_ready.txt)、[套用結果](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/010-split_applied.txt)

新建訓練草稿後手選同一原模型，使用本機 Apple GPU、長度 512、步數 7。真實配置檢查通過，顯示 5 條可訓練、監督 34 和未綁定凍結評測計畫警告；沒有點擊開始訓練。長度改為 256 後舊成功檢查立即失效，再檢查僅被 `DATASET_SPLIT_CHECK_EXPIRED` 阻擋；原劃分仍為 512。第二次啟動直接恢復同一草稿，顯示步數 7／長度 256，沒有經過首頁繼續，也未再次檢查或編輯。[正檢查](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/013-training_512_passed.txt)、[失效與負檢查](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/015-training_256_blocked.txt)、[重新開啟草稿](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui/017-reopened_same_draft.txt)

<a id="停机持久化与保护"></a>

## 停機持久化與保護

停機精確新增 4 個匯入計畫、3 個資料集、1 個劃分計畫、1 個劃分記錄、1 個訓練任務、2 個 preflight，共 12 項資源；匯入、準備、套用各 1 條命令，共 3 條，新增 attempt 為 0。最終草稿修訂 5，正負檢查分別綁定對應修訂與配置；生產證明校驗核對原行、來源組、子集位元組及模型／分詞身分。兩次停機業務、六個資料／證明檔案摘要及原始資料庫 SHA 均相同；沒有把恢復庫中的既有歷史執行說成零。[首次停機](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/first-check.json)、[第二次停機](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/second-check.json)

兩次 App 均正常退出 0，47 項既有保護記錄中 44 項嚴格保持；原 selector 位元組、inode、權限等恢復，ctime 變化保留，兩項啟動日誌按原合同允許更新。守衛已恢復並釋放，不宣稱鎖永不中斷。最終根回執接受本次有限資料流程。[根讀回](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/root-readback.json)、[根接受](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

<a id="操作限制与未完成范围"></a>

## 操作限制與未完成範圍

獨立原生審查接受上述有限範圍，原始操作偏差及證據限制保留；它不替代尚未覆蓋的完整階段。[原生獨審](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/independent-native-review.md)

保留實際操作偏差：首個檔案 GoTo 貼上逾時，重讀後用完整路徑修正；第二檔案 AX 點擊未選中，改用 GoTo 並核對 URL；輔助按鈕匹配誤計焦點說明行而拒絕，修正為只匹配數字節點。數值輸入首輪顯示 07／0256，但有效配方、停機資料及重新開啟介面為 7／256。首次確認退出後 AX 返回 App quit，實際退出碼為 0。沒有額外持久業務記錄；不推定無 HTTP 請求。證據為逐步 AX 與截圖、長頁分圖，不是連續錄影。[操作與觀察邊界](../../../../.artifacts/dataset-workflow-ver2-4-032-v1/native-run-001/ui-review.json)

真實 CPU tokenizer 與配置檢查不載入模型進行訓練或生成，但會執行環境探測、讀取分詞資料及模型清單摘要。來源組隔離不等於語義去重、驗證損失或品質通過；重新開啟沒有重用舊 preflight 宣稱仍可提交。既有 E64—E72 來源組成功、E142 及原始碼階段失敗保留，不稱首次能力；延遲讀取競態和補收故障的原生現場重現、永久儲存故障、完整階段與發布門檻仍未完成。
