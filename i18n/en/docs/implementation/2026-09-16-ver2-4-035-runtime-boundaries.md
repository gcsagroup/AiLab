<a id="ver24035运行边界验收e146"></a>

# Ver2.4 (035) runtime boundary acceptance (E146)

One generation with process network denial using the fixed 035 packaged worker has received limited acceptance; rejection tests for unsupported media and cache requests were published in `b96514c`. This round does not rebuild the App or advance M2, full AC, or release status. Native interaction and reopen evidence remains in [E145](2026-09-16-ver2-4-035-native-inference.md). Real cancellation and recovery through the packaged control service also passed the limited subset below.

<a id="进程网络拒绝下的真实生成"></a>

## Real generation with process network denial

Unsandboxed probe PID 36199 connected successfully to newly created IPv4/IPv6 loopback endpoints. PID 36200 received `EPERM` during connect to the same endpoints, then executed the fixed packaged worker under the same PID. One real generation exited normally with text `7`, 6 artifacts, and 0 incremental token events; all 24 KV layers began empty with no cross-request reuse. Configuration retained 50 prompt tokens / 78 reserved output tokens / 128 context, auto KV, prefill 512, stop sequence `39`, and `stream=false`. [Execution receipt](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/result.json), [Raw output](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/worker.stdout.jsonl)

All 47 original protection records, 12 model source files, 31 native files, and the native database digest remained unchanged. The worker and probe process exited, and listeners closed. No App UI was started, SQL connected, or system network settings changed. [Root acceptance](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-run-001/root-acceptance.json), [Independent readback](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-independent-result.md)

Preparation added cleanup of owned processes and handling of natural-exit races, and tightened exact artifact, configuration, and cache checks. Earlier probes added operation fields to distinguish socket creation from connect rejection; original records remain. The 8 execution-preparation synthetic tests and their independent rerun are not added together. The earlier 8 zero-model probe tests belong to another layer and do not represent real fault injection. [Preparation review](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-execution-preparation-001/independent-review.md), [Earlier probe record](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/offline-preparation-001/REVIEW.md)

This uses a process network-denial policy solely for acceptance. Direct probes cover IPv4/IPv6 loopback TCP connect; DNS, UDP, and external endpoints were not individually probed. It is neither a physical network disconnection nor a default product OS sandbox. Same-user file-reading permissions remain; one short input does not cover the entire offline workflow.

<a id="未开放媒体与缓存请求"></a>

## Unsupported media and cache requests

With unchanged text, tests replace media identity, swap media order, change processor revision or preprocessing size, and request prefix/media cache reuse. Production MLX validation, preflight, and execution entry points reject before loading or computation. Control-service draft updates return 422; submission after a legacy draft fails preflight returns 409, without new runs or artifacts. No silent ignoring was found in these input positions, and no production code or cache reuse implementation was added. [Entry contracts and tests](../../../../.artifacts/m2-cache-contract-ver2-4-035-v1/review.md), [Independent review](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cache-contract-independent-review.md)

The control tests use in-process TestClient requests. Legacy-draft cases substitute the production preflight function for subprocess dispatch; they are not actual network or native UI acceptance.

The new rejection matrix passed 50 tests; related MLX regression passed 139 and control regression passed 50, with overlap that must not be summed. New negative cases use temporary files/databases and counted refusal stubs, with zero model loading, computation, or cache creation. Existing positive cases using CPU cache arrays and fixture generators are not language-model execution. These results do not establish media cache hits, invalidation, or performance. [Test summary](../../../../.artifacts/m2-cache-contract-ver2-4-035-v1/result.json)

<a id="真实取消与恢复"></a>

## Real cancellation and recovery

After the sequence 8 phase message `提示词已处理，正在生成`, one normal cancellation was submitted to the fixed packaged control service, PID 37558, over production loopback HTTP. Worker PID 37568 exited with 130 and emitted a `CANCELLED` warning. State, compute outcome, and collection state were all `cancelled`, stop was confirmed, and the reason was `USER_CANCELLED`, without successful artifacts or work. After its process group disappeared, recovery worker PID 37583 exited normally, producing text `7`, 24 fresh empty KV layers, and 6 artifacts. [Actual run](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-run-001/result.json)

This round had 2 attempts, 1 cancellation, 0 training, and 0 automatic retries. Read-only checks of the new database after shutdown confirmed 4 commands, 25 events, 6 registered artifacts, and 0 works; persistence matched the API, and readback did not change database bytes. The control service exited normally without forced cleanup signals. Relevant processes and groups were absent, and original protections remained unchanged. This demonstrates that a new process can allocate and generate after stopping; it does not establish byte-for-byte zeroing of old GPU memory or constitute App UI acceptance in this round. [Root acceptance](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-run-001/root-cancel-acceptance.json), [Independent readback](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-independent-result.md)

Preparation history remains: after a SyntaxError in the earlier script was corrected, 44 tests passed. The first root preflight misidentified the existing idle remote-protocol service, PID 30114, as a local control service and rejected before starting any new service or model. Exact module matching corrected this; 50 pure tests and preflight checks of 175 sources, 47 protection records, and 12 model sources passed. The old service was not stopped. Stage test counts are not added together, and preparation failures are not product cancellation failures. [Preparation record](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-execution-preparation-001/test-summary.json), [Preflight failure](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-preflight-failure-001.json), [Corrected preflight](../../../../.artifacts/m2-runtime-gaps-ver2-4-035-v1/cancel-execution-preparation-002/root-preflight.json)
