# 本地 MLX 文本适配器

**Apple 配置回归完成（2026-09-29）**：同一 Ver2.6（049）的 7B 原权重、普通 KV 缓存，在默认、512 分块和低延迟三种设置下完成 18 次公开题测试；算术、提取、结构化输出及长输入头部／中部／尾部提取均正确，各为 6/6，未发现新增退化。独立审计确认原始答案、评分、空缓存、完整包及受保护数据一致，自有工作进程已退出。此前性能矩阵经两段完成，共 136 次模型计算成功、45 次设备忙拒绝，另保留 2 次睡眠导致的检查过期拒绝；不代表无中断或独占主机稳定性通过，也不证明所有配置均加速。公开题回归不替代业务留出，LoRA 的 31/32 结果仍不满足格式全对要求；完整 AC24、原生界面与 M6 仍未完成。

[配置质量审计（本地证据）](../../.artifacts/apple-preset-quality049-20260928/root-readback.json)

2026-09-10：Apple M5 Max 的真实推理、SFT + LoRA 参数更新、来源身份核对、独立重载、MLX 4-bit 量化导出、取消与错误组合检查已通过。此处是 Apple 部分的技术试验与执行器，不代表 TV-01 的 NVIDIA 部分、TV-03 跨端回程、模型质量准入或完整训练产品验收通过。

## 已验证组合

- macOS 26.6.2、Apple M5 Max、128 GiB 统一内存；实际 MLX 默认设备为 `Device(gpu, 0)`，未使用或声称 ANE。
- Python 3.13.9、MLX 0.32.2、MLX-LM 0.31.3；全部安装版本见 `requirements.lock.txt`。
- 官方 `Qwen/Qwen2.5-0.5B-Instruct`，revision `7ae557604adf67be50417f59c2c2f167def9a775`，未量化 BF16 权重；许可证文件随模型保留。
- 权重 SHA-256：`fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe`；大小 988,097,824 字节。
- 源模型只读使用；模型、tokenizer、模板、环境、实际参数和每个输出文件的摘要均写入执行证据。

源码结构检查支持 `qwen2` 的 0.5B（896 隐藏维度、24 层）和 7B（3584 隐藏维度、28 层）固定组合。7B 只接受未量化基座，权重量化与 q4 KV 缓存尚未开放；0.5B 保留原有量化范围。结构匹配不等于所有同结构衍生权重或业务质量通过。上述历史记录描述首个组合，新增源码实测边界见文末。

## 准备与复跑

在项目根目录运行；命令中的相对路径均以该目录为准。现有环境和公开试验模型已准备好，无需再次下载。

```sh
python3.13 -m venv adapters/mlx_text/.venv
adapters/mlx_text/.venv/bin/python -m pip install -r adapters/mlx_text/requirements.lock.txt
adapters/mlx_text/.venv/bin/python adapters/mlx_text/prepare_model.py
adapters/mlx_text/.venv/bin/python -m pytest tests/mlx -q
adapters/mlx_text/.venv/bin/python tests/mlx/run_real_probe.py --evidence .artifacts/m0-mlx/new-run
adapters/mlx_text/.venv/bin/python tests/mlx/run_m3_probe.py --evidence .artifacts/m0-mlx/new-m3-run
```

最后一个证据目录必须不存在。`prepare_model.py --verify-only` 可只核对当前模型。下载只请求固定 revision 的 9 个公开文件，写入项目 `.artifacts/models/Qwen2.5-0.5B-Instruct`；不修改 `/Users/lazy/Models` 或用户原有 Hugging Face 模型缓存。此前 Xet 下载与短超时 HTTP 失败均未被当作成功，最终通过 HTTP 重试下载并核对权重摘要。

## 控制服务合同

Python：`adapters/mlx_text/.venv/bin/python`，控制端必须解析并使用绝对路径。

```sh
adapters/mlx_text/.venv/bin/python adapters/mlx_text/preflight.py --snapshot SNAPSHOT --output-dir EMPTY_OUTPUT_DIR
adapters/mlx_text/.venv/bin/python workers/mlx_worker.py --snapshot SNAPSHOT --output-dir EMPTY_OUTPUT_DIR
```

