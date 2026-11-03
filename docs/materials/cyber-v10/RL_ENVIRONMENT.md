# 漏洞识别与修复 AgenticRL 环境方案

状态：材料准备方案，环境适配器、统一 API、生命周期管理及 RL 训练闭环均未实现。本 PR 仅提交方案摘要；固定源码证据、任务卡、Docker 构建和启动材料位于另行交接的完整 v10 包，不随本 PR 上传或执行。

## 场景与分层

目标是让 Agent 在授权目标中探索并识别漏洞，提交可复现证据和候选补丁，再由独立验证器判断发现与修复是否成立。分为目标环境、Agent 观察与动作、独立验证器、策略优化训练器四层。复用环境工作流不等于已经实现 RL 参数更新。

| 任务模式 | Agent 可见 | 组织者保留 |
| --- | --- | --- |
| 盲发现 | 授权范围、工具说明、允许读取的目标源码或服务入口 | 漏洞 ID、报告、参考 PoC、补丁、隐藏测试、验证器源码和答案 |
| 已知问题修复 | 按难度提供的报告、相关源码及必须保持的正常行为 | 参考补丁、隐藏安全与回归测试、管理接口 |
| 发现并修复 | 先盲发现，确认后按阶段释放必要问题信息 | 隐藏测试、参考答案，分别保存发现与修复结果 |

本文件及完整包任务卡属于组织者材料，不直接作为盲发现 Agent 的提示词。组织者知识库、验证结果中的秘密和参考补丁也不能通过工具响应泄露给 Agent。

## 固定候选环境与来源

首期复用 BountyBench 的 `detect_workflow`、`patch_workflow`、`detect_patch_workflow`，候选任务为 MLflow `bounty_1`。

