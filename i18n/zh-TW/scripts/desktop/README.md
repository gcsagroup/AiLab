<!-- translation-navigation:start -->
[简体中文](../../../../scripts/desktop/README.md) · [繁體中文](README.md) · [English](../../../en/scripts/desktop/README.md)
<!-- translation-navigation:end -->

<a id="桌面宿主开发与本机候选构建"></a>

# 桌面宿主開發與本機候選構建

應用身份固定為 `org.gcsa.ailab`，簽名使用 `Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)`。這是本機候選簽名；尚未完成 Developer ID 簽名、公證或獨立機器發佈驗收。

當前候選僅面向 Apple Silicon / macOS 26 及以上：本機 Python 3.13 框架的 Mach-O 最低系統版本為 26.0。不能將桌面殼自身可支持的舊系統版本當作整包兼容證據；後續需要更低版本支持時，應替換為相應構建的 Python 運行時並在目標系統驗證。

<a id="启动"></a>

## 啓動

App 開發、運行、原生測試和交付共用 `apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app`。完整構建使用 `scripts/desktop/build.sh`，隨後用 `scripts/desktop/run.sh` 啓動；`dev.sh` 也調用同一入口，避免另開 debug App。`run.sh` 先核對版本和凍結清單中的身份，舊包不會被誤當作當前候選。網頁熱更新仍可單獨運行 `npm run dev`，但網頁檢查不能替代 App 原生驗收。開發控制服務需要已準備的 `services/control/.venv`，可用 `AILAB_DATA_DIR` 指定獨立測試目錄、`AILAB_WORKER_PYTHON` 指定獨立 MLX 環境；生產包不接受這些開發覆蓋值。

關閉窗口保留本機後台任務；點擊 Dock 圖標重新打開窗口。退出應用先顯示本機任務停止提示，確認後先請求控制服務退出並回收執行器。宿主只管理自己啓動的進程句柄，未使用進程名稱掃描或全局終止。

<a id="前端合同"></a>

## 前端合同

- `invoke('api_request', {request:{method,path,body?,idempotency_key?}})`：成功返回業務 JSON，失敗返回標準錯誤結構。
- `invoke('api_media', {artifactId})`：只讀取已登記產物的受認證內容接口，限定 PNG、MP4、WAV 與 64 MiB，返回 `{media_type,base64}`；界面生成臨時 Blob URL 預覽並在離開時釋放。
- `invoke('host_status')`：返回服務狀態、中文說明、可用時的 PID、端口，以及宿主受控來源設置 `market_fixture_origin`（默認 `null`）。
- `invoke('restart_control')`：已運行時直接返回當前狀態；服務退出後啓動新進程，不自動重跑任務。
- `invoke('pick_import_path', {kind:'model'|'dataset'|'image-dataset'|'material'|'backup'})`：打開原生選擇器，取消返回 `null`，選取後返回 `{path,grant_id}`。圖片數據選擇目錄，素材選擇 PNG 文件；導入或恢復計劃攜帶此授權編號。
- `invoke('pick_worker_python')`：選擇已有 Python 環境並在原生確認框中應用，返回完整設置；取消返回 `null`。前端不能通過通用代理替換執行程序。
- `invoke('pick_media_python', {engine:'diffusers'|'kokoro'})`：選擇圖片/視頻或中文配音的獨立 Python 環境，使用相同原生確認和設置版本核對，分別更新 `media_python` 或 `audio_python`；其他環境保持原值。
- `invoke('use_bundled_worker')`：無參數切回內置 MLX，檢查內置執行器存在後清除外部 Python 選擇，並返回完整設置。
- `invoke('use_bundled_media', {engine:'diffusers'|'kokoro'})`：檢查對應內置執行器存在後，只清除該類外部 Python 選擇，並返回完整設置。
- `invoke('pick_export_directory')`：選擇已有導出目錄，取消返回 `null`，選取後返回 `{path,grant_id}`；這是當前會話的導出寫入授權，與導入讀取授權分開。
- `invoke('use_restored_library', {restoreId})`：僅接受已完成的恢復記錄。宿主向控制服務現場驗證完整文件，以獨立宿主憑據凍結新寫入，停止舊服務後啓動新目錄；健康檢查成功才保存選庫設置，失敗會重新連接原工作庫。
- `invoke('configure_market_fixture', {origin})`：顯式設置 `http://127.0.0.1:端口`，或傳 `null` 關閉夾具來源。只登記固定 `fixture-provider`，不啓動提供方。宿主先申請無活躍寫入、下載或執行器的重配置門禁，再在同一工作庫重啓；健康檢查和獨立 `host-settings.json` 持久化成功後返回 `{market_fixture_origin,status}`，啓動或保存失敗會恢復原配置。該設置不寫進工作庫備份，也不從環境變量隱式注入。
- 事件 `host-status` 通知控制服務狀態變化；前端也可以讀取狀態完成首次同步。

