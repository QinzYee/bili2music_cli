"""Small pure helpers (no I/O) so they are easy to unit-test."""
from __future__ import annotations

import html
import re

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WS = re.compile(r"\s+")
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


def sanitize_filename(name: str, max_len: int = 110) -> str:
    clean = _INVALID_CHARS.sub("_", name or "")
    clean = _WS.sub(" ", clean).strip().strip(". ")
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip(". ")
    if not clean or clean.upper() in _WINDOWS_RESERVED:
        clean = "bili_" + (clean or "item")
    return clean


def strip_html(text: str) -> str:
    """Bili search wraps matched keywords in <em class="keyword">."""
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_duration(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return 0
    parts = str(value).strip().split(":")
    try:
        nums = [int(float(p)) for p in parts]
    except ValueError:
        return 0
    total = 0
    for n in nums:
        total = total * 60 + n
    return total


_AV2BV_TABLE = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
_AV2BV_IDX = [11, 10, 3, 8, 4, 6]
_XOR_CODE = 23442827791579
_MAX_AID = 1 << 51


def avid_to_bvid(aid: int) -> str:
    """Best-effort conversion for older API responses that omit `bvid`.

    Favorites/search normally return bvid directly; this is only a fallback.
    """
    try:
        aid = int(aid)
    except (TypeError, ValueError):
        return ""
    if aid <= 0:
        return ""
    chars = list("BV1000000000")
    tmp = (_MAX_AID | aid) ^ _XOR_CODE
    for i in range(6):
        chars[_AV2BV_IDX[i]] = _AV2BV_TABLE[tmp % 58]
        tmp //= 58
    return "".join(chars)


def parse_favorite_ref(text: str) -> str:
    """Extract a favorite folder id from a URL or plain id."""
    if not text:
        return ""
    s = str(text).strip()
    m = re.search(r"(?:^|[?&\s])fid=(\d+)", s)
    if m:
        return m.group(1)
    m = re.search(r"/ml(\d+)", s)
    if m:
        return m.group(1)
    m = re.search(r"media_id=(\d+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{3,}", s):
        return s
    return ""


def parse_selection(expr: str, total: int) -> set[int]:
    """Parse `1,3-5` / `all` into 1-based indices."""
    expr = (expr or "").strip().lower()
    if expr in ("all", "*", ""):
        return set(range(1, total + 1))
    out: set[int] = set()
    for chunk in expr.replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, _, b = chunk.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                continue
            out.update(i for i in range(lo, hi + 1) if 1 <= i <= total)
        else:
            try:
                i = int(chunk)
            except ValueError:
                continue
            if 1 <= i <= total:
                out.add(i)
    return out


def extract_bvid(text: str) -> str:
    m = re.search(r"\b(BV[0-9A-Za-z]{10})\b", text or "")
    return m.group(1) if m else ""
