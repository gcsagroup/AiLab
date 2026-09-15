<!-- translation-navigation:start -->
[简体中文](../../../docs/05-data-model-and-assets.md) · [繁體中文](05-data-model-and-assets.md) · [English](../../en/docs/05-data-model-and-assets.md)
<!-- translation-navigation:end -->

<a id="数据模型作品与版本管理"></a>

# 數據、模型、作品與版本管理

版本：1.1 · 日期：2026-09-09 · 狀態：已按審計修訂的數據規範，原型中的內存對象與新增合同均待實現。

相關文檔：[訓練](03-training-and-model-lab.md)、[接口](07-api-and-task-lifecycle.md)、[AI 與聲明邊界](08-ai-assistance-and-data-boundaries.md)。

<a id="1-领域对象与关联"></a>

## 1. 領域對象與關聯

| 對象 | 中文名稱 | 關鍵字段 | 關係／不變量 |
| --- | --- | --- | --- |
| Project | 項目 | id、name、created_at、archived_at | 任務和評測歸屬項目，顯示名可變 |
| Model | 模型邏輯條目 | id、name、family、modality | 包含多個固定 ModelVersion |
| ModelVersion | 模型版本 | revision、artifact_ids、format、tokenizer、processor、base_id、load_policy_ref | 完成後不可改變指向的權重或加載信任記錄 |
| ModelImportPlan | 模型導入計劃 | id、manifest_digest、detected_format、loader、trust_class、execution_scope、decision_ref | 不執行待導入文件即可分析；文件或加載方式改變後重新決定 |
| Dataset | 數據集條目 | id、name、provider、source_record | 包含數據版本與獨立聲明記錄 |
| DatasetVersion | 數據版本 | manifest、schema、hash、split、transform_recipe | 訓練引用固定版本 |
| TokenizationRecipe | 分詞與監督配方 | id、version、tokenizer、processor、template、loss_scope、eos_pad、truncation、packing、digest | 訓練檢查與快照固定同一摘要，適配器不得改用默認值 |
| Artifact | 文件資產 | id、sha256、size、mime、storage_uri、status | 內容尋址；引用存在時不可直接刪除 |
| Task | 用戶任務 | id、project_id、kind、name、draft_revision | 描述目標及多個嘗試 |
| RunAttempt | 執行嘗試 | id、task_id、snapshot、state、state_version、source_attempt_id、compute_outcome、collection_state、collection_version、output_manifest_ref | 快照和終態不可改寫；收集恢復另記記錄，不重跑計算 |
| ArtifactCollection | 產物收集記錄 | id、attempt_id、manifest_digest、state、collection_version、error、registered_artifact_ids | 冪等補收原清單；成功不改原嘗試終態和原評測結論 |
| Checkpoint | 檢查點 | attempt_id、step、optimizer_state、rng_state、artifacts | 聲明能否恢復，完整性可驗證 |
| Evaluation | 評測報告 | baseline、candidate、dataset_version、metrics、thresholds | 固定輸入和規則，報告不可就地改寫 |
| Candidate | 模型候選 | model_version、source_attempt、evaluation_ids、status | 登記可用前通過准入檢查 |
| Recipe | 配方 | schema_version、requested_config、effective_config、input_refs | 可複製成新草稿，原記錄不可變 |
| WorkflowRun | 工作流運行 | id、project_id、definition_version、revision、current_step、step_attempts、accepted_outputs | 每次開始新建 id；推進原子校驗來源和目標可進入性 |
| WorkflowStepAttempt | 步驟嘗試 | id、workflow_run_id、step_id、input_revision、input_digest、run_attempt_id、output_refs、reuse_source | 輸入版本不可變；舊結果只能經明確復用記錄成為輸入 |
| Work | 作品 | project_id、artifact_id、source_attempt、current_revision_id、favorite | 收藏是屬性，保存意味著文件已持久化 |
| WorkRevision | 作品修訂 | id、work_id、parent_revision_id、artifact_id、changes、editor、created_at | 保存字幕等人工修訂，不改原輸出、執行快照或生成配方 |
| ExportPlan | 產物導出計劃 | id、digest、object_versions、dependency_manifest、target_format、estimated_bytes、validation_rules | 固定源版本與依賴；執行前復核，完整性通過後發佈本地導出目錄 |
| Device | 執行設備 | id、endpoint_ref、detected_facts、last_seen | 憑證只保存引用 |
| Environment | 運行環境 | engine、version、dependencies、driver、digest | 每次嘗試固定版本快照 |

