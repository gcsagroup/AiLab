<a id="导出目录项完整性修复"></a>

# Export directory-entry integrity fix

The fixed company-signed 039 candidate includes the export directory-entry fix. Its actual packaged service rejected 4 invalid entry types, recovered a valid interrupted package, and completed a fresh export. Native inspection of failed and successful records, normal exit, and reopening of the formally restored library passed. No new models ran; full AC27, M6, M0—M6, and release remain incomplete.

039 passed checks of the complete package, frozen source, actual compiled contents, and 7 company-signed targets. Packaged tests preserve 4 rejection records, 1 recovered original package, and 1 successful fresh export, totaling 6 export attempts. Faults were registration rejections in an independent test library, and the synthetic files cannot run a model. Original packages, links, and source files remain unchanged, with records preserved after formal backup and restoration. [Package verification](../../../../.artifacts/integration-ver2-4-039-resume-20260920-v1/root-frozen-check.json) [Packaged results](../../../../.artifacts/packaged-export-tree-ver2-4-039-resume-20260920-v1/run-001/result.json)

The same candidate opened the formally restored library twice, inspected the manifest-link failure and fresh successful export, and exited normally. Only UI settings changed after the first shutdown; the second database snapshot was entirely identical. Checks passed for 47 protected records against the new September 20 stopped baseline and for 12 model source files, and original library selection was restored. The native UI did not trigger these faults; full-readiness records do not establish initial-visibility performance acceptance. [Native and protection verification](../../../../.artifacts/packaged-export-tree-ver2-4-039-resume-20260920-v1/root-readback.json)

Capacity handling archived and verified regenerable staging data and retained restoration tools before reclaiming the original staging directories. An idle check initially blocked because another project was running tests; no archiving or removal occurred until that process ended. The blocked attempt is preserved, and neither capacity nor idle gates were lowered. [Archive results](../../../../.artifacts/build-cache-recovery-039-v1/staging/result.json) [Idle blocker](../../../../.artifacts/build-cache-recovery-039-v1/idle-blocker.json)

Work resumed on September 20 with approximately 209 GiB free before startup. The current stopped state differs from the original September 16 baseline in 3 records: the original A main database and two startup records. Both the differences and original records are preserved; this does not claim that the original library was unchanged across the intervening period. Historical empty-library sidecars remain untouched, and no SQL connection was made to the original libraries. [Baseline provenance and differences](../../../../.artifacts/integration-ver2-4-039-resume-20260920-v1/baseline-lineage.json)

The frontend build cache directory no longer exists, so the first verification failed and was preserved. Frontend evidence carries forward the earlier direct embedded-byte verification, strictly bound to identical current full-executable and JS hashes; embedded resources were not decompressed again. The actual control PYZ, frozen sources, complete package, and 7 signature targets were verified again. [Initial verification failure](../../../../.artifacts/integration-ver2-4-039-resume-20260920-v1/root-verify.log)

The independent review passed 18 targeted tests in this round. Source tests cover payload symlinks and ordinary empty directories; packaged tests do not include those two controls. Source tests are not presented as packaged observations. Faults were controlled SQLite registration rejections, not operating-system crashes, and these checks do not prove operating-system isolation against concurrent same-user file replacement. [Independent review](../../../../.artifacts/review039-recovery-20260920-v1/review.md)

The first native invocation was rejected before launch because the guard used a relative script path. The App had not started. That failure, selector restoration, and normal guard exit are preserved; both subsequent acceptance rounds used absolute paths. Host full readiness took approximately 8.25 and 7.74 seconds, with external observations of 8.51 and 7.81 seconds. These do not establish the 20-launch, 3-second initial-visibility requirement. [Prelaunch rejection](../../../../.artifacts/packaged-export-tree-ver2-4-039-resume-20260920-v1/native-001/prelaunch-failure.json)

The following records retain their state when written.

An export-recovery check against AC-27 and the operations specification found that the fixed Ver2.4（038） candidate can still accept a package containing symbolic links incorrectly. Source is now fixed and related regressions passed; it has not yet been included in a new signed candidate, so source results do not establish packaged or native acceptance of the fix. The existing 038 manifest-identity acceptance retains its original scope; full M6, M0—M6, and release remain incomplete.

<a id="重现与原因"></a>

## Reproduction and cause

The previous check enumerated only regular files, overlooking extra dangling links, directory symbolic links, and named pipes. Reading the manifest also failed to reject a symbolic link for the manifest itself. In tests using actual files and database shutdown and reopening, these 4 negative cases incorrectly recovered successfully; 3 controls passed for an intact package, an ordinary empty directory, and existing rejection of payload-file links. [Before-fix record](../../../../.artifacts/export-tree-integrity-source-v1/red.log)

A separate HTTP negative case ran through the actual service inside fixed 038. A single export registration rejection was injected only into a fresh test library. After normal shutdown, the packaged manifest was replaced with a link to an identical manifest in the test directory, then the service restarted and reconciled it. The old candidate incorrectly returned success and a usable path; this negative evidence is retained. The fault is controlled registration rejection, not an operating-system process crash; the synthetic model files cannot run a model, and no native UI actions were performed. [Packaged negative case](../../../../.artifacts/export-tree-integrity-source-v1/packaged038-negative-001/result.json)

<a id="最小修复与验证"></a>

## Minimal fix and verification

Verification now traverses all directory entries first without following symbolic links, allowing only regular files and real directories before checking the file set, manifest identity, and individual hashes. Special entries are rejected before reading the manifest; scan errors remain failures. Valid directories remain allowed, with no modification of the original package, recopying, or model execution. This check does not claim operating-system isolation against concurrent tampering by the same user.

All 7 targeted tests passed, covering manifest links, payload links, dangling links, directory links, named pipes, intact packages, and ordinary empty directories. Each reconciles after actual shutdown and reopening; the same idempotency key returns the original result, files and links remain unchanged, and task and attempt counts do not increase. Export, backup and restoration, work revisions, and split-dataset export regressions passed 186 tests, retaining 2 existing dependency warnings. [Targeted results](../../../../.artifacts/export-tree-integrity-source-v1/green.log) [Combined regression](../../../../.artifacts/export-tree-integrity-source-v1/regression.log)

<a id="证据边界与后续"></a>

## Evidence boundaries and follow-up

After the packaged negative case, all 47 original protected records remained unchanged and every control service started in this round stopped normally. No model executed, and no SQL connection was made to the original user library. Existing subagents cannot execute because of usage limits; root-agent review does not count as independent review. The next candidate still needs a company-signed build, actual packaged rejection and valid-recovery checks, and corresponding native verification; this record does not advance full AC27 or M6 status.
