"""技能文件的分发：`b2m skill` 用于把 SKILL.md 装到 Agent 的 skills 目录。

Skill 文件随 wheel 一起分发（package-data），因此 `b2m skill` 在任何安装方式下都可用。
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

SKILL_DIR_NAME = "bili-download"

# 常见 Agent 的 skill 根目录（相对用户主目录）
KNOWN_TARGETS = {
    "workbuddy": Path(".workbuddy") / "skills",
    "claude": Path(".claude") / "skills",
    "cursor": Path(".cursor") / "skills",
    "codex": Path(".codex") / "skills",
}


def read_skill() -> str:
    """返回内置 SKILL.md 的文本。"""
    try:
        ref = resources.files("bili2music") / "skills" / SKILL_DIR_NAME / "SKILL.md"
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        # 源码模式下的回退（未打包时包数据可能不可见）
        fallback = Path(__file__).parent / "skills" / SKILL_DIR_NAME / "SKILL.md"
        if fallback.is_file():
            return fallback.read_text(encoding="utf-8")
        raise RuntimeError(
            "内置技能文件缺失，请升级 b2m，或到仓库 skills/bili-download/SKILL.md 手动获取"
        )


def default_target() -> Path:
    """按运行环境猜一个最可能的目标目录。"""
    home = Path.home()
    marker_order = [
        ("workbuddy", Path(".workbuddy")),
        ("claude", Path(".claude")),
        ("cursor", Path(".cursor")),
        ("codex", Path(".codex")),
    ]
    for _, marker in marker_order:
        if (home / marker).is_dir():
            return home / marker / "skills" / SKILL_DIR_NAME
    return home / ".workbuddy" / "skills" / SKILL_DIR_NAME


def install(target: Path) -> Path:
    """把 SKILL.md 写到 target 目录，返回写入的文件路径。"""
    target.mkdir(parents=True, exist_ok=True)
    dst = target / "SKILL.md"
    dst.write_text(read_skill(), encoding="utf-8")
    return dst


def resolve_target(name: str | None) -> Path:
    """把用户给的别名/路径解析成目标目录。"""
    if not name:
        return default_target()
    key = name.strip().lower()
    if key in KNOWN_TARGETS:
        return Path.home() / KNOWN_TARGETS[key] / SKILL_DIR_NAME
    return Path(name).expanduser() / SKILL_DIR_NAME