快照字段：`attempt_id`、`operation`、`model_path`、`input`、`runtime`。必须提供完整的 `model_manifest=[{path,size,sha256},...]`、`model_manifest_digest`；训练额外提供单个 `messages` JSONL 的绝对 `dataset_path`、单文件 `dataset_manifest` 与 `dataset_manifest_digest`。清单摘要采用 UTF-8、键排序、无多余空格、非 ASCII 字符不转义的标准 JSON 序列化再计算 SHA-256，与控制服务一致；路径为相对路径。

执行前后均重核对输入文件集合、大小和摘要，新增未登记权重也会阻断。正式 worker 还必须提供由预检查返回的 `tokenization_recipe_digest`，加载后再次核对 tokenizer、模板、监督实现摘要。缺少身份字段即拒绝执行，不存在“未传清单就默认可信”的模式；直接运行的开发试验同样显式固定清单并先做预检查。历史 `run-20260910-01` 至 `03` 的旧快照仅作历史证据，不能直接交给强化后的 worker。

生成可在快照顶层提供 `adapter_path`，同时必须提供 `adapter_manifest`、`adapter_manifest_digest` 与 `adapter_training_recipe_digest`。只接受本执行器输出且基座完整清单／模板／来源训练分词配方／模块／参数形状匹配的适配器，执行前后均检查完整 adapter 文件集。训练生成的 `adapter_config.json` 保存 `base_input_manifest_digest` 和 `training_recipe_digest`；缺少这两个来源字段的历史产物不能直接进入生产执行器，不从目录名猜测来源。训练和量化不接受适配器，不支持增量续训或在量化基座上挂载 LoRA。

预检查只加载真实 tokenizer；返回单个 JSON，`can_submit`、`blocking`、`effective_config`、`tokenization_recipe_digest`、`recipe`、`check_report`。成功退出 0，阻断退出 1。该脚本不创建输出目录，不加载模型权重；候选检查会读取 safetensors 参数头和文件摘要。控制端须把配方摘要与当前数据、参数和文件身份一起绑定到提交检查。

执行器 stdout 只输出逐行 JSON；库日志去 stderr。事件 `type` 为 `phase`、`token`、`metric`、`completed`、`error`。`token` 含 `text`、`token_id`、`generation_tokens`；`completed` 含输出目录内相对路径、SHA-256、`media_type` 与实际 `effective_config`。推导后的 `effective_config` 是只读记录，不能原样作为下次可写 `runtime`。

执行器在进程内禁止 Hugging Face 自动联网，模型必须是明确本地路径。输出目录必须为空，不允许符号链接跳转或与模型／数据重叠。执行失败可以留下诊断或中间文件，控制端只能在收到完成事件、进程正常退出且逐个摘要核对后登记正式产物。

SIGTERM／SIGINT 设置取消请求，在实际计算同步点检查，退出 130 且不发送 `completed`。可提供 `AILAB_CONTROL_PID`；它必须等于实际父进程。父控制进程消失后执行器会自行停止，底层算子不返回时最多再等 10 秒退出自身，不给其他进程发信号。资源互斥与队列由控制服务负责。

## 可写参数

生成：`engine=mlx`、`device_id=apple-gpu`、`seed`（0—2³²−1）、`max_tokens`（1—2048，默认 128）、`temperature`（0—2，默认 0）、`top_p`（0.01—1，默认 1）。提示词最多 16,000 字符，真实分词后的输入与最大输出合计最多 4096。temperature=0 使用贪心选择，此时 top_p 不参与选择；实际缓存使用 MLX 默认非量化完整 KV。以上为当前适配器的保守产品限制，不是硬件理论上限。

训练固定项：`training_type=sft`、`update_method=lora`、`recipe_id=qwen25-assistant-only-v1`、`batch_size=1`、`gradient_accumulation=1`、`optimizer=adamw`、`weight_decay=0`、`lora_dropout=0`。

