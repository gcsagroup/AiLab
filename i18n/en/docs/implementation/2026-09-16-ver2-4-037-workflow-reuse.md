<a id="037-工作流明确复用失效与重开"></a>

# 037 workflow explicit reuse, invalidation, and reopening

The fixed company-signed Ver2.4（037）candidate completed limited native acceptance: explicitly reuse an image, video, and voice-over step by step, save the three works, mark downstream results stale after changing upstream input, and preserve the state across same-library reopening. No new model computation or training occurred; full M4, M0—M6, and release remain unpassed.

<a id="候选与独立资料"></a>

## Candidate and independent data

The fixed-path App signed by Global Cybersecurity Alliance Limited was used without rebuilding. Its binary digest is `59ce9d899488da868af0935f6dcb7f09749623deab250d55eeda7def4f0b2ce0`; the [existing package receipt](../../../../.artifacts/integration-ver2-4-037-v1/root-frozen-check.json) binds the actual candidate.

The packaged control service formally restored an existing media backup over real HTTP into an independent library, covering 733 files and 9345059951 bytes. Backup hashes matched before and after restoration; old works were selected from two earlier real media runs. No SQL connection was made to original working libraries, no models were modified, and no generation started. [Restore receipt](../../../../.artifacts/native-workflow-ver2-4-037-v1/restore-001/result.json)

<a id="原生操作与停机读回"></a>

## Native actions and stopped-state readback

A new workflow was created in the native UI. For each step, a work from the first run was selected, differences between original and current inputs were inspected, and explicit confirmation and acceptance preceded advancement. The image preview rendered; video and audio were not played in this run, so this is not motion-quality or human-listening acceptance. After saving, the UI confirmed that all three works were saved and explained that they were not combined into one file. [Saved-state view](../../../../.artifacts/native-workflow-ver2-4-037-v1/native-001/saved-three.png)

The image input was changed from a white cup to a green cup and saved as revision 2 without using the computation entry point. Video and audio became stale, while old acceptance records and the saved result were retained; the current workflow returned to the image step. After normal exit and reopening of the same candidate and independent library, the UI still showed revision 2 and stale downstream results, and the works list retained the originals. [Reopened view](../../../../.artifacts/native-workflow-ver2-4-037-v1/native-001/reopened-stale.png)

Stopped-state readback confirmed that all 507 existing resources were unchanged. There were 14 new resources, bringing the total to 521: 1 image material, 4 unexecuted tasks, 1 saved result, 1 workflow, and 7 step records. There were 9 commands, and the original 656 events remained unchanged; new model attempts and training runs were both 0. All three saved items are marked explicitly reused and not computed, with matching source works, attempts, and artifact hashes; actual hashes and sizes of 6 old media files in the restored library were checked again.

The workflow revision is 9, and the current image input is revision 2; the earlier saved result remains independently stored. Resource, command, event, project, and schema-version tables matched between the two stopped snapshots. The settings table changed only because viewing the works list changed navigation state; database file bytes were not identical. Both App processes exited normally with code 0, and the control service stopped. [Stopped-state verification receipt](../../../../.artifacts/native-workflow-ver2-4-037-v1/native-001/root-readback.json)

The original selector object and bytes were restored. Of 47 original protection records, 44 remained strictly unchanged; the exceptions were selector ctime and two startup diagnostics. Full trees of the 035, 036, and 037 market libraries and 12 source-model files were unchanged, with no new host source settings. The guard restored the selector and released its locks normally. Prototypes, historical failures, and original data were retained.

<a id="测试负例与剩余门槛"></a>

## Tests, negative results, and remaining gates

The frontend workflow passed 14 tests and control-service workflows passed 42 tests, retaining 1 existing warning; preparation and native-guard helpers passed 17 tests. These tests use fixtures and do not establish new model computation or native target-occupancy validation.

Preparation negatives are retained: the first full-tree comparison incorrectly included historical metadata and was rejected before startup; it was corrected against the frozen path, file, and directory contract with an added rejection test. The first frontend command omitted project configuration and failed environment setup; the configured project command passed. The stopped-state analysis script initially expected downstream acceptance records to be cleared; production invalidation logic and existing tests instead require retained records marked stale. The check was corrected accordingly and the original script retained. Production behavior and verification strength were unchanged.

During native interaction, pressing Return on the final selector submitted the valid creation form; the video menu remained open after selection and required confirmation. Work continued only after reading the UI state, and no model started. The tool reported that the App had quit after exit, consistent with process exit codes and stopped snapshots; this is not treated as a crash.

This round accepts only explicit reuse, stepwise advancement, saving, upstream invalidation, and persistence across reopening. Native target occupancy and atomicity remain unverified; image and video quality, human listening, NVIDIA, trusted cross-host execution, passing training/quantization, first-time users, and formal release gates remain open.
