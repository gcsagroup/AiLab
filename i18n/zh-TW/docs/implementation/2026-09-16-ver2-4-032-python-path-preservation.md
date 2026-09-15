<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-16-ver2-4-032-python-path-preservation.md) · [繁體中文](2026-09-16-ver2-4-032-python-path-preservation.md) · [English](../../../en/docs/implementation/2026-09-16-ver2-4-032-python-path-preservation.md)
<!-- translation-navigation:end -->

<a id="ver24032python-路径保留与环境恢复e140"></a>

# Ver2.4（032）Python 路徑保留與環境恢復：E140

032 固定路徑公司簽章包通過根整包複核。真實原生面板保留 venv Python 符號連結原路徑，三環境儲存、同號同庫重新開啟、恢復內建、兩次正常退出與原資料保護恢復的有限子集已獲根接受。外部 venv 依賴探測失敗保留；沒有執行模型，也不提高完整 AC、M0—M6 或發布狀態。031 路徑失敗及原驗收門檻保持歷史原文。

<a id="源码与签名包"></a>

## 原始碼與簽章包

macOS Python helper 明確設定 `setResolvesAliases(false)`，在主執行緒使用原生面板並保留傳回的檔案 URL 路徑；原連線身分校驗與使用者確認保持。66 項宿主測試通過，3 項既有現場測試忽略；新增 5 項 Foundation／臨時檔案測試不建立面板，不能單獨證明原生選擇效果。[原始碼回執](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/source-fix-001/run-summary.json)

唯一正式建置退出 0，根複核以提交 `819c35dab2c621e90e79725aae8090ac0d291841` 為基線，加上 4 項建置自動更新為 032 的版本檔案；該提交自身仍為 031。624 項追蹤來源、162 項生產來源、212 項凍結檔案與 92 項應用輸入核對一致；整包 21966 個普通檔案、48 個連結、4003 個目錄及 7 個公司簽章目標通過。簽章組織 Global Cybersecurity Alliance Limited，團隊 `R3JK7R29AC`；031 歸檔和建置階段 47 項保護記錄保持。[建置回執](../../../../.artifacts/integration-ver2-4-032-v1/build-process-final.json)、[根整包複核](../../../../.artifacts/integration-ver2-4-032-v1/root-frozen-check.json)

<a id="原生选择保存与重开"></a>

## 原生選擇、儲存與重新開啟

本輪只用新 A 獨立庫與同一固定 App。先取消檔案面板，再選精確 `services/control/.venv/bin/python`，確認框保持該原路徑並取消；隨後普通檔案對照選擇解析後的基礎 Python，確認顯示同一普通路徑後取消，未儲存對照路徑。正式 worker、media、audio 選擇各保留面板 URL 和確認框記錄。[符號連結選擇](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/04-venv-selected-before-cancel.ax.txt)、[取消前確認](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/05-venv-confirm-before-cancel.ax.txt)、[普通檔案選擇](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/07-ordinary-python-selected.ax.txt)、[普通檔案確認](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/08-ordinary-python-confirm.ax.txt)

三環境分別明確確認儲存後，首次正常退出 0；停機讀回 `worker_python`、`media_python`、`audio_python` 均精確等於原始 venv 絕對路徑，revision 為 4，資源／事件／命令均為 0。取消和普通檔案對照未增加環境 revision。[external 檢查](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/external-check.json)、[首輪快照](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/a-after-first.json)、[首次退出](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/app-first/exit.json)

第二次啟動綁定同一 App、同一 A 和首輪資料庫摘要。設定介面不顯示精確欄位，因此持久化依據首輪停機欄位、重開前摘要綁定、實際同庫重開及第二輪讀回共同成立，不僅憑按鈕判斷。依序恢復三個內建環境後正常退出 0；三欄位均為明確 null，revision 為 7，資源／事件／命令仍為 0，原 4／7 門檻未降低。[重開狀態](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/23-second-external-status.ax.txt)、[bundled 檢查](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/bundled-check.json)、[第二輪快照](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/a-after-second.json)、[第二次退出](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/app-second/exit.json)

<a id="保护恢复失败与证据限制"></a>

## 保護恢復、失敗與證據限制

守衛跨兩次執行持有，最終恢復與釋放回執完成；App、控制與守衛均已停止。47 項保護記錄中 44 項嚴格不變，含不存在項和重複路徑，並非 44 個不同現存檔案；selector 原位元組、inode 與權限恢復，ctime 差異保留，兩份 startup 日誌允許實際更新。根讀回及接受僅涵蓋本頁有限子集。獨立審查亦通過該限定路徑子集。 [獨立審查](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/independent-native-review.md) [恢復](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/selector-guard/restored.json)、[釋放](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/selector-guard/released.json)、[根讀回](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/root-readback.json)、[根有限接受](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

外部 venv 的四類自動依賴探測失敗，重開時仍顯示失敗；恢復內建後四類介面均顯示環境已準備。這只證明相應依賴狀態變化，不是模型執行或品質通過。本輪沒有安裝依賴、執行模型、匯入資料或匯出診斷 ZIP。[外部狀態](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/20-all-external-save-status.ax.txt)、[內建狀態](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/26-all-bundled-status.ax.txt)

原生證據保存 28 組、56 個 AX 與截圖檔案；截圖副檔名為 PNG，實際位元組為 JPEG／JFIF，原件保留不改寫。19 及 19b 音訊確認截圖異常縮小，路徑結論依據原始 AX、實際確認與停機欄位。根讀回腳本前兩次因普通檔案 AX 屬性順序及 `@` 的 URL 編碼差異失敗；改為擷取 selected 行的檔案 URL 並嚴格核對解碼路徑後通過，原失敗和原 4／7 門檻保持。worker 曾誤選其他列，開啟前已修正到精確 Python，未儲存錯誤路徑；首個截圖輔助函式參數錯誤亦保留。[音訊確認 AX](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/19-audio-python-confirm.ax.txt)、[原異常截圖](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/ui/19-audio-python-confirm.png)、[根記錄](../../../../.artifacts/python-picker-symlink-ver2-4-032-v1/native-run-001/root-readback.json)

本輪沒有重現原生跨庫競態，也未關閉診斷目錄匯出、指定 NVIDIA／HTTPS 跨機、同份 LoRA 回程、既有品質失敗、媒體人工評審、乾淨安裝、五名首次使用者、公證和發布門檻。031 及更早階段繼續按原版本歸屬。[031 失敗記錄](2026-09-16-ver2-4-031-native-picker-progress.md)、[交付矩陣](2026-09-10-current-delivery-matrix.md)

本頁 `.artifacts` 連結為本機證據，不隨 GitHub 原始碼上傳。全部正式文件和歷史記錄繼續提供簡體、繁體、英文三語版本。
