<!-- translation-navigation:start -->
[简体中文](../../../../scripts/desktop/MEDIA_RUNTIME_PLAN.md) · [繁體中文](MEDIA_RUNTIME_PLAN.md) · [English](../../../en/scripts/desktop/MEDIA_RUNTIME_PLAN.md)
<!-- translation-navigation:end -->

<a id="媒体内置运行时打包方案"></a>

# 媒體內置運行時打包方案

結論：採用兩個獨立的固定入口運行時，分別封裝當前已驗證的 Diffusers Python 3.13 和 Kokoro Python 3.10；沿用現有控制層快照、啓動授權、進程組取消和產物收集合同。當前階段是打包設計與本機依賴盤點，尚未證明媒體運行時已隨 App 可用。

<a id="当前证据"></a>

## 當前證據

2026-09-10 對本機環境只讀盤點，未執行 GPU 任務：

| 組合 | 當前 Python | site-packages 文件字節 | Mach-O 文件數 | 當前依賴鎖 |
| --- | --- | ---: | ---: | --- |
| Diffusers 圖片／視頻 | 3.13.9 | 915,126,975 | 65 | `adapters/media/requirements.lock.txt` 已固定版本與 wheel SHA |
| Kokoro 中文配音 | 3.10.19 | 1,037,612,224 | 112 | `.artifacts/m4-media/tts/requirements.lock.txt` 含本機 wheel URL，需歸一化 |

以上字節包含當前環境所有包與緩存，不能作為最終 App 體積。兩個環境的第三方擴展沒有非系統絕對 `LC_LOAD_DYLIB` 引用；部分庫自身 `LC_ID_DYLIB` 仍是構建路徑，打包後需統一重寫並重新檢查。Python Framework、資源和實際加載行為仍需驗證。

FFmpeg 當前來自 `/opt/homebrew/bin`。遞歸盤點 FFmpeg、FFprobe 及非系統動態庫共 19 個文件、38,450,464 字節；運行版為 8.1.1，當前構建配置包含 `--enable-gpl --enable-version3 --enable-libx264`。必須把實際二進制閉包、構建配置和許可一起納入候選包，不能只複製兩個命令。此方案未授權對外發佈，也未把本地運行證據當作分發許可或公證結果。

盤點證據保存在 `.artifacts/desktop/media-packaging-review/{diffusers,kokoro,ffmpeg}.json`，對應腳本也保留在該目錄，可重新執行。

<a id="已定位的搬移障碍"></a>

## 已定位的搬移障礙

1. 兩類配方分別明確檢查 Python 3.13 和 3.10。將它們強行合成一個環境會改變已經驗證的組合，應保留兩個運行時。
2. `workers/media_worker.py:command_for` 當前用 `sys.executable -u image_cli.py/video_cli.py` 啓動固定子進程。凍結後二進制不是任意腳本解釋器，必須新增限定的圖片／視頻子命令入口，並維持同一進程組。
3. `video_cli.py` 通過 PATH 尋找 FFmpeg／FFprobe；圖片與視頻源碼還通過 PATH 調用 `sysctl`。候選包需要自己的媒體命令目錄，並只加入可信系統目錄或改為 `/usr/sbin/sysctl`。
4. 配方會讀取自身源碼、控制層解析器和 lock 的摘要。凍結模塊必須帶同份真實源文件，不能用不存在的 `.py` 路徑或開發目錄替代。
5. TTS 當前按 `sysconfig` 的 site-packages 路徑遍歷依賴；在凍結環境可能得到空清單。需要基於包內實際 metadata 和固定運行時清單生成完整依賴身份，不能把空依賴列表視為已核驗。
6. 當前控制層只支持媒體外部 Python 路徑。必須新增包內二進制路由；不能把 `.artifacts` 環境寫入 App 默認配置。
7. Tauri 資源通配複製會展開符號鏈接。現有 MLX 已通過還原 PyInstaller 鏈接並重簽解決，同樣步驟需覆蓋兩個媒體運行時與媒體工具目錄。

<a id="最小改动范围"></a>

## 最小改動範圍

<a id="桌面打包"></a>

### 桌面打包

在 `scripts/desktop` 新增兩個固定入口和一個按 profile 構建的打包腳本，生成 `resources/diffusers/ailab-diffusers` 與 `resources/kokoro/ailab-kokoro`。每個入口僅開放 `probe`、`preflight`、`launch`、`run`；Diffusers 另開放內部 `image-cli`、`video-cli`。沒有任意腳本、`-c` 或用戶傳入模塊入口。

