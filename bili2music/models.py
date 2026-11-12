"""Data models shared across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

TASKS = ("favorite", "search", "folder_search", "folders", "config", "unknown")
MODES = ("audio", "video", "both")
SCOPES = ("site", "folder", "both")

MODE_LABELS = {"audio": "只要音频", "video": "只要视频", "both": "音频+视频"}
SCOPE_LABELS = {"site": "B 站全站搜索", "folder": "只在我的收藏夹内找", "both": "全站 + 收藏夹"}
TASK_LABELS = {
    "favorite": "下载收藏夹全部内容",
    "search": "关键词搜索后筛选下载",
    "folder_search": "在收藏夹内按关键词筛选下载",
    "folders": "列出我的收藏夹",
    "config": "查看/修改配置",
    "unknown": "未明确",
}


@dataclass
class VideoItem:
    bvid: str
    title: str
    owner: str = ""
    mid: int = 0
    duration: int = 0                 # seconds
    description: str = ""
    pubdate: int = 0
    cover: str = ""
    play: int = 0
    folder: str = ""                  # source folder name, if any
    source: str = ""                  # favorite | search

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}"

    @property
    def duration_str(self) -> str:
        if self.duration <= 0:
            return "-"
        m, s = divmod(int(self.duration), 60)
        return f"{m}:{s:02d}" if m < 60 else f"{m // 60}:{m % 60:02d}:{s:02d}"

    def compact(self) -> dict[str, Any]:
        """Trimmed representation sent to the LLM (keeps token cost low)."""
        return {
            "bvid": self.bvid,
            "title": self.title[:100],
            "up": self.owner[:30],
            "dur": self.duration_str,
            "folder": self.folder[:30],
            "desc": self.description[:120],
            "play": self.play,
        }

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VideoItem":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PlanItem:
    video: VideoItem
    reason: str = ""
    filename: str = ""               # stem, no extension
    score: float = 0.0

    def to_dict(self) -> dict:
        return {"video": self.video.to_dict(), "reason": self.reason,
                "filename": self.filename, "score": self.score}

    @classmethod
    def from_dict(cls, d: dict) -> "PlanItem":
        return cls(video=VideoItem.from_dict(d.get("video", {})),
                   reason=d.get("reason", ""), filename=d.get("filename", ""),
                   score=float(d.get("score", 0) or 0))


@dataclass
class Intent:
    """Slots the assistant must fill before it is allowed to download anything."""
    task: str = ""
    keyword: str = ""
    favorite_id: str = ""
    scope: str = ""
    mode: str = ""
    limit: int = 0
    output_dir: str = ""
    raw: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "raw"}

    def missing(self) -> list[str]:
        """Only genuinely blocking slots. Everything else has a sensible default."""
        gaps: list[str] = []
        if self.task not in TASKS or self.task in ("unknown",):
            gaps.append("task")
        if self.task in ("search", "folder_search") and not self.keyword:
            gaps.append("keyword")
        if self.task in ("favorite", "folder_search") and not self.favorite_id:
            gaps.append("favorite_id")
        if self.task == "search" and not self.scope:
            gaps.append("scope")
        if self.task == "search" and self.scope in ("folder", "both") and not self.favorite_id:
            gaps.append("favorite_id")
        if self.task in ("favorite", "search", "folder_search") and not self.mode:
            gaps.append("mode")
        # preserve order, de-duplicate
        return list(dict.fromkeys(gaps))
