# 参考资料、来源边界与术语

版本：1.1 · 核查日期：2026-09-09；本轮补充审计涉及的 3 项官方资料，原 15 项保留历史核查记录。

## 1. 如何使用这些资料

产品结构来自用户确认的最后一版 Demo；上游资料用于核实技术概念、适配边界和候选实现路径。上游 README 宣称存在功能，不代表 GCSA-AiLab 已经集成或实机通过。

本页链接是动态文档或项目页面，实施时必须额外锁定具体版本、commit、模型 revision 和依赖。不要把 today／latest 等浮动状态写进不可变执行快照。

## 2. 官方参考资料

| 编号 | 官方资料 | 本套文档使用范围 | 实施时仍需确认 |
| --- | --- | --- | --- |
| SRC-01 | [MLX-LM](https://github.com/ml-explore/mlx-lm) | Apple 本地文本运行与训练候选、缓存和量化概念 | 版本、模型家族、训练方法、实际设备 |
| SRC-02 | [llama.cpp](https://github.com/ggml-org/llama.cpp) | 多硬件推理、GGUF 与后端构建边界 | 具体构建、后端、模型和算子 |
| SRC-03 | [vLLM 调优](https://docs.vllm.ai/en/latest/configuration/optimization/) | Prefill、调度和性能对照设计 | 版本默认值、模型架构、设备 |
| SRC-04 | [vLLM MTP](https://docs.vllm.ai/en/latest/features/speculative_decoding/mtp/) | MTP 依赖模型能力和配套实现 | 原生组件、目标版本、实际验收 |
| SRC-05 | [DFlash 官方项目](https://github.com/z-lab/dflash) | 目标／草稿配对、本地与服务路径 | 精确目标和草稿版本、思考模式、引擎 |
| SRC-06 | [Qwen3-4B 模型说明](https://huggingface.co/Qwen/Qwen3-4B) | 思考开关与模板控制的具体模型参考 | tokenizer、模板、服务参数映射 |
| SRC-07 | [TRL](https://huggingface.co/docs/trl/index) | SFT、DPO、GRPO 等后训练库候选 | 当前训练器 API、实验性状态、依赖 |
| SRC-08 | [PEFT](https://huggingface.co/docs/peft/index) | LoRA 与参数高效更新方式、适配器关系 | 模块选择、基座兼容、精度和训练方法 |
| SRC-09 | [Diffusers 内存优化](https://huggingface.co/docs/diffusers/optimization/memory) | VAE 和卸载优化的条件化设计 | 模型 pipeline、设备、速度与质量影响 |
| SRC-10 | [Core ML Typed Execution](https://apple.github.io/coremltools/docs-guides/source/typed-execution.html) | CPU／GPU／ANE 图执行与分配边界 | 产物、形状、系统版本、实际分配证据 |
| SRC-11 | [AMD ROCm 兼容矩阵](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html) | 设备、操作系统和软件组合核查 | 指定 GPU、驱动和库版本 |
| SRC-12 | [OpenVINO 设备与模式](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html) | Intel CPU／GPU／NPU 插件路径 | 插件、模型格式、设备代际 |
| SRC-13 | [Tauri 侧进程](https://v2.tauri.app/develop/sidecar/) | 桌面宿主与外部执行进程方案 | 平台打包、签名和生命周期 |
| SRC-14 | [FastAPI 生命周期](https://fastapi.tiangolo.com/advanced/events/) | 控制服务启动／退出设计参考 | 实际服务资源释放、进程管理 |
| SRC-15 | [SQLite WAL](https://www.sqlite.org/wal.html) | 本地元数据库的事务与并发设计参考 | 备份、检查点、迁移和文件一致性 |
| SRC-16 | [vLLM 前缀缓存设计](https://docs.vllm.ai/en/latest/design/prefix_caching/) | 媒体占位 token 与图片哈希、缓存隔离；支持 AUD-09 修订 | 当前引擎是否纳入全部媒体／处理器身份，应用层不能弱化 |
| SRC-17 | [TRL SFT Trainer](https://huggingface.co/docs/trl/sft_trainer) | assistant-only／completion-only、模板生成标记与 packing；支持 AUD-10 修订 | 具体 tokenizer、模板、labels、EOS/PAD、截断和拼接策略 |
| SRC-18 | [PyTorch 安全政策](https://github.com/pytorch/pytorch/security/policy) | 模型序列化、TorchScript 与不受信任文件加载；支持 AUD-11 修订 | 受限加载方式、允许格式、无不安全降级与执行权限 |

这些资料在编写时已访问核查。没有据此声称本项目支持任何未测试组合，也没有从中推导具体许可证的法律结论。

## 3. 尚未完成的来源核查

Heretic、Abliterix 和自定义图像网络在原型中保留了用户要求的产品入口。本轮没有对其具体源码仓库、依赖、算法和分发条件完成专项审查，因此文档只规定输入、输出、评测和待验证工作，不给出已集成或已可发布结论。

CosyVoice、Whisper、RVC、MusicGen、Wan、FLUX 等原型模型条目也需在各工作包中锁定具体版本和能力。名称存在于 Demo 不代表任一安装环境中的真实支持。AI Beauty 的代码复用范围需要在明确目录、版本和依赖后审查，本轮未复制其项目代码。

## 4. 训练术语

| 术语 | 中文说明 | 容易混淆的地方 |
| --- | --- | --- |
| SFT | 监督微调，学习给定输入与目标回答 | 与 LoRA 不是互斥选项；STF 在当前语境按 SFT 解释 |
| CPT | 继续预训练，使用连续语料适配领域 | 本文指 continued pretraining，不是所有库中同缩写方法 |
| DPO | 直接偏好优化，使用优选／劣选回答 | 不等同监督正确答案训练 |
| GRPO | 基于组内比较和奖励的策略优化 | 奖励上升不等于独立能力提高 |
| PPO | 近端策略优化，训练路径依赖奖励与策略配置 | 接口和实验状态随库版本变化 |
| LoRA | 用低秩适配器更新部分参数 | 通常还需要基座权重才能运行 |
| QLoRA | 在量化基座上进行适配器训练的一类方案 | 不等于所有量化模型都能训练 |
| 全参数更新 | 更新全部开放训练权重 | 资源需求与适配器训练不同 |
| 指定模块 | 只训练选定层或连接模块 | 必须记录解析后的真实模块名 |
| 梯度累积 | 多个微批次累积后进行优化更新 | 不增加单步实际 micro batch |
| 梯度检查点 | 用部分重算降低激活存储 | 与保存训练检查点不同 |
| 检查点 | 用于恢复的模型及训练状态 | 只有权重不一定能继续原训练轨迹 |
| 监督掩码／Loss Mask | 指定哪些 token 参与训练损失计算 | 与输入是否存在不同；有效监督数为零必须处理 |
| Packing | 将多个样本组织进训练序列 | 必须固定样本边界和注意力策略，不能隐式拼接改变目标 |
| 蒸馏 | 使用教师行为或分布训练学生 | 不是模型合并 |
| 模型合并 | 按规则组合兼容权重或适配器 | 结构相同不保证语义兼容 |
| 量化 | 降低权重或状态表示精度 | 体积变小不保证速度和质量都更好 |
| 转换 | 改变模型的运行表示／格式 | 文件生成成功不等于目标设备可执行 |

## 5. 推理与优化术语

| 术语 | 中文说明 | 产品表达要求 |
| --- | --- | --- |
| Token | 模型处理的离散单元 | 不能直接用中文字符数替代 |
| 上下文窗口 | 模型本次可处理的输入和输出范围 | 历史、模板与媒体也占预算 |
| 思考模式 | 模型和模板支持的推理行为模式 | 关闭计算与隐藏输出分开 |
| KV Cache | 缓存已有 token 的键值中间状态 | 与权重量化和前缀复用分开 |
| 前缀缓存 | 复用重复输入前缀对应计算 | 缓存范围与失效条件明确 |
| Prefill | 对输入进行初始计算 | 与后续逐 token 生成分别计时 |
| Decode | 生成后续输出 token | 并发吞吐与单请求速度分开 |
| Chunked Prefill | 对输入计算进行分块调度 | 不与任何分块参数简单等同 |
| 连续批处理 | 运行中不断调度多个请求 | 不等同训练批量 |
| Attention 后端 | 注意力计算的实现路径 | 由模型、引擎和设备决定 |
| CUDA Graph | 捕获和重放适用的 GPU 执行流程 | 需要预热、形状与内存条件 |
| 推测解码 | 草稿提出候选、目标模型验证 | 额外草稿可能没有速度收益 |
| MTP | 多 token 预测相关能力／组件 | 依赖目标模型与引擎支持 |
| DFlash | 使用块扩散草稿的推测解码方法 | 需匹配目标、草稿、模式和版本 |
| 接受率 | 草稿候选被目标验证接受的比例 | 分母与统计口径需写明 |
| CPU Offload | 将部分模型或状态移至 CPU 内存 | 可能降低显存但增加传输延迟 |
| VAE Tiling／Slicing | 图片解码的分块／分批处理 | 只对相应 pipeline 开放 |
| 张量并行 | 在多个设备间拆分张量计算 | 不等同数据并行，不直接扩大有效训练批量 |
| 实际配置 | 执行器最终采用的参数 | 与表单请求配置分别保存 |

## 6. 硬件与工程术语

| 术语 | 中文说明 | 边界 |
| --- | --- | --- |
| Metal／MPS | Apple GPU 相关运行接口／后端 | 不等于 ANE |
| MLX | Apple Silicon 模型计算框架 | 模型和方法需具体适配 |
| ANE | Apple Neural Engine | 允许参与不代表所有算子实际在其上运行 |
| Core ML | Apple 模型运行／转换生态中的接口 | 需对应格式产物和设备检查 |
| CUDA | NVIDIA 计算栈 | 受 GPU 架构、驱动和库版本约束 |
| ROCm／HIP | AMD 相关计算软件栈／编程接口 | 按具体兼容矩阵验证 |
| oneAPI／SYCL | Intel 等相关工具链／编程标准路径 | 本产品首批按 Intel GPU 组合验证 |
| OpenVINO | 模型优化和推理工具链 | CPU、GPU、NPU 插件分别验证 |
| Vulkan | 跨平台 GPU 接口 | 引擎构建和设备驱动必须支持 |
| 统一内存 | CPU／GPU 共享地址或物理资源体系中的内存 | 不直接等同独立显存容量 |
| Revision | 可固定的资源版本 | 不使用浮动 latest 作为证据 |
| Manifest | 文件及元信息清单 | 要与真实文件摘要一致 |
| Collection | 对已计算产物进行传输、校验与登记 | 不重新计算，补收记录与原尝试终态分开 |
| WorkflowRun | 工作流的一次具体执行 | 与可复用的工作流定义分开，步骤绑定输入版本 |
| WorkRevision | 人工编辑形成的作品版本 | 保留原输出与生成快照，不回写为原模型结果 |
| 阶段验证 | 当阶段可实际执行的退出检查 | 与最终 AC 追踪分开；M0 技术试验不依赖后期产品 |
| 幂等 | 重复请求不会重复产生同一副作用 | 必须包含内容冲突处理 |
| SSE | 服务端向客户端发送事件的连接方式 | 断线后靠事件游标恢复 |
| Sidecar | 与主应用配套的独立进程 | 独立启停、打包和故障管理 |
| ADR | 技术决策记录 | 记录依据、替代方案和结论 |

## 7. 资料更新规则

进入适配工作包时重新核对官方来源，固定版本并保存最小可复现测试。升级时按变更影响重新验证能力表、参数映射和报告。官方资料失效或内容变化时更新链接和说明，保留原验收使用的版本身份。
