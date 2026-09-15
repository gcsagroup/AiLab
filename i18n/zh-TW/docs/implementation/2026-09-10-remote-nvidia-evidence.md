<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-10-remote-nvidia-evidence.md) · [繁體中文](2026-09-10-remote-nvidia-evidence.md) · [English](../../../en/docs/implementation/2026-09-10-remote-nvidia-evidence.md)
<!-- translation-navigation:end -->

<a id="独立执行目标与-nvidia-文本组合实现和验证记录"></a>

# 獨立執行目標與 NVIDIA 文本組合：實現和驗證記錄

Ver2.0 已把執行目標、項目默認位置、單次任務選擇、上傳範圍確認、原編號事件同步、取消和只補收接入控制服務。HTTPS 隨 Ver2.1（004）首次打包，Ver2.1（005）隨後通過整包、內置 CA 和原生未知 CA 拒絕驗收；本頁保留這些階段證據。當前簽名候選已更新為 Ver2.2（010），尚未完成該包的遠程原生復驗，也未對外發佈，最新狀態見[010 執行進度](2026-09-12-ver2-2-010-progress.md)。文件傳輸使用獨立進程、持久 SQLite 和真實文件；文本執行器包含固定 NVIDIA 推理與 SFT + LoRA 實現。

當前機器是 Apple Silicon Mac。公共 NVIDIA 入口會明確拒絕運行，未做 CPU 或 Apple 回退。跨主機網絡接入、NVIDIA 實機推理/訓練、該適配器的質量准入仍未驗收；回環傳輸成功不能替代這三項。

<a id="用户操作与边界"></a>

## 用戶操作與邊界

1. 在“設備與環境”登記執行服務的固定地址與身份，再檢查連接。Ver2.1（005）階段已實現 `https://主机:端口`，並保留字面 `http://127.0.0.1:端口` 回環模式；HTTPS 必須通過運行時公開 CA 包的證書鏈、主機名和有效期驗證。連接不採用代理、不跟隨重定向、不降級為 HTTP；上述舊包驗收不代替 010 的實際跨主機驗證。
2. 原生 App 將憑據保存到系統鑰匙串；控制服務只持有當前會話的明文。數據庫只保存隨機引用，不保存明文憑據。鎖定或缺失時必須重新連接；恢復備份會清理憑據引用。開發網頁只支持內存會話憑據。
3. 每個項目可保存默認執行目標，只影響以後新建的文本草稿。任務中的執行位置是單次覆蓋，不會改動已有草稿或其他項目。媒體任務繼續採用已有固定組合。
4. “傳輸驗證”只上傳已導入的數據或素材。先顯示目標、文件名、每個文件字節數和摘要，再由用戶明確開始；它不會加載模型。
5. 文本任務預檢凍結目標版本、模型/數據清單、代碼與分詞配方身份。NVIDIA 未就緒時不創建遠端運行，也不上傳模型。可以執行時仍先顯示上傳範圍，由用戶明確開始。
6. 斷線或證書驗證失敗不等於停止。取消意圖和完整取消命令先持久化，提交正在發出或連接恢復後繼續向原編號發送；確認原進程組退出前保留待確認狀態。補收只讀取原封存清單，不創建新計算，原回收失敗記錄仍保留。

上傳分塊為 1 MiB，單個模型文件最多 2 GiB，輸入總量最多 4 GiB，最多 16 個文件；傳輸驗證每個文件另限 64 MiB。服務分別預留已上傳文件、執行輸入副本和產物空間。上傳在每個哈希/傳輸分塊檢查取消和宿主退出。

<a id="固定-nvidia-组合"></a>

## 固定 NVIDIA 組合

