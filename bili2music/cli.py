"""Command line entry point: REPL + explicit subcommands."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import __version__
from .bilibili import BiliClient, BiliError, fetch_folder, list_folders, local_filter, search_site
from .bilibili.auth import manual_login, qr_login
from .bilibili.library import Folder
from .config import CONFIG_PATH, Config, load_config, save_config
from .core.curator import build_full_plan, curate
from .core.dialogue import collect_intent
from .core.downloader import download_plan, resolve_ffmpeg
from .core.planner import confirm, save_plan
from .llm import LLMClient
from .models import MODE_LABELS, MODES, SCOPES, SCOPE_LABELS, TASK_LABELS, Intent, PlanItem
from .utils import parse_favorite_ref

COOKIE_FIELDS = {
    "SESSDATA": "sessdata",
    "bili_jct": "bili_jct",
    "DedeUserID": "dede_user_id",
    "buvid3": "buvid3",
    "buvid4": "buvid4",
}

BANNER = """[bold cyan]bili-to-music-cli[/bold cyan] [dim]v{}[/dim]
一句话说明想做什么，我会先问清必要信息，再给出清单等你确认，确认后才开始下载。
[dim]例：把收藏夹 https://space.bilibili.com/123/favlist?fid=123456 里的音频都下了
    搜「周杰伦 现场」，挑 10 个最相关的下成 mp3[/dim]