任務、執行嘗試和產物必須分開。用戶重命名任務不影響產物身份；重新執行產生新嘗試；同一文件可以被多個作品或模型引用。

`RunAttempt.state` 的成功／失敗／取消終態不可變。`compute_outcome` 單獨說明計算是否完成，`collection_state` 匯總最新已持久化收集記錄；補收可將收集狀態從失敗變為成功，但原嘗試仍保留“計算完成、收集曾失敗，現已補收”的事實。原產物清單必須由執行器封存，包含文件相對路徑、大小、摘要、用途、完整標記和保留位置。沒有完整清單或計算未完成時不能把重算包裝成補收，具體控制合同見 [07](07-api-and-task-lifecycle.md)。（AUD-08）

<a id="2-数据生命周期"></a>

## 2. 數據生命週期

發現／選擇來源 → 獲取訪問 → 下載／導入 → 文件完整性檢查 → 解析與預覽 → 技術檢查 → 用戶選擇處理 → 新版本 → 訓練／評測引用 → 歸檔或解除引用。

處理中間文件寫入臨時目錄，完整性檢查通過後原子登記到資產存儲。下載取消保留可續傳的臨時信息，但不能將部分文件標記為完整。校驗失敗保留可診斷記錄並允許重新下載，不覆蓋已經被任務引用的舊版本。

<a id="3-数据集市场"></a>

## 3. 數據集市場

<a id="31-详情字段"></a>

### 3.1 詳情字段

名稱、描述、模態、schema、版本、樣本數量、文件大小、格式、提供方、來源鏈接、更新時間、提供方原文、訪問方式、原始許可文件引用、用戶使用範圍聲明、下載完整性信息。

字段未知時顯示未知，不自動補成開放授權。提供方更新數據時產生新版本；舊實驗仍指向舊版本。

<a id="32-访问状态"></a>

### 3.2 訪問狀態

| 狀態 | 用戶可執行操作 | 轉移條件 |
| --- | --- | --- |
| 開放下載 | 下載、查看詳情 | 提供方公開訪問 |
| 需要申請 | 填寫用途、提交申請 | 用戶主動提交 |
| 等待處理 | 查看、撤回申請（如提供方支持） | 提供方處理 |
| 訪問獲准 | 下載、查看原文和有效期 | 提供方授予訪問 |
| 訪問拒絕 | 查看原因、重新申請（如允許） | 提供方返回結果 |
| 訪問到期／撤銷 | 查看已保存記錄、重新申請 | 提供方變更條件 |

訪問狀態只描述提供方訪問控制。用戶聲明與許可材料獨立存儲，AI 不將任何一種訪問狀態改寫成合法性結論。

<a id="33-首期接入方式"></a>

### 3.3 首期接入方式

先使用一個官方／公開資源連接器或受控測試目錄驗證瀏覽、版本、下載和哈希；受限申請使用受控測試服務，不假設任意市場都有同樣 API。每個連接器明確支持的字段與操作，缺失字段保留空值。

<a id="4-数据格式合同"></a>

## 4. 數據格式合同

