<!-- translation-navigation:start -->
[简体中文](../../../../adapters/media/README.md) · [繁體中文](README.md) · [English](../../../en/adapters/media/README.md)
<!-- translation-navigation:end -->

<a id="m4-本机媒体执行器试验"></a>

# M4 本機媒體執行器試驗

這裡是獨立 CLI 與媒體執行橋的真實模型證據入口。圖片選擇 Tiny-SD + UNet LoRA；視頻選擇 SVD 圖生視頻；TTS 由獨立 `tts_*` 執行器記錄。執行橋已提供固定參數檢查、來源綁定、真實事件、取消與產物封存。控制服務和 UI 的媒體路徑由產品驗收另行記錄，不能把 CLI 或執行橋通過等同於 `GATE-M4` 通過。

<a id="冻结组合与证据"></a>

## 凍結組合與證據

| 項目 | 固定選擇 | 當前邊界 |
| --- | --- | --- |
| 圖片基座 | `segmind/tiny-sd`，revision `cad0bd7495fa6c4bcca01b19a723dc91627fe84f` | 官方約 1.062 GB；先驗證受限讀取，再轉換 safetensors；只加載標準 Diffusers 類 |
| 圖片推理 | PyTorch 2.14.0 / Diffusers 0.35.2 / Python 3.13 / MPS FP32 | 512×512、20 採樣步、CFG 7.5、固定 CPU 隨機發生器；不啓用 MPS 算子回退 |
| 圖片訓練 | PEFT 0.18.1、UNet attention LoRA | rank/alpha 4、12 步、批量 1、AdamW 1e-4；VAE/CLIP/基座凍結；epsilon 去噪監督 |
| 圖片數據 | 本次基座生成的 4 張商品茶壺圖 | 來源明確標記為合成；不是外部語料，不證明業務數據權利或風格質量提升 |
| 短視頻基座 | `stabilityai/stable-video-diffusion-img2vid`，revision `9cf024d5bfa8f56622af86c884f26a52f6676f2e` | 3 個 fp16 safetensors 權重合計 4,509,185,018 字節；公開無登錄下載 |
| 短視頻試驗 | 同一 Diffusers/PyTorch 環境，MPS FP16 | 1024×576、14 幀、7 FPS、25 步；真實圖片條件；獨立 FFmpeg 解碼；尚未實現視頻訓練 |

每次執行新建獨立輸出目錄。生成結果保存 PNG 與浮點像素、實際參數、加載和生成耗時、進程身份、依賴版本與文件摘要。圖片訓練記錄每步 loss/梯度、實際可訓練張量、權重變化、凍結參數前後摘要及獨立 safetensors LoRA。內存分別記錄進程峰值 RSS 和結束時 MPS 驅動分配量；當前 MPS 接口沒有獨立峰值讀數，不能把結束值當成顯存峰值。

<a id="复跑"></a>

## 復跑

在項目根目錄執行。所有權重和依賴都放在 `.artifacts/m4-media`，不讀取 `~/Models`，也不修改已有文本執行器環境。

```sh
/opt/homebrew/bin/python3.13 -m venv .artifacts/m4-media/venv
.artifacts/m4-media/venv/bin/python -m pip install \
  --no-index --find-links .artifacts/m4-media/wheels/pytorch-official \
  --find-links .artifacts/m4-media/wheels/resolved \
  --require-hashes -r adapters/media/requirements.lock.txt

# 来源 API 必须对应冻结 revision；若 main 已改变，取固定版本 API，不篡改 SHA。
.artifacts/m4-media/venv/bin/python adapters/media/prepare_tiny_sd.py \
  --root .artifacts/m4-media/model --api .artifacts/m4-media/sources/tiny-sd-api.json
.artifacts/m4-media/venv/bin/python adapters/media/run_image_acceptance.py \
  --root .artifacts/m4-media --run-name acceptance-next

.artifacts/m4-media/venv/bin/python adapters/media/prepare_svd.py \
  --root .artifacts/m4-media/svd-model --api .artifacts/m4-media/sources/svd-api.json
.artifacts/m4-media/venv/bin/python adapters/media/video_cli.py \
  --model-root .artifacts/m4-media/svd-model \
  --input .artifacts/m4-media/acceptance-v2/base-blue_cup/image.png \
  --output .artifacts/m4-media/video-acceptance-next

/opt/homebrew/bin/python3.13 -m unittest discover -s tests/media -v
```

