<!-- translation-navigation:start -->
[简体中文](../../../../adapters/mlx_text/PRESETS_PLAN.md) · [繁體中文](PRESETS_PLAN.md) · [English](../../../en/adapters/mlx_text/PRESETS_PLAN.md)
<!-- translation-navigation:end -->

<a id="m2-运行预设与-kv-缓存只读核查"></a>

# M2 運行預設與 KV 緩存只讀核查

日期：2026-09-10。狀態：源碼核查通過；以下新增參數和預設尚未實現、尚未實機測量，不能稱 M2 已通過。

目標是給當前 Apple 文本組合增加可解釋、可回讀的三個運行預設。保持同一模型、輸入、上下文預算、輸出上限和採樣參數，再測緩存與分塊本身的影響。本報告不更改執行器、控制服務、前端或當前媒體驗收配方，不加載模型、不使用 GPU。

<a id="1-当前事实与完成标准"></a>

## 1. 當前事實與完成標準

- 當前獨立環境：Python 3.13.9、MLX 0.32.2、MLX-LM 0.31.3。已讀實際安裝的 `generate.py`、`models/cache.py`、`models/base.py`、`models/qwen2.py` 和 `mlx.core.quantize` 文檔，並核查官方同版本來源。
- 當前模型：Qwen2.5-0.5B-Instruct；原 BF16 和本地派生的 affine 4 bit/group 64 權重組合分別驗證。模型配置是 24 層、14 個查詢頭、2 個 KV 頭、隱藏維度 896，所以每頭 64 維。
- 當前產品只開放單請求 Apple GPU 文本推理，輸入與最大輸出合計不超過 4096 token。模型配置的 32768 位置數不等於當前產品已開放預算。
- 當前 worker 只傳輸出上限和 sampler；緩存仍使用 MLX-LM 默認完整非量化 KV，Prefill 默認 2048。當前 preflight 尚無本報告新增字段，不能把本報告當成已實現能力。
- 完成標準：字段經過同一提交校驗；預設應用前能看差異和取消；界面、已應用配置、快照與真實引擎參數一致；緩存實際類型/精度有回讀；真實同輸入對照與取消釋放通過；未測組合拒絕；報告清楚區分緩存內存、模型權重、進程內存和任務耗時。

<a id="2-api-的真实语义"></a>

## 2. API 的真實語義

`stream_generate` 把以下參數傳入 `generate_step`，該函數當前默認值如下。參數默認值和實現摘要見`.artifacts/m2-kv/source-audit-v1/source-check.json`。

| 參數 | 上游默認 | 真實作用與邊界 |
| --- | --- | --- |
| `max_kv_size` | `None` | 非空時普通模型建立旋轉 KV 窗口；會丟棄較早 token 的 KV，不是保留全文的內存容量限制 |
| `prompt_cache` | `None` | 可傳緩存對象列表；一旦提供，`generate_step` 不再根據 `max_kv_size` 建緩存，不能默默依賴後者生效 |
| `prefill_step_size` | 2048 | 按 token 分塊計算提示詞；不改變輸入/輸出預算，也不等於併發或 batch size |
| `kv_bits` | `None` | 非空時將支持的緩存轉換為 affine 量化存儲；不修改模型權重 |
| `kv_group_size` | 64 | KV 最後一維的量化分組大小；需要整除該維度 |
| `quantized_kv_start` | 0 | 緩存 offset 達閾值後在一次 Prefill 分塊或解碼 step 結束處轉換；不保證精確在閾值 token 處轉換 |

關鍵限制：

1. `make_prompt_cache` 若發現模型自有 `make_cache()`，會優先調用它，忽略 `max_kv_size`；當前 Qwen2 沒有自有方法，但不能把此行為推廣給其它模型。
2. 默認創建的旋轉緩存保留開頭 4 個 token。`RotatingKVCache.to_quantized()` 明確拋 `NotImplementedError`，所以旋轉窗口與 KV 量化組合必須在提交前拒絕。
3. 旋轉緩存多 token 更新可臨時達到 `max_size + S - 1`，首次還可直接保存整個輸入分塊。窗口數不代表運行峰值內存的硬上限。
4. 普通和量化 KV 按 256 token 擴容，實際已分配 token 數可能超過當前 offset。`nbytes` 是緩存數組存儲大小，不是進程全部內存；擴容或量化轉換時還可能同時存在舊/新數組。
5. MLX 0.32.2 affine 量化支持 group 32/64/128、bits 2/3/4/5/6/8；最後一維必須整除 group。當前 Qwen2 KV 維度為 64，因此 group 128 不兼容。首輪只測和開放 KV 4 bit/group 64，不因底層枚舉更寬而承諾其它值。
6. 量化 Attention 走兩個 `mx.quantized_matmul`，普通緩存走 `mx.fast.scaled_dot_product_attention`；兩者數值及性能可能不同。量化 Attention 不支持 attention sinks；當前 Qwen2 沒傳 sinks。
7. `stream_generate` 的 draft-model 分支會移除 `max_kv_size`。當前產品未開放推測解碼，繼續拒絕該組合，避免聲稱窗口已生效。

