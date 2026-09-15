<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-15-media-keyboard-progress.md) · [繁體中文](../../../zh-TW/docs/implementation/2026-09-15-media-keyboard-progress.md) · [English](2026-09-15-media-keyboard-progress.md)
<!-- translation-navigation:end -->

<a id="media-三入口键盘进度e136e137"></a>

# Media Three-Entry Keyboard Progress: E136—E137

**Latest Media keyboard progress (2026-09-16, E137)**: The fixed company-signed candidate is now Ver2.4（029）. Root acceptance covers the single build and the limited native subset: four instances of the three entries across two existing tasks, forward and reverse Tab, Enter to open, Escape to close and return focus, normal exit, and one stopped-state readback. The 523 resources, 673 events, 3 commands, and all business records remain unchanged; only four expected page-setting leaves changed. No real import or model run occurred. The existing limited acceptances for 028 and 027 remain in place; full AC, M0—M6, notarization, and public release remain incomplete.

<a id="e137029-签名包与原生有限接受"></a>

## E137: 029 Signed Package and Limited Native Acceptance

<a id="包与构建证据"></a>

### Package and Build Evidence

Available capacity before this execution was approximately 117.39 GiB, above the original 40 GiB threshold; no cleanup occurred and the threshold was not lowered. The 028 rollback archive succeeded, and 26 synthetic build-gate tests, 8 root package-verifier tests, and 12 version-synchronization tests passed. The single 029 build took 496.86 seconds and exited 0, automatically updating four version files. The 160 production sources, 210 frozen inputs, 90 application inputs, and 21966 regular files/48 symbolic links/4003 directories matched, and root verification accepted 7 company-signed targets. Before the formal build, the only production source changes relative to 028 were the three Media keyboard attributes. [028 archive acceptance](../../../../.artifacts/integration-ver2-4-029-v1/archive-tool-receipt.json), [Build-gate tests](../../../../.artifacts/integration-ver2-4-029-v1/root-script-acceptance.json), [Root package-verifier tests](../../../../.artifacts/integration-ver2-4-029-v1/root-verifier-acceptance.json), [Version-synchronization tests](../../../../.artifacts/media-keyboard-ver2-4-next-v1/resume-20260916-001/version-tests.json), [029 package acceptance](../../../../.artifacts/integration-ver2-4-029-v1/root-bundle-acceptance.json)

<a id="原生界面与停机数据证据"></a>

### Native UI and Stopped-State Data Evidence

The same 029 App run verified four entry instances across two existing tasks: model/image data for image training and model/image material for video execution. Forward Tab and reverse Shift-Tab reached each entry, Enter opened the correct dialog, and Escape closed it and returned focus to the same entry. Root acceptance covers 19 screenshots and 19 AX records, totaling 38 files. After Cmd+Q, CUA briefly returned pipe closed; the exit confirmation was then reread from the same App and Exit was clicked. There was no restart; the single launch ended normally with exit 0. [Native focus acceptance](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/root-focus-acceptance.json), [Normal exit record](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/run/result.json)

After shutdown, exactly one immutable read-only connection was opened; readback exited 0 and the connection was closed. The 523 resources, 673 events, 3 commands, and all business records remained strictly unchanged. The two task draft revisions remained 2/3, and `module_tab=train` and the original recent text task were preserved. Exactly four page-setting leaves differed: `kind`, `task_id`, `recent_tasks/image:train`, and `recent_tasks/video:generate`. Library selection was restored; the selection file retained its contents and inode, while its timestamps changed. Protection of the old databases, old export packages, and existing remote process remained in place. [Root acceptance of stopped-state readback](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/root-readback.json)

This root acceptance covers only the limited subset above; no real file import, business save, or model run occurred. Independent review has accepted this limited subset; screenshots and AX capture saved states and do not replace per-keystroke event logs. [Native independent review](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-review-001/review.md). The existing 028/027 results remain in place. Complete keyboard coverage, full AC/M0—M6, NVIDIA, cross-platform execution, clean installation, five first-time users, old quality failures and budgets, the old 020 blank-window and initial-display/full-readiness gaps, notarization, and public release are not completed by this work. The package receipt’s statement that native acceptance had not started, and the older records below, retain their meaning at creation time.

