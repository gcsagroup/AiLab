# M4 本机媒体执行器试验

这里是独立 CLI 与媒体执行桥的真实模型证据入口。图片选择 Tiny-SD + UNet LoRA；视频选择 SVD 图生视频；TTS 由独立 `tts_*` 执行器记录。执行桥已提供固定参数检查、来源绑定、真实事件、取消与产物封存。控制服务和 UI 的媒体路径由产品验收另行记录，不能把 CLI 或执行桥通过等同于 `GATE-M4` 通过。

## 冻结组合与证据

| 项目 | 固定选择 | 当前边界 |
| --- | --- | --- |
| 图片基座 | `segmind/tiny-sd`，revision `cad0bd7495fa6c4bcca01b19a723dc91627fe84f` | 官方约 1.062 GB；先验证受限读取，再转换 safetensors；只加载标准 Diffusers 类 |
| 图片推理 | PyTorch 2.14.0 / Diffusers 0.35.2 / Python 3.13 / MPS FP32 | 512×512、20 采样步、CFG 7.5、固定 CPU 随机发生器；不启用 MPS 算子回退 |
| 图片训练 | PEFT 0.18.1、UNet attention LoRA | rank/alpha 4、12 步、批量 1、AdamW 1e-4；VAE/CLIP/基座冻结；epsilon 去噪监督 |
| 图片数据 | 本次基座生成的 4 张商品茶壶图 | 来源明确标记为合成；不是外部语料，不证明业务数据权利或风格质量提升 |
| 短视频基座 | `stabilityai/stable-video-diffusion-img2vid`，revision `9cf024d5bfa8f56622af86c884f26a52f6676f2e` | 3 个 fp16 safetensors 权重合计 4,509,185,018 字节；公开无登录下载 |
| 短视频试验 | 同一 Diffusers/PyTorch 环境，MPS FP16 | 1024×576、14 帧、7 FPS、25 步；真实图片条件；独立 FFmpeg 解码；尚未实现视频训练 |

每次执行新建独立输出目录。生成结果保存 PNG 与浮点像素、实际参数、加载和生成耗时、进程身份、依赖版本与文件摘要。图片训练记录每步 loss/梯度、实际可训练张量、权重变化、冻结参数前后摘要及独立 safetensors LoRA。内存分别记录进程峰值 RSS 和结束时 MPS 驱动分配量；当前 MPS 接口没有独立峰值读数，不能把结束值当成显存峰值。

## 复跑

在项目根目录执行。所有权重和依赖都放在 `.artifacts/m4-media`，不读取 `~/Models`，也不修改已有文本执行器环境。

```sh
/opt/homebrew/bin/python3.13 -m venv .artifacts/m4-media/venv
.artifacts/m4-media/venv/bin/python -m pip install \
  --no-index --find-links .artifacts/m4-media/wheels/pytorch-official \
  --find-links .artifacts/m4-media/wheels/resolved \
  --require-hashes -r adapters/media/requirements.lock.txt

# 来源 API 必须对应冻结 revision；若 main 已改变，取固定版本 API，不篡改 SHA。
.artifacts/m4-media/venv/bin/python adapters/media/prepare_tiny_sd.py \
  --root .artifacts/m4-media/model --api .artifacts/m4-media/sources/tiny-sd-api.json
.artifacts/m4-media/venv/bin/python adapters/media/run_image_acceptance.py \
  --root .artifacts/m4-media --run-name acceptance-next

.artifacts/m4-media/venv/bin/python adapters/media/prepare_svd.py \
  --root .artifacts/m4-media/svd-model --api .artifacts/m4-media/sources/svd-api.json
.artifacts/m4-media/venv/bin/python adapters/media/video_cli.py \
  --model-root .artifacts/m4-media/svd-model \
  --input .artifacts/m4-media/acceptance-v2/base-blue_cup/image.png \
  --output .artifacts/m4-media/video-acceptance-next

/opt/homebrew/bin/python3.13 -m unittest discover -s tests/media -v
```

验收目录已存在时脚本拒绝覆盖。复跑需选择新的证据根目录，或逐个调用 `image_cli.py generate/train` 指向新的输出目录，不能删除旧证据后伪称首次通过。`run_image_acceptance.py` 在生成前冻结训练 seed 和两个独立评测样例；候选还会在另一个进程重新加载，同 seed 浮点像素最大误差上限为 `1e-5`。像素变化仅证明适配器生效，不是质量改进评分。

上面安装命令使用本次实际核验过的本地 wheel 档案。该 lock 专用于 macOS arm64 / Python 3.13；Torch 文件来自 PyTorch 官方索引，同版本 PyPI 文件摘要不同，不能混用。原始索引与下载来源快照在 `sources`，实际安装日志是 `logs/install-local-verified.log`。当前完整图片验收在 `acceptance-v2`；`acceptance-v1` 保留首次 JSON 写出失败的原始证据，不计作成功。

已验证结果见 [ACCEPTANCE.md](ACCEPTANCE.md)。两组图片与 LoRA 的功能通过；红壶提示生成了白壶，候选还有多余杯子和柄部异常，不能称为商品质量通过或训练改善。

大文件通过官方 HTTP Range 端点有界下载；逐段核对响应区间，最终对照官方 LFS SHA256 后才发布完成文件。中断时保留部分文件，受限加载或摘要失败不会降级为任意 pickle 读取。分段器的真实本地 HTTP 测试覆盖已下载前缀续传与损坏前缀拒绝。