來源：[MLX-LM 0.31.3 生成實現](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py)、[緩存實現](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/models/cache.py)、[Attention 實現](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/models/base.py)、[MLX 0.32.2 量化文檔](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.quantize.html)。

<a id="3-建议第一版合同"></a>

## 3. 建議第一版合同

建議只給 `kind=language, operation=generate, engine=mlx, device_id=apple-gpu` 的當前兩個權重組合擴展以下字段。保留原有 `seed/max_tokens/temperature/top_p`，不要讓預設改變用戶任務的輸出上限。評測繼續使用凍結的評測規則；訓練和權重量化操作不接受推理緩存字段。

| 界面說明 | runtime 字段 | 首輪候選值 | 拒絕條件 |
| --- | --- | --- | --- |
| 緩存精度 | `kv_precision` | `auto`、`q4` | 未知值、其它模型/引擎/操作 |
| 提示詞分塊 | `prefill_step_size` | 512、2048、4096 token | 布爾值、非整數、0/負數、非候選值；不可靜默修正 |
| 緩存窗口 | 暫不開放 | 顯示“保留完整上下文” | 任意 `max_kv_size`/旋轉請求 |
| 跨運行前綴復用 | 暫不開放 | `disabled`，每次建立新緩存 | 傳入歷史緩存路徑/緩存 ID、請求開啓共享復用 |

界面精度 `auto` 明確解釋為“跟隨當前模型計算精度，不量化 KV”；運行結果回讀真實 dtype，不能僅根據權重配置推斷。`q4` 明確解釋為“4 bit 推理緩存；可能改變回答，模型權重保持原樣”。group 64、量化起點 0 在第一版作為固定解析值保存，不增加沒有實測需求的可編輯表單項。

若開發者選擇直接暴露上游字段，仍需同樣嚴格限制 `kv_bits ∈ {null, 4}`、`kv_group_size = 64`、`quantized_kv_start = 0`、`max_kv_size = null`；不要同時維護含義衝突的兩套用戶可編輯值。

三個預設必須版本化，並且綁定當前模型格式、模型結構、引擎版本和設備。最小映射如下；這是待測方案，不是當前可應用能力：

| 預設 | 緩存精度 | Prefill 分塊 | 不變字段 | 說明 |
| --- | --- | --- | --- | --- |
| 模型默認 | auto | 2048 | 當前 max_tokens、temperature、top_p、seed、上下文預算 | 復現當前引擎緩存/分塊默認；標題不能暗示重置生成參數為模型卡值 |
| 低內存 | q4 | 512 | 同左 | 嘗試減小緩存與分塊臨時內存；可能改變回答和速度，待測後決定是否開放 |
| 低延遲 | auto | 4096 | 同左 | 嘗試減少長提示詞分塊次數；短提示詞可能沒有差異，待測後決定是否開放 |

“模型默認”建議在差異預覽旁標明“緩存與提示詞分塊恢復引擎默認”。如產品要讓它同時重置全部生成參數，必須在差異中逐項明示，且低內存/低延遲的性能對照另行固定相同採樣和輸出上限。

只保存完整解析字段即可執行；附帶 `preset_id/preset_version` 用於解釋來源，不應讓後端因同名 preset 自動改寫快照。模板 ID 與字段衝突時拒絕；用戶改任一模板字段後標為自定義。換模型/設備/格式時重新取能力，顯示哪些字段失效、哪些值被保留，舊模板不能自動遷移。

<a id="4-执行回读与证据"></a>

## 4. 執行回讀與證據

建議由 adapter 顯式建立本次緩存列表，傳給 `stream_generate`，在生成結束時檢查該同一列表實際存儲：層數、每層類名、offset、已分配 shape、普通 KV dtype 或量化 bits/group 與 scale/bias dtype、總 `nbytes`。量化函數會替換列表元素，因此讀取結束後的同一列表即可確認 `QuantizedKVCache` 真實使用。保存摘要，不導出用戶 KV 內容。

每次運行保存完整解析參數、模型/適配器 manifest、tokenizer/模板摘要、輸入 token 摘要、引擎版本、執行器源碼摘要、硬件、PID、實際輸出 token 數和輸出文本。按現有產品任務快照綁定，執行器復覈實際配置，不僅顯示 UI 標籤。新增推理運行配方身份應與現有分詞配方身份區分；當前分詞配方不含所有 runtime 字段，不能單憑其 digest 證明緩存設置已被凍結。

性能字段至少分開：模型加載時間、從生成開始到首個 token 的耗時、Prefill 詞元/秒、Decode 詞元/秒、整個進程牆鐘時間、MLX 本次生成峰值、進程 RSS 峰值、最終 KV 數組字節。記錄 `mx.get_peak_memory()` 重置/採樣時點，並保留包含模型加載的全流程基線；不要把生成階段峰值與另一次全流程峰值直接比較。