驗收目錄已存在時腳本拒絕覆蓋。復跑需選擇新的證據根目錄，或逐個調用 `image_cli.py generate/train` 指向新的輸出目錄，不能刪除舊證據後偽稱首次通過。`run_image_acceptance.py` 在生成前凍結訓練 seed 和兩個獨立評測樣例；候選還會在另一個進程重新加載，同 seed 浮點像素最大誤差上限為 `1e-5`。像素變化僅證明適配器生效，不是質量改進評分。

上面安裝命令使用本次實際核驗過的本地 wheel 檔案。該 lock 專用於 macOS arm64 / Python 3.13；Torch 文件來自 PyTorch 官方索引，同版本 PyPI 文件摘要不同，不能混用。原始索引與下載來源快照在 `sources`，實際安裝日誌是 `logs/install-local-verified.log`。當前完整圖片驗收在 `acceptance-v2`；`acceptance-v1` 保留首次 JSON 寫出失敗的原始證據，不計作成功。

已驗證結果見 [ACCEPTANCE.md](ACCEPTANCE.md)。兩組圖片與 LoRA 的功能通過；紅壺提示生成了白壺，候選還有多餘杯子和柄部異常，不能稱為商品質量通過或訓練改善。

大文件通過官方 HTTP Range 端點有界下載；逐段核對響應區間，最終對照官方 LFS SHA256 後才發佈完成文件。中斷時保留部分文件，受限加載或摘要失敗不會降級為任意 pickle 讀取。分段器的真實本地 HTTP 測試覆蓋已下載前綴續傳與損壞前綴拒絕。

<a id="许可和源代码依据"></a>

## 許可和源代碼依據

