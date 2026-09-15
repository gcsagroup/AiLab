<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-10-wp08-wp10-minimum-plan.md) · [繁體中文](../../../zh-TW/docs/implementation/2026-09-10-wp08-wp10-minimum-plan.md) · [English](2026-09-10-wp08-wp10-minimum-plan.md)
<!-- translation-navigation:end -->

<a id="wp-08wp-10-首期远程执行软件拆分"></a>

# WP-08/WP-10 First-Phase Remote Execution Software Breakdown

Date: 2026-09-10. Status: initial contract review and implementation breakdown. Subsequent software and loopback acceptance progress is in the [current delivery matrix](2026-09-10-current-delivery-matrix.md); NVIDIA hardware has still not passed.

The recommendation is to connect one independent persistent execution service first, then one NVIDIA text-inference adapter. Controlled local processes and loopback HTTP can verify the remote protocol, uploads, disconnection, cancellation, and collection-only recovery. Evidence for GPU loading, VRAM release, and returning the same LoRA to Apple must come from the designated NVIDIA machine. These two layers use the same protocol but record acceptance separately.

<a id="1-已冻结的合同与当前缺口"></a>

## 1. Frozen Contracts and Current Gaps

This work follows [06 Executor Contracts and Remote Execution](../06-architecture-and-adapters.md), [07 State, Idempotency, and Collection](../07-api-and-task-lifecycle.md), [04 Execution Location and Parameters](../04-runtime-and-hardware.md), [11 AC-18/AC-21/GATE-M2](../11-testing-and-acceptance.md), and [10 WP-08/WP-10](../10-work-breakdown.md). Original-file SHAs are fixed in `.artifacts/desktop/wp08-wp10-contract-snapshot.json`; original contracts are not changed in this round.

The existing control layer accepts only the MLX/local Apple GPU text combination, and media executors are also local processes. Existing Settings has no remote targets or credential references. No execution-service registration, input upload, remote state/log catch-up, or formal NVIDIA run entry was found. Existing local state versions, idempotency, pre-start authorization, ownership verification, collection-only recovery, and restricted file checking can be reused. A local pass does not cover remote-disconnection semantics.

The first phase uses an already configured server or instance. The specific remote host, identity fingerprint, credential, NVIDIA model/driver are not yet locked. They must not be searched for autonomously in existing business servers or environment variables. The execution service uses an independent data root and fixed argument arrays to launch children. Local protocol tests can use processes directly, without introducing Docker, clusters, cloud-instance purchases, or deployment platforms.

<a id="2-最小实现与验收顺序"></a>

## 2. Minimal Implementation and Acceptance Order

| Subitem | Minimum deliverable | Step → verification | What can be completed locally |
| --- | --- | --- | --- |
| 08-A Target identity and send plan | Registered execution target, protocol version, fixed identity, credential reference in system secure storage; per-target input manifest and byte count | Register target → reject identity mismatch, invalid credentials, and address/fingerprint changes. Preflight and submission bind the same target, input digest, and draft revision. | Independent loopback service verifies identity and short-lived test credentials; the secure-storage connection is separately verified through the native host. |
| 08-B Independent persistent execution service | Independent database and stable instance identity per service; each attempt stores snapshot digest, command idempotency, state version, event cursor, and startup receipt | Authorize startup after persistent registration → concurrent duplicate submissions, lost responses, and service restarts retain the same attempt. Changed request digests conflict; query unknown state first. | Real child processes, real SQLite, and forced interruptions at startup/completion demonstrate no increase in execution count. |
| 08-C Digest-based input transfer | Only planned files, restricted read authorization, digest and length; temporary files, resume offsets, atomic publication after complete validation | Interrupted upload → reconnect and resume; deduplicate identical files; reject digest/length mismatch, symlinks, or path traversal; do not start without complete inputs. | Real local files, disconnections, disk errors, and interleaved uploads; sent content matches the frozen manifest item by item. |
| 08-D Reconnection, cancellation, and collection-only recovery | Catch up state/events from a persistent cursor; idempotent cancellation; sealed manifest; transfer, verify, and register against the original manifest | Reopen after control-client exit → query only the original attempt. Disconnected cancellation retains unknown stop status. Computation finished but local collection failed → collect only, without increasing run/resume counts. | Real independent service continues execution through disconnection/restart; interrupted/corrupt collection and duplicate registration; unrelated processes remain unharmed. |
| 10-A NVIDIA text adapter | describe/probe/validate/load/run/cancel/unload; fixed engine, model, and tokenizer identities; actual parameter/resource evidence | Load fixed model → persist streaming/nonstreaming results; reject limits exceeded; verify actual resources after cancellation, errors, and unloading. Reuse the same model; queue or reload different loading configurations. | Protocol and process lifecycle can use an explicitly labeled CPU fixture; CUDA capability, quality, performance, and VRAM release still require hardware. |
| 08-E/10-B Product integration and combination acceptance | Device selection, location/send-scope summary, preparation/connection state, reconnect entry; snapshots and recipes save target identity, not secrets | Default local/one-off remote, default remote/one-off local, recipe reload → summary, button, snapshot, and actual destination match; recheck after changing target. | Loopback service completes the real UI/protocol workflow; rerun the full sequence on the designated NVIDIA machine. |

