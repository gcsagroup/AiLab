<a id="ver24034原生补收恢复与-m1-证据e144"></a>

# Ver2.4（034）原生補收恢復與 M1 證據：E144

固定公司簽章 034 套件及全新假執行器庫的中斷恢復→只補收→保存作品→同庫重新開啟已獲根有限接受。資源從 7 增至 10，新增收集、產物、作品各 1，命令 2、事件 3，無新 attempt 或模型執行；原失敗終態四欄位保持。兩次正常退出、47 項保護中 44 項嚴格不變及 selector 恢復通過。

<a id="m1-阶段判定"></a>

## M1 階段判定

根已單獨接受 M1 應用與資料基礎階段，七行合同及介面子集均獲接受。完整 AC、M0、M2—M6、公證及正式發布仍未通過。原生單場景回執的 M1_complete=false 保留原樣，其範圍聲明不替代本次單獨階段判斷；歷史記錄不倒填。[根 M1 階段回執](../../../../.artifacts/integration-ver2-4-034-v1/m1-stage-acceptance.md)、[原生與七行獨審](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/independent-native-review.md)

| M1 子項 | 本次階段接受依據 |
| --- | --- |
| 專案／草稿持久化與隔離 | 221 控制／上下文回歸、E143 同草稿重新開啟與本輪作品歸屬保持。[原生歷史](2026-09-16-ver2-4-033-dataset-workflow.md) |
| 入口、鍵盤／空態 | 既有限定原生證據與本輪 18 項元件合同、034 只補收及保存入口通過。[元件結果](../../../../.artifacts/integration-ver2-4-034-v1/m1-workbench-contracts.log) |
| 固定原型／測試清單 | 原固定清單、摘要與重跑命令保持，重用資產整理證據；不倒填 M6 新成員驗收。[固定資產](../../prototype/reference-2026-09-09/README.md) |
| 真實檔案／manifest 與匯入信任 | E143 匯入拒絕與檔案證據、本輪原 manifest／輸出及 8 個 runs 檔案保持。[獨審](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/independent-native-review.md) |
| 假執行器狀態與只補收 | 221 中生命週期 10／恢復 11 項及本次真實中斷原生閉環關閉原主要缺口。[控制獨審](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/lifecycle-and-recovery-final-review.md) |
| 能力聯動拒絕 | 本輪 64 項能力合同、E143 長度失效和目前可用動作滿足階段範圍。[能力結果](../../../../.artifacts/integration-ver2-4-034-v1/m1-capability-contracts.log) |
| 交易與備份基礎 | 221 中備份 36／遷移 15 項及新庫恢復、業務持久化、原資料保護通過。[階段根判定](../../../../.artifacts/integration-ver2-4-034-v1/m1-stage-acceptance.md) |

<a id="唯一构建与分层测试"></a>

## 唯一建置與分層測試

以提交 `fe5de1a08e174d1016bf3bdcf0574f107cc35b67` 的 033 原始碼為基線，唯一建置自動修改四項版本檔案為 034，退出 0。根核對 648 追蹤來源、162 生產／212 凍結／92 應用輸入、21966 檔案／48 連結／4003 目錄及 7 個公司簽章目標通過；簽章組織保持 Global Cybersecurity Alliance Limited。套件內控制 PYZ 對應修復程式碼，033 歸檔及 47 項建置保護保持。[根驗包](../../../../.artifacts/integration-ver2-4-034-v1/root-frozen-check.json)、[建置記錄](../../../../.artifacts/integration-ver2-4-034-v1/build-process.json)

