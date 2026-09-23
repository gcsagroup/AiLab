<a id="最后确认的原型参考"></a>

# Last confirmed prototype reference

This preserves the final Demo, build assets, and tests unchanged; the original directory remains. File identities are listed in [manifest.json](../../../../prototype/reference-2026-09-09/manifest.json). The real application lives in `apps/desktop`; this directory is excluded from production packages. This prototype simulates the interface and performs no real training or inference.

The prototype contains 6 known behavioral issues and 1 additional recipe-traceability semantic issue. The checker's assertions reproduce these issues. A successful exit means they still exist, not that they have been fixed.

<a id="从仓库根目录复跑"></a>

## Replay from the repository root

Node.js and Python 3 are required; the steps below use only their standard libraries. Verify the manifest's byte counts and hashes, then copy the files to a separate temporary directory for execution. The checker writes its report there, leaving the fixed reference unchanged. Stop and retain the output if any step fails; do not treat subsequent results as passing.

```sh
node --version
python3 --version
ailab_replay_dir="$(mktemp -d "${TMPDIR:-/tmp}/ailab-reference.XXXXXX")"
python3 - "$ailab_replay_dir" <<'PYTHON'
from pathlib import Path
import hashlib, json, shutil, sys
source = Path("prototype/reference-2026-09-09")
target = Path(sys.argv[1])
manifest = json.loads((source / "manifest.json").read_text())
for item in manifest["files"]:
    data = (source / item["path"]).read_bytes()
    assert len(data) == item["bytes"], item["path"]
    assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
    shutil.copy2(source / item["path"], target / item["path"])
print("Verified files:", len(manifest["files"]))
print("Replay directory:", target)
PYTHON
node "$ailab_replay_dir/test-ailab-unified.cjs"
node "$ailab_replay_dir/test-ailab-runtime.cjs"
node "$ailab_replay_dir/audit-prototype-counterexamples.cjs"
```

This replay used Node.js `v24.14.0`: all 13 manifest files matched, the representative checks reported 42 passing groups, and the runtime-configuration checks reported 17 passing groups. The checker reported `A-01` through `A-07` and saved `audit-prototype-counterexamples.json` in the temporary directory. These are known-issue observations for the historical prototype, not production App test results.

<a id="界面与结论边界"></a>

## Interface and conclusion boundaries

The fixed interface file is [ailab-unified.html](../../../../prototype/reference-2026-09-09/ailab-unified.html). An evaluator must actually open it in a browser and inspect the workbench, category switching, and runtime settings. The scripts above use state functions and a minimal DOM substitute; they do not inspect real layout, keyboard focus, playback, or screenshots.

In this round, the browser tool refused to open the local file under its URL policy, so visual revalidation was not completed. No alternate entry point was used to bypass the restriction. A new member must still independently follow these instructions and record the version, results, and difficulties to contribute new-member evidence for AC-23. Developer replay does not replace that requirement or real-user acceptance under AC-25.

Building overwrites HTML. If `build-ailab-unified.py` is needed, run it only in the temporary copy above and retain the original hashes and report. Product rules, including separation of human revisions from original generation recipes, follow the specifications listed in the [documentation index](../../docs/README.md).
