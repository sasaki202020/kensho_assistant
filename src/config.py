from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw in {"true", "True"}:
        return True
    if raw in {"false", "False"}:
        return False
    if raw in {"null", "None", "~"}:
        return None
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1]
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(",")]
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def load_simple_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if stripped.startswith("- "):
            key = "__list__"
            current.setdefault(key, [])
            current[key].append(_parse_scalar(stripped[2:]))
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not value:
                new_dict: dict[str, Any] = {}
                current[key] = new_dict
                stack.append((indent + 2, new_dict))
            else:
                current[key] = _parse_scalar(value)
    return root


@dataclass
class AppConfig:
    project_name: str = "pension-video-maker"
    output_root: str = "output"
    video_width: int = 1920
    video_height: int = 1080
    fps: int = 30
    target_seconds: int = 600
    subtitle_font_size: int = 30
    subtitle_margin_v: int = 42
    title_font_size: int = 66
    body_font_size: int = 44
    footer_font_size: int = 26
    panel_radius: int = 36
    accent_color: str = "#2E5E8A"
    bg_colors: list[str] = field(
        default_factory=lambda: ["#FFFFFF", "#F5F0E6", "#EAF3FF"]
    )
    tts_preferred_engine: str = "auto"
    tts_rate: int = 145
    openai_model: str = "gpt-4.1-mini"
    openai_voice: str = "alloy"
    openai_tts_model: str = "gpt-4o-mini-tts"


def load_config(path: Path) -> AppConfig:
    data = load_simple_yaml(path)
    video = data.get("video", {})
    theme = data.get("theme", {})
    tts = data.get("tts", {})
    bg_colors = theme.get("bg_colors", ["#FFFFFF", "#F5F0E6", "#EAF3FF"])
    if isinstance(bg_colors, dict):
        bg_colors = bg_colors.get("__list__", ["#FFFFFF", "#F5F0E6", "#EAF3FF"])
    if not isinstance(bg_colors, list):
        bg_colors = ["#FFFFFF", "#F5F0E6", "#EAF3FF"]
    return AppConfig(
        project_name=data.get("project_name", "pension-video-maker"),
        output_root=data.get("output_root", "output"),
        video_width=int(video.get("width", 1920)),
        video_height=int(video.get("height", 1080)),
        fps=int(video.get("fps", 30)),
        target_seconds=int(video.get("target_seconds", 600)),
        subtitle_font_size=int(video.get("subtitle_font_size", 30)),
        subtitle_margin_v=int(video.get("subtitle_margin_v", 42)),
        title_font_size=int(theme.get("title_font_size", 66)),
        body_font_size=int(theme.get("body_font_size", 44)),
        footer_font_size=int(theme.get("footer_font_size", 26)),
        panel_radius=int(theme.get("panel_radius", 36)),
        accent_color=str(theme.get("accent_color", "#2E5E8A")),
        bg_colors=list(bg_colors),
        tts_preferred_engine=str(tts.get("preferred_engine", "auto")),
        tts_rate=int(tts.get("rate", 145)),
        openai_model=str(tts.get("openai_model", "gpt-4.1-mini")),
        openai_voice=str(tts.get("openai_voice", "alloy")),
        openai_tts_model=str(tts.get("openai_tts_model", "gpt-4o-mini-tts")),
    )
