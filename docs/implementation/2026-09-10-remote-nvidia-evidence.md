# 独立执行目标与 NVIDIA 文本组合：实现和验证记录

Ver2.0 已把执行目标、项目默认位置、单次任务选择、上传范围确认、原编号事件同步、取消和只补收接入控制服务。HTTPS 随 Ver2.1（004）首次打包，Ver2.1（005）随后通过整包、内置 CA 和原生未知 CA 拒绝验收；本页保留这些阶段证据。当前签名候选已更新为 Ver2.2（010），尚未完成该包的远程原生复验，也未对外发布，最新状态见[010 执行进度](2026-09-12-ver2-2-010-progress.md)。文件传输使用独立进程、持久 SQLite 和真实文件；文本执行器包含固定 NVIDIA 推理与 SFT + LoRA 实现。

当前机器是 Apple Silicon Mac。公共 NVIDIA 入口会明确拒绝运行，未做 CPU 或 Apple 回退。跨主机网络接入、NVIDIA 实机推理/训练、该适配器的质量准入仍未验收；回环传输成功不能替代这三项。

## 用户操作与边界

1. 在“设备与环境”登记执行服务的固定地址与身份，再检查连接。Ver2.1（005）阶段已实现 `https://主机:端口`，并保留字面 `http://127.0.0.1:端口` 回环模式；HTTPS 必须通过运行时公开 CA 包的证书链、主机名和有效期验证。连接不采用代理、不跟随重定向、不降级为 HTTP；上述旧包验收不代替 010 的实际跨主机验证。
2. 原生 App 将凭据保存到系统钥匙串；控制服务只持有当前会话的明文。数据库只保存随机引用，不保存明文凭据。锁定或缺失时必须重新连接；恢复备份会清理凭据引用。开发网页只支持内存会话凭据。
3. 每个项目可保存默认执行目标，只影响以后新建的文本草稿。任务中的执行位置是单次覆盖，不会改动已有草稿或其他项目。媒体任务继续采用已有固定组合。
4. “传输验证”只上传已导入的数据或素材。先显示目标、文件名、每个文件字节数和摘要，再由用户明确开始；它不会加载模型。
5. 文本任务预检冻结目标版本、模型/数据清单、代码与分词配方身份。NVIDIA 未就绪时不创建远端运行，也不上传模型。可以执行时仍先显示上传范围，由用户明确开始。
6. 断线或证书验证失败不等于停止。取消意图和完整取消命令先持久化，提交正在发出或连接恢复后继续向原编号发送；确认原进程组退出前保留待确认状态。补收只读取原封存清单，不创建新计算，原回收失败记录仍保留。

上传分块为 1 MiB，单个模型文件最多 2 GiB，输入总量最多 4 GiB，最多 16 个文件；传输验证每个文件另限 64 MiB。服务分别预留已上传文件、执行输入副本和产物空间。上传在每个哈希/传输分块检查取消和宿主退出。

## 固定 NVIDIA 组合

| 项目 | 当前实现 |
| --- | --- |
| 设备 | Linux、CUDA 12.8、`cuda:0`、支持 BF16、至少 8 GiB 显存；实际小矩阵探测后释放 |
| 模型 | `Qwen/Qwen2.5-0.5B-Instruct` 原权重，完整清单摘要 `a9b08fa2b761cbfc7335b28c6b0997b6e7713893aaca4b215625ffc99a1d36b3` |
| 依赖 | PyTorch 2.10.0、Transformers 4.57.6、PEFT 0.18.1、Accelerate 1.12.0、Safetensors 0.7.0、NumPy 2.4.2 |
| 生成 | BF16 基座、逐 token 生成、固定 seed；支持 greedy/temperature/top-p、停止序列、流式开关及有限上下文；最多输出 512 tokens |
| 训练 | SFT + LoRA、最后指定层的 q/v 投影、仅助手内容与结束标记参与损失、BF16 基座与 FP32 LoRA；不截断监督样本，不训练 embedding |
| 训练产物 | PEFT 原格式、明确转置得到的 MLX LoRA、转换来源报告；始终是实验产物 |
| 暂未开放 | QLoRA、CPT、远端 checkpoint/暂停继续、远端适配器推理、未知模型或任意命令 |

