"""面向 AI Agent 的调用说明（`b2m agent-guide` 输出）。

指令与 CLI 版本绑定，避免外部文档过期导致 Agent 误用。
"""

GUIDE = """\
# b2m —— 面向 AI Agent 的调用说明

b2m 是 B 站（bilibili）音视频下载 CLI。你作为 Agent 调用它时，**必须遵守「先出清单、人工确认、再下载」**。

## 铁律

1. 两步走：先用 `--dry-run` 只生成清单，把清单交给用户确认，**用户明确确认后**才执行第二步下载。
2. 未经确认，绝不执行任何不带 `--dry-run` 的命令，也绝不对未确认的清单执行 `plan`。
3. 所有 Agent 调用都加 `--json`：stdout 只输出一行结构化 JSON，人类可读日志走 stderr，且绝不弹终端提问。
4. 登录必须用户本人在终端完成（`b2m login`）。不要代填 Cookie，不要把密钥写进项目目录。`--json` 模式下 login 会直接报错。
5. 仅下载用户有权访问的内容，不用于分发他人作品。

## 第一步：生成清单（不下载）

    b2m favorite <fid|收藏夹URL> --mode audio --dry-run --yes --json
    b2m search "<关键词>" --scope site --mode audio --limit 10 --dry-run --yes --json
    b2m search "<关键词>" --scope folder --fav <fid> --mode audio --dry-run --yes --json

常用参数：
- `--mode audio|video|both`  只要音频 / 只要视频 / 两者都要
- `--scope site|folder|both`  全站搜索 / 收藏夹内 / 两者
- `--fav <id|URL>`  收藏夹（`--scope folder|both` 时用）
- `--limit N`  清单最多几条
- `--out <目录>`  输出目录

返回 JSON 关键字段：`status=plan_only`、`candidates`、`plan_count`、`plan_file`、
`plan[]`（每项含 `bvid`/`title`/`up`/`duration`/`filename`/`reason`/`score`）、`downloaded=0`、`exit_code`。

**把 `plan[]` 以表格展示给用户**，说明条数、下载形态、输出目录，然后询问：是否确认？要删哪几条？要不要改形态或目录？

## 第二步：用户确认后下载

    b2m plan <plan_file> --mode audio --yes --json
    b2m plan <plan_file> --out D:/music --mode video --yes --json

返回：`status=downloaded`、`downloaded`、`skipped`、`failed[]`、`outdir`、`exit_code`。
向用户汇总结果；若有 `failed`，逐条说明原因并问是否重试。

## 其它可机读命令

    b2m folders --json    # 列出我的收藏夹（需登录）
    b2m doctor --json     # 环境自检、大模型/登录态连通性
    b2m config --json     # 查看脱敏配置

## 状态与错误处理

| status | 含义 | 你该做什么 |
| --- | --- | --- |
| `plan_only` | 只出了清单，未下载 | 展示清单并请求用户确认 |
| `needs_confirmation` | 用了 `--json` 但没给 `--yes` | 去问用户，确认后加 `--yes` 重跑第二步 |
| `downloaded` | 下载完成 | 汇总成功/跳过/失败 |
| `cancelled` | 用户取消 | 不再重试 |
| `error` | 失败 | 读 `error` 字段，向用户说明 |
| `warning` | 如 doctor 有 WARN | 说明哪些项需处理 |

常见错误：
- `v_voucher` / 「B 站触发风控校验」→ 匿名请求被限，请用户 `b2m login` 后重试或稍后再试。
- 「读取私密收藏夹需要登录」→ 同上。
- 「没有拿到候选结果」→ 换关键词 / 加 `--limit` / 登录后重试。
- 「清单为空」→ 不要进入第二步。
"""


def render() -> str:
    return GUIDE