<a id="2026-09-15-历史准备记录"></a>

## Historical Preparation Record: 2026-09-15

The E136 and earlier records below retain their original wording from 2026-09-15; insufficient capacity and the unbuilt candidate describe the historical state.

The current fixed company-signed candidate remains Ver2.4（028）. The source fix for the three Media import entries, 56 related frontend tests, and the real Safari keyboard subset have been accepted, and the root agent has closed the independent review. 029 has not yet been archived, built, or natively verified. Capacity is below the original 40 GiB threshold; cache cleanup still awaits user confirmation, and no deletion has been performed. The existing acceptance of 028 remains in place; full AC and M0—M6 are not advanced. [028 historical progress](2026-09-15-ver2-4-028-workbench-keyboard-progress.md)

<a id="e136三处属性相关测试与独审"></a>

## E136: Three Attributes, Related Tests, and Independent Review

Of the 160 frozen production sources, only `apps/desktop/src/Media.tsx` changed: `tabIndex={0}` was added to the three native buttons, “Import Model,” “Import Image Data,” and “Import Image Material.” Strictly removing these three attributes restores the entire file byte for byte to the pre-fix 028 version; the other 159 sources remain unchanged. Button types, import callbacks, filtering, branches, and the real Workbench fieldset disabling logic are unchanged. [Root source acceptance](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-source-acceptance.json)

The formal red run had 7 passes and 1 failure out of 8 tests; that failure included assertions that all three entries lacked the attribute. The original initial setup failure, in which JSDOM did not provide showModal, is retained. After the fix, the new test file retains the exact bytes used in the formal red run. All 56 tests across 7 files passed, including the 8 new tests; type checking exited 0, and another 3 fixture tests passed. These are not added to the 59 tests for 028. The new tests verify that ordinary clicks do not import in four read-only/disabled states, that the import types are correct, that the original draft is preserved, and that focus returns on close. Unit-test clicks and simulated cancel events do not replace real Safari Enter/Escape actions. [Red-run record](../../../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/result.json), [Green receipt](../../../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/green-result.json), [Test scope](../../../../.artifacts/media-keyboard-ver2-4-next-v1/source-tests-001/green-REVIEW.md)

The independent reviewer actually viewed 12 key post-fix screenshots from the two groups and checked the source, events, AX, and the 132-item hash manifest. The root agent then rechecked and closed the pending independent review. The pending=true in the original source acceptance retains its meaning at creation time; it does not mean independent review is still pending, and the original has not been rewritten. [Independent re-review](../../../../.artifacts/media-keyboard-ver2-4-next-v1/browser-review-002/review.md), [Root closure of independent review](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-review-closure.json)

<a id="safari-开发组件前后对照"></a>

## Before-and-After Safari Development Component Comparison

The page on fixed loopback port 4328 directly imports the real MediaFields and ImportDialog and uses two empty-resource branches: image training and video execution. It has no control-service proxy or request fallback. The observer only records ordinary keys and focus; it does not take over Tab or actively focus anything. The product Dialog retains its own opening and focus-return logic. Safari’s AppleKeyboardUIMode remains 0; system keyboard settings were not changed. [Fixture preparation](../../../../.artifacts/media-keyboard-ver2-4-next-v1/browser-preparation.json)

The two pre-fix groups contain 26 files in total. Each group has 2 Tab presses and 2 Shift-Tab presses; the three enabled source entries were skipped. Both groups’ original records and hashes remain intact. After the fix, the page was reloaded. Each group contains 29 files and 38 events, with 4 Tab presses, 4 Shift-Tab presses, 2 Enter presses, and 2 Escape presses. Both entries are reachable in both directions. Image training opens the model/image-data dialogs; video execution opens the model/image-material dialogs. All four closes return to their respective entries with a visible focus ring. Request, error, input/change-event, and dropped-record counts are all 0. No file import, save, or model run occurred. [Pre-fix acceptance](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-before-acceptance.json), [Post-fix acceptance](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-after-acceptance.json)