PyTorch 的 CUDA 12.8 安装组合来自[官方历史版本安装页](https://pytorch.org/get-started/previous-versions/)；模型和 LoRA 参数按固定版本的 [Transformers Qwen2 实现](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/models/qwen2/modeling_qwen2.py)与 [PEFT LoRA 配置](https://github.com/huggingface/peft/blob/v0.18.1/src/peft/tuners/lora/config.py)实现。这里采用已固定版本，不表示它们是最新版本。

实际 tokenization 与监督样本检查在输入上传后、模型分配前完成。预检中的 `tokenization_check=on_executor_before_model_allocation` 明确表示该边界；它不能写成已经完成远端样本计算。

## 完成接收与恢复

- 工作进程的 stdout 是有界 NDJSON 事件，库日志进入独立 stderr。执行服务核实子进程身份与整个进程组退出后才确认终态。
- 完成门槛逐项核对引擎、设备、精度、全部有效参数、固定模型、源码与精确分词配方。生成必须有 5 个固定文件，训练必须有 9 个固定文件；缺正文或只有 metrics 不能成功。
- 收回文件后再次核对 `effective-config.json` 与完成对象、环境/计算设备、LoRA 转换来源和权重摘要。文件名齐全不代表报告内容可信。
- 本机收集使用独立字节副本，逐文件验证后排他发布。禁止用硬链接破坏远端收回目录的单链接约束，因此本机登记暂时失败后仍可按原清单补收。
- 源码身份固定在模块加载时。磁盘源码变化后旧进程不能报告新摘要，必须重启执行服务后再检查。
- 已请求取消而原计算先结束时保存这一事实，不伪造“取消已生效”；只有原执行返回已取消并确认进程组退出，才显示取消完成。

## 当前证据

证据均保留在工作区，失败复现不删除。最终整包和界面验收由发布记录单独关联。

Ver2.0 阶段控制服务、执行协议及 NVIDIA 合同合计 **667 项测试通过**；随后补入的跨目标 101 条历史分页用例另 **1 项通过**。独立审查的完成接收合同 **15 项通过**，取消/补收两条失败原复现已修复并通过复验。NVIDIA CPU 组件 v3 和公共 CUDA 拒绝 v2 的源摘要均为 `a88a481daa39fe196586ca9a93307dd277d81e89df9dfea73398a5784feeb5f7`。

HTTPS 候选的后端组合回归 **168 项通过**，最后 TLS/控制链针对性复验 **73 项通过**，两轮分别计数。实际覆盖证书拒绝、运行中换证书、分块续传、原编号取消、重启及原清单补收；10 次服务正常退出、强杀 0。详见 [HTTPS 后端读回](../../.artifacts/https-implementation-ver2-next-v1/backend-readback.json)。这些新测试只有本机回环 TLS 和 CPU 合同夹具，模型生成、训练和外部主机连接均为 0。

| 证据 | 证明范围 |
| --- | --- |
| `.artifacts/control/remote-integrated-final.xml`、`remote-target-pagination.xml` | 最终完整回归 667 项及新增分页 1 项 |
| `.artifacts/control/remote-product-all.xml` | 目标/凭据权限、默认位置、真实 NVIDIA 探测阻断、上传/取消/断线/补收的产品 API 专项 |
| `.artifacts/control/remote-export-regression.xml` | 导出任务不含草稿时仍返回业务拒绝；模型、适配器、作品、报告导出回归 |
| `.artifacts/control/remote-review-fixes.xml` | 完成合同负例与独立复现的取消/补收修复验证 |
| `.artifacts/desktop/remote-product-review/` | 独立复现：登记失败后补收、提交时取消；原失败日志与修复复验 |
| `.artifacts/nvidia-completion-independent-v1/` | 独立完成接收合同正反例；明确没有运行模型或 GPU |
| `.artifacts/nvidia-text/cpu-components-v2/report.json`、`cpu-components-v3/report.json` | 真实 0.5B 原权重在 CPU 上的组件验证；不是 NVIDIA 验收 |
| `.artifacts/nvidia-text/public-cuda-rejection*.json` | 公共入口实际拒绝本机执行、不创建输出、不走 CPU 回退 |
| `.artifacts/nvidia-text/runtime-freeze.txt` | 本机隔离组件测试环境的完整依赖记录；该环境 Python 为 3.14.6 |

CPU 组件测试实际生成“完成”，运行两步 LoRA 并检查参数变化、embedding 抽样不变、PEFT→MLX 矩阵逐值转置与数值等价。它只证明这些计算组件和文件转换在 CPU 上执行；没有证明 CUDA 内存、BF16 实机表现、Apple 独立加载或质量改善。

## 执行服务准备示例

以下是候选版本的安装与启动说明，不表示已经在 NVIDIA 主机部署。控制包要求 Python 3.13 或以上；应在独立目录和虚拟环境中操作，禁止使用主 App 工作库作为执行服务目录。

```sh
python3.13 -m venv .venv-nvidia
.venv-nvidia/bin/python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
.venv-nvidia/bin/python -m pip install -r adapters/nvidia_text/requirements.txt
.venv-nvidia/bin/python -m pip install -e services/control
.venv-nvidia/bin/python workers/nvidia_worker.py --mode probe
```

启动器需要已生成的独立凭据文件（权限 `0600`，32—512 位可见 ASCII），不会输出凭据。服务握手返回端口、执行器身份、PID、连接方式和验证范围；将对应地址、执行器编号和凭据登记到 App。

HTTPS 模式必须显式给出 `--https`、`--bind`、`--cert-file` 和 `--key-file`。以下变量及路径应替换为已经准备好的配置：绑定值为服务本机 IP，登记地址中的主机必须与证书匹配。私钥须由当前用户拥有、权限为 `0600`，使用无口令 PEM；证书链须能由客户端随附的公开 CA 包验证。当前没有私有 CA 配置入口。

```sh
.venv-nvidia/bin/python -m ailab_control.remote \
  --data-dir /新的独立HTTPS执行目录 \
  --token-file /明确授权的私有凭据文件 \
  --https --bind "$AILAB_EXECUTOR_BIND_IP" --port "$AILAB_EXECUTOR_PORT" \
  --cert-file /已准备好的完整证书链.pem \
  --key-file /权限为0600的服务私钥.pem
```

一个执行目录固定一种连接方式。已有回环目录不能直接改成 HTTPS，须使用新的独立目录及其新执行器身份。原回环启动方式继续保留：

```sh
.venv-nvidia/bin/python -m ailab_control.remote \
  --data-dir /明确独立的执行目录 \
  --token-file /明确授权的私有凭据文件 \
  --port 0 \
  --loopback-contract-only
```

本机 TLS 验证不代表跨物理 NVIDIA 验收。NVIDIA 实机仍须完成固定模型推理、SFT、取消/断线/补收、显存与进程释放，以及按训练前冻结方案进行的质量对照，才能更新相应交付状态。005 原生通过登记与真实未知 CA 拒绝，目标显示证书错误、传输入口禁用，执行库未接收文件或任务；服务正常退出，临时凭据已清除。见[原生目标后验](../../.artifacts/native-https-rejection-ver2-005-v1/run-001/root-native-target-postcheck.json)与[本轮原生汇总](../../.artifacts/integration-ver2-1-005-v1/native-acceptance/本轮原生验收.json)。
