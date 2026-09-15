<!-- translation-navigation:start -->
[简体中文](../../../../docs/implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md) · [繁體中文](../../../zh-TW/docs/implementation/2026-09-16-ver2-4-032-diagnostic-directory-regression.md) · [English](2026-09-16-ver2-4-032-diagnostic-directory-regression.md)
<!-- translation-navigation:end -->

<a id="ver24032诊断目录原生回归e141"></a>

# Ver2.4（032） Native Diagnostic Directory Regression: E141

Root acceptance covers the complete diagnostic-directory workflow in the fixed company-signed 032 App: trilingual data import, directory cancellation and whole-diagnostic cancellation, saving to a directory with Chinese characters and a space, ZIP integrity and redaction, reopening the same library, and restoring original data. This is regression testing after the picker change, not the first diagnostic success. Historical E61, E88, E120, E122 successes and the E140 Python-path record remain unchanged. A diagnostic ZIP does not replace complete artifact-export AC27 or advance full AC22, M0—M6, or release status.

<a id="固定候选与分层验证"></a>

## Fixed Candidate and Verification Layers

This run uses source baseline commit `2d4d07745745e4221557a47addfa4055bb466925`, without rebuilding or changing the version. The fixed package remains Ver2.4（032）. Reverification passed for 21966 files, 48 links, 4003 directories, and 7 Global Cybersecurity Alliance Limited company-signed targets. [Package recheck](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/root-preflight.json)

Passed 95 control tests and 14 frontend tests, retaining 2 control-test warnings. Separately, 19 preparation synthetic tests and 25 launch-gate synthetic tests passed; each verifies its own contract and does not replace actual UI evidence. The preparation inspector tightened default non-page settings. The initial launch test failed because an intermediate version added a phase field; correcting the test fixture passed without changing production or lowering gates. [Focused tests](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/focused-tests.json), [preparation verification](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-preparation-001/preparation-check.json), [launch gates](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/launcher-review-001/gate-tests.json)

<a id="真实导入取消与保存"></a>

## Actual Import, Cancellation, and Saving

Only a new isolated A library was used. Actual selection imported 3 SFT samples in Simplified Chinese, Traditional Chinese, and English, totaling 650 bytes. Stopped-state resources are exactly 1 ready dataset and 1 import plan; the source, actual copy, and resource hashes match. At 02, typing the filename in the parent directory selected seed by mistake without opening it. Using the full path at 02b selected the exact file; only one import occurred. [Correct selection](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/02b-dataset-selected-correct.ax.txt), [import result](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/04-dataset-imported.ax.txt)

After the first diagnostic preview became ready, cancelling the native directory chooser returned to ready, left the target directory empty, and showed no success message. Explicitly cancelling the entire diagnostic then changed its record to cancelled. After selecting the scope again and creating a second preview, the native chooser selected `診斷 輸出` and saving was confirmed. The UI displayed “诊断 ZIP 已保存，文件完整性已核对。” These are distinct cancellation actions; an empty directory alone does not establish cancellation state. [After directory cancellation](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/07-directory-cancelled-ready.ax.txt), [whole-diagnostic cancellation](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/08-preview-one-cancelled.ax.txt), [directory confirmation](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/11-output-directory-confirmed.ax.txt), [saving and integrity](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/12-diagnostic-saved.ax.txt)

The output directory contains exactly one 9316-byte ZIP with two members, `diagnostics.json` and `manifest.json`. CRC, overall and member hashes/sizes, manifest complete status, and application version all match. Decoded content excludes the trilingual training text, synthetic sensitive markers, project name/ID, dataset filename, and personal absolute paths. Its SHA is `d57e4eb0eb26089f5e15c8ec9f88712194b68c6be3225ce91f101a8471ec73ba`. [First stopped-state check](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/exported-check.json)

<a id="重开保护恢复与边界"></a>

## Reopening, Protection Restoration, and Limits

The same fixed App and A library completed two normal exits, both 0. Reopening restored the original data page with the project and 3 samples visible. Every stopped-state database table, the raw database bytes, and the ZIP bytes remained exactly identical. There are exactly 5 commands: 1 import, 2 diagnostic previews (one cancelled and one successful), 1 diagnostic cancellation, and 1 export; 2 resources and 0 execution events. The diagnostic UI has no history entry, so its original registration is proven by stopped-state tables and the original ZIP, not by a reopened historical receipt UI. [Reopened data page](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/ui/15-second-restored-dataset.ax.txt), [reopened check](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/reopened-check.json), [two exits and root readback](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-readback.json)

The original selector bytes, inode, and permissions were restored, retaining the ctime difference. Of 47 protection records, 44 remained strictly unchanged, including absent entries and repeated paths; two startup logs were allowed to update. The App, control service, and guard stopped, with restoration and release receipts complete. No uninterrupted-forever guard guarantee is claimed. [Restoration](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/selector-guard/restored.json), [release](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/selector-guard/released.json), [root acceptance](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

Diagnostics contain 3 probe observations and 8 environment observations. App-session automatic probes actually occurred, so this is not zero probing; no new model task ran. Native evidence contains 17 AX/image groups and 34 files. The 16 second-exit image was abnormally reduced, with original AX and exit 0 retained. The directory-column screenshot did not show the final row; the path was checked jointly through the top Where value, complete AX, and returned confirmation, not that screenshot alone. [Root limitations record](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/native-run-001/root-readback.json)

Independent native review passed this diagnostic-directory regression while retaining the screenshot and capability limits. [Independent review](../../../../.artifacts/native-diagnostic-directory-ver2-4-032-v1/independent-native-review.md)

This diagnostic success does not close other artifact-export AC27, clean installation and full AC22, the specified NVIDIA round trip with the same LoRA artifact, quality admission, human media review, native cross-library races, notarization, or complete M0—M6. The limited E140 Python-path acceptance and the 031 failure remain preserved. [Python progress](2026-09-16-ver2-4-032-python-path-preservation.md), [delivery matrix](2026-09-10-current-delivery-matrix.md)

The `.artifacts` links on this page refer to local evidence and are not uploaded with the GitHub source. All formal documents remain available in Simplified Chinese, Traditional Chinese, and English.
