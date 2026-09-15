# M2 运行预设与 KV 缓存只读核查

日期：2026-09-10。状态：源码核查通过；以下新增参数和预设尚未实现、尚未实机测量，不能称 M2 已通过。

目标是给当前 Apple 文本组合增加可解释、可回读的三个运行预设。保持同一模型、输入、上下文预算、输出上限和采样参数，再测缓存与分块本身的影响。本报告不更改执行器、控制服务、前端或当前媒体验收配方，不加载模型、不使用 GPU。

## 1. 当前事实与完成标准

- 当前独立环境：Python 3.13.9、MLX 0.32.2、MLX-LM 0.31.3。已读实际安装的 `generate.py`、`models/cache.py`、`models/base.py`、`models/qwen2.py` 和 `mlx.core.quantize` 文档，并核查官方同版本来源。
- 当前模型：Qwen2.5-0.5B-Instruct；原 BF16 和本地派生的 affine 4 bit/group 64 权重组合分别验证。模型配置是 24 层、14 个查询头、2 个 KV 头、隐藏维度 896，所以每头 64 维。
- 当前产品只开放单请求 Apple GPU 文本推理，输入与最大输出合计不超过 4096 token。模型配置的 32768 位置数不等于当前产品已开放预算。
- 当前 worker 只传输出上限和 sampler；缓存仍使用 MLX-LM 默认完整非量化 KV，Prefill 默认 2048。当前 preflight 尚无本报告新增字段，不能把本报告当成已实现能力。
- 完成标准：字段经过同一提交校验；预设应用前能看差异和取消；界面、已应用配置、快照与真实引擎参数一致；缓存实际类型/精度有回读；真实同输入对照与取消释放通过；未测组合拒绝；报告清楚区分缓存内存、模型权重、进程内存和任务耗时。

## 2. API 的真实语义

`stream_generate` 把以下参数传入 `generate_step`，该函数当前默认值如下。参数默认值和实现摘要见`.artifacts/m2-kv/source-audit-v1/source-check.json`。

| 参数 | 上游默认 | 真实作用与边界 |
| --- | --- | --- |
| `max_kv_size` | `None` | 非空时普通模型建立旋转 KV 窗口；会丢弃较早 token 的 KV，不是保留全文的内存容量限制 |
| `prompt_cache` | `None` | 可传缓存对象列表；一旦提供，`generate_step` 不再根据 `max_kv_size` 建缓存，不能默默依赖后者生效 |
| `prefill_step_size` | 2048 | 按 token 分块计算提示词；不改变输入/输出预算，也不等于并发或 batch size |
| `kv_bits` | `None` | 非空时将支持的缓存转换为 affine 量化存储；不修改模型权重 |
| `kv_group_size` | 64 | KV 最后一维的量化分组大小；需要整除该维度 |
| `quantized_kv_start` | 0 | 缓存 offset 达阈值后在一次 Prefill 分块或解码 step 结束处转换；不保证精确在阈值 token 处转换 |

关键限制：

1. `make_prompt_cache` 若发现模型自有 `make_cache()`，会优先调用它，忽略 `max_kv_size`；当前 Qwen2 没有自有方法，但不能把此行为推广给其它模型。
2. 默认创建的旋转缓存保留开头 4 个 token。`RotatingKVCache.to_quantized()` 明确抛 `NotImplementedError`，所以旋转窗口与 KV 量化组合必须在提交前拒绝。
3. 旋转缓存多 token 更新可临时达到 `max_size + S - 1`，首次还可直接保存整个输入分块。窗口数不代表运行峰值内存的硬上限。
4. 普通和量化 KV 按 256 token 扩容，实际已分配 token 数可能超过当前 offset。`nbytes` 是缓存数组存储大小，不是进程全部内存；扩容或量化转换时还可能同时存在旧/新数组。
5. MLX 0.32.2 affine 量化支持 group 32/64/128、bits 2/3/4/5/6/8；最后一维必须整除 group。当前 Qwen2 KV 维度为 64，因此 group 128 不兼容。首轮只测和开放 KV 4 bit/group 64，不因底层枚举更宽而承诺其它值。
6. 量化 Attention 走两个 `mx.quantized_matmul`，普通缓存走 `mx.fast.scaled_dot_product_attention`；两者数值及性能可能不同。量化 Attention 不支持 attention sinks；当前 Qwen2 没传 sinks。
7. `stream_generate` 的 draft-model 分支会移除 `max_kv_size`。当前产品未开放推测解码，继续拒绝该组合，避免声称窗口已生效。

