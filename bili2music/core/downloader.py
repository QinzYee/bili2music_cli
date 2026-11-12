"""Download engine built on yt-dlp, with ffmpeg discovery and safe skip logic."""
from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..config import Config, write_cookie_file
from ..models import PlanItem


def resolve_ffmpeg(cfg: Config) -> str | None:
    """System ffmpeg -> configured path -> bundled imageio-ffmpeg binary."""
    if cfg.ffmpeg_path and Path(cfg.ffmpeg_path).exists():
        return cfg.ffmpeg_path
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _expected_files(outdir: Path, stem: str, mode: str, cfg: Config) -> list[Path]:
    if mode == "audio":
        return [outdir / f"{stem}.{cfg.audio_format}"]
    if mode == "video":
        return [outdir / f"{stem}.{cfg.video_format}"]
    return [outdir / f"{stem}.{cfg.video_format}", outdir / f"{stem}.{cfg.audio_format}"]


def _build_opts(cfg: Config, outdir: Path, stem: str, mode: str,
                ffmpeg: str | None, cookie_file) -> dict:
    safe_stem = stem.replace("%", "%%")
    opts: dict = {
        "outtmpl": str(outdir / (safe_stem + ".%(ext)s")),
        "format": "bestaudio/best" if mode == "audio" else "bv*+ba/b",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,                 # avoid accidentally pulling every 分P
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "overwrites": cfg.overwrite,
        "http_headers": {"Referer": "https://www.bilibili.com/",
                         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        "postprocessors": [],
    }
    if cookie_file:
        opts["cookiefile"] = str(cookie_file)
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg

    if mode in ("video", "both"):
        opts["merge_output_format"] = cfg.video_format
    if not ffmpeg:
        # No ffmpeg: keep the original stream, skip transcode/merge entirely.
        opts.pop("merge_output_format", None)
        if mode in ("video", "both"):
            opts["format"] = "best[ext=mp4]/best"
        return opts
    if mode in ("audio", "both"):
        extract = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": cfg.audio_format,
            "preferredquality": cfg.audio_quality,
            "nopostoverwrites": False,
        }
        if mode == "both":
            extract["keepvideo"] = True         # keep the merged mp4 as well
        opts["postprocessors"] = [extract, {"key": "FFmpegMetadata"}]
    else:
        opts["postprocessors"] = [{"key": "FFmpegMetadata"}]
    return opts


def _one(item: PlanItem, mode: str, cfg: Config, outdir: Path,
         ffmpeg: str | None, cookie_file, console: Console) -> tuple[str, bool, str]:
    stem = item.filename or item.video.bvid
    targets = _expected_files(outdir, stem, mode, cfg) if ffmpeg else []

    def present() -> list[Path]:
        return [p for p in outdir.iterdir()
                if p.is_file() and p.name.startswith(stem + ".")
                and p.suffix not in (".part", ".ytdl") and p.stat().st_size > 0]

    if not cfg.overwrite:
        if ffmpeg and targets and all(p.exists() and p.stat().st_size > 0 for p in targets):
            return stem, True, "已存在，跳过"
        if not ffmpeg and present():
            return stem, True, "已存在，跳过"

    import yt_dlp
    opts = _build_opts(cfg, outdir, stem, mode, ffmpeg, cookie_file)
    last = ""
    for attempt in range(2):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(item.video.url, download=True)
            if ffmpeg:
                missing = [p.name for p in targets if not p.exists()]
            else:
                missing = [] if present() else ["输出文件"]
            if missing:
                last = "文件未生成：" + ", ".join(missing)
                continue
            console.print(f"  [green]✓[/green] {stem}")
            return stem, True, "完成"
        except Exception as exc:               # yt_dlp raises a wide variety
            last = str(exc)[:180]
            if attempt == 0:
                continue
    console.print(f"  [red]✗[/red] {stem} — {last}")
    return stem, False, last


def download_plan(plan: list[PlanItem], mode: str, cfg: Config, console: Console,
                  *, output_dir: Path | None = None) -> dict:
    """Download the confirmed plan. Returns a summary dict."""
    outdir = (output_dir or cfg.output_path).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_ffmpeg(cfg)
    if not ffmpeg:
        console.print("[yellow]未找到 ffmpeg：已降级为直接保存原始流（不转 mp3、不合并 DASH）。"
                      "建议执行 `pip install imageio-ffmpeg` 后重试。[/yellow]")
    cookie_file = write_cookie_file(cfg)

    console.print(f"[bold]开始下载 {len(plan)} 条 → {outdir}[/bold] "
                  f"[dim]({mode}，并发 {cfg.concurrency})[/dim]")
    ok, failed, skipped = [], [], []
    with ThreadPoolExecutor(max_workers=max(1, cfg.concurrency)) as pool:
        futures = {pool.submit(_one, p, mode, cfg, outdir, ffmpeg, cookie_file, console): p
                   for p in plan}
        for fut in as_completed(futures):
            stem, success, msg = fut.result()
            (ok if success else failed).append((stem, msg))
            if msg == "已存在，跳过":
                skipped.append(stem)

    table = Table(title="下载结果")
    table.add_column("状态", width=8)
    table.add_column("数量", width=6, justify="right")
    table.add_column("说明")
    table.add_row("[green]成功[/green]", str(len(ok) - len(skipped)), "新下载")
    table.add_row("[dim]跳过[/dim]", str(len(skipped)), "目标文件已存在")
    table.add_row("[red]失败[/red]", str(len(failed)), "见下方明细")
    console.print(table)
    if failed:
        console.print("[bold red]失败明细：[/bold red]")
        for stem, msg in failed[:20]:
            console.print(f"  • {stem}: {msg}")
        if len(failed) > 20:
            console.print(f"  … 另有 {len(failed) - 20} 条")
    return {"ok": len(ok) - len(skipped), "skipped": len(skipped),
            "failed": failed, "outdir": str(outdir), "ffmpeg": ffmpeg}