| Schema | 必需結構 | 附加信息 | 檢查重點 |
| --- | --- | --- | --- |
| `sft` | messages 中包含 role、content | source_id、語言、任務標籤 | 角色序列、空回答、聊天模板兼容 |
| `cpt` | text、source_id | 文檔分段信息 | 空文、編碼、文檔邊界 |
| `dpo` | prompt、chosen、rejected | 媒體或對話結構由適配器擴展 | chosen 與 rejected 不能完全相同 |
| `grpo` | prompt、answer | 驗證器標識與版本 | 答案可驗證、獎勵函數輸入匹配 |
| `ppo` | prompt | 獎勵模型、參考策略由任務配置指定 | 提示詞有效、獎勵模型可準備 |
| `vision` | messages、media | 媒體類型、幀採樣參數 | 文件可讀、順序與對話引用一致 |
| `vision-dpo` | media、prompt、chosen、rejected | 圖文佈局 | 回答必須基於同一媒體輸入 |
| `image` | image、caption | trigger、尺寸、裁剪 | 解碼、方向、重復、標注 |
| `paired` | source、reference、target | 對齊方式、掩碼 | 三者對應及空間／語義關係 |
| `video` | video、caption、fps、frames | duration、切片邊界 | 解碼、時間基準、元數據一致 |
| `tts` | audio、text、speaker | language、情緒 | 實際時長、轉寫和說話人 |
| `asr` | audio、text、language | 句級時間戳 | 文本規範和音頻對應 |
| `vc` | audio、speaker | pitch、特徵文件 | 特徵提取版本與錄音關係 |
| `music` | audio、description、duration | 節奏、風格 | 時長、聲道和描述 |

所有路徑都經工作區資產層解析，不直接接受可越出授權目錄的任意相對路徑。遠程 URL 僅由下載器處理，訓練器讀取已經登記的本地或執行設備資產引用。

<a id="41-可解析的最小示例"></a>

### 4.1 可解析的最小示例

以下 JSON 是結構示例，不包含實際媒體文件，也不是可直接用於質量驗收的數據集。

```json
{
  "schema": "sft",
  "samples": [
    {
      "source_id": "售后示例-001",
      "messages": [
        {"role": "user", "content": "申请退货前需要准备哪些信息？"},
        {"role": "assistant", "content": "先准备订单编号、商品信息和购买渠道，再核对适用政策。"}
      ]
    },
    {
      "source_id": "售后示例-002",
      "messages": [
        {"role": "user", "content": "不知道购买日期怎么办？"},
        {"role": "assistant", "content": "可先查订单记录或付款凭证，确认日期后再核对期限。"}
      ]
    }
  ]
}
```

```json
{
  "schema": "video",
  "sample": {
    "video": "artifact:video-001",
    "caption": "镜头缓慢推近商品，主体保持居中。",
    "fps": 16,
    "frames": 80,
    "duration": 5
  },
  "provenance": {
    "source_record": "用户导入的示例素材",
    "user_statement": "由用户填写",
    "technical_check_status": "未检查"
  }
}
```

正式支持 JSONL 時每行一個獨立樣本對象。導入器識別 schema 後展示字段映射，不把任意數組自動當成 messages。導入報告包含有效、失敗、跳過樣本數量和具體行號。

<a id="42-分词与监督配方"></a>

### 4.2 分詞與監督配方

SFT 使用 [03 的監督合同](03-training-and-model-lab.md)，以數據版本、配方摘要、適配器版本形成檢查身份。以下是首個文本對話模板的設計示例；編號均為佔位，實際版本必須由選定模型解析，不能直接作為引擎配置提交。

```json
{
  "id": "tokenization-dialogue-001",
  "version": 1,
  "tokenizer_ref": "固定分词器版本",
  "processor_ref": null,
  "chat_template_ref": "固定模板版本",
  "loss_scope": "assistant_only",
  "label_shift_owner": "model",
  "supervise_turn_end": true,
  "padding_label": -100,
  "eos_pad_policy": "按位置区分真实结束标记与补齐位置",
  "max_sequence_tokens": 2048,
  "truncation": {"strategy": "exclude_overlong", "report_excluded": true},
  "packing": {"enabled": false},
  "zero_supervision": "exclude_sample_and_reject_empty_split",
  "digest": "示例摘要，实际按规范化配置计算"
}
```

檢查產物包括計數報告、代表樣本的 `input_ids`／`attention_mask`／`labels` 對照和媒體位置映射（如適用）；這些是項目內訓練證據，不進入普通診斷包。掩碼規則變更必須創建新配方及新檢查，不能只更新一份可變的“訓練模板默認”。

