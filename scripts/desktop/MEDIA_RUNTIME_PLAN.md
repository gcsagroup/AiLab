# 媒体内置运行时打包方案

结论：采用两个独立的固定入口运行时，分别封装当前已验证的 Diffusers Python 3.13 和 Kokoro Python 3.10；沿用现有控制层快照、启动授权、进程组取消和产物收集合同。当前阶段是打包设计与本机依赖盘点，尚未证明媒体运行时已随 App 可用。

## 当前证据

2026-09-10 对本机环境只读盘点，未执行 GPU 任务：

| 组合 | 当前 Python | site-packages 文件字节 | Mach-O 文件数 | 当前依赖锁 |
| --- | --- | ---: | ---: | --- |
| Diffusers 图片／视频 | 3.13.9 | 915,126,975 | 65 | `adapters/media/requirements.lock.txt` 已固定版本与 wheel SHA |
| Kokoro 中文配音 | 3.10.19 | 1,037,612,224 | 112 | `.artifacts/m4-media/tts/requirements.lock.txt` 含本机 wheel URL，需归一化 |

以上字节包含当前环境所有包与缓存，不能作为最终 App 体积。两个环境的第三方扩展没有非系统绝对 `LC_LOAD_DYLIB` 引用；部分库自身 `LC_ID_DYLIB` 仍是构建路径，打包后需统一重写并重新检查。Python Framework、资源和实际加载行为仍需验证。

FFmpeg 当前来自 `/opt/homebrew/bin`。递归盘点 FFmpeg、FFprobe 及非系统动态库共 19 个文件、38,450,464 字节；运行版为 8.1.1，当前构建配置包含 `--enable-gpl --enable-version3 --enable-libx264`。必须把实际二进制闭包、构建配置和许可一起纳入候选包，不能只复制两个命令。此方案未授权对外发布，也未把本地运行证据当作分发许可或公证结果。

盘点证据保存在 `.artifacts/desktop/media-packaging-review/{diffusers,kokoro,ffmpeg}.json`，对应脚本也保留在该目录，可重新执行。

## 已定位的搬移障碍

1. 两类配方分别明确检查 Python 3.13 和 3.10。将它们强行合成一个环境会改变已经验证的组合，应保留两个运行时。
2. `workers/media_worker.py:command_for` 当前用 `sys.executable -u image_cli.py/video_cli.py` 启动固定子进程。冻结后二进制不是任意脚本解释器，必须新增限定的图片／视频子命令入口，并维持同一进程组。
3. `video_cli.py` 通过 PATH 寻找 FFmpeg／FFprobe；图片与视频源码还通过 PATH 调用 `sysctl`。候选包需要自己的媒体命令目录，并只加入可信系统目录或改为 `/usr/sbin/sysctl`。
4. 配方会读取自身源码、控制层解析器和 lock 的摘要。冻结模块必须带同份真实源文件，不能用不存在的 `.py` 路径或开发目录替代。
5. TTS 当前按 `sysconfig` 的 site-packages 路径遍历依赖；在冻结环境可能得到空清单。需要基于包内实际 metadata 和固定运行时清单生成完整依赖身份，不能把空依赖列表视为已核验。
6. 当前控制层只支持媒体外部 Python 路径。必须新增包内二进制路由；不能把 `.artifacts` 环境写入 App 默认配置。
7. Tauri 资源通配复制会展开符号链接。现有 MLX 已通过还原 PyInstaller 链接并重签解决，同样步骤需覆盖两个媒体运行时与媒体工具目录。

## 最小改动范围

### 桌面打包

在 `scripts/desktop` 新增两个固定入口和一个按 profile 构建的打包脚本，生成 `resources/diffusers/ailab-diffusers` 与 `resources/kokoro/ailab-kokoro`。每个入口仅开放 `probe`、`preflight`、`launch`、`run`；Diffusers 另开放内部 `image-cli`、`video-cli`。没有任意脚本、`-c` 或用户传入模块入口。

`launch` 保留现有 `process.json`、控制器身份、快照摘要、`start-authorized.json` 协议。`media_worker` 的冻结分支改为同一二进制的限定子命令；外部 Python 分支仍使用现有脚本。图片与视频子进程继续继承控制层分配的独立进程组。

