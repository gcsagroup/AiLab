<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-15-ver2-4-027-keyboard-progress.md) · [繁體中文](2026-09-15-ver2-4-027-keyboard-progress.md) · [English](../../../en/docs/implementation/2026-09-15-ver2-4-027-keyboard-progress.md)
<!-- translation-navigation:end -->

<a id="ver24027键盘导出任务"></a>

# Ver2.4（027）鍵盤導出任務

本輪固定公司簽名包為 027。源碼和 Safari 組件驗證完成後，在已有合法恢復根中通過純鍵盤進入文字原作品導出、選擇目錄、核對計劃、一次提交，再從任務隊列重開同號已完成導出並正常退出。停機讀回與該原生鍵盤任務子集已獲根接受；完整 AC 與 M 階段不隨本輪提高。

<a id="e132最小键盘属性与-safari-组件子集"></a>

## E132：最小鍵盤屬性與 Safari 組件子集

僅 `ui.tsx`、`App.tsx` 增加顯式 tabindex 和一行解釋：共用 Button 默認 0、保留調用方指定值，Dialog 關閉按鈕及 App 的 19 處原生按鈕加入宿主順序。沒有新增全局 Tab 接管或改寫業務請求。新增測試原件在修前 4 失敗、2 通過；修後 64 項通過，補回命令誤拼漏選的兩份文件後另 11 項通過，共 75 項，類型檢查通過。7 項夾具測試另計，原紅例與命令誤拼記錄保留。[源碼接受](../../../../.artifacts/keyboard-task-ver2-4-next-v1/root-source-acceptance.json)、[源碼與測試記錄](../../../../.artifacts/keyboard-task-ver2-4-next-v1/source-tests-001/REVIEW.md)、[獨立審查](../../../../.artifacts/keyboard-task-ver2-4-next-v1/independent-source-review.md)

真實 Safari 組件記錄支持 Tab／Shift-Tab、導出彈窗內往返和關閉回入口：37 條 focusin、16 次 GET、零業務寫和頁面錯誤。夾具作品是視頻，任務隊列為空；沒有執行導出，不把空隊列開關寫成同號任務重開。05 保存圖最終焦點仍為目錄，中間關閉按鈕往返由焦點 trace 支持。其它組件原生按鈕及完整宿主規則未逐項驗收。[Safari保存證據讀回](../../../../.artifacts/keyboard-task-ver2-4-next-v1/browser-001/root-readback.json)

<a id="e133027-包真实键盘任务与停机读回"></a>

## E133：027 包、真實鍵盤任務與停機讀回

9 月 14 日唯一 027 構建退出 0，完整包、160 項生產來源與 7 個公司簽名目標已獲根接受。App 仍在 `apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app`；身份為 `Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)`。包接受中的“尚未啓動原生”保留形成時含義，本節記錄後續原生事實；未執行公證或發佈。[027包接受](../../../../.artifacts/integration-ver2-4-027-v1/root-bundle-acceptance.json)

9 月 15 日本次原生直接使用上一輪合法恢復根，沒有新恢復或模型運行。選已有文字作品的“導出原作品”，`work_revision_id=null`；09 展開的負載為 `work/result.txt`、`recipe.json`、`object.json`。10 顯示已完成，export 為 `export-adcafd845a5e492d849b57ea5f6c3ea8`；13 隊列出現 `task-7d983f060f844d39b74a800a450e978a`，14 重開同一 export 和原目標目錄。17 退出確認後 App 正常退出 0。17 份 AX、16 張 JPEG 與 158 條操作記錄（含一次目錄輸入）已保存；目錄通過原生面板鍵盤跳轉和輸入選擇，未用支持字段代填產品只讀路徑。此處的同號重開是原生任務事實，與 E132 的 Safari 空隊列不同。[操作記錄](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/keyboard-log.json)、[展開計劃](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/09-plan-files-expanded.ax.txt)、[初次成功](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/10-export-submitted.ax.txt)、[同號重開](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/14-same-export-reopened.ax.txt)

