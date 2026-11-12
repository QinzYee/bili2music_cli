"""Favorites and search: turn Bili API payloads into VideoItem lists."""
from __future__ import annotations

import time
from dataclasses import dataclass

from .client import BiliClient, BiliError
from ..models import VideoItem
from ..utils import avid_to_bvid, parse_duration, strip_html


@dataclass
class Folder:
    id: str
    title: str
    count: int = 0


def list_folders(client: BiliClient) -> list[Folder]:
    mid = client.my_mid()
    if not mid:
        raise BiliError("读取收藏夹需要登录态，请先执行 `b2m login`")
    try:
        data = client.get("/x/v3/fav/folder/created/list-all", {"up_mid": mid, "type": 2})
    except BiliError:
        data = client.get("/x/v3/fav/folder/created/list", {"up_mid": mid, "pn": 1, "ps": 50})
    raw = data.get("list") or (data if isinstance(data, list) else []) or []
    return [Folder(str(f.get("id") or f.get("media_id") or ""),
                   strip_html(f.get("title") or "未命名"), int(f.get("media_count") or 0))
            for f in raw if f.get("id") or f.get("media_id")]


def _from_fav_media(m: dict, folder_name: str = "") -> VideoItem | None:
    bvid = m.get("bvid") or avid_to_bvid(m.get("id") or 0)
    if not bvid:
        return None
    upper = m.get("upper") or {}
    return VideoItem(
        bvid=bvid,
        title=strip_html(m.get("title") or bvid),
        owner=strip_html(upper.get("name") or ""),
        mid=int(upper.get("mid") or 0),
        duration=int(m.get("duration") or 0),
        description=strip_html(m.get("intro") or ""),
        pubdate=int(m.get("pubtime") or 0),
        cover=(m.get("cover") or "").replace("http://", "https://"),
        folder=folder_name,
        source="favorite",
    )


def fetch_folder(client: BiliClient, fid: str, limit: int = 0,
                 on_page=None) -> tuple[str, list[VideoItem]]:
    """Fetch *all* pages of a favorite folder. `limit=0` means no cap."""
    items: list[VideoItem] = []
    seen: set[str] = set()
    folder_name = ""
    pn = 1
    while True:
        try:
            data = client.get("/x/v3/fav/resource/list", {
                "media_id": fid, "pn": pn, "ps": 20,
                "order": "mtime", "type": 0, "platform": "web",
            })
        except BiliError:
            # Some accounts require WBI on this endpoint.
            data = client.get("/x/v3/fav/resource/list", {
                "media_id": fid, "pn": pn, "ps": 20,
                "order": "mtime", "type": 0, "platform": "web",
            }, signed=True)
        if not folder_name:
            info = data.get("info") or {}
            folder_name = strip_html(info.get("title") or "")
        medias = data.get("medias") or []
        if on_page:
            on_page(pn, len(medias), int(data.get("total") or 0))
        for m in medias:
            v = _from_fav_media(m, folder_name)
            if v and v.bvid not in seen:
                seen.add(v.bvid)
                items.append(v)
        has_more = bool(data.get("has_more")) or (len(medias) == 20 and
                                                  (limit == 0 or len(items) < limit))
        if not medias or not has_more:
            break
        if limit and len(items) >= limit:
            break
        pn += 1
        time.sleep(0.35)
    return folder_name, items[:limit] if limit else items


def search_site(client: BiliClient, keyword: str, limit: int = 30,
                order: str = "totalrank", on_page=None) -> list[VideoItem]:
    """Keyword search over all of Bilibili (WBI signed)."""
    items: list[VideoItem] = []
    seen: set[str] = set()
    page = 1
    risk_retried = False
    while len(items) < limit:
        try:
            data = client.get("/x/web-interface/wbi/search/type", {
                "search_type": "video", "keyword": keyword,
                "page": page, "page_size": 20, "order": order,
            }, signed=True)
        except BiliError as exc:
            if "v_voucher" in str(exc) and not risk_retried:
                risk_retried = True
                time.sleep(2.0)
                if hasattr(client, "refresh_anonymous_identity"):
                    client.refresh_anonymous_identity()
                continue                       # one retry with fresh anonymous identity
            raise
        results = data.get("result") or []
        if on_page:
            on_page(page, len(results), int(data.get("numResults") or 0))
        for r in results:
            bvid = r.get("bvid") or ""
            if not bvid or bvid in seen:
                continue
            seen.add(bvid)
            items.append(VideoItem(
                bvid=bvid,
                title=strip_html(r.get("title") or bvid),
                owner=strip_html(r.get("author") or ""),
                mid=int(r.get("mid") or 0),
                duration=parse_duration(r.get("duration")),
                description=strip_html(r.get("description") or ""),
                pubdate=int(r.get("pubdate") or 0),
                cover=(r.get("pic") or "").replace("http://", "https://"),
                play=int(r.get("play") or 0),
                source="search",
            ))
        if not results or len(results) < 20 or page >= int(data.get("numPages") or 1):
            break
        page += 1
        time.sleep(0.6)
    return items[:limit]


def video_by_bvid(client: BiliClient, bvid: str) -> VideoItem:
    d = client.get("/x/web-interface/view", {"bvid": bvid})
    owner = d.get("owner") or {}
    stat = d.get("stat") or {}
    return VideoItem(
        bvid=d.get("bvid") or bvid,
        title=strip_html(d.get("title") or bvid),
        owner=strip_html(owner.get("name") or ""),
        mid=int(owner.get("mid") or 0),
        duration=int(d.get("duration") or 0),
        description=strip_html(d.get("desc") or "")[:300],
        pubdate=int(d.get("pubdate") or 0),
        cover=(d.get("pic") or "").replace("http://", "https://"),
        play=int(stat.get("view") or 0),
        source="manual",
    )


def keyword_score(v: VideoItem, keyword: str) -> float:
    """Cheap local pre-filter before the LLM sees the candidates."""
    k = keyword.strip().lower()
    if not k:
        return 0.0
    title, owner, desc = v.title.lower(), v.owner.lower(), v.description.lower()
    terms = [t for t in k.replace("，", " ").replace(",", " ").split() if t]
    score = 0.0
    for t in terms:
        if t in title:
            score += 3.0
        if t in owner:
            score += 2.0
        if t in desc:
            score += 1.0
    if k in title:
        score += 2.0
    if v.play:
        import math
        score += min(1.5, math.log10(max(1, v.play)) * 0.2)
    return score


def local_filter(items: list[VideoItem], keyword: str, cap: int = 60) -> list[VideoItem]:
    scored = [(keyword_score(v, keyword), v) for v in items]
    hits = [v for s, v in sorted(scored, key=lambda x: -x[0]) if s > 0]
    return hits[:cap]
