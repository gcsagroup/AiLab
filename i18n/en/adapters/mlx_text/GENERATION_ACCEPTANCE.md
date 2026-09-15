<!-- translation-navigation:start -->
[简体中文](../../../../adapters/mlx_text/GENERATION_ACCEPTANCE.md) · [繁體中文](../../../zh-TW/adapters/mlx_text/GENERATION_ACCEPTANCE.md) · [English](GENERATION_ACCEPTANCE.md)
<!-- translation-navigation:end -->

<a id="本机文本生成参数验收"></a>

# Local text-generation parameter acceptance

Date: 2026-09-10. **Context-budget, stop-sequence, and streaming fields for the fixed local Qwen2.5-0.5B combination have taken effect from the formal API through the real model; sealed content, saved works, and recipe reload have been checked.** This document covers single text inputs only. Multi-turn history trimming and thinking switches are unavailable. Ordinary-user UI and the final relocated installation package are supported by their own acceptance records.

<a id="已开放合同"></a>

## Available contracts

| Field | Default and permitted range | Actual behavior |
| --- | --- | --- |
| `context_limit` | 4096; strict integer 128—4096 | Tokens from the real chat template and input, plus the full `max_tokens` reservation, must fit within this budget |
| `overflow` | Only `reject` | Reject overflow and retain the original input; there is currently no old conversation to trim |
| `stop` | Empty array; at most 8 distinct items, each 1—128 characters | Exact string matching with spaces retained; possible prefixes are buffered across output chunks; a match closes the generator and is excluded from displayed and sealed content |
| `stream` | Strict boolean, default `true` | When disabled, no incremental token events are emitted; phases, cancellation, and final-content saving still work |
| `thinking` | Only `default` | Qwen2.5 and this fixed template have no thinking-switch capability; public capabilities explicitly say unsupported rather than hiding output to simulate disabling it |

New fields not explicitly present in old drafts remain omitted; actual defaults are pinned during preflight. These fields apply only to text `generate`. Training, evaluation, quantization, and media operations reject them. A stop sequence takes effect at the earliest completion position. If several complete together, the earliest start position wins, followed by array order; chunking does not change the result.

The parameters enter the `mlx-inference-v2` identity, binding real input tokens, template, model/adapter, execution source, runtime versions, and sampling parameters. Changing context, stop sequences, or streaming after checking requires another check. An old identity cannot execute new fields. Original execution snapshots and existing evidence are not rewritten.

<a id="最终源码实算"></a>

## Real computation with final source

Final execution evidence: `.artifacts/m2-generation/real-20260910-v2/report.json`; the frozen plan is `frozen-plan.json` in the same directory. Executor and model-source digests for both weight types remained unchanged.

Each weight type performed 7 independent normal generations. The fixed input (translated here from Chinese) was “The order number is 7391 and the amount is 82. Answer only with the order-number digits.” It produced 50 tokens through the real template, with the same seed, greedy sampling, and KV configuration.

| Check | Results for BF16 / 4 bit weights |
| --- | --- |
| Streaming default | Both output `7391`, with 5 engine-returned tokens (including EOS) and 5 token events |
| Non-streaming default | Output bytes and engine tokens were identical to streaming; both had 0 token events |
| `stop=["39"]`, streaming enabled/disabled | `3` and `9` matched across two real tokens; only `7` remained, engine-returned tokens fell from 5 to 3, and streaming events leaked no stop prefix |
| `stop=["7"]` | Matched the first token; final content was empty and completion was normal |
| `stop=[" 7391 "]` | Spaces were not stripped; no match occurred, and output remained `7391` |
| Total budget exactly 128 | Input 50 plus maximum output 78 passed without trimming |

All 6 additional real boundary observations passed: one cancellation after a non-streaming Prefill event, one executor rejection after changing a stop sequence following preflight, and one checker rejection of an actual total budget of 129 against 128 for each weight type. Cancellation exit codes were 130, with no token or completed events, and all process groups were reclaimed. Modified execution returned `INFERENCE_IDENTITY_CHANGED` without a content artifact. Budget rejection returned actual budget details and created no output directory. Non-streaming Decode cancellation has separate CPU-driven coverage and is not described as real-model Decode cancellation in this run.

Engine-returned token counts include a token that triggers stopping or EOS; visible content excludes the stop sequence. Cache records contain only each layer's type, shape, precision, and byte size, not KV contents. Release paths cover initial-cache rejection, normal completion, stop matches, and cancellation.

<a id="正式-http-与作品闭环"></a>

## Formal HTTP and saved-work workflow

Final evidence: `.artifacts/m2-generation/http-real-20260910-v2/report.json`. A new isolated control library and fixed 4 bit weights were used; all cases passed:

| Real execution | attempt | Token events | Final content |
| --- | --- | --- | --- |
| Full streaming output | `attempt-adac8bcb7b3144fab285134757ccb4b3` | 5 | `7391` |
| Full non-streaming output | `attempt-9970e46329ee4c0091c464803de69612` | 0 | `7391` |
| Non-streaming stop sequence | `attempt-140a3739fbd04a1b873827626148881f` | 0 | `7` |

All three executions checked the draft, requested config, immutable snapshot, real effective config, and inference identity. Final content was verified against the original execution manifest, sealed, and saved as a work; file SHA matched the work's content. Loading the original work recipe into a new draft and checking again produced the same identity. Another task with a 129/128 total budget was rejected before API submission; submission returned 409 with 0 attempts.

The first HTTP script's three real executions passed, but its final step incorrectly read an internal manifest from the public import plan and did not seal the overall report. The original directory and error log remain. Only the test script was corrected; a complete rerun in a new v2 directory passed, without changing product source or filling in the old report.

<a id="自动化检查与剩余范围"></a>

## Automated checks and remaining scope

- 187 MLX CPU tests passed, excluding the separate real lifecycle test; evidence: `mlx-integrated-final-results.xml`.
- All 538 control-service tests passed; evidence: `control-stable-source-results.xml`. One crash test previously timed out during concurrent source editing; after source freezing, the 4 CLI tests and complete control suite passed again.
- An independent review exhaustively checked another 69,615 stop-sequence/chunking combinations with consistent results. An exceptional-release gap during initial-cache checking was fixed and covered by regression tests.
- `.artifacts/m2-generation/summary.json` checks final computation state, sample counts, test XML, and referenced-file SHA. Historical performance and KV-candidate evidence is in `PRESETS_ACCEPTANCE.md`; q4 cache remains No-Go.

Multi-turn message structures, history trimming, model thinking switches, other models/devices, and server-side remote streaming are not available. The default context of 4096 is not presented as the model's larger advertised positional capacity. The backend subset of AC-09 for the current single-input local combination passed; the complete interface, cross-location behavior, and multi-turn scope still require separate acceptance.