[dim]/help 查看命令 · /quit 退出 · 请仅下载你有权访问的内容，勿用于分发[/dim]"""

REPL_HELP = """[bold]对话命令[/bold]
  直接用中文描述需求，例如「搜 坂本龙一 钢琴，全站找，只要音频」
  [cyan]/folders[/cyan] 列出收藏夹   [cyan]/login[/cyan] 登录   [cyan]/config[/cyan] 查看配置
  [cyan]/doctor[/cyan] 环境自检      [cyan]/dry-run[/cyan] 切换只出清单不下载
  [cyan]/yes[/cyan] 切换跳过确认     [cyan]/help[/cyan] 帮助   [cyan]/quit[/cyan] 退出"""


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mode", choices=MODES, help="下载形态：audio / video / both")
    common.add_argument("--scope", choices=SCOPES, help="搜索范围：site / folder / both")
    common.add_argument("--limit", type=int, default=0, help="清单最多几条")
    common.add_argument("--out", help="输出目录")
    common.add_argument("-y", "--yes", action="store_true", help="跳过清单确认（脚本用）")
    common.add_argument("--dry-run", action="store_true", help="只生成清单，不下载")
    common.add_argument("--json", action="store_true",
                        help="Agent 模式：stdout 只输出结构化 JSON，人类可读日志走 stderr")

    p = argparse.ArgumentParser(prog="b2m", parents=[common],
                                description="大模型驱动的 B 站收藏夹 / 搜索下载助手",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog="不带子命令直接进入对话模式；也可 `b2m run \"把某个收藏夹的音频都下了\"`")
    p.add_argument("--version", action="version", version=f"b2m {__version__}")
    sub = p.add_subparsers(dest="cmd")

    run = sub.add_parser("run", parents=[common], help="一句话自然语言指令")
    run.add_argument("text", nargs="+", help="自然语言需求")

    fav = sub.add_parser("favorite", aliases=["fav"], parents=[common], help="下载收藏夹全部内容")
    fav.add_argument("ref", help="收藏夹 URL 或 fid 数字")

    se = sub.add_parser("search", parents=[common], help="关键词搜索 → 大模型整理 → 确认下载")
    se.add_argument("keyword", nargs="+", help="搜索关键词")
    se.add_argument("--fav", help="收藏夹 id / 链接（--scope folder 或 both 时使用）")

    pl = sub.add_parser("plan", parents=[common], help="按已确认的 plan.json 执行下载（Agent 第二步）")
    pl.add_argument("path", help="plan.json 路径")

    sub.add_parser("folders", parents=[common], help="列出我的收藏夹")
    sub.add_parser("login", parents=[common], help="扫码或粘贴 Cookie 登录 B 站")
    cfgp = sub.add_parser("config", parents=[common], help="查看/修改配置")
    cfgp.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                      help="写入配置项，可重复，如 --set llm_api_key=sk-xxx")
    sub.add_parser("doctor", parents=[common], help="环境自检")
    sub.add_parser("agent-guide", parents=[common],
                   help="输出给 AI Agent 的调用说明（Markdown，供 Agent 读取）")
    skp = sub.add_parser("skill", parents=[common],
                         help="把 Agent 技能文件装到 skills 目录（给 AI 用）")
    skp.add_argument("--target", default=None,
                     metavar="DIR|workbuddy|claude|cursor|codex",
                     help="目标 skills 根目录，或已知别名；默认自动探测")
    return p


class App:
    def __init__(self, args):
        self.args = args
        self.json_mode = bool(getattr(args, "json", False))
        # In Agent mode stdout must stay clean JSON; human logs go to stderr.
        self.console = Console(file=sys.stderr if self.json_mode else sys.stdout)
        self.result: dict = {}
        self.cfg: Config = load_config()
        if getattr(args, "out", None):
            self.cfg.output_dir = args.out
        self.llm = LLMClient(self.cfg)
        self.client: BiliClient | None = None
        self._folders: list[Folder] | None = None

    # ------------------------------------------------------------ infra
    def get_client(self) -> BiliClient:
        if self.client is None:
            self.client = BiliClient(self.cfg)
        return self.client

    def get_folders(self):
        if not self.cfg.has_login:
            return None
        if self._folders is None:
            try:
                self._folders = list_folders(self.get_client())
            except Exception as exc:
                self.console.print(f"[dim]收藏夹列表读取失败：{exc}[/dim]")
                self._folders = []
        return self._folders

    def outdir(self, intent: Intent) -> Path:
        return Path(intent.output_dir).expanduser() if intent.output_dir else self.cfg.output_path

    def preset(self) -> Intent:
        a = self.args
        return Intent(mode=getattr(a, "mode", "") or "", scope=getattr(a, "scope", "") or "",
                      limit=getattr(a, "limit", 0) or 0,
                      output_dir=getattr(a, "out", "") or "")

    # ------------------------------------------------------------ dispatch
    def dispatch(self) -> int:
        a = self.args
        if a.cmd is None:
            if self.json_mode:
                self.result["error"] = "--json 模式需要显式子命令（search / favorite / plan / folders / doctor / config）"
                return 1
            if not sys.stdin.isatty():
                text = sys.stdin.read().strip()
                if text:
                    return self.handle(text)
            return self.repl()
        if a.cmd == "run":
            return self.handle(" ".join(a.text), self.preset())
        if a.cmd in ("favorite", "fav"):
            preset = self.preset()
            preset.task = "favorite"
            preset.favorite_id = parse_favorite_ref(a.ref) or a.ref
            return self.handle(f"下载收藏夹 {a.ref} 的全部内容", preset)
        if a.cmd == "search":
            preset = self.preset()
            preset.task = "search"
            preset.keyword = " ".join(a.keyword)
            if getattr(a, "fav", None):
                preset.favorite_id = parse_favorite_ref(a.fav) or a.fav
            return self.handle(f"搜索「{preset.keyword}」并筛选后下载", preset)
        if a.cmd == "plan":
            return self.cmd_plan()
        if a.cmd == "folders":
            return self.cmd_folders()
        if a.cmd == "login":
            if self.json_mode:
                self.result["error"] = ("登录需要交互（扫码或粘贴 Cookie），请由用户在终端执行 "
                                        "`b2m login`；--json 模式不支持登录")
                return 1
            return self.cmd_login()
        if a.cmd == "config":
            return self.cmd_config()
        if a.cmd == "doctor":
            return self.cmd_doctor()
        if a.cmd == "agent-guide":
            from .agent_guide import render

            guide = render()
            if self.json_mode:
                self.result["guide"] = guide
                self.result["status"] = "ok"
                return 0
            self.console.print(guide)
            return 0
        if a.cmd == "skill":
            from .skill_install import install, resolve_target

            try:
                target_dir = resolve_target(getattr(a, "target", None))
                path = install(target_dir)
            except (OSError, RuntimeError) as exc:
                self.result["error"] = f"技能安装失败：{exc}"
                return 1
            msg = f"技能已安装到 {path}"
            if self.json_mode:
                self.result["path"] = str(path)
                self.result["status"] = "ok"
                return 0
            self.console.print(f"[green]{msg}[/green]")
            self.console.print(
                "重启你的 AI 工具后生效；之后遇到「下载 B 站音频」会自动触发该技能。"
            )
            return 0
        return 1

    def repl(self) -> int:
        self.console.print(BANNER.format(__version__))
        if not CONFIG_PATH.exists():
            self.onboard()
        while True:
            try:
                line = self.console.input("\n[bold]你 > [/bold]").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]再见。[/dim]")
                break
            if not line:
                continue
            if line.lower() in ("/quit", "/exit", "quit", "exit", "q"):
                self.console.print("[dim]再见。[/dim]")
                break
            if line == "/help":
                self.console.print(REPL_HELP)
            elif line == "/folders":
                self.cmd_folders()
            elif line == "/login":
                self.cmd_login()
            elif line == "/config":
                self.cmd_config()
            elif line == "/doctor":
                self.cmd_doctor()
            elif line == "/dry-run":
                self.args.dry_run = not self.args.dry_run
                self.console.print(f"[green]dry-run = {self.args.dry_run}[/green]")
            elif line == "/yes":
                self.args.yes = not self.args.yes
                self.console.print(f"[green]跳过确认 = {self.args.yes}[/green]")
            else:
                self.handle(line)
        if self.client:
            self.client.close()
        return 0

    # ------------------------------------------------------------ pipeline
    def handle(self, raw: str, preset: Intent | None = None) -> int:
        self.console.print(f"[dim]▸ {escape(raw)}[/dim]")
        try:
            intent = collect_intent(self.llm, self.cfg, raw, self.get_folders(),
                                    self.console, preset,
                                    non_interactive=bool(self.args.yes) or self.json_mode
                                                    or not sys.stdin.isatty())
        except Exception as exc:
            self.console.print(f"[red]意图解析失败：{exc}[/red]")
            self.result["error"] = f"意图解析失败：{exc}"
            return 1
        summary = (f"{TASK_LABELS.get(intent.task, intent.task)}"
                   + (f" · 关键词「{intent.keyword}」" if intent.keyword else "")
                   + (f" · {SCOPE_LABELS.get(intent.scope, '')}" if intent.scope else "")
                   + (f" · {MODE_LABELS.get(intent.mode, '')}" if intent.mode else ""))
        self.console.print(f"[bold]执行计划：[/bold]{summary}")
        self.result["intent"] = intent.as_dict()
        self.result["summary"] = summary
        try:
            return self.execute(intent)
        except BiliError as exc:
            self.console.print(f"[red]{exc}[/red]")
            self.result["error"] = str(exc)
            return 1
        except Exception as exc:
            self.console.print(f"[red]执行失败：{type(exc).__name__}: {exc}[/red]")
            self.result["error"] = f"{type(exc).__name__}: {exc}"
            return 1

    def execute(self, intent: Intent) -> int:
        if intent.task == "folders":
            return self.cmd_folders()
        if intent.task == "config":
            return self.cmd_config()
        if intent.task not in ("favorite", "search", "folder_search"):
            self.console.print("[yellow]任务不明确，未执行任何下载。[/yellow]")
            return 1

        client = self.get_client()
        plan = []
        if intent.task == "favorite":
            if not intent.favorite_id:
                self.console.print("[red]没有指定收藏夹，已取消（不会下载任何内容）。[/red]")
                return 1
            self.console.print(f"[dim]正在分页拉取收藏夹 {intent.favorite_id} 的全部内容…[/dim]")
            name, items = fetch_folder(client, intent.favorite_id, limit=intent.limit,
                                       on_page=lambda pn, n, total: self.console.print(
                                           f"[dim]  第 {pn} 页 / 本页 {n} 条 / 共约 {total} 条[/dim]"))
            self.console.print(f"[green]收藏夹「{name or intent.favorite_id}」共 {len(items)} 条[/green]")
            self.result["folder_items"] = len(items)
            if not items and not self.cfg.has_login:
                self.console.print("[yellow]返回 0 条：可能是 id 无效、收藏夹为空，或未登录读不到私密收藏夹。"
                                   "建议先 `b2m login` 再用 `b2m folders` 确认 id。[/yellow]")
            plan = build_full_plan(items)
            self.console.print("[dim]全量下载模式：不交给大模型筛选（要智能筛选请用关键词搜索）。[/dim]")
        else:
            candidates = []
            want = max(30, (intent.limit or self.cfg.max_results) * 3)
            if intent.scope in ("site", "both"):
                self.console.print(f"[dim]全站搜索「{intent.keyword}」…[/dim]")
                found = search_site(client, intent.keyword, limit=want,
                                    on_page=lambda pn, n, total: self.console.print(
                                        f"[dim]  搜索第 {pn} 页，本页 {n} 条，约 {total} 条结果[/dim]"))
                self.console.print(f"[green]全站候选 {len(found)} 条[/green]")
                candidates.extend(found)
            if intent.scope in ("folder", "both"):
                fid = intent.favorite_id
                if not fid:
                    if self.json_mode:
                        self.result["error"] = ("收藏夹内搜索需要指定收藏夹："
                                                "`b2m search ... --scope folder --fav <id|链接> --json`")
                        return 1
                    self.console.print("[yellow]需要指定在哪个收藏夹内查找。[/yellow]")
                    self.cmd_folders()
                    answer = self.console.input("[cyan]收藏夹 id / 链接> [/cyan]").strip()
                    fid = parse_favorite_ref(answer)
                    if not fid:
                        self.console.print("[red]未提供有效收藏夹，已取消。[/red]")
                        return 1
                    intent.favorite_id = fid
                _, items = fetch_folder(client, fid)
                hits = local_filter(items, intent.keyword, cap=60)
                self.console.print(f"[green]收藏夹内 {len(items)} 条，初筛命中 {len(hits)} 条[/green]")
                candidates.extend(hits)
            # de-duplicate by bvid, favorites win over search results
            uniq = {}
            for v in candidates:
                if v.bvid and v.bvid not in uniq:
                    uniq[v.bvid] = v
            candidates = list(uniq.values())
            if not candidates:
                self.console.print("[yellow]没有拿到候选结果：可能是关键词过窄、B 站临时风控或未登录。"
                                   "建议 `b2m login` 后重试，或换个关键词 / 稍后再试。[/yellow]")
                self.result["candidates"] = 0
                self.result["error"] = "没有拿到候选结果（可能是 B 站风控或未登录）"
                return 1
            self.result["candidates"] = len(candidates)
            self.console.print(f"[bold]共 {len(candidates)} 条候选，交给大模型整理…[/bold]")
            plan = curate(self.llm, self.cfg, intent, candidates, self.console)

        return self._finalize(plan, intent, client)

    # ------------------------------------------------------------ agent API
    @staticmethod
    def _brief_plan(plan: list[PlanItem]) -> list[dict]:
        """Compact, stable schema for Agent consumption."""
        return [{"bvid": p.video.bvid, "title": p.video.title, "up": p.video.owner,
                 "duration": p.video.duration, "filename": p.filename,
                 "reason": p.reason, "score": p.score} for p in plan]

    def _finalize(self, plan: list[PlanItem], intent: Intent, client=None) -> int:
        """Single place where a plan becomes a confirmation and (maybe) a download."""
        self.result["plan_count"] = len(plan)
        self.result["plan"] = self._brief_plan(plan)
        if not plan:
            self.console.print("[yellow]没有生成任何清单条目，已停止（未下载）。[/yellow]")
            self.result["error"] = "清单为空"
            return 0

        # --json must never block on a terminal prompt: let the Agent confirm.
        if self.json_mode and not self.args.yes:
            if self.args.dry_run:
                path = save_plan(plan, intent, self.outdir(intent))
                self.result["plan_file"] = str(path)
            self.result.update({"status": "needs_confirmation", "downloaded": 0})
            return 0

        confirmed = confirm(self.console, plan, intent, self.cfg, client=client,
                            assume_yes=self.args.yes, dry_run=self.args.dry_run)
        if confirmed is None:
            self.result.update({"cancelled": True, "downloaded": 0, "status": "cancelled"})
            return 0
        self.result["confirmed_count"] = len(confirmed)
        outdir = self.outdir(intent)
        if self.args.dry_run:
            path = save_plan(confirmed, intent, outdir)
            self.console.print(f"[green]dry-run 完成：仅生成清单 {path}，未下载任何文件。[/green]")
            self.result.update({"plan_file": str(path), "downloaded": 0,
                                "status": "plan_only", "outdir": str(outdir)})
            return 0

        self.console.print("[dim]提示：请仅保存你有权访问的内容，遵守平台条款与版权法规。[/dim]")
        stats = download_plan(confirmed, intent.mode, self.cfg, self.console, output_dir=outdir)
        self.console.print(f"[bold green]完成：新下载 {stats['ok']} 条，跳过 {stats['skipped']} 条，"
                           f"失败 {len(stats['failed'])} 条 → {stats['outdir']}[/bold green]")
        self.result.update({
            "status": "downloaded", "downloaded": stats["ok"], "skipped": stats["skipped"],
            "failed": [{"filename": s, "error": m} for s, m in stats["failed"]],
            "outdir": stats["outdir"], "ffmpeg": stats["ffmpeg"],
        })
        return 0 if not stats["failed"] else 1

    def cmd_plan(self) -> int:
        """Second step for Agents: execute an already-reviewed plan.json."""
        path = Path(self.args.path).expanduser()
        if not path.is_file():
            msg = f"清单文件不存在：{path}"
            self.console.print(f"[red]{msg}[/red]")
            self.result["error"] = msg
            return 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            plan = [PlanItem.from_dict(d) for d in data.get("items", [])]
        except (OSError, ValueError, TypeError) as exc:
            self.console.print(f"[red]清单解析失败：{exc}[/red]")
            self.result["error"] = f"清单解析失败：{exc}"
            return 1
        if not plan:
            self.console.print("[yellow]清单为空，没有可下载的内容。[/yellow]")
            self.result.update({"error": "清单为空", "plan_count": 0})
            return 1

        mode = getattr(self.args, "mode", None) or data.get("mode") or "audio"
        intent = Intent(task=data.get("task") or "favorite",
                        keyword=data.get("keyword") or "",
                        favorite_id=str(data.get("favorite_id") or ""),
                        scope=data.get("scope") or "",
                        mode=mode if mode in MODES else "audio",
                        output_dir=getattr(self.args, "out", None) or data.get("output_dir") or "")
        self.result.update({"plan_file": str(path), "source": "plan.json",
                            "intent": intent.as_dict()})
        self.console.print(f"[dim]读取清单 {path}（{len(plan)} 条，形态 {intent.mode}）[/dim]")
        if self.args.dry_run:
            self.result.update({"status": "plan_only", "downloaded": 0,
                                "plan_count": len(plan), "plan": self._brief_plan(plan)})
            return 0
        return self._finalize(plan, intent)

    # ------------------------------------------------------------ commands
    def cmd_folders(self) -> int:
        if not self.cfg.has_login:
            msg = "读取私密收藏夹需要登录，请先 `b2m login`。"
            self.console.print(f"[yellow]{msg}[/yellow]")
            self.result["error"] = msg
            return 1
        try:
            folders = list_folders(self.get_client())
        except BiliError as exc:
            self.console.print(f"[red]{exc}[/red]")
            self.result["error"] = str(exc)
            return 1
        self.result["folders"] = [{"id": f.id, "title": f.title, "count": f.count}
                                  for f in folders]
        if not folders:
            self.console.print("[yellow]没有读到收藏夹。[/yellow]")
            return 0
        t = Table(title="我的收藏夹")
        t.add_column("id", style="cyan")
        t.add_column("名称")
        t.add_column("数量", justify="right")
        for f in folders:
            t.add_row(f.id, f.title, str(f.count))
        self.console.print(t)
        self.console.print("[dim]用法：b2m favorite <id> --mode audio[/dim]")
        return 0

    def cmd_login(self) -> int:
        self.console.print("[bold]B 站登录方式[/bold]\n  1. 扫码登录（推荐）\n  2. 粘贴 Cookie / SESSDATA")
        choice = self.console.input("[cyan]选择 [1/2]> [/cyan]").strip()
        try:
            creds = qr_login(self.console, self.cfg) if choice == "1" else manual_login(self.console)
        except Exception as exc:
            self.console.print(f"[red]登录失败：{exc}[/red]")
            return 1
        for key, field_name in COOKIE_FIELDS.items():
            if creds.get(key):
                setattr(self.cfg, field_name, creds[key])
        path = save_config(self.cfg)
        if self.client:
            self.client.refresh_cookies()
        self._folders = None
        self.console.print(f"[green]登录信息已保存到 {path}[/green]")
        try:
            ok = self.get_client().is_logged_in()
            self.console.print("[green]登录态校验通过。[/green]" if ok
                               else "[yellow]Cookie 已保存，但 B 站未确认登录态，请检查是否过期。[/yellow]")
        except Exception as exc:
            self.console.print(f"[yellow]登录态校验未完成：{exc}[/yellow]")
        return 0

    def cmd_config(self) -> int:
        sets = getattr(self.args, "set", []) or []
        if sets:
            for pair in sets:
                key, sep, value = pair.partition("=")
                key = key.strip()
                if not sep or key not in Config.__dataclass_fields__:
                    self.console.print(f"[red]忽略无效配置：{pair}[/red]")
                    continue
                sample = getattr(Config(), key)
                if isinstance(sample, bool):
                    value = value.lower() in ("1", "true", "yes", "on")
                elif isinstance(sample, int):
                    try:
                        value = int(value)
                    except ValueError:
                        self.console.print(f"[red]{key} 需要整数[/red]")
                        continue
                setattr(self.cfg, key, value)
            self.console.print(f"[green]已保存配置 → {save_config(self.cfg)}[/green]")
            self.llm = LLMClient(self.cfg)
            self.result.update({"status": "config_saved", "config": self.cfg.public_dict()})
            return 0
        self.result["config"] = self.cfg.public_dict()
        t = Table(title=f"当前配置（{CONFIG_PATH}）")
        t.add_column("配置项", style="cyan")
        t.add_column("值")
        for k, v in self.cfg.public_dict().items():
            t.add_row(k, str(v))
        self.console.print(t)
        self.console.print("[dim]修改示例：b2m config --set llm_api_key=sk-xxx "
                           "--set llm_model=deepseek-chat；也可编辑上面的 TOML 文件。[/dim]")
        return 0

    def cmd_doctor(self) -> int:
        rows: list[tuple[str, bool, str]] = []
        rows.append(("Python", True, sys.version.split()[0]))
        try:
            rows.append(("yt-dlp", True, importlib.metadata.version("yt-dlp")))
        except importlib.metadata.PackageNotFoundError:
            rows.append(("yt-dlp", False, "未安装：pip install yt-dlp"))
        ff = resolve_ffmpeg(self.cfg)
        rows.append(("ffmpeg", bool(ff), ff or "未找到：pip install imageio-ffmpeg"))
        rows.append(("大模型配置", self.cfg.llm_ready(),
                     f"{self.cfg.llm_provider} / "
                     f"{self.cfg.ollama_model if self.cfg.llm_provider == 'ollama' else self.cfg.llm_model}"))
        if self.cfg.llm_ready():
            ok, msg = self.llm.ping()
            rows.append(("大模型连通性", ok, msg))
        rows.append(("B 站登录态", self.cfg.has_login,
                     "已配置 SESSDATA" if self.cfg.has_login else "未登录（公开收藏夹/全站搜索仍可用）"))
        if self.cfg.has_login:
            try:
                ok = self.get_client().is_logged_in()
                rows.append(("B 站登录校验", ok, "有效" if ok else "Cookie 可能已过期，请 b2m login"))
            except Exception as exc:
                rows.append(("B 站登录校验", False, str(exc)[:80]))
        out = self.cfg.output_path
        try:
            out.mkdir(parents=True, exist_ok=True)
            rows.append(("输出目录", True, str(out)))
        except OSError as exc:
            rows.append(("输出目录", False, str(exc)))

        t = Table(title="环境自检")
        t.add_column("检查项")
        t.add_column("状态", width=8)
        t.add_column("说明", overflow="fold")
        for name, ok, detail in rows:
            t.add_row(name, "[green]OK[/green]" if ok else "[yellow]WARN[/yellow]", detail)
        self.console.print(t)
        self.result["doctor"] = [{"name": n, "ok": o, "detail": d} for n, o, d in rows]
        return 0 if all(r[1] for r in rows) else 1

    # ------------------------------------------------------------ onboarding
    def onboard(self) -> None:
        """First run: proactively ask only for the two things that block usage."""
        if not sys.stdin.isatty():
            return
        self.console.print("\n[bold]首次使用，有两项配置会直接影响功能，现在补齐？（随时可跳过）[/bold]")
        if not self.cfg.llm_ready():
            self.console.print("[cyan]1) 大模型：[/cyan] 1 OpenAI 兼容（DeepSeek/通义/OpenAI）"
                               "  2 本地 Ollama  3 稍后")
            c = self.console.input("[cyan]选择 [1/2/3]> [/cyan]").strip()
            if c == "1":
                self.cfg.llm_provider = "openai"
                self.cfg.llm_base_url = (self.console.input(
                    f"[cyan]API Base URL [{self.cfg.llm_base_url}]> [/cyan]").strip()
                                        or self.cfg.llm_base_url)
                self.cfg.llm_model = (self.console.input(
                    f"[cyan]模型名 [{self.cfg.llm_model}]> [/cyan]").strip() or self.cfg.llm_model)
                self.cfg.llm_api_key = self.console.input("[cyan]API Key> [/cyan]").strip()
            elif c == "2":
                self.cfg.llm_provider = "ollama"
                self.cfg.ollama_model = (self.console.input(
                    f"[cyan]Ollama 模型 [{self.cfg.ollama_model}]> [/cyan]").strip()
                                         or self.cfg.ollama_model)
        if not self.cfg.has_login:
            self.console.print("[cyan]2) B 站登录：[/cyan] 1 扫码登录  2 粘贴 Cookie  3 稍后"
                               "（私密收藏夹必须登录；全站搜索可匿名）")
            c = self.console.input("[cyan]选择 [1/2/3]> [/cyan]").strip()
            if c in ("1", "2"):
                try:
                    creds = qr_login(self.console, self.cfg) if c == "1" else manual_login(self.console)
                    for key, field_name in COOKIE_FIELDS.items():
                        if creds.get(key):
                            setattr(self.cfg, field_name, creds[key])
                except Exception as exc:
                    self.console.print(f"[yellow]登录未完成：{exc}（可之后执行 b2m login）[/yellow]")
        try:
            path = save_config(self.cfg)
            self.console.print(f"[green]配置已保存到 {path}，之后可用 `b2m config` 修改。[/green]")
        except OSError as exc:
            self.console.print(f"[yellow]配置保存失败：{exc}[/yellow]")
        self.llm = LLMClient(self.cfg)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    app = App(args)
    rc = 0
    try:
        rc = app.dispatch()
    except KeyboardInterrupt:
        app.console.print("\n[yellow]已中断。[/yellow]")
        app.result["error"] = "用户中断"
        rc = 130
    except BiliError as exc:
        app.console.print(f"[red]{exc}[/red]")
        app.result["error"] = str(exc)
        rc = 1
    finally:
        if app.client:
            app.client.close()

    if getattr(args, "json", False):
        if "error" in app.result:
            app.result["status"] = "error"
        elif rc != 0:
            app.result["status"] = "warning"
        else:
            app.result.setdefault("status", "ok")
        app.result["exit_code"] = rc
        sys.stdout.write(json.dumps(app.result, ensure_ascii=False, default=str) + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
