# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-11-12

首个公开发布（PyPI: `bili2music`）。

### 新增
- 收藏夹全量下载：支持收藏夹链接或 fid，自动分页，可选只要音频 / 只要视频 / 两者都要
- 关键词搜索 → 大模型整理（去重、相关度排序、命名）→ 清单确认 → 下载
- 强制两步流程：先出清单、人工确认，确认前绝不下载
- 双大模型后端：OpenAI 兼容接口（DeepSeek / 通义 / OpenAI / Kimi 等）+ 本地 Ollama；
  模型不可用时自动降级为规则式问答与排序
- `--json` 结构化输出：stdout 纯 JSON、人类可读日志走 stderr、不弹终端提问，适合 Agent 调用
- `b2m agent-guide`：面向 AI Agent 的调用说明内嵌于 CLI，随版本更新
- `b2m skill`：把路径无关的 SKILL.md 装到 WorkBuddy / Claude / Cursor / Codex 技能目录
- `b2m doctor` 环境自检、`b2m login` 扫码登录、`b2m folders` 列出收藏夹、`b2m config` 配置管理
- 下载侧：yt-dlp + imageio-ffmpeg（自带静态 ffmpeg）、Cookie 透传、跳过已存在文件、
  失败重试、并发控制、`plan.json` 可复现

### 说明
- 许可证：MIT
- 仅用于下载用户有权访问的内容，不用于分发他人作品