| 項目 | 當前實現 |
| --- | --- |
| 設備 | Linux、CUDA 12.8、`cuda:0`、支持 BF16、至少 8 GiB 顯存；實際小矩陣探測後釋放 |
| 模型 | `Qwen/Qwen2.5-0.5B-Instruct` 原權重，完整清單摘要 `a9b08fa2b761cbfc7335b28c6b0997b6e7713893aaca4b215625ffc99a1d36b3` |
| 依賴 | PyTorch 2.10.0、Transformers 4.57.6、PEFT 0.18.1、Accelerate 1.12.0、Safetensors 0.7.0、NumPy 2.4.2 |
| 生成 | BF16 基座、逐 token 生成、固定 seed；支持 greedy/temperature/top-p、停止序列、流式開關及有限上下文；最多輸出 512 tokens |
| 訓練 | SFT + LoRA、最後指定層的 q/v 投影、僅助手內容與結束標記參與損失、BF16 基座與 FP32 LoRA；不截斷監督樣本，不訓練 embedding |
| 訓練產物 | PEFT 原格式、明確轉置得到的 MLX LoRA、轉換來源報告；始終是實驗產物 |
| 暫未開放 | QLoRA、CPT、遠端 checkpoint/暫停繼續、遠端適配器推理、未知模型或任意命令 |

