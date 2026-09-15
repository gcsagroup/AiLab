<!-- translation-navigation:start -->
[简体中文](../../../../scripts/desktop/MEDIA_RUNTIME_PLAN.md) · [繁體中文](../../../zh-TW/scripts/desktop/MEDIA_RUNTIME_PLAN.md) · [English](MEDIA_RUNTIME_PLAN.md)
<!-- translation-navigation:end -->

<a id="媒体内置运行时打包方案"></a>

# Bundled media runtime packaging plan

Conclusion: use two independent fixed-entry runtimes to package the currently verified Diffusers Python 3.13 and Kokoro Python 3.10 environments separately, retaining the existing control-layer snapshot, startup-authorization, process-group cancellation, and artifact-collection contracts. The current stage is packaging design and local dependency inventory; it has not established that the media runtimes are usable inside the App.

<a id="当前证据"></a>

## Current evidence

A read-only inventory of local environments on 2026-09-10 ran no GPU tasks:

| Combination | Current Python | site-packages file bytes | Mach-O file count | Current dependency lock |
| --- | --- | ---: | ---: | --- |
| Diffusers image/video | 3.13.9 | 915,126,975 | 65 | `adapters/media/requirements.lock.txt` pins versions and wheel SHAs |
| Kokoro Chinese voice-over | 3.10.19 | 1,037,612,224 | 112 | `.artifacts/m4-media/tts/requirements.lock.txt` contains local wheel URLs requiring normalization |

These byte counts include all packages and caches in the current environments and are not final App sizes. Third-party extensions in both environments have no non-system absolute `LC_LOAD_DYLIB` references. Some libraries' own `LC_ID_DYLIB` values still point to build paths and need consistent rewriting and rechecking after packaging. Python Framework, resources, and actual loading behavior still require verification.

FFmpeg currently comes from `/opt/homebrew/bin`. Recursive inventory of FFmpeg, FFprobe, and non-system dynamic libraries found 19 files totaling 38,450,464 bytes. Runtime version is 8.1.1; build configuration includes `--enable-gpl --enable-version3 --enable-libx264`. The candidate must include the actual binary dependency closure, build configuration, and licenses, not merely copy the two commands. This plan does not authorize external release, and local execution evidence is not distribution permission or a notarization result.

Inventory evidence is saved under `.artifacts/desktop/media-packaging-review/{diffusers,kokoro,ffmpeg}.json`; the corresponding scripts are retained there and can be rerun.

<a id="已定位的搬移障碍"></a>

## Identified relocation obstacles

1. The two recipes explicitly check Python 3.13 and 3.10 respectively. Forcing them into one environment would change verified combinations; retain two runtimes.
2. `workers/media_worker.py:command_for` currently starts fixed children with `sys.executable -u image_cli.py/video_cli.py`. A frozen binary is not an arbitrary script interpreter. Add restricted image/video subcommand entry points while retaining the same process group.
3. `video_cli.py` finds FFmpeg/FFprobe through PATH, and image/video source also invokes `sysctl` through PATH. The candidate needs its own media-command directory and only trusted system directories in the path, or an explicit `/usr/sbin/sysctl` call.
4. Recipes read digests of their source, control-layer parsers, and locks. Frozen modules must carry the same real source files; nonexistent `.py` paths or development directories are not substitutes.
5. TTS currently walks dependencies using the site-packages path from `sysconfig`, which may produce an empty manifest when frozen. Complete dependency identity must use actual bundled metadata and a fixed runtime manifest; an empty list is not verified dependencies.
6. The control layer currently supports only external media Python paths. Add bundled-binary routing; do not write `.artifacts` environments into App defaults.
7. Tauri resource-glob copying expands symlinks. MLX already addresses this by restoring PyInstaller links and signing again. Apply the same steps to both media runtimes and the media-tools directory.

<a id="最小改动范围"></a>

## Minimal change scope

<a id="桌面打包"></a>

### Desktop packaging

Add two fixed entry points and a profile-based packaging script under `scripts/desktop`, producing `resources/diffusers/ailab-diffusers` and `resources/kokoro/ailab-kokoro`. Each entry permits only `probe`, `preflight`, `launch`, and `run`; Diffusers additionally permits internal `image-cli` and `video-cli` commands. There is no arbitrary-script, `-c`, or user-supplied-module entry point.

