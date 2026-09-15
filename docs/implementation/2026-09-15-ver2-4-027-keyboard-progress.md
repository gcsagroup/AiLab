# Ver2.4（027）键盘导出任务

本轮固定公司签名包为 027。源码和 Safari 组件验证完成后，在已有合法恢复根中通过纯键盘进入文字原作品导出、选择目录、核对计划、一次提交，再从任务队列重开同号已完成导出并正常退出。停机读回与该原生键盘任务子集已获根接受；完整 AC 与 M 阶段不随本轮提高。

## E132：最小键盘属性与 Safari 组件子集

仅 `ui.tsx`、`App.tsx` 增加显式 tabindex 和一行解释：共用 Button 默认 0、保留调用方指定值，Dialog 关闭按钮及 App 的 19 处原生按钮加入宿主顺序。没有新增全局 Tab 接管或改写业务请求。新增测试原件在修前 4 失败、2 通过；修后 64 项通过，补回命令误拼漏选的两份文件后另 11 项通过，共 75 项，类型检查通过。7 项夹具测试另计，原红例与命令误拼记录保留。[源码接受](../../.artifacts/keyboard-task-ver2-4-next-v1/root-source-acceptance.json)、[源码与测试记录](../../.artifacts/keyboard-task-ver2-4-next-v1/source-tests-001/REVIEW.md)、[独立审查](../../.artifacts/keyboard-task-ver2-4-next-v1/independent-source-review.md)

真实 Safari 组件记录支持 Tab／Shift-Tab、导出弹窗内往返和关闭回入口：37 条 focusin、16 次 GET、零业务写和页面错误。夹具作品是视频，任务队列为空；没有执行导出，不把空队列开关写成同号任务重开。05 保存图最终焦点仍为目录，中间关闭按钮往返由焦点 trace 支持。其它组件原生按钮及完整宿主规则未逐项验收。[Safari保存证据读回](../../.artifacts/keyboard-task-ver2-4-next-v1/browser-001/root-readback.json)

## E133：027 包、真实键盘任务与停机读回

9 月 14 日唯一 027 构建退出 0，完整包、160 项生产来源与 7 个公司签名目标已获根接受。App 仍在 `apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app`；身份为 `Apple Distribution: Global Cybersecurity Alliance Limited (R3JK7R29AC)`。包接受中的“尚未启动原生”保留形成时含义，本节记录后续原生事实；未执行公证或发布。[027包接受](../../.artifacts/integration-ver2-4-027-v1/root-bundle-acceptance.json)

9 月 15 日本次原生直接使用上一轮合法恢复根，没有新恢复或模型运行。选已有文字作品的“导出原作品”，`work_revision_id=null`；09 展开的负载为 `work/result.txt`、`recipe.json`、`object.json`。10 显示已完成，export 为 `export-adcafd845a5e492d849b57ea5f6c3ea8`；13 队列出现 `task-7d983f060f844d39b74a800a450e978a`，14 重开同一 export 和原目标目录。17 退出确认后 App 正常退出 0。17 份 AX、16 张 JPEG 与 158 条操作记录（含一次目录输入）已保存；目录通过原生面板键盘跳转和输入选择，未用支持字段代填产品只读路径。此处的同号重开是原生任务事实，与 E132 的 Safari 空队列不同。[操作记录](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/keyboard-log.json)、[展开计划](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/09-plan-files-expanded.ax.txt)、[初次成功](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/10-export-submitted.ax.txt)、[同号重开](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/ui/14-same-export-reopened.ax.txt)

正常退出记录表明 1 次 App、1 次导出、0 模型、0 reconcile、0 额外 probe／系统设置修改，原选择恢复。启动会话额外 SQL 为 0；随后根以唯一 `mode=ro&immutable=1` 连接读取停机新库，实际退出 0，连接已关闭且 DB／三旁路完整文件事实前后相同。本次停机后三旁路均不存在，这是当次文件事实；上轮保存的空 WAL／32768 字节 SHM 历史事实不改写，也没有外部清理。[正常退出](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/run/result.json)、[连接回执](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/connection.json)、[读回后文件事实](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/facts-after.json)

读回结果为 `export_verified_settings_unchanged`：旧 519 个资源、665 条事件、2 条命令、项目、schema version 和 settings 保持；新增计划／导出／任务／执行共 4 资源、8 条正常事件和 1 条 export 命令，未出现 reconcile。实际包为三负载加 manifest 共四文件，来源、摘要与内容核对通过。八条事件由三条前置状态、三条进度、finalizing 和 succeeded 组成；此前九条预估更正，旧准备稿保留。本轮是原文字产物，不套用 E131 修订版 3 的四负载加 manifest 或 16000 字符断言；旧五文件包完整保护另核。[停机逻辑与包核对](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/result.json)、[包清单与文件事实](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/readback-001/package.json)

根已接受本次停机原作品导出数据子集：最终 523 资源／673 事件／3 命令，原文字为 105 个 Unicode 字符、315 个 UTF-8 字节，三负载合计 4114 字节；原 23 项保护按约定字段、原 020 全树与上轮五文件包保持。选择器原字节、inode 和权限身份恢复，其时间随本次切换和恢复变化。[根停机数据接受](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/root-readback.json)

保存原件独审与根已接受本次完整任务的纯键盘操作链，未使用鼠标、AXPress、直接 focus 或 setValue 完成链路。08 计划更新和 10 成功更新后，焦点均曾为 HTML2，下一次 Tab 才回关闭按钮6；不能声称全程焦点连续或所有按钮已验。06 仅有 AX，没有图像；系统退出提示的 16／17 在 Tab 后仍为 sheet，最终 Return 正常退出由进程回执证明，不写成“退出按钮已聚焦”。无逐键时钟，不签交互效率。[原生保存证据独审](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/independent-keyboard-review.md)、[根原生任务接受](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/root-native-acceptance.json)

## 保持的边界

当前剩余项以本次新增摘要为准：E131 已补中性待核实提示与完整文字修订包同号补登记成功的有限子项，E133 已有文字原作品键盘导出、同号任务重开及停机读回证据；这些已完成的有限子项不再列为重复待办。历史表中的“仍未验”保留其形成时点；其它对象／故障出口、其它键盘任务与完整 AC／M 阶段继续待验。

同次宿主回执为 7997.902083 毫秒（约 7.998 秒），其 scope 是宿主 run 入口至首屏数据和环境完成后的双动画帧。它是一次完整就绪参考，不是单独的主窗口初显计时，不提高 20 次冷启动初显门槛，也不解释旧长尾。[原始启动回执](../../.artifacts/keyboard-task-ver2-4-next-v1/native-run-001/run/first-frame.original.json)

只记录这一已有文字原作品导出的真实键盘路径；其它组件按钮、其它任务组合、完整 AC-23／AC-27、AC-25 五名首次用户、AC-26 指定跨端同份产物和 M0—M6 保持未整体签署。旧 020 偶发空白、设备／质量／安装／公证等缺口不随本轮提高。E130／E131 和旧 026 进度保留形成时原文。[上一轮登记恢复](2026-09-14-ver2-4-026-export-recovery-progress.md)
