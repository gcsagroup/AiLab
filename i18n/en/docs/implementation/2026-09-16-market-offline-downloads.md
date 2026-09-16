<a id="市场不可用时使用已下载数据"></a>

# Using downloaded data when the market is unavailable

Completed downloads no longer lose their registration entry when the provider catalog is unavailable. Source checks, host routing, and the real HTTP browser flow passed. The fixed company-signed App remains 036 and does not yet contain this fix; native acceptance of the next candidate remains pending. Full M4 and release status are not advanced. [Source receipt](../../../../.artifacts/market-offline-next-v1/source-acceptance.json)

<a id="行为与边界"></a>

## Behavior and boundaries

The data market now offers a view of downloaded data. When the online catalog fails or is still pending, users can switch to completed local downloads for the current project and configured source. Late online responses cannot replace the local list. Switching does not actively cancel an already sent online request. Local mode hides access applications, new downloads, and resume actions; users must explicitly return to the online catalog for those entries. Registration and use in the current task remain separate confirmation actions.

`GET /market/local-versions` reads saved completed-download versions without contacting the provider or writing to the database; it does not claim to recheck every byte. Existing rules still verify the source origin and version digest. Browsed-only versions, incomplete downloads, and records from other projects or sources are excluded. Registration still checks actual files, format, and sample counts and remains idempotent. Applying data still checks the original draft revision, changes only the dataset, and invalidates prior checks. Unconfigured sources, changed origins, and damaged metadata remain rejected. [Backend report](../../../../.artifacts/market-offline-next-v1/backend/review.md)

<a id="测试与实际界面验证"></a>

## Tests and actual UI validation

The frontend first failed 3 new cases confirming the gap. After the fix and added coverage for late responses, project changes, and uncertain registration responses, 31 related tests and type checking passed. The backend passed 15 new and 48 related tests, totaling 63, with 1 existing warning retained. The precise read-only host route changed from 1 failed test to 1 passed test; 68 filtered tests were not counted as passed. The initial system toolchain LLVM symbol error prevented test execution and is retained as an environment failure. The existing project toolchain was then used without changing system configuration. [Host receipt](../../../../.artifacts/market-offline-next-v1/host/result.json)

The actual production market component ran in a temporary page connected to a real control HTTP service with an independent temporary library. After downloading 292 bytes containing 2 rows, the loopback provider was stopped. Closing and reopening the market produced an online catalog failure, while the local entry allowed registration and explicit application to the original draft. The draft revision changed from 2→3, with only the dataset field changed and the original input and configuration preserved. Reopening retained registration; repeated registration returned the same dataset, with no new model or attempt. The 1280×720 view, scrolling interaction, and console checks passed, with 0 console errors/warnings. The 2 optional dependency-resolution warnings at Vite startup are retained. The page, control service, and development server for this run were stopped. [Browser and HTTP evidence](../../../../.artifacts/market-offline-next-v1/browser-http-001/result.json)

This is limited integration acceptance of a production component and real service. It does not cover the complete workbench, mobile viewports, the signed App's native entry, or full M4. A subagent independently reviewed the frontend. The root agent checked the backend and execution evidence; an additional browser review did not finish because the subagent reached its usage limit and is not counted as passed. No original-library SQL, model execution, or training occurred. Prototypes and historical failures remain preserved.
