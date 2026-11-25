GCSA AI Lab — Windows UI 预览版 3.0.0

运行方法：双击同目录的 AiLab-UI.exe。
四类模型的“运行结果”中可查看“推理性能”。总耗时从提交起算，包含排队。展开“查看计时明细”可查看输入校验、执行器运行与结果登记耗时。语言生成显示首 token 延迟及执行器实测的预填充、解码速度。图片和视频显示执行器上报的采样阶段，视频生成速度按实际输出帧数计算。音频实时因子等于执行器运行耗时除以音频时长。历史运行保留当时采集的数据。
工作台的“检查本机环境”和侧栏的“设备与环境”均可启动本机检测。页面显示 GGML 识别的设备、可用内存和显存、模型磁盘余量及读写结果。展开“检测明细”可查看语言、图像、视频和音频执行器以及 FFmpeg 编码测试的结果。“刷新环境”会重新探测，“导出诊断摘要”可将当前结果保存为 JSON。具体模型所需的权重和配套组件在任务的“检查配置”中核对。
无需安装 Node.js、Python、Rust 或模型；界面可以离线打开。
请保留整个文件夹，勿单独移动 EXE，旁边的 DLL、resources 和 locales 是运行必需文件。

本版用途：浏览原项目的工作台、模型库、数据集市场、模型实验室、作品与素材；
查看弹窗，创建项目、编辑并保存本地任务草稿。
点击工作台的“准备官方语言模型”或模型库的“准备官方模型”。输入模型名称、发布者/仓库名或 HF 仓库网址，选择仓库和下载格式。GGUF 可选量化版本；分片自动组成一组。也可选“完整仓库（所有格式）”或“指定单个文件（任意格式）”。
确认许可、固定提交和文件大小后，点击“下载并核对所选文件”。可停止并在“模型准备记录”中续传。核对完成后，点击“加入当前项目模型库”查看保存位置。权重和配置均作为文件保存。
受限仓库需在 Hugging Face 获得授权后设置 HF_TOKEN 并重新打开程序。
在“模型准备记录”打开已登记的 Qwen GGUF，点击“用此模型开始试用”。也可从模型库点击“试用”。在原工作台输入内容，点击“检查配置”和“开始运行”。本地 C++ 执行器使用 ggml 和 libllama。CPU、Vulkan、KV 精度、采样、停止序列、分块与流式显示由现有执行设置控制。Qwen3 模板支持思考模式切换，Qwen2.5 使用模型默认。
Qwen3.5-4B 和 Gemma 4 E2B IT 既可处理文字，也能结合项目 PNG 回答问题。Gemma 还可读取 WAV。导入本地目录时，放入主 GGUF 和同版本的 mmproj GGUF；从模型准备入口选 GGUF 时自动加入配套投影。将 PNG 或 WAV 拖到“输入内容”可以导入并引用素材。也可以在第一行写“@素材 素材名称或编号”，换行写问题，同名素材请使用编号。
MiniMax-H3-Image 用于文生图，默认采用 6 步 Euler 采样和引导强度 1。MiniMax-H3 FL2VA 可按画面描述生成短片，可在“输入图片”中选择项目 PNG 作为首帧。两者使用各自的 VAE，共用保留 BF16 精度的 4B 文本编码器。可用显存少于 6 GiB 时，两种 MiniMax 配方均使用 CPU。选择这两个官方项目的 GGUF 格式时，清单会显示量化仓库和配套组件的下载地址与大小，下载后按固定版本的摘要核验。加入模型库时，应用在本机将配套权重转换为 GGUF。视频试用默认 4 步、22 帧、24 FPS，生成步数可调，配备音频 VAE 时会同时保存声音。
图片试用可使用完整 Tiny-SD GGUF；音频试用使用 audio.cpp 的多语种 Kokoro GGUF 与小北中文音色。视频和图片共用 stable-diffusion.cpp。选择 AnimateDiff 视频试用时，需要完整 SD 1.5 GGUF（含 CLIP 和 VAE）和 AnimateDiff SD 1.5 运动模块 GGUF。在“导入模型”选择只包含这两个 GGUF 的目录，再选当前项目中的 PNG。工作台使用所选种子和步数，将 512×288 的输入上下补边到 512×320，联合生成 14 帧，去除对齐补边后放大并编码为 1024×576、7 FPS 的 H.264 短片。运行记录与作品保存在当前项目。
开发环境可使用 second-state/stable-diffusion-v1-5-GGUF 的 stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf 作为基座。运动模块取自 guoyww/animatediff 的 v3_sd15_mm.safetensors（提交 9cfaa8a83b89eec48b4b0ee8c970e8b9f69f2089）。运行 node scripts/windows/prepare-animatediff.cjs v3_sd15_mm.safetensors motion.gguf 校验并离线转换，将两份 GGUF 放进同一目录。

预览草稿保存在当前 Windows 用户的：
%APPDATA%\GCSA-AiLab-UI-Preview
与完整版本的工作库隔离。

从源码重新构建：
1. 在项目根目录用 Node.js 24 执行 npm ci。
2. 新下载的源码不包含本地执行器。安装 Python 3.12+、WSL Ubuntu-24.04 及 g++-mingw-w64-x86-64-posix，执行 python scripts/windows/prepare-gguf.py 下载校验推理库并编译执行器。随后执行 npm run build:windows-ui。首次构建会下载 Electron Windows 运行时。
3. 输出位于上一级 release\GCSA-AiLab-Windows-UI。
4. 如需更改输出目录，先设置 AILAB_WINDOWS_OUTPUT_DIR 环境变量。

历史上游 UI 预览包（本次下载功能请使用当前源码的构建产物）：
https://github.com/gcsagroup/AiLab/releases/download/windows-ui-preview-20261020/GCSA-AiLab-Windows-UI-3.0-x64.zip
下载并解压后双击 AiLab-UI.exe。无需运行 GitHub Actions。
本分支已移除云端自动打包流程。

便携包 SHA-256：
8e26c0ab56363d8a1530ecc25910c714561b7699904c91bb4bc2ddde1d92287f
