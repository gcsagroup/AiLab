<!-- translation-navigation:start -->
[简体中文](../../../../adapters/mlx_text/PRESETS_ACCEPTANCE.md) · [繁體中文](../../../zh-TW/adapters/mlx_text/PRESETS_ACCEPTANCE.md) · [English](PRESETS_ACCEPTANCE.md)
<!-- translation-navigation:end -->

<a id="本机文本运行预设与-kv-缓存实算封存"></a>

# Sealed local text-execution preset and KV-cache results

Date: 2026-09-10. **The original q4/512 cache candidate is No-Go; the new auto/512 candidate passed fixed-question checks for no added regression, isolation, cancellation, and performance.** This document covers only the fixed local executor. Frontend application, submission, recipe reload, and the final relocated installation package have separate acceptance; complete M2 or cross-device acceptance cannot be claimed from this report.

<a id="组合与证据口径"></a>

## Combination and evidence definitions

Local Apple M5 Max with 128 GiB memory, macOS 26.6.2; Python 3.13.9, MLX 0.32.2, MLX-LM 0.31.3. Models were original BF16 and local affine 4 bit/group 64 Qwen2.5-0.5B-Instruct weights. Model and original LoRA file digests remained unchanged after each round. Performance inputs produced 62, 1022, and 3582 tokens through the real template. Each case used max_tokens=128, seed=0, temperature=0, top_p=1; every performance run actually produced 128 tokens.

There were 194 model processes: 190 normal completions and 4 requested cancellations, including 24 independent read-only processes observing first-step logits. This is an execution count, not a count of correct answers. The original plan and q4 failure reports are retained; v2 saved its plan in a new directory before independent execution.

<a id="原候选的功能与质量"></a>

## Original candidate functionality and quality

Basic execution passed 18/18. Performance passed 68/68, comprising 2 warmups, 54 interleaved comparisons across three rounds, and 12 attribution runs. All 24 cache layers were read back: each started empty; normal cache used KVCache and q4 used QuantizedKVCache. At the end of long-input execution, normal KV occupied 45 MiB and q4 KV occupied 12.65625 MiB.

| Weights | Configuration | Strict fixed-question correct count |
| --- | --- | --- |
| BF16 weights | Default auto/2048 | 4/6 |
| BF16 weights | Old candidate q4/512 | 1/6 |
| BF16 weights | Low latency for long input auto/4096 | 4/6 |
| 4 bit weights | Default auto/2048 | 5/6 |
| 4 bit weights | Old candidate q4/512 | 0/6 |
| 4 bit weights | Low latency for long input auto/4096 | 5/6 |

Fixed questions covered addition, identifier extraction, bare JSON, and code retrieval near the beginning/middle/end of long text. Output token IDs were identical for all 12 normal auto/2048 versus auto/4096 pairs. Default BF16 answered addition incorrectly, and both default weight types wrapped JSON in fences; all were marked incorrect under the original rules. All 6 long-retrieval q4/512 cases failed, with repetition and structural corruption, so No-Go remains. Source review confirmed only consistency with the upstream calling contract; it cannot establish a particular upstream kernel defect as the cause.

<a id="新-auto512-候选"></a>

## New auto/512 candidate

v2 restored KV to the model's computation precision while retaining 512-token chunks. All output token IDs for the 12 original fixed questions exactly matched the original default. Default correctness remained 9/12; the conclusion is no added regression. All 12 pairs of first-step full-vocabulary logits were finite and had the same argmax. The 6 short questions matched element by element; the 6 long questions had rounding differences, with maximum absolute difference 0.757812 and maximum RMSE 0.181574, so they are not numerically identical.

v2 additionally passed 36/36: 18 independent performance runs, 8 interleaved A/B requests across both weight types, 4 real LoRA off/on/off/on executions, 4 cancellations after actual Prefill/Decode events, and 2 recoveries after cancellation. Every new cache started empty; repeated outputs matched their own cold starts, and adapter identities differed. The 4 cancellations exited with 130 and no completed event; process groups were naturally reclaimed in approximately 92—123 ms. Recovery output matched that before cancellation.

<a id="性能与取舍"></a>

## Performance and trade-offs

All table values are medians of 3 runs. TTFT runs from before this execution's cache creation to the first engine token, excluding model loading. Generation peak is measured after resetting MLX counters before generation and includes loaded weights; it is neither whole-machine memory nor process RSS. Original reports separately retain load time, Decode speed, whole-process wall time, RSS, and every individual value.