打包必须同时收集：

- 当前实际依赖的 metadata、Python Framework、动态模块和原生库；Diffusers 的 pipeline／模型动态导入，Torch 所需资源与符号链接。
- Kokoro／Misaki、中文分词与拼音词典资源、音频动态库，以及真实入口导入链涉及的包。固定模型权重由模型库管理，不随运行时重复打包。
- 与同次 stage 一致的 worker、adapter、受限媒体解析源码、依赖 lock 和入口源码摘要。
- Python 与全部实际随包依赖的许可证、NOTICE、包名版本和 wheel SHA。
- FFmpeg／FFprobe 动态库闭包，重写为包内相对加载路径，保存构建版本及所需许可文件。

两套媒体环境单独从完整哈希锁建立打包 venv，不修改现有 `.artifacts/m4-media` 验收环境。TTS 将本机 wheel URL 归一化为名称、版本、wheel 文件名和 SHA，保留原清单作历史证据。Diffusers Torch 必须沿用官方 wheel SHA，不能用同版本的其它构建替代。

`stage_control.py`、`build.sh`、`seal_runtime.py` 和 `verify_bundle.py` 扩展到这两个 profile。先签嵌套代码、还原链接和重算各 runtime manifest，最后签外层 App；每个 probe 返回 profile、Python／依赖版本、设备状态、源码清单摘要和 runtime manifest 摘要。

### 控制层与原生主进程

建议在 Settings 末尾新增 `bundled_media_worker`、`bundled_audio_worker` 和对应 CLI 参数。Rust 只传从 App 资源目录解析出的固定绝对二进制路径；WebView 不接收这些路径或控制 token。

媒体环境选择、检查和启动均按同一优先顺序：用户明确选择的外部 Python；否则使用当前已探测的包内运行时。内置缺失或探测失败应明确阻断，不退回开发目录、系统 Python 或静默更换执行设备。切换为内置时保留版本检查和活动任务保护。设置界面需要分别显示图片／视频与配音的真实探测状态；“高级选择 Python”保留为可选入口。

`Media.environment` 为包内运行时调用固定 `--mode probe`，身份绑定 binary、runtime manifest 与源码摘要；`Media.command` 的 preflight／run 和 Service 的 launch 必须同路由。复制 App 或切换恢复库后的新检查应重新生成运行身份；已有运行证据保持原快照。

## 步骤与验收

1. 固定源码与依赖 → 用完整哈希锁创建两个新的打包环境，验证实际版本和许可清单；不改已冻结模型、配方参数或历史证据。
2. 构建与签名 → 产生两个 onedir 运行时，检查所有 Mach-O 依赖与链接均在包内或系统路径；精确签名、源清单和运行时清单逐项通过。
3. 搬移后探测 → 将运行时复制到带空格的新目录，从空工作目录、`PATH=/usr/bin:/bin`、无项目 Python／模块路径启动 `probe` 与 preflight。用真实本地模型和受限输入核实失败与成功分支。
4. 搬移后真实执行 → Tiny-SD 512×512／20 步生成；图片 12 步 LoRA 训练与同基座适配器试用；SVD 14 帧／7 FPS 视频并通过随包 FFprobe 与解码；Kokoro 短中文生成 24 kHz 单声道 PCM WAV。全部由控制层协议授权启动，核实产物摘要、实际配置、原模型未改与进程回收。
5. 真实取消与异常 → 视频或图片运行中正常取消、控制器退出后子进程回收；错误 profile、任意脚本参数、变化的源／模型／产物、缺失动态资源均明确拒绝。无需重复改变质量阈值。
6. 最终 App → 用同一次 stage 构建全部 sidecar 与前端，验证签名及各 probe；在该确切 `.app` 的原生窗口检查内置能力，实际生成并预览媒体，退出回收后重启复读记录。

只有第 6 步完成后才能称为“媒体已内置到本次 App 且本机验证通过”。独立 Mac、Developer ID、公证、安装分发和公开发布仍是单独的验收事实。