認證令牌保存在 Rust 內存中；WebView 不持有控制服務令牌。切換工作庫和重配置另用僅從 stdout 握手發給 Rust 的宿主憑據，不寫入開發橋接的令牌文件。代理只訪問固定回環地址、固定接口前綴和已登記業務資源，拒絕重定向、路徑穿越、額外認證頭、前端自行創建導入授權以及直接調用工作庫激活或宿主重配置接口。

完整備份以短數據庫鎖凍結 SQLite，再按不可變引用複製模型、數據、適配器、凍結評測與原運行證據。恢復先檢查完整閉包、數據庫結構、文件摘要、讀取授權及獨立目標授權，隨後恢復到已有目標目錄下的新子目錄。macOS 無覆蓋原子重命名保證發佈時不會替換已存在目錄。計劃與命令回執保存在原庫的 `backups/.commands`，不寫原業務數據庫；同一命令在服務重啓後仍可覈實原恢復結果。原始快照和產物文件保持原字節，數據庫中的遷移引用明確記錄原快照、原摘要及路徑映射。恢復清除原機器外部 Python 選擇與舊冪等響應，新運行默認使用本包內置執行器。

當前數據庫版本為 4；新庫直接創建當前結構。舊庫按 v1→v2→v3→v4 逐步遷移：前兩步新增分頁及按任務查詢最近執行的索引，v4 標記來源組劃分及成對數據資源語義，保持原表結構和業務正文。每一步都先在 `migrations` 保存包含 WAL 的一致副本、SHA 和持久回執，再事務更新版本；失敗回滾並禁止初始化運行器，未知未來版本只讀拒絕。初始回執完成前的臨時目錄不會妨礙中斷後重試。完整備份支持數據庫版本 1、2、3、4，清單版本必須與實際數據庫一致；單庫不超過 1 GiB，數據庫與最多 50000 個引用文件合計不超過 32 GiB。資源檢查使用可重復的只讀迭代，恢復按 512 行遷移引用，避免百萬條元信息全部駐留內存。

集合接口每頁只從 SQLite 讀取限定行數。任務、作品、工作流與執行歷史默認最新在前，降序游標帶 `desc:`，舊升序游標不能混用。任務列表返回概要和最近執行的狀態摘要，草稿在單任務接口讀取；單任務附首 100 條執行摘要及下一頁游標，完整快照、正文和產物只在單執行接口讀取。前端顯式加載下一頁，不在後台自動拉完整集合。

存儲清理先生成包含精確路徑、字節數、文件摘要和理由的計劃。用戶明確執行後，只把當前庫 `assets` 中沒有項目、運行、檢查點、備份或恢復引用的不可變資產移到本庫 `trash`，保留原始清單並支持恢復；沒有永久刪除接口。原運行證據、項目外下載與緩存不在清理範圍內。計劃後引用或文件變化、存在運行/切庫/備份操作時均拒絕移動；恢復時原位置被佔用也拒絕覆蓋。同一命令可在中斷後覈實並繼續，清理期間仍可讀取已有內容。

<a id="构建与验证"></a>

## 構建與驗證

`scripts/desktop/version.json` 是唯一版本源。小修改遞增括號內構建編號，新增功能調整功能版本，大範圍變化調整主版本；例如版本 `2.2.0`、構建 `7` 顯示為 `Ver2.2(007)`。`build=0` 只表示該功能版本尚未產生候選包。每次實際完整候選構建開始時，`app_version.py begin` 只遞增一次，並同步 package／Cargo／Tauri／控制層／前端版本；內部執行器打包和測試不另佔編號。`CFBundleShortVersionString` 保存功能版本，`CFBundleVersion` 保存構建編號，界面和診斷讀取生成常量，“技術預覽”等驗收狀態獨立顯示。不要手工編輯生成字段。

