"""Configuration: defaults -> TOML file -> environment variables.

Secrets live in ~/.bili2music/config.toml (mode 0600 on POSIX) or in the
environment. Nothing is ever written into the project directory.
"""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

APP_DIR = Path(os.environ.get("B2M_HOME", Path.home() / ".bili2music"))
CONFIG_PATH = APP_DIR / "config.toml"
COOKIE_PATH = APP_DIR / "cookies.txt"
LOG_PATH = APP_DIR / "b2m.log"


@dataclass
class Config:
    # --- LLM ---
    llm_provider: str = "openai"                       # openai | ollama
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_api_key: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_timeout: int = 90

    # --- Bilibili credentials ---
    sessdata: str = ""
    bili_jct: str = ""
    dede_user_id: str = ""
    buvid3: str = ""
    buvid4: str = ""

    # --- Download behaviour ---
    output_dir: str = ""                               # empty -> ~/Music/bili2music
    audio_format: str = "mp3"                         # mp3 | m4a | flac | wav
    audio_quality: str = "192"                        # kbps
    video_format: str = "mp4"
    max_results: int = 20                             # default curated list size
    concurrency: int = 2
    max_questions: int = 3                            # max proactive clarification rounds
    ffmpeg_path: str = ""                             # empty -> auto detect
    overwrite: bool = False

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir).expanduser() if self.output_dir else Path.home() / "Music" / "bili2music"

    @property
    def has_login(self) -> bool:
        return bool(self.sessdata)

    def llm_ready(self) -> bool:
        if self.llm_provider == "ollama":
            return bool(self.ollama_base_url and self.ollama_model)
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    def public_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        for k in ("llm_api_key", "sessdata", "bili_jct", "dede_user_id"):
            if d.get(k):
                d[k] = "***" + str(d[k])[-4:]
        return d


def _coerce(value, sample):
    if isinstance(sample, bool):
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(sample, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return sample
    return str(value)


def load_config() -> Config:
    cfg = Config()
    if CONFIG_PATH.is_file():
        try:
            data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for f in fields(cfg):
                if f.name in data and data[f.name] is not None:
                    setattr(cfg, f.name, _coerce(data[f.name], getattr(cfg, f.name)))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(f"配置文件解析失败 {CONFIG_PATH}: {exc}") from exc

    # Explicit B2M_* overrides win.
    for f in fields(cfg):
        raw = os.environ.get("B2M_" + f.name.upper())
        if raw is not None and raw != "":
            setattr(cfg, f.name, _coerce(raw, getattr(cfg, f.name)))

    # Common aliases so users don't have to rename their existing keys.
    if not cfg.llm_api_key:
        for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "LLM_API_KEY"):
            if os.environ.get(key):
                cfg.llm_api_key = os.environ[key]
                break
    if not cfg.llm_base_url or cfg.llm_base_url == Config.llm_base_url:
        if os.environ.get("OPENAI_BASE_URL"):
            cfg.llm_base_url = os.environ["OPENAI_BASE_URL"]
    return cfg


def save_config(cfg: Config) -> Path:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# bili-to-music-cli configuration", ""]
    for f in fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, bool):
            lines.append(f"{f.name} = {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{f.name} = {v}")
        else:
            # json.dumps produces a valid TOML basic string.
            lines.append(f"{f.name} = {json.dumps(str(v), ensure_ascii=True)}")
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass  # Windows may not support POSIX modes; fine.
    return CONFIG_PATH


def write_cookie_file(cfg: Config) -> Path | None:
    """Render Bili cookies in Netscape format for yt-dlp's `cookiefile`."""
    pairs = {
        "SESSDATA": cfg.sessdata,
        "bili_jct": cfg.bili_jct,
        "DedeUserID": cfg.dede_user_id,
        "buvid3": cfg.buvid3,
        "buvid4": cfg.buvid4,
    }
    if not any(pairs.values()):
        return None
    APP_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Netscape HTTP Cookie File", "# generated by bili-to-music-cli", ""]
    for name, value in pairs.items():
        if value:
            lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    COOKIE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(COOKIE_PATH, 0o600)
    except OSError:
        pass
    return COOKIE_PATH
