<a id="导出目录项完整性修复"></a>

# Export directory-entry integrity fix

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
