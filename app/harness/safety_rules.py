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
OPERATIONAL_ID_RE = re.compile(r"(?i)\b(?:later|campaign|queue)-[0-9a-f]{12}\b")

OPERATIONAL_REFERENCE_KEYS = {
    "campaign_id",
    "entry_id",
    "history_id",
    "id",
    "later_id",
    "normalized_url",
    "post_url",
    "queue_id",
    "resolved_entry_url",
    "url",
    "final_url",
}


def find_exaggeration_flags(texts: list[str]) -> list[str]:
    joined = "\n".join(texts)
    return [phrase for phrase in EXAGGERATION_PHRASES if phrase in joined]


def requires_official_check(query: str, texts: list[str]) -> bool:
    joined = query + "\n" + "\n".join(texts)
    return any(genre in joined for genre in OFFICIAL_CHECK_GENRES)


def sanitize_output(value: Any) -> Any:
    if isinstance(value, str):
        references: list[str] = []

        def protect_reference(match: re.Match[str]) -> str:
            references.append(match.group(0))
            return f"__OPERATIONAL_REFERENCE_{len(references) - 1}__"

        protected = OPERATIONAL_ID_RE.sub(protect_reference, value)
        safe = redact_personal_info(protected)
        for index, reference in enumerate(references):
            safe = safe.replace(f"__OPERATIONAL_REFERENCE_{index}__", reference)
        return TOKEN_RE.sub(r"\1=[redacted]", safe)
    if isinstance(value, dict):
        return {
            key: TOKEN_RE.sub(r"\1=[redacted]", item)
            if key in OPERATIONAL_REFERENCE_KEYS and isinstance(item, str)
            else sanitize_output(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_output(item) for item in value]
    return value