當前單次新進程不跨任務保留前綴緩存。緩存命中率應記錄為“不適用/未啓用”，不能填 100%。後續若開放復用，身份還必須包含模型、適配器、tokenizer、模板、輸入前綴、KV 精度、引擎緩存格式、隔離範圍；多模態另加媒體順序、內容摘要、處理器與預處理配方。

<a id="5-可核算的量级仅作理论参照"></a>

## 5. 可覈算的量級，僅作理論參照

Qwen2.5-0.5B 的 BF16 KV 理論數據量：每 token 為 `2 × 24 × 2 × 64 × 2 = 12,288` 字節。4096 token 的 K/V 為 48 MiB。若 affine 4 bit、group 64，且 scale/bias 都為 2 字節，每 token 為 3456 字節，4096 token 為 13.5 MiB。差值 34.5 MiB，是 KV 數組理論差值，不是模型權重或整機內存節省量。

這些數不包含 256 token 擴容、臨時激活、轉換期間舊新緩存並存、allocator、模型權重、Python 進程和系統開銷。量化權重模型的 KV 實際 dtype 還要運行回讀；不能僅因為權重為 4 bit 就認定其 KV 也為 4 bit。

<a id="6-分阶段真实验证矩阵"></a>

## 6. 分階段真實驗證矩陣

先等當前媒體 UI 使用完 GPU，再凍結測試方案與源碼。不要在正在驗收的媒體配方中途更改共享 worker。

1. **提交合同和能力負例 →** 默認缺省得到 auto/2048；布爾值/未知值/非法範圍拒絕；train/evaluate/quantize 和媒體操作拒絕推理緩存字段；未驗設備/模型拒絕；旋轉+量化、歷史 prompt-cache、draft-model 等未開放項拒絕。改變預設字段後不再宣稱命中原模板。
2. **18 個基礎功能樣例 →** 兩個權重格式 × 三個預設 × 短/中/長三個輸入。用真實 tokenizer 將三檔輸入控制在約 64/1024/3584 token，三者輸出上限統一 128、貪心採樣、同一 seed；保存精確輸入 token 數，不以字符數充數。全部可獨立加載、生成有限輸出、回讀實際緩存類/精度/分塊、沒有裁剪和靜默丟參。
3. **性能重復 →** 對上一步每組合在獨立進程運行三次，預先固定交錯順序，額外暖機樣例不計入統計；記錄中位數和全體單次值，不能只挑最優。每個模型至少單列短/長輸入結果。同 max_tokens 下若實際輸出長度不同，TTFT 可直接比較；Decode 速度同時列實際 token 數，並只比較足夠長度樣例。
4. **效果歸因 →** 長輸入補測 q4/2048 與 auto/512 兩個診斷組合，每模型三次，拆開緩存量化和分塊各自影響。未達到可重復減少內存/首 token 耗時的模板不宣稱有收益；可繼續顯示待驗證或不可應用原因。
5. **文本正確性 →** 固定短問答、數字提取、JSON 結構、長文本前部/中部/尾部檢索樣例。auto 的不同分塊先比較 token ID/文本；若不同則保留差異並做答案檢查。q4 允許數值/文本不同，但必須報告各項正確率和回歸，不能以沒有 NaN 代替質量驗收。
6. **緩存隔離與身份 →** A/B 兩個獨立任務同前綴不同結尾，各與冷啓動自身基線對照；換模型/適配器/模板/精度後使用新緩存，記錄每次緩存初始為空。媒體輸入仍被當前文本能力拒絕；這證明當前路徑沒有錯誤復用，不證明多模態共享緩存已實現。
7. **取消和資源 →** 分別在長 Prefill、低內存 Decode 時取消，確認 worker/process group 回收且無 completed，隨後新任務正常生成；緩存不得進入通用診斷包或被當作作品導出。
8. **普通用戶 UI →** 逐個打開差異、取消、應用、提交、查看實際參數和配方重載；運行中不變快照；換模型/格式/設備後失效說明正確。Browser/Computer Use 實際操作，保存可見結果和 API/worker 證據。

完成 1—8 只能關閉 M2 的本機文本預設/緩存子項；NVIDIA、遠程、其它模型、共享前綴緩存、多模態緩存、Prefill/Decode 分離和完整 M2 gate 仍需各自證據。

<a id="7-本次核查的验证边界"></a>

## 7. 本次核查的驗證邊界

本次已運行純 Python AST/結構核查與理論字節計算，結果在 `.artifacts/m2-kv/source-audit-v1/source-check.json`；只讀取依賴、當前模型配置和 worker，不執行模型。已確認上游參數默認值、旋轉量化明確拒絕、Qwen2 結構與默認緩存路徑。本文測試矩陣尚未執行，`source-check.json` 中 `gpu_execution` 和 `runtime_presets_implemented` 明確為 false。
