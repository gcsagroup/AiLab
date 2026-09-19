<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-10-current-delivery-matrix.md) · [繁體中文](2026-09-10-current-delivery-matrix.md) · [English](../../../en/docs/implementation/2026-09-10-current-delivery-matrix.md)
<!-- translation-navigation:end -->

<a id="当前实现证据与剩余交付矩阵"></a>

# 當前實現、證據與剩餘交付矩陣

Ver2.5（040）公司簽名候選已通過受控空庫的原生冷啟動恢復：故障切換後回到恢復工作區，健康備份遷移、專案保存及同庫重開通過，資料庫與遷移回執保持。最初重開的進程監視器失敗已保留，工具補強後的複驗通過；沒有新增模型執行。含業務資料的失敗升級、完整 AC-22／M6、公證與正式發行仍未完成。 [冷啟動恢復驗收](2026-09-20-cold-start-recovery-source-progress.md)

039 同一公司簽名候選已完成受控空庫的原生遷移失敗回復、健康舊版備份還原及同庫重開。原健康庫 8 項資源保持，修復庫 1→2→3→4 遷移與測試專案重開通過，51 項遷移／備份測試通過；沒有模型執行。冷啟動離線還原、含業務資料的失敗升級及完整 AC-22／M6 仍待完成。 [遷移回復驗收](2026-09-20-ver2-4-039-migration-recovery.md)

039 同一公司簽名候選已完成原 12 項匯出庫重開，並補上 1 項既有受控資料劃分匯出與重開；2 個庫的重開前後資料庫及匯出包完全不變。原版／修訂包的 4 份音影片在獨立播放器播至結尾，圖片獨立開啟。沒有新增模型執行，完整 AC27、M6 與發行仍未完成。 [十二項匯出驗收](2026-09-20-ver2-4-039-twelve-exports.md)

039 固定公司簽名候選已納入匯出目錄項修復。實際包內服務拒絕 4 類不合法目錄項，合法中斷包恢復及全新匯出成功；正式恢復庫中的原生失敗／成功記錄查看、正常退出和同庫重開通過。未新增模型執行，完整 AC27、M6、M0—M6 與發行仍未完成。 [039 驗收與邊界](2026-09-16-export-tree-integrity.md)

以下記錄保留形成時狀態。

原始碼後續修復：038 實際包內服務仍會誤接受清單符號連結，負例已保留。現已在原始碼拒絕清單連結、斷鏈、目錄連結及特殊檔案，186 項相關回歸通過；尚未編入新簽名候選，完整 M6 與發行狀態不提高。 [目錄項修復與負例](2026-09-16-export-tree-integrity.md)

038 固定公司簽名候選已包含完整匯出清單身分修復：包內受控登記故障後的錯誤版本拒絕與新匯出成功通過，正式恢復庫的原生查看、正常退出及同庫重開通過，第二次停機資料庫完全不變。沒有新增模型執行；完整 M6、M0—M6 與發行仍未完成。 [038 驗收與邊界](2026-09-16-ver2-4-038-export-identity.md)

以下記錄保留形成時狀態。

037 已驗證原生複製前磁碟滿拒絕與恢復，以及包內服務複製途中真實卷滿後的失敗保留與恢復匯出。後續正式備份恢復後的原生歷史檢視與重開通過，原失敗、成功記錄及檔案保持；沒有新增模型執行。複製途中故障的觸發仍為 HTTP 路徑，合成夾具不代表模型能力；完整 M6、M0—M6 與發行仍未通過。 [037 磁碟滿恢復驗收](2026-09-16-ver2-4-037-storage-recovery.md)

037 同一簽名候選已完成既有失敗評測的實際准入拒絕、原生報告匯出及重開。11 個內容檔案、60884 位元組逐項核對通過；52 項原資源保持，新增 4 項匯出資源，模型執行與評測均為 0。品質失敗保留，完整 M5、M0—M6 與發行仍未通過。 [037 品質報告驗收](2026-09-16-ver2-4-037-quality-export.md)

037 同一簽名候選已完成工作流明確復用、三項保存、上游修改後失效及同庫重開。原 507 項資源保持，新增 14 項資源、9 條命令，模型執行與訓練均為 0；後續受控占用夾具已驗證原生拒絕時六表不變，正式核實後僅推進一次且重開保持；真實執行競爭、品質與完整 M4 仍待驗收。 [037 工作流驗收](2026-09-16-ver2-4-037-workflow-reuse.md)

037 固定公司簽名候選已完成已下載資料的原生離線登記與套用：真實下載 292 位元組、2 筆資料，提供方停止後重開市場，登記並用於原任務；草稿修訂 2→3，僅資料版本改變，種子 817 保留。正常退出、停機讀回和原資料還原通過；完整 M4、M0—M6 與發行仍未通過。 [037 原生離線驗收](2026-09-16-market-offline-downloads.md)

以下原始碼階段記錄保留形成時狀態。

原始碼進展：市場目錄不可用時可明確查看本機完整下載，檢查登記並用於原草稿。31 項前端、63 項後端及宿主定向測試通過，真實 HTTP 瀏覽器流程通過；固定 App 仍為 036，未包含本輪修復，原生驗收與完整 M4 待完成。 [離線下載入口](2026-09-16-market-offline-downloads.md)

036 固定公司簽名候選已包含官方模型執行邊界修復，整包與原生告知有限驗收通過：官方目錄及本地檢查說明可見；1 專案／1 匯入計畫，未下載、確認匯入或執行模型。正常退出與原資料保護恢復通過，完整 M2 和發行未通過。 [036 告知驗收](2026-09-16-official-model-runtime-boundary.md)

以下原始碼階段與舊候選記錄保留形成時狀態。

原始碼進展：官方模型準備頁增加與手工匯入一致的執行邊界說明，新登記模型保存實際檢查所得欄位；缺失／未知說明不新增下載或登記門檻。相關測試已通過，固定簽名 App 仍為 035，未包含此修復，不提高完整 M2 或發行狀態。 [官方模型準備邊界](2026-09-16-official-model-runtime-boundary.md)

035 包內執行器已完成單次進程網路拒絕下的真實生成，結果為 `7`；未開放媒體／快取請求的拒絕矩陣已發布（E146）。這不代表實體斷網、產品 OS 沙箱或快取命中效能；包內控制服務的真實 HTTP 取消及後續生成恢復也已通過，未作本輪 App UI 驗收；M2 與發布狀態不提高。 [執行邊界與證據](2026-09-16-ver2-4-035-runtime-boundaries.md)

035 固定公司簽章候選的 Apple M5 Max 本機真實推論與同庫重開已獲有限接受（E145）：匯入信任與邊界持久化、預設取消／套用、50+79拒絕／50+78允許、auto512／stop39／stream=false→正文7、作品儲存與未執行配方草稿均有證據。1 次 attempt、0 訓練；15 資源／4 命令／13 事件／6 產物及31份檔案摘要保持，兩次 App 正常退出，47／44 保護與12個模型源復原核對通過。原守衛退出1、被拒啟動與持鎖中斷保留；M2、完整 AC、M0、M2—M6及發佈狀態不提高。 [035 推論與重開證據](2026-09-16-ver2-4-035-native-inference.md)

以下原始碼與候選段落保留形成時狀態，其中「035 未建置」不代表目前候選。

034 固定公司簽章套件與原生補收閉環已獲有限接受（E144）：全新假執行器庫真實中斷後恢復，只補收、保存短文字作品並同庫重新開啟；原失敗終態保持，無新 attempt 或模型執行。資源 7→10、2 命令／3 事件、兩次正常退出和 47／44 保護恢復通過。M1 應用與資料基礎階段通過（合同與介面子集）；完整 AC、M0、M2—M6 與發布仍未通過。 [034 補收恢復與階段證據](2026-09-16-ver2-4-034-collection-recovery.md)

以下原始碼階段及 E143 和更早記錄保留形成時狀態。

原始碼進展：修復人工補收中斷後卡住 collecting，並補齊計算先完成、失敗退出記錄與停止訊號異常的控制邊界。最終 221 項整合回歸通過。固定簽章 App 仍為 033，不包含本輪修改；034 未建置，完整 M1 和發布狀態不提高。 [補收恢復與原始碼邊界](2026-09-16-collection-recovery-source-progress.md)

033 固定公司簽章套件與原生資料流程已獲有限接受（E143）：三項匯入拒絕、7 條主資料匯入、來源劃分、配置通過後長度失效及同庫直接恢復草稿完成。停機新增 12 項資源／3 條命令／0 次執行，草稿修訂 5，兩次正常退出和 47／44 保護恢復通過。沒有訓練或模型生成，不提高完整 M1、M0—M6 或發布狀態。 [033 資料流程與邊界](2026-09-16-ver2-4-033-dataset-workflow.md)

以下原始碼階段及 E142 和更早記錄保留形成時狀態。

**032 字幕流程驗收（2026-09-16，E142）**：固定簽章 App 未重新建置。功能鏈鍵盤操作、容器捲動取樣、繼續／放棄臨時修改、一次儲存 v5 及同庫重新開啟通過；200 條／16000 字元僅末條變化。明確選擇歷史 v4 完成 5 檔案匯出，目前 v5 與歷史 v4 保持；兩次正常退出、47 項保護記錄中 44 項嚴格不變和 selector 恢復已獲根接受。沒有模型執行；舊 020 根因仍未明，完整 AC22、AC27、M0—M6 和發布狀態不提高。 [字幕流程與邊界](2026-09-16-ver2-4-032-subtitle-workflow.md)

以下 E141 及更早記錄保留形成時狀態。

**032 診斷目錄迴歸（2026-09-16，E141）**：固定公司簽章 App 未重新建置。3 條、650 位元組三語資料真實匯入，目錄選擇取消與整次診斷取消分別驗證；中文空格目錄儲存 9316 位元組 ZIP，清單、CRC、摘要和脫敏通過。同號同庫重新開啟後全表、原始資料庫及 ZIP 不變，兩次正常退出與原資料恢復通過。自動環境探測並非零，未執行模型；診斷成功不替代完整 AC27、AC22、M0—M6 或發布驗收。 [診斷迴歸與邊界](2026-09-16-ver2-4-032-diagnostic-directory-regression.md)

以下 E140 及更早記錄保留形成時狀態。

**032 Python 路徑進展（2026-09-16，E140）**：固定公司簽章候選已更新為 Ver2.4（032），原始碼測試、唯一建置與根整包複核通過。原生符號連結原路徑選擇、取消與普通檔案對照、三環境儲存、同號同庫重新開啟、恢復內建、兩次正常退出及保護恢復的有限子集已獲根接受。停機 revision 為 4／7，三欄位先精確儲存原路徑，再明確恢復 null；外部依賴探測失敗保留，未執行模型。完整 AC、原生競態、M0—M6 及發布狀態不提高。 [032 進度與邊界](2026-09-16-ver2-4-032-python-path-preservation.md)

以下 031 及更早記錄保留形成時狀態。

**031 原生選擇器進展（2026-09-16，E139）**：固定公司簽章候選已更新為 Ver2.4（031），原始碼測試、唯一建置與根整包複核通過。原生實際匯入 3 條、509 位元組 JSONL，完成檔案選擇與 Python 確認取消；但選擇 venv Python 後確認框顯示基礎直譯器路徑，已取消且沒有儲存環境設定。三環境儲存、重新開啟、恢復內建與診斷匯出未完成；原生競態、完整 AC、M0—M6 及發布狀態不提高。 [031 進度與負例](2026-09-16-ver2-4-031-native-picker-progress.md)

以下 030 及更早記錄保留形成時狀態。

**最新連線隔離進展（2026-09-16，E138）**：固定公司簽章候選已更新為 Ver2.4（030）。原始碼迴歸、唯一簽章建置、根整包複核及包內真實控制服務的重新啟動驗證與遷移失敗復原兩項測試通過；原生完整備份、目標庫啟動失敗復原、成功切庫、分別儲存專案及同號重新開啟的有限子集已獲根接受；停機讀回與原庫選擇恢復通過。原生檔案、目錄和 Python 環境選擇器的非同步競態仍不在本次涵蓋範圍；完整 AC、M0—M6、公證及公開發布未完成。 [030 進度與邊界](2026-09-16-ver2-4-030-connection-isolation.md)

以下歷史快照保留形成時狀態，不代表目前候選仍停留在舊版本。

**最新 Media 鍵盤進展（2026-09-16，E137）**：固定公司簽名候選已更新為 Ver2.4（029）。唯一構建、三入口在兩個既有任務中的四個原生實例、正反向 Tab、Enter 打開、Escape 關閉回焦、正常退出及一次停機讀回的有限子集已獲根接受。523 資源／673 事件／3 命令及全部業務記錄保持，僅四個預期頁面設定葉子變化；沒有真實導入或模型運行。028 與 027 的既有的有限接受保留，完整 AC、M0—M6、公證及公開發佈未完成。[本次進度](2026-09-15-media-keyboard-progress.md)

以下 E136 及更早記錄保留 2026-09-15 形成時原文；其中容量不足與尚未構建描述屬於歷史狀態。

**最新 Media 鍵盤進展（2026-09-15）**：當前固定公司簽名候選仍為 Ver2.4（028）。Media“導入模型／導入圖片數據／導入圖片素材”三入口的最小屬性修復、56 項相關前端測試、類型檢查及真實 Safari 正反向焦點和 Enter／Escape 回焦子集已接受，獨審待辦已關閉（E136）。029 尚未歸檔、打包或原生驗證；容量低於原 40 GiB 門檻，debug 緩存清理僅待用戶確認，未執行。完整 AC 和 M0—M6 不提高。[本次進度](2026-09-15-media-keyboard-progress.md)

以下 E134／E135 及更早記錄保留形成時原文。

**最新工作台鍵盤進展（2026-09-15）**：固定公司簽名候選已更新為 Ver2.4（028）。Workbench 返回、導入模型、導入數據和新建評測方案四按鈕的最小鍵盤屬性修復、59 項相關前端測試、類型檢查與真實 Safari 子集通過（E134），快照保存錯誤及證據範圍已記錄。028 唯一構建、原生四按鈕正反向焦點、正常退出和停機數據子集已獲根接受（E135）：523 資源／673 事件／3 命令及全部業務記錄嚴格不變，僅三項頁面選擇變化。027 原文字作品純鍵盤導出及同號重開的有限接受保留；完整 AC 和 M0—M6 不提高。[本次進度](2026-09-15-ver2-4-028-workbench-keyboard-progress.md)

以下 E132／E133 及更早記錄保留形成時原文。

**最新鍵盤任務進展（2026-09-15）**：固定公司簽名候選為 Ver2.4（027）。最小鍵盤屬性修復、75 項前端回歸和 Safari 組件子集已有證據（E132）；原生文字原作品導出成功並從隊列重開同號記錄，停機讀回與該原生鍵盤任務子集已獲根接受（E133）。完整 AC-23／AC-25／AC-26 與 M0—M6 不提高。[本次進度](2026-09-15-ver2-4-027-keyboard-progress.md)

以下 E130／E131 及更早記錄保留形成時原文。

**最新導出恢復進展（2026-09-14）**：固定公司簽名候選仍為 Ver2.4（026），本輪未修改產品或重新構建。登記故障相關測試與合法獨立恢復已完成（E130）；一次文字修訂版 3 完整導出包待覈實後同號成功，原生與保護有限子集已接受（E131）。完整 AC-23／AC-27 和 M0—M6 不提高。[本次進度](2026-09-14-ver2-4-026-export-recovery-progress.md)

以下 E128／E129 及更早記錄保留形成時原文。

**最新狀態（2026-09-14）**：固定公司簽名候選已更新為 Ver2.4（026）。首次修訂讀取焦點補救、41 項相關回歸、Safari 對照和唯一簽名包已接受（E128）。一次同包原生首開／重開焦點、關閉回入口和保存字幕讀取，以及退出保護的有限子集已接受（E129）。完整鍵盤、舊 020 空白及全部 WP／AC／M 階段狀態保持。[026執行進度](2026-09-14-ver2-4-026-progress.md)

啓動口徑說明：1.1 的 3 秒目標是已安裝環境、常規數據規模下的主窗口“初次可見”，驗證方法為 20 次獨立冷啓動，不計首次模型下載。完整就緒是另一項觀測；024／025 單輪完整就緒超過 3 秒不能直接判作初顯失敗。011 初顯 20/20 與舊完整就緒波動記錄分別保留，本輪沒有新的 20 次初顯驗收。 [原需求第118行](../01-product-requirements.md)

以下 E127 及更早入口保留形成時原文；其中完整就緒與 3 秒的比較須按上方口徑區分。

**最新入口（2026-09-14）**：固定公司簽名候選仍為 Ver2.4（025）。已通過正式恢復建立可直接使用的新獨立庫（E126）；同包原生讀到當前字幕版 4／父版 3、200 條／16000 字符，關閉回入口、Enter 重開及臨時編輯的繼續核對／明確放棄有限子集成立（E127）。首次 E125 來源失敗保留；完整鍵盤、020 空白及完整 AC／M0—M6 不提高。[025執行進度](2026-09-14-ver2-4-025-progress.md)

以下 E124／E125 概述保留形成時原文。

**當前入口（2026-09-14）**：固定公司簽名候選為 Ver2.4（025）。E124 的入口回焦修復、36 項相關測試、Safari 對照與唯一公司簽名包已接受。E125 原生因恢復來源錯誤未進入保存字幕及編輯，僅錯誤彈窗回焦、Enter 重開與保護恢復成立，不能記為完整原生通過；單次宿主完整就緒約 5.055 秒仍超過 3 秒。舊證據及全部 WP／AC／M 階段狀態保持。[025執行進度](2026-09-14-ver2-4-025-progress.md)

以下 024 概述保留形成時原文，其中“本輪”與“當前”指當時批次。

更新日期：2026-09-14（當前固定簽名候選為 Ver2.4（024）；靜態索引、測試與簽名包已接受；單次完整就緒仍超過 3 秒，原生診斷有限子集已接受、完整性能未簽）。責任人：總負責人；初版審計由 control_m3 子代理完成。依據為凍結 1.1 設計、已選[Ver2組合](2026-09-10-ver2-scope.md)和逐項實際報告；本表不是版本發佈簽署。初版審計快照繼續保留在[manifest](../../../../.artifacts/implementation-audit-20260910/manifest.json)，後續證據從 E20 起逐項補充。

**本輪結論：024 靜態導入索引、相關測試與唯一公司簽名包已接受（E121）；一次原生診斷與保護恢復有限子集已接受（E122），完整就緒約 3.938 秒，仍超過 3 秒。** 離線導入有中位收益，但不把兩個版本各一輪的全部差值歸因於索引，也不能解釋舊 011 的 45 秒長尾。020 偶發空白、完整鍵盤及完整 AC／M0—M6 仍待驗。見[024執行進度](2026-09-14-ver2-4-024-progress.md)；023 分段及更早結果保持歷史歸屬。

**017 歷史結論：017 簽名包、圖片／項目切換及普通歷史 v2 導出與保護有限子集已接受（E107—E109）；故障窗口失敗，導出中性提示原生、完整已發佈包補登記成功、完整 AC 和 M0—M6 仍未完成。** 中性待覈實提示窄修、83 項控制服務／28 項前端相關測試、唯一構建、整包與凍結來源核驗完成（E107）。首次來源審查因環境缺 PyInstaller 退出 1，尚未讀取源碼／PYZ；保持腳本原字節、改用既有打包環境後補充執行通過，原失敗保留。016 兩項導出修復與 A／B 原生子集保留 E104—E106 歷史歸屬：非最新 v2 保持、空 final 覈實後同號失敗、首次 SQL 退出 1 及離線投影修正均不回寫；26 項業務仍按 17 項重算加 9 項原現場沿用，13 項原生觀察與 72 份原件分別有證據。015 佈局／圖片仍歸 E101—E103。

011 原生窄窗口、獨立空庫與正常工作台初顯 20/20 最遲 3 秒內可見的歷史結果保留（E90—E94），不歸為 017 新測。初顯接受幀只證明可見時間上界，不計算其中位數或 p95。011 完整就緒中位 8.197 秒、p95 16.435 秒、最長 45.102 秒仍明顯波動；原九項及 S／E 最終保護狀態見 E94，原件不改寫。

舊質量失敗和舊完整就緒口徑的失敗記錄不變：003 正式 20 輪仍超過 3 秒；004 新訂單 LoRA 同題基線 4/32、候選 7/32，業務淨增 1 且回歸降 1，仍未登記，兩輪各自預算已用完。014 配方查看／載入、模型差異和收藏重開屬於 E99—E100 的歷史驗收；014 和 015 佈局批零模型運行，後續 E103 新增一次圖片生成保存。30 組快速採樣只覆蓋 1.338 秒提交等待，真實運行階段位於 16.673 秒採樣空檔；該批四項原生觀察保持 null，不回寫舊結論。017 已另獲運行中只讀及項目切換有限時序接受（E108），但從乙運行幀結束到首有效甲幀結束的 9.445 秒觀察窗口未達 3 秒目標，不能等同於已定位的 App 切換耗時；20.610 秒與 28.223 秒採樣缺口不能證明全程連續停留。016 普通失敗重開已通過 E105，非最新 v2 保持及空 final 待覈實後同號失敗通過 E106；完整包補登記成功仍未驗。016 的“文件已發佈”提示在 B1 中不準確；017 中性提示的源碼、相關測試與簽名包已接受；E109 點擊晚於窗口 70 毫秒、watcher 退出 3 且 0 mkdir，pending／reconciled 保持 null，中性提示原生仍未覆蓋。25 項純窗口決策測試僅為準備，本輪不再重試、不增加預算。014的03既有文字修訂長行右裁和按鈕標籤不可見，由015現有樣本佈局復驗關閉；設備差異、指定 NVIDIA、實際跨主機、乾淨安裝、遲到舊請求原生、五名首次用戶和完整 AC／全階段簽署仍缺證據。018 修復見[018執行進度](2026-09-13-ver2-4-018-progress.md)，[017記錄](2026-09-13-ver2-4-017-progress.md)，[016記錄](2026-09-13-ver2-4-016-progress.md)、[015記錄](2026-09-13-ver2-4-015-progress.md)、[014記錄](2026-09-13-ver2-4-014-progress.md)保留原文。

