<!-- translation-navigation:start -->
[简体中文](../../../../adapters/mlx_text/README.md) · [繁體中文](README.md) · [English](../../../en/adapters/mlx_text/README.md)
<!-- translation-navigation:end -->

<a id="本地-mlx-文本适配器"></a>

# 本地 MLX 文本適配器

2026-09-10：Apple M5 Max 的真實推理、SFT + LoRA 參數更新、來源身份核對、獨立重載、MLX 4-bit 量化導出、取消與錯誤組合檢查已通過。此處是 Apple 部分的技術試驗與執行器，不代表 TV-01 的 NVIDIA 部分、TV-03 跨端回程、模型質量准入或完整訓練產品驗收通過。

<a id="已验证组合"></a>

## 已驗證組合

- macOS 26.6.2、Apple M5 Max、128 GiB 統一內存；實際 MLX 默認設備為 `Device(gpu, 0)`，未使用或聲稱 ANE。
- Python 3.13.9、MLX 0.32.2、MLX-LM 0.31.3；全部安裝版本見 `requirements.lock.txt`。
- 官方 `Qwen/Qwen2.5-0.5B-Instruct`，revision `7ae557604adf67be50417f59c2c2f167def9a775`，未量化 BF16 權重；許可證文件隨模型保留。
- 權重 SHA-256：`fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe`；大小 988,097,824 字節。
- 源模型只讀使用；模型、tokenizer、模板、環境、實際參數和每個輸出文件的摘要均寫入執行證據。

原始碼結構檢查支援 `qwen2` 的 0.5B（896 隱藏維度、24 層）和 7B（3584 隱藏維度、28 層）固定組合。7B 只接受未量化基座，權重量化與 q4 KV 快取尚未開放；0.5B 保留原有量化範圍。結構匹配不等於所有同結構衍生權重或業務品質通過。上述歷史紀錄描述首個組合，新增原始碼實測邊界見文末。

<a id="准备与复跑"></a>

## 準備與復跑

在項目根目錄運行；命令中的相對路徑均以該目錄為準。現有環境和公開試驗模型已準備好，無需再次下載。

```sh
python3.13 -m venv adapters/mlx_text/.venv
adapters/mlx_text/.venv/bin/python -m pip install -r adapters/mlx_text/requirements.lock.txt
adapters/mlx_text/.venv/bin/python adapters/mlx_text/prepare_model.py
adapters/mlx_text/.venv/bin/python -m pytest tests/mlx -q
adapters/mlx_text/.venv/bin/python tests/mlx/run_real_probe.py --evidence .artifacts/m0-mlx/new-run
adapters/mlx_text/.venv/bin/python tests/mlx/run_m3_probe.py --evidence .artifacts/m0-mlx/new-m3-run
```

最後一個證據目錄必須不存在。`prepare_model.py --verify-only` 可只核對當前模型。下載只請求固定 revision 的 9 個公開文件，寫入項目 `.artifacts/models/Qwen2.5-0.5B-Instruct`；不修改 `/Users/lazy/Models` 或用戶原有 Hugging Face 模型緩存。此前 Xet 下載與短超時 HTTP 失敗均未被當作成功，最終通過 HTTP 重試下載並核對權重摘要。

<a id="控制服务合同"></a>

## 控制服務合同

Python：`adapters/mlx_text/.venv/bin/python`，控制端必須解析並使用絕對路徑。

```sh
adapters/mlx_text/.venv/bin/python adapters/mlx_text/preflight.py --snapshot SNAPSHOT --output-dir EMPTY_OUTPUT_DIR
adapters/mlx_text/.venv/bin/python workers/mlx_worker.py --snapshot SNAPSHOT --output-dir EMPTY_OUTPUT_DIR
```

快照字段：`attempt_id`、`operation`、`model_path`、`input`、`runtime`。必須提供完整的 `model_manifest=[{path,size,sha256},...]`、`model_manifest_digest`；訓練額外提供單個 `messages` JSONL 的絕對 `dataset_path`、單文件 `dataset_manifest` 與 `dataset_manifest_digest`。清單摘要採用 UTF-8、鍵排序、無多餘空格、非 ASCII 字符不轉義的標準 JSON 序列化再計算 SHA-256，與控制服務一致；路徑為相對路徑。

執行前後均重核對輸入文件集合、大小和摘要，新增未登記權重也會阻斷。正式 worker 還必須提供由預檢查返回的 `tokenization_recipe_digest`，加載後再次核對 tokenizer、模板、監督實現摘要。缺少身份字段即拒絕執行，不存在“未傳清單就默認可信”的模式；直接運行的開發試驗同樣顯式固定清單並先做預檢查。歷史 `run-20260910-01` 至 `03` 的舊快照僅作歷史證據，不能直接交給強化後的 worker。

