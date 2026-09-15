<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-10-remote-nvidia-evidence.md) · [繁體中文](../../../zh-TW/docs/implementation/2026-09-10-remote-nvidia-evidence.md) · [English](2026-09-10-remote-nvidia-evidence.md)
<!-- translation-navigation:end -->

<a id="独立执行目标与-nvidia-文本组合实现和验证记录"></a>

# Independent Execution Targets and NVIDIA Text Combination: Implementation and Verification Record

Ver2.0 integrated execution targets, project default locations, per-task selection, upload-scope confirmation, original-ID event synchronization, cancellation, and collection-only recovery into the control service. HTTPS was first packaged with Ver2.1（004）; Ver2.1（005）subsequently passed complete-package, bundled-CA, and native unknown-CA rejection acceptance. This page retains evidence from those phases. The current signed candidate has been updated to Ver2.2（010）, but its remote native reverification is incomplete and it has not been publicly released. See [010 execution progress](2026-09-12-ver2-2-010-progress.md) for the latest status. File transfer uses independent processes, persistent SQLite, and real files; the text executor includes fixed NVIDIA inference and SFT + LoRA implementations.

The current machine is an Apple Silicon Mac. The public NVIDIA entry explicitly refuses to run, with no CPU or Apple fallback. Cross-host network access, NVIDIA hardware inference/training, and quality admission of that adapter remain unaccepted. Successful loopback transfer cannot replace these three items.

<a id="用户操作与边界"></a>

## User Operations and Boundaries

1. Register the execution service’s fixed address and identity in “Devices and Environment,” then check the connection. The Ver2.1（005）phase implemented `https://主机:端口` while retaining literal `http://127.0.0.1:端口` loopback mode. HTTPS must pass certificate-chain, hostname, and validity checks using the runtime’s public CA bundle. Connections use no proxy, follow no redirects, and do not downgrade to HTTP. The old-package acceptance above does not replace actual cross-host verification for 010.
2. The native App stores credentials in the system keychain; the control service holds plaintext only for the current session. The database stores only random references, not plaintext credentials. Locked or missing credentials require reconnection, and backup restoration clears credential references. The development webpage supports only in-memory session credentials.
3. Each project can save a default execution target, affecting only subsequently created text drafts. A task’s execution location is a one-off override and does not change existing drafts or other projects. Media tasks continue using existing fixed combinations.
4. “Transfer Verification” uploads only imported data or materials. It first displays the target, filenames, byte counts, and digests for every file, then requires the user to explicitly start. It does not load a model.
5. Text-task preflight freezes target version, model/data manifests, code identity, and tokenization-recipe identity. If NVIDIA is not ready, no remote run is created and no model uploaded. Even when execution is possible, upload scope is shown first and the user must explicitly start.
6. Disconnection or certificate-verification failure does not mean stopped. Cancellation intent and the complete cancel command are persisted first, then continue to the original ID while submission is being sent or after connection recovery. Pending-confirmation state remains until the original process group is confirmed exited. Collection recovery reads only the original sealed manifest and creates no new computation; the original collection-failure record is retained.

Upload chunks are 1 MiB. A single model file is limited to 2 GiB, total inputs to 4 GiB, and file count to 16; transfer verification additionally limits each file to 64 MiB. The service separately reserves space for uploaded files, execution-input copies, and artifacts. Uploads check cancellation and host exit at each hashing/transfer chunk.

<a id="固定-nvidia-组合"></a>

## Fixed NVIDIA Combination

| Item | Current implementation |
| --- | --- |
| Device | Linux, CUDA 12.8, `cuda:0`, BF16 support, at least 8 GiB VRAM; released after a real small-matrix probe |
| Model | Original `Qwen/Qwen2.5-0.5B-Instruct` weights, complete-manifest digest `a9b08fa2b761cbfc7335b28c6b0997b6e7713893aaca4b215625ffc99a1d36b3` |
| Dependencies | PyTorch 2.10.0, Transformers 4.57.6, PEFT 0.18.1, Accelerate 1.12.0, Safetensors 0.7.0, NumPy 2.4.2 |
| Generation | BF16 base, token-by-token generation, fixed seed; greedy/temperature/top-p, stop sequences, streaming toggle, and bounded context; at most 512 output tokens |
| Training | SFT + LoRA, q/v projections in the specified final layers, loss only on assistant content and end markers, BF16 base with FP32 LoRA; no truncation of supervised samples or embedding training |
| Training artifacts | Original PEFT format, MLX LoRA from explicit transposition, and conversion-provenance report; always experimental artifacts |
| Not yet opened | QLoRA, CPT, remote checkpoint/pause/resume, remote adapter inference, unknown models, or arbitrary commands |

