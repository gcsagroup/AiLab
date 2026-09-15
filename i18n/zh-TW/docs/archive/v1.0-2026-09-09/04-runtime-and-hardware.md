<!-- translation-navigation:start -->
[简体中文](../../../../../docs/archive/v1.0-2026-09-09/04-runtime-and-hardware.md) · [繁體中文](04-runtime-and-hardware.md) · [English](../../../../en/docs/archive/v1.0-2026-09-09/04-runtime-and-hardware.md)
<!-- translation-navigation:end -->

<a id="运行参数优化与硬件适配规格"></a>

# 運行參數、優化與硬件適配規格

版本：1.0 · 日期：2026-09-09 · 狀態：以最終運行優化 Demo 為需求基線；真實後端待接入。

相關文檔：[接口合同](07-api-and-task-lifecycle.md)、[架構](06-architecture-and-adapters.md)、[性能驗收](11-testing-and-acceptance.md)。

<a id="1-核心原则"></a>

## 1. 核心原則

運行能力由“模型版本 × 模型格式 × tokenizer／處理器 × 引擎版本 × 操作系統 × 驅動 × 硬件 × 參數組合”共同決定。品牌名、文件下載完成或設備連接成功都不足以確定支持。

產品必須同時保存用戶請求配置、校驗結果、引擎實際執行配置和運行證據。所有字段都有適用條件、單位和作用階段。不能用一個大 JSON 輸入框代替完整的配置界面，也不能把不同引擎名稱相似的參數無條件互相映射。

<a id="2-参数层级与生效时机"></a>

## 2. 參數層級與生效時機

| 層級 | 示例 | 修改後的動作 | 與已有任務的關係 |
| --- | --- | --- | --- |
| 單次請求 | temperature、最大輸出、停止詞、思考模式 | 下次請求生效 | 不修改執行中請求 |
| 會話／輸入管理 | 上下文限額、歷史裁剪、緩存隔離 | 重新計算輸入和緩存鍵 | 不改變已經保存的結果 |
| 引擎實例 | KV dtype、批處理預算、CUDA Graph | 可能需要重新加載或重啓實例 | 先排空或新建實例，不能靜默打斷任務 |
| 模型加載 | 權重精度、適配器、GPU 卸載、並行佈局 | 加載新實例並檢查 | 保留舊實例上的任務歸屬 |
| 部署 | Prefill／Decode 分離、遠程連接器 | 單獨部署與驗收 | 不通過請求表單隱式部署 |

界面在應用前展示哪些修改需要重啓、重新加載或重新分詞。默認值取自版本化模型模板；真實執行時應顯示已解析後的數值或明確的自動策略。

<a id="3-生成与上下文字段"></a>

## 3. 生成與上下文字段

本節“Demo 默認”只描述當前原型。正式默認值從能力聲明與模型推薦配置生成。

| 字段 | 中文含義 | Demo 默認 | 正式校驗與語義 |
| --- | --- | --- | --- |
| `thinking` | 思考模式 | `default` | 默認／關閉／開啓；只有模型和模板明確支持時可切換 |
| `context` | 上下文限制 | 8192 token | 輸入、歷史、系統指令、媒體 token、輸出合計受限 |
| `maxOutput` | 最大輸出 | 1024 token | 必須給輸入留空間；最終根據實際分詞結果檢查 |
| `overflow` | 超限處理 | `reject` | 拒絕或裁剪最舊對話；保留系統消息與工具調用完整性 |
| `temperature` | 溫度 | 0.7 | 有限非負數；0 的含義由引擎映射為確定性策略並記錄 |
| `topP` | 累積概率採樣 | 0.9 | 有效範圍由引擎定義，空值不能變成 0 |
| `topK` | 候選數量 | 20 | 0 表示不限制只在適配器確實如此解釋時使用 |
| `minP` | 最小相對概率 | 0 | 不支持該採樣器時不得悄悄忽略 |
| `repeatPenalty` | 重復懲罰 | 1.05 | 與 presence／frequency penalty 區分，不能直接替代 |
| `stop` | 停止序列 | 空 | 正式產品使用字符串數組；界面按行輸入後解析 |
| `stream` | 流式輸出 | 開啓 | 區分服務端流、前端展示和最終結果持久化 |
| 任務 `seed` | 隨機種子 | 42 | 隨結果保存；跨引擎相同種子不承諾逐字相同 |

<a id="31-关闭思考"></a>

### 3.1 關閉思考

