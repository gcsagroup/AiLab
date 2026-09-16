<a id="gcsa-ai-lab"></a>

# GCSA AI Lab

[簡體中文](../../README.md) · [繁體中文](README.md) · [English](../en/README.md)

本地優先的模型訓練與運行桌面工作台。圍繞項目管理模型、數據、訓練任務、評測和作品，提供語言、圖片、視頻及配音的工作流程。

<a id="当前状态"></a>

## 當前狀態

當前固定公司簽名候選為 **Ver2.4（032）**，簽名組織為 **Global Cybersecurity Alliance Limited**。這是開發候選，完整 M0—M6、乾淨安裝、公證及正式分發驗收尚未完成。

建置前原始碼進展：資料劃分的過時讀取不再清除套用錯誤；人工補收登記交易失敗後可保留原計算結果並恢復重試。相關原始碼測試和瀏覽器元件夾具驗證通過。固定 App 仍為 032，033 尚未建置，本輪原生資料流程未執行。 [原始碼修復與邊界](docs/implementation/2026-09-16-dataset-and-collection-source-fixes.md)

032 字幕流程的功能鏈鍵盤操作、繼續／放棄修改、儲存 v5 和同庫重新開啟已通過；200 條／16000 字元僅末條變化，隨後明確匯出歷史 v4 的 5 檔案包。目前 v5、歷史 v4 與原影片保持，兩次正常退出及資料恢復通過。渲染僅作容器捲動取樣，舊 020 根因仍未明；未重新建置或執行模型，不提高完整 AC 和發布狀態。 [字幕流程與邊界](docs/implementation/2026-09-16-ver2-4-032-subtitle-workflow.md)

以下 E141 及更早記錄保留形成時狀態。

032 診斷目錄完整迴歸已通過：真實三語資料匯入、兩種取消、中文空格目錄 ZIP 儲存及完整性／脫敏驗證完成。同號同庫重新開啟後資料庫與 ZIP 位元組不變，兩次正常退出和資料恢復通過。自動探測並非零，未執行模型；本輪診斷成功不替代完整產物匯出與發布驗收。 [診斷迴歸與邊界](docs/implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md)

以下 E140 及更早記錄保留形成時狀態。

032 已通過真實 Python 符號連結原路徑選擇、三環境儲存、同號同庫重新開啟和恢復內建的有限驗收；兩次停機讀回及原資料保護恢復通過。外部 venv 依賴探測失敗保留，恢復內建後的環境就緒不等於模型執行；原生跨庫競態和診斷匯出仍未涵蓋。 [032 進度與邊界](docs/implementation/2026-09-16-ver2-4-032-python-path-preservation.md)

030 已將工作庫連線隔離修復納入簽章包：原始碼迴歸、整包複核及包內兩項真實控制服務測試通過，原生備份、目標庫啟動失敗復原、成功切庫和同號重新開啟的有限子集已獲根接受，停機讀回通過。切庫、復原或重新啟動後的舊請求不會自動改用新庫身分重送；原生選擇器的非同步競態仍未涵蓋。[030 進度](docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md)

Media 三個導入入口的源碼修復、相關測試與 Safari 驗證已有證據；029 公司簽名包、兩個既有任務中的四個原生入口實例、正常退出及一次停機讀回的有限子集已獲根接受（E137）。未執行真實導入或模型運行。028 工作台四按鈕、027 文字原作品純鍵盤導出與同號重開的既有的有限接受保留。詳細狀態見[當前交付矩陣](docs/implementation/2026-09-10-current-delivery-matrix.md)和[更新記錄](CHANGELOG.md)。

<a id="功能与范围"></a>

## 功能與範圍

- **語言模型**：固定 Qwen2.5-0.5B-Instruct / Apple MLX 組合的生成、SFT + LoRA、檢查點、評測和候選准入。
- **媒體工作流**：圖片生成與 Tiny-SD LoRA、固定 SVD 視頻生成、Kokoro 中文配音，以及分步保存和明確復用。
- **項目與數據**：任務草稿、來源組訓練／驗證劃分、版本記錄、作品修訂、導出、完整備份與恢復。
- **執行管理**：本機執行、獨立執行服務協議、傳輸核驗和中斷恢復。指定 NVIDIA 與同份產物跨端仍待實機驗收。

視頻與音頻訓練尚未開放；媒體工作流分別保存作品，尚不合成為一條配音成片。既有 LoRA 和量化候選質量失敗仍保留，不能把訓練完成或文件可讀取等同質量通過。精確組合和未開放範圍見[候選範圍](docs/implementation/2026-09-10-ver2-scope.md)。

<a id="开发与验证"></a>

## 開發與驗證

前端使用 React / TypeScript，桌面宿主使用 Tauri / Rust，本機控制服務使用 Python。依賴版本固定在倉庫的鎖文件中。

    npm ci
    npm test
    npm run check:docs
    npm run test:docs

TypeScript 檢查與控制服務測試：

    ./node_modules/.bin/tsc --noEmit -p apps/desktop/tsconfig.json
    services/control/.venv/bin/python -B -m pytest tests/control -q

控制服務命令需要先準備對應的 Python 3.13 環境及依賴。完整構建、各運行時環境、簽名和啓動步驟見[桌面開發與構建說明](scripts/desktop/README.md)。當前候選的系統範圍為 Apple Silicon / macOS 26 及以上，仍需最終候選復驗。

開發、原生測試和本機候選運行共用：

    apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app

每次實際 App 構建遞增構建編號。提交源碼或修改文檔不會生成新 App 版本。

<a id="文档"></a>

## 文檔

- [用戶操作手冊](docs/USER_GUIDE.zh-CN.md)
- [文檔中心與 1.1 設計基線](docs/README.md)
- [完整三語文檔目錄](../README.md)
- [更新記錄](CHANGELOG.md)
- [原型參考](prototype/reference-2026-09-09/README.md)

倉庫收錄源碼、測試、構建腳本、用戶手冊、設計規範和歷史驗收記錄。文檔中指向 .artifacts/ 的鏈接屬於本地證據索引，需在保留相應目錄的工作區查看；GitHub 上可直接閱讀結論和範圍說明。運行庫、App 構建產物、模型、用戶資料庫和本地憑據由各自環境管理。

<a id="交付边界"></a>

## 交付邊界

完整交付仍需指定 NVIDIA、受信 HTTPS 跨主機、同份產物跨端、乾淨安裝、五名首次用戶、達標質量與人工評審等證據。舊字幕長列表偶發空白和其餘未覆蓋原生路徑保持待驗。原型、歷史失敗和設計基線保留各自形成時的結論。
