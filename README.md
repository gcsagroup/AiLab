# GCSA AI Lab

[简体中文](README.md) · [繁體中文](i18n/zh-TW/README.md) · [English](i18n/en/README.md) · [日本語](i18n/ja/README.md) · [한국어](i18n/ko/README.md) · [Français](i18n/fr/README.md) · [Português](i18n/pt/README.md)

GCSA AI Lab 是本地模型试用与作品管理桌面工作台。当前分支提供 Windows x64 技术预览，支持准备模型与素材、试用语言和多模态模型、生成图片与视频、生成或处理音频，并记录运行结果、性能数据和作品。

> 本页描述 2026-11-25 的 Windows 源码和本地构建进度。[2026-11-22 发布包](https://github.com/gcsagroup/AiLab/releases/tag/windows-ui-preview-20261122) 对应较早的代码快照，不含本页随后新增的所有功能。本次更新不自动改写该发布包。模型适配、模型下载和实际生成测试是不同阶段，具体结果见下文。

## 快速开始

1. 如使用现有发布包，下载并解压完整的 Windows 便携目录，双击 `AiLab-UI.exe`。便携包不需要另装 Node.js、Python 或 Rust。
2. 打开工作台的“检查本机环境”，查看 CPU、GGML 识别的设备、内存、磁盘和执行器检测结果。可刷新检测并导出 JSON 诊断摘要。
3. 在模型准备入口下载并登记模型，或导入满足要求的本地模型及配套组件。程序包不包含模型权重。
4. 选择语言、图片、视频或音频试用，填写输入和参数，点击“检查配置”并开始运行。结果页显示输出、耗时和适用的性能指标。
5. 在工作台的“新建工作流”中配置图片 → 视频 → 配音，视频描述和配音文字均可编辑。各步骤可检查结果并保存作品。

源码构建方法见[从源码准备和构建](#从源码准备和构建)，操作细节见 [Windows 使用说明](scripts/windows/README-Windows.txt)。

## 当前功能

| 部分 | 实现情况 |
| --- | --- |
| 桌面 UI | Electron Windows 界面，包含工作台、模型库、数据集市场、模型实验室、作品与素材、任务草稿及运行历史。 |
| 模型准备 | 搜索 Hugging Face 仓库、选择文件、下载与续传、摘要校验、登记本地模型，并按已配置的配方准备所需组件。 |
| 本机环境 | 实际枚举 GGML 设备，检查执行器启动、FFmpeg 视频编码和音频转换，测试模型目录读写并导出诊断。 |
| 模型试用 | 语言与多模态理解、图片生成、视频生成、音频任务均接入运行入口、模型预检、队列、结果和作品保存。 |
| 工作流 | 图片生成 → 视频生成 → 配音。步骤使用项目素材，允许修改视频描述与配音文字，保留步骤和运行记录。 |
| 运行性能 | 总耗时包含排队。语言显示首 token 延迟、预填充与解码速度；图片和视频显示可取得的采样及 VAE 阶段，视频按实际输出帧数计算帧率；音频显示时长和实时因子。历史记录显示当时保存的数据。 |

## 已接入的推理架构与模型

下列名称表示项目中的架构识别或配方接入。不同权重、组件、量化和设备需要分别验证，模型搜索结果也需要通过导入与运行前检查。运行方式以任务的预检结果为准。

| 类型 | 入口与主要模型 | 输入与输出 |
| --- | --- | --- |
| 语言和多模态 | llama.cpp b12648 的 GGUF 架构识别，包含 Qwen2.5、Qwen3、Qwen3.5、Gemma、Llama、DeepSeek 等；部分组合需要匹配的投影器。另有针对特定模型的布局转换和专用图执行器。 | 文字，以及相应模型支持的图片或音频素材，输出文字或相应任务结果。 |
| 图片 | Tiny-SD、MiniMax-H3-Image，以及 Flux、Qwen Image、SD3、PixArt、Z-Image、Chroma 等配方。 | 根据模型配方使用提示词或参考图片，输出 PNG。 |
| 视频 | AnimateDiff SD 1.5、MiniMax-H3 FL2VA，以及 Hunyuan Video、LingBot Video、LTX-2、LTX-2.5、Wan 2.2 配方。 | 根据配方使用提示词及可能需要的首帧，输出 MP4。 |
| 音频 | Kokoro，以及 Qwen3-TTS、F5-TTS、CosyVoice3、Fish Audio、VibeVoice、ACE-Step、MiniMax Music 等配方和部分语音识别、检测任务。 | 根据模型使用文字或音频素材，输出 WAV、文字或检测结果。 |

### 完整架构和配方清单

语言侧的架构注册表包含 178 个模型架构条目，另列投影器和无构造器条目。清单包含生成、编码、决策及其他专用架构，支持方式和所需组件由 [架构注册表](apps/windows-ui/hf/llama-architectures.json) 和 [运行分派逻辑](apps/windows-ui/hf/llama-model.cjs) 决定。

<details>
<summary>展开语言模型架构标识</summary>

`llama`、`llama4`、`deci`、`falcon`、`grok`、`gpt2`、`gptneox`、`mpt`、`baichuan`、`starcoder`、`refact`、`bert`、`modern-bert`、`nomic-bert`、`nomic-bert-moe`、`neo-bert`、`jina-bert-v2`、`jina-bert-v3`、`eurobert`、`bloom`、`stablelm`、`qwen`、`qwen2`、`qwen2moe`、`qwen2vl`、`sensenova_u1`、`qwen3`、`flint`、`qwen3moe`、`clover_moe`、`qwen3next`、`qwen3vl`、`qwen3vlmoe`、`qwen35`、`qwen35moe`、`clef`、`vllm-decision2`、`qwen4exp`、`phi2`、`phi3`、`phimoe`、`plamo`、`plamo2`、`plamo3`、`codeshell`、`orion`、`internlm2`、`minicpm`、`minicpm3`、`gemma`、`gemma2`、`gemma3`、`gemma3n`、`gemma4`、`gemma4-assistant`、`gemma-embedding`、`gemma-embedding2`、`starcoder2`、`mamba`、`mamba2`、`maple`、`jamba`、`falcon-h1`、`xverse`、`command-r`、`cohere2`、`cohere2moe`、`dbrx`、`olmo`、`olmo2`、`olmoe`、`muse-glimmer`、`muse-spark`、`openelm`、`arctic`、`deepseek`、`deepseek2`、`deepseek2-ocr`、`deepseek32`、`deepseek4`、`deepseek41`、`xing4_0`、`chatglm`、`glm4`、`glm4moe`、`glm-dsa`、`bitnet`、`t5`、`t5encoder`、`jais`、`jais2`、`nemotron`、`nemotron_h`、`nemotron_h_moe`、`metis16`、`exaone`、`exaone4`、`exaone-moe`、`rwkv6`、`rwkv6qwen2`、`rwkv7`、`arwkv7`、`granite`、`granitemoe`、`granitehybrid`、`graniteswitch`、`granite_swa`、`chameleon`、`wavtokenizer-dec`、`plm`、`bailingmoe`、`bailingmoe2`、`bailingmoe3`、`dots1`、`dots3note`、`arcee`、`afmoe`、`laguna`、`ernie4_5`、`ernie4_5-moe`、`hunyuan-moe`、`hunyuan-dense`、`hunyuan_vl`、`hy_v3`、`hy_v4`、`smollm3`、`gpt-oss`、`lfm2`、`lfm2moe`、`lfm3`、`zaya1`、`dream`、`smallthinker`、`llada`、`llada-moe`、`seed_oss`、`grovemoe`、`apertus`、`minimax-01`、`hrm_text`、`limite`、`minimax-m2`、`minimax-m3`、`cogvlm`、`rnd1`、`pangu-embedded`、`mistral3`、`eagle3`、`dflash`、`mistral4`、`mistral-large4`、`paddleocr`、`mimo2`、`step35`、`spark2_5`、`llama-embed`、`maincoder`、`maion-coder`、`kimi-linear`、`kimi-k3`、`kimi-k31`、`glm5-next`、`talkie`、`mellum`、`nanbeige`、`qwen3tts`、`pockettts`、`moshi`、`zonos3`、`kokoro`、`tiny-voca`、`k2-horizon`、`beam`、`kolibri1`、`ricursive`、`inkling2`、`inkling2_loop`、`domynedge`

</details>

图片、视频和音频配方分别有 41、6、194 条。不同量化版本或配套文件可能分别占一条。完整固定版本、文件名称、大小和组件见 [生成模型配方](apps/windows-ui/hf/generation-packages.json)。

<details>
<summary>展开图片配方家族</summary>

`boogu_image`、`chroma`、`chroma_radiance`、`ernie_image`、`fibo2`、`flux2`、`flux3`、`hidream_o1_image`、`ideogram4`、`krea2`、`lens`、`llada_image`、`longcat_image`、`mage_flow`、`ming_image`、`minit2i`、`moss_image`、`ovis_image`、`pid`、`pixart`、`qwen_image`、`qwen_image_2.1`、`sensenova_u1`、`sd3`、`z_image_l2p`、`z_image_controlnet`、`flux1`、`p_h3_image`、`sefi_image`

</details>

<details>
<summary>展开视频配方家族</summary>

`hunyuan_video`、`lingbot_video`、`ltx2`、`wan22_ti2v_5b`、`wan22_t2v_a14b`、`ltx25`

</details>

<details>
<summary>展开音频配方家族</summary>

`audio8_tts`、`auk`、`breeze_tts`、`chatterbox`、`chatterbox_turbo`、`confucius4_tts`、`cosyvoice3`、`dots_tts`、`dramabox`、`echo_tts`、`f5_tts`、`firered_audio`、`fireredtts3`、`fish_audio`、`fish_drama3`、`glm_tts`、`higgs_audio_tts`、`index_tts2`、`irodori_tts`、`kitten_tts2`、`kugelaudio`、`lfm2_audio`、`lfm3_audio`、`magpie_tts`、`maya1`、`ming3_tts`、`miotts`、`moss_tts_local`、`m5_tts`、`moss_tts_v15`、`moss_ttsd`、`neutts`、`omnivoice`、`outetts`、`plapre`、`pocket_tts`、`qwen3_tts`、`sopro_tts`、`tiny_voca`、`vibevoice`、`vieneu_v3_turbo`、`voxcpm2`、`voxmel_tts`、`voxtral_tts`、`xtts_v2`、`zipvoice`、`zonos2`、`zonos3`、`ming3_audio`、`controlfoley`、`ace_step`、`heartmula`、`midashenglm_gen`、`minimax_h3`、`minimax_music3`、`moss_soundeffect`、`mulacover`、`soulx_singer`、`vevo2`、`yue2`、`mira_tts`

</details>

Tiny-SD 试用使用完整 GGUF。MiniMax-H3-Image 还需要匹配的文本编码器和图片 VAE。AnimateDiff 需要包含 CLIP 和 VAE 的 SD 1.5 GGUF 及匹配的运动模块。MiniMax-H3 FL2VA 使用文本编码器和视频 VAE，可按配方带音频 VAE。具体文件与输入要求由模型准备和预检核对。

## 推理架构与底层加速

AiLab 负责界面、模型和素材管理、任务编排、模型与组件检查、运行参数、计时和结果保存。模型计算由随包的执行器和底层推理库完成。

| 组件 | 接入方式 |
| --- | --- |
| llama.cpp b12648 / GGML | AiLab 的 C++ 执行器及 llama-server 执行语言和多模态相关任务，提供 CPU、Vulkan、采样、KV 精度、停止序列、预填充分块与流式输出等设置。 |
| stable-diffusion.cpp `532d2c1` / `0d71f96` | AiLab 图像执行器或对应 CLI 配方执行图片和视频生成，按模型使用 CPU 或 Vulkan、内存映射及 VAE 分块等设置。 |
| audio.cpp | 随包的 0.9.5、0.9.6 和 F5 配方执行器处理音频；实际可用任务取决于模型家族与组件。 |
| FFmpeg | 处理输入素材，并将生成帧或音频编码为可播放媒体。 |

本机任务通过队列执行。文字执行器跨任务不共享前缀缓存。硬件、模型组件和运行参数会影响速度与内存需求。

## 开发进度记录

以下时间为北京时间。日期级记录汇总当日工作，标注具体时间的记录依据构建或提交记录。

| 时间 | 完成事项与验证 |
| --- | --- |
| 2026-11-22 | 提交 Windows 本地 GGUF 试用入口，接入模型准备、推理执行和作品保存，并发布当日 Windows 预览包。 |
| 2026-11-24 | 整理语言、图片、视频和音频模型的架构识别与 CPU 试用记录，补充模型配方和运行适配。各架构和权重的验证范围各不相同。 |
| 2026-11-25 | 完善图片 → 视频 → 配音工作流，加入视频提示词编辑，并验证工作流的结果传递。 |
| 2026-11-25 | 实现 Windows 本机环境检测、设备刷新和诊断摘要导出。本机 12 项环境检测通过。 |
| 2026-11-25 | 为四类模型试用加入耗时和适用的速度指标。Qwen2.5、Tiny-SD、AnimateDiff、Kokoro 的指定组合完成运行验证，历史记录可读取已保存的性能数据。 |
| 2026-11-25 18:17 | 构建新的 Windows x64 便携包，完成界面冒烟检查和压缩包读取验证。 |
| 2026-11-25 18:18 后 | 提交源码与 README 到 windows-ui-preview 分支，提交号 15dcd79。 |

## 近期验证与使用边界

2026-11-25 在 Windows、Ryzen 7 4800H 和 GTX 1650 Ti 的本机上，检查到 GGML CPU 与 Vulkan 设备，12 项环境检查通过。Qwen2.5、Tiny-SD、AnimateDiff 和 Kokoro 的指定组合完成过试用，四类运行记录的性能数据显示及历史读取已验证。一次 CPU AnimateDiff 生成 14 帧的试用约 9 分 24 秒，其中 VAE 解码约 8 分 14 秒。测试值对应当时的硬件、模型和参数。

窗口中对远程执行目标、市场数据源管理、整库备份恢复和存储清理标明了 Windows 尚未接入。Windows 训练执行器尚未接入。模型适配清单并不表示每种权重和量化都已完成端到端验证。

## 从源码准备和构建

仓库不包含预编译推理运行库或模型权重。Windows x64 开发环境需要 Node.js、Python、WSL 与编译工具，准备运行库时需要网络。

```powershell
npm ci
python scripts/windows/prepare-gguf.py
npm run build:windows-ui
```

脚本生成的便携目录包含 `AiLab-UI.exe`、Electron 依赖、各推理运行库及使用说明。保留完整目录后运行。模型需要另行下载或导入。

## 原项目历史记录

以下保留原 README 对其他版本和平台的历史说明。版本号、验证结果与功能范围均对应各自记录的环境，并不代表 Windows 预览版已经实现或验证。

当前版本为 **Ver3.0（070），技术预览**。Ver2.7（054）已在原生 App 中通过 SSH 隧道验证 Qwen2.5-0.5B-Instruct 的 Jetson Orin 生成、两步 LoRA 训练、产物回收，以及同份适配器在 Apple GPU 上运行。此验证限于指定模型和环境，不代表质量提升；直接 HTTPS 部署、干净安装、首次用户测试及正式发行验收仍未完成。当前没有已验收的正式安装包或自动更新渠道。 055 修复上传断线后的原因提示与终态说明，并在原生 App 中验证中断、核实和重新传输；未重跑 054 的完整跨设备模型流程。

模型实验室新增可执行的 LoRA 带权合并、本地离线回答蒸馏，以及 Core ML、ONNX、TorchScript 转换。合并与学生仅支持未量化 Qwen2.5-0.5B，教师可选本地 0.5B 或 7B。每项都经过真实计算、独立加载与生成、保存及导出文件校验；输入文件保持。产物仍为实验模型，固定样例通过不代表整体质量提升。

070 同一公司签名 App 已原生完成合并、4 步蒸馏、Core ML 转换与独立试用（输出 9），并在 41/200 步取消蒸馏；冷重开保留新模型和取消记录。最终 App 内置运行库分别完成三种格式转换、独立试用和导出校验。另用 7B 教师训练 0.5B 学生，三题对照中教师 3/3、学生前后均 2/3，没有证明质量提升。日常库保持并恢复。控制层全量 1175 项、前端 720 项、Rust 88 项测试通过；新增及备份／划分相关 87 项复验通过。Rust 另有 3 项忽略，打包测试 43 项通过、1 项跳过。

操作：在模型实验室选择“合并”“蒸馏”或“格式转换”，填写后创建任务，再检查并明确开始。合并选择原始基座与匹配 LoRA，比例为 0.01—1；蒸馏先在数据页按来源组划分，选择单轮训练子集（1—64 条），本地教师生成回答，学生实际训练 1—200 步。完成后保存实验模型，在模型库独立试用或导出；执行报告包含来源、参数、教师回答和对照结果。

当前限制：三种新格式固定 CPU／FP32／128 词元上下文、无 KV 缓存；Core ML 不代表 GPU 或 ANE 已验收，TorchScript 使用上游已弃用的导出接口。输入和最大输出合计超限时拒绝，不截断。尚未完成多模型权重合并、在线或 KL 蒸馏、蒸馏检查点续训、多架构与动态形状转换，以及跨平台目标设备验收。Heretic／Abliterix 无入口或执行器；其他训练方法、推测解码、硬件扩展、独立业务质量、五名真实用户、干净安装和正式发行仍未完成，M5／M6 未关闭。

066 修复导入检查后的焦点丢失，保留重新检查入口，并关联文件错误说明。同一公司签名 App 实际验证错误文件拒绝、重新检查、中文含空格路径、长名称数据导入和冷重开保留。714 项前端测试与 12 项版本测试通过；另复跑 17 项针对性测试和 37 项能力／训练／量化合同测试。原有 2,465 条资源、1,321 份登记产物及 3,056 份原始文件核对保持，日常库恢复。窄窗口矩阵和读屏帮助文本仍未完成，不能据此判定完整无障碍或整包验收通过。指定 NVIDIA 设备的真实环境探测已恢复可用；这不代表 066 的远端业务验收完成。

065 修复响应记录的计数核对与阈值解释。同一公司签名 App 完成模型库、设备窗口打开／关闭、已有任务及预设预览五类原生操作，共 10 次预热、100 次正式样本。四份记录的 558 个输入均与浏览器计数一致；所选五类的 330 个输入中，6 个有时长，324 个按实时 Event Timing 交付契约及完整计数解释为低于上报阈值，未填零。计入 8 毫秒量化余量后，每类输入到下一次渲染的 p95 上界为 24 毫秒；精确 p95 未知，不包含后续异步业务完成时间。系统未提供额外丢弃诊断，保留为空；计数不符、未匹配或明确丢弃时不判通过。707 项前端、24 项计时分析与 12 项版本测试通过。2,465 条历史资源、1,321 份登记产物和 3,056 份原始文件保持，日常库已恢复，未运行模型、训练或远端任务。063 的启动与外观证据仍属旧版；完整普通交互、065 整包、真实 NVIDIA、质量、五名用户、干净安装与正式发行仍未完成。


同一 063 公司签名 App 在 M5 Max／128 GB Mac 上完成 20 次独立进程冷启动，保留系统缓存和 2,465 条历史资源。20 次模型库正文均在 3 秒内实际可见，含原生打开和截图开销的观测上界为 0.79–1.25 秒。数据与环境完整就绪另计：中位数 3.65 秒、p95 3.71 秒、最长 3.79 秒，20 次均超过 3 秒，全部样本保留。每轮正常退出且无残留进程；全部业务表、1,321 份登记产物、3,056 份原始文件核对保持，日常库已恢复。71 项启动相关测试通过，未重建 App，没有模型运行、训练或远端执行。此结果不覆盖整机冷启动、干净安装或普通交互延迟；M6 与正式发行仍未完成。

063 另完成 320／360／736／1024 四种窗口宽度的深浅色代表页面检查，并在 320 宽度深色窗口以键盘完成新建文本试用、检查、一次真实生成、保存及重开；中文内容通过原生粘贴输入，不代表中文输入法验收。21 项相关测试通过，2,454 条历史资源、1,315 份历史产物及 3,056 份原始文件核对保持，日常库和系统外观已恢复；仅启动诊断记录正常更新。没有训练或远端运行，App 未重建。全部关键状态、普通交互 p95、新成员独立复跑和其余最终候选、质量、真实 NVIDIA、五名用户及发行门槛仍未完成。

Ver2.8（063）在“设备与环境 → 诊断与支持”增加手动响应记录。开始后可关闭窗口，操作模型库、设备窗口、已有任务或预设预览，再返回停止并查看结果。记录仅在本机内存保留操作类别与时间，不包含输入正文、任务名称或文件路径；可选中结果自行保存，退出或切换工作库后清空。系统不支持计时时明确提示；缺失记录不按零延迟处理，此功能不会自动判定性能验收通过。

此前响应记录检查中，同一 063 公司签名 App 完成 110 次原生界面操作，含 10 次预热和 100 次正式样本，界面结果均符合预期。330 个输入事件仅上报 5 条 16 毫秒记录，其余 325 条保持缺失，不能判定 p95≤300 毫秒。704 项前端、14 项计时分析及 12 项版本测试通过。没有新增模型运行或训练，2,454 条历史资源与数据库各表保持，日常库已恢复。062 的启动和业务证据单独保留；063 整包复验、真实 NVIDIA、质量达标、五名用户、干净安装及正式发行仍未完成。

062 修复服务重连后当前任务误显示“尚未开始”的问题。同一公司签名 App 在真实输出后中断服务，重连直接恢复停止待核实的只读任务；核实原进程退出后，新尝试成功，旧终态保持。另验存储拒写后只补收：一次计算、两次补收，没有重复计算或重复产物。本轮六次真实生成覆盖文本、图片、视频与语音，三项媒体保存、三包导出共九个清单文件及完整媒体解码通过，冷启动保留结果。738 项相关测试通过；未训练，2,312 条历史资源、3,056 个原始文件及日常业务库保持。各版证据分别留存，干净安装、完整最终候选适用验收、真实 NVIDIA、质量达标、五名用户与正式发行仍未完成。

同一 062 公司签名 App 另完成四次真实文本运行：正常取消、停止请求未确认时保持只读、原生确认强制停止、执行器异常退出，以及随后新尝试成功并保存。冷启动重开四条记录，旧终态和输出保持；2,437 条旧资源、3,056 个原始文件及上一轮 79 份产物核对通过，日常库恢复。10 项生命周期回归测试通过，未训练、未重建 App。成功生成未按提示词仅返回指定短语，原内容偏差保留，不计质量通过。指定设备的 SSH 端口可达，但会话被关闭，未执行远端命令。完整生命周期、最终候选远端验收、模型质量、五名用户、干净安装及正式发行仍未完成。

同一 062 公司签名 App 在 M5 Max／128 GB Mac 上完成 20 次独立进程冷启动，保留系统缓存与 2,454 条历史资源。20 次主窗口正文均在 3 秒内实际可见；含原生打开和截图开销的时间上界为 0.78–1.77 秒。数据与环境完整就绪另计，中位数 3.71 秒、p95 4.26 秒、最长 5.93 秒，保留全部样本。每轮正常退出且无残留进程，历史数据库、资产与日常库核对保持；71 项启动相关测试通过，没有新增模型运行或训练。此结果不覆盖整机冷启动、干净安装或常规交互延迟，M6 与正式发行仍未完成。

数据导入错误现在显示原文件行号，JSON 格式错误和非文本消息使用明确的中文提示。同一公司签名 060 App 复验五类模型拒绝和四类数据拒绝；059 停止的官方下载在 060 续传完成，校验后明确登记并完成一次真实短生成，缺失权重也得到真实加载失败终态。来源组划分的 CPU 结果与参考逐字节一致，生成独立训练／留出版本；零监督、重复提示词及修改长度后的过期检查均拒绝。86 项控制、95 项前端、70 项 CPU 监督及 33 项划分合同测试通过。未启动训练，原工作库已恢复。此结果限于所选本机文本功能；独立进程并非操作系统沙箱，完整配方、设备、质量、用户和发行验收仍未完成。

修正历史建议误报“任务尚未执行”的提示，改为引导查看实际运行记录。058 的五次真实本机建议覆盖四个开放字段，显式应用／撤销、过期冲突及真实提交后拒绝均已验证；另一次目标文本运行用于提交边界。059 同一公司签名 App 复验历史提示、提交拒绝，以及一次新的真实建议与应用／撤销。32 项控制层测试和修复后 13 项前端测试通过，原工作库恢复，没有训练。各版本证据分别保留；远程建议未开放，模型质量、完整设备矩阵、真实用户及正式发行仍未完成。

修正任务尚在后页时误报“没有任务记录”的提示；加载后可查看已有评测，确实无记录时才显示空态。76 项相关前端测试通过。同一公司签名 058 App 验证两项目语言／图片草稿重开、四类入口和已有结果返回，并实测图片运行中切换项目后结果仍归属原项目。原工作库恢复，没有训练。旧质量失败结论保持；完整设备矩阵、五名用户、干净安装与正式发行仍未完成。

057 现已在同一公司签名 App 完成两轮图片→视频→中文配音，六份独立导出通过完整解码并在外部应用打开／播放。原生覆盖中断后的待核实提示、核实退出、修改输入重做及上游变更失效；同包正式接口覆盖真实取消和自然完成时的双请求推进，仅成功推进一次，重复请求保持结果。42 项工作流回归通过；首次验收脚本失败及其取消记录保留。没有训练。以上仅证明指定组合功能，不代表媒体质量、完整 M4／M6、五名用户或正式发行通过。

当前按内部试用推进。055 已补验历史备份恢复、升级与回退、导出后独立使用、键盘任务和指定媒体生成。业务材料评审与五名真实用户测试仍保留待验，未用模拟结果代替。

2026-10-13 质量补充：现有 Qwen2.5-7B-Instruct 已在独立本地推理中完成 50 条合成运维记录的基线及两轮提示词试验，未进行训练。新提示词改善了部分字段，但仍有事实遗漏、状态错误，修正轮还被原文误导附注诱导而伪造操作与恢复；两轮均未采用。这些样本已用于调试，未经独立业务复核，不能作为盲测或生产质量通过的证据。

- 文字生成、SFT + LoRA 微调及基线／候选评测。
- 图片生成与实验性图片 LoRA，视频生成、配音和转写入口。视频和音频训练尚未开放。
- 数据导入、来源组划分、运行历史、作品修订、导出和备份恢复。

可运行范围取决于具体模型、设备、引擎和精度，开始前以配置检查结果为准。现有质量实验仍有失败项，不能把训练完成当作质量合格。文档提供七种语言；这不代表应用界面支持七种语言。

[用户手册](docs/USER_GUIDE.md) · [更新记录](CHANGELOG.md) · [GitHub](https://github.com/gcsagroup/AiLab)
