<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-15-ver2-4-028-workbench-keyboard-progress.md) · [繁體中文](2026-09-15-ver2-4-028-workbench-keyboard-progress.md) · [English](../../../en/docs/implementation/2026-09-15-ver2-4-028-workbench-keyboard-progress.md)
<!-- translation-navigation:end -->

<a id="ver24028workbench-四按钮键盘修复"></a>

# Ver2.4（028）Workbench 四按鈕鍵盤修復

固定公司簽名候選已更新為 028。四按鈕的最小源碼修復、59 項相關前端測試與真實 Safari 子集通過；028 唯一構建、已有任務的原生正反向焦點、正常退出及停機數據子集已獲根接受。027 原文字作品純鍵盤導出和同號重開的有限接受保留；完整 AC 和 M0—M6 不提高。

<a id="e134源码与-safari-组件子集"></a>

## E134：源碼與 Safari 組件子集

正式構建前，160 項生產輸入相對 027 僅 Workbench.tsx 變化：為“工作台”返回、導入模型、導入數據、新建評測方案四按鈕增加 `tabIndex={0}`，保留回調、fieldset 禁用與返回先 save 的邏輯。新增回歸修前 1 個用例失敗、包含四按鈕斷言，另 8 個通過；修後 6 文件共 59 項相關測試及類型檢查通過，不與 027 的 75 項累計。[源碼接受](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/root-source-acceptance.json)、[獨立審查補充接受](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/root-review-acceptance.json)

真實 Safari 組件中，8 次 Tab、7 次 Shift-Tab 後四按鈕正反可達，44 條被動記錄、2 次 GET，業務寫、回調與頁面錯誤均為 0；沒有激活入口或改變系統設置。該組件不含原生已有的“劃分訓練與驗證”，不能套用兩者的按鍵數和順序。[Safari 修後接受](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/browser-after-readback.json)

保存 helper 誤寫舊 ui-before 目錄，導致 4 份修前快照哈希變化，部分字節相同的 AX 也被重寫；修前正向截圖／AX、完整按鍵和被動日誌仍匹配原哈希，覆蓋前獨審保留，8 份修後原字節另存 ui-after。不能稱整套修前快照原封保全，也沒有偽造或重跑修前界面抵消錯誤。[保存事故](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/snapshot-save-incident.json)

<a id="e135028-包原生焦点与停机读回"></a>

## E135：028 包、原生焦點與停機讀回

9 月 15 日北京時間，唯一 028 構建退出 0，構建自動更新四個版本文件。根整包復核通過：160 項生產來源、210 項凍結輸入、90 項應用輸入一致，包內 21966 個普通文件、48 個符號鏈接、4003 個目錄及 7 個公司簽名目標獲接受。固定 App 仍在 `apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app`，簽名為 `Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)`；未公證或發佈。源碼原件的待獨審、包原件的尚未啓動原生均保留形成時含義，後續接受分別關閉對應待辦。[028 包接受](../../../../.artifacts/integration-ver2-4-028-v1/root-bundle-acceptance.json)

原生打開已有 `task-6fe6ed2f8cbd4a909d93d27e3a9b785c`／“模型微調 · 05:01”，草稿 revision 4、訓練步數 64、最近運行 cancelled；界面 50／64 屬於舊運行。舊 AX 編號 227 被拒後，fresh 狀態中的編號 37 成功打開同一任務，沒有錯點。實際 9 次 Tab、7 次 Shift-Tab，含前導“AI 輔助”和已有“劃分訓練與驗證”，四目標按鈕正反焦點可見且未激活，沒有編輯、保存草稿或訓練。[原生根接受](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/root-native-acceptance.json)

保存集為 19 份 AX、19 張 JPEG 加 1 份觀察，共 39 文件，集合及摘要已核；前導“AI 輔助”焦點無獨立截圖，04—18 的 15 份逐項觀察不等於每鍵截圖或逐鍵時鐘。系統退出確認仍聚焦 sheet，正常退出由進程回執證明，不稱退出按鈕已聚焦。[保存證據獨審](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-review-001/review.md)、[運行回執](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/run/result.json)

唯一原生執行退出 0，1 次 App、0 模型，鎖已釋放。隨後唯一 `mode=ro&immutable=1` 停機連接讀取成功並在 finally 關閉，根復核額外 SQL 為 0。523 資源／673 事件／3 命令、項目、schema version 及全部業務記錄嚴格不變，草稿 revision 4 保持；僅當前項目三項 settings 頁面選擇變化：page 從 assets 到 home，recent_tasks 從不存在到 text:train 指向上述同一任務，task_id 從 null 到同一任務 ID。[停機根接受](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/root-readback.json)

工作庫 SHA 從 `02ed3063…` 變為 `e40dc70d…`，不能聲稱 App 啓動前後庫字節或全部 settings 不變；停機讀回期間 DB／三旁路文件事實保持，三旁路均不存在。23 項保護中 selector 內容、inode 與權限身份恢復，mtime／ctime 隨切換恢復變化；原 020 全樹、舊庫、既有遠程 PID 30114、舊五文件與 027 四文件導出包均保持。[邏輯結果](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/readback-001/result.json)、[保護明細](../../../../.artifacts/workbench-keyboard-ver2-4-next-v1/native-run-001/root-readback.json)

027 原文字作品完整純鍵盤導出、隊列同號重開與停機接受不撤回；新增 4 資源／8 事件／1 命令和四文件包仍歸 027，不在本輪重復計數。[027 進度原文](2026-09-15-ver2-4-027-keyboard-progress.md)

本輪未驗四按鈕激活及彈窗業務效果、原生 busy／running／checkpoint 禁用組合或其它完整鍵盤任務；“工作台”返回會先 save，不能當只讀返回。完整 AC-23／AC-27 及其它完整 AC、AC-25 五名首次用戶、AC-26 指定跨端同份產物、M0—M6 均不提高。指定 NVIDIA、設備差異、舊質量失敗與既用模型預算、乾淨安裝／公證發佈、舊 020 偶發空白及冷啓動初顯／完整就緒的歷史缺口保持原狀態。