- [Tiny-SD 官方模型卡與固定源](https://huggingface.co/segmind/tiny-sd/tree/cad0bd7495fa6c4bcca01b19a723dc91627fe84f)標明 CreativeML OpenRAIL-M，並說明從 Realistic Vision V4.0 蒸餾。模型卡聲明不能證明全部上游訓練語料或輸出權利；本試驗不提供底模打包發佈許可結論。
- [Diffusers 0.35.2 官方 LoRA 訓練源碼](https://github.com/huggingface/diffusers/blob/v0.35.2/examples/text_to_image/train_text_to_image_lora.py)提供凍結 VAE/CLIP/UNet、添加 attention LoRA、隨機 timestep 去噪 MSE、保存適配器的依據。這裡實現了固定單設備最小循環，並實際檢查更新與重載，不直接運行倉庫任意腳本。庫代碼是 Apache-2.0。
- [PyTorch 官方受限權重讀取](https://docs.pytorch.org/docs/2.14/notes/serialization.html#torch-load-with-weights-only-true)及 [MPS 接口](https://docs.pytorch.org/docs/2.14/mps.html)用於加載和設備邊界；使用 `weights_only=True` 失敗時不擴大執行權限。實際 Torch wheel 來源為 PyTorch 官方索引，wheel SHA256 為 `caf6359d64c0074bcb9f8641a169239118c8165a0a0fef79110c72bfd6474bec`。
- [SVD 固定源許可證](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid/blob/9cf024d5bfa8f56622af86c884f26a52f6676f2e/LICENSE.md)含商業註冊與年度收入條件。當前僅做本地評估測試，不將它聲明成無條件可商用模型，也不把權重打入應用包。
- [SVD 官方模型卡](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid)說明它以圖像為條件、原生 14 幀，不能用文本控制；模型可能產生靜止或緩慢運動。接口不偽造 `prompt` 控制能力。

相應官方 API、許可證及讀取過的上游源碼快照保存在 `.artifacts/m4-media/sources`。Wan 1.3B 官方 Diffusers 版本此次未選：其源文件實際約 29 GB，且首組合是文生視頻，超出本次總下載預算，也不能直接承擔商品圖輸入。Kokoro 的包版本、中文前端、設備與聲音輸出證據見獨立 TTS 說明。

<a id="尚未完成的产品验收"></a>

## 尚未完成的產品驗收

媒體模型準備、任務生命週期/恢復、候選質量准入、普通用戶導出、兩輪商品圖→視頻→配音工作流及市場返回仍須後續接入真實控制服務和 UI 驗證。CLI 的獨立 PNG/MP4 解碼不能替代上述產品入口，也不能代替完整 `AC-27`。

<a id="媒体执行桥"></a>

## 媒體執行橋

控制側使用同一圖片／視頻隔離 Python 分別調用 `adapters/media/preflight.py` 和 `workers/media_worker.py`，兩者均接收 `--snapshot` 與 `--output-dir`。預檢不寫輸出目錄、不加載基座權重；它以固定官方文件卡、完整目錄清單、實際 CLIP 分詞和輸入圖片解碼為依據。已有 LoRA 的形狀用 meta 設備建立的標準 UNet 檢查，不佔用 GPU。`media_recipe_digest` 綁定實際配置、輸入清單、執行器源碼和依賴環境，獨立於文本的分詞配方字段。

| 操作 | 當前開放參數 | 輸入 |
| --- | --- | --- |
| 圖片生成 | `engine=diffusers`、`device_id=apple-gpu`、512×512、20 步、CFG 7.5、顯式 32-bit 非負 seed | `input.prompt` 與可選 `negative_prompt`；可選已綁定完整清單的圖片 LoRA |
| 圖片 LoRA 訓練 | 同設備、512×512、12 步、rank/alpha 4、學習率 1e-4 | `dataset_root_path` 的完整清單，`dataset_path` 必須指向其中 `dataset.json`；1—8 張有 caption/來源/SHA 的 RGB 原圖 |
| 圖片生成短視頻 | 同設備、1024×576、25 步、14 幀、7 FPS | `input.material_id` 與頂層 `input_image_path`、完整 PNG 清單及摘要；當前 SVD 不接收文字控制 |

所有模型、輸入圖片、訓練目錄和可選適配器都必須綁定完整清單。目錄額外文件、符號鏈接、未知參數、未驗證組合、輸出與輸入重疊或覆蓋舊輸出均拒絕。圖片可用乾淨導入目錄 `.artifacts/m4-media/image-model-runtime`，其完整清單見旁邊 `image-model-runtime-import.json`；數據示例為 `.artifacts/m4-media/image-dataset-runtime`，保持原先已說明的合成數據質量邊界。

真實模型 CLI 與橋留在同一執行進程組。橋只把 CLI 已寫出的訓練 step 轉為進度事件；生成階段沒有偽造百分比。完成後復核輸入與執行配方，寫 `effective-config.json`、`output-manifest.json` 和實際源碼快照，向控制服務發送有 SHA256 的完成清單。主產物位於 `result/image.png`、`result/video.mp4` 或 `result/pytorch_lora_weights.safetensors`。當前媒體橋不支持訓練暫停或檢查點恢復。

`tests/media/run_real_bridge.py` 的本次代表性執行見 `.artifacts/m4-media/bridge-acceptance-v2/acceptance.json`：真實圖片生成、12 步訓練、新 LoRA 獨立生成通過；視頻完成真實第 1/25 步後取消，返回 130、沒有完成事件、進程組已退出。此取消用例只證明停止邊界，不計作成功視頻或成功 UI 工作流。