當前靜止雙向結果：018 另一新生命週期的一次啓動、兩次既有項目切換，獨審確認甲→乙 0.874 秒、乙→甲 0.846 秒的完整圖文觀察上界，第三幀均再次確認；包含選擇與採集開銷，不是純 App 加載耗時。零新業務與模型運行，唯一停機讀回零業務及設置變化；僅補足本次靜止雙向三秒子集，不簽完整 AC-24 或 M0—M6。[第二批觀察及獨審](2026-09-13-ver2-4-018-progress.md#静止双向切换补测第二批)

上一批歷史記錄保留：018 同包新增一次啓動、兩次靜止項目切換觀察：乙→甲在 0.822 秒觀察上界內取得正確項目、完整界面與既有正文；甲→乙因 AX／截圖過渡不一致及 19.813 秒採樣空檔，既不判三秒通過，也不據此判 App 慢。沒有新任務、模型運行、保存或導出，停機唯一讀回業務與設置零差；完整 AC-24 和 M0—M6 未簽署。[本次計時與邊界](2026-09-13-ver2-4-018-progress.md#项目切换计时观察)、[獨立復核](../../../../.artifacts/project-switch-timing-ver2-4-018-v1/independent-review-001/REVIEW.md)

1.1 文檔頁首“真實產品開發尚未開始”是 2026-09-09 的設計基線狀態。本報告記錄之後的實現，不改寫基線、舊實驗計劃或失敗結論。下表的“通過”只適用於列明的設備、模型、源碼和證據層級；中間 App、開發瀏覽器、合同夾具、真實模型及最終候選包分別取證。

<a id="一总目标与阶段退出"></a>

## 一、總目標與階段退出

| 階段 | 當前真實進展 | 尚未滿足的退出條件 |
| --- | --- | --- |
| M0 | Apple 本機訓練／推理、同機適配器獨立加載和 TV-02 中間簽名包已有證據 | TV-01 的 NVIDIA 子集、TV-03 同一份 NVIDIA LoRA 到 Apple；首期精確組合與成本重估簽署 |
| M1 | 項目／草稿、資源清單、信任計劃、持久化、任務控制、事務、冪等、基礎備份已有證據；011 原生窄窗口及有條件鍵盤路徑通過（E92）；012 兩項目四草稿恢復通過（E96）；013 六入口續做、手選舊任務及正常重開、唯一新生成保存歸甲通過（E98）；014 四類來源草稿與重開恢復通過，終態過時提示已有源碼修復（E99—E100）；017 圖片運行中只讀與跨項目返回保存的有限子集通過（E108） | 逐項 GATE-M1 和最終包簽署；3 秒切離目標未達、採樣非連續，其餘對象及終態提示路徑仍需原生補驗 |
| M2 | 固定 Apple MLX 真實生成、取消、配方重載、新生成參數與 KV 對照；官方準備→真實結果→保存已完成 ；035 Apple 參數／預設與同庫重開有限子集通過（E145）| 指定 NVIDIA／遠端執行與其異常流程、其餘 M2 子集繼續；5 名首次使用者完整乾淨安裝驗收歸 M6 獨立門檻，不作 M2 條件 |
| M3 | SFT LoRA、監督配方、暫停／繼續／新進程恢復、評測拒絕門禁、AI 正向、導出均有真實證據；004包內新數據192步訓練及獨立評測完成，4/32→7/32仍失敗（E56） | 真實達標候選的登記→試用→導出；AC-26 同份產物跨端產品鏈 |
| M4 | 圖片／視頻／TTS、圖片 LoRA、兩輪真實工作流、第三輪復用失效和受控市場 UI 已跑通 | 選定媒體質量、人工作品評審、最終包回歸；當前 TTS 不等於音頻訓練已實現，SVD 生成不等於視頻訓練已實現 |
| M5 | 固定 MLX 4-bit 權重量化、原權重與量化獨立質量比較、失敗准入及報告導出已驗；本版組合已凍結 | 已選量化質量失敗；不能因管線正確而簽署質量通過，額外方法按範圍表明確未開放 |
| M6 | 003同包更新／回滾、原生遷移／完整恢復、十二項導出及限定使用已有；005指定原生子項（E58—E63）、007故障回連與保存提示（E76—E77）、011窄窗口與獨立空庫（E92—E93）通過；011初顯20/20（E94）、012恢復庫遷移與兩輪重開（E96）、013及014同一R庫正常退出與19項原庫保護恢復（E98、E100）通過。015現有三類修訂佈局及文字短窗通過，一次App正常退出、19項保護恢復和guard002實際退出0（E101—E102）；016當前修訂失敗重開、已有v3後仍導出v2成功、空final待覈實後同號失敗及保護恢復通過（E104—E106）；017 普通歷史 v2 導出及原 19 項／選擇器保護恢復有限接受（E109） | 中性提示原生仍未覆蓋；乾淨安裝、遲到舊請求等其餘原生路徑、完整就緒波動定位、5名首次用戶及完整AC簽署；015未測完整鍵盤路徑或極限樣本，舊完整就緒失敗保留 |

<a id="二三类清单"></a>

## 二、三類清單

<a id="a-必须继续实现或集成的软件"></a>

### A. 必須繼續實現或集成的軟件

| 項目 | 現狀與明確缺口 | 可驗證的下一步 |
| --- | --- | --- |
| 分類續做與運行中界面狀態（WP-04、AC-02） | 013 六入口續做、手選舊任務與正常重開通過（E97—E98）；014 源碼已修復終態過時離開提示（E99）；015 普通圖片終態預覽、保存與同乙歸屬通過（E103）；017 圖片運行中只讀、首有效甲早於收集、終態後甲樣本及返回乙保存已接受（E108） | E103 漏採原件保留；E108 首有效甲延遲 9.445 秒，3 秒目標未達，20.610／28.223 秒缺口不證明連續全程，完整 AC-01/02 未簽 |
| 作品配方與既有修訂佈局（AC-16） | 014 原配方查看、四類普通草稿復用、模型差異與收藏重開子集通過（E99—E100）；015 兩處局部修復後，現有文字、配音文案、字幕的正文／完整差異、編輯後取消及文字短窗按鈕顯示通過（E101—E102）；020 字符計數修復、33 項相關測試、開發瀏覽器和簽名包已接受（E113）；020 邊界保存、重開、父版和原媒體播放有限子集通過（E114） | 設備差異、完整AC-16繼續；015沒有新修訂保存、導出或播放，短窗僅文字，完整鍵盤仍未驗，020 長列表大幅滾動兩幀空白未解，完整長列表渲染未簽 |
| 導出異常恢復與所選修訂保持（AC-16、AC-27） | 016 修復及原生子集保留（E104—E106）：當前修訂失敗重開、非最新 v2 保持、空 final 覈實後同號失敗且文件不變。017 中性提示、83／28 項相關測試及唯一簽名包已接受（E107）；普通歷史 v2 導出及保護恢復有限接受（E109） | E109 故障窗口失敗，pending／reconciled 為 null；中性提示原生復驗、完整已發佈包補登記成功和整個 AC-16／27 仍未驗 |
| 首期遠程／NVIDIA 執行（WP-08、WP-10） | 003 回環目標／默認位置／鑰匙串重連／200B 傳輸已有（E54）；HTTPS 與固定公開 CA 已納入 005，原生未知 CA 拒絕、目標佈局和禁用傳輸通過（E62） | 實際跨主機受信證書連接、指定 NVIDIA 機器真實加載／訓練／推理仍需驗收；本機協議及證書負例不證明 NVIDIA 就緒 |
| 權重量化正式質量比較（WP-14、WP-24） | 已支持原權重→本產品量化產物、首次方案綁定、來源／全部文件檢查、獨立進程比較和量化候選登記。真實 16 題候選未達標，API 409 拒絕且 UI 禁用，11 文件報告導出與原文件一致（E22）；[只讀失敗診斷](../../../../.artifacts/m5-quantization-quality/failure-diagnosis-20260911-v1/诊断说明.md)確認6項失敗含4項輸出約束與2項內容錯誤，未新跑模型或改變原計分 | 最終包重復驗收。當前只通過管線和拒絕門禁，不能登記或宣稱該量化模型質量合格 |
| 運行參數與預設最後集成（WP-11） | 生成參數已有真實 HTTP／worker；005 訓練表單按執行位置讀取版本化範圍，原生越界保留、中文錯誤與修正後保存通過（E57、E59、E63）；多輪裁剪和當前 Qwen 思考開關未開放 | 新關係集成後再核表單→快照→實際參數；原生參數保存不是設備／數據檢查或訓練質量通過 |
| 數據來源分組與派生版本（PRD-004、WP-12） | 已按[最小完整計劃](../../../../.artifacts/m3-dataset-split-gap-20260911-v1/最小完整实现计划.md)實現CPU檢查、預覽／明確應用、兩個純messages版本、獨立證明、訓練關係、v4與恢復導出清理；源碼／開發瀏覽器E64—E67、006包內E70—E71及普通原生恢復／應用／草稿／導出／重啓E72通過，005實際拒絕v4 | 本次原生不加載模型訓練；原件和舊質量實驗保持。語義近似去重及validation loss未執行；其他故障路徑單獨驗收 |
| M5 額外方法與適配（WP-15、WP-16b、WP-17、WP-23—27） | 本輪 M5 選擇固定 MLX 4-bit；其他額外方法與設備未選入，理由和未開放範圍已記入組合表 | 保持界面不可啓動未實現入口；首期 NVIDIA、已選質量失敗和 M6 必需項不因範圍選擇取消 |
| 安裝更新交付（WP-29c） | 固定路徑更新工具49項通過；001真實SIGKILL→recover已有（E34），003完整升級→回滾→新計劃再次安裝和獨立讀回通過（E45），原生舊庫1→3遷移及原內容保持已覈實（E49）；恢復、十二項新導出及限定獨立使用見E51—E53，恢復庫重啓後目標與草稿延續見E54 | 005成功切庫及同庫重啓已驗（E60、E63）；007指定GUI失敗回連和空庫修復遷移通過（E76）。繼續乾淨安裝與其餘原生路徑；舊包不能自動降級數據庫 |
| 含導出任務的完整備份 | 001的合法export空配置缺陷已修復並獨審（E36）；003完整主庫備份733文件／9.35GB成功（E44），原生恢復後原業務與732數據文件保持，十二項新導出和限定獨立使用通過（E51—E53）；同一恢復庫正常重啓後項目默認、兩份草稿和目標連接延續通過（E54） | 005已自動切入新庫並保持重啓（E60）；007兩種失敗切庫回連通過（E76），其餘原生路徑繼續；003手工繞行記錄保持 |
| 環境顯式重新探測 | 舊版緩存缺陷及切換交疊已修復；27文件206項前端、20項控制定向和控制目錄620項回歸通過（E39）。003原生首次四類可用，一次明確刷新時按鈕互斥，完成後仍四類可用（E48）；005 增加會話探測結果與診斷記錄，原生 3902B 診斷 ZIP 通過（E61） | 普通讀取保留緩存，刷新不重載項目或未保存輸入；副本路徑90秒失敗單獨保留，原因尚未確定 |
| 發佈矩陣與用戶材料（WP-30） | [使用手冊](../USER_GUIDE.zh-CN.md)、[組合範圍](2026-09-10-ver2-scope.md)和本矩陣已編寫；原型／設計基線保留 | 凍結候選源碼、依賴、簽名／包摘要後補最終安裝更新說明與 AC-01—27 簽署，不能僅留測試數量 |

代碼依據：[文本組合檢查](../../../../services/control/ailab_control/service.py)、[能力與參數接口](../../../../services/control/ailab_control/api.py)、[固定量化](../../../../services/control/ailab_control/conversion.py)、[適配器評測與准入](../../../../services/control/ailab_control/evaluation.py)、[執行器目錄](../../../../workers)、[版本化遷移](../../../../services/control/ailab_control/migrations.py)。這些是審計時間點的範圍判斷，後續源碼變更需要刷新證據。

<a id="b-需要新实验额外设备或人工验收"></a>

### B. 需要新實驗、額外設備或人工驗收

| 條件 | 必須保留的邊界 |
| --- | --- |
| 新的本機 LoRA 正向質量實驗 | 原128步候選6/8及舊訂單v2的192步、基線／候選均5/32、業務淨增0繼續保留為失敗。新訂單v3只改變數據，64訓練／32離線審閱／32留出與原模型、MLX、參數、192步和四類門檻預先凍結並獨審；004包內一次實際訓練後，同一新32題基線4/32、候選7/32，業務淨增1低於2且回歸降1，仍不准入（E56）。兩套32題不能橫比5/32與7/32；兩輪各自預算均已用完，不追加、挑檢查點或用已曝光留出調參 |
| 指定 NVIDIA Linux 設備 | TV-01、TV-03、AC-26 必需。003回環原生子項已驗；HTTPS已納入004簽名包，實際跨主機與公開證書接入未驗。真實CUDA加載、資源釋放和同份訓練產物回程均缺硬件證據，不能用本機另一份LoRA代替 |
| AMD／Intel／相應 NPU | 只有本版實際選入的組合需要相應硬件驗收；Apple／Kokoro CPU 結果不能繼承到 ROCm、SYCL 或 OpenVINO |
| 圖片／視頻／音頻人工質量評審 | 圖片 LoRA 固定顏色／結構質量失敗；SVD 兩秒視頻幾乎靜止；TTS 波形、解碼及字節一致不代替聽評。需要固定樣例與逐項審查，既有失敗不刪 |
| 乾淨安裝環境 | 獨立乾淨賬戶或適用 VM 等需具備安裝條件；空 cwd、最小 PATH、獨立數據目錄只能證明各自隔離範圍，不能稱乾淨機器安裝通過 |
| AC-25 的 5 名目標用戶 | 每人用同一最終候選包，從零模型／項目／數據／歷史完成首次結果、保存與重啓繼續，記錄耗時、阻塞和幫助。[驗收材料與空白記錄表](2026-09-11-first-user-acceptance-kit.md)已準備；代理／開發者預演不能代替 |
| 最終 GUI 與非功能驗收 | 011 原生四種寬度 × 深淺色、設置／導入彈窗、隱藏重開和有條件鍵盤路徑通過（E92），獨立空庫入口通過（E93）。011 初顯 20/20 正文最遲 3 秒內可見及逐輪正常退出通過（E94）；完整就緒中位 8.197 秒、p95 16.435 秒、最大 45.102 秒，仍明顯波動。保留系統緩存，初顯只給上界；大庫、其餘交互及性能簽署另驗，003 舊完整就緒失敗保持 |
| 分發與公證 | 當前 Apple Distribution 組織簽名只支持已證實的本機候選結論；具體分發渠道、適用簽名／公證和獨立安裝另驗。準備包不等於已對外發佈 |

<a id="c-已取得的真实验证结果"></a>

### C. 已取得的真實驗證結果

| 編號 | 真實結果 | 證據與界限 |
| --- | --- | --- |
| E01 | MLX 生成、SFT LoRA 及保存／重啓持久化 | [控制真實試跑](../../../../.artifacts/control/real-smoke/real-smoke-report.json)；功能證據，不是質量通過 |
| E02 | 同一適配器獨立加載；4-bit／64／affine 權重量化輸出可加載 | [模型技術報告](../../../../.artifacts/m0-mlx/m3-20260910-01/report.json)；原權重不變，量化質量未准入 |
| E03 | 界面量化、保存實驗模型、試用、13 文件導出，移位後內置執行器實際回答 `12` | [UI 與導出](../../../../.artifacts/frontend/real-ui-20260910/quantization-and-export.json)、[獨立使用](../../../../.artifacts/frontend/real-ui-20260910/quantized-model-independent/report.json)；中間包，不是最終包 |
| E04 | 連續訓練／同進程暫停繼續／新進程恢復：最終權重最大差 0.0，損失逐值一致 | [12 步軌跡](../../../../.artifacts/m3-checkpoints/real-20260910-01/report.json)、[正式 UI 暫停與恢復](../../../../.artifacts/frontend/real-ui-20260910/checkpoint-ui-report.json)；不修改質量實驗預算 |
| E05 | 真實失敗評測被拒絕登記，原 128 步質量失敗保留 | [預定實驗](../../../../.artifacts/m0-mlx/evaluation-20260910-01/summary.json)、[UI 事後評測與報告導出](../../../../.artifacts/frontend/real-ui-20260910/evaluation-and-export.json)；此項通過的是門禁和導出，不是候選質量 |
| E06 | 三組不同字段值的真實 AI 建議解析、應用、撤銷；普通 UI 128→64→128，目標任務零計算 | [原始回答交叉驗證](../../../../.artifacts/m3-ai/structured-positive-20260910-v1/source-verification.json)、[AI UI](../../../../.artifacts/frontend/real-ui-20260910/ai-ui-evidence.json)；僅本地固定模型組合 |
| E07 | KV 功能／性能／質量／隔離與取消按凍結計劃執行；低內存 v2 沒有新增質量回退 | [完整驗收](../../adapters/mlx_text/PRESETS_ACCEPTANCE.md)、[摘要](../../../../.artifacts/m2-kv/summary.json)；194 次模型進程觀察含 4 次取消，不是 194 次質量通過。原 q4 KV No-Go 保留，不能與 q4 權重混同；無普遍加速承諾 |
| E08 | 新生成字段共 24 次真實執行或拒絕觀察；流式／非流式同最終文本，停止序列跨塊正確，邊界預算和身份改變被拒 | [驗收](../../adapters/mlx_text/GENERATION_ACCEPTANCE.md)、[摘要](../../../../.artifacts/m2-generation/summary.json)；兩種固定 Qwen 權重、單 prompt。CPU MLX 187 項、控制 538 項當時通過；非流式真實取消在 Prefill，Decode 取消另有 CPU 合同 |
| E09 | 圖片生成、12 步 LoRA 更新及獨立重載；媒體控制執行橋通過 | [圖片驗收](../../../../.artifacts/m4-media/acceptance-v2/acceptance.json)、[媒體橋](../../../../.artifacts/m4-media/bridge-acceptance-v2/acceptance.json)；圖片質量未通過 |
| E10 | 兩個獨立視頻進程輸出相同 14 幀／7 FPS／2 秒 MP4 | [視頻復跑與視檢](../../../../.artifacts/m4-media/video-repeat-and-visual-review.json)；主體近靜止，運動質量 No-Go；實際步驟取消另有媒體橋證據 |
| E11 | Kokoro 中文配音兩個獨立 CPU 進程輸出同字節、24 kHz PCM16 WAV | [TTS 驗證](../../../../.artifacts/m4-media/tts/real-verification.json)；沒有人工聽評准入 |
| E12 | 兩輪正式 UI 圖片→視頻→配音共 6 次獨立計算，各保存 3 項作品 | [兩輪摘要](../../../../.artifacts/frontend/real-ui-20260910/two-workflow-runs-summary.json)；三項作品分別保存，沒有合成成片，不宣稱質量達標 |
| E13 | 第三輪明確復用三項結果；修改上游後下游過期，舊結果／產物不變，新增計算 0 | [明確復用](../../../../.artifacts/frontend/real-ui-20260910/workflow-third-reused-complete.json)、[失效核驗](../../../../.artifacts/frontend/real-ui-20260910/workflow-third-invalidation.json) |
| E14 | 受控獨立提供方服務＋正式 UI 申請／等待／拒絕後重申、提供方批准、下載登記、返回原文本／圖片草稿；下載 11,141,120 字節取消後同編號續傳至 14,600,000 字節，前綴一致，任務不變、模型計算 0 | [UI](../../../../.artifacts/wp22-market-ui-v1/ui-report.json)、[資產與續傳](../../../../.artifacts/wp22-market-ui-v1/asset-ui-report.json)、[獨立生命週期](../../../../.artifacts/wp22-market-v3/acceptance.json)；文本原草稿先保存 steps=6，使用數據僅改原 dataset 字段；JSONL／PNG 字節與解碼已核。測試提供方，不是商業市場實際授權 |
| E15 | 中間原生 App 完整備份、隔離恢復、明確切庫、退出／重啓和恢復庫生成；原 12 個運行文件摘要一致 | [原生驗收](../../../../.artifacts/desktop/native-acceptance-20260910/report.json)；後續源碼需最終同包回歸 |
| E16 | 最新 v3 一萬任務／一百萬元信息，真實 SQLite／HTTP 首中尾頁共 360 次查詢，最慢 p95 13.938 ms；任務按最新順序分頁 | [最新分頁規模](../../../../.artifacts/desktop/storage-scale-20260910-v3/report.json)；夾具元信息，不是一百萬實際訓練文件；舊 v1 的 8.89 ms 保留為歷史值，不用於最新實現或 UI 耗時 |
| E17 | 同規模 DB 893,276,160 字節＋真實共享 JSONL 閉包，完整備份 62.42 秒、隔離恢復 73.29 秒，原庫不變、路徑歸一後記錄相同 | [備份規模](../../../../.artifacts/desktop/scale-backup-v1/report.json)；一份共享數據，不能外推百萬獨立大文件吞吐 |
| E18 | 可恢復清理經真實 UI 計劃、移動、恢復，61 字節獨立測試產物摘要不變 | [清理 UI](../../../../.artifacts/cleanup-ui-20260910/report.json)；沒有清理主工作庫或永久刪除 |
| E19 | 主開發 App 設置→範圍預覽→明確導出診斷 ZIP，4,401 字節、2 個文件；ZIP 及清單摘要驗證通過 | [診斷 UI](../../../../.artifacts/dev/diagnostics-ui-report.json)；核對 32 個原任務，沒有令牌、路徑、任務名與輸入。依賴來自已保存觀察，不冒充本次重新探測；最終包仍另驗 |
| E20 | 官方固定版本下載 999,602,607 字節，停止後同編號續傳，9 文件摘要與已保存前綴一致；明確入庫→示例草稿→真實 MLX 輸出→保存作品 | [首次使用預演](../../../../.artifacts/first-use-20260910/report.json)；新項目 1 模型／1 任務／1 生成，保存文本與原產物摘要一致。開發者預演，不代替乾淨安裝或 5 名目標用戶 |
| E21 | 正文、音頻腳本、視頻字幕三類實際修訂至第二版，分別導出 4 文件，原版可查看、來源與全部摘要核對 | [修訂與導出](../../../../.artifacts/work-revisions-ui-v1/report.json)；新增僅 3 次導出，無新模型計算；腳本未重合成語音，字幕為外置 VTT，原媒體不變 |
| E22 | 原權重與新 4-bit 候選按預定 16 題獨立評測；基線 11/16、候選 10/16，業務／格式 2/4 不達 75%，登記 API 409；正式 UI 展示16題、禁用登記、11文件報告導出再核通過 | [真實運行補核](../../../../.artifacts/m5-quantization-quality/real-20260910-v1/completion.json)、[界面及導出](../../../../.artifacts/m5-quantization-quality/ui-v1/report.json)、[驗收說明](../../adapters/mlx_text/MODEL_QUALITY_ACCEPTANCE.md)；候選仍 experimental、登記數0。原腳本末尾誤檢 HF 緩存的失敗報告保留；獨立補核未重跑模型或改規則 |
| E23 | 8組寬度／主題，168項檢查和76張原始截圖；鍵盤創建項目、輸入正文和新生成參數、保存 revision2 到真實 SQLite，計算0次；彈窗焦點循環和返回已修復復驗 | [界面驗收](../../../../.artifacts/ac23-responsive/cua-v1/验收报告.md)；正式React開發瀏覽器，最終包和新成員復跑另驗 |
| E24 | 5類操作各20次，共100次完整交互、10次預熱；瀏覽器 EventTiming 至下次呈現中位68.5385／p95 152.796／最大233.501 ms，獨立解析110份原trace一致 | [測量報告](../../../../.artifacts/ac24-interactions/browser-v1/测量报告.md)；工具牆鐘另列，不混入 UI 耗時；小庫開發瀏覽器，不是最終原生包或異步數據完成時間 |
| E25 | 正式界面登記獨立執行服務、導入200字節SFT、預覽目標／SHA後明確傳輸；最終源碼重啓後再次傳輸，兩端共2次且每次run_count=1，2個接收文件均與原字節／SHA一致，上傳blob去重為1 | [首次實操](../../../../.artifacts/remote-product-ui/control-v1/transfer-report.json)、[最終源碼復驗](../../../../.artifacts/remote-product-ui/control-v1/transfer-current-source.json)；數據庫與WAL未發現本測試憑據。不含模型計算、不代表外網或CUDA；中斷邊界另有真實故障夾具 |
| E26 | 候選更新27項＋啓動22項，由總負責人獨立復跑49項通過；包含4處真實SIGKILL、WAL、同名進程、鎖、schema和未知路徑保護 | [獨立復跑](../../../../.artifacts/desktop/candidate-update-root-review.xml)、[腳本說明](../../scripts/desktop/README.md)；此批為腳本夾具，後續真實包替換見E34，不將兩層證據混同 |
| E27 | 獨立完成32題訂單實驗加載復核：192步最終權重16張量實際改變，評測候選文件與最終適配器一致，24題輸出改變；基線／候選仍5/32，導出原字節一致 | [只讀復核](../../../../.artifacts/m3-order-sft/read-only-audit-v1/复核说明.md)、[實驗結果](../../../../.artifacts/m3-order-sft/real-v2/结果说明.md)；加載證據不等於質量達標 |
| E28 | NVIDIA實現的固定Transformers／PEFT組件在明確CPU模式完成原權重生成、2步訓練、權重變化和逐值轉換合同；最終源碼v3再次通過 | [CPU組件v3](../../../../.artifacts/nvidia-text/cpu-components-v3/report.json)、[實現與證據](2026-09-10-remote-nvidia-evidence.md)；不是CUDA實機，也不是同一份NVIDIA訓練產物跨端驗收。正式公開入口不會回退CPU冒充NVIDIA |
| E29 | 正式界面設置項目默認執行目標後，舊本機草稿記錄未變，新草稿使用遠端；單次改回本機不改項目默認。最終源碼服務實際預檢顯示Linux／CUDA環境阻斷，列明9文件953.3MB範圍，沒有開始按鈕、模型上傳或計算 | [默認只影響新草稿](../../../../.artifacts/remote-product-ui/control-v1/default-new-only.json)、[單次覆蓋](../../../../.artifacts/remote-product-ui/control-v1/local-override.json)、[真實CUDA阻斷](../../../../.artifacts/remote-product-ui/control-v1/nvidia-ui-blocked.json)；開發瀏覽器、真實控制／執行服務，原生鑰匙串同包另驗 |
| E30 | 最終控制回歸667項＋跨目標101條分頁1項；前端26文件200項；獨立完成接收合同15項，取消／補收的原失敗現場復驗通過 | [控制](../../../../.artifacts/control/remote-integrated-final.xml)、[前端](../../../../.artifacts/frontend/full-remote-location-v6.log)、[獨立合同](../../../../.artifacts/nvidia-completion-independent-v1/recheck-v1/report.json)、[取消與補收](../../../../.artifacts/desktop/remote-product-review/fix-recheck-tests.txt)；測試合同與實際傳輸分別取證，不繼承為GPU或最終包結論 |
| E31 | 新遠端界面320／736／1024×深淺色×草稿／設置／歷史共18組，40張原圖；無橫溢，288次雙向Tab均有2px焦點環且留在彈窗內，6次Esc返回原入口，草稿和原歷史記錄不變 | [獨立CUA檢查](../../../../.artifacts/remote-product-ui/independent-cua-v1/只读验收说明.md)；只讀開發瀏覽器，未新增業務執行，不代替最終原生包 |
| E32 | Ver2.0(001)統一構建與組織簽名通過；42201文件／48鏈接探測前後相同，478個Mach-O依賴與191源碼核對通過 | [簽名包交接](../../../../.artifacts/desktop/bundle-ver2-001-handoff.json)、[封存完整驗證](../../../../.artifacts/desktop/bundle-ver2-001-verification.json)；Apple Distribution組織簽名，未公證／獨立機器分發，001另有備份缺陷，不能交付為最終包 |
| E33 | 001包控制／MLX副本在空cwd及最小PATH真實生成“4”，16題量化和32題LoRA獨立評測分數與原報告相同，登記均409；42個原輸入／報告／庫不變，9個相關PID及進程組均消失 | [運行報告](../../../../.artifacts/desktop/final-mlx-acceptance-v1/run-002/report.json)、[整包同源與釋放補核](../../../../.artifacts/desktop/final-mlx-acceptance-v1/run-002/completion-proof.json)；質量仍失敗，001文本組件證據，不替代後續候選包或原生界面。首次驗收腳本誤查構建生成空文件的失敗已保留 |
| E34 | 真實組織簽名0.1.0→001：舊包移動後注入SIGKILL，公開recover恢復舊包；另一事務完整apply後公開rollback恢復舊包，雙方包摘要／簽名及原schema1數據庫均核對一致 | [真實中斷恢復](../../../../.artifacts/desktop/final-native-v2/real-sigkill-recovery.json)、[完整升級後回滾](../../../../.artifacts/desktop/final-native-v2/successful-cycle-rollback.json)；全程未啓動App／遷移數據庫。001因另發現備份缺陷未再次安裝，固定路徑回舊版後交給002構建 |
| E35 | 在原生舊庫停寫鎖內保留47文件999802661字節完整副本及含WAL一致數據庫／選擇設置備份，逐文件相同，原庫不變 | [遷移前保護副本](../../../../.artifacts/desktop/final-native-v2/pre-migration-backup/report.json)；完整離線保護，不計作產品備份／恢復驗收 |
| E36 | 001真實備份失敗已定位並修復：僅合法export空草稿歸一，其它壞配置仍拒絕。94項導出／備份／恢復回歸、14組獨立邊界及真實庫引用集合對照通過 | [源碼差異](../../../../.artifacts/ac27-readonly-inventory-v1/backup-fix.diff)、[獨審](../../../../.artifacts/backup-export-null-review-v1/independent-fixed-review.json)、[全對象準備](../../../../.artifacts/ac27-readonly-inventory-v1/准备说明.md)；主庫733文件約9.35GB，現成舊備份不覆蓋所有對象，003尚需實操 |
| E37 | 001媒體技術批次在Kokoro探測120秒超時，6個業務子項均未開始。獨立同上限探測105.12秒自然通過；採樣顯示導入期dyld映射／簽名登記持續推進，6個Mach-O與候選字節／架構／簽名相同 | [診斷](../../../../.artifacts/desktop/final-media-acceptance-ver2-001-v1/kokoro-probe-diagnostic-v1/summary.json)；沒有調大上限，沒有媒體生成／訓練，不把單次探測成功改稱完整媒體回歸通過 |
| E38 | 舊實際App組件連續點擊3次刷新，恢復後的3個固定執行器計數均停在1，界面仍未準備；002自有構建組正常SIGTERM、退出143且進程組消失、構建鎖釋放，版本2保留失敗 | [按鈕實證](../../../../.artifacts/environment-refresh-review-v1/frontend-report.json)、[002中止](../../../../.artifacts/desktop/build-ver2-002-stopped.json)；CPU合同執行器，未執行模型。固定App仍0.1.0，002未進入前端／Tauri，暫存運行時不可交付 |
| E39 | 環境窄修後控制目錄620項、前端27文件206項全過；獨審6場景通過。最終源碼DOM→真實HTTP及總負責人瀏覽器一次點擊均恢復四類環境，三執行器各1→2次，關閉重開不重探測；0業務對象、0模型計算 | [控制與源凍結](../../../../.artifacts/environment-refresh-review-v1/source-freeze.json)、[前端回歸](../../../../.artifacts/frontend/full-environment-refresh-v2.log)、[獨立審查](../../../../.artifacts/environment-refresh-independent-v1/review-result.json)、[實際CUA回讀](../../../../.artifacts/environment-refresh-review-v1/cua-report.json)；620覆蓋前600控制項，原667另含20遠程／47NVIDIA，收集範圍[逐項比較](../../../../.artifacts/environment-refresh-review-v1/test-scope-comparison.json)無遺漏；CPU執行器僅允許探測，非GPU能力結論 |
| E40 | 003已凍結191源碼文件，較002僅版本、環境刷新前端和API的8個鏡像條目變化；完整主庫507資源／2項目靜止後，自有開發控制服務正常退出0、進程組消失、鎖釋放，六表前後一致 | [003凍結比對](../../../../.artifacts/desktop/ver2-003-source-change-review.json)、[主庫停寫回讀](../../../../.artifacts/ac27-product-backup-helper-v1/main-stopped.json)；僅是構建和備份準備，不是003包驗證或完整備份完成 |
| E41 | Ver2.0(003)公司簽名、整包實際探測和探測後不可變復核全部通過；42201文件、48鏈接、478 Mach-O與191凍結源碼核對一致。control／MLX及三個媒體profile副本均從此包逐項核對後獨立 | [正式交接](../../../../.artifacts/desktop/bundle-ver2-003-handoff.json)、[整包報告](../../../../.artifacts/desktop/bundle-ver2-003-verification.json)、[探測後復核](../../../../.artifacts/desktop/postprobe-ver2-003-tree.json)、[媒體複製回執](../../../../.artifacts/desktop/final-media-acceptance-ver2-003-v1/copy-receipt.json)；包摘要5bf9958b…91527，尚未啓動原生App／遷移，尚未公證或獨立安裝，同包模型業務繼續驗證 |
| E42 | 003控制／MLX副本在空cwd和最小PATH完成明確刷新→設備→普通能力讀取，獨立庫0業務對象；真實Apple GPU生成“4”。控制正常SIGTERM退出0、無強殺，生成PID／進程組消失，42保護文件與運行時副本不變 | [本輪報告](../../../../.artifacts/desktop/final-mlx-acceptance-v3/run-001/report.json)、[總負責人回讀](../../../../.artifacts/desktop/final-mlx-acceptance-v3/root-readback.json)；綁定003整包5bf9958b…91527，僅代表性文本生成，無新訓練或16／32題重跑，不改原質量失敗結論 |
| E43 | 003媒體副本在原120秒探測上限內通過；圖片20步、圖片LoRA12步及同份適配器獨立重載、視頻25步和TTS真實完成。視頻獨立解碼14幀／7FPS，音頻24kHz；視頻第1個真實去噪步驟取消後退出130，無完成事件，全部業務PID／進程組消失 | [本輪報告](../../../../.artifacts/desktop/final-media-acceptance-ver2-003-v1/run/report.json)、[獨立讀回](../../../../.artifacts/desktop/final-media-acceptance-ver2-003-v1/readback-report.json)；144張量、431616參數，72個LoRA up張量全部非零，11個歷史文件未改；圖片／視頻質量失敗與TTS未聽評邊界保留 |
| E44 | 003固定App內控制服務通過正式備份接口完成主庫portable備份：733文件、9345059951字節，逐文件SHA／完整閉包／數據庫六表一致。原業務表和原文件不變，控制正常退出0、PID／進程組消失、庫鎖歸還 | [完整備份回執](../../../../.artifacts/ac27-product-backup-helper-v1/main-ver2-003-retry-v2/run.json)、[候選身份](../../../../.artifacts/ac27-product-backup-helper-v1/main-ver2-003-retry-v2/candidate-identity.json)；首批驗收腳本證書參數錯誤及失敗記錄保留，修正後一批成功；未運行模型、未恢復或切庫，原生後續驗收另計 |
| E45 | 003使用公開工具實際完成0.1.0→003升級→rollback回舊版→新計劃再次安裝003；總負責人在停寫鎖內回讀固定App公司簽名／整樹、庫選擇和數據庫。原生舊庫仍schema1，原庫與完整保護副本各47文件全部相同 | [獨立讀回](../../../../.artifacts/desktop/final-native-ver2-003-v1/update-cycle-readback.json)、[首次升級回執](../../../../.artifacts/desktop/final-native-ver2-003-v1/successful-cycle-apply-receipt.json)、[回滾回執](../../../../.artifacts/desktop/final-native-ver2-003-v1/successful-cycle-rollback-receipt.json)、[最終安裝回執](../../../../.artifacts/desktop/candidate-updates/ver2-003-final-install/receipt.json)；只在固定路徑操作，舊包／候選均保留；未啓動原生App或遷移數據庫 |
| E46 | 003已核副本的真實控制入口並行探測在90.066秒返回：文本可用，圖片／視頻／音頻未準備。控制握手1.047秒，退出0、無強殺，進程組／端口／鎖釋放，空庫業務記錄與運行時不變 | [副本路徑失敗](../../../../.artifacts/startup-control-probe-ver2-003-v1/run-001/report.json)、[分段診斷](../../../../.artifacts/diagnostics/startup-probe-ver2-003-evidence-v1/诊断说明.md)；獨立暖緩存純校驗為7.630／8.304秒，不足以歸因其餘耗時；不得把副本失敗套為E48固定App的實際狀態 |
| E47 | 003控制入口對完整舊庫新副本觸發真實索引衝突，失敗回滾仍schema1且原業務／資產不變；只移測試索引後成功1→2→3。三份遷移備份實際核對、舊保護47文件不變，進程與鎖全部釋放 | [最終批次](../../../../.artifacts/migration-failure-retry-ver2-003-v1/run-002/report.json)、[獨立10項復審](../../../../.artifacts/migration-failure-retry-ver2-003-v1/independent-review-control-v1.json)；首輪輔助腳本漏讀非空WAL的失敗保留，已修輔助腳本重跑；未更改產品遷移源碼，不代替GUI故障提示 |
| E48 | 固定003首次原生啓動顯示舊項目及歷史任務，四類環境全可用；明確刷新時按鈕互斥，完成後仍全可用。正常菜單退出0，App與control均消失；嚴格首屏回執宿主15.073秒、外部23.091秒 | [單輪原始報告](../../../../.artifacts/desktop/native-startup-diagnostic-ver2-003-v1/report.json)、[環境界面](../../../../.artifacts/desktop/native-startup-diagnostic-ver2-003-v1/environment.png)、[刷新完成](../../../../.artifacts/desktop/native-startup-diagnostic-ver2-003-v1/refresh-complete.png)；該輪含原庫首次遷移，未另測主窗口初次可見的準確時刻；未達到3秒，且不冒充20輪通過。與E46路徑差異原因未定 |
| E49 | 003首次原生啓動後的原庫遷移獨立讀回通過：schema1→3，原業務行／rowid、資產與運行證據保持；兩份真實成功遷移回執及數據庫備份都屬於本次啓動時間窗，舊完整保護47文件不變 | [實際讀回](../../../../.artifacts/native-migration-readback-ver2-003-v1/run-002/report.json)、[獨立復審](../../../../.artifacts/native-migration-readback-ver2-003-v1/independent-control-review-v1.json)；只將停寫DB／WAL／SHM穩定複製後讀取副本一致視圖，原庫未打開或checkpoint；首輪保守拒非空WAL的審計記錄保留，不是產品遷移失敗 |
| E50 | 固定003在Apple M5 Max／128GiB／macOS26.6.2完成20次獨立原生啓動，20次正常UI退出且對應40個App／control PID和包內運行時均已結束；完整回執中位10.850秒、p95 11.068秒、最大11.173秒 | [20輪原始報告](../../../../.artifacts/desktop/native-startup-twenty-ver2-003-v1/report.json)、[總負責人回讀](../../../../.artifacts/desktop/native-startup-twenty-ver2-003-v1/root-readback.json)；每輪均超過3秒，性能目標未過。第一輪退出前等待解鎖，不計入已取得的回執時間；沿用既有環境與項目數據完成口徑，未改變定義，也非系統重啓／乾淨安裝 |
| E51 | 固定003普通備份恢復入口完成733文件校驗並切入獨立新庫；導出前獨立比對schema3、507對象、732個數據文件／9,327,512,687字節與原備份相符，事件、路徑轉換及舊授權清除通過 | [恢復比對](../../../../.artifacts/native-all-exports-ver2-003-v1/restore-comparison-v1/report.json)、[數據讀回](../../../../.artifacts/native-all-exports-ver2-003-v1/restore-execution-v1/data-readback.json)、[原生完成界面](../../../../.artifacts/native-all-exports-ver2-003-v1/cua/restore-outcome.png)。切庫後界面保留舊項目並報“記錄不存在”，普通下拉選新項目後恢復；此繞行不代表缺陷已修。隨後新導出與限定獨立使用見E52、E53 |
| E52 | 固定003從恢復庫普通入口完成12個新導出：原模型、4-bit模型、兩類舊LoRA、四份原作品、三份指定人工修訂及原失敗評測報告。獨立審計逐項核對導出任務／執行／版本、來源、文件集合與SHA通過；原732文件、原對象與事件不變，導出階段無模型重算 | [十二項審計](../../../../.artifacts/native-all-exports-ver2-003-v1/new-exports-audit-v1/report.json)、[原生新ID映射](../../../../.artifacts/native-all-exports-ver2-003-v1/exports-current.json)。所有新包的independent_use=not_verified原字段保留，隨後獨立使用另記E53。正常UI確認退出後App／control兩PID消失；由系統啓動，本輪沒有獨立取得退出碼，不能補記exit0 |
| E53 | 003包內執行器從新導出原模型／4-bit／舊文本LoRA各獨立生成一次，均回答“4”；七份作品及修訂完成獨立讀取或完整解碼；新導出舊圖片LoRA另配精確基座生成一張512×512圖片；原失敗評測報告讀回仍failed／eligible=false | [文本三項](../../../../.artifacts/native-text-export-use-ver2-003-v1/run-001/report.json)、[文本獨立回讀](../../../../.artifacts/native-text-export-use-ver2-003-v1/root-readback-v1.json)、[媒體獨立使用](../../../../.artifacts/native-media-export-use-ver2-003-v1/readback-summary.json)、[媒體獨立回讀](../../../../.artifacts/native-media-export-use-ver2-003-v1/root-readback-v1.json)。所有記錄進程／進程組已釋放，導出／運行時／外部基座字節不變；限定使用通過不改變原質量失敗 |
| E54 | 固定003原生目標／默認位置／鑰匙串重連／200B傳輸四階段通過：A登記與身份6項、B默認僅作用新草稿18項、C正常重啓後不重輸憑據連接15項、D單次傳輸與字節／登記來源37項；舊草稿、此前業務資源與此前遠端執行保持 | [A目標](../../../../.artifacts/native-target-audit-ver2-003-v1/native-A.json)、[B默認](../../../../.artifacts/native-target-audit-ver2-003-v1/native-B.json)、[C重連](../../../../.artifacts/native-target-audit-ver2-003-v1/native-C.json)、[D傳輸](../../../../.artifacts/native-target-audit-ver2-003-v1/native-D.json)。同一回環目標、同一恢復庫；network_remote_ready=false、nvidia_ready=false，未上傳模型或執行模型計算，不代表HTTPS／實際跨主機／CUDA通過 |
| E55 | Ver2.1(004)唯一正式完整構建exit0，公司簽名及整包驗證通過：192項凍結輸入、42,203個文件與48個鏈接；完整App實際CA摘要相符，顯式加載121個CA；同源碼Rust26項通過、2項按原標記忽略，測試後81項構建輸入保持 | [構建交付讀回](../../../../.artifacts/desktop/build-ver2-1-004-v1/readback.json)、[完整包報告](../../../../.artifacts/desktop/build-ver2-1-004-v1/bundle-verification.json)、[實際CA讀回](../../../../.artifacts/desktop/build-ver2-1-004-v1/full-app-ca-readback.json)、[總負責人13項獨審](../../../../.artifacts/integration-ver2-1-004-v1/root-built-candidate-readback.json)。合併後前端29文件246項與佈局12項已通過；本批當時未啓動004原生App；後續005原生結果另記 E60—E63 |
| E56 | 004包內控制與MLX入口完成新訂單v3的數據單變量實驗：64條全部接收、0排除、636監督token，一次192步訓練；同一新32題基線4/32、候選7/32，四類門檻均失敗，業務淨增1低於2且回歸降1，eligible=false、未登記。正式報告清單11個載荷文件／82,473字節逐項讀回一致，控制正常退出0、無強殺，記錄進程／進程組及監聽釋放 | [真實run-002](../../../../.artifacts/m3-order-sft/real-v3-packaged-004-run-002/report.json)、[原始評測](../../../../.artifacts/m3-order-sft/real-v3-packaged-004-run-002/evaluation-record.json)、[逐題規則重算](../../../../.artifacts/m3-order-sft/real-v3-packaged-004-run-002/independent-rule-readback.json)、[總負責人獨立回讀](../../../../.artifacts/m3-order-sft/real-v3-root-readback/report.json)、[實際結果獨審](../../../../.artifacts/m3-order-sft/real-v3-independent-review/run-002/独立审查结论.md)、[執行次數與清理獨審](../../../../.artifacts/m3-order-sft/real-v3-independent-review/run-002/process-cleanup/审阅说明.md)。執行流程完成不等於質量通過；沒有啓動004原生App，也不改變原量化／LoRA失敗 |
| E57 | 005 訓練參數、切庫回調及環境探測診斷完成源碼和開發瀏覽器驗證；前端 288 項通過，真實瀏覽器 48 請求／3 草稿保存／0 執行 | [源碼審查](../../../../.artifacts/integration-ver2-1-005-v1/源码审查与验收.md)；控制 701 完整回歸與後來 93 專項分別記，不相加為同輪 |
| E58 | 005 公司簽名、195 凍結輸入、42,206 文件／48 鏈接及七個簽名目標全部讀回；Rust 27 通過、2 忽略 | [獨立包與 Rust](../../../../.artifacts/desktop/build-ver2-1-005-v1/005独立包与Rust复验.md)；原構建記錄 succeeded，wrapper 退出碼未知；不是公證或獨立安裝通過 |
| E59 | 固定 005 包內三次控制服務會話驗證 12 非法遠端草稿、探測失敗／緩存／刷新、凍結診斷與舊 ZIP 字節兼容；三服務退出 0 | [真實 HTTP／CPU](../../../../.artifacts/integration-ver2-1-005-v1/packaged-http-run-001/report.json)；無模型計算，CPU 失敗夾具與真實引擎另分 |
| E60 | 005 普通原生恢復獨立 B、明確切庫，舊未保存草稿／AI 面板清除；正常退出再重開，同 B／恢復 ID／自有草稿保持 | [獨立 UI 證據審查](../../../../.artifacts/integration-ver2-1-005-v1/native-acceptance/independent-ui-review.json)；成功路徑樣本，不冒充人為遲到請求或失敗切庫原生覆蓋 |
| E61 | 005 原生預覽→選擇目錄→保存診斷 ZIP，3902 字節／2 文件完整，包含三次真實內置環境探測成功結果 | [診斷回讀](../../../../.artifacts/integration-ver2-1-005-v1/native-acceptance/native-diagnostic-readback.json)；無輸入正文／私有路徑，記錄是會話觀察，不是訓練或性能驗收 |
| E62 | 005 原生登記真實 HTTPS 公開 CLI 並拒絕未知 CA，中文提示／單欄佈局正常、傳輸入口禁用；服務正常退出 0，執行庫零文件／任務 | [目標與執行庫](../../../../.artifacts/native-https-rejection-ver2-005-v1/run-001/root-native-target-postcheck.json)；僅同 Mac 證書負例，非受信跨主機或 NVIDIA 實機；臨時憑據後續清除 |
| E63 | 005 原生切到 NVIDIA 保留越界學習率／小數 Alpha 並禁檢查；修正保存後 DB 為 1e-6／整數 8。清除測試憑據、按原字節恢復選庫，005 回 A 兩份舊草稿保持並正常退出 | [參數讀回](../../../../.artifacts/integration-ver2-1-005-v1/native-acceptance/native-training-and-final-B-readback.json)、[回 A 驗證](../../../../.artifacts/integration-ver2-1-005-v1/native-acceptance/return-to-A-final-readback.json)、[原生匯總](../../../../.artifacts/integration-ver2-1-005-v1/native-acceptance/本轮原生验收.json)；無新訓練，回 A 為測試清理，不是產品新增返回庫功能；原生退出碼未知 |
| E64 | 來源組計劃、CPU 監督檢查、明確應用及獨立訓練／驗證版本已實現；真實 HTTP 為4條接納、1條超長排除，訓練3條／驗證1條，監督與移位後監督均40。完整控制回歸778項通過，隨後同源變體／併發／兩類中途故障4項通過 | [控制總報告](../../../../.artifacts/m3-dataset-split-implementation-v1/control/final-verification.json)、[真實 CPU](../../../../.artifacts/m3-dataset-split-implementation-v1/browser-acceptance/control-http-run-001/report.json)、[持久化補充](../../../../.artifacts/m3-dataset-split-implementation-v1/control/persistence-verification.json)。93個源碼／測試輸入前後一致；4項為後續定向驗證。使用真實 tokenizer 與4字節權重清單夾具，未加載模型，不是006包內驗收 |
| E65 | ready預覽與已應用劃分的原件／子集／證明隨完整備份保留，隔離恢復後明確應用不重分詞；缺件及角色／版本／配置錯配被拒。導出逐文件核對，暫存清理失敗保留正式結果，可重試且不重復登記 | [存儲驗收](../../../../.artifacts/m3-dataset-split-implementation-v1/storage/验收说明.md)、[根讀回](../../../../.artifacts/m3-dataset-split-implementation-v1/storage/root-storage-readback.json)。129項相關回歸和最後43項有重疊，不相加；固定詞元夾具核驗真實SQLite／HTTP／文件與故障。完整數據包含7份業務文件，普通報告／適配器只帶固定關係及外部依賴；此份證據不是GUI，後續普通App結果見E72 |
| E66 | v4遷移保存一致v3數據庫副本；固定005包內控制器實際拒絕隔離v4庫，退出1、無握手／連接文件，數據庫摘要不變，進程已退出 | [005實際拒絕](../../../../.artifacts/m3-dataset-split-implementation-v1/storage/005-v4-refusal-run-002/readback.json)。沒有打開GUI或宿主工作庫，不證明舊GUI錯誤提示或006原生升級；遷移數據庫副本不替代完整資產備份 |
| E67 | 開發瀏覽器完成預覽、關閉後找回、失效後重新讀取、應用、明確選擇訓練子集並保存53步、7業務文件／20,150字節導出；最終源碼重開讀取原記錄並另建CPU預覽後取消。前端33文件351項及類型檢查通過 | [HTTP／導出](../../../../.artifacts/dataset-split-next-v1/frontend/browser-control-v2/readback.json)、[停止後獨立DB](../../../../.artifacts/dataset-split-next-v1/frontend/browser-control-v2/independent-database-readback.json)、[最終頁面](../../../../.artifacts/dataset-split-next-v1/frontend/browser-evidence/12-final-source-applied-readback.png)。訓練草稿綁定train，0模型attempt；根已視檢預覽、導出告知與窄屏動作。正式React連接獨立開發控制器，不是006原生 |
| E68 | 單次完整媒體校驗按當前打開文件身份復用別名摘要，保留逐路徑摘要、鏈接和最終身份核驗；005包純函數三組交替對照，每組Diffusers少讀440,018,320字節、Kokoro少讀425,309,360字節。桌面完整回歸124項通過 | [去重驗證](../../../../.artifacts/startup-improvement-audit-20260911-v1/单次完整校验去重验证.md)、[三組統計](../../../../.artifacts/startup-improvement-audit-20260911-v1/comparison-readback.json)、[124項回歸](../../../../.artifacts/startup-improvement-audit-20260911-v1/desktop-review-full-run-002-readback.json)。讀取量為程序邏輯字節，非物理磁盤I/O；時間有快有慢，保留緩存，不能稱顯著加速或啓動3秒通過。首版退化及版本測試夾具失敗均保留 |
| E69 | 006唯一完整構建實際退出0，版本2.2.0／6，199項凍結輸入與工作樹對應；42,214文件／48鏈接完整核對，七目標籤名通過。JS／CSS／HTML生成資產在主程序中的完整物理字節映射已驗；Rust27通過、2保留忽略，83應用輸入不變 | [構建結果](../../../../.artifacts/desktop/build-ver2-2-006-v1/build-process-result.json)、[獨立整包](../../../../.artifacts/desktop/build-ver2-2-006-v1/independent-bundle-readback.json)、[嵌入資產](../../../../.artifacts/desktop/build-ver2-2-006-v1/embedded-assets-independent-review.json)、[Rust](../../../../.artifacts/desktop/build-ver2-2-006-v1/rust-process-result.json)。Global Cybersecurity Alliance Limited／R3JK7R29AC；arm64、最低macOS26。未公證或驗證獨立機器發佈，靜態包含不等於原生呈現 |
| E70 | 固定006包內控制器與分詞入口實際執行新7條原件：6接納／1排除、5來源組、train5條4組／validation1條1組，監督與移位後監督均60；同源兩條均在train，同／異鍵應用不重復，原件和12個引用文件逐項核對 | [實際包內CPU報告](../../../../.artifacts/m3-dataset-split-implementation-v1/browser-acceptance/packaged-006-cpu-http-run-001/report.json)、[已審運行器](../../../../.artifacts/m3-dataset-split-implementation-v1/browser-acceptance/verify_packaged_006_cpu_http.py)。最小PATH、無Python覆蓋、獨立v4；控制退出0、無強殺，control及獨立checker PID／PGID消失、監聽關閉；0任務／模型attempt。使用真實tokenizer與4字節權重清單夾具，不加載模型，不是訓練或原生驗收 |
| E71 | 固定006包內真實CPU預覽後，正式16文件完整備份恢復；新源測試庫移開、原請求路徑實際不存在時，同ready預覽明確應用成功。隨後13文件完整備份再次恢復，18項固定關係和原件／train／validation／proof保持；源測試庫原路徑及全部文件恢復 | [實際報告](../../../../.artifacts/m3-dataset-split-implementation-v1/packaged-backup-restore-v1/run-001/report.json)、[中文簡報](../../../../.artifacts/m3-dataset-split-implementation-v1/packaged-backup-restore-v1/ACCEPTANCE.zh-CN.md)、[根獨立回讀](../../../../.artifacts/m3-dataset-split-implementation-v1/docs/root-packaged-restore-readback.json)。三個control均退出0、無強殺，PID／PGID／監聽關閉；原A及selector保持。恢復庫未調用新prepare，三庫0task／attempt。真實tokenizer與4字節張量夾具；不是GUI、模型訓練或質量驗收 |
| E72 | 固定006普通原生完成七行原件CPU預覽、16文件完整備份恢復、明確切庫、找回同ready並應用、選擇訓練子集保存53步、7業務文件／21,880字節導出及同恢復庫正常重啓讀回；同源兩條均在train，18項關係保持 | [原生驗收](../../../../.artifacts/m3-dataset-split-implementation-v1/native-acceptance/原生来源组验收-003.md)、[獨立文件核對](../../../../.artifacts/m3-dataset-split-implementation-v1/native-acceptance/native-applied-export-readback-003.json)、[重啓後根讀回](../../../../.artifacts/m3-dataset-split-implementation-v1/native-acceptance/root-reopened-readback-003.json)。真實tokenizer配四字節張量夾具；0模型attempt，另1次成功export。附屬manifest另核，共8個導出文件。兩次原生確認退出後進程組／端口消失，退出碼未知；原selector按原字節還原、原A仍v3且SHA不變，006未回A重開。不是模型訓練、質量或啓動性能通過 |
| E73 | 保存訓練子集草稿後清除過期提示；已知遷移失敗返回有界狀態並先保存原異常。六文件精確集成，前端353項與類型檢查、控制789項實際通過；候選日誌丟失紅測及修復記錄保留 | [007執行進度](2026-09-11-ver2-2-007-progress.md)、[集成記錄](../../../../.artifacts/integration-ver2-2-007-v1/integration-manifest.json)、[根回歸讀回](../../../../.artifacts/integration-ver2-2-007-v1/root-regression-readback.json)。源碼與候選控制模塊證據，不是原生提示通過 |
| E74 | 007唯一完整構建實際退出0，2.2.0／7；42,214文件／48鏈接與清單一致，七目標籤名均為指定公司；JS／CSS／HTML完整物理嵌入已核。默認Rust31通過、3忽略，另行顯式兩項真實控制用例通過；199凍結輸入及包內來源核對、83應用輸入保持 | [構建結果](../../../../.artifacts/desktop/build-ver2-2-007-v1/build-process-result.json)、[獨立整包](../../../../.artifacts/desktop/build-ver2-2-007-v1/independent-bundle-readback.json)、[嵌入資產](../../../../.artifacts/desktop/build-ver2-2-007-v1/embedded-assets-independent-review.json)、[Rust結果](../../../../.artifacts/desktop/build-ver2-2-007-v1/rust-process-result.json)。Global Cybersecurity Alliance Limited／R3JK7R29AC，arm64、最低macOS26；[來源核對](../../../../.artifacts/desktop/build-ver2-2-007-v1/bundle-source-independent-review.json)與[真實控制用例](../../../../.artifacts/desktop/build-ver2-2-007-v1/rust-packaged-real-run-001/result.json)分開記錄；未公證或獨立安裝 |
| E75 | 固定007在最小環境中實際健康啓動、認證200／401並正常退出0；獨立schema1空庫衝突返回固定三字段失敗響應並自行退出1，原異常各一次、失敗庫字節保持、真實回滾回執及備份有效 | [包內報告](../../../../.artifacts/integration-ver2-2-007-v1/packaged-startup-run-001/report.json)、[實際調用退出](../../../../.artifacts/integration-ver2-2-007-v1/packaged-startup-run-001-wrapper.json)、[根獨立讀回](../../../../.artifacts/integration-ver2-2-007-v1/root-packaged-startup-readback.json)。兩PID／PGID均已退出、鎖可重取、連接文件撤銷；沒有模型執行或GUI操作，不代表歷史業務庫遷移或原生中文提示已驗 |
| E76 | 固定007普通原生從健康S正式恢復遷移故障空庫與修復空庫；遷移失敗中文及日誌目錄失敗均回連S，57步未保存輸入保留、參數失效後可重讀；移走本次logs障礙後修復庫成功1→2→3→4並切入，舊表單清除 | [失敗持久核對](../../../../.artifacts/integration-ver2-2-007-v1/native-run-001/control-persistent-readback-001.json)、[日誌失敗](../../../../.artifacts/integration-ver2-2-007-v1/native-run-001/logs-failure-persistent-readback-001.json)、[三段成功遷移](../../../../.artifacts/integration-ver2-2-007-v1/native-run-001/T2-migrations-offline-readback-001.json)、[原生圖文獨審](../../../../.artifacts/integration-ver2-2-007-v1/native-run-001/native-logs-notice-retry-ui-independent-review-001.json)。失敗庫及備份回執保留；專用空庫故障不等於歷史業務庫遷移，未覆蓋跨切庫遲到響應 |
| E77 | 固定007普通原生重新CPU檢查七行原件並明確應用train5／validation1，使用訓練子集時保留57步；保存後舊提醒消失，持久草稿從53／rev3／原件變為57／rev4／新訓練子集。新檢查器身份及6個原件／子集／證明實體覈實，舊ready保留，0模型attempt | [保存與文件核對](../../../../.artifacts/integration-ver2-2-007-v1/native-run-001/task-after-save-proof-readback-001.json)、[根核心讀回](../../../../.artifacts/integration-ver2-2-007-v1/native-run-001/root-native-core-readback.json)。正常GUI退出後App／control及三觀察端口消失，原生退出碼未知；[原selector與九項保護讀回](../../../../.artifacts/integration-ver2-2-007-v1/native-run-001/root-original-selection-restored.json)通過，原A／默認庫v3保持；原兩庫保護鎖釋放實際退出0。沒有新模型訓練、導出或質量實驗 |
| E78 | 008啓動環境讀取與項目讀取並行，斷連拒絕舊響應；全部數據映射展開後僅排除兩套Torch頭文件。前端365項、類型檢查、桌面124項通過；桌面跳過1模塊，媒體兩固定環境各10項實際通過，代表輸入已運行 | [008進度](2026-09-12-ver2-2-008-progress.md)、[整合清單](../../../../.artifacts/integration-ver2-2-008-v1/integration-manifest.json)。保留舊紅測和環境／夾具失敗；未改完整首屏回執定義，源碼回歸不代表啓動性能通過 |
| E79 | 008唯一build.sh退出0，外層收尾誤判版本退出1保留；獨立補檢退出0。整包21,956文件／48鏈接、2,031,749,907字節及七個指定公司簽名目標通過；來源、4個PYZ及前端嵌入已核。與007路徑差異僅移除20,258個頭文件 | [原構建](../../../../.artifacts/desktop/build-ver2-2-008-v1/build-process-result.json)、[補檢](../../../../.artifacts/desktop/build-ver2-2-008-v1/postbuild-recheck.json)、[獨立整包](../../../../.artifacts/desktop/build-ver2-2-008-v1/independent-bundle-readback.json)、[包內來源](../../../../.artifacts/desktop/build-ver2-2-008-v1/bundle-source-independent-review.json)、[嵌入](../../../../.artifacts/desktop/build-ver2-2-008-v1/embedded-assets-independent-review.json)。007完整歸檔保留；移除字節數不等於整包淨減或啓動收益，原生尚未執行 |
| E80 | 008唯一媒體批次前五項成功：中文CPU配音、圖片、12步技術LoRA、新適配器重載和14幀視頻。獨立讀回144個有限LoRA張量、72個非零up張量、視頻解碼與7.85秒非靜音WAV通過；最後真實1/25步取消出現信號量警告，整批實際退出1、未通過 | [實際退出](../../../../.artifacts/integration-ver2-2-008-v1/media-run-001-exec-result.json)、[部分產物獨立讀回](../../../../.artifacts/integration-ver2-2-008-v1/root-media-partial-readback.json)、[取消原日誌](../../../../.artifacts/integration-ver2-2-008-v1/media-run-001/video-cancel/result/executor.stderr.log)、[失敗後保護核對](../../../../.artifacts/integration-ver2-2-008-v1/media-run-001-failure-integrity.json)。有CANCELLED而無completed，取消階段退出碼未落盤、不推填130；已知進程和臨時運行時均退出／清除，原快照與庫保持，原質量失敗及訓練預算不變 |
| E81 | 媒體橋普通取消給10秒清理寬限，普通異常2秒；超時仍強殺並記錄CLI實際退出。新增5項無模型測試、43項既有媒體回歸通過，1個既有TTS模塊因缺Torch跳過 | [009進度](2026-09-12-ver2-2-009-progress.md)、[定向測試](../../../../.artifacts/integration-ver2-2-008-v1/cancel-cleanup-candidate-v1/targeted-001/result.json)、[既有回歸](../../../../.artifacts/integration-ver2-2-008-v1/cancel-cleanup-candidate-v1/existing-media-001/result.json)。舊源碼紅測實際CLI為-9、橋為130，原證據保留；不據此補造008實際CLI退出碼 |
| E82 | 009唯一構建、外層收尾、獨立整包和來源核驗均實際退出0；21,956文件／48鏈接／2,031,758,125字節、7個公司簽名目標通過。199凍結文件、276包內源碼副本、379來源聲明及4個PYZ核對一致 | [真實構建退出](../../../../.artifacts/desktop/build-ver2-2-009-v1/build-execution-result.json)、[獨立整包](../../../../.artifacts/desktop/build-ver2-2-009-v1/independent-bundle-readback.json)、[包內來源](../../../../.artifacts/desktop/build-ver2-2-009-v1/bundle-source-independent-review.json)、[來源實際退出](../../../../.artifacts/desktop/build-ver2-2-009-v1/source-review-execution-result.json)。379含control的199及其餘三runtime的180，統計口徑不冒稱新增模塊；008完整歸檔，九庫保護與舊失敗保持 |
| E83 | 009唯一正常視頻與首步取消專項實際退出0。正常橋／CLI均0，40項產物摘要匹配，1024×576／14幀／7FPS／2秒視頻可解碼；取消實際1/25步後橋／CLI均130，清理約3.123秒，無KILL或資源追蹤警告 | [專項實際退出](../../../../.artifacts/integration-ver2-2-009-v1/media-lifecycle-run-001-exec-result.json)、[CLI及前後核對](../../../../.artifacts/integration-ver2-2-009-v1/media-lifecycle-run-001-wrapper-result.json)、[進程與產物讀回](../../../../.artifacts/integration-ver2-2-009-v1/root-media-lifecycle-readback.json)。兩橋／CLI／進程組與臨時目錄已回收，九庫保護保持；未重跑訓練、圖片、音頻或質量計劃，不改008原失敗，原生仍待驗 |
| E84 | 009完成1輪原生完整就緒4.308秒、普通診斷ZIP導出與UI正常退出，App／計時器實際退出0。同control三探測均0，Kokoro耗時3.651秒。S日誌原件保全後外部checkpoint，所有表邏輯摘要不變，原任務57步／rev4／0attempt，原selector及九項保護恢復 | [原單輪報告](../../../../.artifacts/integration-ver2-2-009-v1/native-run-001/startup-round-001/report.json)、[同會話診斷](../../../../.artifacts/integration-ver2-2-009-v1/native-run-001/control-session-diagnostics-readback.json)、[持久回執和正常退出](../../../../.artifacts/integration-ver2-2-009-v1/native-run-001/root-native-quit-and-diagnostic-readback.json)、[外部日誌合併](../../../../.artifacts/integration-ver2-2-009-v1/native-run-001/safe-library-checkpoint-001.json)、[保護釋放](../../../../.artifacts/integration-ver2-2-009-v1/native-run-001/root-guard-release-readback.json)。單輪超過3秒，不代替正式20輪；外部收尾不算應用自動關閉數據庫通過，連接關閉及分段耗時正在修復 |
| E85 | 010關閉連接、後台末寫後釋放鎖、停服市場錯誤和媒體探測分段修復；控制839項、媒體50項、啓動計時器25項實際通過 | [控制回歸](../../../../.artifacts/shutdown-and-probe-stages-next-v1/control-close-tests-001/full-control-001/result.json)、[媒體回歸](../../../../.artifacts/shutdown-and-probe-stages-next-v1/probe-stage-tests-001/media-001.result.json)、[計時器回歸](../../../../.artifacts/shutdown-and-probe-stages-next-v1/startup-reader-tests-001/fixed-full-result.json)、[獨審](../../../../.artifacts/shutdown-and-probe-stages-next-v1/readonly-close-review.json)。控制有5條依賴警告；定向控制已含在839項中，舊紅測保留，完整就緒定義不變 |
| E86 | 010唯一構建、外層、獨立整包及來源核驗實際退出0；21,956文件／48鏈接／2,031,775,349字節、7個公司簽名目標通過，199凍結文件、276包內副本、379來源聲明及4個PYZ一致 | [構建實際退出](../../../../.artifacts/desktop/build-ver2-2-010-v1/build-execution-result.json)、[獨立整包](../../../../.artifacts/desktop/build-ver2-2-010-v1/independent-bundle-readback.json)、[來源](../../../../.artifacts/desktop/build-ver2-2-010-v1/bundle-source-independent-review.json)、[來源實際退出](../../../../.artifacts/desktop/build-ver2-2-010-v1/source-review-tool-result.json)、[009歸檔](../../../../.artifacts/integration-ver2-2-010-v1/archive-009-result.json)。13項保護保持；本機公司簽名不代表公證或分發驗收 |
| E87 | 010包內程序在獨立空庫真實探測、導出診斷ZIP並正常停服，實際退出0；三probe成功，Kokoro總3.313秒／引擎導入1.533秒。外部讀庫前WAL／SHM／journal均缺失，成功診斷已持久保存，0項目／任務／attempt，13項保護保持 | [實際結果](../../../../.artifacts/integration-ver2-2-010-v1/bundled-diagnostics-001/result.json)、[實際退出與保護](../../../../.artifacts/integration-ver2-2-010-v1/bundled-diagnostics-001-exec-result.json)、[010進度](2026-09-12-ver2-2-010-progress.md)。沒有外部checkpoint、手刪旁路、模型或原生啓動；010原生因鎖屏待驗，本次不代替3秒／20輪性能結論 |
| E88 | 010完成1輪原生首頁／四類環境、同會話診斷ZIP保存核對與持久succeeded、正常UI退出，App／計時器實際退出0；外部4387.758084毫秒／宿主4372.967167毫秒。三probe成功：MLX 1.418183秒、diffusers 3.097750秒、Kokoro 3.782997秒。S完整性、57步／rev4／0attempt保持，原selector與九項保護復原，guard正常退出0 | [實際單輪及UI記錄](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/startup-execution-result.json)、[完整計時](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/startup-round-001/report.json)、[同會話診斷ZIP](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/control-session-diagnostics-readback.json)、[S停機核對](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/root-S-postexit-readback.json)、[原選擇恢復](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/root-original-selection-restored.json)、[保護實際退出](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/root-guard-release-readback.json)、[持久化獨審](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/control-S-diagnostic-persistence-readback.json)、[根最終接受](../../../../.artifacts/integration-ver2-2-010-v1/native-run-001/root-native-acceptance-readback.json)。唯一持久導出與同一預覽、實際4900字節ZIP正文／清單／摘要一致；單輪仍超過3秒，不替代正式20輪；與E87空庫CLI分別記賬。S僅殘留空WAL／32768字節SHM，無非零WAL、無句柄；沒有外部checkpoint或手刪旁路，不稱旁路全部自然消失。無新模型或質量驗收 |

E53合計3次文本生成、7項讀取／解碼、1次舊圖片LoRA生成及1份原失敗報告讀回，覆蓋E52指定十二項；沒有新訓練或重跑質量計劃。文本使用最小PATH、無Python覆蓋，三次實際輸出均為2個生成token。圖片LoRA導出不含基座，另提供的精確基座14文件／1,061,888,300字節均核對SHA；在MPS、float32、20步下只生成一次。總負責人已視檢藍灰杯身、完整杯把與陰影；原生成報告的visual_review=pending保留，後續觀察另存回讀報告，原圖片／視頻質量失敗不變。音頻及其腳本修訂引用同一原WAV，未重合成、未聽評；視頻字幕為外置VTT，未重算視頻。

E54的正常重啓與未重輸憑據由原生操作、[重啓前身份](../../../../.artifacts/native-target-audit-ver2-003-v1/native-C-process-before.json)、[舊進程退出](../../../../.artifacts/native-target-audit-ver2-003-v1/native-C-process-exited.json)、[重啓後身份](../../../../.artifacts/native-target-audit-ver2-003-v1/native-C-process-after.json)及[原生重新連接](../../../../.artifacts/native-target-audit-ver2-003-v1/cua/native-C-keychain-reconnected.png)共同證明，不能只憑憑據引用仍在作結論。App／control由53904／53908變為60810／60814，舊進程、進程組與舊監聽已消失，新進程仍用同一固定包和恢復庫；正常UI退出未獨立取得退出碼，不補記exit0。原生預覽明確一份200字節文件後再開始，唯一新增執行attempt-8258e49ff03a4f488dc848d37655413f、run_count=1；操作輸入、已導入來源、執行器blob、執行器輸出、控制端輸出和已登記產物六處SHA均為81aa1651a6716eecfe6766d1bd2ac23c13d039d3524499373fc1cf36a1f0cb90，完成界面及只讀審計均通過。原A—D審計期間源文件保持；新增業務記錄僅包含已明確保存的新草稿及本次傳輸所需記錄。

004整合過程與003證據分開保留：[切庫修復獨審](../../../../.artifacts/library-switch-ui-candidate-ver2-004-v1/desktop-independent-final-review.json)通過，覆蓋切換成功清除舊界面、失敗保留原草稿及遲到舊請求不混入新庫內容；[HTTPS後端獨審](../../../../.artifacts/https-implementation-ver2-next-v1/backend-independent-control-readback-v1.json)與[前端／憑據調用獨審](../../../../.artifacts/https-implementation-ver2-next-v1/frontend-independent-desktop-review-v1.json)通過各自限定範圍。真實TLS夾具證書輪換已驗斷線／取消恢復；補收使用指定TLS錯誤注入，仍保持原執行編號且不重算。總負責人已接受[固定CA隨包機制候選](../../../../.artifacts/https-implementation-ver2-next-v1/ca-portability/handoff.json)，小型凍結探針的搬移、缺失及錯摘要驗證不代替完整App驗收。總負責人核對003原191項輸入後已合併30項候選，見[合併清單](../../../../.artifacts/integration-ver2-1-004-v1/accepted-files.json)；合併後[前端29文件246項](../../../../.artifacts/integration-ver2-1-004-v1/frontend-tests.log)與類型檢查通過。原生截圖另發現目標卡片三欄樣式擠壓執行器編號；單欄樣式窄修已完成，720／360px瀏覽器實看及12項目標組件測試通過，見[佈局修復](../../../../.artifacts/integration-ver2-1-004-v1/target-layout/report.json)。隨後Ver2.1(004)唯一完整構建、公司簽名、整包校驗及實際CA讀回通過（E55）；本批當時原生未驗，現由005成功切庫、證書拒絕與佈局實操補證（E60—E63）；跨主機受信證書與NVIDIA實機仍需後續證據。

E55簽名組織為Global Cybersecurity Alliance Limited、團隊R3JK7R29AC，證書指紋7C33B517942161311A087CE893D2F1CE9B204B44；固定App路徑與版本記錄一致。實際包內CA為240,216字節、SHA為9cc2a774b5198dcff14d9be1e66091f538975d867ce029a96bce15a55dfd730f，審計Python空SSLContext顯式加載後為121個CA；該讀回不冒充凍結控制層真實TLS握手。Rust忽略項為需要單獨實操的真實控制服務及鑰匙串條目測試，未計作通過。005現有原生證據另見E60—E63，不改寫004當時結論，也不據此改變M0—M6總狀態。

E56的[數據獨審](../../../../.artifacts/m3-order-sft/data-independent-review-v3/independent-review.json)與[運行器獨審](../../../../.artifacts/m3-order-sft/packaged-runner-v1/independent-review.json)均已完成。首批準備因API將整數規範化為浮點後的摘要預期差異，在訓練前失敗，原報告與0任務／0執行證據保留；經[最小修版增量審查](../../../../.artifacts/m3-order-sft/packaged-runner-v1/incremental-review-run-002.json)後才執行run-002，沒有第二次訓練或重置已消費預算。新32題每類8題：業務0→1、格式0→3、回歸4→3、行為0→0；四類原門檻與業務至少淨增2均未通過。唯一新增業務通過為business-03：基線在代碼圍欄內已經算對尾款285，候選去掉圍欄後符合完整JSON規則，不能據此稱算術能力提高；regression-08保留正確日期但追加禁止的說明而失分。worker記錄訓練階段至校驗並保存適配器為11.334秒，MLX峰值內存1,416,330,561字節；該時間不含前置加載，不是整條任務耗時。實際16個LoRA張量、90,112個參數均有限，8個B張量全部非零，仍不足以使本次候選達標。正式導出的independent_use=not_verified原字段不回寫；清單11個載荷文件SHA與失敗報告內容另有獨立讀回，計入manifest本身為12文件／84,235字節。數據作者知道留出答案，此次不是盲測或家族外泛化驗收；不能僅憑這次失敗歸因模型容量、步數或算法。

遷移回滾與三類 WorkRevision 的源碼、合同和實操分別保留；三類修訂開發界面與導出已閉合（E21），003隨後從恢復庫對指定第二版重新導出並獨立讀取／解碼（E52、E53），本輪沒有在003新編輯修訂。舊完整就緒計時見 [測量腳本](../../../../scripts/desktop/verify_startup.py)。003舊完整就緒口徑的正式20輪已全部完成，20輪均正常退出；完整回執中位10.850秒、p95 11.068秒、最大11.173秒，全部超過3秒。[只讀診斷與單輪採集方案](../../../../.artifacts/startup-readonly-diagnosis-ver2-1-004-v1/诊断与单轮采集.md)確認當前首頁渲染不等待環境探測就緒，但未取得主窗口初次可見的準確時刻，不能將完整回執等同全程白屏；005已真實啓動並顯示界面，但此次離散UI採樣不足以測准首次可見時刻；後續採集仍保留舊完整回執定義；原設計初次可見≤3秒須另做20次獨立測量，當前不記為通過。

上述為當時狀態；011 當前 20 輪結果見 [E94 原始報告](../../../../.artifacts/startup-initial-visible-20-ver2-2-011-v1/RESULT.zh-CN.md)，已按本批範圍完成驗收，原段結論不回寫。

<a id="d-010-初显补证与-011-当前批次"></a>

### D. 010 初顯補證與 011 當前批次

<a id="e89010-单次独立初显历史补证"></a>

#### E89：010 單次獨立初顯歷史補證

固定公司簽名 010、已安裝環境和含 1 項目的 S 庫，正常工作台正文最遲 0.813 秒可見。前後幀為 770.646750／812.313583 毫秒；保留系統緩存，屬於一次觀察的保守上界，觀察器開銷未獨立量化。正常退出後原九項及 S 主庫與任務保持，空 WAL／SHM 已不存在；此狀態只屬於該批次，不改寫 E88 或 011 的旁路記錄。[原始結果](../../../../.artifacts/startup-initial-visible-observation-v1/RESULT.zh-CN.md)、[根逐幀接受](../../../../.artifacts/startup-initial-visible-observation-v1/native-preparation/run-001/root-native-initial-visible-review.json)

<a id="e90011-窄屏源码与浏览器"></a>

#### E90：011 窄屏源碼與瀏覽器

兩處窄屏修復通過 185 項瀏覽器檢查、12 項版本配置測試和 5 項彈窗焦點測試，瀏覽器錯誤為零；69 張留存截圖未全部人工查看。原失敗證據保留，源碼證據與後續原生操作分開。[源碼接受記錄](../../../../.artifacts/narrow-window-next-v1/root-source-acceptance.json)、[011整合清單](../../../../.artifacts/integration-ver2-2-011-v1/integration-manifest.json)

<a id="e91011-唯一构建整包与来源"></a>

#### E91：011 唯一構建、整包與來源

010 已完整歸檔；同一路徑唯一構建 011，構建、外層、獨立整包和來源核驗均實際退出 0。21,956 個文件、48 個符號鏈接、2,031,775,413 字節及 7 個公司簽名目標通過；199 個凍結文件、276 個包內源碼副本、379 條來源聲明和 4 個嵌入 PYZ 核對一致，13 項保護保持。本機簽名不代表公證或獨立安裝通過。[構建實際退出](../../../../.artifacts/desktop/build-ver2-2-011-v1/build-execution-result.json)、[獨立整包](../../../../.artifacts/desktop/build-ver2-2-011-v1/independent-bundle-readback.json)、[凍結來源](../../../../.artifacts/desktop/build-ver2-2-011-v1/frozen-source-independent-review.json)、[包內來源](../../../../.artifacts/desktop/build-ver2-2-011-v1/bundle-source-independent-review.json)、[實際退出](../../../../.artifacts/desktop/build-ver2-2-011-v1/source-review-execution.json)

<a id="e92011-原生窄窗口与正常退出"></a>

#### E92：011 原生窄窗口與正常退出

真實 App 同一主窗口完成 1024／736／360／320 四種寬度 × 深淺色首頁檢查，320 寬度設置長內容可滾動到底、導入彈窗可打開，最小寬度 320、隱藏後同 PID 和窗口重開、最後恢復 1440×960。鍵盤打開、首尾循環、Esc 關閉與焦點返回在系統“鍵盤導航”開啓後通過；檢查後恢復關閉、自動外觀及關閉系統設置。寬度為 WindowServer 邏輯邊界，沒有獨立讀取 DOM 內容寬度；原生 JPEG 與可訪問性樹留在 Computer Use 會話，未另存 PNG。[原生接受](../../../../.artifacts/integration-ver2-2-011-v1/native-run-001/root-native-acceptance.json)、[操作記錄](../../../../.artifacts/integration-ver2-2-011-v1/native-run-001/root-native-ui-session.json)

App、計時器和 guard 實際退出 0，control 退出被觀察到；原九項一致，S 主庫及 57 步／修訂 4／0 次運行保持。本輪留有 0 字節 WAL 和 32768 字節 SHM，journal／connection.json 不存在，沒有外部 checkpoint 或手動清理。本輪舊完整就緒外部 6.367 秒、宿主 6.346 秒單獨保留；本批當時的空庫待辦現由 E93 補證，20 次獨立初顯待完成。[保護最終讀回](../../../../.artifacts/integration-ver2-2-011-v1/native-run-001/root-guard-release-readback.json)、[完整計時原報告](../../../../.artifacts/integration-ver2-2-011-v1/native-run-001/startup-round-001/report.json)、[011執行進度](2026-09-13-ver2-2-011-progress.md)

上述為當時狀態；011 當前 20 輪結果見 [E94 原始報告](../../../../.artifacts/startup-initial-visible-20-ver2-2-011-v1/RESULT.zh-CN.md)，已按本批範圍完成驗收，原段結論不回寫。

<a id="e93011-独立空库的原生入口与正常退出"></a>

#### E93：011 獨立空庫的原生入口與正常退出

同一 011 包在獨立恢復的 E 空庫，實看 320 寬度深淺色首頁與全局設置、深色設置下部的診斷／備份／清理、深色新建項目彈窗開關和空名禁創建；隨後恢復 1440×960、自動外觀並關閉系統設置。窗口 11126 的兩次尺寸均有 WindowServer 實際讀回；未獨立測量 DOM 寬度。App 57096 與啓動外層實際退出 0，control 57107 退出被觀察到。[原生空庫接受](../../../../.artifacts/integration-ver2-2-011-v1/native-empty-001/root-native-empty-acceptance.json)、[窗口尺寸](../../../../.artifacts/integration-ver2-2-011-v1/native-empty-001/root-window-geometry.json)、[實際退出](../../../../.artifacts/integration-ver2-2-011-v1/native-empty-001/startup-execution-result.json)

E 退出後項目、全部資源、命令、模型、數據集、任務和運行均為 0；首次啓動後主庫 SHA 從 `50f8ac36…` 變為 `e9a50a41…`，主庫 57,344 字節，空 WAL 與 32768 字節 SHM 保留，只讀核對前後穩定，不能宣稱從建庫起字節不變。S 整個 E 階段完整快照和原任務保持，原 selector 與原九項恢復。共用 guard 45165 繼續持鎖供 20 次 S 啓動，本階段退出碼為空，未宣稱釋放 0；沒有外部 checkpoint 或手動清理。E 舊完整就緒單輪外部 13.184 秒、宿主 13.154 秒，非初顯、不加入 20 輪。[E停機核對](../../../../.artifacts/integration-ver2-2-011-v1/native-empty-001/root-E-postexit.json)、[E完整計時](../../../../.artifacts/integration-ver2-2-011-v1/native-empty-001/startup-round-001/report.json)

<a id="e94011-原生初显-20-轮与最终保护释放"></a>

#### E94：011 原生初顯 20 輪與最終保護釋放

同一固定 011 包、已安裝環境、保留系統緩存與含 1 項目的 S 庫，完成 20 次獨立啓動；根逐輪實際查看的原接受圖均證明正常工作台正文最遲在 3000 毫秒內可見，20/20 通過，無重跑。每輪真實 UI 正常退出，App／觀察器／入口實際退出 0、control 確認退出，後輪在前輪停機核對後開始。3515 張 PNG、3748 個樣本、2,246,953,875 字節圖像摘要經分批獨審核對；獨審另實看六輪的接受圖及兩張遮擋圖，共 8 張，未聲稱人工看過全部圖。[逐輪圖像與結果](../../../../.artifacts/startup-initial-visible-20-ver2-2-011-v1/RESULT.zh-CN.md)、[根接受](../../../../.artifacts/startup-initial-visible-20-ver2-2-011-v1/root-native-initial-visible-acceptance.json)、[獨立復核](../../../../.artifacts/startup-initial-visible-20-ver2-2-011-v1/final-independent-review.json)

初顯接受幀僅給出保守上界，不計算初顯中位數或 p95；觀察器開銷未獨立量化，不是系統冷啓動或乾淨安裝。同批舊完整就緒中位 8.196588 秒、nearest-rank p95 16.435419 秒、最長 45.101796 秒，明顯波動仍保留。第 8、9 輪近 3 秒遮擋圖保留，用更早 frame-0028 的 956.726167／938.500542 毫秒證明正文可見；第 7 輪鎖屏、第 10 輪 CUA 管道關閉和第 20 輪 AX 外殼補查均沿原輪次完成，未以重跑覆蓋。

原選擇的 374 字節、同一 inode、權限、屬主和原九項恢復，共用 guard 45165 實際退出 0。S 主庫、57 步／修訂 4／0 次運行保持，第 1—20 輪正常退出後均無旁路；E 最終與 E93 空庫退出快照一致，業務全零、空 WAL 與 32768 字節 SHM 保留。沒有外部 checkpoint 或手動清理；E93 held 原件保持歷史狀態，最終釋放另行取證。[最終釋放與讀回](../../../../.artifacts/integration-ver2-2-011-v1/native-final-guard-001/root-final-release-readback.json)

本批關閉 011 本機初顯 20 輪及正常退出保護門檻；完整就緒波動、指定 NVIDIA、跨主機、乾淨安裝、遲到舊請求、五名首次用戶與完整 AC／M0—M6 簽署仍需繼續，舊質量失敗和兩輪已用預算不變。[011當前進度](2026-09-13-ver2-2-011-progress.md)

<a id="e-012-项目草稿与界面选择恢复"></a>

### E. 012 項目草稿與界面選擇恢復

<a id="e95012-源码测试唯一构建与公司签名"></a>

#### E95：012 源碼測試、唯一構建與公司簽名

新增按項目持久化界面選擇、草稿自動保存與退出前保存握手。前端完整 399 項和類型檢查、後端相關 78 項（2 項既有警告）、宿主相關 17 項通過；失敗的舊夾具與修復後回歸記錄分別保留。011 完整歸檔後同一路徑唯一構建 012。獨立核對 7 個公司簽名目標、21,959 個文件、48 個鏈接；204 個凍結項、279 個物理源碼副本、386 條來源聲明和 4 個嵌入 PYZ 一致。[前端](../../../../.artifacts/project-context-ver2-2-012-v1/root-frontend-regression-002/result.json)、[後端](../../../../.artifacts/project-context-ver2-2-012-v1/backend/green-002/result.json)、[宿主](../../../../.artifacts/project-context-ver2-2-012-v1/host/result.json)、[構建與包接受](../../../../.artifacts/integration-ver2-2-012-v1/root-bundle-acceptance.json)

<a id="e96012-原生四草稿两项目恢复与停机读回"></a>

#### E96：012 原生四草稿、兩項目恢復與停機讀回

通過正式恢復 API 得到新 R 庫，再由固定 012 首次啓動完成一次 3→4 遷移。根在真實原生 UI 編輯甲乙兩項目各一份語言／圖片草稿，自動保存後核對原歷史，來回切換恢復各自圖片草稿，並從任務行重新打開語言草稿。退出前選擇列表非首項甲項目圖片；正常重開後直接恢復該項目與草稿，隨後切到乙項目恢復其圖片及原結果。兩輪 App PID 36681／45761 均實際退出 0。[原生接受及截圖索引](../../../../.artifacts/project-context-ver2-2-012-v1/native-run-001/root-native-acceptance.json)

停機只讀核對 18 項全部通過：四份 Draft 精確匹配，只有三條既有任務的指定草稿字段、版本和時間變化，並新增唯一甲圖片任務；31 次運行、11 件作品、3 個修訂、所有歷史事件和六個歷史小文件保持。舊草稿首次保存補齊空的可選字段單獨記錄。原選擇的 374 字節及同一 inode 恢復，19 項保護對象一致，保護入口實際退出 0，所有產品進程停止。[停機對比](../../../../.artifacts/project-context-ver2-2-012-v1/native-run-001/post-native-readback-001/comparison.json)、[原選擇恢復](../../../../.artifacts/project-context-ver2-2-012-v1/native-run-001/root-original-selection-restored.json)、[保護退出](../../../../.artifacts/project-context-ver2-2-012-v1/native-run-001/guard-002/entry-exit.json)

本批通過 AC-01 的上述子集；沒有新計算，後台結果跨項目歸屬未補驗。AC-02 分類續做、AC-16 作品頁配方載入和其餘原有門檻繼續，012 沒有新測 20 輪性能。[012執行進度](2026-09-13-ver2-2-012-progress.md)

<a id="f-013-分类续做与正常重开"></a>

### F. 013 分類續做與正常重開

<a id="e97013-相关源码测试唯一构建与公司签名"></a>

#### E97：013 相關源碼測試、唯一構建與公司簽名

已實現按項目／類別／操作記住最近任務，分類主入口繼續上次任務，明確新建與手選舊任務分別保留選擇；運行快照關聯和界面禁用規則經過相關源碼測試。前端 10 個相關文件 95/95 及類型檢查通過；後端相關 40 項通過、32 項未選入，有 1 項既有 Starlette／AnyIO 棄用警告。不是重跑 012 的 399 項完整前端與宿主測試。[013前端](../../../../.artifacts/category-resume-ver2-3-013-v1/frontend-final-001/result.json)、[013後端](../../../../.artifacts/category-resume-ver2-3-013-v1/backend/green-001/result.json)

012 完整歸檔後同一路徑唯一構建 Ver2.3（013），實際退出 0；公司簽名、整包和凍結來源兩層獨立核驗通過，7 個簽名目標、21,959 個文件、48 個鏈接、204 個凍結項、279 個物理源碼副本、386 條來源聲明及 4 個嵌入 PYZ 一致，19 項保護對象保持。此為本機簽名包證據，未新增公證、乾淨安裝或對外發佈驗收。[013構建與包接受](../../../../.artifacts/integration-ver2-3-013-v1/root-bundle-acceptance.json)

<a id="e98013-原生六入口续做唯一生成保存及退出保护"></a>

#### E98：013 原生六入口續做、唯一生成保存及退出保護

復用 012 正式恢復的同一 R 庫，未另行恢復或遷移。乙項目文字／圖片／視頻／音頻生成及文字／圖片訓練六個主入口均續做原普通任務。甲項目明確新建唯一文字任務後，手選較早文字任務，跨圖片再回文字仍繼續所選舊任務；正常退出重開直接恢復乙音頻，切回甲後分類續做仍為較早文字任務。兩輪 App 實際退出 0。[原生接受與截圖索引](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/root-native-acceptance.json)

唯一新文字任務用固定 Qwen2.5-0.5B-Instruct／MLX／Apple GPU、128 tokens、seed 0、temperature 0、top-p 1 完成一次生成並保存甲項目作品。停機核對原 508 條資源、2 個項目、31 次原運行的全部 656 條歷史事件與 schema 保持；新增恰好 11 條資源全部歸甲（任務、運行、作品各 1，產物 6，預檢與收集各 1），81 條新事件和提交／保存作品兩個命令一致。作品完整配方與運行快照相同，六個物理產物的大小與摘要相符；根接受 21 項、JSON 獨審 34 項通過。獨審只核已生成 JSON，六個物理文件由根另行讀回。[停機對比](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/post-native-readback-001/comparison.json)、[補採命令與物理產物](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/root-supplemental-readback-001/result.json)、[34項獨審](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/independent-readback-review.json)

12／13 號原生截圖均早於運行對象創建，只證明提交等待鎖定；13 號原計劃切乙，實際被提交守衛阻止且仍在甲；14 號已終態。後端事件有完整運行狀態鏈，但不能代替實際運行中控件只讀或後台跨項目完成的原生觀察。提交攔截提示在終態後殘留，留待下一版修復。AC-01／AC-02 僅通過以上子集；AC-16 可見配方查看／載入、差異提示及收藏仍未完成。[12／13時間核對](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/ui/12-13-timing.json)、[14號採樣時間](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/ui/14-at.json)

原選擇的字節、同一 inode 及 19 項保護對象已恢復，保護入口實際退出 0，全部產品與保護進程停止。011 的初顯 20 輪、舊完整就緒波動、舊質量失敗和兩輪已用預算原樣保留；硬件、安裝、五名首次用戶和完整階段門檻不變。[原選擇恢復](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/root-original-selection-restored.json)、[保護退出](../../../../.artifacts/category-resume-ver2-3-013-v1/native-run-001/guard-001/entry-exit.json)、[013執行進度](2026-09-13-ver2-3-013-progress.md)

<a id="g-014-作品配方来源草稿与收藏重开"></a>

### G. 014 作品配方、來源草稿與收藏重開

<a id="e99014-相关源码测试唯一构建与两层独审"></a>

#### E99：014 相關源碼測試、唯一構建與兩層獨審

已增加作品頁原配方查看、明確載入普通生成草稿、來源記錄、模型／版本／摘要及設備差異提示、收藏；同時修復終態過時離開提示。前端最終 14 個相關文件 156/156 及類型檢查通過；後端配方與收藏 47 項、關聯回歸 38 項分別實際退出 0。它們是本批定向驗證，不記作完整前後端回歸，也沒有重跑宿主測試。[前端最終002](../../../../.artifacts/work-recipe-ver2-4-014-v1/frontend-final-002/result.json)、[後端47項](../../../../.artifacts/work-recipe-ver2-4-014-v1/backend-tests-001/targeted-002/result.json)、[關聯38項](../../../../.artifacts/work-recipe-ver2-4-014-v1/backend-tests-001/regression-001/result.json)

013 完整歸檔後，同一路徑唯一構建 Ver2.4（014），實際退出 0；Global Cybersecurity Alliance Limited／R3JK7R29AC 的 7 個簽名目標、21,962 個文件及 48 個鏈接核對通過。208 個凍結項含 88 個應用輸入；206 份工作樹副本對應 157 個唯一源文件，282 個包內物理源碼副本、392 條來源聲明與 4 個嵌入 PYZ 核對一致。整包和來源兩層獨審各有實際退出 0 回執，19 項保護對象保持。[凍結與整合清單](../../../../.artifacts/integration-ver2-4-014-v1/integration-manifest.json)、[構建與包接受](../../../../.artifacts/integration-ver2-4-014-v1/root-bundle-acceptance.json)、[整包002實際回執](../../../../.artifacts/desktop/build-ver2-4-014-v1/independent-bundle-readback-execution-002.json)、[來源實際回執](../../../../.artifacts/desktop/build-ver2-4-014-v1/source-review-execution.json)

首輪整包獨審因核驗器將控制層 `__init__.py` 的構建後版本與構建前摘要比較而退出 1；失敗001保留，最小修正核驗器依據後的002退出0，沒有重建產品。源碼和簽名包不等於原生操作、公證、乾淨安裝或發佈通過。[首輪失敗回執](../../../../.artifacts/desktop/build-ver2-4-014-v1/independent-bundle-readback-execution.json)、[核驗器修正記錄](../../../../.artifacts/desktop/build-ver2-4-014-v1/independent-bundle-readback-correction-002.json)

<a id="e100014-原生四类配方子集唯一停机读回与恢复"></a>

#### E100：014 原生四類配方子集、唯一停機讀回與恢復

同一 R 庫兩輪真實原生操作留存29份AX與26張JPG。文字、圖片、配音、視頻四類已保存作品分別查看原配方並各明確載入一次新普通草稿；文字草稿改選既有4-bit模型後，實際展示模型編號、版本與摘要三項差異，再保存回原模型。文本收藏開啓後正常退出，重開仍開啓，再取消恢復false；四個草稿重新打開均恢復各自原來源。獨立UI審查逐張看過26張圖並核對55份文件；18最近任務的四個編號來自AX，不聲稱同張截圖內四行均可見。[根原生接受](../../../../.artifacts/work-recipe-ver2-4-014-v1/native-run-001/root-native-acceptance.json)、[UI獨審](../../../../.artifacts/work-recipe-ver2-4-014-v1/native-run-001/independent-ui-review-001.md)

唯一停機SQLite讀取實際退出0，原519條資源、737條事件原始行、32次運行、2個項目、3份人工修訂、2條原命令及schema保持。恰新增四個乙項目普通生成草稿和四條復用命令，合計523資源／42任務／6命令；文本草稿修訂3，其餘修訂1。新任務編號由快照與命令獨立派生，再與18的AX編號核對；最終設置只更新乙四個生成槽及當前文本草稿，甲上下文、乙訓練槽和非UI設置保持。根29項和純JSON獨審138項全部通過，本輪沒有配置檢查、模型運行、新修訂或導出。[停機比較](../../../../.artifacts/work-recipe-ver2-4-014-v1/native-run-001/post-native-readback-001/comparison.json)、[138項獨審](../../../../.artifacts/work-recipe-ver2-4-014-v1/native-run-001/independent-data-review-001.json)、[獨審實際退出](../../../../.artifacts/work-recipe-ver2-4-014-v1/native-run-001/independent-data-review-execution-001.json)

751份業務文件的逐文件metadata清單保持，7份原產物／人工修訂的實際大小與SHA保持；不將751份metadata稱為全部文件字節重新哈希。014順序為：兩輪App正常退出→selector仍指向R且保護持鎖時執行唯一停機讀回→按原字節和同一inode恢復原selector→核對19項保護並釋放guard；該順序與013先恢復selector再讀回不同。兩輪App和guard實際退出0，最終全部產品與保護進程停止。[文件範圍](../../../../.artifacts/work-recipe-ver2-4-014-v1/native-run-001/root-after-files.json)、[最終釋放與讀回](../../../../.artifacts/work-recipe-ver2-4-014-v1/native-run-001/root-final-release-readback.json)

本批只簽收014配方子集。真實文字設備菜單僅Apple GPU，設備差異未觀察；03既有WorkRevisions的正文／差異長行向右裁切、底部按鈕居中標籤不可見，證據不支持縱向擠出或不能橫滾的斷言。015兩處源碼最小修復已完成，仍待新簽名包和原生復驗。014源碼已修終態過時提示，但零運行沒有補實際運行中只讀或後台跨項目完成；整個AC-16、完整AC和M0—M6繼續。011性能、舊失敗、兩輪質量預算及硬件／跨主機／安裝／五用戶門檻不變。[014執行進度](2026-09-13-ver2-4-014-progress.md)

<a id="h-015-既有人工修订布局复验"></a>

### H. 015 既有人工修訂佈局復驗

<a id="e101015-两处局部修复相关测试与签名来源"></a>

#### E101：015 兩處局部修復、相關測試與簽名來源

014的03截圖中，既有文字修訂正文和差異長行向右裁切，底部按鈕居中標籤不可見。015只改 WorkRevisions.tsx 與 styles.css：局部單列及子項允許收縮，預格式正文保留換行並對長行折行；未改保存、導出或全局彈窗行為。現有修訂7項、彈窗焦點5項共12項相關前端測試及TypeScript類型檢查實際退出0，不稱完整前端／後端／宿主回歸。[兩處源碼審查](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/root-source-review.json)、[12項與類型檢查](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/frontend-validation-001/result.json)

同一路徑唯一構建015，構建和外層實際退出0；Global Cybersecurity Alliance Limited／R3JK7R29AC 的7個簽名目標、21,962文件／48鏈接及2,031,852,170字節核對通過。208凍結項含88應用輸入，206工作樹副本對應157唯一源文件；282包內物理源碼副本、392來源聲明與4個嵌入PYZ一致。整包及凍結來源獨審分別有實際退出0回執，不代替原生操作、公證、乾淨安裝或發佈驗收。[構建實際回執](../../../../.artifacts/desktop/build-ver2-4-015-v1/build-execution-result.json)、[簽名包接受](../../../../.artifacts/integration-ver2-4-015-v1/root-bundle-acceptance.json)、[整包獨審實際回執](../../../../.artifacts/desktop/build-ver2-4-015-v1/independent-bundle-readback-execution.json)、[來源獨審實際回執](../../../../.artifacts/desktop/build-ver2-4-015-v1/source-review-execution.json)

<a id="e102015-原生布局唯一快照勘误与保护收尾"></a>

#### E102：015 原生佈局、唯一快照勘誤與保護收尾

同一R庫一次真實App操作，完成現有文字、配音文案、字幕的原版／當前修訂／完整差異查看，進入編輯器後未改字段即取消；正文與差異未見橫向裁切。文字窗口縮為1440×673後，實際滾動到完整保存／取消按鈕，取消後完整顯示編輯／導出按鈕，並回到頂部；音頻和字幕使用恢復高度後的窗口，最終恢復1440×960。本批26份AX、23張JPG、26份時間記錄、2份幾何記錄共77文件；獨立審閱者實際看18張原圖，008／016／019單張不證明底部可達，分別由009／017／022—024補證。根20項接受檢查、獨審29項及勘誤補審18項分別通過，不合計為測試套件。[根原生接受](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/root-native-acceptance.json)、[獨立原圖審閱](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/independent-ui-review-001/review.json)、[勘誤補審](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/independent-ui-review-001/root-correction-review.json)

App正常退出實際0後，在selector仍指向R且guard持鎖時只執行一次停機SQLite讀取。原比較實際退出1，只因準備及UI觀察將“作品與素材”內部page誤寫為works；現有快照和凍結前後端源碼均為assets。原reader、UI和失敗comparison保留，新記錄僅糾正頁名並用既存JSON復算實際0，7項檢查含原失敗重現、錯誤頁值及額外變化拒絕；沒有追加SQL或App。最終原523資源／42任務／737事件／32運行／2項目／6命令／12作品／3修訂及schema保持，僅乙page從home到assets、task_id從舊任務到null。751份業務文件逐項metadata及7份原產物／人工修訂的大小與SHA保持，不稱751份文件全部重新哈希；本批零新任務、模型運行、修訂保存、導出或媒體播放。[原唯一比較失敗](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/post-native-readback-001/comparison.json)、[既存JSON頁名勘誤](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/page-name-correction-001/comparison.json)、[業務文件範圍](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/post-native-readback-001/business-files.json)

首次guard在App啓動前已消失，實際退出碼未知，原held記錄保留而不當作當前鎖證據。核19項原對象、同R及包保持後，先按原字節和同一inode恢復selector，再由guard002重新持鎖覆蓋唯一App與讀回。最終再次恢復原selector與19項保護，guard002實際退出0，全部產品和保護進程停止；R最終無旁路。根首次接受記錄因資源kind誤寫在寫入前拒絕，後按既存快照糾正，未改產品或原證據。015只關閉現有樣本佈局；完整鍵盤、極限樣本、設備差異、整個AC-16及M0—M6未簽署。下一批圖片實際運行中狀態僅準備，舊性能／質量失敗和已用預算不變。[首次guard異常恢復](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/guard-001-abnormal-recovery.json)、[最終釋放](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/native-run-001/root-final-release-readback.json)、[015執行進度](2026-09-13-ver2-4-015-progress.md)

<a id="i-015-普通图片完成保存与归属子集"></a>

### I. 015 普通圖片完成、保存與歸屬子集

<a id="e103同一签名包的一次图片生成保存运行窗口漏采保留"></a>

#### E103：同一簽名包的一次圖片生成保存，運行窗口漏採保留

在已接受的同一015公司簽名包、同一獨立恢復R庫中另啓動一次App，乙項目“本機完整流程驗證”新建普通圖片任務。固定Tiny-SD／Apple GPU、512×512、20步、CFG7.5、種子2027，明確開始一次、保存一次，終態藍杯預覽、作品列表、配方和來源可見。根24項接受檢查與唯一停機讀回的33項業務檢查分別通過；只簽收圖片完成、保存及同乙項目歸屬，不簽AC-01/02、完整原計劃或M0—M6。[根子集接受](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/root-native-acceptance.json)、[原生獨審](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/independent-ui-review-001/independent-ui-review.json)

47份AX、47份時間、46張JPG和3份動作記錄共143文件哈希吻合，獨審實際看15張代表原圖。30組快速採樣僅覆蓋07:24:33.558—34.896 UTC、共1.338秒，全部早於queued（38.204192）。真實running從39.016236到finalizing的48.231989，共9.215753秒，terminal為48.248670；015幀於51.569已終態。整個運行窗口位於16.673秒採樣空檔，文件名running或終態後的事件歷史不能替代現場觀察。未切甲、未留甲觀察終態、未返回乙，running_readonly／away_project_visible／away_after_terminal／return_origin四槽保持null。缺口是採樣方法錯過，不是已證功能失敗，也未重跑模型補證。[漏窗口分析](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/root-missed-window-analysis.json)、[全部圖文時間核對](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/independent-ui-review-001/timeline-and-ax-review.json)

App正常退出實際0後只做一次停機SQL，實際退出0。新增1任務、1預檢、1執行、1收集、1作品和23產物，共28資源，10事件與提交／保存2命令；所有新增記錄歸乙，任務→執行→作品→主圖片關係閉合。最終551資源、2項目、43任務、33次運行、13作品、747事件、8命令和3份舊修訂；業務metadata由751到797，舊751項metadata與7份原產物／修訂大小和SHA保持，不稱全庫重新哈希。原生看見task、attempt、work、主artifact四個編號，預檢和收集僅由唯一snapshot推導。[唯一快照](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/post-native-readback-001/snapshot.json)、[業務關係比較](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/post-native-readback-001/comparison.json)、[文件範圍](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/post-native-readback-001/business-files.json)

主圖片輸出和保存副本均完整解碼為RGB512×512、288119字節，文件及像素SHA一致；藍杯可見不代表原質量計劃通過。準備guard首次綁定因兩份歷史“旁路不存在”結構不同而誤拒，原退出1和原件保留；僅修正該契約比較後23項已綁定正負例通過，才進行原生操作。此前9項未綁定入口和32項純JSON準備測試未覆蓋該路徑，不合計為產品驗收；原夾具失敗和默認解釋器無Pillow失敗也保留。最終原selector同字節同inode恢復，19項原對象與015包錨點不變，guard實際退出0、全部產品及保護進程停止。[PNG完整解碼](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/root-png-decode.json)、[guard原拒絕](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/root-guard-binding-attempt-001-failure.json)、[修後23項](../../../../.artifacts/project-running-ver2-4-015-v1/preparation-002/entry-binding-tests-001/result.json)、[原夾具失敗](../../../../.artifacts/project-running-ver2-4-015-v1/preparation-002/readback-tests-001/test-run-001-failure.json)、[最終恢復釋放](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/root-final-release-readback.json)

較早reader的root_acceptance_pending、png_full_decode_verified原值和缺觀察的NoneType記錄均保留，後續PNG／根接受另附；獨審中命名含false_preserved的字段僅展示原false，不是保留檢查失敗，澄清已斷言原值和SHA未變。E01—E102的C—H歷史塊逐字保留，其中“圖片僅準備”是當時狀態，由本節更新當前結果。舊失敗、011初顯性能歸屬和兩輪已用質量預算不變。[字段澄清](../../../../.artifacts/project-running-ver2-4-015-v1/native-run-001/independent-ui-review-001/field-meaning-clarification.json)

<a id="j-016-导出异常恢复与固定修订保持"></a>

### J. 016 導出異常恢復與固定修訂保持

<a id="e104016-导出恢复修复相关测试与唯一签名构建"></a>

#### E104：016 導出恢復修復、相關測試與唯一簽名構建

導出異常恢復與所選修訂保持兩項問題涉及 App.tsx、ExportDialog.tsx 和 delivery.py 三個產品文件：補齊非終態錯誤與覈實原包入口，歷史重開保留已覈實的原版／固定修訂，未知版本明確提示；同時修正舊冪等響應的過時路徑／錯誤，以及同項目歷史請求亂序覆蓋。54 項相關前端測試、82 項控制服務測試和 TypeScript 類型檢查分別實際退出 0，原失敗重現與修後記錄保留，不稱全項目回歸。[根源碼審查](../../../../.artifacts/export-recovery-ver2-4-016-v1/root-source-review.json)

同一路徑唯一構建 Ver2.4（016），構建與外層實際退出 0。Global Cybersecurity Alliance Limited／R3JK7R29AC 的 7 個簽名目標、21,962 文件／48 鏈接及 2,031,864,516 字節核對通過；208 凍結項、282 包內物理源碼副本、392 來源聲明及 4 個嵌入 PYZ 一致。整包與來源獨審分別實際退出 0；根首次把 PYZ 記錄列表當字符串集合的檢查錯誤已保留，按原 JSON 結構糾正後通過，沒有改產品或原報告。[簽名包接受](../../../../.artifacts/integration-ver2-4-016-v1/root-bundle-acceptance.json)、[構建實際回執](../../../../.artifacts/desktop/build-ver2-4-016-v1/build-execution-result.json)、[整包獨審回執](../../../../.artifacts/desktop/build-ver2-4-016-v1/independent-bundle-readback-execution.json)、[來源獨審回執](../../../../.artifacts/desktop/build-ver2-4-016-v1/source-review-execution.json)

<a id="e105016-当前修订导出失败重开与第二次新导出成功"></a>

#### E105：016 當前修訂導出失敗重開與第二次新導出成功

同一固定 016 簽名包、同一獨立恢復 R 庫中一次真實 App，將當前文字修訂版 2 導出到本次只讀空目標，實際出現 EXPORT_INCOMPLETE，目標無負載殘留。從失敗任務歷史重開同記錄，重新檢查仍保留固定修訂版 2；顯式換獨立可寫目標並開始第二次新導出，第二條記錄成功。成功包 4 份負載加 manifest 共 5 文件逐項核對，原正文 315 字節及修訂版 2 的 204 字節與凍結計劃、原件一致。35 項業務檢查、8 項原生觀察及獨審分別通過，52 份 CUA 原件已審閱，不合計為完整測試。[根原生 A 子集接受](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-run-001/root-native-acceptance.json)、[唯一比較](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-run-001/post-native-readback-001/comparison.json)、[導出文件核對](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-run-001/post-native-readback-001/exported-files.json)、[獨審實際回執](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-run-001/independent-review-001/execution-result.json)

新增 8 個導出相關資源、12 事件及 2 命令，沒有模型執行或新修訂；最終 559 資源／759 事件／10 命令／45 任務／35 次運行記錄（其中本批新增 2 次導出執行）／12 導出／13 作品／3 份舊修訂。原 551 資源、797 份業務文件 metadata 和 7 份原件大小／SHA 保持，不稱業務目錄全部重新哈希。App 正常退出後唯一 SQL 讀回實際 0，原 selector 同字節同 inode 恢復，19 項原對象與包保持，目標權限恢復，App 與 guard 實際退出 0 且全部停止。[業務文件範圍](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-run-001/post-native-readback-001/business-files.json)、[唯一讀回回執](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-run-001/root-reader-execution.json)、[最終恢復](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-run-001/root-final-release-readback.json)

A 只覆蓋當前修訂版 2 的普通失敗重開；待覈實原包入口 B1、已有新版後的舊修訂保持 B2 仍僅準備，完整包補登記成功也未驗。queued／running 瞬時狀態未單獨觀察。較早 reader 的根接受／原圖待審標記保留，後續根接受另附；不簽完整 AC-16／27、M0—M6 或對外發佈。E01—E103 的 C—I 歷史塊逐字保留，“016 修復中”仍是當時狀態；當前結果以本節和[016進度](2026-09-13-ver2-4-016-progress.md)為準。

<a id="e106016-非最新-v2-保持与空-final-待核实后同号失败"></a>

#### E106：016 非最新 v2 保持與空 final 待覈實後同號失敗

同一 016 簽名包、同一 R 庫中保存 1 份 237 字節 v3，父版本為原 v2；重開 A 的舊失敗記錄後，B2 新導出仍固定 204 字節 v2 並成功，5 文件與凍結計劃一致。B1 在新獨佔目標只做一次空 final 目錄碰撞，原生顯示“運行中／待覈實”及覈實按鈕；唯一覈實後，同一導出記錄轉為 EXPORT_INTERRUPTED／失敗。完整 partial 與空 final 的 9 個目錄條目、5 個文件在覈實前後保持身份、時間和摘要。[根 B 子集接受](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/root-native-acceptance.json)、[原生觀察](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/root-ui-observations.json)、[前後文件觀察](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/root-b1-file-observations.json)

首次唯一 SQL 讀回 c8a470 實際退出 1，原比較 25／26 項通過且 failed 保留。凍結產品本來派生 text_truncated:false，校驗器漏算該字段；離線僅補三行同規則投影，嚴格比較完整響應。7 項測試及一次保存 JSON 復核分別實際退出 0，只有這一項改變；26 項業務檢查為 17 項純數據重算加 9 項原現場檢查沿用，13 項原生觀察原樣保留，未追加 SQL／App。[首次失敗](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/root-reader-execution.json)、[原比較](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/post-native-readback-001/comparison.json)、[離線修正](../../../../.artifacts/export-recovery-ver2-4-016-v1/B-saved-readback-correction-001/offline-result-001.json)、[7項測試](../../../../.artifacts/export-recovery-ver2-4-016-v1/B-saved-readback-correction-001/synthetic-tests-execution-001.json)、[離線實際回執](../../../../.artifacts/export-recovery-ver2-4-016-v1/B-saved-readback-correction-001/offline-execution-001.json)

本批 1 次啓動、1 次修訂保存、2 次導出開始、1 次覈實、0 次模型運行；新增 10 資源／18 事件／4 命令，最終 569 資源／777 事件／14 命令。根初稿將 37 個運行事件分組誤當事件總數，已用同一保存快照合計更正，原件保留。72 份 CUA 原件為 21 AX／20 JPG／31 JSON，獨審看過 10 張圖；77 項原件檢查與 19 項閉合檢查不計為產品測試。App／guard 實際退出 0，原選擇 374 字節同 inode 恢復，19 項原對象、A 導出與包保持。[唯一快照](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/post-native-readback-001/snapshot.json)、[計數初稿](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/root-native-acceptance-attempt-group-count-001.json)、[獨審](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/independent-review-001/result.json)、[最終恢復釋放](../../../../.artifacts/export-recovery-ver2-4-016-v1/native-B-run-001/root-final-release-readback.json)

05 菜單僅 AX／時間、沒有截圖，04／06 頁面不能替代；B2 未採到 queued／running，task 編號在 13／20 隊列稍後出現。B1 的“文件已發佈”文案不準確，空 final 不代表完整包發佈；完整包成功覈實、完整 AC-16／27、M0—M6、質量性能及發佈資格仍未驗。017 已將提示窄修為“導出結果尚未確認”，83 項控制服務和 28 項前端相關測試通過，僅為下一步源碼接受，尚未構建／原生，不回寫 016 原件或提前新增 E107。[017源碼接受](../../../../.artifacts/export-status-ver2-4-017-v1/root-source-review.json)

<a id="k-017-中性待核实提示与签名包"></a>

### K. 017 中性待覈實提示與簽名包

<a id="e107017-中性待核实提示相关测试与唯一签名构建"></a>

#### E107：017 中性待覈實提示、相關測試與唯一簽名構建

產品只將待覈實錯誤提示改為“導出結果尚未確認，請覈實原導出；不會重新運行模型。”，錯誤碼、狀態、覈實與文件行為不變。新增確定性完整 partial／空 final 碰撞測試，既有完整包補登記成功測試補核相同提示；原兩項文字斷言失敗 f543fe／1 保留，修後 83 項控制服務測試 77e369／0、28 項前端相關測試 e38dd0／0，不稱全項目回歸。[根源碼接受](../../../../.artifacts/export-status-ver2-4-017-v1/root-source-review.json)、[原失敗](../../../../.artifacts/export-status-ver2-4-017-v1/red-001/execution.json)、[控制服務測試](../../../../.artifacts/export-status-ver2-4-017-v1/green-001/execution.json)、[前端測試](../../../../.artifacts/export-status-ver2-4-017-v1/frontend-001/execution.json)

同路徑唯一構建 Ver2.4（017），構建及包裝層實際 e2f59f／0；整包獨審 4d5ee7／0。Global Cybersecurity Alliance Limited／R3JK7R29AC 的 7 個簽名目標、21,962 普通文件／48 鏈接和 2,031,864,537 字節核對通過。首次來源審查 05ae30／1 因根選用的控制服務 venv 缺 PyInstaller，尚未讀取源碼／PYZ，失敗原件保留；根 84e573／0 核對既有 package-venv 後，保持校驗腳本原字節補充執行 f0e8b8／0，未安裝依賴。208 凍結項、282 包內物理源碼副本、392 來源聲明及 4 個嵌入 PYZ 一致，原 19 項與 R 在原生前保持，根已正式接受簽名包。[根包接受](../../../../.artifacts/integration-ver2-4-017-v1/root-bundle-acceptance.json)、[構建實際回執](../../../../.artifacts/desktop/build-ver2-4-017-v1/build-execution-result.json)、[整包實際回執](../../../../.artifacts/desktop/build-ver2-4-017-v1/independent-bundle-readback-execution.json)、[首次來源失敗](../../../../.artifacts/desktop/build-ver2-4-017-v1/source-review-execution.json)、[後續來源實際回執](../../../../.artifacts/desktop/build-ver2-4-017-v1/source-review-002-execution.json)

017 原生交互仍待驗：運行中只讀與跨項目時序、中性提示真實碰撞復驗、完整已發佈包補登記成功尚無本版原生接受。整個 AC-01/02、AC-16/27、完整同包與 M0—M6、質量性能及發佈資格未通過。上方 E01—E106、舊 015／016 進度及執行記錄歷史塊逐字保留；其中“017 尚未構建／不提前新增 E107”是形成當時的狀態，由本條新增後續結果，未回寫原件。[017進度](2026-09-13-ver2-4-017-progress.md)、[E107文檔校驗](../../../../.artifacts/integration-ver2-4-017-v1/docs-update-001/result.json)

<a id="e108017-图片生成与项目切换的原生有限子集"></a>

#### E108：017 圖片生成與項目切換的原生有限子集

同一 017 簽名 App 一次真實 Tiny-SD Apple GPU 圖片生成完成並保存。運行中配置只讀、首份有效甲項目畫面早於收集階段、終態後甲項目樣本保留原草稿與輸出，返回乙後保存同一次運行作品；根已接受這個有限子集。[根原生接受](../../../../.artifacts/project-running-ver2-4-017-v1/native-run-001/root-native-acceptance.json)、[獨立原圖與保存證據審閱](../../../../.artifacts/project-running-ver2-4-017-v1/native-run-001/independent-native-review-001/REVIEW.md)

後台 running 區間為 13.165216 秒，運行中只讀截圖完整落在其中；第一份有效甲截圖結束比 finalizing 早 2.929342 秒。首份有效甲延遲 9.445 秒，未達 3 秒目標；20.610 秒與 28.223 秒採樣缺口保留，不證明全程連續停留甲。19 過渡樣本被拒絕，21 返回無原件，pipe closed 後以 21b 保存畫面恢復觀察，不補造缺幀。

一次模型運行、一次作品保存、停機唯一 SQL 核對及原 19 項／selector 同字節同 inode 恢復有證據；新增 28 資源、23 artifact、10 事件、2 命令。輸出與登記 PNG 均為 512 × 512 RGB、288119 字節，完整解碼通過但質量未評估；23 個 artifact 記錄不等於 23 個新 assets 實體。017 導出中性提示原生復驗、完整已發佈包補登記成功、整個 AC 與 M0—M6 及發佈仍待驗。E01—E107 和 016 全歷史不改寫。[017進度](2026-09-13-ver2-4-017-progress.md)、[E108文檔校驗](../../../../.artifacts/integration-ver2-4-017-v1/docs-update-002/result.json)

<a id="e109017-普通历史-v2-导出与故障窗口失败"></a>

#### E109：017 普通歷史 v2 導出與故障窗口失敗

當前已有 v3 時選擇歷史 v2，完成一次普通導出並從隊列重開同號已完成導出。4 個內容文件加 manifest 共 5 文件的保存實體核驗通過；原 19 項、selector 原字節同 inode 恢復，App／guard 正常退出。根只接受普通歷史 v2 導出與保護有限子集。[根接受](../../../../.artifacts/export-status-ver2-4-017-v1/native-run-001/root-native-acceptance.json)、[獨立原件審閱](../../../../.artifacts/export-status-ver2-4-017-v1/native-run-001/independent-native-review-001/REVIEW.md)

故障窗口於 10:48:11.489 UTC 截止，根實際點擊為 10:48:11.559，晚 70 毫秒；watcher 實際退出 3、timeout、0 mkdir。兩次定位錯誤與窗口執行失敗保留，pending／reconciled 兩槽為 null；沒有覈實，也未覆蓋中性提示，不能據此認定產品故障或原故障場景通過。1 次 App、1 次普通導出、0 覈實／模型／修訂保存；唯一停機 SQL 的 18 項業務檢查與 14 項獨審檢查分別通過，54 份原件中實看 6 張關鍵圖。新增 4 資源／9 事件／1 命令，最終 601 資源／796 事件／17 命令／838 業務元數據文件。task 編號僅在後續隊列關聯，重開標題通用，不回填 UI 不可見字段。

25 項純窗口決策測試通過只代表準備，未執行新的 CUA 窗口、不授權重試、不增加預算。本輪停止原生執行；最新停機基線僅引用本批根接受的 `latest_stopped_baseline`，圖片批舊基線保持歷史歸屬。中性提示原生、完整已發佈包成功覈實、整個 AC-16／27 與 M0—M6 仍未通過。E01—E108 原文保持。[窗口決策準備接受](../../../../.artifacts/export-status-ver2-4-017-v1/window-submit-preparation-001/root-review.json)、[017進度](2026-09-13-ver2-4-017-progress.md)、[E109文檔校驗](../../../../.artifacts/integration-ver2-4-017-v1/docs-update-003/result.json)

<a id="l-018-迟到结果操作与同库刷新"></a>

### L. 018 遲到結果操作與同庫刷新

<a id="e110018-修复签名包与原生只读记录"></a>

#### E110：018 修復、簽名包與原生只讀記錄

真實 React 組件配合固定傳輸夾具復現：控制請求在切庫後遲到時，原組件仍可能追加新庫 GET 並回寫舊回調；三類保存操作也缺少同等保護。修復覆蓋動作入口和各次等待後的庫身份與組件生命週期。第一版把同庫卸載後的成功父刷新一並丟棄，真實 App 的“保存作品途中進入作品頁”反例失敗；第二版保留同庫成功刷新，跨庫仍拒絕後續 GET、狀態與父回調。[根源碼接受](../../../../.artifacts/library-stale-response-ver2-4-017-v1/root-source-acceptance.json)、[同庫導航反例](../../../../.artifacts/library-stale-response-ver2-4-017-v1/red-002/execution.json)

兩份核心測試 48 項及五份直接相關回歸 35 項、TypeScript 檢查通過。開發瀏覽器 3 場景通過：跨庫待決和同時切庫卸載均只有原 A POST、零新 GET／回調；同庫正常追加 A GET，兩種父回調各一次。12 份 AX 與 3 張視口截圖保留，完整請求計數依據 AX；這不是簽名 App 或真實切庫驗收。AC-22 與 M0—M6 不提高，Rust 宿主競爭僅為待證假設。[相關回歸](../../../../.artifacts/library-stale-response-ver2-4-017-v1/green-002/result.json)、[瀏覽器原件](../../../../.artifacts/library-stale-response-ver2-4-017-v1/browser-001/root-browser-001/ui-records.json)、[瀏覽器獨審](../../../../.artifacts/library-stale-response-ver2-4-017-v1/browser-independent-review-001/REVIEW.md)

018 在固定路徑唯一構建完成，7 個公司簽名目標、整包及凍結來源核對已獲根接受。隨後一次同庫原生歷史讀取、離開後重開及正常退出完成；停機唯一讀取中 601 資源、796 事件、17 命令原樣，僅當前項目選擇由乙轉甲；既有 302 字節正文與兩次結果畫面一致。App 已停，原 19 項與選擇器原字節同 inode 恢復；最新停機基線採用 018 根原生接受中的 `latest_stopped_baseline`，對應本次 snapshot 與 final-release。10 份 AX 與 6 張截圖保留。原生獨審 23 項通過並獲根接受，此普通讀取不證明跨庫遲到響應。[簽名包接受](../../../../.artifacts/integration-ver2-4-018-v1/root-bundle-acceptance.json)、[根原生接受](../../../../.artifacts/integration-ver2-4-018-v1/native-readonly-001/root-native-acceptance.json)、[原生實際回執](../../../../.artifacts/integration-ver2-4-018-v1/native-readonly-001/actual-execution.json)、[停機比較](../../../../.artifacts/integration-ver2-4-018-v1/native-readonly-001/post-stop-readback-001/comparison.json)

<a id="m-019-修订历史分页"></a>

### M. 019 修訂歷史分頁

<a id="e111019-分页源码开发浏览器与公司签名包"></a>

#### E111：019 分頁源碼、開發瀏覽器與公司簽名包

超過 100 次修訂後，用戶可加載更早版本，繼續查看最早正文、父版本與差異；明確選擇的舊版編號保持，當前版本變化時保留正文、顯示待重新讀取，並暫時禁用編輯與導出。後端 23 項新增測試、93 項既有回歸及前端 11 項測試共 127 項通過，首個歷史不可達反例與後續當前標記反例保留。後端仍讀取同項目修訂集合，不聲稱大庫查詢性能優化。[根源碼接受](../../../../.artifacts/work-revision-pagination-ver2-4-019-v1/root-source-acceptance.json)

真實產品組件配固定數據的開發瀏覽器觀察到最早版 2、父差異、明確舊版導出回調，以及新修訂提示後重新讀取當前 103。普通場景早於最後標記修正，新修訂場景使用最終源碼；差異只涉及待重新讀取標記。這不是簽名 App 或真正導出，舊頁面句柄採集失敗保留，頁面與服務已關閉。[瀏覽器有限接受](../../../../.artifacts/work-revision-pagination-ver2-4-019-v1/browser-001/root-browser-acceptance.json)

019 在固定路徑唯一構建，TypeScript／Vite 與 Rust release 通過，018 完整 APFS 歸檔保留。整包 21,962 文件、48 鏈接、7 個公司簽名目標、208 份凍結文件、282 份物理來源副本、392 項聲明及 4 個真實嵌入 PYZ 已獲根接受；158 項源碼等於預期自動版本後的凍結輸入，原 19 項／selector 同 inode／最新 R 完整 stat 保持。分頁原生仍待驗，合法恢復後的首輪準備因 Row 比較腳本失敗而創建 0 修訂，原失敗保留；恢復庫窄續行和原生結果另記，不提前通過。[簽名包接受](../../../../.artifacts/integration-ver2-4-019-v1/root-bundle-acceptance.json)、[019進度](2026-09-13-ver2-4-019-progress.md)

本條只接受源碼、相關測試、開發瀏覽器和簽名包；不簽完整 AC-16／27 或 M0—M6。018 計時、舊質量失敗和兩輪已用訓練預算、017 故障窗口不重試均保持；指定 NVIDIA、實際跨主機、達標質量、乾淨安裝與五名首次用戶仍缺對應證據。

<a id="e112019-原生分页最早旧版普通导出与恢复"></a>

#### E112：019 原生分頁、最早舊版普通導出與恢復

同一固定 019 簽名 App 在獨立恢復庫中，首次歷史菜單含 100 條，加載後含 101 條；加載時版 3 的選擇與正文保持，隨後明確選擇最早版 2，查看父原版及完整差異，再完成一次普通導出。導出包的原正文、舊版正文、作品說明和配方共 4 個內容文件（8,314 字節）加 manifest 經獨立字節核對，選擇始終為版 2，未混入當前版 102。[根原生接受](../../../../.artifacts/work-revision-pagination-ver2-4-019-v1/native-run-001/root-native-acceptance.json)、[獨立審閱](../../../../.artifacts/work-revision-pagination-ver2-4-019-v1/native-run-001/independent-review-001/REVIEW.md)

101 條歷史由源碼業務接口預先創建；本次原生只有 1 次普通導出、0 修訂保存、0 模型運行。16 份 AX（含兩份完整菜單）與 13 張 JPEG 保留；一幀圖文過渡不一致被排除，採用後續穩定幀。正常退出後僅一次測試庫 SQL：舊 709 資源、656 事件、101 命令與修訂鏈均不變，僅新增 4 個導出資源、9 個導出事件和 1 命令，最終為 713／665／102；設置新增默認值和界面導航記錄。原 19 項和 R 保持，selector 原字節同 inode 恢復。[最終恢復](../../../../.artifacts/work-revision-pagination-ver2-4-019-v1/native-run-001/final-release.json)

首次停機檢查在 SQL 前拒絕，首次物理比較過強的失敗也保留；後續核對約定字段通過，未證明 atime 是原因。32 項獨審為離線核對，不追加為產品測試。原生沒有覆蓋新修訂衝突、獨立運行導出包、公證或整個 AC-16／27；E111 形成時的待驗狀態與舊失敗不回寫，舊質量／訓練預算、017 故障窗口不重試，以及 NVIDIA、跨主機、乾淨安裝和五名首次用戶缺口保持。[停機檢查原件](../../../../.artifacts/work-revision-pagination-ver2-4-019-v1/native-run-001/readback-first-failure.json)、[物理比較邊界](../../../../.artifacts/work-revision-pagination-ver2-4-019-v1/native-run-001/restore-readback-failure-analysis.json)

<a id="n-020-人工修订字符上限"></a>

### N. 020 人工修訂字符上限

<a id="e113020-字符计数修复开发浏览器与公司签名包"></a>

#### E113：020 字符計數修復、開發瀏覽器與公司簽名包

正文、配音文案和字幕改為與服務端一致的字符計數，擴展漢字“𠮷”計一個字符；移除輸入框的提前截斷，顯示已輸入字數與上限。正文 16000、單條字幕 500、字幕總文字 16000 和 200 條上限保持；超限輸入完整保留，保存前拒絕，父版、冪等、分頁和原媒體語義不變。15 項後端純邊界與 18 項最終前端測試共 33 項，以及 TypeScript 檢查通過。首輪測試夾具問題、第二輪 4 個產品失敗反例及修復後結果均保留。[根源碼接受](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/root-source-acceptance.json)、[首輪夾具原件](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/frontend-red-001/result.json)、[產品反例](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/frontend-red-002/result.json)

真實組件配固定內存數據的開發瀏覽器完成 3 次保存：正文 16000 字符含“𠮷”、配音文案 16000 個“𠮷”、199 條字幕增加至 200 條且總計 16000 字符；正文、單條及總字幕超限時均保留輸入並拒絕。配音保存後的工具超時保留，重連原標籤頁後確認只有一次配音保存，未重復提交，超時根因未證。這些是開發組件觀察，不是簽名 App 原生保存，也沒有模型運行。[瀏覽器記錄](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/browser-001/result.json)

020 經同一路徑唯一正式構建自動更新版本，019 完整 App 與凍結來源已 APFS 歸檔。完整包樹、7 個公司簽名、208 份凍結來源、282 份物理副本、392 條來源聲明與 4 份嵌入 PYZ 已獲根接受；158 個構建輸入與預期一致，原 19 項、selector 同字節同 inode 和 R 完整 stat 保持。[根簽名包接受](../../../../.artifacts/integration-ver2-4-020-v1/root-bundle-acceptance.json)

獨立新庫通過正式恢復並先覈實初次回執，再用 1 次真實業務調用預置 199 條字幕；這是準備階段，原生修訂保存為 0。020 的邊界保存、重開、父差異與原媒體播放仍待同包原生驗收，不簽完整 AC-16／27、M0—M6 或公證。[恢復準備接受](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/root-preparation-acceptance.json)

<a id="e114020-原生边界保存重开与长列表空白边界"></a>

#### E114：020 原生邊界保存、重開與長列表空白邊界

同一固定 020 公司簽名 App 完成正文、配音文案各 16000 字符及 200 條／總計 16000 字符字幕的 3 次修訂保存，正常退出後再次打開，當前版 3／3／4 與父版 2／2／3 一致。兩輪原音頻 8 秒、視頻 2 秒的播放控件均到達終點，屬於播放與時間軸觀察，不是音質聽評。199 條字幕的 1 次業務預置另算，本輪模型與導出為 0。[根原生接受](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/native-run-001/root-native-acceptance.json)、[全文字節與保存範圍](2026-09-13-ver2-4-020-progress.md)

輸入 AX 含全文，靜態正文 AX 僅 511 字符前綴，完整內容以停機讀回和實體字節為據；首份封存錯誤要求靜態 AX 全文的失敗保留，修正後的 25 項是證據核對，不追加產品測試。[首次封存](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/native-run-001/ui-evidence-seal.json)。大幅滾動的 29／30 兩幀空白未解，31／32 常規上、下一頁恢復不證明全列表始終正常。測試庫新增默認設置記錄及界面導航上下文，原庫與系統設置未改；原受保護文件按約定字段保持，原選擇同字節同 inode 恢復，其 mtime／ctime 隨恢復寫入變化。僅接受保存、重開、父版與原媒體播放有限子集，完整長列表渲染、鍵盤、AC-16／23／27、M0—M6 和公證均未簽。[最終恢復](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/native-run-001/final-release.json)、[未解滾動空白](../../../../.artifacts/work-revision-limits-ver2-4-020-v1/native-run-001/scroll-followup.md)

<a id="o-021-人工修订滚动边界"></a>

### O. 021 人工修訂滾動邊界

<a id="e115020-背景反例单条样式修复与-021-公司签名包"></a>

#### E115：020 背景反例、單條樣式修復與 021 公司簽名包

020 只讀復現確認彈窗到底後帶動背景；單條人工修訂彈窗縱向滾動邊界規則經開發瀏覽器前後對照、23 項前端測試和 TypeScript 檢查通過。020 完整 APFS 回滾包已保留，唯一正式構建生成固定路徑 021，正式包樹、公司簽名及本次輸入通過；沒有新增自定義 PYZ 審計。[源碼與瀏覽器接受](../../../../.artifacts/revision-scroll-ver2-4-020-v1/root-source-acceptance.json)、[021包接受](../../../../.artifacts/integration-ver2-4-021-v1/root-bundle-acceptance.json)

<a id="e116021-本机滚动边界与退出恢复"></a>

#### E116：021 本機滾動邊界與退出恢復

同一 021 簽名 App 的 200 條字幕在差異展開／折疊、逐頁／大幅和上下邊界滾動時背景保持原位，關閉後背景可滾；原視頻播放到 2 秒終點。一次正常退出，0 保存、導出、模型或 SQL；測試庫物理事實保持，原選擇恢復且鎖釋放。020 偶發空白本輪未重現、根因未定，Escape 後 HTML 焦點不證明入口焦點返回或完整鍵盤；完整 AC 與 M0—M6 不提高。[原生接受](../../../../.artifacts/revision-scroll-ver2-4-021-v1/native-run-001/root-native-acceptance.json)、[021範圍與原件](2026-09-14-ver2-4-021-progress.md)

<a id="p-022-人工修订键盘焦点"></a>

### P. 022 人工修訂鍵盤焦點

<a id="e117焦点修复开发浏览器与公司签名包"></a>

#### E117：焦點修復、開發瀏覽器與公司簽名包

人工修訂的開始編輯、退出確認、繼續和取消焦點已修復，保存或刷新後也回到可用控件；相關前端測試、TypeScript 檢查和真實開發瀏覽器前後對照通過，唯一正式構建生成同路徑 022 公司簽名候選。首次測試宿主錯誤、舊產品真實失敗及構建前檢查失敗均保留。[源碼與瀏覽器接受](../../../../.artifacts/keyboard-and-guide-ver2-4-021-v1/root-source-acceptance.json)、[022包接受](../../../../.artifacts/integration-ver2-4-022-v1/root-bundle-acceptance.json)

<a id="e118022-本机编辑焦点与退出恢复"></a>

#### E118：022 本機編輯焦點與退出恢復

同一 022 App 的已有字幕編輯首字段、Escape 後可見的“繼續核對”、Return 返回原字幕輸入，以及取消後直接 Return 重入編輯的原生有限子集通過。入口與取消含鼠標操作；部分焦點僅由 AX 和後續按鍵響應支持，不宣稱每幀都有焦點環。關閉後為 HTML 焦點，不簽入口返回或完整鍵盤。一次正常退出，無輸入、保存、導出、模型或 SQL；測試庫物理事實保持，原選擇與保護恢復，鎖釋放。[原生接受](../../../../.artifacts/revision-focus-ver2-4-022-v1/native-run-001/root-native-acceptance.json)、[022範圍與原件](2026-09-14-ver2-4-022-progress.md)

<a id="q-023-启动分段诊断"></a>

### Q. 023 啓動分段診斷

<a id="e119分段记录相关测试与公司签名包"></a>

#### E119：分段記錄、相關測試與公司簽名包

新增宿主、前端和後端環境檢查分段，保留原首屏就緒口徑、緩存、刷新及並行行為；前端、Rust、後端和計時器相關測試通過。022 完整回滾包保留，唯一正式構建與公司簽名、完整來源核驗通過，未做公證。測試原失敗、忽略項及構建前失敗保留。[源碼接受](../../../../.artifacts/startup-phases-ver2-4-023-v1/root-source-acceptance.json)、[023包接受](../../../../.artifacts/integration-ver2-4-023-v1/root-bundle-acceptance.json)、[023進度](2026-09-14-ver2-4-023-progress.md)

<a id="e120单次原生启动分段与诊断导出"></a>

#### E120：單次原生啓動分段與診斷導出

一次固定 023 App 啓動取得同次首屏、分段和診斷 ZIP，隨後正常退出；外部完整就緒 5.263 秒、宿主 5.206 秒，仍超過 3 秒。前端項目與資源較早就緒，本輪主要等待落在環境檢查，Kokoro 探測約 4.483 秒；各進程計時不能直接相減，不能據此解釋舊 45 秒長尾。使用舊測試庫完整 APFS 隔離副本，不是新恢復驗收；診斷允許寫新副本命令記錄，0 模型、業務保存／導出及額外 SQL，不簽精確業務零差。本次原生診斷有限子集已[正式接受](../../../../.artifacts/startup-phases-ver2-4-023-v1/native-run-001/root-native-acceptance.json)。原 23 項保護、舊完整庫及選擇恢復情況見[停機讀回](../../../../.artifacts/startup-phases-ver2-4-023-v1/native-run-001/root-readback.json)；[範圍與原件](2026-09-14-ver2-4-023-progress.md)。

<a id="r-024-静态导入索引"></a>

### R. 024 靜態導入索引

<a id="e121静态索引离线对照与公司签名包"></a>

#### E121：靜態索引、離線對照與公司簽名包

四個生產文件將固定 Transformers 頂層模型索引移到構建期，保留完整性、動態合併與中文就緒範圍；恢復器、雙解釋器打包／最終包校驗及媒體回歸通過。十二次真實離線導入中，Kokoro／Diffusers 中位分別減少 195.072／197.427 毫秒，各變體三樣本，未清系統緩存。唯一 024 公司簽名包的最終索引、映射順序和凍結來源已接受；原失敗與未採用的文件校驗候選保留。[024進度與證據](2026-09-14-ver2-4-024-progress.md#e121静态导入索引与签名候选)、[根包接受](../../../../.artifacts/integration-ver2-4-024-v1/root-bundle-acceptance.json)

<a id="e122单次原生启动与诊断读回"></a>

#### E122：單次原生啓動與診斷讀回

一次完整就緒外部觀測 3.938206 秒、宿主 3.903551 秒，仍超 3 秒；Kokoro 環境檢查約 3.336826 秒。一次診斷預覽／ZIP 後正常退出，舊完整庫與 23 項保護保持、原選擇恢復、三鎖可重獲。本次原生診斷與保護恢復有限子集已獲根接受；不簽精確業務零差、新恢復驗收、穩定啓動收益或完整 AC-24。[本輪讀回](../../../../.artifacts/transformers-static-index-next-v1/native-run-001/root-readback.json)、[024原生範圍](2026-09-14-ver2-4-024-progress.md#e122单次原生分段与保护恢复)

<a id="s-024-后长字幕空白诊断"></a>

### S. 024 後長字幕空白診斷

<a id="e123原操作取证与safari对照旧空白保持"></a>

#### E123：原操作取證與Safari對照，舊空白保持

當時工具文檔確認原調用為一次160頁，而非160像素；折疊後到大滾動前沒有原截圖。當前024真實組件與固定200條／16000字符、原2秒視頻的Safari分步及同頁連續對照均未重現空白。6項夾具測試、16組保存圖文和34條完整事件／幾何記錄通過核對，正式來源160份、包錨點7個、保護23項保持；測試標籤與服務已關閉。0正式App、構建、模型、probe、SQL或業務保存／導出，不簽原生空白修復、完整長列表／鍵盤或任何新AC。[診斷](2026-09-14-subtitle-scroll-diagnosis.md)、[根記錄核對](../../../../.artifacts/revision-blank-after-024-v1/safari-run-001/result.json)、[獨立審閱](../../../../.artifacts/revision-blank-after-024-v1/safari-review-001/REVIEW.md)

<a id="t-025-人工修订入口回焦"></a>

### T. 025 人工修訂入口回焦

<a id="e124真实入口修复safari-对照与公司签名包"></a>

#### E124：真實入口修復、Safari 對照與公司簽名包

打開人工修訂前聚焦被點擊的真實作品入口，沿用原彈窗歸還機制；沒有改變修訂數據、保存或導出請求。3 項新增回歸由紅轉綠，五個相關文件共 36 項及類型檢查通過；Safari 固定傳輸對照驗證回焦、Enter 重開、繼續核對和明確放棄，0 業務寫。唯一 025 公司簽名包及凍結來源已接受。[025進度與證據](2026-09-14-ver2-4-025-progress.md)、[根包接受](../../../../.artifacts/integration-ver2-4-025-v1/root-bundle-acceptance.json)

<a id="e125原生内容读取失败错误弹窗回焦及保护恢复"></a>

#### E125：原生內容讀取失敗、錯誤彈窗回焦及保護恢復

一次固定 025 App 打開 APFS 副本中的已有字幕，報“修訂原快照沒有完整恢復來源”。錯誤彈窗 Escape／關閉回同一入口、Enter 重開成立；200 條保存正文和未保存編輯流程均未進入。六份 AX、四張 JPEG 和退出保護已獨審；原 020 庫、舊 024 副本與 23 項保護保持，選擇恢復、三鎖可重獲。0 修訂正文輸入、保存、播放、導出、模型和 SQL；宿主單次完整就緒 5054.747167 毫秒仍超 3 秒，不提高性能、恢復、完整鍵盤或階段接受。[根原生記錄](../../../../.artifacts/work-revision-return-focus-next-v1/native-run-001/root-native-acceptance.json)、[獨立審閱](../../../../.artifacts/work-revision-return-focus-next-v1/native-run-001/independent-review-001/REVIEW.md)

<a id="u-025-合法恢复准备与原生回焦"></a>

### U. 025 合法恢復準備與原生回焦

<a id="e126合法独立恢复与全部历史核对"></a>

#### E126：合法獨立恢復與全部歷史核對

通過正式備份校驗、恢復計劃與恢復流程建立新獨立庫，先覈實恢復回執，再讀取文字、配音文案、字幕的全部歷史；當前版分別為 3／3／4，字幕保留 200 條／16000 字符。61 個連接均在新準備範圍內且已關閉，原源庫 SQL 為 0；本次不是 `Backup.create` 產品驗收。後續原生直接使用該恢復根，沒有再次複製或修改業務來源繞過校驗。[準備接受](../../../../.artifacts/work-revision-return-focus-next-v1/restoration-preparation-001/root-preparation-acceptance.json)、[實際結果獨審](../../../../.artifacts/work-revision-return-focus-next-v1/restoration-preparation-001/actual-review-001/REVIEW.md)

<a id="e127内容读取回焦与明确放弃有限通过"></a>

#### E127：內容讀取、回焦與明確放棄有限通過

同一 025 簽名 App 在合法恢復根中成功讀取當前字幕版 4／父版 3；Escape 和關閉按鈕返回入口 112，Enter 可重開。編輯時輸入 46 字符 ASCII 臨時文本，繼續核對回到同一字段並保留文本；明確放棄後回入口，再次打開恢復原保存內容。15 份 AX、8 張 JPEG 支持這些有限路徑，02 首開焦點仍為 HTML，不能稱所有彈窗初始焦點或完整鍵盤通過。[根原生接受](../../../../.artifacts/work-revision-return-focus-next-v1/native-run-002/root-native-acceptance.json)、[原件](../../../../.artifacts/work-revision-return-focus-next-v1/native-run-002/ui/records.json)

App 正常退出 0，新恢復庫數據庫完整文件事實前後相等；原 020 庫、舊 024 與首次 025 副本、23 項保護保持，選擇器原字節、inode 和權限身份恢復，mtime／ctime 隨選擇與恢復變化。本輪 0 保存、導出、模型、額外 SQL、額外 probe 和系統設置變更；啓動自帶的環境檢查照常發生。宿主單次完整就緒 5449.750541 毫秒（約 5.450 秒）仍超 3 秒，不代表穩定性能或舊長尾已解釋。[停機讀回](../../../../.artifacts/work-revision-return-focus-next-v1/native-run-002/root-readback.json)

<a id="v-026-首次修订读取后的焦点"></a>

### V. 026 首次修訂讀取後的焦點

E128：首次修訂讀取結束後，僅在焦點已失效時回到可用關閉按鈕，保持用戶已選控件的焦點；讀取、保存、分頁和退出守衛不變。5 項新增與 36 項既有回歸共 41 項及類型檢查通過。Safari 延遲成功／失敗修前失焦、修後恢復，已有播放器焦點保持、即時讀取和 Enter 重開正常；這是固定傳輸的真實組件對照。025 完整回滾包已保留，唯一 026 公司簽名包已接受。[源碼接受](../../../../.artifacts/revision-loading-focus-next-v1/root-source-acceptance.json)、[Safari保存證據復核](../../../../.artifacts/revision-loading-focus-next-v1/browser-001/browser-review.md)、[包接受](../../../../.artifacts/integration-ver2-4-026-v1/root-bundle-acceptance.json)

E129：一次固定 App 首開與 Enter 重開時，焦點均在可用關閉按鈕；Escape／點擊關閉後回原入口。9 份 AX、7 張 JPEG；Option-Tab 實際到版本選擇器，沒有播放。四份 AX 的 200 條正文和時間與保存版 4／父版 3 逐條相等，共 16000 字符。正常退出後恢復根數據庫完整文件事實和原保護保持，選擇恢復；無輸入、保存、導出、模型、額外 SQL／probe 或系統設置變更。不簽完整鍵盤，也不據單輪完整就緒計時判定 20 次初顯指標。[根原生接受](../../../../.artifacts/revision-loading-focus-next-v1/native-run-001/root-native-acceptance.json)、[停機讀回](../../../../.artifacts/revision-loading-focus-next-v1/native-run-001/root-readback.json)

<a id="w-026-完整导出包登记恢复"></a>

### W. 026 完整導出包登記恢復

E130：5 項後端相關測試通過（1 新增、4 既有）；登記觀察器 30 項、恢復準備 7 項、監督器 6 項合成測試分別通過。正式恢復的新獨立庫使用 61 個新範圍連接且全部關閉，原源庫 SQL 為 0；不是 Backup.create 產品界面驗收。

E131：一次 026 App 導出已有文字修訂版 3，完整 4 負載加 manifest 發佈後登記失敗，08 中性待覈實、09 同號覈實成功。1 App、1 導出、1 UI 覈實，0 模型／額外 probe、4 額外 SQL，正常退出並恢復原選擇和保護。原生與保護有限子集已接受，不簽完整 AC 或 M0—M6。[範圍與證據](2026-09-14-ver2-4-026-export-recovery-progress.md)

<a id="x-027-最小键盘属性与原生文字原作品导出"></a>

### X. 027 最小鍵盤屬性與原生文字原作品導出

E132：共用 Button、Dialog 關閉按鈕及 App 的 19 處原生按鈕顯式參與宿主鍵盤順序，沒有新增全局 Tab 接管。75 項前端測試、類型檢查通過；7 項夾具測試與真實 Safari 焦點路徑各自留證，不代替原生任務。

E133：唯一 027 公司簽名包已接受。一次原生純鍵盤文字原作品導出成功，展開三負載清單，隨後從隊列重開同號記錄並正常退出；一個獨立 immutable 連接關閉後，舊記錄與 settings 保持，新添 4 資源／8 事件／1 命令，四文件包核對通過。該任務鍵盤子集已獲根接受，不簽完整 AC 或 M0—M6。[範圍與證據](2026-09-15-ver2-4-027-keyboard-progress.md)

當前剩餘項以本次新增摘要為準：E131 已補中性待覈實提示與完整文字修訂包同號補登記成功的有限子項，E133 已有文字原作品鍵盤導出、同號任務重開及停機讀回證據；這些已完成的有限子項不再列為重復待辦。歷史表中的“仍未驗”保留其形成時點；其它對象／故障出口、其它鍵盤任務與完整 AC／M 階段繼續待驗。

<a id="y-media-三入口源码与-safari-键盘子集"></a>

### Y. Media 三入口源碼與 Safari 鍵盤子集

E136：僅 Media.tsx 三個導入 button 新增 `tabIndex={0}`；56 項相關前端測試、類型檢查、3 項夾具測試與真實 Safari 前後對照通過，獨審已獲根關閉。修前 26 文件保持，修後兩空資源分支共 58 文件／76 事件，四次 Enter 打開正確彈窗、Escape 回到各自入口，API 請求／錯誤／草稿更改為 0。當前簽名 App 仍為 028；029 歸檔、打包與原生待驗證，容量未達 40 GiB，debug 緩存清理未獲確認、未執行。不新增模型能力，不提高完整 AC／M0—M6。[進度與邊界](2026-09-15-media-keyboard-progress.md)、[獨審根關閉](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-review-closure.json)

<a id="z-029-media-原生键盘与停机数据子集"></a>

### Z. 029 Media 原生鍵盤與停機資料子集

E137：029 固定路徑公司簽名包已獲根接受。兩個既有任務中的四個 Media 入口實例均完成正反向 Tab、Enter 打開及 Escape 關閉回焦，正常退出；一次停機讀回確認 523 資源／673 事件／3 命令及全部業務記錄保持，僅四個預期頁面設定葉子變化。沒有真實導入或模型運行，完整 AC／M0—M6 不提高。[進度與證據](2026-09-15-media-keyboard-progress.md)

<a id="三wp-01wp-30-当前覆盖"></a>

## 三、WP-01—WP-30 當前覆蓋

| 工作包 | 實現／證據範圍 | 剩餘項；不得自動簽署 |
| --- | --- | --- |
| WP-01 | Apple 固定組合與訓練／加載真實通過（E01、E02） | NVIDIA、TV-03 與最終選型重估 |
| WP-02 | TV-02 和中間原生包啓停／恢復通過（E15） | 最終同源包不繼承全部舊證據 |
| WP-03 | SQLite、版本對象、事務；新增遷移與分頁，E16／E17 | 最新 schema／排序回歸和最終升級簽署 |
| WP-04 | 四類工作台和真實路徑；8組外觀與鍵盤草稿已驗（E23）；013 六入口續做原編號、甲手選較早任務與正常重開已驗（E98）；014 四類配方草稿來源恢復通過，終態過時提示已有源碼修復（E99—E100）；015普通圖片終態預覽、保存及同乙歸屬通過（E103）；017 圖片運行中只讀與跨項目返回保存有限子集通過（E108） | E103漏採不回寫；E108的3秒目標未達及採樣缺口保留，其餘對象、最終包與首次用戶驗收繼續 |
| WP-05 | 模型／SFT／圖片／素材導入、manifest、受限信任和官方準備入庫（E20） | 最終包及遠端信任驗收；未選格式不可啓動 |
| WP-06 | 本地生命週期與回環遠端賬本、事件、取消未知和原產物補收已實現；中斷邊界已獨立復驗（E30） | 最終包與實際跨主機環境 |
| WP-07 | 本機能力與字段拒絕，真實參數身份（E08） | NVIDIA／新增模式與優化組合聯動 |
| WP-08 | 獨立回環傳輸E25、默認位置E29、故障復驗E30；003原生目標、默認新草稿、鑰匙串重啓重連與200字節單次傳輸通過（E54） | 005 HTTPS原生證書拒絕與佈局通過（E62），實際跨主機受信證書和設備仍缺 |
| WP-09 | 固定 MLX 生成／取消／適配器，E01／E04／E08 | 最終 UI／App 新配置回歸與跨端目標鏈 |
| WP-10 | NVIDIA固定組合適配器、產品路由和協議完成合同已集成；本機CPU組件E28、真實預檢阻斷E29，003原生仍明確NVIDIA未就緒（E54）；005原生未知CA拒絕與禁傳輸已驗（E62） | 受信HTTPS跨主機接入、指定NVIDIA實機及006原生復驗；不得回退CPU冒充CUDA |
| WP-11 | 本機表單／配方／預設已有 E07／E08，005 靜態聲明與原生參數保存 E57／E63；來源組關係與開發草稿保存 E64／E67 | 006劃分關係與最終執行鏈復核 |
| WP-12 | 固定SFT、監督與檢查點已有E04；005參數聲明已驗；來源組E64—E67、006包內E70—E71及原生預覽恢復／應用／草稿／導出／重啓E72通過 | 指定NVIDIA訓練及同份產物仍待驗；E72只做CPU分詞和數據關係，不代表新模型訓練或質量通過 |
| WP-13 | 本地真實建議、預覽應用撤銷和控制隔離，E06 | 如本版開放遠程建議，連接／發送範圍另實現驗收 |
| WP-14 | 嚴格凍結評測／候選門禁；LoRA與量化真實失敗拒絕（E05、E22）；004新數據192步實驗已真實評測和導出，仍失敗（E56） | 新LoRA真實達標及最終包；舊v2與新v3失敗分別保留，均不登記 |
| WP-15 | 本輪僅首期 SFT LoRA，擴展方法未選入 Ver2 組合 | 額外方法不可啓動；首期 NVIDIA SFT 仍繼續 |
| WP-16 | 16a 本地 KV 對照與隔離已驗（E07） | 16a NVIDIA；16b 前綴／併發調度／圖捕獲等擴展未開放 |
| WP-17 | 普通草稿／MTP／DFlash 未選入本輪且無正式實現 | 保持未開放，不承諾推測提速 |
| WP-18 | Tiny-SD 生成／圖片 LoRA／導出功能通過（E09）；003恢復後原圖新導出解碼、舊適配器新導出並另配基座生成一圖通過（E52、E53）；015一次普通圖片生成、保存及雙文件RGB512×512完整解碼通過（E103） | 固定質量失敗；單張視檢不改原質量結論，新增 VAE／卸載選項須獨立對照 |
| WP-19 | 固定 SVD 圖生視頻、時間元數據和導出（E10）；003恢復後視頻新導出完整解碼14幀／7FPS／2秒、字幕第二版VTT讀取通過（E53） | 運動質量失敗；字幕沒有重算視頻，視頻訓練／切片擴展未實現 |
| WP-20 | 固定 Kokoro TTS、腳本修訂與獨立導出（E11、E21）；003恢復後原音頻與腳本第二版新導出、24kHz單聲道PCM16／8.05秒解碼通過（E53） | 尚無人工聽評；腳本修訂沿用原WAV，未重合成，音頻訓練／ASR不支持 |
| WP-21 | 兩輪實際運行、忙碌阻斷、明確復用與下游失效（E12、E13） | 最終同包回歸；沒有合成成片能力聲明 |
| WP-22 | 測試提供方協議和普通 UI 生命週期（E14） | 實際提供方商業授權及最終原生來源配置另驗 |
| WP-23 | 合併／蒸餾未選入本輪且無正式路徑 | 如後續選入，另定輸入兼容、獨立產物和質量閉環 |
| WP-24 | 固定MLX權重量化、原模型對照、准入拒絕及導出通過（E22） | 已選候選質量失敗；Core ML／ANE未選入 |
| WP-25 | Heretic／Abliterix未選入且未實現 | 沒有相關支持或質量聲明 |
| WP-26 | 已測 CPU 範圍為 Kokoro TTS | 不能稱 CPU 文本／OpenVINO／AMD／Intel 已支持 |
| WP-27 | 分離式 Prefill／Decode 雙服務本輪明確延後 | 不與單進程 Prefill 分塊或本次遠端執行協議混同 |
| WP-28 | 28a基礎、28b新遷移、備份／恢復與可恢復清理，E15—E18；003完整備份、故障遷移、原生舊庫遷移與完整恢復已驗，十二項新導出及限定獨立使用通過（E44、E47、E49、E51—E53）；同恢復庫重啓後目標、默認與草稿延續通過（E54） | 005成功切庫與同庫重啓已驗（E60、E63），007指定GUI故障回連及修復空庫遷移通過（E76）；乾淨安裝與其他原生路徑繼續 |
| WP-29 | 29a／29b多類導出與診斷已有；001中斷恢復E34，003完整升級／回滾／再次安裝E45，恢復後十二項新導出及限定獨立使用E52、E53；005原生診斷ZIP保存與讀回通過（E61）；016當前修訂導出失敗重開後保持並新導出成功（E105）；已有v3後仍導出v2成功，空final待覈實後同號失敗並保持原件（E106）；017 普通歷史 v2 導出與保護有限接受（E109） | E109 窗口失敗，中性提示原生未覆蓋； 006來源組原生E72、007指定故障及保存提示E76—E77已驗；其餘故障出口繼續，指定證據不代表所有異常路徑通過 |
| WP-30 | 持續測試、獨立審查、手冊／組合範圍／證據矩陣，原型保留 | 最終同源包、全適用AC簽署、5名首次用戶及設備證據 |

<a id="四m5-本轮范围与技术备忘"></a>

## 四、M5 本輪範圍與技術備忘

本輪已經按原設計允許的版本組合方式，選擇固定 MLX 4-bit 權重量化；範圍與理由見[Ver2 組合決定](2026-09-10-ver2-scope.md)。下表保留初版審計的技術備忘，額外方法未選入，不能讀成已開放能力。首期 NVIDIA、已選質量失敗和 M6 必需項繼續執行。

| 方向 | 已覈實的技術基礎 | 產品還需完成的最小閉環 |
| --- | --- | --- |
| 固定 MLX 權重量化質量 | 轉換、加載、獨立質量比較、門禁和導出已實際跑通（E22） | 本次候選未達到原定門檻，保留實驗模型；最終同源包另驗 |
| LoRA 合併 | MLX-LM 0.31.3 官方 `fuse.py` 提供適配器合併和保存 | 精確基座／適配器／模塊兼容；寫新模型，保存輸入輸出清單；未合併帶適配器 vs 合併模型逐樣本對照、獨立加載與導出。不能把安裝了庫說成產品功能已完成。[官方源碼](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/fuse.py) |
| QLoRA／全參數中的一個小組合 | 本機安裝版本和官方 `lora.py` 包含 LoRA／QLoRA 說明及 full／lora／dora 類型 | 現有產品訓練檢查只接受固定 SFT LoRA，量化基座被拒。需獨立開放輸入／配方、監督檢查、訓練／檢查點、預算和質量評測。不能直接把底層參數透傳視為支持。[官方源碼](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/lora.py) |
| 教師輸出蒸餾 | 現有文本生成可以作為受控教師輸出的基礎 | 教師模型和參數、生成數據版本、訓練／留出隔離、學生訓練和原教師／學生對照仍需實現；沒有“蒸餾任務已完成”證據 |
| 普通草稿推測 | MLX-LM 0.31.3 `generate.py` 有 draft model 分支 | 固定可兼容且較小的草稿模型；目標／草稿身份和 tokenizer 校驗；實際接受率、取消／回退、開關性能與質量。當前固定 Qwen 0.5B 未選相容更小草稿；MTP／DFlash 不繼承普通草稿支持。[官方源碼](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py) |
| Core ML／ANE | Apple 官方提供 PyTorch 捕獲圖→Core ML 轉換流程，可在 Mac 研究 | 當前沒有產品轉換器、依賴、格式註冊、Core ML 執行器或計算分配證據。先選適配小模型並驗數值，再入口選擇／雙向格式拒絕、導出。允許 ANE 不證明實際算子都在 ANE。[官方轉換流程](https://apple.github.io/coremltools/docs-guides/source/convert-pytorch-workflow.html) |
| Heretic／Abliterix、分離部署、其他設備 | 當前倉庫未找到完整實現；本報告沒有執行這些方法 | 獨立選擇來源、版本、模型、設備和評測；正常能力與目標效果同時報告。分離部署先要遠端服務與 KV 連接器，不是把 Prefill chunk 改小 |

官方 `fuse.py` 的 GGUF 導出白名單只列 llama／mixtral／mistral；當前 Qwen 組合不能據此承諾 GGUF 支持。上述是可實施性判斷，不是本機產品驗收通過。

<a id="五最终-ac-签署前的具体缺口"></a>

## 五、最終 AC 簽署前的具體缺口

| AC | 當前邊界／待閉合事項 |
| --- | --- |
| AC-01 | 012 兩項目四草稿自動保存、選擇、歷史保持與正常重開通過（E96）；013 唯一新生成、作品與六產物完整歸甲（E98）；014 四個來源草稿只歸乙、原記錄及甲上下文保持（E100）。015新增一次普通圖片完成保存，新增業務鏈均歸乙（E103）；該批未切甲或返回乙。017新增圖片運行中切甲、終態後甲樣本及返回乙保存，來源與歸屬鏈通過有限接受（E108）；3秒目標未達且採樣有缺口，未整條簽署 |
| AC-02 | 011 空庫入口通過（E93）；013 六入口續做、甲手選較早任務後跨分類與正常重開恢復通過（E98）；014源碼已修復終態過時離開提示（E99）。013只觀察到提交等待鎖定，014零運行；015圖片批30組快速採樣全在queued前，下一幀已終態（E103），該批實際running只讀與跨項目時序未觀察。017另有完整只讀採樣區間落在running內、首有效甲早於finalizing及返回保存的有限證據（E108）；9.445秒延遲和採樣缺口保留，不簽整條通過 |
| AC-03 | 本機受限導入及官方準備完整預演通過（E20）；遠端信任、最終包另驗 |
| AC-04 | 固定 SFT／圖片數據已驗；僅聲明已選監督配方 |
| AC-05 | 受控提供方真實 UI 通過；不冒稱第三方商業授權 |
| AC-06 | 固定文本 SFT LoRA／圖片 LoRA；其他訓練方法逐項未開放 |
| AC-07 | 本機生命週期／檢查點通過；回環遠端未知狀態、持久取消意圖和原編號恢復已實現復驗，最終包／實機另驗 |
| AC-08 | 本機固定模型真實輸出；003從恢復庫新導出的原模型／4-bit／舊文本LoRA各一次代表性生成均為“4”（E53），不改變質量失敗；跨端及其他模式未繼承 |
| AC-09 | 新字段真實 HTTP 已有；005 訓練參數原生切位置、越界保留與修正保存通過（E63）；全執行鏈和多輪未開放邊界繼續核對 |
| AC-10 | 本機 KV 子集已驗；前綴、分離、媒體緩存實測按實際開放範圍，不借未開功能湊通過 |
| AC-11 | 本輪未選擇推測策略，界面無可啓動實現；無性能支持聲明 |
| AC-12 | Apple／Kokoro CPU限定組合；首期NVIDIA仍必需，AMD／Intel未選入 |
| AC-13 | 固定媒體參數通過；Core ML／ANE本輪未選入，不承諾設備分配 |
| AC-14 | LoRA／量化失敗拒絕與准入軟件已驗；004新數據LoRA的4/32→7/32仍失敗且未登記（E56），真實達標候選仍缺 |
| AC-15 | 本地真實建議正向通過；若開放遠程再補連接和發送邊界 |
| AC-16 | 既有工作流、正文／腳本／字幕修訂及導出證據（E21、E52、E53）保留。014 四類原配方查看、普通草稿載入、模型編號／版本／摘要差異及恢復、收藏正常重開後取消、四草稿來源恢復通過（E99—E100）。015修復既有文字長行右裁與按鈕標籤問題，現有文字／配音文案／字幕原版、修訂版、完整差異和編輯後取消，以及文字短窗滾動通過（E101—E102）。015佈局批零模型運行、新修訂與導出；後續E103一次圖片生成保存不補新修訂驗收。短窗僅文字，播放、完整鍵盤和極限樣本未驗。016當前修訂版2失敗重開後保持並新導出成功（E104—E105）；已有v3後的舊失敗重開仍固定v2導出成功（E106）；017 當前已有 v3 時普通歷史 v2 導出有限接受（E109），故障窗口失敗、中性提示未覆蓋；設備差異和整個AC-16未簽署；019 原生最早歷史查看與舊版普通導出有限子集通過（E112）；020 字符計數修復、33 項相關測試、開發瀏覽器及公司簽名包通過（E113）；同包 16000 字符／200 條字幕保存、正常退出重開、父版與原媒體播放有限子集通過（E114），長列表兩幀空白未解，完整鍵盤、設備差異與整個 AC-16 仍未簽署；021 修復並原生核對人工修訂滾動邊界，差異展開／折疊及逐頁／大幅滾動不帶動背景（E115—E116）；020 偶發空白根因未定，完整 AC-16 不提高；022 編輯與退出確認焦點修復通過源碼、開發瀏覽器和簽名包驗證（E117），已有字幕的編輯首字段、確認返回及取消後重入原生有限子集通過（E118）；完整鍵盤、入口焦點返回與整個 AC-16 仍未簽署 |
| AC-17 | 兩輪真實媒體鏈及第三輪復用失效通過；最終同包回歸 |
| AC-18 | 本地故障／補收、備份恢復已有；獨立回環服務斷連及只補收已實測，跨主機與最終包另驗 |
| AC-19 | MLX量化獨立質量比較及門禁已驗（E22），候選質量失敗；其他實驗未開放 |
| AC-20 | 本地併發、冪等與工作流原子裁決已驗；最終包和遠端再驗 |
| AC-21 | 回環身份、會話憑證、上傳範圍、目的地、取消未知和只補收已有實測；003同包原生目標／默認值、鑰匙串正常重啓後不重輸憑據重連、200B明確傳輸及同編號字節核對已通過（E54）。005原生未知CA拒絕、中文提示與禁傳輸通過（E62）；受信HTTPS跨主機、真實設備鏈及最終包指定遠程原生復驗仍缺 |
| AC-22 | 003完整升級／包回滾／再次安裝、9.35GB完整備份、舊庫副本真實失敗回滾／重試及原生原庫1→3遷移讀回通過（E44—E49）；原生完整恢復、十二項新導出及限定獨立使用通過（E51—E53），恢復庫重啓後目標、默認值與草稿延續通過（E54）。003手工選項目的歷史繞行保留；005成功切入B、清除舊界面及同B重啓通過（E60）；006來源組原生預覽備份恢復、應用、草稿、導出和同庫重啓通過（E72）。007遷移故障中文、日誌目錄失敗回連、未保存輸入及修復空庫切入通過（E76），保存提示通過（E77）。018 前端遲到操作修復、83 項相關回歸及三個開發瀏覽器場景已接受（E110），同庫成功刷新保留；018 原生普通歷史讀取、導航重開與正常退出有限子集另已接受，未觸發跨庫遲到請求；乾淨安裝與跨切庫遲到舊請求原生仍缺 |
| AC-23 | 開發瀏覽器鍵盤草稿持久化與截圖證據保留（E23）；011 原生四種窗口寬度 × 深淺色、320 彈窗、隱藏重開與系統鍵盤導航開啓後的焦點路徑已驗（E92）。011 獨立空庫的深淺色首頁、全局設置與新建彈窗已驗（E93）；018 系統鍵盤導航為 0 時僅觀察模型／項目下拉焦點，未到達工作台，零新任務／模型／保存／導出，完整鍵盤未通過；設置未改、退出及保護恢復完成（[受阻觀察](../../../../.artifacts/keyboard-workflow-ver2-4-018-v1/final-release.json)）。020 重開 200 條字幕後大幅滾動出現兩幀空白，常規上、下一頁恢復，原因未定位；不簽完整長列表渲染或鍵盤路徑（E114）。其餘任務交互和新成員驗收仍需完成；021 原生滾動邊界有限子集通過（E116），關閉後背景可滾；Escape 後焦點為 HTML，不證明入口焦點返回或完整鍵盤，020 偶發空白根因仍未定；022 開發瀏覽器鍵盤焦點前後驗證通過（E117），原生已有字幕編輯、確認返回和取消後重入有限子集通過（E118）；原生入口含鼠標、關閉後為 HTML 焦點，系統鍵盤導航保持 0，不簽完整鍵盤或入口焦點返回 |
| AC-24 | KV固定對照及開發瀏覽器100次交互已驗（E24）；011同包原生初顯20/20最遲3秒內可見、逐輪正常退出及原庫保護通過（E94），保留系統緩存且不計算初顯上界的中位數或p95。完整就緒中位8.197秒／p95 16.435秒／最長45.102秒，波動原因待定位；003舊完整就緒20輪失敗（E50）不變，其餘性能與質量範圍仍待簽署。此前 018 同包靜止切換中乙→甲取得 0.822 秒有效觀察上界，甲→乙受採樣空檔限制未判三秒通過；僅為單向有限子集，不簽完整 AC-24。[觀察與保護恢復](2026-09-13-ver2-4-018-progress.md#项目切换计时观察)。 隨後另一生命週期的靜止雙向補測分別取得甲→乙 0.874 秒、乙→甲 0.846 秒有效觀察上界，第二／第三幀完整圖文一致；此前單向結果及空檔保留，完整 AC-24 仍未簽署。[第二批獨審](../../../../.artifacts/project-switch-timing-ver2-4-018-v1/followup-002/independent-review-001/REVIEW.md)。 只讀復核確認 011 完整就緒長尾的主體在宿主計時內部，具體慢段和根因仍未證實；本次未改性能，也沒有新增 019／020 性能驗收。[只讀診斷](../../../../.artifacts/startup-readiness-diagnosis-ver2-4-019-v1/readonly-001/DIAGNOSIS.md)  023 新增啓動分段並完成一次原生採集：完整就緒 5.263 秒仍超 3 秒，本輪環境檢查等待可核對，但不解釋舊 45 秒長尾、不替代二十輪性能或提高完整 AC-24。[023單次分段](2026-09-14-ver2-4-023-progress.md#e120单次原生分段与保护恢复)  024 靜態索引的十二次離線導入中位有所減少；一次原生完整就緒約 3.938 秒仍超 3 秒，原生診斷有限子集已獲根接受。與023各一輪的差值不證明穩定收益或單一歸因，舊二十輪失敗及完整 AC-24 保持。[024範圍](2026-09-14-ver2-4-024-progress.md) |
| AC-25 | 官方準備→首次生成→保存的開發者預演已完成（E20）；5名用戶同最終包完整驗收缺失 |
| AC-26 | 必需 NVIDIA 訓練同一份達標 LoRA→Apple 產品試用與獨立導出回載；當前未通過 |
| AC-27 | 003升級／恢復後指定十二項新導出的來源、版本、文件集合及字節均核對，3次文本生成、7項讀取／解碼、1次舊圖片LoRA生成和1份原失敗報告讀回通過（E52、E53）。原包independent_use=not_verified不回寫，後續獨立使用另附證據；005 原生診斷另有 E61；016當前修訂失敗重開並新導出成功（E104—E105）；非最新v2保持與空final待覈實後同號失敗通過（E106）；017 普通歷史 v2 導出及 5 文件保存核驗有限接受（E109），pending／reconciled 為 null，中性提示原生未覆蓋；完整已發佈包補登記成功仍未驗，其餘故障出口尚未全簽署 |

<a id="六验证记录与后续操作"></a>

## 六、驗證記錄與後續操作

026 的源碼／Safari 子集與唯一簽名包已接受，一次原生焦點、保存內容讀取及保護恢復的有限子集已接受；完整就緒不是需求第 118 行的初次可見指標。舊表和狀態不因此提高。[026執行進度](2026-09-14-ver2-4-026-progress.md)

以下為此前形成時記錄。

固定公司簽名候選仍為 Ver2.4（025）。已通過正式恢復建立可直接使用的新獨立庫（E126）；同包原生讀到當前字幕版 4／父版 3、200 條／16000 字符，關閉回入口、Enter 重開及臨時編輯的繼續核對／明確放棄有限子集成立（E127）。首次 E125 來源失敗保留；完整鍵盤、020 空白及完整 AC／M0—M6 不提高。本次宿主約 5.450 秒仍超 3 秒；原失敗、完整鍵盤、舊空白及全部 WP／AC／M 階段原文保持。[本次範圍](2026-09-14-ver2-4-025-progress.md)

以下 E124／E125 及更早記錄保留形成時原文。

當前固定候選已為 Ver2.4（025）。E124 源碼／Safari／36 項測試與公司簽名包已接受；E125 保留恢復來源讀取失敗，僅錯誤彈窗回焦與退出保護成立，保存內容和編輯未驗。先糾正獨立庫合法恢復準備，不原樣重啓該副本或放寬產品來源檢查；單次宿主完整就緒仍超 3 秒。完整 AC／M0—M6 不提高。[025範圍與原件](2026-09-14-ver2-4-025-progress.md)、[根原生記錄](../../../../.artifacts/work-revision-return-focus-next-v1/native-run-001/root-native-acceptance.json)。

以下 024 及更早驗證記錄保留形成時原文。

當前固定候選為 Ver2.4（024）。E121 靜態索引、離線對照與唯一公司簽名包已接受；E122 單次完整就緒約 3.938 秒仍超過 3 秒，本次原生診斷與保護恢復有限子集已獲根接受。023 原單輪與 011 二十輪歷史結果不回寫，不據單輪差值宣稱穩定性能收益。020 偶發空白、完整鍵盤及完整 AC／M0—M6 仍待驗。[024範圍與原件](2026-09-14-ver2-4-024-progress.md)。

歷史退出掃描只覆蓋固定 App 與捆綁控制；舊獨立回環服務仍運行，不能稱全部產品進程已停。舊原件不改，另見[進程範圍更正](2026-09-14-ver2-4-022-progress.md#历史退出检查范围更正)。

下列 018 及更早驗證記錄保留形成時原文。

初版只讀審計的源碼、30個工作包／27個AC覆蓋、文檔負例與原設計摘要檢查繼續保留在[原審計清單](../../../../.artifacts/implementation-audit-20260910/manifest.json)。本次更新匯總之後的真實執行，不能把舊審計快照描述為當前源碼的全部測試結果。E20起逐項附原始報告、哈希和範圍。

當前固定候選為 Ver2.4（018）。E110 的遲到結果操作修復、83 項相關前端測試、TypeScript 檢查、3 個開發瀏覽器場景、唯一公司簽名包，以及同庫原生歷史讀取、導航重開與正常退出有限子集已接受。原生普通讀取未觸發跨庫遲到請求，AC-22、Rust 宿主競爭與完整 M0—M6 仍待驗。[018執行進度](2026-09-13-ver2-4-018-progress.md)、[簽名包接受](../../../../.artifacts/integration-ver2-4-018-v1/root-bundle-acceptance.json)、[原生有限接受](../../../../.artifacts/integration-ver2-4-018-v1/native-readonly-001/root-native-acceptance.json)、[E110首次文檔接受](../../../../.artifacts/integration-ver2-4-018-v1/root-docs-E110-acceptance.json)。本節當前入口的後續勘誤及重新運行的既有校驗、21 項測試見[本次勘誤回執](../../../../.artifacts/integration-ver2-4-018-v1/docs-followup-001/result.json)。

017 歷史（E107—E109）：Ver2.4（017）的中性提示、83／28 項相關測試、唯一構建、簽名整包和凍結來源已接受（E107）；圖片生成／項目切換原生有限子集已獲根接受（E108）；普通歷史 v2 導出與保護有限接受（E109），故障窗口失敗，中性提示原生仍未覆蓋。首次來源環境失敗及同腳本補充執行記錄保留；016 A／B 仍歸 E105—E106，首次 SQL 退出 1 及投影修正、17 項重算加 9 項原現場沿用和 13 項原生觀察不回寫。該批結構檢查、校驗器 21 項正負例、五文件鏈接／表格及歷史字節檢查見[E109歷史文檔校驗](../../../../.artifacts/integration-ver2-4-017-v1/docs-update-003/result.json)；[E108舊回執](../../../../.artifacts/integration-ver2-4-017-v1/docs-update-002/result.json)、[E106舊回執](../../../../.artifacts/export-recovery-ver2-4-016-v1/docs-B-update-001/result.json)、[E104／E105舊回執](../../../../.artifacts/export-recovery-ver2-4-016-v1/docs-update-001/result.json)、[015圖片批回執](../../../../.artifacts/project-running-ver2-4-015-v1/docs-update-001/result.json)和[佈局批回執](../../../../.artifacts/work-revisions-layout-ver2-4-015-v1/docs-update-001/result.json)保留。E01—E108、舊015／016進度、011性能歸屬、舊質量失敗和兩輪已用預算保持。完整包成功覈實、導出中性提示原生、3秒目標與採樣缺口、指定 NVIDIA、跨主機、乾淨安裝、遲到舊請求、五名首次用戶、完整 AC 和 M0—M6 繼續。[017歷史進度](2026-09-13-ver2-4-017-progress.md)
