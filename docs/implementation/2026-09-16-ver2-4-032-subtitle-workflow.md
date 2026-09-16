# Ver2.4（032）字幕键盘、保存与历史导出：E142

固定 032 公司签名 App 的本轮字幕流程已获根接受：功能链键盘操作、播放器与展开／折叠采样、继续／放弃临时修改、一次保存 v5、同库重开、明确选择历史 v4 导出、两次正常退出及保护恢复完成。渲染检查使用容器滚动，不能称全部动作都是键盘。本轮没有重建或执行模型，完整 AC22、AC27、M0—M6 和发布状态不提高。

## 候选与验证层次

源码基线为 `bff931f89528ced651dc4fb30ff37b90e5bc9fb9`，沿用固定 Ver2.4（032）签名包，162 项生产来源已绑定。相关控制测试 70 项、前端测试 64 项通过；交付导出控制测试另有 31 项通过，控制两组各保留 2 项警告。它们不是本轮原生操作的替代证据。[前检](../../.artifacts/subtitle-workflow-ver2-4-032-v1/root-preflight.json)、[修订控制测试](../../.artifacts/subtitle-workflow-ver2-4-032-v1/control-tests.log)、[前端测试](../../.artifacts/subtitle-workflow-ver2-4-032-v1/frontend-tests.log)、[交付测试](../../.artifacts/subtitle-workflow-ver2-4-032-v1/delivery-tests.log)

准备阶段的 8 项测试、守卫 16 项边界测试、启动器 39 项 AST 合成门禁及停机验收器 12 项合成测试分层记录；只证明各自范围。新 A 来自已审历史备份恢复，守卫沿用 47 项保护基线与原 selector 文件身份恢复合同；准备不向既有工作库写入。[准备接受](../../.artifacts/subtitle-workflow-ver2-4-032-v1/root-preparation-acceptance.json)、[守卫检查](../../.artifacts/subtitle-workflow-ver2-4-032-v1/guard-001/check-result.json)、[启动门禁](../../.artifacts/subtitle-workflow-ver2-4-032-v1/launcher-review-001/gate-tests.json)、[验收器测试](../../.artifacts/subtitle-workflow-ver2-4-032-v1/checker-tests-result.json)

## 首轮真实操作与保存

功能链使用键盘，从作品入口打开原 v4 字幕；05 是载入黑屏，06 的容器 Space 是滚动，07 至 08 才记录原视频播放从 1 秒到 2 秒。渲染检查另用 CUA 容器 scroll，展开和折叠时采样首、中、末字幕及逐页往返；11 是差异尾部，12 才是字幕列表尾部。折叠后 160 页位置的两帧只证明两个采样时点未空白，不证明连续无空白或旧 020 根因已修复。[键盘入口](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/04-v4-open-keyboard.ax.txt)、[实际播放](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/07-original-playback.ax.txt)、[播放结束](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/08-original-video-ended.ax.txt)、[字幕列表尾部](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/12-expanded-reverse-tail.ax.txt)、[折叠位置](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/16-17-collapse-down160.ax.txt)

编辑时键盘定位末条，输入 36 字符临时文本；关闭提示中先继续编辑，临时文本保持，再明确放弃，返回入口后重开仍为原 v4。随后再次编辑末条为 `native032 keyboard subtitle tail xxxxxxxxxxxxxxxxxxxxxxx`，只保存一次独立 v5。[临时编辑](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/26-temporary-tail.ax.txt)、[继续编辑](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/28-continue-restores-tail.ax.txt)、[放弃后重开](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/31-reopen-still-v4.ax.txt)、[保存 v5](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/33-v5-saved.ax.txt)

首轮正常退出 0。停机检查确认新增 v5 `work-revision-2ae05533e4e1418cbd9d8e2d97b6d658` 的父版本为原 v4，仅末条变化，仍为 200 条／16000 字符；恰新增 1 个修订、1 个字幕产物及 1 条命令，新增事件与模型任务为 0。页面上下文最终回到原值；生成的 v5 VTT 为 54989 字节。原视频与历史 v4 未被这次字幕修订替换。[首轮退出](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/app-first/exit.json)、[停机保存检查](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/saved-check.json)

## 重开导出与证据边界

第二次同 App、同 A 重开显示当前 v5 及其原 v4 父版本，随后明确选择历史 v4，导出编号 `export-1bfb2c6b4c04497b995bc3285b6498e1`。中文空格目录内实际 5 文件：`work/video.mp4`、`revision/subtitles.vtt`、`recipe.json`、`object.json` 和 `manifest.json`；其中 4 个载荷文件加清单，摘要与登记一致。导出字幕精确属于历史 v4，当前 v5、历史 v4 与原视频保持，不把当前 v5 误当成已导出版本。[重开 v5](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/36-reopened-v5.ax.txt)、[选择历史 v4](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/38-historical-v4-selected.ax.txt)、[完成界面](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/47-export-completed.ax.txt)、[历史导出检查](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/exported-check.json)

导出阶段新增 1 个导出任务、9 个预期事件，没有新模型任务；两次正常退出均为 0，最终页面上下文回到原值。162 项生产来源保持；47 项保护记录中 44 项严格不变（含缺席项与重复路径），selector 原字节、inode、权限恢复，ctime 差异保留，两份 startup 日志允许更新。App、控制及守卫均已停止，恢复与释放回执齐全。[第二次退出](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/app-second/exit.json)、[守卫恢复](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/selector-guard/restored.json)、[释放](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/selector-guard/released.json)、[根读回](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/root-readback.json)、[根接受](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/root-native-acceptance.json)

根保留 47 张 JPEG、317 条动作记录，其中 216 次 pressKey、95 次 scroll、6 次 typeText。40 实际停在只读路径框，不是真正目录面板；41 的中文 typeText 丢字、粘贴超时及全选无效后，Escape 退出并重开 GoTo，输入 ASCII 父目录，再 Right 与 6 次 Down，42 精确选中中文空格目录，43 返回正确路径。粘贴超时没有 actions 条目，仅由原 CUA 执行记录及根读回说明；48 退出图像缩小，正常退出由原 AX 与退出 0 补足。[精确目录选择](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/42-native-directory-keyboard-selected.ax.txt)、[目录返回](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/43-directory-returned-to-app.ax.txt)、[根限制记录](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/root-readback.json)

独立审查接受本轮完整字幕操作与历史导出流程，范围限当前固定包、新 A 和已记录系统条件。原视频播放不表示字幕烧录或播放器已加载外置字幕；根接受措辞勘误及原摘要链保留。 [独立审查](../../.artifacts/subtitle-workflow-ver2-4-032-v1/independent-native-review.md)

操作记录器曾因证据文件名重复出现 `EEXIST`，原失败保留并修正后续命名，不是产品数据失败；根保留动作日志、分步 AX 和图像。自动环境探测与模型执行分开，本轮不能称零探测。旧 020 原因仍未明，完整 AC27、干净安装、质量准入、指定 NVIDIA 与同份产物回程、M0—M6 及发布门槛保持。[动作日志](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/actions.jsonl)、[捕获记录](../../.artifacts/subtitle-workflow-ver2-4-032-v1/native-run-001/ui/captures.jsonl)、[交付矩阵](2026-09-10-current-delivery-matrix.md)

本页 `.artifacts` 链接为本机证据，不随 GitHub 源码上传。全部正式文档与历史记录继续提供简体、繁体、英文版本。