来源：[MLX-LM 0.31.3 生成实现](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py)、[缓存实现](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/models/cache.py)、[Attention 实现](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/models/base.py)、[MLX 0.32.2 量化文档](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.quantize.html)。

## 3. 建议第一版合同

建议只给 `kind=language, operation=generate, engine=mlx, device_id=apple-gpu` 的当前两个权重组合扩展以下字段。保留原有 `seed/max_tokens/temperature/top_p`，不要让预设改变用户任务的输出上限。评测继续使用冻结的评测规则；训练和权重量化操作不接受推理缓存字段。

| 界面说明 | runtime 字段 | 首轮候选值 | 拒绝条件 |
| --- | --- | --- | --- |
| 缓存精度 | `kv_precision` | `auto`、`q4` | 未知值、其它模型/引擎/操作 |
| 提示词分块 | `prefill_step_size` | 512、2048、4096 token | 布尔值、非整数、0/负数、非候选值；不可静默修正 |
| 缓存窗口 | 暂不开放 | 显示“保留完整上下文” | 任意 `max_kv_size`/旋转请求 |
| 跨运行前缀复用 | 暂不开放 | `disabled`，每次建立新缓存 | 传入历史缓存路径/缓存 ID、请求开启共享复用 |

界面精度 `auto` 明确解释为“跟随当前模型计算精度，不量化 KV”；运行结果回读真实 dtype，不能仅根据权重配置推断。`q4` 明确解释为“4 bit 推理缓存；可能改变回答，模型权重保持原样”。group 64、量化起点 0 在第一版作为固定解析值保存，不增加没有实测需求的可编辑表单项。

若开发者选择直接暴露上游字段，仍需同样严格限制 `kv_bits ∈ {null, 4}`、`kv_group_size = 64`、`quantized_kv_start = 0`、`max_kv_size = null`；不要同时维护含义冲突的两套用户可编辑值。

三个预设必须版本化，并且绑定当前模型格式、模型结构、引擎版本和设备。最小映射如下；这是待测方案，不是当前可应用能力：

| 预设 | 缓存精度 | Prefill 分块 | 不变字段 | 说明 |
| --- | --- | --- | --- | --- |
| 模型默认 | auto | 2048 | 当前 max_tokens、temperature、top_p、seed、上下文预算 | 复现当前引擎缓存/分块默认；标题不能暗示重置生成参数为模型卡值 |
| 低内存 | q4 | 512 | 同左 | 尝试减小缓存与分块临时内存；可能改变回答和速度，待测后决定是否开放 |
| 低延迟 | auto | 4096 | 同左 | 尝试减少长提示词分块次数；短提示词可能没有差异，待测后决定是否开放 |

“模型默认”建议在差异预览旁标明“缓存与提示词分块恢复引擎默认”。如产品要让它同时重置全部生成参数，必须在差异中逐项明示，且低内存/低延迟的性能对照另行固定相同采样和输出上限。

只保存完整解析字段即可执行；附带 `preset_id/preset_version` 用于解释来源，不应让后端因同名 preset 自动改写快照。模板 ID 与字段冲突时拒绝；用户改任一模板字段后标为自定义。换模型/设备/格式时重新取能力，显示哪些字段失效、哪些值被保留，旧模板不能自动迁移。

## 4. 执行回读与证据

建议由 adapter 显式建立本次缓存列表，传给 `stream_generate`，在生成结束时检查该同一列表实际存储：层数、每层类名、offset、已分配 shape、普通 KV dtype 或量化 bits/group 与 scale/bias dtype、总 `nbytes`。量化函数会替换列表元素，因此读取结束后的同一列表即可确认 `QuantizedKVCache` 真实使用。保存摘要，不导出用户 KV 内容。

每次运行保存完整解析参数、模型/适配器 manifest、tokenizer/模板摘要、输入 token 摘要、引擎版本、执行器源码摘要、硬件、PID、实际输出 token 数和输出文本。按现有产品任务快照绑定，执行器复核实际配置，不仅显示 UI 标签。新增推理运行配方身份应与现有分词配方身份区分；当前分词配方不含所有 runtime 字段，不能单凭其 digest 证明缓存设置已被冻结。

性能字段至少分开：模型加载时间、从生成开始到首个 token 的耗时、Prefill 词元/秒、Decode 词元/秒、整个进程墙钟时间、MLX 本次生成峰值、进程 RSS 峰值、最终 KV 数组字节。记录 `mx.get_peak_memory()` 重置/采样时点，并保留包含模型加载的全流程基线；不要把生成阶段峰值与另一次全流程峰值直接比较。

