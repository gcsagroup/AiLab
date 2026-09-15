<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-14-subtitle-scroll-diagnosis.md) · [繁體中文](../../../zh-TW/docs/implementation/2026-09-14-subtitle-scroll-diagnosis.md) · [English](2026-09-14-subtitle-scroll-diagnosis.md)
<!-- translation-navigation:end -->

<a id="024-后长字幕空白诊断e123"></a>

# Long-Subtitle Blank-Window Diagnosis After 024 (E123)

This round established the exact operations preceding the old issue and completed a Safari comparison. **The intermittent blank-window issue in 020 has not been located or fixed.** The current fixed candidate remains company-signed Ver2.4（024）. There were no product changes, new build, or formal App startup; complete long-list, keyboard, AC, and M0—M6 status are not advanced.

<a id="原操作已查明"></a>

## Original Operations Established

The tool documentation available during the original session explicitly defined the third argument as “pages.” After the video reached 2/2 seconds, the original operation clicked the expanded “Differences from Parent Version,” immediately scrolled down 160 pages once, and then captured 29. There was no further input before capture 30. Both original images are blank, and their capture completions are 6 seconds apart; they do not prove continuous blankness between them. Subsequent scrolling up 1 page and down 1 page restored the view in 31/32. All four AX records are identical, which cannot establish the actual scroll position or correct painting. [Original action and contemporary documentation](../../../../.artifacts/revision-blank-after-024-v1/original-action-review-001/REVIEW.md), [Original-image review](../../../../.artifacts/revision-blank-after-024-v1/evidence-review-001/REVIEW.md)

The current component has no logic that unmounts subtitles in response to scrolling. Current version 4 displays only its own 19 diff lines and does not recursively display parent version 3’s 804 diff lines. The scroll-boundary isolation in 021 has been verified, but no evidence shows that it explains the old blankness. No scroll container was replaced or product changed based on speculation in this round. [Source diagnosis](../../../../.artifacts/revision-blank-after-024-v1/source-review-001/REVIEW.md)

<a id="safari-实际结果"></a>

## Actual Safari Results

One isolated loopback service, one new Safari tab, and one opening of the real revision component used the saved 200 entries/16000 characters, current 4/parent 3, and original 119551-byte video. Safari 26.6.2（21624.5.1.11.3）ran on macOS 26.6.2 arm64. The measured CSS viewport was 1337×959, DPR 2, and visual scale 1. 16 groups of AX and 979×768 JPEGs cover preparation, operations, and final state. The old App’s 1152×768 screenshots cannot directly be treated as a known CSS viewport. [Live result](../../../../.artifacts/revision-blank-after-024-v1/safari-run-001/result.json), [Capture start and end](../../../../.artifacts/revision-blank-after-024-v1/safari-run-001/ui/records.json)

| Comparison | Observation |
| --- | --- |
| Separate collapse click and 160-page scroll | 05, after collapse but before scrolling, already shows entries 195—200 and parent 3. Both unmodified images 06/07 after the large scroll are normal. |
| Restore expansion and the top on the same page, then contiguous click→160 pages | Both unmodified images 12/13 are normal. DOM click to wheel event was 35 milliseconds; the two CUA action calls together took approximately 78.887 milliseconds. These measure different intervals. |
| Original up-1-page/down-1-page path | Images show scrolling upward and returning to the end. Detailed scrollTop measurements are 19224→18175→19224; subtitle node identity remains unchanged. |

The records reveal the tool’s actual behavior: before clicking summary it had already scrolled to 19504; clicking to collapse reduced the position to 19224. The subsequent 160-page input appeared in this window as one wheel event with deltaMode=0 and deltaY=167840, while content remained at the bottom boundary. The 1-page input in this run was 1049 pixels. This cannot be generalized to the viewport height of every scroll container, nor can this pixel amount be retroactively applied to the old App. [Complete events and geometry](../../../../.artifacts/revision-blank-after-024-v1/safari-run-001/observations.json), [Contiguous-call timing](../../../../.artifacts/revision-blank-after-024-v1/safari-run-001/contiguous-actions.json)

None of the 34 records were dropped and there were no page errors. All 4 explicit geometry measurements showed 200 entries/16000 characters, dialog total height 20131, internal visible height 907, and maximum scrollTop 19224. Background scrollTop was always 0, and the original video had always reached 2/2 seconds. After the dialog closed, the complete JSON in the AX text area was parsed and compared value by value with the saved records. Rectangle intersection identifies potentially visible items; it does not prove that text pixels were painted. Explicit measurement began only after the first two unmodified images, and the default scrollTop observer still does not guarantee zero layout disturbance.

<a id="验证与结束状态"></a>

## Verification and Final State

The fixture’s 6 tests passed, covering the fixed sample, GET restrictions, media-digest rejection, observation limits, and geometry timing. After adding an ordinary-click collapse assertion, only the 1 affected test was rerun and passed. This is not counted as 7 independent tests or product acceptance. The first round’s 4 passes and 2 failures arose from test initial state and the old TypeScript transformation API; the originals are retained. [Tests and source digests](../../../../.artifacts/revision-blank-after-024-v1/safari-fixture-001/result.json)

Two people reviewed the run files read-only. At completion, the complete records for 160 product sources, 7 anchors of the fixed 024 package, and 23 protected files matched the state before this run. The new tab was closed, while the original blank Safari tab was retained. The root agent explicitly ended the development service with Ctrl-C; the tool returned 1, and port release was subsequently confirmed. This is not described as a normal exit 0. This round had 0 formal App runs, builds, model runs, probes, SQL connections, or business saves/exports. [Pre-operation check](../../../../.artifacts/revision-blank-after-024-v1/before.json), [Post-operation check](../../../../.artifacts/revision-blank-after-024-v1/after.json)

After the initial Safari paste tool timed out, the next AX already showed the full address, so only Return was added; paste was not repeated and no extra tab was created. The root agent’s first digest check encountered an observer still finishing, and no incorrect acceptance was written. The first image verification failed before writing a result because the default Python lacked PIL. An existing workspace runtime was used to actually decode all 16 images and compare images with text, without installing dependencies or recapturing images. Both failures and corrections are retained in the live result’s boundary records.

The independent reviewer also personally viewed 8 original images, passed 19 saved-evidence checks, and bound 50 input digests; these are not new product tests. The first screenshot call in the contiguous sequence took approximately 0.674 seconds and cannot prove every frame at shorter intervals within it. The independent reviewer’s initial wrong-directory read failure is retained; the live run was not repeated. [Independent-review conclusion](../../../../.artifacts/revision-blank-after-024-v1/safari-review-001/REVIEW.md)

This round closes only the evidence gap concerning an imprecise description of the original operations. The Safari host, current 024 source, and second sequence on the same page all differ from the old 020 live conditions, so success cannot close the original issue. The next step still requires simultaneous position, text geometry, and pixel evidence under native conditions that reproduce blankness. Without such evidence, the blank-window fix is not signed off. 024’s 3.938-second full readiness still does not meet 3 seconds. Old quality, training budgets, the 017 fault window, and gaps for the designated NVIDIA environment, cross-host operation, notarization, clean installation, and five first-time users remain. [Formal 024 scope](2026-09-14-ver2-4-024-progress.md)