08-A and 08-B can run in parallel. After integration with 08-B, 08-C and 08-D can proceed in parallel. 10-A can independently implement field mapping but may start only under an attempt registered by 08-B. Integrate product entries last to avoid displaying a “Remote Ready” state that cannot be fulfilled.

<a id="3-必须保留的协议语义"></a>

## 3. Protocol Semantics That Must Be Preserved

The control client assigns stable `attempt_id` and idempotency keys. The remote side identifies the same computation by `attempt_id + snapshot_sha256` and exposes complete startup authorization only after persistent recording. Query the attempt first after a lost response; a network retry with the same ID must not invoke the executor again. Remote process startup, control-client connection, and task-execution identity are recorded separately; PID alone cannot prove ownership.

State, events, and artifacts are accessed through the registered target. The first phase may use an SSH tunnel carrying loopback HTTP: the host verifies a fixed host fingerprint, secure storage supplies credentials, and commands execute as argument arrays. Skipping host-identity checking is forbidden. Loopback-only tests use independent temporary credentials and test directories; this does not replace formal SSH/native credential paths. Keys must not appear in errors, recipes, logs, diagnostics, or exports.

`connection_state` is separate from `state`; disconnection means only that the last state awaits confirmation. If a cancellation request lacks stop evidence, preserve `stop_status=unknown`. Do not display resources as released or resubmit computation. Remote event sequence numbers increase monotonically. Local deduplication uses remote instance, attempt, and sequence number; completion/cancellation races are adjudicated only once.

After computation completes, seal a read-only manifest first. The remote side retains original files until local complete registration is confirmed or the user performs cleanup against an explicit manifest. Collection accepts only the original attempt, manifest digest, and an independent collection ID. It does not call run/resume, alter original digests, or rewrite the original terminal state. Missing or corrupt originals return a missing-file list; regeneration cannot be substituted to masquerade as successful collection recovery.

Input preparation and model loading continue restricted-format and trust checks. Unknown formats, custom repository code, and arbitrary deserialization do not enter the first-phase default path. Restricted-loading failure cannot trigger a retry with broader privileges. A virtual environment fixes dependencies only; it does not prove isolation of file, network, or credential permissions.

<a id="4-nvidia-的首个组合与完成边界"></a>

## 4. First NVIDIA Combination and Completion Boundary

The recommended first inference adapter uses a fixed PyTorch/Transformers CUDA combination and one explicit safetensors text model for loading, streaming generation, cancellation, and unloading. The rationale is to reuse restricted weight/tokenizer verification first, then bring the same process contract to CUDA. Exact versions, model revision, GPU, system, and driver must be frozen together once the real target is determined. This recommendation does not mean vLLM/SGLang has been selected and does not open unmapped KV, parallelism, or speculative parameters.

First-phase WP-10 completion requires real inference and service lifecycle for that fixed NVIDIA combination to pass the GATE-M2 subset. CPU-fixture success, loopback-service success, or successful CUDA probing cannot individually complete WP-10. TV-03 and AC-26 also require a LoRA actually trained on NVIDIA to be transferred/necessarily converted and independently loaded in the designated Apple engine. An existing Apple-trained artifact cannot replace this evidence.

Delivery must retain at least two reports: one for local protocol fault injection, native target selection, and real file transfer; another for the exact NVIDIA combination, fixed inputs, effective parameters, artifact SHA, cancellation/reconnection/resource release, and necessary LoRA return results. List every missing item separately as unverified rather than hiding it behind an overall “remote passed.”
