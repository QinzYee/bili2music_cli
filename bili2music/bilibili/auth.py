"""Login helpers: QR-code login (recommended) or pasting a cookie string."""
from __future__ import annotations

import re
import time

import httpx
from rich.console import Console

PASSPORT = "https://passport.bilibili.com"


def parse_cookie_string(raw: str) -> dict[str, str]:
    """Accept either a full Cookie header or a bare SESSDATA value."""
    raw = (raw or "").strip().strip("'\"")
    if ";" not in raw and "=" not in raw and len(raw) > 20:
        return {"SESSDATA": raw}
    out: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" in part:
            k, _, v = part.strip().partition("=")
            if k in ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"):
                out[k] = v.strip()
    return out


def _cookies_from_response(resp: httpx.Response) -> dict[str, str]:
    found: dict[str, str] = {}
    for header in resp.headers.get_list("set-cookie"):
        m = re.match(r"\s*([^=;]+)=([^;]*)", header)
        if m and m.group(1).strip() in ("SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4"):
            found[m.group(1).strip()] = m.group(2).strip()
    return found


def qr_login(console: Console, cfg, max_wait: int = 180) -> dict[str, str]:
    """Show a terminal QR code and poll until confirmed."""
    with httpx.Client(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as http:
        data = http.get(PASSPORT + "/x/passport-login/web/qrcode/generate").json().get("data") or {}
        url, key = data.get("url", ""), data.get("qrcode_key", "")
        if not url or not key:
            raise RuntimeError("获取二维码失败，请改用手动粘贴 Cookie")

        console.print("\n[bold]请用 B 站 App 扫描下面的二维码并确认登录：[/bold]")
        try:
            import qrcode
            qr = qrcode.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)
            for row in qr.get_matrix():
                console.print("".join("██" if cell else "  " for cell in row), highlight=False)
        except Exception:
            console.print(f"[yellow]二维码渲染失败，请在浏览器打开：{url}[/yellow]")
        console.print(f"[dim]如果扫不出来，可手动打开：{url}[/dim]")

        deadline = time.time() + max_wait
        last_status = ""
        while time.time() < deadline:
            r = http.get(PASSPORT + "/x/passport-login/web/qrcode/poll",
                         params={"qrcode_key": key})
            d = (r.json() or {}).get("data") or {}
            code = d.get("code")
            if code == 0:
                creds = _cookies_from_response(r)
                if not creds.get("SESSDATA"):
                    raise RuntimeError("登录成功但没拿到 SESSDATA，请改用手动粘贴 Cookie")
                return creds
            status = {86090: "已扫码，等待在手机上确认…", 86101: "等待扫码…"}.get(code, "")
            if status and status != last_status:
                console.print(f"[dim]{status}[/dim]")
                last_status = status
            if code == 86038:
                raise RuntimeError("二维码已过期，请重新执行 `b2m login`")
            time.sleep(2)
        raise RuntimeError("等待登录超时")


def manual_login(console: Console) -> dict[str, str]:
    console.print(
        "\n[bold]粘贴 B 站 Cookie[/bold]\n"
        "浏览器登录 bilibili.com → F12 → 网络 → 任意请求 → 请求标头 → 复制整条 Cookie；\n"
        "也可以只粘贴 SESSDATA 的值。输入内容不会回显到日志。"
    )
    raw = console.input("[cyan]Cookie / SESSDATA> [/cyan]").strip()
    creds = parse_cookie_string(raw)
    if not creds.get("SESSDATA"):
        raise RuntimeError("没解析到 SESSDATA，请检查粘贴内容")
    return creds
