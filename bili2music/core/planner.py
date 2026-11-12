"""Render and confirm the download list. Nothing is downloaded before a `y`."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..config import Config
from ..models import Intent, MODE_LABELS, PlanItem
from ..utils import extract_bvid, parse_selection

HELP = """\
[bold]清单命令[/bold]
  [cyan]y[/cyan] / 回车      确认并下载当前清单
  [cyan]n[/cyan] / q        取消，不下载任何内容
  [cyan]rm 2,5-7[/cyan]     从清单中移除指定条目
  [cyan]keep 1,3-6[/cyan]   只保留指定条目
  [cyan]add BV... / URL[/cyan]  追加一个视频
  [cyan]info 3[/cyan]       查看第 3 条的完整信息
  [cyan]mode audio|video|both[/cyan]  改下载形态
  [cyan]dir <路径>[/cyan]   改输出目录
  [cyan]edit[/cyan]         用编辑器直接改清单 JSON
  [cyan]all[/cyan]          显示/隐藏完整清单
  [cyan]p[/cyan]            重新打印清单
  [cyan]?[/cyan]            显示本帮助
"""


def render_plan(console: Console, plan: list[PlanItem], intent: Intent,
                outdir: Path, show_all: bool = False, max_rows: int = 25) -> None:
    table = Table(title=f"下载清单（{len(plan)} 条） · {MODE_LABELS.get(intent.mode, intent.mode)}"
                        f" · 输出：{outdir}", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("标题", overflow="fold", max_width=42)
    table.add_column("UP 主", overflow="fold", max_width=16)
    table.add_column("时长", width=8, justify="right")
    table.add_column("分", width=5, justify="right")
    table.add_column("理由 / 目标文件名", overflow="fold", max_width=44)

    rows = plan if show_all else plan[:max_rows]
    for i, p in enumerate(rows, 1):
        v = p.video
        note = (p.reason or "").strip()
        detail = f"[dim]{p.filename}[/dim]"
        table.add_row(str(i), v.title, v.owner, v.duration_str,
                      f"{p.score:.0f}", f"{note}\n{detail}" if note else detail)
    console.print(table)
    if not show_all and len(plan) > max_rows:
        console.print(f"[dim]… 还有 {len(plan) - max_rows} 条未显示，输入 `all` 查看全部。[/dim]")
    if not plan:
        console.print("[yellow]清单为空，输入 `add BV号` 追加，或 `n` 取消。[/yellow]")


def save_plan(plan: list[PlanItem], intent: Intent, outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "plan.json"
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "task": intent.task, "keyword": intent.keyword, "favorite_id": intent.favorite_id,
        "scope": intent.scope, "mode": intent.mode, "output_dir": str(outdir),
        "count": len(plan),
        "items": [p.to_dict() for p in plan],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _editor_cmd() -> list[str]:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        return [editor]
    return ["notepad"] if sys.platform == "win32" else ["vi"]


def _open_in_editor(path: Path) -> bool:
    try:
        return subprocess.run(_editor_cmd() + [str(path)], check=False).returncode == 0
    except (OSError, ValueError):
        return False


def confirm(console: Console, plan: list[PlanItem], intent: Intent, cfg: Config,
            *, client=None, assume_yes: bool = False, dry_run: bool = False) -> list[PlanItem] | None:
    """Interactive confirmation loop. Returns the final list, or None on cancel."""
    if assume_yes:
        console.print(f"[green]--yes 已指定，跳过确认：{len(plan)} 条待下载。[/green]")
        return plan

    outdir = Path(intent.output_dir).expanduser() if intent.output_dir else cfg.output_path
    show_all = False
    console.print(HELP)
    if dry_run:
        console.print("[yellow]dry-run 模式：确认后只保存清单，不会下载文件。[/yellow]")
    render_plan(console, plan, intent, outdir, show_all)

    while True:
        try:
            line = console.input("\n[bold green]确认下载？[y/n/命令] > [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]已取消。[/yellow]")
            return None
        if not line or line.lower() in ("y", "yes", "ok", "确认", "是"):
            if not plan:
                console.print("[yellow]清单为空，没有可下载的内容。[/yellow]")
                continue
            path = save_plan(plan, intent, outdir)
            console.print(f"[dim]清单已保存到 {path}[/dim]")
            return plan
        if line.lower() in ("n", "no", "q", "quit", "cancel", "否", "取消"):
            console.print("[yellow]已取消，未下载任何内容。[/yellow]")
            return None
        if line in ("?", "help", "h"):
            console.print(HELP)
            continue
        if line in ("p", "print", "ls"):
            render_plan(console, plan, intent, outdir, show_all)
            continue
        if line == "all":
            show_all = not show_all
            render_plan(console, plan, intent, outdir, show_all)
            continue

        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower().strip(), arg.strip()
        if cmd in ("rm", "del", "remove"):
            idx = parse_selection(arg, len(plan))
            if not idx:
                console.print("[red]没有匹配到条目，示例：`rm 2,5-7`[/red]")
                continue
            plan = [p for i, p in enumerate(plan, 1) if i not in idx]
            console.print(f"[green]已移除 {len(idx)} 条，剩余 {len(plan)} 条。[/green]")
            render_plan(console, plan, intent, outdir, show_all)
        elif cmd == "keep":
            idx = parse_selection(arg, len(plan))
            if not idx:
                console.print("[red]没有匹配到条目，示例：`keep 1,3-6`[/red]")
                continue
            plan = [p for i, p in enumerate(plan, 1) if i in idx]
            console.print(f"[green]已保留 {len(plan)} 条。[/green]")
            render_plan(console, plan, intent, outdir, show_all)
        elif cmd == "info":
            idx = parse_selection(arg, len(plan))
            if not idx:
                console.print("[red]示例：`info 3`[/red]")
                continue
            for i in sorted(idx):
                p = plan[i - 1]
                v = p.video
                console.print(f"[bold]#{i} {v.title}[/bold]\n"
                              f"  {v.url}\n  UP：{v.owner}   时长：{v.duration_str}   "
                              f"来源：{v.source or '-'} {v.folder}\n"
                              f"  文件名：{p.filename}\n  理由：{p.reason}\n"
                              f"  简介：{v.description[:200]}")
        elif cmd == "add":
            bvid = extract_bvid(arg)
            if not bvid:
                console.print("[red]请输入 BV 号或 B 站视频链接。[/red]")
                continue
            if any(p.video.bvid == bvid for p in plan):
                console.print("[yellow]该视频已在清单中。[/yellow]")
                continue
            if client is None:
                console.print("[red]当前无法读取视频信息（API 客户端不可用）。[/red]")
                continue
            try:
                from ..bilibili.library import video_by_bvid
                from .curator import default_filename
                v = video_by_bvid(client, bvid)
                plan.append(PlanItem(video=v, filename=default_filename(v),
                                     reason="手动追加", score=100))
                console.print(f"[green]已追加：{v.title}[/green]")
                render_plan(console, plan, intent, outdir, show_all)
            except Exception as exc:
                console.print(f"[red]追加失败：{exc}[/red]")
        elif cmd == "mode" and arg in MODE_LABELS:
            intent.mode = arg
            console.print(f"[green]下载形态改为：{MODE_LABELS[arg]}[/green]")
        elif cmd == "dir" and arg:
            intent.output_dir = arg
            outdir = Path(arg).expanduser()
            console.print(f"[green]输出目录改为：{outdir}[/green]")
        elif cmd == "edit":
            tmp = Path(cfg.output_path) / "plan_edit.json"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps([p.to_dict() for p in plan], ensure_ascii=False, indent=2),
                           encoding="utf-8")
            console.print(f"[dim]正在打开编辑器：{tmp}（保存并关闭后回到这里）[/dim]")
            if _open_in_editor(tmp):
                try:
                    data = json.loads(tmp.read_text(encoding="utf-8"))
                    plan = [PlanItem.from_dict(d) for d in data]
                    console.print(f"[green]已载入 {len(plan)} 条。[/green]")
                    render_plan(console, plan, intent, outdir, show_all)
                except Exception as exc:
                    console.print(f"[red]清单解析失败，保留原清单：{exc}[/red]")
            else:
                console.print("[red]编辑器启动失败，保留原清单。[/red]")
        else:
            console.print("[red]无法识别的命令，输入 `?` 查看帮助。[/red]")