正常退出記錄表明 1 次 App、1 次導出、0 模型、0 reconcile、0 額外 probe／系統設置修改，原選擇恢復。啓動會話額外 SQL 為 0；隨後根以唯一 `mode=ro&immutable=1` 連接讀取停機新庫，實際退出 0，連接已關閉且 DB／三旁路完整文件事實前後相同。本次停機後三旁路均不存在，這是當次文件事實；上輪保存的空 WAL／32768 字節 SHM 歷史事實不改寫，也沒有外部清理。[正常退出](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/run/result.json)、[連接回執](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/connection.json)、[讀回後文件事實](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/facts-after.json)

讀回結果為 `export_verified_settings_unchanged`：舊 519 個資源、665 條事件、2 條命令、項目、schema version 和 settings 保持；新增計劃／導出／任務／執行共 4 資源、8 條正常事件和 1 條 export 命令，未出現 reconcile。實際包為三負載加 manifest 共四文件，來源、摘要與內容核對通過。八條事件由三條前置狀態、三條進度、finalizing 和 succeeded 組成；此前九條預估更正，舊準備稿保留。本輪是原文字產物，不套用 E131 修訂版 3 的四負載加 manifest 或 16000 字符斷言；舊五文件包完整保護另核。[停機邏輯與包核對](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/result.json)、[包清單與文件事實](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/package.json)

根已接受本次停機原作品導出數據子集：最終 523 資源／673 事件／3 命令，原文字為 105 個 Unicode 字符、315 個 UTF-8 字節，三負載合計 4114 字節；原 23 項保護按約定字段、原 020 全樹與上輪五文件包保持。選擇器原字節、inode 和權限身份恢復，其時間隨本次切換和恢復變化。[根停機數據接受](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/root-readback.json)

保存原件獨審與根已接受本次完整任務的純鍵盤操作鏈，未使用鼠標、AXPress、直接 focus 或 setValue 完成鏈路。08 計劃更新和 10 成功更新後，焦點均曾為 HTML2，下一次 Tab 才回關閉按鈕6；不能聲稱全程焦點連續或所有按鈕已驗。06 僅有 AX，沒有圖像；系統退出提示的 16／17 在 Tab 後仍為 sheet，最終 Return 正常退出由進程回執證明，不寫成“退出按鈕已聚焦”。無逐鍵時鐘，不簽交互效率。[原生保存證據獨審](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/independent-keyboard-review.md)、[根原生任務接受](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/root-native-acceptance.json)

<a id="保持的边界"></a>

## 保持的邊界

當前剩餘項以本次新增摘要為準：E131 已補中性待覈實提示與完整文字修訂包同號補登記成功的有限子項，E133 已有文字原作品鍵盤導出、同號任務重開及停機讀回證據；這些已完成的有限子項不再列為重復待辦。歷史表中的“仍未驗”保留其形成時點；其它對象／故障出口、其它鍵盤任務與完整 AC／M 階段繼續待驗。

同次宿主回執為 7997.902083 毫秒（約 7.998 秒），其 scope 是宿主 run 入口至首屏數據和環境完成後的雙動畫幀。它是一次完整就緒參考，不是單獨的主窗口初顯計時，不提高 20 次冷啓動初顯門檻，也不解釋舊長尾。[原始啓動回執](../../../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/run/first-frame.original.json)

只記錄這一已有文字原作品導出的真實鍵盤路徑；其它組件按鈕、其它任務組合、完整 AC-23／AC-27、AC-25 五名首次用戶、AC-26 指定跨端同份產物和 M0—M6 保持未整體簽署。舊 020 偶發空白、設備／質量／安裝／公證等缺口不隨本輪提高。E130／E131 和舊 026 進度保留形成時原文。[上一輪登記恢復](2026-09-14-ver2-4-026-export-recovery-progress.md)
