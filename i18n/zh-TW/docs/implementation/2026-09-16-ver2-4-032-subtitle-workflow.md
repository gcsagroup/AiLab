<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-16-ver2-4-032-subtitle-workflow.md) · [繁體中文](2026-09-16-ver2-4-032-subtitle-workflow.md) · [English](../../../en/docs/implementation/2026-09-16-ver2-4-032-subtitle-workflow.md)
<!-- translation-navigation:end -->

<a id="ver24032字幕键盘保存与历史导出e142"></a>

# Ver2.4（032）字幕鍵盤、儲存與歷史匯出：E142

固定 032 公司簽章 App 的本輪字幕流程已獲根接受：功能鏈鍵盤操作、播放器與展開／摺疊取樣、繼續／放棄臨時修改、一次儲存 v5、同庫重新開啟、明確選擇歷史 v4 匯出、兩次正常退出及保護恢復完成。渲染檢查使用容器捲動，不能稱全部動作都是鍵盤。本輪沒有重新建置或執行模型，完整 AC22、AC27、M0—M6 和發布狀態不提高。

<a id="候选与验证层次"></a>

## 候選與驗證層次

原始碼基線為 `bff931f89528ced651dc4fb30ff37b90e5bc9fb9`，沿用固定 Ver2.4（032）簽章包，162 項生產來源已綁定。相關控制測試 70 項、前端測試 64 項通過；交付匯出控制測試另有 31 項通過，控制兩組各保留 2 項警告。它們不是本輪原生操作的替代證據。[前檢](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/root-preflight.json)、[修訂控制測試](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/control-tests.log)、[前端測試](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/frontend-tests.log)、[交付測試](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/delivery-tests.log)

準備階段的 8 項測試、守衛 16 項邊界測試、啟動器 39 項 AST 合成門檻及停機驗收器 12 項合成測試分層記錄；只證明各自範圍。新 A 來自已審歷史備份恢復，守衛沿用 47 項保護基線與原 selector 檔案身分恢復合同；準備不向既有工作庫寫入。[準備接受](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/root-preparation-acceptance.json)、[守衛檢查](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/guard-001/check-result.json)、[啟動門檻](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/launcher-review-001/gate-tests.json)、[驗收器測試](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/checker-tests-result.json)

<a id="首轮真实操作与保存"></a>

## 首輪真實操作與儲存

功能鏈使用鍵盤，從作品入口開啟原 v4 字幕；05 是載入黑畫面，06 的容器 Space 是捲動，07 至 08 才記錄原影片播放從 1 秒到 2 秒。渲染檢查另用 CUA 容器 scroll，展開和摺疊時取樣首、中、末字幕及逐頁往返；11 是差異尾部，12 才是字幕列表尾部。摺疊後 160 頁位置的兩幀只證明兩個取樣時點未空白，不證明連續無空白或舊 020 根因已修復。[鍵盤入口](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/04-v4-open-keyboard.ax.txt)、[實際播放](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/07-original-playback.ax.txt)、[播放結束](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/08-original-video-ended.ax.txt)、[字幕列表尾部](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/12-expanded-reverse-tail.ax.txt)、[摺疊位置](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/16-17-collapse-down160.ax.txt)

編輯時鍵盤定位末條，輸入 36 字元臨時文字；關閉提示中先繼續編輯，臨時文字保持，再明確放棄，返回入口後重開仍為原 v4。隨後再次編輯末條為 `native032 keyboard subtitle tail xxxxxxxxxxxxxxxxxxxxxxx`，只儲存一次獨立 v5。[臨時編輯](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/26-temporary-tail.ax.txt)、[繼續編輯](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/28-continue-restores-tail.ax.txt)、[放棄後重開](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/31-reopen-still-v4.ax.txt)、[儲存 v5](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/33-v5-saved.ax.txt)