| 对象 | 固定版本或位置 |
| --- | --- |
| 框架 | [bountybench/bountybench](https://github.com/bountybench/bountybench/tree/8ece6aab0b954f7c85b5705e69f0142eeaf2c5d1)，`8ece6aab0b954f7c85b5705e69f0142eeaf2c5d1` |
| 任务库 | [bountybench/bountytasks](https://github.com/bountybench/bountytasks/tree/60311f3d9334af493841b769245d9fed4e07cf88)，`60311f3d9334af493841b769245d9fed4e07cf88` |
| 任务记录的脆弱版本 | `fc515cd25072248fb3328b16ae1bd621dbffa50a` |
| 任务树中 codebase 子模块版本 | `d10f342899f2677a57e92e6380ea2ba883c3adf3`，与脆弱版本不同，不能混用 |
| 完整包方案与任务卡 | `当前材料_v10/rl_environment/` |
| 完整包构建说明 | `当前材料_v10/rl_environment/Docker封装/README.md` |
| 完整包版本与定义证据 | `environment_task_manifest.json`、`任务材料/source_inventory.json`，位于上述环境目录 |
| 未来运行回执模板 | `当前材料_v10/rl_environment/run_receipt.template.json` |

上游记录该任务为 CVE-2024-1558 / CWE-22；这是固定任务元数据声明，本轮未运行复现。完整包未下载目标代码库、参考 PoC、参考补丁和报告 HTML，也不是可直接离线启动的镜像仓库。框架许可不能自动覆盖任务、报告或目标源码；任务树许可适用范围仍待确认。

## 独立判定与已知限制

发现成立需要固定脆弱版本上的可复现证据或独立验证回执，不能仅凭 Agent 自报。修复成立至少同时满足：脆弱基线成立、补丁后目标健康、安全判据通过、约定正常功能回归通过。

准备阶段静态读取固定任务定义发现以下限制，相关源码定位与摘要保存在完整包，未执行这些脚本：

- 验证器会消费并删除本地 `FLAG.txt`；连续运行第二次的缺文件状态不能当作修复成功。后续需新鲜初态及独立补丁后安全检查。
- 任务级 `run_bounty_invariants.sh` 仅含 shebang，成功退出不能视为正常功能回归通过。
- 项目级回归脚本统计 pytest 输出中的通过数量；未来需同时记录测试收集数、通过、失败、错误、跳过、退出码和健康状态，单看通过数量不足以判定。
- 代码树子模块版本不等于任务指定的脆弱版本，未来需记录实际 checkout 结果。

拟保留以下独立字段；这是回执语义，不是当前框架已有接口或已测结果：

| 字段 | 语义 |
| --- | --- |
| `finding_verified` | 是否独立确认发现 |
| `security_test_passed` | 候选补丁是否通过约定安全判据 |
| `regression_passed` | 约定正常功能是否通过回归 |
| `infrastructure_error` | 环境、工具或验证器故障信息，与 Agent 失败分开 |

前三项均可为 `null`，表示尚未判定。目标未启动、测试未收集或验证器故障不能记作安全通过。任意 Agent 补丁的统一判分入口仍需后续实现和验收。

## 待讨论的环境接口与轨迹

```text
describe -> 环境、框架、任务、镜像版本及可用动作
reset(task_id, seed, information_level) -> episode_id, observation
step(episode_id, step_id, action) -> observation, status, evidence_refs
evaluate(episode_id, submitted_finding_or_patch) -> verification_receipt
close(episode_id) -> cleanup_receipt
```

以上是协议草案，不是可调用的 Studio API。未来适配需明确动作工具、参数、工作目录、超时、预算、重复请求、取消及复位语义；验证器和环境管理权限不开放为 Agent 普通动作。

轨迹至少关联任务、模型、环境版本、`episode_id`、`step_id`、过滤后的观察、动作、工具输出、耗时、token 数、判定证据及 `terminated` / `truncated` 原因。进入 RL 优化还需真实采样 token、旧策略 log probability、loss mask 等；SFT 问答不能当作已验证的 Agent 轨迹。本轮没有采集实际轨迹。

## 奖励与评估草案

奖励分量区分首次确认发现、首次完整修复和动作或预算成本；权重待任务负责人确定，不提供伪造数值。重复报告同一问题不重复奖励。关闭服务、破坏测试、隐藏症状或读取参考答案不算修复；基础设施故障标记无效回合。

训练与评估按项目、漏洞及修复家族隔离，不把同一漏洞的不同提交分到两侧。已经用于调试的候选任务不再宣称为独立盲测任务；SFT 与知识库材料也需检查是否泄露评测答案。

## Docker 材料与未来验收

完整包保存 `prepare_source.py`、`Dockerfile.controller`、`compose.yaml`、启动脚本、官方工作流调用脚本、无凭据配置示例及固定上游说明。这里只描述它们的用途，不复制构建文件或运行命令。

后续需要 Linux Docker 主机、Git、Python、Compose v2 和外部依赖访问。现有方案沿用上游 privileged Docker-in-Docker 控制器，不挂载宿主机 Docker socket；该控制器不构成 Agent 代码的隔离边界，需专用可重置主机或虚拟机，并限制 Agent 的管理权限和网络范围。

CPU、内存、磁盘、耗时、token 预算均未实测。源码固定不代表镜像可逐字节复现，未来还需记录基础镜像 digest、依赖版本和最终 image ID。模型 provider 兼容性也未完成实际接入，不能声称团队模型端点已可用。

| 未来验收步骤 | 应保存的证据 | 本轮状态 |
| --- | --- | --- |
| 版本与构建 | 实际框架、任务和脆弱提交；镜像与依赖摘要、构建日志 | 未执行 |
| 脆弱基线 | 服务健康、新鲜状态、复现日志和独立发现回执 | 未执行 |
| 修复检查 | 候选补丁摘要、补丁后健康、安全测试和完整回归结果 | 未执行 |
| 复位与清理 | 恢复规定初态、任务容器退出、缓存和残留检查 | 未执行 |
| 环境接入 | 观察过滤、动作、超时、预算、取消、轨迹与判分映射 | 未实现 |
| RL 训练闭环 | 真实 rollout、奖励、策略更新与独立评估结果 | 未实现 |

下一阶段由负责人确认主机、资源、隔离、网络、许可和判据后另行开展。本次 PR 不启动 Docker、不发出模型请求、不改平台或训练器，不把材料准备标为部署或训练验收通过。
