GCSA AI Lab — Windows UI 预览版 3.0.0

运行方法：双击同目录的 AiLab-UI.exe。
无需安装 Node.js、Python、Rust 或模型；界面可以离线打开。
请保留整个文件夹，勿单独移动 EXE，旁边的 DLL、resources 和 locales 是运行必需文件。

本版用途：浏览原项目的工作台、模型库、数据集市场、模型实验室、作品与素材；
查看弹窗，创建项目、编辑并保存本地任务草稿。
模型生成、训练、评测执行、导入导出、模型下载和远程连接尚未接入。
界面中保留的 Apple GPU / MLX 等配置来自原项目，仅供 UI 预览，不代表 Windows 支持。

预览草稿保存在当前 Windows 用户的：
%APPDATA%\GCSA-AiLab-UI-Preview
与完整版本的工作库隔离。

从源码重新构建：
1. 在项目根目录用 Node.js 24 执行 npm ci。
2. 执行 npm run build:windows-ui。首次构建会下载并校验 Electron Windows 运行时。
3. 输出位于上一级 release\GCSA-AiLab-Windows-UI。
4. 如需更改输出目录，先设置 AILAB_WINDOWS_OUTPUT_DIR 环境变量。

GitHub 下载：
本地编译和验证后上传的便携包：
https://github.com/gcsagroup/AiLab/releases/download/windows-ui-preview-20261020/GCSA-AiLab-Windows-UI-3.0-x64.zip
下载并解压后双击 AiLab-UI.exe。无需运行 GitHub Actions。
本分支已移除云端自动打包流程。

便携包 SHA-256：
8e26c0ab56363d8a1530ecc25910c714561b7699904c91bb4bc2ddde1d92287f
