# bili-to-music-cli (`b2m`)

[![PyPI](https://img.shields.io/pypi/v/bili2music.svg)](https://pypi.org/project/bili2music/)
[![Python](https://img.shields.io/pypi/pyversions/bili2music.svg)](https://pypi.org/project/bili2music/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

一个和大模型对话的 B 站下载 CLI。核心特点：**信息不全时先主动提问，整理出清单后必须你确认，才真正开始下载**。

> 已发布到 PyPI：`pipx install bili2music` → 命令 `b2m`

## 能力

| 能力 | 说明 |
| --- | --- |
| 收藏夹全量下载 | 给收藏夹链接 / fid，自动分页拉完所有条目，支持只要音频 / 只要视频 / 两者都要 |
| 关键词搜索 → 大模型整理 → 清单确认 → 下载 | 全站搜索、收藏夹内搜索或两者合并；大模型做相关度筛选、去重、排序、命名 |
| 主动提问 | 缺收藏夹、缺关键词、没说要音频还是视频、搜索范围不明时先反问；关键词太泛也会追问风格/歌手 |
| 可编辑清单 | 确认前可删减、保留、追加、改下载形态、改输出目录，甚至用编辑器改 JSON |
| 双大模型后端 | OpenAI 兼容接口（DeepSeek / 通义 / OpenAI / Kimi…）+ 本地 Ollama；**没配模型也能用**（规则式问答与排序） |
| 稳健下载 | yt-dlp + ffmpeg、Cookie 透传、跳过已下载、失败重试、并发控制、`plan.json` 可复现 |
| Agent 可调用 | `--json` 结构化输出 + `plan` 两步流程；stdout 纯 JSON、不弹提问、确认前绝不下载 |

## 安装

### 推荐：pipx（隔离安装，全局可用 `b2m` 命令）

```bash
# 先装 pipx（只需一次）
python -m pip install --user pipx
python -m pipx ensurepath        # 之后重开终端

# 安装 b2m
pipx install bili2music

b2m doctor
```

从源码或本地构建安装：

```bash
pipx install "git+https://github.com/QinzYee/bili2music_cli.git"
pipx install ./dist/bili2music-0.1.0-py3-none-any.whl
```

pipx 会把 `b2m` 放进独立环境并注入 PATH，**不污染系统 Python**，卸载用 `pipx uninstall bili2music`。

### 备选：pip / uv

```bash
pip install bili2music          # 装在当前环境
uv tool install bili2music      # uv 的隔离安装，等价 pipx
python -m bili2music doctor     # 若 PATH 未生效，用模块方式运行
```

### 源码开发模式

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"    # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # macOS / Linux
.venv/Scripts/python.exe -m bili2music doctor
```

> 依赖：`httpx`、`yt-dlp`、`rich`、`qrcode`、`imageio-ffmpeg`。其中 `imageio-ffmpeg` 提供静态 ffmpeg 二进制 —— 系统没装 ffmpeg 也能转 mp3、合并 DASH 视频流。
>
> 若默认镜像源在 pip 构建隔离环境里拉不到 `setuptools`，换官方源：`pip install -i https://pypi.org/simple ...`，或打包时加 `--no-isolation`。

## 配置与登录

首次进入对话模式会主动问两件事（都可跳过，之后用命令补）：

1. 大模型后端与凭证
2. B 站登录态（私密收藏夹必须有）

手动方式：

```bash
b2m login                                  # 扫码（终端显示二维码）或粘贴 Cookie / SESSDATA
b2m config --set llm_api_key=sk-xxx \
           --set llm_base_url=https://api.deepseek.com/v1 \
           --set llm_model=deepseek-chat
b2m config --set llm_provider=ollama --set ollama_model=qwen2.5:7b   # 换成本地模型
b2m config                                 # 查看当前配置（密钥脱敏）
b2m doctor                                 # 环境自检 + 大模型/登录态连通性
```

配置保存在 `~/.bili2music/config.toml`（权限 0600），也可用 `B2M_*` 环境变量覆盖，例如 `B2M_LLM_API_KEY`、`B2M_SESSDATA`、`B2M_OUTPUT_DIR`。常见别名 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `DEEPSEEK_API_KEY` 也会自动识别。**密钥不会写进项目目录，也不会进 git。**

收藏夹 fid 从链接里取：`https://space.bilibili.com/123/favlist?fid=123456` → `123456`，或 `b2m folders` 直接列出。

## 用法

### 对话模式（推荐）

```bash
b2m
```

```
你 > 把收藏夹 https://space.bilibili.com/123/favlist?fid=123456 里的视频音频都下了
? 下载成什么形态？            ← 主动补问缺失信息
  1. 只要音频（mp3，提取音轨）
  2. 只要完整视频（mp4）
  3. 音频 + 视频都要
> 3
...
确认下载？[y/n/命令] > rm 2,5-7     ← 先看清单，可编辑
确认下载？[y/n/命令] > y            ← 确认后才下载
```

对话命令：`/help` `/folders` `/login` `/config` `/doctor` `/dry-run`（切换只出清单）/`/yes`（切换跳过确认）/`/quit`。

### 子命令（适合脚本）

```bash
# 收藏夹全量下载
b2m favorite 123456 --mode audio -y
b2m favorite "https://space.bilibili.com/123/favlist?fid=123456" --mode both

# 搜索 → 大模型整理 → 确认 → 下载
b2m search "周杰伦 现场" --scope site --mode audio --limit 10
b2m search "坂本龙一 钢琴" --scope folder --mode audio        # 只在收藏夹里找
b2m search "lofi" --scope both --dry-run                    # 只生成清单，不下载

# 一句话直达
b2m run "搜「City Pop」，全站找，挑 8 个下成 mp3"

# 按已确认的清单下载（可复现 / Agent 第二步）
b2m plan <plan.json> --mode audio --yes
```

`--mode` / `--scope` 没给时不会乱猜，CLI 会当场问你。`--dry-run` 会把最终清单写到输出目录的 `plan.json`。

### 清单确认命令

| 命令 | 作用 |
| --- | --- |
| `y` / 回车 | 确认并下载 |
| `n` / `q` | 取消，不下载任何内容 |
| `rm 2,5-7` | 移除指定条目 |
| `keep 1,3-6` | 只保留指定条目 |
| `add BV1xx...` / `add <视频链接>` | 追加一条 |
| `info 3` | 查看第 3 条详情（链接、简介、目标文件名） |
| `mode audio\|video\|both` | 改下载形态 |
| `dir <路径>` | 改输出目录 |
| `edit` | 用 `$EDITOR`（Windows 用 notepad）直接改清单 JSON |
| `all` / `p` / `?` | 展开完整清单 / 重绘 / 帮助 |

## 在 Agent 里使用（两步流程）

> **给 AI 读的权威说明在 CLI 里，不在文档里。** 任何 Agent 只要执行一次
> `b2m agent-guide`（或 `b2m agent-guide --json`）就能拿到与当前版本匹配的完整调用约定，
> 不会因为外部文档过期而误用。把这句话告诉你的 Agent 即可。

Agent 调用需要两件事：**stdout 只给结构化 JSON**、**「出清单」和「下载」分开**，这样 Agent 可以先把清单交给人确认。所有命令加 `--json` 即进入该模式（人类可读日志全部转 stderr，不会污染 stdout），`--json` 下永不弹终端提问。

**第一步：只生成清单，绝不下载**

```bash
b2m search "周杰伦 现场" --scope site --mode audio --limit 10 --dry-run --yes --json
b2m favorite 123456 --mode both --dry-run --yes --json
b2m search "lofi" --scope folder --fav 123456 --mode audio --dry-run --yes --json
```

stdout 是一行 JSON：

```json
{
  "status": "plan_only",
  "candidates": 30,
  "plan_count": 10,
  "plan_file": ".../plan.json",
  "plan": [{"bvid": "BV...", "title": "...", "up": "...", "duration": 245,
            "filename": "...", "reason": "...", "score": 95}],
  "downloaded": 0,
  "exit_code": 0
}
```

**第二步：把清单给用户确认，确认后才下载**

Agent 应展示 `plan`，允许用户删条目、改下载形态、改输出目录，甚至直接编辑 `plan.json`；拿到明确确认后：

```bash
b2m plan <plan_file> --mode audio --yes --json
b2m plan <plan_file> --out D:/music --mode video --yes --json
```

返回 `{"status": "downloaded", "downloaded": 10, "skipped": 0, "failed": [], "outdir": "...", "exit_code": 0}`。

**给 Agent 的规则**

- 没得到用户对清单的明确确认前，不要执行任何不带 `--dry-run` 的命令，也不要对未确认的清单执行 `plan`。
- `--json` 且不带 `--yes` 时不会卡在终端：返回 `status: "needs_confirmation"`，Agent 据此去问人。
- `--json` 下不问问题，请在命令里显式给 `--mode` / `--scope` / `--limit` / `--fav`；缺失项会用默认值并体现在 `intent` 字段里。
- 失败看 `status: "error"` 和 `error` 字段；出现 `v_voucher` 风控提示时，先请用户 `b2m login`。
- 登录必须人工完成，`b2m login --json` 会明确报错。
- 其它可机读命令：`b2m folders --json`、`b2m doctor --json`、`b2m config --json`、`b2m agent-guide --json`。

## 用 AI 使用它（把这条指令发给你的 AI）

安装完成后，把下面这段直接发给你的 AI 助手（Claude Code / Cursor / WorkBuddy / ChatGPT 等任何能执行命令的 Agent）：

```
我用 b2m 下载 B 站音频/视频。请先执行 b2m agent-guide 读取权威调用说明，
然后严格按「先 --dry-run 出清单 → 我确认 → 再 plan 下载」两步流程操作。
我的需求：<这里写你要下载什么>
```

Agent 会自己跑 `b2m agent-guide` 学会全部参数和错误处理，无需你解释。如果你想把这个能力固化成一个 Skill（这样以后不用每次贴指令），见下一节。

### 作为 Skill 安装（推荐给 AI 常态化使用）

技能文件**已随 wheel 一起安装**，一条命令即可落地，不需要手抄或下载：

```bash
b2m skill                     # 自动探测已安装的 AI 工具，写入对应 skills 目录
b2m skill --target workbuddy  # 指定：workbuddy / claude / cursor / codex
b2m skill --target ~/my-agent/skills   # 或任意自定义目录
```

装好后它会提示目标路径；重启你的 AI 工具即生效。之后你说「把某个 B 站收藏夹下成 mp3」，AI 会自动触发该技能并按两步流程操作。

技能文件只依赖 PATH 上的 `b2m` 命令，不绑定任何绝对路径 —— 装在哪台机器都能用。核心内容始终来自 `b2m agent-guide`，技能文件只是触发器与铁律摘要。


## 工作流程

```
自然语言 → 规则提取 + 大模型解析槽位
        → 缺必要信息 → 主动提问（最多 2 个/轮，有兜底默认值并明确告知）
        → 收藏夹分页 / 全站搜索 → 候选
        → 大模型整理（去重、相关度排序、命名）→ 下载清单
        → 人工确认 / 编辑 → plan.json
        → yt-dlp 下载 → 汇总（成功 / 跳过 / 失败）
```

「必要槽位」只有：`task`（做什么）、`favorite_id`（哪个收藏夹）、`keyword`（搜什么）、`scope`（搜哪里）、`mode`（下成什么）。数量、音质、输出目录都有默认值，不会拿来烦你。大模型离线、返回非 JSON 或幻觉 bvid 时，会自动降级到规则问答 / 规则排序，并校验 `bvid` 必须来自候选列表。

## 下载行为

- 默认输出 `~/Music/bili2music`，文件名 `UP主 - 标题.mp3`（清洗过 Windows 非法字符）。
- `audio` 用 `FFmpegExtractAudio`；`video` 合并 DASH 为 mp4；`both` 一次下载同时产出 mp4 + mp3。
- 默认 `noplaylist=True`，一个 BV 只下第一 P，避免多 P 合集意外拉下几十个文件。
- 已存在的目标文件直接跳过（`--set overwrite=true` 可强制覆盖）。
- 登录态会写成 Netscape cookie 文件传给 yt-dlp，用于获取更高码率。
- 没有 ffmpeg 时降级为保存原始流（不转码、不合并），`doctor` 会提示。

## 常见问题

- **读不到收藏夹 / 报 `-101`**：执行 `b2m login`；私密收藏夹必须登录。
- **搜索报 `-352` / 「B 站触发风控校验（v_voucher）」/ 结果 0 条**：匿名搜索高频时 B 站会返回 `code=0` 但只给 `v_voucher` 的挑战响应。工具会显式识别、换一次匿名 buvid 并重试；仍失败请先 `b2m login` 登录、降低请求频率或稍后重试。收藏夹接口同理。
- **大模型整理很慢或报错**：换小一点的模型，或 `b2m config --set llm_provider=ollama` 走本地；工具会自动降级。
- **只想试跑不下载**：任何命令加 `--dry-run`。

## 开发

```bash
python -m unittest discover -s tests -v
```

代码结构：

```
bili2music/
  config.py              配置（TOML + 环境变量）、Cookie 文件
  models.py / utils.py   数据模型、纯函数
  bilibili/              HTTP 客户端 + WBI 签名 / 收藏夹 / 搜索 / 登录
  llm/                   OpenAI 兼容 + Ollama、提示词
  core/dialogue.py       主动提问（LLM + 确定性补问守卫）
  core/curator.py        大模型整理清单 + 降级
  core/planner.py        清单展示与可编辑确认
  core/downloader.py     yt-dlp 下载引擎
  cli.py                 REPL + 子命令 + doctor / onboarding
```

> 请仅下载你有权访问的内容，遵守 B 站服务条款与相关版权法规，勿用于公开分发。
