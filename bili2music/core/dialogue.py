"""Proactive clarification: fill the slots that are truly required before acting.

Two layers:
1. LLM parses the utterance and may add one clarifying question.
2. A deterministic guard guarantees every blocking slot gets asked, even when
   the model is offline, hallucinates, or forgets to ask.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rich.console import Console

from ..config import Config
from ..llm.client import LLMClient, LLMError
from ..llm.prompts import INTENT_SYSTEM, build_intent_user
from ..models import Intent, MODES, SCOPES, TASKS
from ..utils import extract_bvid, parse_favorite_ref

GENERIC_WORDS = {"视频", "音频", "歌", "歌曲", "音乐", "内容", "东西", "全部",
                 "所有", "相关", "的", "合集", "一下", "一些"}


@dataclass
class Question:
    key: str
    text: str
    choices: list[tuple[str, str]] = field(default_factory=list)


def rule_parse(text: str) -> Intent:
    """Deterministic extraction; never guesses values that were not said."""
    s = (text or "").strip()
    it = Intent(raw=s)
    low = s.lower()

    fid = parse_favorite_ref(s)
    if fid:
        it.favorite_id = fid
        it.notes.append(f"从文本中识别到收藏夹 id={fid}")

    if re.search(r"(列出|有哪些|看看|显示).{0,6}收藏夹", s) and "下载" not in s:
        it.task = "folders"
    elif re.search(r"^(配置|设置|config)$", low) or "修改配置" in s:
        it.task = "config"
    elif re.search(r"搜|找|关键词|筛选|挑|推荐|关于", s):
        it.task = "folder_search" if "收藏夹" in s else "search"
    elif fid or "收藏夹" in s or extract_bvid(s):
        it.task = "favorite"

    # keyword: quoted text wins, then "搜索/找/关键词 X".
    m = re.search(r"[「『\"《]([^」』\"》]{1,40})[」』\"》]", s)
    kw = m.group(1).strip() if m else ""
    if not kw:
        m = re.search(r"(?:搜索|搜|找|关键词|关于)\s*[:：]?\s*([^\s,，。；;、]{1,30})", s)
        kw = m.group(1).strip() if m else ""
    if kw and kw not in GENERIC_WORDS and not kw.isdigit():
        it.keyword = kw

    if re.search(r"音视频|视频音频|视频和音频|音频和视频|都要|两个都要|全都要|全部都要", s):
        it.mode = "both"
    elif re.search(r"音频|音轨|mp3|m4a|flac|音乐|只要声音|听歌|转成音乐", low):
        it.mode = "audio"
    elif re.search(r"视频|mp4|画面|要看|下载视频", low):
        it.mode = "video"

    if re.search(r"全站.*收藏夹|收藏夹.*全站|都搜|两边", s):
        it.scope = "both"
    elif re.search(r"全站|站内搜索|b站搜|哔哩哔哩搜", low):
        it.scope = "site"
    elif "收藏夹" in s and re.search(r"搜|找|里", s):
        it.scope = "folder"
    if it.task == "folder_search":
        it.scope = "folder"

    m = re.search(r"(\d{1,3})\s*(?:个|条|首|部|支)", s)
    if m:
        it.limit = int(m.group(1))
    return it


QUESTION_BANK: dict[str, Question] = {
    "task": Question("task", "你想做什么？", [
        ("下载某个收藏夹的全部内容", "favorite"),
        ("按关键词搜索、筛选后下载", "search"),
        ("在我的收藏夹里按关键词找", "folder_search"),
        ("只列出我的收藏夹", "folders"),
    ]),
    "keyword": Question("keyword", "要搜什么关键词？（可写多个词，越具体越准）"),
    "scope": Question("scope", "搜索范围是哪里？", [
        ("B 站全站（发现新内容）", "site"),
        ("只在我的收藏夹里找", "folder"),
        ("两边都搜", "both"),
    ]),
    "mode": Question("mode", "下载成什么形态？", [
        ("只要音频（mp3，提取音轨）", "audio"),
        ("只要完整视频（mp4）", "video"),
        ("音频 + 视频都要", "both"),
    ]),
}


def _favorite_question(folders) -> Question:
    if folders:
        choices = [(f"{f.title}（{f.count} 个）· id={f.id}", f.id) for f in folders[:20]]
        return Question("favorite_id", "用哪个收藏夹？（选编号，或直接粘贴收藏夹链接 / fid 数字）", choices)
    return Question("favorite_id", "用哪个收藏夹？请粘贴收藏夹链接（含 fid=）或纯数字 id。"
                                   "（未登录时列不出收藏夹；也可先执行 `b2m login`）")


def question_for(key: str, folders) -> Question:
    if key == "favorite_id":
        return _favorite_question(folders)
    return QUESTION_BANK.get(key, Question(key, f"请提供 {key}："))


def _coerce(key: str, value: str, q: Question, folders) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    for label, val in q.choices:
        if value == label or value == val:
            return val
    # Free-form answers: try rule parsing first, then keep the raw text.
    parsed = rule_parse(value)
    candidate = {"task": parsed.task, "keyword": parsed.keyword,
                 "favorite_id": parsed.favorite_id, "scope": parsed.scope,
                 "mode": parsed.mode}.get(key, "")
    if candidate:
        return candidate
    if not q.choices:
        return value                       # open-ended question (e.g. style preference)
    if key == "favorite_id" and folders:
        for f in folders:
            if value.lower() in f.title.lower() or f.title.lower() in value.lower():
                return f.id
    for label, val in q.choices:
        if value and (value in label or label in value):
            return val
    return value if key in ("keyword", "favorite_id", "output_dir") else ""


def _merge(it: Intent, slots: dict) -> None:
    if not isinstance(slots, dict):
        return
    for key, val in slots.items():
        if key not in Intent.__dataclass_fields__ or val in (None, "", 0, "0"):
            continue
        if key == "task" and val not in TASKS:
            continue
        if key == "mode" and val not in MODES:
            continue
        if key == "scope" and val not in SCOPES:
            continue
        if key == "favorite_id":
            val = parse_favorite_ref(str(val)) or (str(val) if str(val).isdigit() else "")
            if not val:
                continue
        if key == "limit":
            try:
                val = max(0, min(500, int(val)))
            except (TypeError, ValueError):
                continue
        setattr(it, key, val)


def ask_question(console: Console, q: Question, folders=None) -> str:
    console.print(f"\n[bold cyan]? {q.text}[/bold cyan]")
    if q.choices:
        for i, (label, _) in enumerate(q.choices, 1):
            console.print(f"  [dim]{i}.[/dim] {label}")
    try:
        raw = console.input("[cyan]> [/cyan]").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    if raw.isdigit() and q.choices and 1 <= int(raw) <= len(q.choices):
        return q.choices[int(raw) - 1][1]
    return _coerce(q.key, raw, q, folders)


def collect_intent(llm: LLMClient, cfg: Config, raw: str, folders,
                   console: Console, preset: Intent | None = None,
                   *, non_interactive: bool = False) -> Intent:
    """Parse + proactively ask for missing information. Returns a ready Intent."""
    intent = rule_parse(raw)
    if preset:
        _merge(intent, preset.as_dict())

    llm_ok = cfg.llm_ready()
    if llm_ok:
        try:
            res = llm.chat_json(INTENT_SYSTEM,
                                build_intent_user(raw, intent.as_dict(), folders, intent.missing()))
            _merge(intent, res.get("slots") or {})
            if res.get("reply"):
                console.print(f"[dim]理解：{res['reply']}[/dim]")
            # A model-generated clarification about vague wording (not a required slot).
            for q in (res.get("questions") or [])[:1]:
                key = (q or {}).get("key", "")
                text = (q or {}).get("text", "")
                if key == "keyword_detail" and text and intent.keyword and not non_interactive:
                    ans = ask_question(console, Question("keyword_detail", text), folders)
                    if ans:
                        intent.notes.append(f"关键词补充说明：{ans}")
                        raw += f"\n关键词补充：{ans}"
        except LLMError as exc:
            console.print(f"[yellow]大模型不可用（{exc}），已切换为规则式问答。[/yellow]")
            llm_ok = False
    else:
        console.print("[yellow]未检测到大模型配置，使用规则式问答（仍可完成全部功能）。[/yellow]")

    # Deterministic guard: ask every still-blocking slot, max 2 per round.
    if non_interactive and intent.missing():
        console.print("[dim]非交互模式：跳过追问，缺失项使用默认值（可用 --mode/--scope 显式指定）。[/dim]")
    rounds = 0
    budget = max(2, cfg.max_questions + 2)
    while intent.missing() and rounds < budget and not non_interactive:
        batch = intent.missing()[:2]
        answers: list[str] = []
        for key in batch:
            q = question_for(key, folders)
            value = ask_question(console, q, folders)
            if value:
                _merge(intent, {key: value})
            answers.append(f"{q.text} → {value or '（未回答）'}")
        if not any(a for a in answers if "（未回答）" not in a):
            break
        raw += "\n用户补充：" + "；".join(answers)
        # Let the model re-parse the enriched conversation (catches compound answers).
        if llm_ok:
            try:
                res = llm.chat_json(INTENT_SYSTEM,
                                    build_intent_user(raw, intent.as_dict(), folders, intent.missing()))
                _merge(intent, res.get("slots") or {})
            except LLMError:
                llm_ok = False
        rounds += 1

    # Last-resort defaults are always announced, never silent.
    if intent.task in ("unknown", ""):
        intent.task = "folders"
        console.print("[yellow]未能确定任务，默认改为「列出收藏夹」，不会下载任何内容。[/yellow]")
    if intent.task in ("favorite", "search", "folder_search"):
        if intent.mode not in MODES:
            intent.mode = "audio"
            console.print("[yellow]未指定下载形态，默认「只要音频」。可在清单确认时用 `mode` 修改。[/yellow]")
        if intent.task == "search" and intent.scope not in SCOPES:
            intent.scope = "site"
            console.print("[yellow]未指定搜索范围，默认「B 站全站搜索」。[/yellow]")
        if not intent.limit:
            intent.limit = 0 if intent.task == "favorite" else cfg.max_results
    if intent.task == "folder_search":
        intent.scope = "folder"
    return intent