| Round / configuration | Weights | Input tokens | TTFT ms | Generation peak MiB | KV MiB |
| --- | --- | --- | --- | --- | --- |
| Default auto/2048 | BF16 weights | 3582 | 169.43 | 1668.31 | 45 |
| Old candidate q4/512 | BF16 weights | 3582 | 261.23 | 1593.52 | 12.656 |
| Low latency for long input auto/4096 | BF16 weights | 3582 | 160.01 | 1648.24 | 45 |
| Default auto/2048 | 4 bit weights | 3582 | 166.76 | 1047.65 | 45 |
| Old candidate q4/512 | 4 bit weights | 3582 | 267.07 | 910.75 | 12.656 |
| Low latency for long input auto/4096 | 4 bit weights | 3582 | 160.63 | 1187.53 | 45 |
| Original attribution q4/2048 | BF16 weights | 3582 | 226.91 | 1746.61 | 12.656 |
| Original attribution auto/512 | BF16 weights | 3582 | 201.18 | 1329.18 | 45 |
| Original attribution q4/2048 | 4 bit weights | 3582 | 225.78 | 1047.65 | 12.656 |
| Original attribution auto/512 | 4 bit weights | 3582 | 202.82 | 641.78 | 45 |
| v2 independent auto/512 | BF16 weights | 62 | 117.05 | 993.13 | 3 |
| v2 independent auto/512 | BF16 weights | 1022 | 136.65 | 1310.55 | 15 |
| v2 independent auto/512 | BF16 weights | 3582 | 216.17 | 1310.56 | 45 |
| v2 independent auto/512 | 4 bit weights | 62 | 110.47 | 356.08 | 3 |
| v2 independent auto/512 | 4 bit weights | 1022 | 134.14 | 641.77 | 15 |
| v2 independent auto/512 | 4 bit weights | 3582 | 222.17 | 641.65 | 45 |

auto/512 reduced generation peak for medium and long inputs while keeping KV size unchanged, at the cost of slower first-token output; short inputs showed no stable memory benefit. Original auto/512 attribution and independent v2 measurements belong to different rounds. They cannot be combined into one round's statistics or used as individual measurements from different times to promise gains. auto/4096 was slightly faster than its respective default in all three local long-input rounds: BF16 median 169.43→160.01 ms and 4 bit weights 166.76→160.63 ms. For the latter, peak memory rose from 1047.65 to 1187.53 MiB, so neither general acceleration nor lower memory can be claimed.

<a id="剩余边界与复核"></a>

## Remaining boundaries and review

NVIDIA/remote execution, other models, rotating windows, cross-request prefix reuse, speculative decoding, multimodal cache, and Prefill/Decode separation are unavailable. Prefix hit rate is recorded as null (not enabled), not 100%. Any future q4 cache work must be proposed as a new candidate; renaming cannot reuse this failed evidence. Snapshots after new product fields or execution-source changes require new preflight; old evidence is not rewritten as a new version.

The summary script `tests/mlx/summarize_kv_probe.py` reads the following sealed reports, asserts counts, quality, token comparisons, process reclamation, and performance-output length, and generates `.artifacts/m2-kv/summary.json`. Historical source digests are governed by each report and frozen-plan.

- `.artifacts/m2-kv/functional-20260910-v1/report.json`, SHA-256 `67376362ca13f270d7869676331c3d1b509b81f0566cd11b739517495ffe667c`
- `.artifacts/m2-kv/performance-20260910-v1/report.json`, SHA-256 `169ccecfb561f3966522efc776cb2eda4a7278d1c06b9bdf65df5819e3eaea7f`
- `.artifacts/m2-kv/quality-20260910-v1/report.json`, SHA-256 `af0ac08f45495f8674be2a7c37259ef5380f61995ed18ae255f50e9a0fe2f93b`
- `.artifacts/m2-kv/low-memory-v2-20260910-v1/report.json`, SHA-256 `6885931d45c60f2591fb25ffdf7210557c6168c708d55d4bbff1a8715ea21528`
- `.artifacts/m2-kv/low-memory-v2-acceptance-20260910-v1/report.json`, SHA-256 `db8d8b549d5ff1d0f59e86dfef5bd723a708441db682852ef272e0df33666cbe`