训练可调项：`steps`（1—200，默认 4）、`learning_rate`（1e-7—0.01，默认 1e-4）、`max_seq_length`（32—2048，默认 512）、`lora_rank`（1—32，默认 4）、`lora_alpha`（1—64，默认 8）、`num_layers`（末尾 1—28 层，0.5B 最多 24 层，默认 2）与 `seed`。目标模块固定为 `self_attn.q_proj`、`self_attn.v_proj`。MLX scale 显式取 `alpha / rank`。

AdamW 显式固定 betas=[0.9,0.999]、eps=1e-8、bias_correction=true；恒定学习率，无 warmup／梯度裁剪。源 BF16 权重冻结，LoRA 参数 FP32；数据按文件顺序循环，seed 控制 LoRA 初始化。每步产出真实损失与监督词元数，结束保存 LoRA 文件与参数变化。未开放中间检查点恢复、断点续训、全参数、量化训练、packing、多媒体或 NVIDIA。

量化：`operation=quantize`，`input={}`，`runtime` 仅允许 `engine=mlx`、`device_id=apple-gpu`、`seed`、`bits=4`、`group_size=64`、`mode=affine`。从未量化源权重产生独立 `model/` 目录，保留 tokenizer、模板和许可证，按约 128 MiB 张量预算拆分 safetensors；输出模型清单及来源摘要保存在 `conversion.json`。该格式仅开放生成，禁止直接再量化、量化训练或混入 adapter。模型体积变化有实测，不承诺推理速度或质量收益。

## 固定文本评测合同

`operation=evaluate`，`input={}`，模型与 adapter 沿用生成合同。`runtime` 为 MLX／Apple GPU 加固定 `max_tokens`、`temperature=0`、`top_p=1`、`seed`，必须与评测规则内的生成配置完全相同。评测样本和规则各不超过 4 MiB，均为完整清单所指定的本地文件；必须传入 `evaluation_dataset_path`／`evaluation_dataset_manifest`／`evaluation_dataset_manifest_digest` 与对应 `evaluation_criteria_*`。`evaluation_plan_digest` 为包含这两个 manifest_digest 字段的规范 JSON 摘要。

样本 JSONL 为 `{id,category,prompt,rule}`，4—64 条，类别 `business`、`format`、`regression`、`behavior` 都必须非空。规则只支持 `exact`（非空 `expected`，输出去除首尾空白后精确比较）、`contains_all`（非空 `keywords`，区分大小写）、`json_equals`（`expected` 为对象或数组，完整输出严格解析，不能去除围栏、重复字段或接受非有限数）和 `manual`（`instruction`，保持待审）。没有可执行表达式、自定义脚本或远端裁判。

规则 JSON 固定为 `schema_version=text-rules-v1`、`category_min_pass_rate`（四类分别为大于 0 且不超过 1 的阈值）、`regression_tolerance`（0—1）、`generation={max_tokens,temperature,top_p,seed}`。布尔值不能冒充数值。评测在两个独立子进程中分别加载基线和候选，生成同一冻结样本，保存逐样本原文、规则结论、原因、两边各类 passed／total／pass_rate、阈值、退化差值、manual 待审和 unknown 数量。

训练可绑定同组评测计划字段；执行器核对清单并在 adapter 元信息写入该计划摘要。评测的 `eligible=true` 要求候选达到全部固定阈值、回归未超容忍、无待人工项或未知项，且训练产物绑定同一计划。缺少训练前绑定的旧候选只能事后评测并保持不可准入；控制服务还必须核对计划不可变版本和创建时间早于来源训练提交，不能只信报告布尔值。报告中“通过”仅适用于该冻结文本规则集，不代表通用模型质量。

开发验证先执行 `tests/mlx/run_evaluation_probe.py --prepare --evidence NEW_DIRECTORY` 封存人工样本、规则和固定 128 步预算，再去掉 `--prepare` 执行。已有证据目录不能覆盖，预算启动记录采用独占创建。规则成功／失败、缺样本、人工待审、事后评测、零阈值、错误类型和文件修改反例已包含在测试中；新的真实质量结果以对应目录最终 `summary.json` 为准。

