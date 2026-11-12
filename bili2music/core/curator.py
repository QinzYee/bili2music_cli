"""Turn candidates into a curated, human-reviewable download plan."""
from __future__ import annotations

from rich.console import Console

from ..bilibili.library import keyword_score, local_filter
from ..config import Config
from ..llm.client import LLMClient, LLMError
from ..llm.prompts import CURATE_SYSTEM, build_curate_user
from ..models import Intent, PlanItem, VideoItem
from ..utils import sanitize_filename

_MAX_CANDIDATES_FOR_LLM = 60


def default_filename(v: VideoItem) -> str:
    base = f"{v.owner} - {v.title}" if v.owner else v.title
    return sanitize_filename(base)


def build_full_plan(items: list[VideoItem]) -> list[PlanItem]:
    """`favorite` task = download everything, no LLM filtering (user asked for all)."""
    out, seen = [], set()
    for v in items:
        if v.bvid in seen:
            continue
        seen.add(v.bvid)
        out.append(PlanItem(video=v, filename=default_filename(v),
                            reason="收藏夹内条目（全量下载）", score=100.0))
    return out


def _fallback(intent: Intent, candidates: list[VideoItem], limit: int) -> list[PlanItem]:
    scored = sorted(((keyword_score(v, intent.keyword) + (1.0 if v.play else 0), v)
                     for v in candidates), key=lambda x: -x[0])
    if intent.keyword:
        scored = [x for x in scored if x[0] > 0] or scored
    picked = scored[:limit]
    return [PlanItem(video=v, filename=default_filename(v), score=min(100.0, s * 10),
                     reason="按关键词命中度与热度排序（未经大模型整理）")
            for s, v in picked]


def _intent_desc(intent: Intent, cfg: Config) -> str:
    from ..models import MODE_LABELS, SCOPE_LABELS, TASK_LABELS
    bits = [f"任务：{TASK_LABELS.get(intent.task, intent.task)}",
            f"下载形态：{MODE_LABELS.get(intent.mode, '未定')}",
            f"搜索范围：{SCOPE_LABELS.get(intent.scope, '不限')}"]
    if intent.notes:
        bits.append("补充：" + "；".join(intent.notes))
    return "；".join(bits)


def curate(llm: LLMClient, cfg: Config, intent: Intent,
           candidates: list[VideoItem], console: Console) -> list[PlanItem]:
    """LLM-curated list; degrades gracefully to deterministic ranking."""
    if not candidates:
        return []
    limit = intent.limit or cfg.max_results
    pool = candidates
    if intent.keyword and len(pool) > _MAX_CANDIDATES_FOR_LLM:
        pool = local_filter(pool, intent.keyword, cap=_MAX_CANDIDATES_FOR_LLM) or pool[:_MAX_CANDIDATES_FOR_LLM]
        console.print(f"[dim]候选较多，先按关键词预筛到 {len(pool)} 条再交给大模型。[/dim]")
    else:
        pool = pool[:_MAX_CANDIDATES_FOR_LLM]

    if not cfg.llm_ready():
        console.print("[yellow]大模型未配置，改用关键词规则排序生成清单。[/yellow]")
        return _fallback(intent, pool, limit)

    by_bvid = {v.bvid: v for v in pool}
    try:
        result = llm.chat_json(
            CURATE_SYSTEM,
            build_curate_user(_intent_desc(intent, cfg), intent.keyword, limit,
                              [v.compact() for v in pool]),
        )
        raw_items = result.get("items") or []
        if result.get("summary"):
            console.print(f"[dim]整理思路：{result['summary']}[/dim]")
        if not isinstance(raw_items, list) or not raw_items:
            console.print("[yellow]大模型没有选中任何条目，回退到规则排序清单。[/yellow]")
            return _fallback(intent, pool, limit)

        out, seen = [], set()
        for r in raw_items:
            if not isinstance(r, dict):
                continue
            bvid = str(r.get("bvid") or "")
            v = by_bvid.get(bvid)
            if not v or bvid in seen:
                continue                      # never invent / accept unknown ids
            seen.add(bvid)
            name = sanitize_filename(str(r.get("filename") or "")) or default_filename(v)
            try:
                score = float(r.get("score") or 0)
            except (TypeError, ValueError):
                score = 0.0
            out.append(PlanItem(video=v, filename=name,
                                reason=str(r.get("reason") or ""), score=score))
        if not out:
            console.print("[yellow]大模型返回的条目都不在候选里，回退到规则排序清单。[/yellow]")
            return _fallback(intent, pool, limit)
        out.sort(key=lambda p: -p.score)
        return out[:limit]
    except LLMError as exc:
        console.print(f"[yellow]大模型整理失败（{exc}），回退到规则排序清单。[/yellow]")
        return _fallback(intent, pool, limit)