生成可在快照頂層提供 `adapter_path`，同時必須提供 `adapter_manifest`、`adapter_manifest_digest` 與 `adapter_training_recipe_digest`。只接受本執行器輸出且基座完整清單／模板／來源訓練分詞配方／模塊／參數形狀匹配的適配器，執行前後均檢查完整 adapter 文件集。訓練生成的 `adapter_config.json` 保存 `base_input_manifest_digest` 和 `training_recipe_digest`；缺少這兩個來源字段的歷史產物不能直接進入生產執行器，不從目錄名猜測來源。訓練和量化不接受適配器，不支持增量續訓或在量化基座上掛載 LoRA。

預檢查只加載真實 tokenizer；返回單個 JSON，`can_submit`、`blocking`、`effective_config`、`tokenization_recipe_digest`、`recipe`、`check_report`。成功退出 0，阻斷退出 1。該腳本不創建輸出目錄，不加載模型權重；候選檢查會讀取 safetensors 參數頭和文件摘要。控制端須把配方摘要與當前數據、參數和文件身份一起綁定到提交檢查。

執行器 stdout 只輸出逐行 JSON；庫日誌去 stderr。事件 `type` 為 `phase`、`token`、`metric`、`completed`、`error`。`token` 含 `text`、`token_id`、`generation_tokens`；`completed` 含輸出目錄內相對路徑、SHA-256、`media_type` 與實際 `effective_config`。推導後的 `effective_config` 是只讀記錄，不能原樣作為下次可寫 `runtime`。

執行器在進程內禁止 Hugging Face 自動聯網，模型必須是明確本地路徑。輸出目錄必須為空，不允許符號鏈接跳轉或與模型／數據重疊。執行失敗可以留下診斷或中間文件，控制端只能在收到完成事件、進程正常退出且逐個摘要核對後登記正式產物。

SIGTERM／SIGINT 設置取消請求，在實際計算同步點檢查，退出 130 且不發送 `completed`。可提供 `AILAB_CONTROL_PID`；它必須等於實際父進程。父控制進程消失後執行器會自行停止，底層算子不返回時最多再等 10 秒退出自身，不給其他進程發信號。資源互斥與隊列由控制服務負責。

<a id="可写参数"></a>

## 可寫參數

生成：`engine=mlx`、`device_id=apple-gpu`、`seed`（0—2³²−1）、`max_tokens`（1—2048，默認 128）、`temperature`（0—2，默認 0）、`top_p`（0.01—1，默認 1）。提示詞最多 16,000 字符，真實分詞後的輸入與最大輸出合計最多 4096。temperature=0 使用貪心選擇，此時 top_p 不參與選擇；實際緩存使用 MLX 默認非量化完整 KV。以上為當前適配器的保守產品限制，不是硬件理論上限。

訓練固定項：`training_type=sft`、`update_method=lora`、`recipe_id=qwen25-assistant-only-v1`、`batch_size=1`、`gradient_accumulation=1`、`optimizer=adamw`、`weight_decay=0`、`lora_dropout=0`。

訓練可調項：`steps`（1—200，默認 4）、`learning_rate`（1e-7—0.01，默認 1e-4）、`max_seq_length`（32—2048，默認 512）、`lora_rank`（1—32，默認 4）、`lora_alpha`（1—64，默認 8）、`num_layers`（末尾 1—28 層，0.5B 最多 24 層，默認 2）與 `seed`。目標模塊固定為 `self_attn.q_proj`、`self_attn.v_proj`。MLX scale 顯式取 `alpha / rank`。

AdamW 顯式固定 betas=[0.9,0.999]、eps=1e-8、bias_correction=true；恆定學習率，無 warmup／梯度裁剪。源 BF16 權重凍結，LoRA 參數 FP32；數據按文件順序循環，seed 控制 LoRA 初始化。每步產出真實損失與監督詞元數，結束保存 LoRA 文件與參數變化。未開放中間檢查點恢復、斷點續訓、全參數、量化訓練、packing、多媒體或 NVIDIA。

量化：`operation=quantize`，`input={}`，`runtime` 僅允許 `engine=mlx`、`device_id=apple-gpu`、`seed`、`bits=4`、`group_size=64`、`mode=affine`。從未量化源權重產生獨立 `model/` 目錄，保留 tokenizer、模板和許可證，按約 128 MiB 張量預算拆分 safetensors；輸出模型清單及來源摘要保存在 `conversion.json`。該格式僅開放生成，禁止直接再量化、量化訓練或混入 adapter。模型體積變化有實測，不承諾推理速度或質量收益。

<a id="固定文本评测合同"></a>

## 固定文本評測合同

`operation=evaluate`，`input={}`，模型與 adapter 沿用生成合同。`runtime` 為 MLX／Apple GPU 加固定 `max_tokens`、`temperature=0`、`top_p=1`、`seed`，必須與評測規則內的生成配置完全相同。評測樣本和規則各不超過 4 MiB，均為完整清單所指定的本地文件；必須傳入 `evaluation_dataset_path`／`evaluation_dataset_manifest`／`evaluation_dataset_manifest_digest` 與對應 `evaluation_criteria_*`。`evaluation_plan_digest` 為包含這兩個 manifest_digest 字段的規範 JSON 摘要。

