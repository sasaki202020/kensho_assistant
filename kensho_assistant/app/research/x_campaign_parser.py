from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any


x_campaign_fields = [
    "candidate_id",
    "source",
    "platform",
    "query",
    "status",
    "title",
    "organizer",
    "account_handle",
    "post_url",
    "campaign_url",
    "prize",
    "deadline",
    "requirements",
    "eligibility",
    "age_requirement",
    "region_requirement",
    "risk_flags",
    "safety_score",
    "trust_score",
    "ease_score",
    "value_score",
    "deadline_score",
    "total_score",
    "recommendation",
    "recommendation_reason",
    "apply_difficulty",
    "confidence",
    "queue_status",
    "queue_reason",
    "raw_text",
    "collected_at",
]


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _clean_text(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    chunks = re.split(r"[,\n/、]+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    if value is None:
        return ""
    return _clean_text(value)


def _candidate_id(item: dict[str, Any]) -> str:
    seed = _clean_text(item.get("post_url")) or _clean_text(item.get("campaign_url")) or json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _extract_json_text(text: str) -> str:
    stripped = _clean_text(text)
    if not stripped:
        return ""
    if stripped.startswith("[") or stripped.startswith("{"):
        return stripped
    code_fences = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    for block in code_fences:
        block = block.strip()
        if block.startswith("[") or block.startswith("{"):
            return block
    first = stripped.find("[")
    last = stripped.rfind("]")
    if first != -1 and last != -1 and last > first:
        return stripped[first : last + 1]
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first != -1 and last != -1 and last > first:
        return stripped[first : last + 1]
    return ""


def _load_json_payload(text: str) -> list[dict[str, Any]]:
    json_text = _extract_json_text(text)
    if not json_text:
        return []
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        for key in ("items", "campaigns", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                payload = value
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def extract_x_campaigns(text: str) -> list[dict[str, Any]]:
    return _load_json_payload(text)


def normalize_x_campaigns(text: str, *, query: str, source: str = "hermes_x_search") -> list[dict[str, object]]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    normalized: list[dict[str, object]] = []
    for item in extract_x_campaigns(text):
        post_url = _as_text(item.get("post_url"))
        if not post_url:
            continue
        candidate = {
            "candidate_id": _candidate_id(item),
            "source": source,
            "platform": _as_text(item.get("platform")) or "x",
            "query": query,
            "status": _as_text(item.get("status")) or "research_found",
            "title": _as_text(item.get("title")),
            "organizer": _as_text(item.get("organizer")),
            "account_handle": _as_text(item.get("account_handle")),
            "post_url": post_url,
            "campaign_url": _as_text(item.get("campaign_url")),
            "prize": _as_text(item.get("prize")),
            "deadline": _as_text(item.get("deadline")),
            "requirements": _as_list(item.get("requirements")),
            "eligibility": _as_text(item.get("eligibility")),
            "age_requirement": _as_text(item.get("age_requirement")),
            "region_requirement": _as_text(item.get("region_requirement")),
            "risk_flags": _as_list(item.get("risk_flags")),
            "safety_score": _as_float(item.get("safety_score"), default=0.0),
            "trust_score": _as_float(item.get("trust_score"), default=0.0),
            "ease_score": _as_float(item.get("ease_score"), default=0.0),
            "value_score": _as_float(item.get("value_score"), default=0.0),
            "deadline_score": _as_float(item.get("deadline_score"), default=0.0),
            "total_score": _as_float(item.get("total_score"), default=0.0),
            "recommendation": _as_text(item.get("recommendation")),
            "recommendation_reason": _as_text(item.get("recommendation_reason")),
            "apply_difficulty": _as_text(item.get("apply_difficulty")),
            "confidence": _as_float(item.get("confidence"), default=0.0),
            "queue_status": _as_text(item.get("queue_status")) or "research_found",
            "queue_reason": _as_text(item.get("queue_reason")),
            "raw_text": json.dumps(item, ensure_ascii=False, sort_keys=True),
            "collected_at": now,
        }
        normalized.append(candidate)
    return normalized