## 许可和源代码依据

- [Tiny-SD 官方模型卡与固定源](https://huggingface.co/segmind/tiny-sd/tree/cad0bd7495fa6c4bcca01b19a723dc91627fe84f)标明 CreativeML OpenRAIL-M，并说明从 Realistic Vision V4.0 蒸馏。模型卡声明不能证明全部上游训练语料或输出权利；本试验不提供底模打包发布许可结论。
- [Diffusers 0.35.2 官方 LoRA 训练源码](https://github.com/huggingface/diffusers/blob/v0.35.2/examples/text_to_image/train_text_to_image_lora.py)提供冻结 VAE/CLIP/UNet、添加 attention LoRA、随机 timestep 去噪 MSE、保存适配器的依据。这里实现了固定单设备最小循环，并实际检查更新与重载，不直接运行仓库任意脚本。库代码是 Apache-2.0。
- [PyTorch 官方受限权重读取](https://docs.pytorch.org/docs/2.14/notes/serialization.html#torch-load-with-weights-only-true)及 [MPS 接口](https://docs.pytorch.org/docs/2.14/mps.html)用于加载和设备边界；使用 `weights_only=True` 失败时不扩大执行权限。实际 Torch wheel 来源为 PyTorch 官方索引，wheel SHA256 为 `caf6359d64c0074bcb9f8641a169239118c8165a0a0fef79110c72bfd6474bec`。
- [SVD 固定源许可证](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid/blob/9cf024d5bfa8f56622af86c884f26a52f6676f2e/LICENSE.md)含商业注册与年度收入条件。当前仅做本地评估测试，不将它声明成无条件可商用模型，也不把权重打入应用包。
- [SVD 官方模型卡](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid)说明它以图像为条件、原生 14 帧，不能用文本控制；模型可能产生静止或缓慢运动。接口不伪造 `prompt` 控制能力。

相应官方 API、许可证及读取过的上游源码快照保存在 `.artifacts/m4-media/sources`。Wan 1.3B 官方 Diffusers 版本此次未选：其源文件实际约 29 GB，且首组合是文生视频，超出本次总下载预算，也不能直接承担商品图输入。Kokoro 的包版本、中文前端、设备与声音输出证据见独立 TTS 说明。

## 尚未完成的产品验收

媒体模型准备、任务生命周期/恢复、候选质量准入、普通用户导出、两轮商品图→视频→配音工作流及市场返回仍须后续接入真实控制服务和 UI 验证。CLI 的独立 PNG/MP4 解码不能替代上述产品入口，也不能代替完整 `AC-27`。

## 媒体执行桥

控制侧使用同一图片／视频隔离 Python 分别调用 `adapters/media/preflight.py` 和 `workers/media_worker.py`，两者均接收 `--snapshot` 与 `--output-dir`。预检不写输出目录、不加载基座权重；它以固定官方文件卡、完整目录清单、实际 CLIP 分词和输入图片解码为依据。已有 LoRA 的形状用 meta 设备建立的标准 UNet 检查，不占用 GPU。`media_recipe_digest` 绑定实际配置、输入清单、执行器源码和依赖环境，独立于文本的分词配方字段。

| 操作 | 当前开放参数 | 输入 |
| --- | --- | --- |
| 图片生成 | `engine=diffusers`、`device_id=apple-gpu`、512×512、20 步、CFG 7.5、显式 32-bit 非负 seed | `input.prompt` 与可选 `negative_prompt`；可选已绑定完整清单的图片 LoRA |
| 图片 LoRA 训练 | 同设备、512×512、12 步、rank/alpha 4、学习率 1e-4 | `dataset_root_path` 的完整清单，`dataset_path` 必须指向其中 `dataset.json`；1—8 张有 caption/来源/SHA 的 RGB 原图 |
| 图片生成短视频 | 同设备、1024×576、25 步、14 帧、7 FPS | `input.material_id` 与顶层 `input_image_path`、完整 PNG 清单及摘要；当前 SVD 不接收文字控制 |

所有模型、输入图片、训练目录和可选适配器都必须绑定完整清单。目录额外文件、符号链接、未知参数、未验证组合、输出与输入重叠或覆盖旧输出均拒绝。图片可用干净导入目录 `.artifacts/m4-media/image-model-runtime`，其完整清单见旁边 `image-model-runtime-import.json`；数据示例为 `.artifacts/m4-media/image-dataset-runtime`，保持原先已说明的合成数据质量边界。

真实模型 CLI 与桥留在同一执行进程组。桥只把 CLI 已写出的训练 step 转为进度事件；生成阶段没有伪造百分比。完成后复核输入与执行配方，写 `effective-config.json`、`output-manifest.json` 和实际源码快照，向控制服务发送有 SHA256 的完成清单。主产物位于 `result/image.png`、`result/video.mp4` 或 `result/pytorch_lora_weights.safetensors`。当前媒体桥不支持训练暂停或检查点恢复。

`tests/media/run_real_bridge.py` 的本次代表性执行见 `.artifacts/m4-media/bridge-acceptance-v2/acceptance.json`：真实图片生成、12 步训练、新 LoRA 独立生成通过；视频完成真实第 1/25 步后取消，返回 130、没有完成事件、进程组已退出。此取消用例只证明停止边界，不计作成功视频或成功 UI 工作流。
