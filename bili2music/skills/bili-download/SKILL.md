---
name: bili-download
description: 用 b2m CLI 下载 B 站（bilibili）收藏夹的视频或音频，或按关键词搜索、经大模型整理后生成下载清单再下载。当用户要求下载 B 站视频、提取音频/转 mp3/m4a/flac、整理收藏夹、搜索 B 站内容并下载、查看 B 站收藏夹、把 B 站歌单转成音乐文件时使用。
---

# bili-download（b2m CLI）

`b2m` 是一个已安装到 PATH 的 B 站音视频下载 CLI。**本技能不假设任何项目路径**，所有命令直接用 `b2m`。

## 第一步永远是读权威说明

```bash
b2m agent-guide        # Markdown，给人看或你自己读
b2m agent-guide --json # {"status":"ok","guide":"<完整说明>"}
```

`agent-guide` 的内容与 CLI 版本绑定，比任何外部文档都新。**如果本技能与 `agent-guide` 冲突，以 `agent-guide` 为准。**
若命令不存在，说明环境没装好，先跑 `b2m doctor` 排查，不要自己猜参数。

## 铁律（必须遵守）

1. **两步走**：先只生成清单（`--dry-run`），把清单交给用户确认，**确认之后**才下载。
2. 未经用户对清单的明确确认，绝不执行任何不带 `--dry-run` 的命令，也绝不对未确认清单执行 `plan`。
3. 所有 Agent 调用都加 `--json`：stdout 只有一行结构化 JSON，人类可读日志走 stderr，且不会弹终端提问。
4. 登录必须用户本人在终端完成（`b2m login`）。不要代填 Cookie，不要把密钥写进任何项目目录。
5. 仅下载用户有权访问的内容，不用于分发他人作品。

## 快速命令模板

```bash
# 第一步：出清单，不下载
b2m favorite <fid|收藏夹URL> --mode audio --dry-run --yes --json
b2m search "<关键词>" --scope site --mode audio --limit 10 --dry-run --yes --json
b2m search "<关键词>" --scope folder --fav <fid> --mode audio --dry-run --yes --json

# 第二步：用户确认后下载
b2m plan <plan_file> --mode audio --yes --json
```

参数：`--mode audio|video|both`、`--scope site|folder|both`、`--fav <id|URL>`、`--limit N`、`--out <目录>`。

返回 `status=plan_only` 时，把 `plan[]`（含 `bvid`/`title`/`up`/`duration`/`filename`/`reason`/`score`）
以表格展示给用户，说明条数、下载形态、输出目录，然后询问是否确认、要删哪几条、要不要改形态或目录。

## 其它可机读命令

```bash
b2m folders --json    # 列出收藏夹（需登录）
b2m doctor --json     # 环境自检、大模型/登录态连通性
b2m config --json     # 查看脱敏配置
```

## 状态处理

| status | 含义 | 你该做什么 |
| --- | --- | --- |
| `plan_only` | 只出了清单，未下载 | 展示清单并请求用户确认 |
| `needs_confirmation` | 用了 `--json` 但没给 `--yes` | 去问用户，确认后加 `--yes` 重跑 |
| `downloaded` | 下载完成 | 汇总成功/跳过/失败 |
| `cancelled` | 用户取消 | 不再重试 |
| `error` | 失败 | 读 `error` 字段，向用户说明 |
| `warning` | 如 doctor 有 WARN | 说明哪些项需处理 |

常见错误：
- `v_voucher` / 「B 站触发风控校验」→ 匿名请求被限，请用户 `b2m login` 后重试或稍后再试。
- 「读取私密收藏夹需要登录」→ 同上。
- 「没有拿到候选结果」→ 换关键词 / 加 `--limit` / 登录后重试。
- 「清单为空」→ 不要进入第二步。

## 首次使用引导

用户第一次使用时，按顺序确认（不要一次性问一堆）：

1. `b2m doctor --json` → 若大模型配置缺失，告知用户「不配也能用，会自动降级为规则式筛选」，需要时再引导 `b2m config --set llm_api_key=...`。
2. 若要访问私密收藏夹，请用户自己执行 `b2m login`（扫码或粘贴 Cookie）。
3. 再开始第一步出清单。
