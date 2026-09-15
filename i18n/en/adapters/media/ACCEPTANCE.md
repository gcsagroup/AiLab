<!-- translation-navigation:start -->
[简体中文](../../../../adapters/media/ACCEPTANCE.md) · [繁體中文](../../../zh-TW/adapters/media/ACCEPTANCE.md) · [English](ACCEPTANCE.md)
<!-- translation-navigation:end -->

<a id="m4-图片与视频独立执行证据"></a>

# M4 independent image and video execution evidence

2026-09-10, local Apple M5 Max with 128 GiB memory and macOS 26.6.2. Image generation and LoRA, SVD image-to-video, and independent reload passed functional checks. Image quality partly failed; video was almost static and did not pass visible-motion quality. This is not a `GATE-M4` product acceptance report.

<a id="图片实际生成训练与重载"></a>

## Images: actual generation, training, and reload

Evidence root: `.artifacts/m4-media/acceptance-v2`. Each result's `generation.json` records the fixed Tiny-SD revision, complete model-file digests, recipe, and environment. The frozen plan is `frozen-plan.json` and the summary is `acceptance.json`. Seeds for 4 training-source images, two independent evaluation prompt/seed groups, and the reload-error threshold were frozen before execution.

| Actual verification | Result |
| --- | --- |
| 4 training-source images + 2 base images + 2 LoRA-candidate images + 1 image reloaded in a second process | 9 PNGs at 512×512, all independently decoded with PIL |
| Image generation | 20 steps, CFG 7.5, MPS FP32; actual generation approximately 4.22—6.89 seconds per image, plus approximately 0.49—0.64 seconds for model loading |
| Real LoRA training | 4 explicitly labeled synthetic images, 12 steps, rank/alpha 4, AdamW 1e-4; actual training took 5.98 seconds |
| Trainable scope | 431,616 parameters in 144 tensors, all UNet attention LoRA; frozen base-parameter digests were identical before and after |
| Weight changes | All 144 LoRA tensors had finite changes; final weight SHA256 `e184bd60b03acf1b626bb81a54ad9b933dba658391e3a51f5b16617f68c67805` |
| Effect after independent loading | Under the same recipe, mean absolute pixel difference between base/candidate was 0.05412 for the red teapot and 0.02164 for the blue cup (pixel range 0—1) |
| Reloading the same adapter in a second independent process | Maximum floating-point pixel difference at the same seed was 0.0, below the preregistered 1e-5 threshold |
| Memory evidence | Each process recorded peak RSS (approximately 2.49—2.95 GiB) and MPS driver allocation at exit; no measured MPS peak was claimed |

The training report is `lora/training.json` and the artifact is `lora/pytorch_lora_weights.safetensors`. Training loss is denoising MSE at random timesteps; comparing the first and last loss does not establish improved quality. This experiment did not test training recovery.

The independent artifact audit `independent-artifact-audit.json` used the standard library, PIL, and NumPy without loading models or the original acceptance script. It checked all 9 PNGs, corresponding floating-point pixels, file digests, the same base identity, training-data and LoRA digests, executor-source digests, and 10 distinct generation/training process identities.

The executor and dependency lock used in this run were separately saved under `executors`. Entry-source SHA matches every generation/training report, allowing the actual version used in this run to be checked after later product-integration source changes.

<a id="图片质量有明确失败项"></a>

## Image quality: explicit failures

Both PNG groups were directly inspected; detailed observations are in `visual-review.json`. A blue ceramic cup is recognizable in both base and candidate images, with changes to its rim and body. The red-teapot prompt actually produced a white teapot against a red background; the candidate added a red cup and had an abnormal teapot-handle structure. Red coloration, single-object composition, and structural quality failed. “LoRA effective” here means that genuinely trained weights were reloaded and affected output, not that quality improved.

This was not a blind review and did not evaluate user business materials, brand consistency, broad seed coverage, text accuracy, or video continuity. All 4 training images came from the same base model and serve only as technical-experiment data with known provenance.

Training-source images were also inspected individually: 101/103 show red-and-white teapots; 102 has a handle resembling an extra spout; 104 includes a second small white teapot. Their color, structure, and object counts differ from the shared red-teapot caption, so they cannot pass business-training-data quality admission. The original frozen data and real training evidence are retained without retrospectively changing captions or selecting only successful samples.

