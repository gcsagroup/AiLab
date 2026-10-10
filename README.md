# GCSA AI Lab

[简体中文](README.md) · [繁體中文](i18n/zh-TW/README.md) · [English](i18n/en/README.md) · [日本語](i18n/ja/README.md) · [한국어](i18n/ko/README.md) · [Français](i18n/fr/README.md) · [Português](i18n/pt/README.md)

GCSA AI Lab 是用于本地模型试用、LoRA 微调、评测和作品管理的桌面工作台。项目把模型、数据、任务与输出保存在一起，便于继续任务和追溯结果。

当前版本为 **Ver2.7（054），技术预览**。已在原生 App 中通过 SSH 隧道验证 Qwen2.5-0.5B-Instruct 的 Jetson Orin 生成、两步 LoRA 训练、产物回收，以及同份适配器在 Apple GPU 上运行。此验证限于指定模型和环境，不代表质量提升；直接 HTTPS 部署、干净安装、首次用户测试及正式发行验收仍未完成。当前没有已验收的正式安装包或自动更新渠道。

- 文字生成、SFT + LoRA 微调及基线／候选评测。
- 图片生成与实验性图片 LoRA，视频生成、配音和转写入口。视频和音频训练尚未开放。
- 数据导入、来源组划分、运行历史、作品修订、导出和备份恢复。

可运行范围取决于具体模型、设备、引擎和精度，开始前以配置检查结果为准。现有质量实验仍有失败项，不能把训练完成当作质量合格。文档提供七种语言；这不代表应用界面支持七种语言。

[用户手册](docs/USER_GUIDE.md) · [更新记录](CHANGELOG.md) · [GitHub](https://github.com/gcsagroup/AiLab)