完整候選構建使用互斥目錄保護固定輸出。每次編號和開始、成功或失敗記錄保存在 `.artifacts/desktop/version-history/build-NNNN.json`，失敗不回收編號；進程被強制殺死留下的 `building` 和互斥目錄須在確認無構建進程後處理。結束時版本腳本核對固定路徑的 `Info.plist`、凍結版本摘要及當前源碼；成功記錄同時固定完整包驗證報告摘要。舊 `0.1.0` 證據保留原版號。可運行 `services/control/.venv/bin/python scripts/desktop/app_version.py check` 做只讀同步檢查。

`scripts/desktop/build.sh` 將控制服務、執行器與配方源碼暫存到同一份 `.artifacts/desktop/source-*`，使用獨立打包環境製作自包含控制層、MLX、Diffusers 與 Kokoro 執行器，再執行前端構建、Tauri 構建及簽名檢查。所有執行器的依賴許可隨包攜帶；模型權重和用戶數據由用戶導入，不進入安裝包。`scripts/desktop/toolchain.sh` 只為本次命令選擇本機已有的獨立 Rust 1.95 工具鏈。

媒體運行時分別使用已驗證的 Python 3.13.9 與 3.10.19，不能合併到同一個依賴環境。`runtime-*.lock.txt` 與對應 `sources.json` 固定版本、官方下載地址及 SHA；構建只安裝通過摘要驗證的緩存。`package_media.py` 收集動態模塊、凍結依賴的數據文件、真實源碼和 metadata，並生成許可索引與完整文件清單。所有數據來源匯合後，使用 PyInstaller 自帶展開器解析目錄與 glob，僅排除最終目標 `torch/include/` 下的 `.h`、`.hpp`、`.cuh` 開發頭文件；預編譯運行庫、元數據、許可和其他路徑保持。該規則有兩固定打包環境的專門測試；改過收集範圍的包仍須通過實際媒體配方復驗才能交付。媒體腳本與受限解析依賴也保持原目錄關係，從同一快照複製到資源中的 `workers`、`adapters/media` 和 `services/control`，使運行時身份可逐文件對齊。顯式外部 Python 選擇優先；無選擇時使用宿主傳入的包內執行器，不自動查找開發目錄。

凍結媒體入口只允許完整匹配的標準庫資源追蹤調用，檢查當前解釋器生成的完整選項和繼承的只讀管道，再直接調用固定函數；不會執行傳入的 Python 文本。探測會實際啓動同參數子進程並要求自然退出成功。視頻驗收同時拒絕追蹤器異常、入口執行失敗及資源洩漏警告。

`package_media_tools.py` 將 FFmpeg/FFprobe 的實際動態庫閉包複製到包內，重寫非系統加載路徑、保留許可和構建信息，並逐個簽名。當前來源為啓用 GPL 的本機 FFmpeg 8.1.1，最終分發需按該組合履行相應許可義務；構建成功只證明本機候選，不能替代獨立機器或發佈驗收。

Tauri 資源通配拷貝會展開符號鏈接，因此 `seal_runtime.py` 先還原各自包含運行時的包內鏈接佈局，使 MLX 能從動態庫的真實目錄找到 Metal 資源。最終簽名會改變嵌套二進制，腳本在嵌套代碼完成簽名後重算全部運行時清單，再簽外層 App。`verify_bundle.py` 檢查外層及所有入口的證書指紋、包內鏈接、動態庫路徑和運行時完整性，並將控制清單中的執行器、配方、入口和依賴鎖摘要逐項與內置運行時對齊。

真實運行驗收使用 `verify_mlx_runtime.py`：將整份內置運行時複製到帶空格的新路徑，以僅包含 `/usr/bin:/bin` 的 PATH 和空工作目錄啓動，執行探測、預檢查與持久登記後的授權生成。加上 `--evaluation-snapshot` 會繼續用固定計劃啓動兩個獨立進程，分別加載基線與候選，保留質量報告，不把執行成功當作評測達標。示例：

```sh
.artifacts/desktop/package-venv/bin/python scripts/desktop/verify_mlx_runtime.py \
  'apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app/Contents/Resources/resources/mlx/ailab-mlx' \
  --snapshot .artifacts/m0-mlx/evaluation-20260910-01/candidate-evaluation.snapshot.json \
  --evaluation-snapshot .artifacts/m0-mlx/evaluation-20260910-01/candidate-evaluation.snapshot.json \
  --output .artifacts/desktop/bundled-runtime-acceptance
```

