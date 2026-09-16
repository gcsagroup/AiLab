<a id="模型导入信任与权限说明源码验证"></a>

# Model Import Trust and Permission Explanations: Source Validation

This change displays loading trust categories and actual permission boundaries during model import checks, addressing the missing explanation in the UI despite existing API loading policies. The fixed company-signed App remains Ver2.4（034） and does not contain these changes. No 035 build has occurred; native acceptance from the same source remains pending. M2, full AC, and release status do not advance.

<a id="加载与权限边界"></a>

## Loading and Permission Boundaries

Text models use the fixed local MLX loader; media models use fixed safetensors or restricted official Kokoro weight loaders. Only known trust-category and loader combinations are accepted, with no support for model custom code. Existing dangerous-format rejection rules remain. The separate worker process retains the current user’s file permissions and is not an operating-system sandbox.

Local files and offline loading options do not establish operating-system network blocking. The worker environment allowlist excludes application credentials but does not prevent reading credential files. The new `execution_boundary` states these limits explicitly. The existing three `execution_scope` booleans remain compatible and describe loading policy, not operating-system permissions.

The backend rechecks source files at import and writes boundary information from the actual check, supporting old plans without the new field. The frontend permits model import confirmation only when known, complete boundary information is present. Missing, unknown, or inconsistent information displays an error and disables confirmation until the application is updated and the model rechecked. Dataset and image-material imports do not use the model explanation.

<a id="验证与限制"></a>

## Validation and Limits

The backend passed 40 tests: 8 new cases and 32 related regressions covering text/fixed media, old plans, dangerous-format rejection, and the credential environment allowlist. The initial 3 failures/4 passes and the first fixed run’s 39 passes/1 old-plan fixture error are retained. That fixture was corrected to read the internal original plan and remove only the new field. All databases were temporary, with no model or App execution. [Backend implementation and test receipt](../../../../.artifacts/m2-gap-audit-ver2-4-034-v1/model-boundary-implementation.md)

The frontend passed 46 related tests across 4 files, and TypeScript checking passed. These source and component tests do not establish operating-system isolation or replace real model import, execution, or native acceptance in the fixed App. Frozen design requirements and historical acceptance conclusions remain unchanged. [Frontend test log](../../../../.artifacts/m2-gap-audit-ver2-4-034-v1/model-boundary-frontend.log)

Actual browser checks used the current import component with synthetic responses, without connecting to the control service or a model. Known explanations were visible and scrollable to the confirmation button, producing a confirmation count of 1. Missing/unknown explanations disabled confirmation; closing the unknown case left the count at 0. The record retains 4 screenshots and interface text, with no console errors or warnings. This is component visual validation only. [UI receipt](../../../../.artifacts/model-import-boundary-ui-v1/ui-review.json), [Source and validation summary](../../../../.artifacts/m2-gap-audit-ver2-4-034-v1/model-boundary-root-validation.json)
