# GCSA AI Lab

[简体中文](README.md) · [繁體中文](i18n/zh-TW/README.md) · [English](i18n/en/README.md)

本地优先的模型训练与运行桌面工作台。围绕项目管理模型、数据、训练任务、评测和作品，提供语言、图片、视频及配音的工作流程。

## 当前状态

当前固定公司签名候选为 **Ver2.4（032）**，签名组织为 **Global Cybersecurity Alliance Limited**。这是开发候选，完整 M0—M6、干净安装、公证及正式分发验收尚未完成。

032 已通过真实 Python 符号链接原路径选择、三环境保存、同号同库重开和恢复内置的有限验收；两次停机读回及原资料保护恢复通过。外部 venv 依赖探测失败保留，恢复内置后的环境就绪不等于模型执行；原生跨库竞态和诊断导出仍未覆盖。 [032 进度与边界](docs/implementation/2026-09-16-ver2-4-032-python-path-preservation.md)

030 已将工作库连接隔离修复打入签名包：源码回归、整包复核及包内两项真实控制服务测试通过，原生备份、目标库启动失败回滚、成功切库和同号重开的有限子集已获根接受，停机读回通过。切库、回滚或重启后的旧请求不会自动换用新库身份重发；原生选择器的异步竞态仍未覆盖。[030 进度](docs/implementation/2026-09-16-ver2-4-030-connection-isolation.md)

Media 三个导入入口的源码修复、相关测试与 Safari 验证已有证据；029 公司签名包、两个既有任务中的四个原生入口实例、正常退出及一次停机读回的有限子集已获根接受（E137）。未执行真实导入或模型运行。028 工作台四按钮、027 文字原作品纯键盘导出与同号重开的既有有限接受保留。详细状态见[当前交付矩阵](docs/implementation/2026-09-10-current-delivery-matrix.md)和[更新记录](CHANGELOG.md)。

## 功能与范围

- **语言模型**：固定 Qwen2.5-0.5B-Instruct / Apple MLX 组合的生成、SFT + LoRA、检查点、评测和候选准入。
- **媒体工作流**：图片生成与 Tiny-SD LoRA、固定 SVD 视频生成、Kokoro 中文配音，以及分步保存和明确复用。
- **项目与数据**：任务草稿、来源组训练／验证划分、版本记录、作品修订、导出、完整备份与恢复。
- **执行管理**：本机执行、独立执行服务协议、传输核验和中断恢复。指定 NVIDIA 与同份产物跨端仍待实机验收。

视频与音频训练尚未开放；媒体工作流分别保存作品，尚不合成为一条配音成片。既有 LoRA 和量化候选质量失败仍保留，不能把训练完成或文件可读取等同质量通过。精确组合和未开放范围见[候选范围](docs/implementation/2026-09-10-ver2-scope.md)。

## 开发与验证

前端使用 React / TypeScript，桌面宿主使用 Tauri / Rust，本机控制服务使用 Python。依赖版本固定在仓库的锁文件中。

    npm ci
    npm test
    npm run check:docs
    npm run test:docs

TypeScript 检查与控制服务测试：

    ./node_modules/.bin/tsc --noEmit -p apps/desktop/tsconfig.json
    services/control/.venv/bin/python -B -m pytest tests/control -q

控制服务命令需要先准备对应的 Python 3.13 环境及依赖。完整构建、各运行时环境、签名和启动步骤见[桌面开发与构建说明](scripts/desktop/README.md)。当前候选的系统范围为 Apple Silicon / macOS 26 及以上，仍需最终候选复验。

开发、原生测试和本机候选运行共用：

    apps/desktop/src-tauri/target/release/bundle/macos/GCSA AI Lab.app

每次实际 App 构建递增构建编号。提交源码或修改文档不会生成新 App 版本。

## 文档

- [用户操作手册](docs/USER_GUIDE.zh-CN.md)
- [文档中心与 1.1 设计基线](docs/README.md)
- [完整三语文档目录](i18n/README.md)
- [更新记录](CHANGELOG.md)
- [原型参考](prototype/reference-2026-09-09/README.md)

仓库收录源码、测试、构建脚本、用户手册、设计规范和历史验收记录。文档中指向 .artifacts/ 的链接属于本地证据索引，需在保留相应目录的工作区查看；GitHub 上可直接阅读结论和范围说明。运行库、App 构建产物、模型、用户资料库和本地凭据由各自环境管理。

## 交付边界

完整交付仍需指定 NVIDIA、受信 HTTPS 跨主机、同份产物跨端、干净安装、五名首次用户、达标质量与人工评审等证据。旧字幕长列表偶发空白和其余未覆盖原生路径保持待验。原型、历史失败和设计基线保留各自形成时的结论。