首輪正常退出 0。停機檢查確認新增 v5 `work-revision-2ae05533e4e1418cbd9d8e2d97b6d658` 的父版本為原 v4，僅末條變化，仍為 200 條／16000 字元；恰新增 1 個修訂、1 個字幕產物及 1 條命令，新增事件與模型任務為 0。頁面上下文最終回到原值；產生的 v5 VTT 為 54989 位元組。原影片與歷史 v4 未被這次字幕修訂替換。[首輪退出](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/app-first/exit.json)、[停機儲存檢查](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/saved-check.json)

<a id="重开导出与证据边界"></a>

## 重開匯出與證據邊界

第二次同 App、同 A 重新開啟顯示目前 v5 及其原 v4 父版本，隨後明確選擇歷史 v4，匯出編號 `export-1bfb2c6b4c04497b995bc3285b6498e1`。中文空格目錄內實際 5 檔案：`work/video.mp4`、`revision/subtitles.vtt`、`recipe.json`、`object.json` 和 `manifest.json`；其中 4 個載荷檔案加清單，摘要與登記一致。匯出字幕精確屬於歷史 v4，目前 v5、歷史 v4 與原影片保持，不把目前 v5 誤當成已匯出版本。[重開 v5](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/36-reopened-v5.ax.txt)、[選擇歷史 v4](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/38-historical-v4-selected.ax.txt)、[完成介面](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/47-export-completed.ax.txt)、[歷史匯出檢查](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/exported-check.json)

匯出階段新增 1 個匯出任務、9 個預期事件，沒有新模型任務；兩次正常退出均為 0，最終頁面上下文回到原值。162 項生產來源保持；47 項保護記錄中 44 項嚴格不變（含缺席項與重複路徑），selector 原位元組、inode、權限恢復，ctime 差異保留，兩份 startup 日誌允許更新。App、控制及守衛均已停止，恢復與釋放回執齊全。[第二次退出](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/app-second/exit.json)、[守衛恢復](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/selector-guard/restored.json)、[釋放](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/selector-guard/released.json)、[根讀回](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/root-readback.json)、[根接受](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

根保留 47 張 JPEG、317 條動作記錄，其中 216 次 pressKey、95 次 scroll、6 次 typeText。40 實際停在唯讀路徑框，不是真正目錄面板；41 的中文 typeText 丟字、貼上逾時及全選無效後，Escape 退出並重開 GoTo，輸入 ASCII 父目錄，再 Right 與 6 次 Down，42 精確選中中文空格目錄，43 傳回正確路徑。貼上逾時沒有 actions 條目，僅由原 CUA 執行記錄及根讀回說明；48 退出圖像縮小，正常退出由原 AX 與退出 0 補足。[精確目錄選擇](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/42-native-directory-keyboard-selected.ax.txt)、[目錄傳回](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/43-directory-returned-to-app.ax.txt)、[根限制記錄](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/root-readback.json)

獨立審查接受本輪完整字幕操作與歷史匯出流程，範圍限目前固定套件、新 A 和已記錄系統條件。原影片播放不表示字幕燒錄或播放器已載入外置字幕；根接受措辭勘誤及原摘要鏈保留。 [獨立審查](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/independent-native-review.md)

操作記錄器曾因證據檔名重複出現 `EEXIST`，原失敗保留並修正後續命名，不是產品資料失敗；根保留動作日誌、分步 AX 和圖像。自動環境探測與模型執行分開，本輪不能稱零探測。舊 020 原因仍未明，完整 AC27、乾淨安裝、品質准入、指定 NVIDIA 與同份產物回程、M0—M6 及發布門檻保持。[動作日誌](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/actions.jsonl)、[擷取記錄](../../../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/captures.jsonl)、[交付矩陣](2026-09-10-current-delivery-matrix.md)

本頁 `.artifacts` 連結為本機證據，不隨 GitHub 原始碼上傳。全部正式文件與歷史記錄繼續提供簡體、繁體、英文版本。
