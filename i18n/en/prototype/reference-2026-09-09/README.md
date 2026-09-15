<!-- translation-navigation:start -->
[简体中文](../../../../prototype/reference-2026-09-09/README.md) · [繁體中文](../../../zh-TW/prototype/reference-2026-09-09/README.md) · [English](README.md)
<!-- translation-navigation:end -->

<a id="最后确认的原型参考"></a>

# Final confirmed prototype reference

The final Demo, build assets, and tests are copied unchanged; the original directory is retained. See manifest.json for source-file identities. The real application is in apps/desktop; this directory is not included in the production package.

This prototype has 6 known behavioral issues. Assertions in audit-prototype-counterexamples.cjs reproduce their presence and must not be counted as successful fixes.

Rerun:

```sh
node prototype/reference-2026-09-09/test-ailab-unified.cjs
node prototype/reference-2026-09-09/test-ailab-runtime.cjs
```

Building rewrites this copy's HTML, so copy it to a temporary directory before executing build-ailab-unified.py. Product rules such as keeping manual revisions separate from the original generation recipe follow the 1.1 specifications in docs.