原始碼整合 221 項通過，117 項來源前後綁定一致；另有 64 項能力合同和 18 項工作台元件測試通過。它們分別覆蓋臨時真實檔案／資料庫／程序、驗證器和瀏覽器元件，不合併為階段通過數。歷史 36／73／134 與部分新回歸重疊；原 SIGKILL 紅例、生命週期紅例、測試準備錯誤、209＋2／219＋2 及較早 CLI 逾時原因未明均保留。回環測試代理隔離不修改產品或系統代理。[原始碼進展](2026-09-16-collection-recovery-source-progress.md)、[221 獨審](../../../../.artifacts/m1-exit-audit-ver2-4-033-v1/final-221-v2-independent-review.md)、[64 項](../../../../.artifacts/integration-ver2-4-034-v1/m1-capability-contracts.log)、[18 項](../../../../.artifacts/integration-ver2-4-034-v1/m1-workbench-contracts.log)

<a id="原生准备与实际操作"></a>

## 原生準備與實際操作

新庫明確標為非模型結果，明確假執行器只執行 1 次、resume 為 0；一次受控 ENOSPC 留下計算成功但收集失敗的原嘗試。備份／恢復後，子程序在只補收的複製邊界被真實 SIGKILL，退出 -9，留下 collecting；之後沒有用 Service 提前恢復新 A。準備回執記錄 70 次 SQL 連接關閉、原庫 SQL 為 0；被殺子程序由作業系統關閉連接，不冒稱正常 Service.close。[準備結果](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/setup-result.json)、[中斷邊界](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/crash-checkpoint.json)

第一次實際啟動 034 後，介面保留原執行失敗並提供 `只补收已有产物`。根點擊一次後，介面顯示已補收且原中斷或取消記錄仍保留；再點擊保存作品一次，作品與素材的文字卡顯示已保存、原 attempt 編號及完整短正文。沒有另開編輯器或修改文字。第二次同號同庫啟動直接恢復作品頁，再返回原任務，正文、原失敗與已補收提示均保持，沒有再次補收或保存。[原生介面與邊界](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/ui-review.json)

停機確認資源 7→10，僅新增 collection／artifact／work 各 1；新增 2 命令、3 事件，無新 attempt、訓練或模型生成。收集版本從 3 到 6，最終有 3 條收集記錄；原 state、state_version、terminal_reason、finished_at 四欄位和原計算清單／輸出摘要保持。精確 `COLLECTION_INTERRUPTED` 原因來自收集記錄及停機事件，介面沒有顯示該代碼。[首次讀回](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/first-check.json)、[重新開啟讀回](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/second-check.json)

兩次 App 正常退出 0；重新開啟前後業務表與作品實物保持，允許 UI 上下文改變，不宣稱原始資料庫或整個快照位元組相同。47 項既有保護記錄中 44 項嚴格不變，selector 原位元組／inode／權限等恢復，ctime 變化保留，兩項啟動日誌允許更新；守衛恢復並釋放。[根讀回](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/root-readback.json)、[原生有限接受](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/native-run-001/root-native-acceptance.json)

<a id="失败历史与证据限制"></a>

## 失敗歷史與證據限制

首次啟動請求在 Popen 前因合法相對守衛路徑被拒絕，尚未建立 App。啟動器僅修精確路徑與工作目錄識別，9 項代表測試通過，原檔案和失敗回執保留；根隨後明確重試，實際 App 總共啟動兩次，無自動重試或產品修改。退出後 AX 返回 App quit，由記錄器的退出 0 補足。[啟動器修正與原失敗](../../../../.artifacts/native-collection-recovery-ver2-4-034-v1/launch-path-fix-001/REVIEW.md)

本輪保存 5 組 AX 與截圖，證明關鍵介面狀態，不是連續錄影。短正文在卡片中完整顯示，不擴大為編輯器驗收；假執行器結果不等於模型品質或真實訓練。M1 使用假執行器的合同與介面子集，不把 M2—M6、NVIDIA 實機或新成員安裝驗收新增為 M1 門檻；原生順序流程也不替代全部原始碼競態負例。E143 及此前原始碼階段原文與失敗保持。

部分模型名在截圖中被截短，完整名稱由 AX 核對；關鍵檢查點不證明 HTTP 請求總數，也不宣稱零環境探測。
