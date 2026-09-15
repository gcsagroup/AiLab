<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-16-ver2-4-031-native-picker-progress.md) · [繁體中文](2026-09-16-ver2-4-031-native-picker-progress.md) · [English](../../../en/docs/implementation/2026-09-16-ver2-4-031-native-picker-progress.md)
<!-- translation-navigation:end -->

<a id="ver24031原生选择器验证与-python-路径失败e139"></a>

# Ver2.4（031）原生選擇器驗證與 Python 路徑失敗：E139

031 公司簽章建置與原始碼迴歸通過。原生實際匯入及取消操作已有觀察，正常退出和原資料保護恢復完成；Python 選擇確認顯示錯誤環境路徑，因此取消並中止原兩階段計畫。完整原生驗收未通過，後續修復尚未實施。根回執僅接受實際匯入、取消、正常退出及保護恢復的有限子集，並明確原生 venv 路徑保持失敗；原計畫未通過，失敗證據不被後續階段覆蓋。

<a id="源码与签名包"></a>

## 原始碼與簽章包

六個原生選擇／環境命令綁定呼叫連線身分，選擇開始與完成、HTTP 派發及傳回均複核；匯入和評測方案彈窗按專案隔離舊回呼。618 項前端、61 項宿主測試及型別檢查通過，3 項現場測試保持忽略；38 項文件／版本測試通過。臨時 HTTP 與注入選擇 Future 的紅綠測試證明其各自範圍，不能替代真實 NSOpenPanel 路徑傳回。[前端迴歸](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/root-tests-001/frontend.log)、[宿主回執](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/host-tests-001/run-summary.json)

唯一正式建置結束碼 0，固定路徑候選為 Ver2.4（031）。根複核以提交 `7047eb0b6bba4a364f19d21313c7919fe6574974` 為原始碼基線，加上 4 項由建置自動更新為 031 的版本檔案；該提交本身並非 031 版本：620 項追蹤檔案、161 項生產來源、211 項凍結檔案及 91 項應用輸入核對一致；整包為 21966 個一般檔案、48 個連結、4003 個目錄，7 個公司簽章目標通過。簽章組織為 Global Cybersecurity Alliance Limited，團隊 `R3JK7R29AC`；030 歸檔保持，建置階段 47 項保護記錄保持。[建置回執](../../../../.artifacts/integration-ver2-4-031-v1/build-process-final.json)、[根整包複核](../../../../.artifacts/integration-ver2-4-031-v1/root-frozen-check.json)

<a id="实际完成与原失败"></a>

## 實際完成與原失敗

本次僅新 A 獨立庫、一次 App 啟動。資料選擇先取消，再選擇準備的 3 條 UTF-8 SFT JSONL，實際檢查並匯入 509 位元組；停機庫記錄原文摘要為 `8b080fe0e0f66107d38fae58b1fbcf7dc46513a583eeffe8658076db6be51273`。編碼與結構檢查通過，分詞、品質和劃分洩漏檢查未執行。[取消資料選擇](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/ui/03-import-cancelled.ax.txt)、[實際匯入](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/ui/06-dataset-imported.ax.txt)、[停機快照](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/a-after-first.json)

Python 檔案視窗先取消。再次在原生面板選擇 `services/control/.venv/bin/python`，生產確認框卻顯示 `/opt/homebrew/Cellar/python@3.13/3.13.9_1/Frameworks/Python.framework/Versions/3.13/bin/python3.13`，與所選 venv 身分不一致，因此取消確認，沒有儲存基礎直譯器。停機設定 revision 仍為 1，`worker_python` 為 null，`media_python`／`audio_python` 欄位不存在；不存在欄位不應改寫為已儲存 null。Python 環境沒有修改，但介面專案／頁面選擇已寫入 `ui_context`，不能聲稱設定完全沒有寫入。[選擇取消](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/ui/07-worker-picker-cancelled.ax.txt)、[路徑偏差確認框](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/ui/08-worker-confirm-before-cancel.ax.txt)、[取消確認](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/ui/09-worker-confirm-cancelled.ax.txt)

原 external 階段檢查實際結束碼 1，錯誤為 `三环境最终字段与阶段目标不符`。原計畫要求三欄位為 venv 路徑、revision 4，實際未進行成功設定；保留該失敗，不改檢查器、快照或資料庫來湊通過。沒有第二次啟動，沒有 revision 7 的 bundled 恢復，也沒有診斷 ZIP 匯出或模型執行。[原檢查失敗](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/planned-external-check.stderr.log)

App 正常退出 0。守衛恢復原 selector 位元組及檔案身分，ctime 變化保留；47 項基線中除 selector 和兩份新 startup 外，44 項保護記錄嚴格不變，包含不存在項和重複路徑。守衛記錄不承諾無限期連續持鎖。[退出回執](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/app-first/exit.json)、[恢復與保護讀回](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/selector-guard/restored.json)、[釋放回執](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/selector-guard/released.json)

根最終讀回核對匯入原件、副本、資料庫資源和命令記錄一致，並確認 App／控制／守衛已停止。自動環境探測已有觀察，不能寫成零探測；本輪沒有模型任務。儲存的 10 組 AX／截圖中，確認框含基礎路徑，但選中 Python 當刻沒有另存獨立介面檔案；準確所選 URL 來自既有會話 CUA 呼叫與輸出摘錄，指向 venv 的 Python，不是重新執行操作。面板舊元素編號失效、路徑貼上逾時、完整檔案路徑未跳轉及誤選列後的重新核對均保留在根記錄中。[根讀回](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/root-readback.json)、[有限接受與失敗](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/root-native-acceptance.json)、[原始選擇記錄摘錄](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/native-run-001/python-panel-selection-original-cua.json)

<a id="根因与下一步边界"></a>

## 根因與下一步邊界

唯讀原始碼顯示鎖定 rfd 使用 NSOpenPanel，未關閉預設別名解析；這是與現場路徑偏差一致的機制解釋，不是原生面板內部行為的直接觀測。已觀察的事實是確認框在宿主業務層儲存前顯示基礎 Python 路徑。既有 helper 測試直接注入符號連結 PathBuf，只證明業務層保留傳入路徑，沒有經過真實原生面板。針對面板關閉解析的最小修復尚未實施；即使後續程式碼或屬性檢查通過，也須用下一候選的真實選擇操作驗證 POSIX 符號連結路徑，不拼接預期路徑偽造結果。[根因與證據](../../../../.artifacts/native-picker-scope-ver2-4-next-v1/python-picker-alias-root-cause.md)

本次不能關閉三環境設定／重新開啟／恢復內建、診斷目錄匯出、原生跨庫競態或完整 AC。指定 NVIDIA 與同份 LoRA 回程、既有品質失敗、媒體人工評審、乾淨安裝、五名首次使用者、公證及發布門檻繼續保留。030／E138 及更早記錄保持原版本歸屬。[交付矩陣](2026-09-10-current-delivery-matrix.md)

本頁 `.artifacts` 連結為本機證據，不隨 GitHub 原始碼上傳。正式文件和歷史記錄繼續提供簡體、繁體、英文三語版本。
