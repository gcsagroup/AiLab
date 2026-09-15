<!-- translation-navigation:start -->
[简体中文](../../../docs/15-sources-and-glossary.md) · [繁體中文](15-sources-and-glossary.md) · [English](../../en/docs/15-sources-and-glossary.md)
<!-- translation-navigation:end -->

<a id="参考资料来源边界与术语"></a>

# 參考資料、來源邊界與術語

版本：1.1 · 核查日期：2026-09-09；本輪補充審計涉及的 3 項官方資料，原 15 項保留歷史核查記錄。

<a id="1-如何使用这些资料"></a>

## 1. 如何使用這些資料

產品結構來自用戶確認的最後一版 Demo；上游資料用於覈實技術概念、適配邊界和候選實現路徑。上游 README 宣稱存在功能，不代表 GCSA-AiLab 已經集成或實機通過。

本頁鏈接是動態文檔或項目頁面，實施時必須額外鎖定具體版本、commit、模型 revision 和依賴。不要把 today／latest 等浮動狀態寫進不可變執行快照。

<a id="2-官方参考资料"></a>

## 2. 官方參考資料

| 編號 | 官方資料 | 本套文檔使用範圍 | 實施時仍需確認 |
| --- | --- | --- | --- |
| SRC-01 | [MLX-LM](https://github.com/ml-explore/mlx-lm) | Apple 本地文本運行與訓練候選、緩存和量化概念 | 版本、模型家族、訓練方法、實際設備 |
| SRC-02 | [llama.cpp](https://github.com/ggml-org/llama.cpp) | 多硬件推理、GGUF 與後端構建邊界 | 具體構建、後端、模型和算子 |
| SRC-03 | [vLLM 調優](https://docs.vllm.ai/en/latest/configuration/optimization/) | Prefill、調度和性能對照設計 | 版本默認值、模型架構、設備 |
| SRC-04 | [vLLM MTP](https://docs.vllm.ai/en/latest/features/speculative_decoding/mtp/) | MTP 依賴模型能力和配套實現 | 原生組件、目標版本、實際驗收 |
| SRC-05 | [DFlash 官方項目](https://github.com/z-lab/dflash) | 目標／草稿配對、本地與服務路徑 | 精確目標和草稿版本、思考模式、引擎 |
| SRC-06 | [Qwen3-4B 模型說明](https://huggingface.co/Qwen/Qwen3-4B) | 思考開關與模板控制的具體模型參考 | tokenizer、模板、服務參數映射 |
| SRC-07 | [TRL](https://huggingface.co/docs/trl/index) | SFT、DPO、GRPO 等後訓練庫候選 | 當前訓練器 API、實驗性狀態、依賴 |
| SRC-08 | [PEFT](https://huggingface.co/docs/peft/index) | LoRA 與參數高效更新方式、適配器關係 | 模塊選擇、基座兼容、精度和訓練方法 |
| SRC-09 | [Diffusers 內存優化](https://huggingface.co/docs/diffusers/optimization/memory) | VAE 和卸載優化的條件化設計 | 模型 pipeline、設備、速度與質量影響 |
| SRC-10 | [Core ML Typed Execution](https://apple.github.io/coremltools/docs-guides/source/typed-execution.html) | CPU／GPU／ANE 圖執行與分配邊界 | 產物、形狀、系統版本、實際分配證據 |
| SRC-11 | [AMD ROCm 兼容矩陣](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html) | 設備、操作系統和軟件組合核查 | 指定 GPU、驅動和庫版本 |
| SRC-12 | [OpenVINO 設備與模式](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html) | Intel CPU／GPU／NPU 插件路徑 | 插件、模型格式、設備代際 |
| SRC-13 | [Tauri 側進程](https://v2.tauri.app/develop/sidecar/) | 桌面宿主與外部執行進程方案 | 平台打包、簽名和生命週期 |
| SRC-14 | [FastAPI 生命週期](https://fastapi.tiangolo.com/advanced/events/) | 控制服務啓動／退出設計參考 | 實際服務資源釋放、進程管理 |
| SRC-15 | [SQLite WAL](https://www.sqlite.org/wal.html) | 本地元數據庫的事務與併發設計參考 | 備份、檢查點、遷移和文件一致性 |
| SRC-16 | [vLLM 前綴緩存設計](https://docs.vllm.ai/en/latest/design/prefix_caching/) | 媒體佔位 token 與圖片哈希、緩存隔離；支持 AUD-09 修訂 | 當前引擎是否納入全部媒體／處理器身份，應用層不能弱化 |
| SRC-17 | [TRL SFT Trainer](https://huggingface.co/docs/trl/sft_trainer) | assistant-only／completion-only、模板生成標記與 packing；支持 AUD-10 修訂 | 具體 tokenizer、模板、labels、EOS/PAD、截斷和拼接策略 |
| SRC-18 | [PyTorch 安全政策](https://github.com/pytorch/pytorch/security/policy) | 模型序列化、TorchScript 與不受信任文件加載；支持 AUD-11 修訂 | 受限加載方式、允許格式、無不安全降級與執行權限 |

這些資料在編寫時已訪問核查。沒有據此聲稱本項目支持任何未測試組合，也沒有從中推導具體許可證的法律結論。

<a id="3-尚未完成的来源核查"></a>

## 3. 尚未完成的來源核查

Heretic、Abliterix 和自定義圖像網絡在原型中保留了用戶要求的產品入口。本輪沒有對其具體源碼倉庫、依賴、算法和分發條件完成專項審查，因此文檔只規定輸入、輸出、評測和待驗證工作，不給出已集成或已可發佈結論。

CosyVoice、Whisper、RVC、MusicGen、Wan、FLUX 等原型模型條目也需在各工作包中鎖定具體版本和能力。名稱存在於 Demo 不代表任一安裝環境中的真實支持。AI Beauty 的代碼復用範圍需要在明確目錄、版本和依賴後審查，本輪未複製其項目代碼。

<a id="4-训练术语"></a>

## 4. 訓練術語

| 術語 | 中文說明 | 容易混淆的地方 |
| --- | --- | --- |
| SFT | 監督微調，學習給定輸入與目標回答 | 與 LoRA 不是互斥選項；STF 在當前語境按 SFT 解釋 |
| CPT | 繼續預訓練，使用連續語料適配領域 | 本文指 continued pretraining，不是所有庫中同縮寫方法 |
| DPO | 直接偏好優化，使用優選／劣選回答 | 不等同監督正確答案訓練 |
| GRPO | 基於組內比較和獎勵的策略優化 | 獎勵上升不等於獨立能力提高 |
| PPO | 近端策略優化，訓練路徑依賴獎勵與策略配置 | 接口和實驗狀態隨庫版本變化 |
| LoRA | 用低秩適配器更新部分參數 | 通常還需要基座權重才能運行 |
| QLoRA | 在量化基座上進行適配器訓練的一類方案 | 不等於所有量化模型都能訓練 |
| 全參數更新 | 更新全部開放訓練權重 | 資源需求與適配器訓練不同 |
| 指定模塊 | 只訓練選定層或連接模塊 | 必須記錄解析後的真實模塊名 |
| 梯度累積 | 多個微批次累積後進行優化更新 | 不增加單步實際 micro batch |
| 梯度檢查點 | 用部分重算降低激活存儲 | 與保存訓練檢查點不同 |
| 檢查點 | 用於恢復的模型及訓練狀態 | 只有權重不一定能繼續原訓練軌跡 |
| 監督掩碼／Loss Mask | 指定哪些 token 參與訓練損失計算 | 與輸入是否存在不同；有效監督數為零必須處理 |
| Packing | 將多個樣本組織進訓練序列 | 必須固定樣本邊界和注意力策略，不能隱式拼接改變目標 |
| 蒸餾 | 使用教師行為或分布訓練學生 | 不是模型合併 |
| 模型合併 | 按規則組合兼容權重或適配器 | 結構相同不保證語義兼容 |
| 量化 | 降低權重或狀態表示精度 | 體積變小不保證速度和質量都更好 |
| 轉換 | 改變模型的運行表示／格式 | 文件生成成功不等於目標設備可執行 |

<a id="5-推理与优化术语"></a>

## 5. 推理與優化術語

| 術語 | 中文說明 | 產品表達要求 |
| --- | --- | --- |
| Token | 模型處理的離散單元 | 不能直接用中文字符數替代 |
| 上下文窗口 | 模型本次可處理的輸入和輸出範圍 | 歷史、模板與媒體也佔預算 |
| 思考模式 | 模型和模板支持的推理行為模式 | 關閉計算與隱藏輸出分開 |
| KV Cache | 緩存已有 token 的鍵值中間狀態 | 與權重量化和前綴復用分開 |
| 前綴緩存 | 復用重復輸入前綴對應計算 | 緩存範圍與失效條件明確 |
| Prefill | 對輸入進行初始計算 | 與後續逐 token 生成分別計時 |
| Decode | 生成後續輸出 token | 併發吞吐與單請求速度分開 |
| Chunked Prefill | 對輸入計算進行分塊調度 | 不與任何分塊參數簡單等同 |
| 連續批處理 | 運行中不斷調度多個請求 | 不等同訓練批量 |
| Attention 後端 | 注意力計算的實現路徑 | 由模型、引擎和設備決定 |
| CUDA Graph | 捕獲和重放適用的 GPU 執行流程 | 需要預熱、形狀與內存條件 |
| 推測解碼 | 草稿提出候選、目標模型驗證 | 額外草稿可能沒有速度收益 |
| MTP | 多 token 預測相關能力／組件 | 依賴目標模型與引擎支持 |
| DFlash | 使用塊擴散草稿的推測解碼方法 | 需匹配目標、草稿、模式和版本 |
| 接受率 | 草稿候選被目標驗證接受的比例 | 分母與統計口徑需寫明 |
| CPU Offload | 將部分模型或狀態移至 CPU 內存 | 可能降低顯存但增加傳輸延遲 |
| VAE Tiling／Slicing | 圖片解碼的分塊／分批處理 | 只對相應 pipeline 開放 |
| 張量並行 | 在多個設備間拆分張量計算 | 不等同數據並行，不直接擴大有效訓練批量 |
| 實際配置 | 執行器最終採用的參數 | 與表單請求配置分別保存 |

<a id="6-硬件与工程术语"></a>

## 6. 硬件與工程術語

| 術語 | 中文說明 | 邊界 |
| --- | --- | --- |
| Metal／MPS | Apple GPU 相關運行接口／後端 | 不等於 ANE |
| MLX | Apple Silicon 模型計算框架 | 模型和方法需具體適配 |
| ANE | Apple Neural Engine | 允許參與不代表所有算子實際在其上運行 |
| Core ML | Apple 模型運行／轉換生態中的接口 | 需對應格式產物和設備檢查 |
| CUDA | NVIDIA 計算棧 | 受 GPU 架構、驅動和庫版本約束 |
| ROCm／HIP | AMD 相關計算軟件棧／編程接口 | 按具體兼容矩陣驗證 |
| oneAPI／SYCL | Intel 等相關工具鏈／編程標準路徑 | 本產品首批按 Intel GPU 組合驗證 |
| OpenVINO | 模型優化和推理工具鏈 | CPU、GPU、NPU 插件分別驗證 |
| Vulkan | 跨平台 GPU 接口 | 引擎構建和設備驅動必須支持 |
| 統一內存 | CPU／GPU 共享地址或物理資源體系中的內存 | 不直接等同獨立顯存容量 |
| Revision | 可固定的資源版本 | 不使用浮動 latest 作為證據 |
| Manifest | 文件及元信息清單 | 要與真實文件摘要一致 |
| Collection | 對已計算產物進行傳輸、校驗與登記 | 不重新計算，補收記錄與原嘗試終態分開 |
| WorkflowRun | 工作流的一次具體執行 | 與可復用的工作流定義分開，步驟綁定輸入版本 |
| WorkRevision | 人工編輯形成的作品版本 | 保留原輸出與生成快照，不回寫為原模型結果 |
| 階段驗證 | 當階段可實際執行的退出檢查 | 與最終 AC 追蹤分開；M0 技術試驗不依賴後期產品 |
| 冪等 | 重復請求不會重復產生同一副作用 | 必須包含內容衝突處理 |
| SSE | 服務端向客戶端發送事件的連接方式 | 斷線後靠事件游標恢復 |
| Sidecar | 與主應用配套的獨立進程 | 獨立啓停、打包和故障管理 |
| ADR | 技術決策記錄 | 記錄依據、替代方案和結論 |

<a id="7-资料更新规则"></a>

## 7. 資料更新規則

進入適配工作包時重新核對官方來源，固定版本並保存最小可復現測試。升級時按變更影響重新驗證能力表、參數映射和報告。官方資料失效或內容變化時更新鏈接和說明，保留原驗收使用的版本身份。