<a id="5-技术检查和数据处理"></a>

## 5. 技術檢查和數據處理

<a id="51-检查分层"></a>

### 5.1 檢查分層

1. 容器：文件存在、大小、編碼、哈希、解壓限制。
2. 結構：必需字段、類型、角色、引用、空值。
3. 媒體：實際解碼、採樣率、尺寸、幀率、時長和邊界。
4. 重復：內容哈希、近重復候選、訓練／驗證重疊。
5. 任務適配：模板可渲染、實際 token／labels 與監督範圍、序列預算、配對關係、獎勵規則可調用。

報告中的檢查結論必須區分已運行與未運行。示例“字段完整”不能表示媒體文件已被讀取。

<a id="52-处理不覆盖原件"></a>

### 5.2 處理不覆蓋原件

去重、排除、裁剪、切片、重採樣、補充標注等操作先顯示影響範圍，用戶應用後生成新數據版本。處理記錄包含操作、參數、工具版本、輸入版本和輸出 manifest。原始數據仍可查看、撤銷引用或重新派生。

<a id="53-划分与泄漏"></a>

### 5.3 劃分與洩漏

固定劃分隨機種子；按文檔、說話人、視頻、主體或來源組劃分，避免同一實體的近似樣本跨訓練和驗證。測試集不能因模型表現而回流訓練。用戶調整劃分後舊技術檢查與評測緩存失效。

Demo 中“至少兩個有效樣本”僅用於模擬流程校驗，真實質量驗收必須有任務匹配的樣本量和統計解釋。

<a id="6-文件与版本策略"></a>

## 6. 文件與版本策略

建議邏輯佈局：元數據庫、內容尋址文件、任務目錄、環境目錄、臨時下載、緩存、日誌、導出包分別存儲。最終物理根目錄由用戶選擇並記錄，不能默默寫入其他項目。

數據庫保存索引和關係，大文件保存在文件系統。寫入採用臨時文件、校驗、原子移動、事務登記；應用啓動時回收未完成登記的孤立臨時文件前先給出清單。內容相同的文件可以去重，記錄仍按項目與版本分別存在。

刪除使用引用檢查和可恢復區。已被實驗、模型、作品或報告引用的文件先解除引用或歸檔，不能直接清空。緩存可單獨清理，但正在使用的緩存需要等待使用完成或取消請求。

<a id="7-模型和适配器"></a>

## 7. 模型和適配器

模型版本要記錄權重文件列表、格式、大小、精度、模型配置、tokenizer、處理器、聊天模板、來源 revision、許可證文件引用和完整性狀態。

模型導入計劃另記錄實際識別格式、固定加載器及版本、受限加載選項、信任類別、允許訪問的文件／網絡／憑證範圍、用戶對所需執行能力的決定及執行隔離證據。信任類別為受限權重、需要代碼執行、未知／不支持；摘要匹配只證明文件一致，不能把可執行序列化文件變成安全權重。未知格式、偽裝格式或受限加載失敗都不自動降級到任意反序列化，規則詳見 [06](06-architecture-and-adapters.md)。（AUD-11）

LoRA 適配器必須綁定基座版本、目標模塊和參數配置。僅有適配器文件時，不顯示為獨立完整模型。試用入口自動檢查基座是否準備，並明確是“基座 + 適配器”還是已合併權重。

量化模型、Core ML、ONNX、GGUF 等產物保留源版本關係。後續操作由轉換／訓練適配器聲明：不能從文件擴展名或原型的 `runtimeOnly` 字段推斷所有能力。

跨設備 LoRA 試用同時固定訓練端產物摘要、源基座 revision、目標模塊和參數、目標引擎／模板及轉換記錄。若產生轉換產物，保留原 LoRA 和新產物的雙向來源關係；候選只能對實際驗證的目標組合標為可用，不能繼承源模型全部設備能力。（E-03、AUD-05）

<a id="8-作品与配方"></a>

## 8. 作品與配方