`launch` retains the existing `process.json`, controller identity, snapshot digest, and `start-authorized.json` protocol. The frozen `media_worker` branch uses restricted subcommands of the same binary; the external-Python branch retains existing scripts. Image/video children continue inheriting the independent process group assigned by the control layer.

Packaging must collect:

- Metadata for actual dependencies, Python Framework, dynamic modules, and native libraries; Diffusers pipeline/model dynamic imports and Torch resources/symlinks.
- Kokoro/Misaki, Chinese tokenization and pinyin dictionaries, audio dynamic libraries, and packages in the real entry-import chain. Fixed model weights remain managed by the model library and are not duplicated in runtimes.
- Worker, adapter, restricted media-parser source, dependency locks, and entry-source digests matching the same staging run.
- Licenses, NOTICE files, package names/versions, and wheel SHAs for Python and every dependency actually bundled.
- The FFmpeg/FFprobe dynamic-library closure, rewritten to bundle-relative loading paths, with build version and required license files.

Create separate packaging venvs for both media environments from complete hash locks without modifying existing `.artifacts/m4-media` acceptance environments. Normalize TTS local wheel URLs into names, versions, wheel filenames, and SHA values, retaining the original manifest as historical evidence. Diffusers Torch must retain the official wheel SHA; a different same-version build is not interchangeable.

Extend `stage_control.py`, `build.sh`, `seal_runtime.py`, and `verify_bundle.py` for these two profiles. Sign nested code, restore links, and recalculate runtime manifests before signing the outer App. Each probe returns its profile, Python/dependency versions, device state, source-manifest digest, and runtime-manifest digest.

<a id="控制层与原生主进程"></a>

### Control layer and native main process

Add `bundled_media_worker`, `bundled_audio_worker`, and corresponding CLI options at the end of Settings. Rust passes only fixed absolute binary paths resolved from App resources; the WebView receives neither these paths nor the control token.

Media-environment selection, checks, and startup use the same priority: explicitly selected external Python, otherwise the currently probed bundled runtime. A missing or failed bundled runtime blocks clearly, without falling back to a development directory, system Python, or silently changing devices. Switching to bundled execution retains version checks and active-task protection. Settings must separately display real image/video and voice-over probe status, retaining “Advanced Python selection” as optional.

`Media.environment` invokes fixed `--mode probe` for bundled runtimes, binding identity to the binary, runtime manifest, and source digests. Preflight/run in `Media.command` and launch in Service must use the same route. Checks after copying the App or switching to a restored library regenerate runtime identity; existing execution evidence retains its original snapshot.

<a id="步骤与验收"></a>

## Steps and acceptance

1. Freeze source and dependencies → create two new packaging environments from complete hash locks; verify actual versions and license manifests without changing frozen models, recipe parameters, or historical evidence.
2. Build and sign → produce two onedir runtimes; check all Mach-O dependencies and links are within the bundle or system paths; exact signatures, source manifests, and runtime manifests must pass item by item.
3. Probe after relocation → copy runtimes to a new directory containing spaces and, with `PATH=/usr/bin:/bin` and no project Python/module paths, run `probe` and preflight from an empty working directory. Use real local models and restricted inputs to verify failure and success branches.
4. Real execution after relocation → Tiny-SD 512×512/20-step generation; image 12-step LoRA training and trial with the same base/adapter; SVD 14-frame/7-FPS video checked with bundled FFprobe and decoding; short Chinese Kokoro output as 24 kHz mono PCM WAV. All starts are authorized by the control-layer protocol; verify artifact digests, actual configuration, unchanged original models, and process reclamation.
5. Real cancellation and exceptions → normal cancellation during video or image execution and child reclamation after controller exit; explicitly reject wrong profiles, arbitrary-script arguments, changed source/models/artifacts, and missing dynamic resources. Quality thresholds need not be changed repeatedly.
6. Final App → build all sidecars and frontend from the same staging run; verify signatures and probes. Check bundled capabilities in that exact `.app` native window, actually generate and preview media, exit and reclaim processes, then restart and reread records.

Only after step 6 may the claim be made that “media is bundled in this App and locally verified.” Independent Macs, Developer ID, notarization, installation/distribution, and public release remain separate acceptance facts.
