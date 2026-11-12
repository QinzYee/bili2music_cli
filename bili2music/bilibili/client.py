"""Bilibili HTTP client: cookies, WBI signing, friendly errors."""
from __future__ import annotations

import hashlib
import time
from urllib.parse import urlencode

import httpx

from ..config import Config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
API_BASE = "https://api.bilibili.com"

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22,
    25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


class BiliError(Exception):
    """Human-readable Bilibili API failure."""


class BiliClient:
    def __init__(self, cfg: Config, timeout: float = 20):
        self.cfg = cfg
        self._wbi: tuple[str, str] | None = None
        self._mid: int = 0
        self.http = httpx.Client(
            timeout=timeout, follow_redirects=True,
            headers={
                "User-Agent": UA,
                "Referer": "https://www.bilibili.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        self._apply_cookies()

    # ---------------------------------------------------------------- cookies
    def _apply_cookies(self) -> None:
        for name, value in (
            ("SESSDATA", self.cfg.sessdata),
            ("bili_jct", self.cfg.bili_jct),
            ("DedeUserID", self.cfg.dede_user_id),
            ("buvid3", self.cfg.buvid3),
            ("buvid4", self.cfg.buvid4),
        ):
            if value:
                self.http.cookies.set(name, value, domain=".bilibili.com", path="/")
        if not self.cfg.buvid3:
            self._fetch_anonymous_buvid()

    def _fetch_anonymous_buvid(self) -> None:
        """Anonymous search requires a buvid3/buvid4 pair."""
        try:
            r = self.http.get(API_BASE + "/x/frontend/finger/spi")
            data = (r.json() or {}).get("data") or {}
            b3, b4 = data.get("b_3", ""), data.get("b_4", "")
            if b3:
                self.cfg.buvid3, self.cfg.buvid4 = b3, b4
                self.http.cookies.set("buvid3", b3, domain=".bilibili.com", path="/")
                if b4:
                    self.http.cookies.set("buvid4", b4, domain=".bilibili.com", path="/")
        except Exception:
            pass  # best effort; login cookies are usually enough

    def refresh_anonymous_identity(self) -> None:
        """Rotate buvid3/buvid4 after a risk-control challenge."""
        self.cfg.buvid3 = self.cfg.buvid4 = ""
        self._fetch_anonymous_buvid()
        self.refresh_cookies()

    def refresh_cookies(self) -> None:
        self.http.cookies.clear()
        self._apply_cookies()

    # ------------------------------------------------------------------- WBI
    def wbi_keys(self) -> tuple[str, str]:
        if self._wbi:
            return self._wbi
        try:
            nav = self.get("/x/web-interface/nav", check=False)
            wbi = (nav or {}).get("wbi_img") or {}
            img = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
            sub = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
            if img and sub:
                self._wbi = (img, sub)
                return self._wbi
        except Exception:
            pass
        # Fallback to the currently published keys; still better than no signature.
        self._wbi = ("7cd084941338484aae1ad9425b84077c", "4932caff0ff746eab6f01bf08b70ac45")
        return self._wbi

    def sign(self, params: dict) -> dict:
        img_key, sub_key = self.wbi_keys()
        raw = img_key + sub_key
        mixin_key = "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]
        p = dict(params)
        p["wts"] = int(time.time())
        # Bili filters !'()* from values before hashing.
        clean = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in p.items()}
        query = urlencode(sorted(clean.items()))
        p["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
        return p

    # ---------------------------------------------------------------- requests
    def get(self, path: str, params: dict | None = None, *, signed: bool = False,
            check: bool = True, base: str = API_BASE) -> dict:
        p = dict(params or {})
        if signed:
            p = self.sign(p)
        try:
            r = self.http.get(base + path if path.startswith("/") else path, params=p)
            r.raise_for_status()
            payload = r.json()
        except httpx.HTTPError as exc:
            raise BiliError(f"网络请求失败：{exc}") from exc
        except ValueError as exc:
            raise BiliError("B 站返回的不是 JSON（可能触发了风控）") from exc

        code = payload.get("code", 0)
        if check and code != 0:
            msg = payload.get("message") or "未知错误"
            if code in (-352, -412, -509):
                msg += "（触发风控，建议先 `b2m login` 登录并稍后重试）"
            elif code in (-101, -111):
                msg += "（需要登录：`b2m login`）"
            raise BiliError(f"B 站接口返回 {code}: {msg}")
        data = payload.get("data") or {}
        if isinstance(data, dict) and data.get("v_voucher"):
            # Bili returns code=0 with only a voucher when risk control kicks in.
            raise BiliError("B 站触发风控校验（v_voucher）：请 `b2m login` 登录后重试，"
                            "或稍后再试；本次未获取到任何数据")
        return data

    def my_mid(self) -> int:
        if not self._mid:
            self._mid = int((self.get("/x/web-interface/nav", check=False) or {}).get("mid") or 0)
        return self._mid

    def is_logged_in(self) -> bool:
        try:
            return bool((self.get("/x/web-interface/nav", check=False) or {}).get("isLogin"))
        except BiliError:
            return False

    def close(self) -> None:
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