保存作品意味著產物文件已驗證和持久化，收藏僅用於篩選。輸入素材、生成結果和中間產物分別記錄，用戶可從結果查看原任務、原模型和輸入來源。

配方至少保存：schema 版本、任務種類、項目引用、模型與適配器版本、輸入資產與文本、請求配置、實際配置、環境、隨機種子、工作流節點、產物和時間。載入配方創建可編輯副本；如果舊引擎或模型不可用，先列出差異，不直接以新版本冒充相同環境。

<a id="81-工作流的执行身份与失效"></a>

### 8.1 工作流的執行身份與失效

工作流定義是模板；每次“開始”必須新建 `WorkflowRun.id`，不能僅以模板編號尋找結果。步驟輸入修改產生新的 `input_revision` 和摘要，運行提交時綁定對應 `WorkflowStepAttempt.id`；接受下一步輸入時必須核對本次運行、本步驟、本輸入版本和完整產物。沒有本輪結果時保持等待，不從歷史列表第一項回退取圖。（AUD-01）

用戶明確選擇“復用已有結果”後，新建當前步驟的復用記錄，保存源嘗試、產物摘要、來源輸入版本、選擇動作和時間，並顯示輸入與舊結果的差異。復用不算新計算。上游輸入修改後，下游引用原輸入版本的結果標為過期，舊資產和歷史仍保留；重做或再次明確接受來源之前不能將過期鏈保存為當前完整工作流。

“帶入下一步”在一個事務中檢查運行 revision、步驟輸入版本、選中產物和目標類別佔用狀態，再一起提交當前產物接受記錄、目標草稿引用與步驟位置。目標不可進入或版本衝突時這三者全部不變；客戶端只按成功響應切頁。佔用狀態由控制服務在提交時重新判斷，不能僅依靠提前檢查；目標任務剛完成／剛取消時也只能推進一次。（AUD-02）

<a id="82-字幕与其他人工修订"></a>

### 8.2 字幕與其他人工修訂

原轉寫／生成結果及生成 `Recipe` 保持不可變。字幕校正寫新的 `WorkRevision`，保存原版本、修訂文件、文字／時間戳差異和編輯信息；作品可切換查看原輸出與各次修訂。界面分別展示“生成設置”和“人工修訂”，禁止把編輯後的轉寫寫回聲稱“提交時固定”的配方。（E-04）

重跑原生成配方不隱含套用人工校正。使用校正文案繼續生成須顯式選定修訂版本並寫入新嘗試的輸入；導出時同樣固定用戶選擇的原版或修訂版，不能隨當前界面選擇變化。

<a id="83-用户产物导出"></a>

### 8.3 用戶產物導出

導出計劃固定模型、適配器、作品修訂或報告的對象版本，解析所有內含文件與外部依賴。適配器的基座依賴必須有確切 revision／摘要及獲取說明，可選擇一並打包或明確作為外部依賴；“包完整”不等於“無需基座即可獨立運行”。導出清單、完整性、落盤和失敗恢復合同見 [12](12-operations-and-release.md)，WP-29 負責普通產物導出，診斷導出不能代替它。（AUD-13）

<a id="9-数据库与一致性要求"></a>

## 9. 數據庫與一致性要求

- 所有可編輯草稿有 revision，避免 AI 建議和用戶手工修改相互覆蓋。
- 固定版本對象使用唯一標識和內容摘要，禁止就地改變已被執行快照引用的內容。
- 運行狀態變更和事件寫入使用同一事務或可靠 outbox，避免前端看到完成但沒有產物。
- 數據庫遷移前備份；遷移失敗不啓動運行器，不刪除舊庫。
- 備份必須包含數據庫、一致的文件 manifest 和密鑰引用說明；不把明文憑證打包。

<a id="10-验收标准"></a>

## 10. 驗收標準

導入真實文本、圖片、視頻和音頻樣本，檢查失敗定位；執行處理後原文件哈希不變；任務重啓後仍能找到相同版本；跨項目後台結果歸屬正確；配方重載保留模型和輸入；刪除被引用資產受到約束。詳細用例見 [11](11-testing-and-acceptance.md)。