<a id="保留的失败与修复"></a>

## Retained failures and fixes

The first `acceptance-v1` generated real PNGs, but the upstream scheduler's `lambda_min_clipped=-inf` could not be written as strict JSON, and report writing failed. That unbounded default is now explicitly recorded as an object with an added unit test. A new `acceptance-v2` completed successfully; old outputs were not overwritten, and v1 without a complete report is not treated as success evidence.

<a id="视频真实-svd独立重载与解码"></a>

## Video: real SVD, independent reload, and decoding

The entire fixed source of 4,509,208,405 bytes was downloaded. Three fp16 weights passed official LFS SHA256 checks and metadata passed Git blob-digest checks. The first video is in `.artifacts/m4-media/video-acceptance-v1`; a second Python process reloaded the same recipe in `video-acceptance-repeat-v1`. Input was the checked base blue-cup PNG, proportionally resized and padded to 1024×576. Full original-image and conditioning-image digests were frozen.

Both runs completed 25 steps of native SVD temporal generation, producing 14 frames at 7 FPS in a 2-second H.264 MP4. All floating-point frames were finite; actual FFprobe frame counting and independent full-frame FFmpeg decoding passed. Frozen parameters were identical in the two distinct processes. Maximum floating-point frame difference was 0.0 and both MP4 SHA256 values were `53913f16d15d779939c4579479362bc884fe67b8449972d752e67d1294c51cad`. Generation took 118.53 and 132.58 seconds. The first run may have overlapped device residency from paused text training; these are not exclusive-device performance benchmarks. MPS operator fallback was not enabled.

Direct inspection of the conditioning image and frames 0/6/13 showed the blue cup and background retained, with only extremely slight outline/texture jitter. The video is almost static. Real inference and media encoding therefore passed functionally, while visible-motion quality failed. Different frame SHAs cannot be used to promote camera or product motion. The summary is `.artifacts/m4-media/video-repeat-and-visual-review.json`. Each run retains `acceptance.json`, floating-point frames `pixels.npy`, 14 PNGs, a decoding manifest, and an executor-source snapshot.

<a id="范围与剩余验证"></a>

## Scope and remaining verification

9 representative automated tests passed for image/video configurations, digests, wrong bases, missing files, out-of-directory paths, refusal to overwrite old output, real local HTTP resume, and rejection of a bad final digest. Video training is unimplemented. Independent TTS results are covered by the `tts_*` executors in the same directory and their dedicated evidence.

<a id="媒体产品执行桥验证"></a>

## Media product execution-bridge verification

Added `workers/media_worker.py` and `adapters/media/preflight.py` without modifying the frozen image/video CLIs. 6 CPU bridge tests passed, covering exact parameters, complete input identity, rejection of extra hidden files/symlinks, output protection, real subprocess progress/failure, and reclamation after cancellation. All 4 actual input preflights passed: image generation, LoRA image generation, image training, and video generation. Preflight checks actual tokenization, files, decoding, and LoRA metadata shapes without loading base weights.

Real bridge acceptance is in `.artifacts/m4-media/bridge-acceptance-v2`. Image generation → 12-step training → independent generation with the new LoRA all succeeded, with all 12 real step events received. An independent test process checked every sealed-artifact digest. New image, LoRA, and candidate-image SHAs exactly matched their previously inspected counterparts. For video, same-group SIGTERM was sent after CLI logs showed actual completion of step 1/25. The bridge returned 130/CANCELLED, emitted no completion event, and the whole process group disappeared. All original bridge and model-child PIDs were subsequently confirmed absent.

Summaries, events, and process checks are in `acceptance.json`, each case's `*.events.jsonl`, and `independent-output-and-process-audit.json`. This is real execution-bridge lifecycle evidence. The control API and ordinary-user UI workflow require separate main-product acceptance; a cancelled video is not a successful video.

Market return, media capability registration, ordinary-user operations, pause/resume, and two end-to-end product-image → short-video → voice-over rounds with transfer and export require separate control-service/UI acceptance. Tiny-SD's OpenRAIL and distilled upstream provenance, and the SVD Community License's commercial terms, remain separate release limitations. No weights are packaged or published in this run.