以 [Qwen3-4B 模型說明](https://huggingface.co/Qwen/Qwen3-4B)中的模板控制為參考實現一個明確組合。實際適配必須確認思考開關如何傳到模板和推理接口，不能只在輸出後移除思考文本。

模型只有一種行為模式、模板不接受開關或遠程服務不支持時，界面顯示模型默認並解釋原因。輸出顯示策略與模型思考計算分開記錄。思考預算是後續按引擎聲明開放的參數，當前 Demo 沒有單獨實現其預算控制，不以 `maxOutput` 冒充完整的思考預算。

<a id="32-上下文预算"></a>

### 3.2 上下文預算

提交前使用本次模型的 tokenizer／處理器計算實際輸入 token。多模態輸入必須計入模型處理後的媒體 token，不能只統計問題字符數。預留系統消息、模板標記和輸出空間，超過限額時執行用戶選擇的策略。

Demo 的 512—32,768 校驗範圍是演示約束，不是所有 Qwen 模型或所有引擎的產品上限。正式最大值來自模型能力、引擎配置和資源約束；上下文擴展方法需要獨立版本與質量驗證。

<a id="4-kv-cache-与前缀缓存"></a>

## 4. KV Cache 與前綴緩存

| 字段 | 含義 | Demo 默認 | 正式要求 |
| --- | --- | --- | --- |
| `kvPrecision` | KV 存儲精度 | auto | 分引擎列出 dtype／量化格式；和權重量化獨立 |
| `kvBudget` | KV token 容量／窗口 | 8192 | 必須標注它在該引擎中是容量、窗口還是由預算推導的估計值 |
| `prefixCache` | 提示詞／前綴復用 | 關閉 | 僅在引擎確實支持並可驗證命中時啓用 |
| `cacheScope` | 緩存隔離 | 當前任務 | 可選擇項目範圍；不跨項目共享私有輸入 |

當前原型提供 MLX 的 auto／8-bit／4-bit、llama.cpp 的 auto／f16／q8_0／q4_0、服務引擎的 auto／fp8 示例。真實適配必須驗證版本與設備的格式組合，不能把這些列表直接認定為完整可用列表。

KV 容量的統一界面語義要謹慎處理：MLX 的旋轉緩存窗口會丟棄更早 KV；服務引擎通常通過顯存預算、塊管理或具體 cache 配置管理容量。適配器必須輸出實際映射，無法等價映射時更換字段標籤並顯示原因。

緩存鍵至少包括模型版本、權重／適配器組合、tokenizer、聊天模板、輸入 token 前綴、KV 精度和隔離範圍。模型／模板／適配器改變後失效。緩存數據不能進入普通診斷包；清理緩存不能刪除用戶模型和作品。

<a id="5-prefill-与-decode-调度"></a>

## 5. Prefill 與 Decode 調度

| 字段 | 含義 | Demo 默認 | 適用與驗收 |
| --- | --- | --- | --- |
| `prefillChunk` | 輸入處理分塊大小 | 512 token | 單請求步長與服務端 chunked prefill 區分 |
| `chunkedPrefill` | 服務端分塊調度 | 關閉 | 按 vLLM／SGLang 具體版本和架構適配 |
| `batchTokens` | 批處理 token 預算 | 2048 | 檢查與分塊、最大序列及調度規則的關係 |
| `decodeBatch` | 併發序列數 | 1 | 本次實例併發上限；不等於訓練批量 |
| `attention` | Attention 實現 | auto | 由模型算子、引擎和設備共同決定 |
| `graphs` | CUDA Graph | 關閉 | 需要合適的形狀、預熱、顯存和引擎支持 |
| `splitPD` | Prefill／Decode 分離 | 關閉 | 屬於部署能力，需要連接器和故障恢復 |
| `prefillEndpoint` | Prefill 服務地址 | 空 | 驗證服務身份、模型版本、可用性 |
| `decodeEndpoint` | Decode 服務地址 | 空 | 需與 Prefill 的 KV 格式和傳輸協議兼容 |

參考 [vLLM 調優說明](https://docs.vllm.ai/en/latest/configuration/optimization/)定義測試條件，但不將上游默認值寫死為產品默認。較大批處理通常服務於吞吐，較小輸入分塊可能影響首 token 和調度公平性，必須以實測決定。

前後端分離部署在 Demo 中沒有真實服務或 KV 傳輸連接器，當前應保持阻斷。正式實現需要額外驗證遠端身份、傳輸失敗、模型版本錯配、緩存傳輸超時和請求恢復，不能靠兩個 URL 輸入框就稱為支持。

<a id="6-推测解码"></a>

## 6. 推測解碼

| 策略 | 必要依賴 | 配置 | 驗證重點 |
| --- | --- | --- | --- |
| 關閉 | 正常目標模型 | 無草稿組件 | 正常基線 |
| 普通草稿模型 | 目標、草稿、tokenizer／詞表兼容、引擎適配 | 草稿版本、精度、推測長度 | 分布／正確性、接受率、總延遲 |
| MTP | 目標模型原生預測能力或對應配套組件、引擎實現 | 預測組件、推測長度、驗證模式 | 組件匹配、逐步驗證與回歸 |
| DFlash | 目標模型、匹配的塊擴散草稿、引擎與版本 | 草稿配對、塊大小、草稿精度 | 家族／思考模式條件、接受率、驗證成本 |

Demo 字段為 `speculation`、`draftModel`、`draftReady`、`specTokens`、`draftPrecision`。其中 `draftReady` 當前只是模擬狀態，真實實現必須拆成下載完整、哈希校驗、加載、配對驗證四個階段。

[vLLM MTP 文檔](https://docs.vllm.ai/en/latest/features/speculative_decoding/mtp/)將 MTP 作為依賴模型能力的路徑；當前 Demo 中的 Qwen3-4B 不應因用戶勾選 MTP 就獲得原生預測組件。

[DFlash 官方項目](https://github.com/z-lab/dflash)列出了特定模型與本地／服務後端路徑。不能泛稱 DFlash 只支持 CUDA，也不能泛稱任意 MLX 模型都可開啓。當前 Demo 使用 Qwen3-4B 非思考模式配套示例；正式實現鎖定目標 revision、草稿 revision、引擎 revision 和思考策略後再驗收。

推測解碼默認只選擇一種策略。啓用後不保證更快；必須測量草稿開銷、接受率、Prefill、Decode、總延遲、吞吐和峰值內存。對不兼容配對拒絕執行，不能降級到標準生成後仍顯示推測加速已開啓。

<a id="7-通用硬件与加载字段"></a>

## 7. 通用硬件與加載字段

| 字段 | 含義 | Demo 默認 | 正式規則 |
| --- | --- | --- | --- |
| `device` | 執行位置 | 全局默認設備 | 固定設備標識，不能只記錄易變顯示名 |
| `accelerator` | 硬件後端 | 按設備模板 | 驗證廠商、架構、操作系統和驅動 |
| `engine` | 運行引擎 | 按模型類別與後端 | 記錄實際二進制／包版本 |
| `precision` | 權重計算精度 | auto | FP16／BF16／FP32 只是候選，設備不支持時拒絕 |
| `memoryLimit` | 內存使用預算 | 80% | GPU 顯存、統一內存和系統內存必須分開解釋 |
| `cpuThreads` | CPU 線程 | 8 | 區分計算線程和輸入處理線程 |
| `gpuLayers` | llama.cpp GPU 卸載層 | auto | 記錄實際卸載結果，不能把請求 all 等同於全部成功 |
| `tensorParallel` | 張量並行設備數 | 1 | 校驗設備數量、拓撲、模型切分與引擎支持 |
| `computeUnits` | Core ML 計算單元策略 | 按後端 | CPU_ONLY／CPU_AND_GPU／CPU_AND_NE／ALL 等策略 |

全局設備列表保留本機、自有服務器、雲實例、AMD 工作站、Intel 工作站和 CPU 示例。真實設備條目必須通過探測數據生成，不能把 Demo 內的“Apple”“Linux”當成本機或用戶服務器的真實硬件事實。

<a id="8-硬件适配目标矩阵"></a>

## 8. 硬件適配目標矩陣

所有條目當前均為**待驗證的目標路徑**。首期重點組合是 Apple 本地推理與 NVIDIA Linux 訓練／推理，其餘逐階段加入。

| 硬件／軟件棧 | 候選引擎 | 運行目標 | 訓練目標 | 關鍵限制與檢查 |
| --- | --- | --- | --- | --- |
| Apple GPU／Metal | MLX-LM、MLX-VLM、llama.cpp | 文本及適配的多模態 | MLX 支持的模型方法 | 統一內存、模型轉換、處理器和算子支持 |
| Apple GPU／MPS | PyTorch、Transformers、Diffusers | 媒體與適配模型 | 逐模型驗證 | 不等同 CUDA；缺算子和回退需顯式記錄 |
| Apple ANE／Core ML | Core ML | 轉換後的端側模型 | 不作為通用訓練後端 | 圖劃分、模型格式、靜態／動態形狀與設備執行 |
| NVIDIA／CUDA | PyTorch、vLLM、SGLang、llama.cpp、Diffusers | 文本、多模態、媒體 | PEFT／TRL 等已驗證方法 | GPU 架構、驅動、CUDA、顯存和精度 |
| AMD／ROCm／HIP | PyTorch、vLLM、SGLang、llama.cpp | 適配模型 | 逐方法驗證 | 精確 GPU、系統、驅動及庫版本 |
| Intel GPU／oneAPI／SYCL | llama.cpp 等已適配引擎 | GGUF 等適配模型 | 另行評估，不由推理能力推導 | 編譯後端、Level Zero／SYCL 運行庫和設備代際 |
| Intel／OpenVINO | OpenVINO | 支持插件上的 IR／可轉換模型 | 不作為首期通用訓練後端 | CPU／GPU／NPU 插件、模型格式和算子 |
| Vulkan GPU | llama.cpp 等 | 構建支持的模型 | 不作為首期訓練後端 | 驅動、擴展和實際圖形設備 |
| CPU | llama.cpp、PyTorch 等 | 小模型和回歸基線 | 小規模功能性測試 | 內存、指令集、線程；不承諾大模型可用速度 |

官方邊界參考：[Core ML 圖執行](https://apple.github.io/coremltools/docs-guides/source/typed-execution.html)、[ROCm 兼容矩陣](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html)、[OpenVINO 設備模式](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html)、[llama.cpp](https://github.com/ggml-org/llama.cpp)。

<a id="81-ane-的产品表达"></a>

### 8.1 ANE 的產品表達

ANE 是計算硬件，Core ML 是選擇該路徑的一種運行接口；MLX 使用 Apple GPU 的路徑與它分開。選擇 CPU + ANE 表示允許相應計算單元參與，不保證全部算子落到 ANE。正式報告應保存 Core ML 計算計劃或可獲得的執行證據；無法直接歸因時標為“未確認實際 ANE 分配”。

<a id="82-训练与运行能力分别判断"></a>

### 8.2 訓練與運行能力分別判斷

設備可運行 GGUF 不等於能用該文件訓練；ROCm 能加載模型不等於支持所選 QLoRA 實現；Intel GPU 的 SYCL 推理不等於提供對應訓練後端。當前 Demo 訓練端仍有簡化判斷，必須在真實實現中替換為統一能力查詢。

<a id="9-媒体模型参数"></a>

## 9. 媒體模型參數

| 字段 | 用途 | Demo 默認 | 驗收要求 |
| --- | --- | --- | --- |
| `scheduler` | 圖像／視頻採樣調度器 | 模型默認 | 調度器與 checkpoint 配置匹配 |
| `sampling` | 採樣步數 | 20 | 結果配方和真實 pipeline 參數一致 |
| `cfg` | 引導強度 | 7 | 只對使用該語義的模型開放 |
| `vaeTiling` | VAE 分塊解碼 | 關閉 | 檢查拼接邊界、內存和質量 |
| `vaeSlicing` | VAE 分批解碼 | 關閉 | 檢查批量維度和支持條件 |
| `offload` | CPU 卸載策略 | 無 | 區分按組件／順序卸載，檢查傳輸開銷 |
| `compile` | 編譯優化 | 關閉 | 區分首次編譯與預熱後性能，記錄緩存 |
| `frames`／`fps` | 生成幀數／幀率 | 81／16 | 與時長、容器、模型限制一致 |
| `sampleRate` | 輸出採樣率 | 24000 Hz | 引擎原生採樣率與後處理重採樣分開 |
| `audioChunk` | 音頻塊時長 | 200 ms | 僅流式適配器支持時開放 |
| `streamAudio` | 分塊音頻輸出 | 關閉 | 實際收到可播放塊、順序和最終文件完整 |
| `speed` | 語速 | 1.0 | 模型控制與後處理變速分別記錄 |

參考 [Diffusers 內存優化](https://huggingface.co/docs/diffusers/optimization/memory)建立有條件的配置，不將 VAE、CFG、Euler 或 DPM++ 當成所有圖片模型的通用能力。自定義圖像融合網絡可以完全不使用這些參數。

Demo 中視頻時長、幀數與幀率仍是演示配置，實際產品必須在提交前統一換算並檢查矛盾，不能同時保存多個互相衝突的“最終時長”。

<a id="10-能力状态与诊断"></a>

## 10. 能力狀態與診斷

能力至少具有未知、需準備、支持、條件支持、不支持、已驗證六種狀態。界面顯示狀態的依據與時間：文件、探測、配置檢查或實機報告。

推薦診斷順序：設備可達 → 硬件探測 → 驅動與運行庫 → 引擎版本 → 模型文件／格式 → 加載 → 固定樣例推理 → 目標優化驗證。每一步單獨保存結果，避免“連接成功”掩蓋後續失敗。

<a id="11-参数验收合同"></a>

## 11. 參數驗收合同

每個正式開放參數必須完成：字段類型校驗、適用條件校驗、後端參數映射、實際值回讀、有效行為驗證、配方保存、配方重載、錯誤提示。性能開關增加開／關對照與回歸報告。

請求未被執行器採用時必須拒絕或返回明確的變更確認，不能把“界面保存成功”當作“優化已生效”。完整用例見 [11](11-testing-and-acceptance.md)。