## 监督配方与验收边界

聊天模板 SHA-256 固定为 `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f`。配方摘要同时包含 `recipe.py` 实现源码摘要，防止只改监督逻辑却沿用旧配方身份。使用真实聊天模板逐前缀分词，并核对完整序列与每个助手生成前缀一致；只监督助手回答及 `<|im_end|>`，不监督角色头、系统／用户内容和回答后的换行。标签初始与输入位置对齐，在损失处以 `input_ids[:-1]` 预测 `labels[1:]`，恰好移位一次。padding 按位置设为 -100，即使 EOS 与 PAD 编号相同也保留真实 EOS 监督。

超长样本完整排除，不截断、不拼接。空回答、仅系统／用户、非法角色、媒体、工具调用、特殊标记和模板变化有明确错误；全数据无可训练样本时阻断。检查报告保留排除原因、有效监督数量和代表性 token／labels 对照。

真实试验使用 4 条人工测试数据、4 步 LoRA 和预先固定的 4 个问题。源模型摘要不变；适配器确有参数变化，独立进程重载改变 logits，另一独立重载的 logits 与输出可复现。目标代号未可靠学会，部分输出与 JSON 格式仍不合格，所以不把损失或输出变化当作模型质量验收。

`m3-20260910-01/report.json` 记录新来源合同下的另一次 1 步训练、严格适配器回载、量化导出与独立加载。量化权重从 988,097,824 字节缩至 278,064,792 字节，占源权重 28.14%；3 个分片最大 134,188,406 字节。4 个固定问题的两次量化模型独立重载 logits 差均为 0；与基座的数值和文字输出存在变化，原始输出全部保留。错误训练配方、错误适配器摘要真实阻断；当前 46 项测试通过。固定问题同时包含训练探针，不能当独立质量评测集；该结果仅允许作为实验产物，仍未完成候选质量准入。

官方资料：[MLX-LM 用法与 Python API](https://github.com/ml-explore/mlx-lm)、[固定 Qwen 源版本](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/tree/7ae557604adf67be50417f59c2c2f167def9a775)。具体训练 API 与 AdamW 默认值均以本机锁定版本源码复核。

**源码新增 Apple 7B 实验支持（2026-09-28）**：固定 Qwen2.5-7B-Instruct 已完成真实 LoRA 训练、暂停及独立恢复对照；普通 KV 缓存可用，q4 KV 缓存因输出失败而阻断。源码支持不代表业务质量通过，也尚未进入已安装的 046 App；新签名候选及完整 M6 验收仍待完成。

固定 7B 权重只读复核：`python3 adapters/mlx_text/prepare_model.py --variant 7b --verify-only`；移除 `--verify-only` 可下载固定版本，默认仍为 0.5B。

**Apple 签名候选更新（2026-09-28）**：固定路径现为 Ver2.6（049），已包含 7B 实验支持。包内正式接口完成空库恢复、导入、来源划分、2 步 LoRA 训练、生成与导出；导出适配器脱离控制服务后，使用外部固定基座也能独立生成。以上为技术链路验证，不是业务质量准入。原生界面检查因 Computer Use 运行环境无法启动而未执行；完整 M6、干净安装、公证和发行仍未完成。

**Apple 大基座质量实验（2026-09-28）**：同一 Ver2.6（049）的 7B LoRA 完成 192 步训练，预先冻结的新 32 题结果为基座 5/32、适配器 31/32；业务 0/8→8/8、格式 0/8→7/8、正常回归 5/8→8/8、行为 0/8→8/8。唯一失败将订单编号 `C5-fo-02-04` 写成 `C5-fo-002-04`。业务改善达标，但格式要求全对，因此未登记合格候选，也未追加训练或重试留出。样本为作者可见的合成合同材料，非盲评；完整业务质量、原生界面及 M6 仍未完成。
