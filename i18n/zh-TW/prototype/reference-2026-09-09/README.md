<a id="最后确认的原型参考"></a>

# 最後確認的原型參考

原樣複製最終 Demo、建置素材和測試，原目錄保留。來源檔案身分見 [manifest.json](../../../../prototype/reference-2026-09-09/manifest.json)；真實應用位於 `apps/desktop`，此目錄不進入正式套件。此原型是模擬介面，不執行真實訓練或推論。

此原型含 6 項已知行為問題，另有 1 項配方追溯語義問題。檢查器的斷言用於重現這些問題，退出成功表示問題仍存在，不能計為修復通過。

<a id="从仓库根目录复跑"></a>

## 從儲存庫根目錄重跑

需要 Node.js 和 Python 3，以下步驟只使用其標準函式庫。先核對清單中的位元組數和摘要，再複製到獨立暫存目錄執行；檢查器會在那裡寫出報告，固定副本保持不變。任一步失敗時停止並保留輸出，不繼續將後續結果判為通過。

```sh
node --version
python3 --version
ailab_replay_dir="$(mktemp -d "${TMPDIR:-/tmp}/ailab-reference.XXXXXX")"
python3 - "$ailab_replay_dir" <<'PYTHON'
from pathlib import Path
import hashlib, json, shutil, sys
source = Path("prototype/reference-2026-09-09")
target = Path(sys.argv[1])
manifest = json.loads((source / "manifest.json").read_text())
for item in manifest["files"]:
    data = (source / item["path"]).read_bytes()
    assert len(data) == item["bytes"], item["path"]
    assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
    shutil.copy2(source / item["path"], target / item["path"])
print("Verified files:", len(manifest["files"]))
print("Replay directory:", target)
PYTHON
node "$ailab_replay_dir/test-ailab-unified.cjs"
node "$ailab_replay_dir/test-ailab-runtime.cjs"
node "$ailab_replay_dir/audit-prototype-counterexamples.cjs"
```

本次以 Node.js `v24.14.0` 實際執行：13 個清單檔案身分一致，代表性檢查輸出 42 組通過，執行設定檢查輸出 17 組通過。檢查器輸出 `A-01` 至 `A-07`，報告儲存在暫存目錄的 `audit-prototype-counterexamples.json`；這是歷史原型的已知問題證據，不是正式 App 測試結果。

<a id="界面与结论边界"></a>

## 介面與結論邊界

固定介面檔案是 [ailab-unified.html](../../../../prototype/reference-2026-09-09/ailab-unified.html)，須由驗收者在瀏覽器中實際開啟並核對工作台、類別切換與執行設定。上述腳本使用狀態函式及最小 DOM 替身，不檢查真實版面、鍵盤焦點、播放或截圖。

本輪瀏覽器工具因本機檔案 URL 政策拒絕開啟，未完成可視介面複驗；沒有改用其他入口繞過限制。新成員仍需獨立依說明執行並記錄版本、結果和困難，才能補充 AC-23 的新成員證據；開發者重跑不代替該項或 AC-25 的真實使用者驗收。

建置會重寫 HTML；如需執行 `build-ailab-unified.py`，僅在上述暫存副本中執行，保留原始摘要與報告。人工修訂與原生成配方分離等產品規則以 [文件首頁](../../docs/README.md) 所列規範為準。