`launch` 保留現有 `process.json`、控制器身份、快照摘要、`start-authorized.json` 協議。`media_worker` 的凍結分支改為同一二進制的限定子命令；外部 Python 分支仍使用現有腳本。圖片與視頻子進程繼續繼承控制層分配的獨立進程組。

打包必須同時收集：

- 當前實際依賴的 metadata、Python Framework、動態模塊和原生庫；Diffusers 的 pipeline／模型動態導入，Torch 所需資源與符號鏈接。
- Kokoro／Misaki、中文分詞與拼音詞典資源、音頻動態庫，以及真實入口導入鏈涉及的包。固定模型權重由模型庫管理，不隨運行時重復打包。
- 與同次 stage 一致的 worker、adapter、受限媒體解析源碼、依賴 lock 和入口源碼摘要。
- Python 與全部實際隨包依賴的許可證、NOTICE、包名版本和 wheel SHA。
- FFmpeg／FFprobe 動態庫閉包，重寫為包內相對加載路徑，保存構建版本及所需許可文件。

兩套媒體環境單獨從完整哈希鎖建立打包 venv，不修改現有 `.artifacts/m4-media` 驗收環境。TTS 將本機 wheel URL 歸一化為名稱、版本、wheel 文件名和 SHA，保留原清單作歷史證據。Diffusers Torch 必須沿用官方 wheel SHA，不能用同版本的其它構建替代。

`stage_control.py`、`build.sh`、`seal_runtime.py` 和 `verify_bundle.py` 擴展到這兩個 profile。先簽嵌套代碼、還原鏈接和重算各 runtime manifest，最後簽外層 App；每個 probe 返回 profile、Python／依賴版本、設備狀態、源碼清單摘要和 runtime manifest 摘要。

<a id="控制层与原生主进程"></a>

### 控制層與原生主進程

建議在 Settings 末尾新增 `bundled_media_worker`、`bundled_audio_worker` 和對應 CLI 參數。Rust 只傳從 App 資源目錄解析出的固定絕對二進制路徑；WebView 不接收這些路徑或控制 token。

媒體環境選擇、檢查和啓動均按同一優先順序：用戶明確選擇的外部 Python；否則使用當前已探測的包內運行時。內置缺失或探測失敗應明確阻斷，不退回開發目錄、系統 Python 或靜默更換執行設備。切換為內置時保留版本檢查和活動任務保護。設置界面需要分別顯示圖片／視頻與配音的真實探測狀態；“高級選擇 Python”保留為可選入口。

`Media.environment` 為包內運行時調用固定 `--mode probe`，身份綁定 binary、runtime manifest 與源碼摘要；`Media.command` 的 preflight／run 和 Service 的 launch 必須同路由。複製 App 或切換恢復庫後的新檢查應重新生成運行身份；已有運行證據保持原快照。

<a id="步骤与验收"></a>

## 步驟與驗收

1. 固定源碼與依賴 → 用完整哈希鎖創建兩個新的打包環境，驗證實際版本和許可清單；不改已凍結模型、配方參數或歷史證據。
2. 構建與簽名 → 產生兩個 onedir 運行時，檢查所有 Mach-O 依賴與鏈接均在包內或系統路徑；精確簽名、源清單和運行時清單逐項通過。
3. 搬移後探測 → 將運行時複製到帶空格的新目錄，從空工作目錄、`PATH=/usr/bin:/bin`、無項目 Python／模塊路徑啓動 `probe` 與 preflight。用真實本地模型和受限輸入覈實失敗與成功分支。
4. 搬移後真實執行 → Tiny-SD 512×512／20 步生成；圖片 12 步 LoRA 訓練與同基座適配器試用；SVD 14 幀／7 FPS 視頻並通過隨包 FFprobe 與解碼；Kokoro 短中文生成 24 kHz 單聲道 PCM WAV。全部由控制層協議授權啓動，覈實產物摘要、實際配置、原模型未改與進程回收。
5. 真實取消與異常 → 視頻或圖片運行中正常取消、控制器退出後子進程回收；錯誤 profile、任意腳本參數、變化的源／模型／產物、缺失動態資源均明確拒絕。無需重復改變質量閾值。
6. 最終 App → 用同一次 stage 構建全部 sidecar 與前端，驗證簽名及各 probe；在該確切 `.app` 的原生窗口檢查內置能力，實際生成並預覽媒體，退出回收後重啓復讀記錄。

只有第 6 步完成後才能稱為“媒體已內置到本次 App 且本機驗證通過”。獨立 Mac、Developer ID、公證、安裝分發和公開發佈仍是單獨的驗收事實。
