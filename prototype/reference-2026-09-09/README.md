# 最后确认的原型参考

原样复制最终 Demo、构建素材和测试，原目录保留。源文件身份见 manifest.json；真实应用位于 apps/desktop，此目录不进入生产包。

此原型含6项已知行为问题，audit-prototype-counterexamples.cjs 的断言复现问题存在，不能计为修复通过。

复跑：

```sh
node prototype/reference-2026-09-09/test-ailab-unified.cjs
node prototype/reference-2026-09-09/test-ailab-runtime.cjs
```

构建会重写本副本 HTML，应先复制到临时目录再执行 build-ailab-unified.py。人工修订与原生成配方分离等产品规则以 docs 的1.1规范为准。
