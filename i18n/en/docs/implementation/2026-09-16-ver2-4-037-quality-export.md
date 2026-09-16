<a id="037-失败质量准入报告导出与重开"></a>

# 037 failed-quality admission, report export, and reopening

The fixed company-signed Ver2.4（037）candidate completed limited acceptance of an existing failed evaluation: actual HTTP candidate-registration rejection, native per-item results, report export, and same-library reopening passed. The original weights scored 11/16 and the quantized candidate 10/16; the quality failure remains. No new model computation or evaluation occurred; full M5, M0—M6, and release remain unpassed.

<a id="候选来源与恢复"></a>

## Candidate, source, and restoration

The fixed App signed by Global Cybersecurity Alliance Limited was reused without rebuilding. Its actual binary digest is `59ce9d899488da868af0935f6dcb7f09749623deab250d55eeda7def4f0b2ce0`; deep, strict signature verification passed again. [Package receipt](../../../../.artifacts/integration-ver2-4-037-v1/root-frozen-check.json)

With the original E22 library stopped, only frozen files were copied; no SQL connection was made to the original library. The offline restoration input contains 91 files and 1868874298 bytes and is explicitly identified as an acceptance file copy, not a backup created by the product backup API. The packaged 037 control service then formally checked and restored it into an independent library over actual HTTP. Product restoration logic rewrote path references; all 11 sealed evaluation artifacts retained their hashes. [Restore receipt](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/restore-001/result.json)

<a id="实际准入与原生操作"></a>

## Actual admission and native operation

The packaged service read the existing failed evaluation and requested registration of the original quantized candidate against it, returning `409 / EVALUATION_FAILED`. The candidate registry still contains 0 entries, and the model remains experimental. Resources, commands, events, and projects were unchanged across the request, and the service exited normally. No new model task was submitted. [Actual admission receipt](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/admission-001/result.json)

The existing evaluation task was opened natively to inspect baseline and candidate outputs, decisions, and failure reasons for all 16 questions. Business tasks and output formatting both scored 2/4, below 75%; regression scored 3/4 for both, and behavior fell from 4/4 to 3/4. The interface distinguishes completed execution from failed quality and disables candidate registration. [Quality screen](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/native-001/01-quality-failed.png) [Per-item record](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/native-001/02-item-results.ax.txt)

A directory containing Chinese characters and spaces was selected through the native picker. After scope checking, the report was exported once. Both planned and actual payloads contain 11 files and 60884 bytes, plus an integrity manifest. Of these, 7 JSON reports come from the original sealed artifacts; the remaining files contain the recipe, fixed questions, criteria, and object metadata. Every payload file matches its size and hash, and the original quality report bytes are unchanged. The export record is `export-38e8198354cb4b1a82a6299f7108eed0`. [Completion screen](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/native-001/04-export-result.png)

After normal exit, the same candidate and independent library were reopened. Failed quality, disabled registration, and the same completed export record persisted; the App then exited normally again. Every exported file and the manifest retained their bytes. Report export does not establish independent model execution or passing quality. [Reopening screen](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/native-001/06-reopen-export.png)

<a id="停机核对测试与边界"></a>

## Stopped-state checks, tests, and boundaries

Stopped snapshots confirm that all 52 original resources remain unchanged. Only an export plan, export record, export task, and export execution record were added, giving 56 resources, 1 command, and 90 events. New model runs and evaluations both total 0. All business tables remain identical across reopening; only the selected task in settings was cleared by returning to the workbench, so database bytes are not identical. Both App exits returned 0. [Root readback receipt](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/native-001/root-readback.json)

The original selector file object and contents were restored. Of 47 protected records, 44 remained strictly unchanged; the exceptions are selector ctime and the two startup diagnostics. The original E22 library, all files in the previous 4 acceptance libraries, 12 model source files, and the offline restoration input are unchanged. No host source settings were added; the guard restored the selector and released its locks.

Evaluation and conversion tests passed: 8 frontend and 65 control-service tests, with 2 control warnings retained. Restoration preparation passed 8 helper tests and the native launch guard passed 7. These tests use fixtures and do not establish new quality results. [Frontend log](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/frontend-tests.log) [Control log](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/control-tests.log)

The root verifier initially stopped because it used the manifest file-byte hash where a canonical JSON digest was required, then because it assumed the execution manifest contained a size field. Both scripts and failure logs were retained. After checking the production format, it verifies canonical JSON and independent file hashes separately and obtains sizes from sealed artifact records. Verification then passed without changing the product, execution records, or exported files. [Initial digest failure](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/native-001/readback-initial-byte-digest.log) [Size-field failure](../../../../.artifacts/native-m5-quality-ver2-4-037-v1/native-001/readback-initial-size-field.log)

This acceptance covers only registration rejection, native reading, report export, and persistence across reopening for an existing failed evaluation. The frozen quality plan was not rerun; there is no passing candidate. New quantization execution, speed gains, cross-device use, clean installation, notarization, and full release were not verified. Prototypes, research assets, earlier failures, and original acceptance records are preserved.
