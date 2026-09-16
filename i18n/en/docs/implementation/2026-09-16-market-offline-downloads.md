<a id="市场不可用时使用已下载数据"></a>

# Using downloaded data when the market is unavailable

The fixed company-signed 037 candidate passed native offline registration and application of downloaded data: a real 292-byte download containing 2 rows was registered and applied to the original task after the provider stopped and the market reopened. Draft revision changed from 2→3, only the dataset changed, and seed 817 was preserved. Normal exit, stopped-library readback, and original-data restoration passed; full M4, M0—M6, and release remain unpassed.

<a id="037-公司签名包与原生验收"></a>

## 037 company-signed package and native acceptance

The fixed-path App is now Ver2.4（037）, and all 7 targets signed by Global Cybersecurity Alliance Limited passed verification. The single build exited normally. The 672 tracked files, 163 production inputs, 213 frozen files, and 93 application inputs matched; actual packaged control modules and embedded frontend bytes were checked. [Package receipt](../../../../.artifacts/integration-ver2-4-037-v1/root-frozen-check.json)

All 47 preparation tests using temporary files passed, covering restoration of the original selector and source-settings objects, failed writes, rejection of unknown changes, occupied locks, launch constraints, and restore constraints. An independent library was created through a real HTTP empty-library backup and restore using the packaged service, with no SQL connection to original libraries. The native UI created a project and training draft and saved seed 817. It downloaded 292 bytes containing 2 synthetic SFT rows from a controlled loopback provider. After file completion, the market was closed, the provider stopped normally, and its port was confirmed to refuse connections.

Within the same App run, reopening the online catalog showed a provider failure. Switching to downloaded data allowed verification, registration, and explicit application to the original task. Reopening again retained the imported state without a duplicate-registration button. The stopped new library contains 1 project, 8 resources, 8 commands, and 0 events. Task revision changed from 2→3, and a complete draft comparison proves that only the dataset changed. Actual file sizes, hashes, source version, download record, and sample count match. Model runs and training runs are both 0. [Native stopped-library verification](../../../../.artifacts/market-offline-next-v1/native-run-001/root-readback.json)

The App exited normally with code 0, and both App and control service stopped. The original selector object and bytes were restored; temporary source settings were removed to restore their original absence. Of 47 original protection records, 44 remained strictly unchanged; the exceptions are selector ctime and two startup diagnostics. All 35 files in the independent 035 library, 4 files in the independent 036 library, and 12 source-model files remained unchanged. Prototypes, historical failures, and original data are retained.

Interaction negatives are retained: the paste tool timed out after text reached the form, which was checked before proceeding; a stale AX index was rejected before clicking, then fresh indexes were used; stopped-library verification refused its precondition while quit confirmation was pending, without opening SQL. A snapshot was taken only after confirmed normal exit. These are not counted as an uninterrupted first-pass success.

This is limited workflow acceptance of the company-signed native App with a synthetic loopback provider. It does not establish an external market, model quality, persistence across App restart, or full M4 acceptance; this run did not restart the App. NVIDIA, trusted cross-host operation, passing quality, first-time users, and formal release gates remain open.

<a id="构建前源码与浏览器记录"></a>

## Pre-build source and browser records

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