当前单次新进程不跨任务保留前缀缓存。缓存命中率应记录为“不适用/未启用”，不能填 100%。后续若开放复用，身份还必须包含模型、适配器、tokenizer、模板、输入前缀、KV 精度、引擎缓存格式、隔离范围；多模态另加媒体顺序、内容摘要、处理器与预处理配方。

## 5. 可核算的量级，仅作理论参照

Qwen2.5-0.5B 的 BF16 KV 理论数据量：每 token 为 `2 × 24 × 2 × 64 × 2 = 12,288` 字节。4096 token 的 K/V 为 48 MiB。若 affine 4 bit、group 64，且 scale/bias 都为 2 字节，每 token 为 3456 字节，4096 token 为 13.5 MiB。差值 34.5 MiB，是 KV 数组理论差值，不是模型权重或整机内存节省量。

这些数不包含 256 token 扩容、临时激活、转换期间旧新缓存并存、allocator、模型权重、Python 进程和系统开销。量化权重模型的 KV 实际 dtype 还要运行回读；不能仅因为权重为 4 bit 就认定其 KV 也为 4 bit。

## 6. 分阶段真实验证矩阵

先等当前媒体 UI 使用完 GPU，再冻结测试方案与源码。不要在正在验收的媒体配方中途更改共享 worker。

1. **提交合同和能力负例 →** 默认缺省得到 auto/2048；布尔值/未知值/非法范围拒绝；train/evaluate/quantize 和媒体操作拒绝推理缓存字段；未验设备/模型拒绝；旋转+量化、历史 prompt-cache、draft-model 等未开放项拒绝。改变预设字段后不再宣称命中原模板。
2. **18 个基础功能样例 →** 两个权重格式 × 三个预设 × 短/中/长三个输入。用真实 tokenizer 将三档输入控制在约 64/1024/3584 token，三者输出上限统一 128、贪心采样、同一 seed；保存精确输入 token 数，不以字符数充数。全部可独立加载、生成有限输出、回读实际缓存类/精度/分块、没有裁剪和静默丢参。
3. **性能重复 →** 对上一步每组合在独立进程运行三次，预先固定交错顺序，额外暖机样例不计入统计；记录中位数和全体单次值，不能只挑最优。每个模型至少单列短/长输入结果。同 max_tokens 下若实际输出长度不同，TTFT 可直接比较；Decode 速度同时列实际 token 数，并只比较足够长度样例。
4. **效果归因 →** 长输入补测 q4/2048 与 auto/512 两个诊断组合，每模型三次，拆开缓存量化和分块各自影响。未达到可重复减少内存/首 token 耗时的模板不宣称有收益；可继续显示待验证或不可应用原因。
5. **文本正确性 →** 固定短问答、数字提取、JSON 结构、长文本前部/中部/尾部检索样例。auto 的不同分块先比较 token ID/文本；若不同则保留差异并做答案检查。q4 允许数值/文本不同，但必须报告各项正确率和回归，不能以没有 NaN 代替质量验收。
6. **缓存隔离与身份 →** A/B 两个独立任务同前缀不同结尾，各与冷启动自身基线对照；换模型/适配器/模板/精度后使用新缓存，记录每次缓存初始为空。媒体输入仍被当前文本能力拒绝；这证明当前路径没有错误复用，不证明多模态共享缓存已实现。
7. **取消和资源 →** 分别在长 Prefill、低内存 Decode 时取消，确认 worker/process group 回收且无 completed，随后新任务正常生成；缓存不得进入通用诊断包或被当作作品导出。
8. **普通用户 UI →** 逐个打开差异、取消、应用、提交、查看实际参数和配方重载；运行中不变快照；换模型/格式/设备后失效说明正确。Browser/Computer Use 实际操作，保存可见结果和 API/worker 证据。

完成 1—8 只能关闭 M2 的本机文本预设/缓存子项；NVIDIA、远程、其它模型、共享前缀缓存、多模态缓存、Prefill/Decode 分离和完整 M2 gate 仍需各自证据。

## 7. 本次核查的验证边界

本次已运行纯 Python AST/结构核查与理论字节计算，结果在 `.artifacts/m2-kv/source-audit-v1/source-check.json`；只读取依赖、当前模型配置和 worker，不执行模型。已确认上游参数默认值、旋转量化明确拒绝、Qwen2 结构与默认缓存路径。本文测试矩阵尚未执行，`source-check.json` 中 `gpu_execution` 和 `runtime_presets_implemented` 明确为 false。