`verify_media_runtime.py` 接受 `--image-snapshot`、`--train-snapshot`、`--video-snapshot` 和 `--audio-snapshot`。它將所需運行時和媒體工具一起複製到帶空格目錄，使用全新 HOME、空 cwd 和最小 PATH 完成真實預檢查與兩階段授權執行；訓練後重新加載新適配器生成圖片，視頻用包內 FFprobe/FFmpeg 獨立讀取並解碼 14 幀，配音檢查完整 24 kHz 單聲道 WAV。`--cancel-video` 在實際完成第一個去噪步後取消，要求沒有完成事件且同組進程自然回收。原驗收快照只讀保留，每次按搬遷後的實際環境重新凍結執行配方。該腳本報告須與最終 App 的源碼清單和簽名一同核對，不能用中間運行時報告替代最終原生 App 驗收。

Rust 代表性測試：`cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib`，覆蓋歸屬回收、無關進程保留、身份錯誤、啓動超時、崩潰重啓、代理路徑與請求邊界。已準備控制環境後顯式運行 `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib real_control_handshake_authentication_and_restart -- --ignored`，檢查真實健康響應、認證、崩潰重啓、會話令牌更新和退出端口關閉。設置 `AILAB_TEST_CONTROL_BINARY` 可用相同測試驗證自包含控制程序。完整應用仍需實際打開，驗證真實業務請求、退出與簽名身份。

<a id="同一候选的启动测量"></a>

## 同一候選的啓動測量

`verify_startup.py` 默認順序啓動固定路徑 App 20 次。每輪從啓動進程前計時，到讀取本輪 PID、版本、構建號和可見首屏回執為止；回執須在項目資源與環境加載完畢、界面經過兩次呈現調度後由原生宿主寫入。腳本隨後等待操作者通過真實 App 菜單確認退出，並覈實控制進程退出，才開始下一輪。腳本不會用健康接口代替首屏，也不會自動強制退出 App。

```sh
services/control/.venv/bin/python scripts/desktop/verify_startup.py \
  --output .artifacts/desktop/startup-acceptance-v1 --rounds 20
```

輸出目錄必須不存在，每輪單獨保存回執、外部耗時和退出結果。報告版本為 `schema_version: 2`；原 `twenty_launch_target_passed` 欄位改為 `twenty_full_readiness_under_3000_ms`，仍統計完整20輪是否全部不超過3000毫秒。該值只描述完整就緒；`initial_visibility_target_passed` 保持 `null`，`initial_visibility_evidence` 為 `not_measured`，初顯目標仍須獨立的20次真實介面測量。失敗輪、慢樣本及舊批次保留，不回寫歷史報告。這是獨立進程啟動測量，保留作業系統檔案快取，不代表系統重啟或乾淨安裝。啟動前會拒絕版本或簽名不符、已有App進程、未結束任務、恢復待處理和活動下載。

<a id="本地候选更新与恢复"></a>

## 本地候選更新與恢復

`candidate_update.py` 只更新本項目固定 App 路徑。先對本地已簽名新候選生成計劃，再用計劃SHA執行替換；雙方必須屬於本項目組織證書，新候選版本必須更高。計劃固定雙方完整目錄摘要、選中工作庫與數據庫內容，執行前再次覈實靜止狀態。新包暫存並校驗後才移動舊包；舊包、新候選來源和回執全部保留。該工具不聯網，不自動啓動App。

```sh
services/control/.venv/bin/python scripts/desktop/candidate_update.py plan \
  --source '.artifacts/desktop/candidates/GCSA AI Lab.app' \
  --output .artifacts/desktop/candidate-updates/update-v1
```

檢查生成的 `plan.json` 後，執行 `apply --plan <计划绝对路径> --sha256 <计划SHA>`。中斷時對同一計劃執行 `recover`，完整替換後需要回退時執行 `rollback`。每個計劃只應用一次，完成或中斷後不重復apply。恢復按磁盤上的實際包摘要判斷，遇到未知包或已佔用位置會停止並保留現場。

替換前的 `database-backup` 保存包含WAL的一致數據庫和庫選擇設置，**不包含模型、素材等資產**。舊0.1.0包只支持schema1；新版運行升級到schema3後，工具拒絕舊包回退，也不降級數據庫。此時必須使用已有完整備份恢復流程。腳本測試通過仍不替代真實舊包升級、失敗回滾和新版原生驗收。