樣本 JSONL 為 `{id,category,prompt,rule}`，4—64 條，類別 `business`、`format`、`regression`、`behavior` 都必須非空。規則只支持 `exact`（非空 `expected`，輸出去除首尾空白後精確比較）、`contains_all`（非空 `keywords`，區分大小寫）、`json_equals`（`expected` 為對象或數組，完整輸出嚴格解析，不能去除圍欄、重復字段或接受非有限數）和 `manual`（`instruction`，保持待審）。沒有可執行表達式、自定義腳本或遠端裁判。

規則 JSON 固定為 `schema_version=text-rules-v1`、`category_min_pass_rate`（四類分別為大於 0 且不超過 1 的閾值）、`regression_tolerance`（0—1）、`generation={max_tokens,temperature,top_p,seed}`。布爾值不能冒充數值。評測在兩個獨立子進程中分別加載基線和候選，生成同一凍結樣本，保存逐樣本原文、規則結論、原因、兩邊各類 passed／total／pass_rate、閾值、退化差值、manual 待審和 unknown 數量。

訓練可綁定同組評測計劃字段；執行器核對清單並在 adapter 元信息寫入該計劃摘要。評測的 `eligible=true` 要求候選達到全部固定閾值、回歸未超容忍、無待人工項或未知項，且訓練產物綁定同一計劃。缺少訓練前綁定的舊候選只能事後評測並保持不可准入；控制服務還必須核對計劃不可變版本和創建時間早於來源訓練提交，不能只信報告布爾值。報告中“通過”僅適用於該凍結文本規則集，不代表通用模型質量。

開發驗證先執行 `tests/mlx/run_evaluation_probe.py --prepare --evidence NEW_DIRECTORY` 封存人工樣本、規則和固定 128 步預算，再去掉 `--prepare` 執行。已有證據目錄不能覆蓋，預算啓動記錄採用獨佔創建。規則成功／失敗、缺樣本、人工待審、事後評測、零閾值、錯誤類型和文件修改反例已包含在測試中；新的真實質量結果以對應目錄最終 `summary.json` 為準。

<a id="监督配方与验收边界"></a>

## 監督配方與驗收邊界

聊天模板 SHA-256 固定為 `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f`。配方摘要同時包含 `recipe.py` 實現源碼摘要，防止只改監督邏輯卻沿用舊配方身份。使用真實聊天模板逐前綴分詞，並核對完整序列與每個助手生成前綴一致；只監督助手回答及 `<|im_end|>`，不監督角色頭、系統／用戶內容和回答後的換行。標籤初始與輸入位置對齊，在損失處以 `input_ids[:-1]` 預測 `labels[1:]`，恰好移位一次。padding 按位置設為 -100，即使 EOS 與 PAD 編號相同也保留真實 EOS 監督。

超長樣本完整排除，不截斷、不拼接。空回答、僅系統／用戶、非法角色、媒體、工具調用、特殊標記和模板變化有明確錯誤；全數據無可訓練樣本時阻斷。檢查報告保留排除原因、有效監督數量和代表性 token／labels 對照。

真實試驗使用 4 條人工測試數據、4 步 LoRA 和預先固定的 4 個問題。源模型摘要不變；適配器確有參數變化，獨立進程重載改變 logits，另一獨立重載的 logits 與輸出可復現。目標代號未可靠學會，部分輸出與 JSON 格式仍不合格，所以不把損失或輸出變化當作模型質量驗收。

`m3-20260910-01/report.json` 記錄新來源合同下的另一次 1 步訓練、嚴格適配器回載、量化導出與獨立加載。量化權重從 988,097,824 字節縮至 278,064,792 字節，佔源權重 28.14%；3 個分片最大 134,188,406 字節。4 個固定問題的兩次量化模型獨立重載 logits 差均為 0；與基座的數值和文字輸出存在變化，原始輸出全部保留。錯誤訓練配方、錯誤適配器摘要真實阻斷；當前 46 項測試通過。固定問題同時包含訓練探針，不能當獨立質量評測集；該結果僅允許作為實驗產物，仍未完成候選質量准入。

官方資料：[MLX-LM 用法與 Python API](https://github.com/ml-explore/mlx-lm)、[固定 Qwen 源版本](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/tree/7ae557604adf67be50417f59c2c2f167def9a775)。具體訓練 API 與 AdamW 默認值均以本機鎖定版本源碼復核。

**原始碼新增 Apple 7B 實驗支援（2026-09-28）**：固定 Qwen2.5-7B-Instruct 已完成真實 LoRA 訓練、暫停及獨立恢復對照；普通 KV 快取可用，q4 KV 快取因輸出失敗而阻斷。原始碼支援不代表業務品質通過，也尚未進入已安裝的 046 App；新簽章候選及完整 M6 驗收仍待完成。

固定 7B 權重唯讀複核：`python3 adapters/mlx_text/prepare_model.py --variant 7b --verify-only`；移除 `--verify-only` 可下載固定版本，預設仍為 0.5B。
