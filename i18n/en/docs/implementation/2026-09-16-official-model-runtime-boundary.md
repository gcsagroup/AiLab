<a id="官方模型准备入口的运行边界说明"></a>

# Runtime boundary notice for official model preparation

This change fixes the missing runtime-permission notice in official model preparation and the omission of the same fields from registered models. Source checks and related tests passed. The fixed company-signed App remains 035, has not been rebuilt, and does not contain this change. Full M2, native acceptance, and release status are not advanced. [Earlier manual import boundary](2026-09-16-model-import-trust-boundary.md)

<a id="行为与兼容边界"></a>

## Behavior and compatibility boundaries

The official catalog adds a generic `execution_boundary`, retaining the download-format meaning of `loader=safetensors`. New model registration persists the same fields from the actual `model_manifest` report after file verification; a catalog declaration is not treated as proof of verification or execution. Existing models and historical idempotency receipts are neither backfilled nor migrated. [Design review](../../../../.artifacts/official-model-boundary-next-v1/design-review.md)

The shared `ModelExecutionNotice` reuses manual import's seven-field recognition and explanation: fixed loaders, no custom code, and a separate same-user process rather than an OS sandbox. Offline loader options do not block network access, and a credential environment allowlist does not prohibit reading credential files. Missing or unknown fields on the official page display an uncertainty notice, without adding gates for download, stop, resume, registration, or handing a model to a trial draft. Manual import retains its original confirmation gate; creating a trial draft does not automatically run it. [Independent review](../../../../.artifacts/official-model-boundary-next-v1/independent-review.md)

<a id="验证与限制"></a>

## Validation and limits

The backend first failed 2 targeted negative cases, then passed 67 related tests after the fix, retaining 2 existing dependency warnings. The frontend first failed 4 new negative cases, then passed 27 related tests after the fix; type checking passed. Backend control APIs use in-process TestClient requests, while the download fixture uses real loopback HTTP and temporary files/databases. No model execution or original-library SQL occurred. [Backend receipt](../../../../.artifacts/official-model-boundary-next-v1/backend/result.json), [Frontend regression](../../../../.artifacts/official-model-boundary-next-v1/frontend/green.log)

Component browser acceptance passed at 1280×720. Actual production components with in-memory API responses showed the known notice without writes; explicit start produced only 1 download-creation request, displaying 1024/1024 and the registration button. Unknown fields showed an uncertainty notice while stop and resume remained usable. Scrolling the long dialog exposed an enabled registration button. No real control service, model, or SQL was connected; this is not actual official downloading or native App acceptance. [Browser receipt](../../../../.artifacts/official-model-boundary-next-v1/browser-001/result.json)

Two fixture issues remain recorded: duplicate React in the initial temporary Vite configuration caused a hook error and blank page; correcting acceptance configuration passed without changing product dependencies. An earlier completed record showed 256/1024; after correction to 1024/1024, the known-notice and start paths were rechecked. The console retains the initial 4 errors/warnings, with none added after correction. Mobile viewports were not tested.