PyTorch 的 CUDA 12.8 安裝組合來自[官方歷史版本安裝頁](https://pytorch.org/get-started/previous-versions/)；模型和 LoRA 參數按固定版本的 [Transformers Qwen2 實現](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/qwen2/modeling_qwen2.py)與 [PEFT LoRA 配置](https://github.com/huggingface/peft/blob/v0.18.1/src/peft/tuners/lora/config.py)實現。這裡採用已固定版本，不表示它們是最新版本。

實際 tokenization 與監督樣本檢查在輸入上傳後、模型分配前完成。預檢中的 `tokenization_check=on_executor_before_model_allocation` 明確表示該邊界；它不能寫成已經完成遠端樣本計算。

<a id="完成接收与恢复"></a>

## 完成接收與恢復

- 工作進程的 stdout 是有界 NDJSON 事件，庫日誌進入獨立 stderr。執行服務覈實子進程身份與整個進程組退出後才確認終態。
- 完成門檻逐項核對引擎、設備、精度、全部有效參數、固定模型、源碼與精確分詞配方。生成必須有 5 個固定文件，訓練必須有 9 個固定文件；缺正文或只有 metrics 不能成功。
- 收回文件後再次核對 `effective-config.json` 與完成對象、環境/計算設備、LoRA 轉換來源和權重摘要。文件名齊全不代表報告內容可信。
- 本機收集使用獨立字節副本，逐文件驗證後排他發佈。禁止用硬鏈接破壞遠端收回目錄的單鏈接約束，因此本機登記暫時失敗後仍可按原清單補收。
- 源碼身份固定在模塊加載時。磁盤源碼變化後舊進程不能報告新摘要，必須重啓執行服務後再檢查。
- 已請求取消而原計算先結束時保存這一事實，不偽造“取消已生效”；只有原執行返回已取消並確認進程組退出，才顯示取消完成。

<a id="当前证据"></a>

## 當前證據

證據均保留在工作區，失敗復現不刪除。最終整包和界面驗收由發佈記錄單獨關聯。

Ver2.0 階段控制服務、執行協議及 NVIDIA 合同合計 **667 項測試通過**；隨後補入的跨目標 101 條歷史分頁用例另 **1 項通過**。獨立審查的完成接收合同 **15 項通過**，取消/補收兩條失敗原復現已修復並通過復驗。NVIDIA CPU 組件 v3 和公共 CUDA 拒絕 v2 的源摘要均為 `a88a481daa39fe196586ca9a93307dd277d81e89df9dfea73398a5784feeb5f7`。

HTTPS 候選的後端組合回歸 **168 項通過**，最後 TLS/控制鏈針對性復驗 **73 項通過**，兩輪分別計數。實際覆蓋證書拒絕、運行中換證書、分塊續傳、原編號取消、重啓及原清單補收；10 次服務正常退出、強殺 0。詳見 [HTTPS 後端讀回](../../../../.artifacts/https-implementation-ver2-next-v1/backend-readback.json)。這些新測試只有本機回環 TLS 和 CPU 合同夾具，模型生成、訓練和外部主機連接均為 0。

| 證據 | 證明範圍 |
| --- | --- |
| `.artifacts/control/remote-integrated-final.xml`、`remote-target-pagination.xml` | 最終完整回歸 667 項及新增分頁 1 項 |
| `.artifacts/control/remote-product-all.xml` | 目標/憑據權限、默認位置、真實 NVIDIA 探測阻斷、上傳/取消/斷線/補收的產品 API 專項 |
| `.artifacts/control/remote-export-regression.xml` | 導出任務不含草稿時仍返回業務拒絕；模型、適配器、作品、報告導出回歸 |
| `.artifacts/control/remote-review-fixes.xml` | 完成合同負例與獨立復現的取消/補收修復驗證 |
| `.artifacts/desktop/remote-product-review/` | 獨立復現：登記失敗後補收、提交時取消；原失敗日誌與修復復驗 |
| `.artifacts/nvidia-completion-independent-v1/` | 獨立完成接收合同正反例；明確沒有運行模型或 GPU |
| `.artifacts/nvidia-text/cpu-components-v2/report.json`、`cpu-components-v3/report.json` | 真實 0.5B 原權重在 CPU 上的組件驗證；不是 NVIDIA 驗收 |
| `.artifacts/nvidia-text/public-cuda-rejection*.json` | 公共入口實際拒絕本機執行、不創建輸出、不走 CPU 回退 |
| `.artifacts/nvidia-text/runtime-freeze.txt` | 本機隔離組件測試環境的完整依賴記錄；該環境 Python 為 3.14.6 |

CPU 組件測試實際生成“完成”，運行兩步 LoRA 並檢查參數變化、embedding 抽樣不變、PEFT→MLX 矩陣逐值轉置與數值等價。它只證明這些計算組件和文件轉換在 CPU 上執行；沒有證明 CUDA 內存、BF16 實機表現、Apple 獨立加載或質量改善。

<a id="执行服务准备示例"></a>

## 執行服務準備示例

以下是候選版本的安裝與啓動說明，不表示已經在 NVIDIA 主機部署。控制包要求 Python 3.13 或以上；應在獨立目錄和虛擬環境中操作，禁止使用主 App 工作庫作為執行服務目錄。

```sh
python3.13 -m venv .venv-nvidia
.venv-nvidia/bin/python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
.venv-nvidia/bin/python -m pip install -r adapters/nvidia_text/requirements.txt
.venv-nvidia/bin/python -m pip install -e services/control
.venv-nvidia/bin/python workers/nvidia_worker.py --mode probe
```

啓動器需要已生成的獨立憑據文件（權限 `0600`，32—512 位可見 ASCII），不會輸出憑據。服務握手返回端口、執行器身份、PID、連接方式和驗證範圍；將對應地址、執行器編號和憑據登記到 App。

HTTPS 模式必須顯式給出 `--https`、`--bind`、`--cert-file` 和 `--key-file`。以下變量及路徑應替換為已經準備好的配置：綁定值為服務本機 IP，登記地址中的主機必須與證書匹配。私鑰須由當前用戶擁有、權限為 `0600`，使用無口令 PEM；證書鏈須能由客戶端隨附的公開 CA 包驗證。當前沒有私有 CA 配置入口。

```sh
.venv-nvidia/bin/python -m ailab_control.remote \
  --data-dir /新的独立HTTPS执行目录 \
  --token-file /明确授权的私有凭据文件 \
  --https --bind "$AILAB_EXECUTOR_BIND_IP" --port "$AILAB_EXECUTOR_PORT" \
  --cert-file /已准备好的完整证书链.pem \
  --key-file /权限为0600的服务私钥.pem
```

一個執行目錄固定一種連接方式。已有回環目錄不能直接改成 HTTPS，須使用新的獨立目錄及其新執行器身份。原回環啓動方式繼續保留：

```sh
.venv-nvidia/bin/python -m ailab_control.remote \
  --data-dir /明确独立的执行目录 \
  --token-file /明确授权的私有凭据文件 \
  --port 0 \
  --loopback-contract-only
```

本機 TLS 驗證不代表跨物理 NVIDIA 驗收。NVIDIA 實機仍須完成固定模型推理、SFT、取消/斷線/補收、顯存與進程釋放，以及按訓練前凍結方案進行的質量對照，才能更新相應交付狀態。005 原生通過登記與真實未知 CA 拒絕，目標顯示證書錯誤、傳輸入口禁用，執行庫未接收文件或任務；服務正常退出，臨時憑據已清除。見[原生目標後驗](../../../../.artifacts/native-https-rejection-ver2-005-v1/run-001/root-native-target-postcheck.json)與[本輪原生匯總](../../../../.artifacts/integration-ver2-1-005-v1/native-acceptance/本轮原生验收.json)。
