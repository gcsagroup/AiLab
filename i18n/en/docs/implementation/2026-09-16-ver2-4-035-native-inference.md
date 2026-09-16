<a id="ver24035本机真实推理与重开e145"></a>

# Ver2.4（035） Native Inference and Reopening: E145

Root accepted the limited local-inference and same-library reopening flow in the fixed company-signed 035 candidate: 1 real attempt, 0 training runs, saved work, an unexecuted recipe draft, and both normal App exits. The original guard failure and rejected launch request remain recorded; M2, full AC, M0, M2—M6, notarization, and formal release are not advanced.

The observed device was Apple M5 Max; only the evidenced local parameter/preset regression subset is closed. The 12 version tests and version check passed; their counts are not combined with source or other fixture tests. [Root limited acceptance](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-native-acceptance.json)

<a id="构建与来源"></a>

## Build and Sources

The build baseline was `c6d2e0886e1274b653179c4d8512194cdcffce25`, with automatic version projection to 035 and one build exiting 0. Root and independent review checked 656 tracked sources, 162 production / 212 frozen / 92 application inputs, 21966 files / 48 links / 4003 directories, and 7 company-signed targets; the 034 archive and build protections remained intact. Actual packaged control code matches the loading-boundary fix. [Root package check](../../../../.artifacts/integration-ver2-4-035-v1/root-frozen-check.json), [independent build review](../../../../.artifacts/integration-ver2-4-035-v1/independent-build-review.json)

<a id="真实界面与实际参数"></a>

## Native UI and Actual Parameters

The frozen Qwen 4bit model was imported through the native UI into a new isolated library, with loading-trust and permission explanations visible before confirmation. Offline loader options, an environment-variable allowlist, and a separate process do not provide an operating-system sandbox; custom model code remains unsupported. The 12 source-model files have separate protection. [UI record](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui-review-first.json)

Root separately verified that the native import-plan and model both persist the correct 7-field `execution_boundary`, bound to the import-confirmation AX/screenshot. This includes stored-data evidence, not UI wording alone. [Native boundary check](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/model-boundary-native-check.json)

Cancelling the low-latency and low-memory previews preserved auto／2048; applying low memory afterward selected auto／512. The exact prompt was `订单编号为 7391，金额为 82。只回答订单编号数字。`; actual settings were temperature 0, Top-p 1, seed 0, context 128, stop sequence `39`, and stream=false. The check rejected 50＋79＝129 with no associated attempt; changing only the maximum output allowed 50＋78＝128. Input was not truncated. [Rejected check UI](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui/09-over-budget-rejected.txt), [accepted check UI](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui/10-boundary-preflight-allowed.txt)

The single real inference succeeded with non-streamed text `7` and 0 token events. One work was saved and its original recipe viewed; a derived draft was created without checking or running it. The first App exit was normal, with code 0. Stopped checks verified 15 resources, 4 commands, 13 events, and 6 artifacts, linking the model, checks, snapshot, actual settings, artifact copies, and work recipe rather than merely comparing counts. [First-run check](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/first-check.json)

<a id="守卫失败与已确认恢复"></a>

## Guard Failure and Confirmed Restoration

The guard raised `UnicodeDecodeError` while decoding ps output and exited 1; its finally path restored the original selector after the App stopped. No normal released receipt was produced. Root separately confirmed that the old guard had exited and actually reacquired and released the original-library locks. Of 47 protection records, 44 remained strictly unchanged; the original selector identity and bytes were restored, retaining the ctime change and startup logs. Continuous locking is not claimed. [Original failure record](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/guard-failure-001.json), [root restoration readback](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-readback-after-first.json)

The second launch request exited 1 because the guard had entered restoration; no second App process was created. This rejection does not establish reopening acceptance or invalidate the completed first-run inference evidence. The original failure, first snapshot, and root acceptance binding remain unchanged.

<a id="同库重开与最终保护"></a>

## Same-Library Reopening and Final Protection

After independent review of the recovery procedure and gates, the same 035 package actually reopened the same new library. The UI restored the unexecuted recipe draft, and both the work and original task showed text `7`. No additional run or save occurred; both App exits were 0, and the new guard restored the selector, released locks, and exited 0. [Final UI record](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/ui-review.json), [second stopped check](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/second-check.json)

Business tables matched across both stopped snapshots, allowing only UI-context changes. The raw database SHA actually changed; identical database bytes are not claimed. The 15 resources, 4 commands, 13 events, 1 attempt／0 training／6 artifacts remained, with 31 model/run/artifact file hashes unchanged. Finally, 44 of 47 protection records were strictly unchanged, the original selector inode/bytes were restored, and the 12 source-model files were unchanged. The interruption in locking remains recorded. [Root final readback](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/native-run-001/root-readback.json)

UI evidence consists of AX and screenshots at key checkpoints, not continuous video. Numeric fields may display leading zeros; stopped records confirm their numeric values. The completion screenshot remained at the page bottom, while the saved-work screenshot shows the complete short text. A short input and one fixed model do not establish general quality or performance, NVIDIA or training acceptance, a first-user rehearsal, or full M2. Existing M1 stage acceptance remains; the source-stage statement that “035 is not built” remains as historical evidence.

Full clean-install acceptance by 5 first-time users is a separate M6 gate, not a condition for M2 completion; M2 still needs evidence for its own specified devices, execution locations, failure flows, and first-language-trial stage rehearsal.

First-run and final independent reviews remain separate, with original failures preserved. The 46 recovery-helper fixture tests passed; these are not real-model tests and are not added to other test counts. [First-run review](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/independent-first-review.md), [final review](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/independent-native-review.md), [recovery fixture tests](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/reopen-tests-final-v2.log), [version tests](../../../../.artifacts/native-m2-inference-ver2-4-035-v1/version-tests.log)
