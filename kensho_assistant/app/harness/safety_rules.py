from __future__ import annotations

import re
from typing import Any

from kensho_assistant.app.privacy_guard import redact_personal_info


EXAGGERATION_PHRASES = (
    "完全自動",
    "誰でもできる",
    "寝ている間に稼げる",
    "API不要",
    "無料で無限",
    "絶対",
    "公式が発表",
    "激変",
    "最強",
    "これだけでOK",
)

OFFICIAL_CHECK_GENRES = (
    "年金",
    "税金",
    "保険",
    "医療",
    "育児",
    "法律",
    "防犯",
    "金融",
    "行政制度",
)

TOKEN_RE = re.compile(
    r"(?i)\b(api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|bearer\s+token|token)\b\s*[:=]\s*([^\s,;\"']+)"
)


def find_exaggeration_flags(texts: list[str]) -> list[str]:
    joined = "\n".join(texts)
    return [phrase for phrase in EXAGGERATION_PHRASES if phrase in joined]


def requires_official_check(query: str, texts: list[str]) -> bool:
    joined = query + "\n" + "\n".join(texts)
    return any(genre in joined for genre in OFFICIAL_CHECK_GENRES)


def sanitize_output(value: Any) -> Any:
    if isinstance(value, str):
        safe = redact_personal_info(value)
        return TOKEN_RE.sub(r"\1=[redacted]", safe)
    if isinstance(value, dict):
        return {key: sanitize_output(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_output(item) for item in value]
    return value