The PyTorch CUDA 12.8 installation combination comes from the [official previous-versions installation page](https://pytorch.org/get-started/previous-versions/). Model and LoRA parameters follow the fixed-version [Transformers Qwen2 implementation](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/qwen2/modeling_qwen2.py) and [PEFT LoRA configuration](https://github.com/huggingface/peft/blob/v0.18.1/src/peft/tuners/lora/config.py). These are fixed versions, not a claim that they are the latest.

Actual tokenization and supervised-sample checking occur after input upload and before model allocation. Preflight explicitly describes this boundary with `tokenization_check=on_executor_before_model_allocation`; it must not be described as remote sample computation already completed.

<a id="完成接收与恢复"></a>

## Completion Acceptance and Recovery

- Worker stdout is bounded NDJSON events, while library logs go to separate stderr. The execution service confirms terminal state only after verifying child identity and exit of the entire process group.
- The completion gate checks engine, device, precision, all effective parameters, fixed model, source, and exact tokenization recipe item by item. Generation requires 5 fixed files and training 9; missing body content or metrics alone cannot succeed.
- After retrieving files, recheck `effective-config.json` against the completion object, environment/computation device, LoRA conversion provenance, and weight digests. Complete filenames do not establish trustworthy report contents.
- Local collection uses independent byte copies and exclusive publication after per-file validation. Hard links must not violate the single-link constraint of the remote-retrieval directory, so collection can still resume from the original manifest after temporary local-registration failure.
- Source identity is fixed at module load. An old process cannot report a new digest after on-disk source changes; restart the execution service before checking again.
- If cancellation was requested but original computation finished first, record that fact rather than fabricating “cancellation took effect.” Display cancellation complete only when the original execution returns cancelled and process-group exit is confirmed.

<a id="当前证据"></a>

## Current Evidence

Evidence is retained in the workspace, and failing reproductions are not deleted. Release records separately associate final complete-package and UI acceptance.

The Ver2.0 control-service, execution-protocol, and NVIDIA-contract suites totaled **667 passing tests**, followed by **1 additional passing test** for 101-entry cross-target history pagination. Independent review’s completion-acceptance contract had **15 passes**. Two independently reproduced cancellation/collection failures were fixed and passed reverification. NVIDIA CPU components v3 and public CUDA rejection v2 both have source digest `a88a481daa39fe196586ca9a93307dd277d81e89df9dfea73398a5784feeb5f7`.

The HTTPS candidate’s combined backend regression had **168 passes**, and the final targeted TLS/control-chain reverification had **73 passes**; the two runs are counted separately. Actual coverage includes certificate rejection, certificate replacement while running, chunked resumption, original-ID cancellation, restart, and collection from the original manifest. Services exited normally 10 times, with 0 force-kills. See [HTTPS backend readback](../../../../.artifacts/https-implementation-ver2-next-v1/backend-readback.json). These new tests use only local loopback TLS and CPU-contract fixtures, with 0 model generations, training runs, or external-host connections.

| Evidence | What it proves |
| --- | --- |
| `.artifacts/control/remote-integrated-final.xml`, `remote-target-pagination.xml` | Final complete regression of 667 tests and 1 new pagination test |
| `.artifacts/control/remote-product-all.xml` | Product API focused checks for target/credential permissions, default location, real NVIDIA probe blocking, and upload/cancellation/disconnection/collection recovery |
| `.artifacts/control/remote-export-regression.xml` | Export tasks without drafts still return a business rejection; model, adapter, work, and report export regressions |
| `.artifacts/control/remote-review-fixes.xml` | Completion-contract negative cases and verification of independently reproduced cancellation/collection-recovery fixes |
| `.artifacts/desktop/remote-product-review/` | Independent reproductions: collection after registration failure and cancellation during submission; original failure logs and post-fix reverification |
| `.artifacts/nvidia-completion-independent-v1/` | Positive/negative completion-acceptance contract cases; explicitly no model or GPU execution |
| `.artifacts/nvidia-text/cpu-components-v2/report.json`, `cpu-components-v3/report.json` | CPU component verification using real original 0.5B weights; not NVIDIA acceptance |
| `.artifacts/nvidia-text/public-cuda-rejection*.json` | Public entry actually rejects local execution, creates no output, and uses no CPU fallback |
| `.artifacts/nvidia-text/runtime-freeze.txt` | Complete dependencies of the local isolated component-test environment, whose Python is 3.14.6 |

The CPU component test actually generated “Completed,” ran two LoRA steps, and checked parameter changes, unchanged sampled embeddings, elementwise PEFT→MLX matrix transposition, and numerical equivalence. It proves only that these computational components and file conversions executed on CPU. It does not prove CUDA memory behavior, BF16 performance on hardware, independent Apple loading, or quality improvement.

<a id="执行服务准备示例"></a>

## Execution-Service Preparation Example

The following installation/startup instructions describe the candidate version, not an existing deployment on a NVIDIA host. The control package requires Python 3.13 or later. Use an independent directory and virtual environment; the main App working library must not be used as the execution-service directory.

```sh
python3.13 -m venv .venv-nvidia
.venv-nvidia/bin/python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
.venv-nvidia/bin/python -m pip install -r adapters/nvidia_text/requirements.txt
.venv-nvidia/bin/python -m pip install -e services/control
.venv-nvidia/bin/python workers/nvidia_worker.py --mode probe
```

The launcher requires a pre-generated independent credential file with permissions `0600` and 32—512 visible ASCII characters, and does not print credentials. The service handshake returns port, executor identity, PID, connection method, and verification scope. Register the corresponding address, executor ID, and credential in the App.

HTTPS mode requires explicit `--https`, `--bind`, `--cert-file`, and `--key-file`. Replace the variables and paths below with prepared configuration. The bind value is the service machine’s local IP, and the host in the registered address must match the certificate. The private key must belong to the current user, have permissions `0600`, and use unencrypted PEM. The client’s bundled public CA package must be able to verify the certificate chain. There is currently no private-CA configuration entry.

```sh
.venv-nvidia/bin/python -m ailab_control.remote \
  --data-dir /新的独立HTTPS执行目录 \
  --token-file /明确授权的私有凭据文件 \
  --https --bind "$AILAB_EXECUTOR_BIND_IP" --port "$AILAB_EXECUTOR_PORT" \
  --cert-file /已准备好的完整证书链.pem \
  --key-file /权限为0600的服务私钥.pem
```

An execution directory is fixed to one connection method. An existing loopback directory cannot be converted directly to HTTPS; use a new independent directory with its new executor identity. The original loopback startup method remains available:

```sh
.venv-nvidia/bin/python -m ailab_control.remote \
  --data-dir /明确独立的执行目录 \
  --token-file /明确授权的私有凭据文件 \
  --port 0 \
  --loopback-contract-only
```

Local TLS verification does not mean acceptance across a physical NVIDIA machine. NVIDIA hardware must still complete fixed-model inference, SFT, cancellation/disconnection/collection recovery, VRAM/process release, and quality comparisons under a plan frozen before training before the corresponding delivery status can advance. 005 natively passed registration and real unknown-CA rejection: the target showed a certificate error, the transfer entry was disabled, and the execution database received no files or tasks. The service exited normally, and temporary credentials were cleared. See [native target postcheck](../../../../.artifacts/native-https-rejection-ver2-005-v1/run-001/root-native-target-postcheck.json) and [this round’s native summary](../../../../.artifacts/integration-ver2-1-005-v1/native-acceptance/本轮原生验收.json).