During initial navigation, typeText lost URL punctuation and opened a search page; a paste operation also reported a timeout. The fixture was entered only after confirming the correct local address. This preliminary navigation issue is retained and is outside the fixture’s zero-API-request scope. The last two AX records do not list a separate focused row. The final return to the starting anchor is established by focusin and report.active; the missing AX row is not described as an absence of focus. The dedicated Safari window has been closed, the fixture service has stopped, and port 4328 has no listener. [Post-fix and stop receipt](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-browser-after-acceptance.json)

<a id="029-仍待容量打包与原生验证"></a>

## 029 Still Awaits Capacity, Packaging, and Native Verification

The current App still uses the fixed company-signed 028 package. This change did not update the version or build a new package. 029 continues to use the same path and the existing archive, protection, and build gates. Passing source and Safari checks must not be described as passing the 029 package or native acceptance. [Integration preparation](../../../../.artifacts/media-keyboard-ver2-4-next-v1/integration-preparation-001/plan.md)

The read-only capacity record at 07:06:10 Beijing time on September 15 was 34.084 GiB, below the original 40 GiB threshold. This number is an observation from that time and must be measured again before execution. The only scope proposed for confirmation is this project’s `apps/desktop/src-tauri/target/debug` debug/test cache, whose accounted directory size is approximately 8.190 GiB. This is a proposal: cleanup confirmation has not been received, and nothing has been deleted. APFS shared blocks and snapshots may affect the space actually reclaimed. The accounted size must not be treated as already available space, and the threshold must not be lowered. The fixed 028 App, release, historical archives, working database, models, and evidence are outside this proposal. [Capacity and cleanup proposal](../../../../.artifacts/media-keyboard-ver2-4-next-v1/integration-preparation-001/capacity-options.md)

This work adds no model capability and does not sign off real file import, the Media path in the signed App, complete keyboard coverage, full AC, or M0—M6. The designated NVIDIA environment, the same artifact across platforms, clean installation/notarized release, five first-time users, old quality failures and consumed budgets, the old 020 blank-window issue, and historical gaps in initial display/full readiness remain unchanged. [Current delivery matrix](2026-09-10-current-delivery-matrix.md)

<a id="原生脚本准备已完成尚未启动"></a>

## Native Script Preparation: Complete, Not Yet Started

The supervisor, stopped-state readback, and data comparison scripts have been prepared and independently reviewed with acceptance. All synthetic tests passed: 10 supervisor tests, 13 readback tests, and 12 comparator tests. The formal Python 3.13 environment also passed these 35 tests; the readback/comparator compatibility rerun is not counted twice. One negative case in the first readback run did not actually change its input. It passed after the test was corrected; the original failure logs and receipt are retained, and the readback rules were not relaxed. Neither independent review found a blocker. The inherited process-exit logic received static review only; no real App was restarted in this round. [Root script acceptance](../../../../.artifacts/media-keyboard-ver2-4-next-v1/root-native-preparation-acceptance.json), [Independent supervisor review](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/supervisor-review.md), [Independent readback and comparator review](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/reader-review.md)

The subsequent native scope is limited to four entry instances in two existing tasks, using only Enter to open and Escape to close and verify focus return. The comparator requires the complete business data to remain unchanged and permits changes to only four leaf settings for page selection. These are criteria for future execution; no real readback result exists yet. No run binding has been created, no connection has been made to the working database, and no 029 App has been started. The scripts refuse to proceed without the formal 029 package and UI/exit evidence from the same run. [Task scope](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/task-scope.json), [Supervisor script acceptance](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-run-001/root-supervisor-review.json)

The final read-only check at 07:49:30 Beijing time on September 15 confirmed that the 160 production sources, five 029 build-preparation inputs, and seven anchors of the fixed 028 package remained unchanged, and that all 29 specified real-execution outputs were absent. Available disk space at that time was approximately 28.86 GiB, still below 40 GiB. Even counting the full previously recorded debug directory size of about 8.19 GiB would not reach 40 GiB; capacity must be reconfirmed before actual execution. The original cleanup confirmation has not been received. No cleanup or scope expansion occurred, and the current version remains 028. [State record](../../../../.artifacts/media-keyboard-ver2-4-next-v1/native-preparation-review-001/final-state-001.json)
