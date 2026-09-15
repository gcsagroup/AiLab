<!-- translation-navigation:start -->
[简体中文](../../../../prototype/reference-2026-09-09/README.md) · [繁體中文](README.md) · [English](../../../en/prototype/reference-2026-09-09/README.md)
<!-- translation-navigation:end -->

<a id="最后确认的原型参考"></a>

# 最後確認的原型參考

原樣複製最終 Demo、構建素材和測試，原目錄保留。源文件身份見 manifest.json；真實應用位於 apps/desktop，此目錄不進入生產包。

此原型含6項已知行為問題，audit-prototype-counterexamples.cjs 的斷言復現問題存在，不能計為修復通過。

復跑：

```sh
node prototype/reference-2026-09-09/test-ailab-unified.cjs
node prototype/reference-2026-09-09/test-ailab-runtime.cjs
```

構建會重寫本副本 HTML，應先複製到臨時目錄再執行 build-ailab-unified.py。人工修訂與原生成配方分離等產品規則以 docs 的1.1規範為準。
