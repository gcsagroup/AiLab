<a id="038-导出清单身份恢复与原生重开"></a>

# 038 export manifest identity recovery and native reopening

The fixed company-signed candidate is now Ver2.4（038）, including the complete export manifest identity check. Controlled registration failure, rejection of an incorrect version, a successful new export through the actual packaged service, and native history inspection and reopening of a formally restored library passed. This conclusion covers only this subset; full M6, M0—M6, notarization, and formal release remain incomplete.

<a id="候选与修复"></a>

## Candidate and fix

The signing organization is Global Cybersecurity Alliance Limited. Full package readback checked 21966 regular files, 48 symbolic links, and 7 company-signed targets; frozen source matches the actual compiled control service inside the package. The main binary digest is `60c0940798b39a7c9378ffd5f1d4fb544e4a409fb2b52b26403ed0e894be75fc`. [Build verification](../../../../.artifacts/integration-ver2-4-038-v1/root-frozen-check.json)

The preceding source regression passed 179 tests. The producer and recovery verifier share the complete frozen manifest, rejecting incorrect objects or versions, missing fields, extra claims, incorrect types, and nonfinite values; valid complete packages remain recoverable. Evidence of failures before the fix is preserved. [Source regression](../../../../.artifacts/export-manifest-identity-source-v1/regression-final.log)

<a id="包内服务与故障边界"></a>

## Packaged service and fault boundaries

Actual HTTP requests used synthetic model-file fixtures that cannot run as a model in a fresh independent library. A SQLite registration rejection was injected only for this export. After files were written, the service was stopped normally, the test trigger was removed, and the version identity in the manifest was changed before restarting and reconciling. This simulates registration failure, rather than an operating-system process kill or an actual crash during copying.

The package with the incorrect version was rejected. Its original record became `EXPORT_INTERRUPTED`, with no usable path registered; original files and the altered package were preserved. Preparing again produced a successful new export, with all 4 payload files and the manifest verified. Failed and successful records remained separate after service restart. Formal product backup and restoration then created an independent library for native acceptance. [Packaged results](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/run-001/result.json)

<a id="原生查看退出与保护"></a>

## Native inspection, exit, and protection

The same fixed App opened the formally restored library twice, inspected the existing failed and successful records, and stopped normally through native quit confirmation. Only the UI settings table changed on the first shutdown; business tables remained unchanged. The entire database snapshot after the second shutdown matches the first. The original library selection was restored, 47 protected records were verified, and 12 model source files and previous acceptance libraries remained unchanged; no new model execution or SQL connection to the original user library occurred. [Final verification](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/root-readback.json)

Host full readiness took 4522.186 and 4580.050 milliseconds; external observations took 4650.026 and 4732.063 milliseconds. These do not measure initial window visibility or meet the evidence requirements for 20 initial-visibility launches. [First launch](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-001/startup/report.json) [Reopened launch](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/startup/report.json)

Native actions only inspected export results already created during the HTTP stage; the fault and new export were not triggered through the UI. [Reopened failure](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/01-failed.jpg) [Reopened success](../../../../.artifacts/packaged-export-identity-ver2-4-038-v1/native-reopen-002/02-success.jpg)

<a id="容量处理与未完成事项"></a>

## Capacity handling and remaining work

Capacity failures before and after building are preserved. Only regenerable build caches were removed after archiving and verifying all contents, hard links, and attributes. Archives and restoration tools that refuse overwrites remain available; user data, models, and historical failures were not deleted. The initial helper error, interrupted inefficient read-only verification, and post-build capacity-gate failure are preserved, and the gate was not lowered. [Cache archive](../../../../.artifacts/build-cache-recovery-038-v1/result.json) [Staging archives](../../../../.artifacts/build-cache-recovery-038-v1/staging/result.json) [Capacity failure](../../../../.artifacts/integration-ver2-4-038-v1/root-verify.log)

This round adds no passing evidence for model quality, designated NVIDIA cross-device operation, exports of all real object types, clean installation, five first-time users, long tasks, or network faults. Full AC27, M6, M0—M6, and release remain pending; 037 and earlier records retain their original conclusions.
