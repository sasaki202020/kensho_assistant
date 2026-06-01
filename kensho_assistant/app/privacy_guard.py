from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,64})@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PHONE_RE = re.compile(r"(?<!\d)(0\d{1,3})[- ]?(\d{2,4})[- ]?(\d{3,4})(?!\d)")
POSTAL_RE = re.compile(r"(?<!\d)(\d{3})-?(\d{4})(?!\d)")
BIRTHDATE_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})[/-](\d{1,2})[/-](\d{1,2})(?!\d)|(?<!\d)((?:19|20)\d{2})年(\d{1,2})月(\d{1,2})日(?!\d)")
COOKIE_RE = re.compile(r"(?i)\b(cookie|session|sessionid|csrf|xsrf|token)\b[=:]\s*[^,\s;]+")

SENSITIVE_KEYS = {
    "last_name",
    "first_name",
    "last_name_kana",
    "first_name_kana",
    "postal_code",
    "prefecture",
    "city",
    "address1",
    "address2",
    "phone",
    "email",
    "gender",
    "birth_year",
    "birth_month",
    "birth_day",
}

SENSITIVE_LABELS = {
    "cookie",
    "session",
    "sessionid",
    "csrf",
    "xsrf",
    "token",
    "html",
    "formvalue",
    "入力済み",
}


def detect_email(text: str) -> bool:
    return bool(EMAIL_RE.search(text or ""))


def detect_phone(text: str) -> bool:
    return bool(PHONE_RE.search(text or ""))


def detect_postal_code(text: str) -> bool:
    return bool(POSTAL_RE.search(text or ""))


def detect_birthdate(text: str) -> bool:
    return bool(BIRTHDATE_RE.search(text or ""))


def redact_email(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        local, domain = match.group(1), match.group(2)
        prefix = local[:2] if len(local) > 2 else local[:1]
        return f"{prefix}***@{domain}"

    return EMAIL_RE.sub(_replace, text)


def redact_phone(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < 10:
            return match.group(0)
        return f"{digits[:3]}-****-{digits[-4:]}"

    return PHONE_RE.sub(_replace, text)


def redact_postal_code(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}-****"

    return POSTAL_RE.sub(_replace, text)


def redact_birthdate(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        year = match.group(1) or match.group(4)
        return f"{year}-**-**"

    return BIRTHDATE_RE.sub(_replace, text)


def redact_personal_info(text: str) -> str:
    safe = text or ""
    safe = redact_email(safe)
    safe = redact_phone(safe)
    safe = redact_postal_code(safe)
    safe = redact_birthdate(safe)
    safe = COOKIE_RE.sub("[redacted cookie/session]", safe)
    return safe


def sanitize_exception_message(error: BaseException | str) -> str:
    text = str(error)
    text = redact_personal_info(text)
    return text


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_personal_info(value)
    if isinstance(value, Mapping):
        return sanitize_log_payload(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_sanitize_value(item) for item in value]
    return value


def sanitize_log_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).casefold()
        if lowered in SENSITIVE_KEYS or any(label in lowered for label in SENSITIVE_LABELS):
            sanitized[key] = "[redacted]"
        else:
            sanitized[key] = _sanitize_value(value)
    return sanitized


def assert_no_personal_info(payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str) if not isinstance(payload, str) else payload
    if detect_email(text) or detect_phone(text) or detect_postal_code(text) or detect_birthdate(text) or COOKIE_RE.search(text):
        raise ValueError("personal information detected in payload")
    lowered = text.casefold()
    if any(label in lowered for label in SENSITIVE_LABELS):
        raise ValueError("personal information detected in payload")


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 10:
        return value
    return f"{digits[:3]}-****-{digits[-4:]}"


def mask_email(value: str) -> str:
    if "@" not in value:
        return value
    local, domain = value.split("@", 1)
    prefix = local[:2] if len(local) > 2 else local[:1]
    return f"{prefix}***@{domain}"


def mask_name(last_name: str, first_name: str) -> str:
    if not last_name and not first_name:
        return ""
    if last_name and first_name:
        return f"{last_name} **"
    return f"{last_name or first_name} **"


def mask_profile(profile: Mapping[str, str]) -> dict[str, str]:
    masked = dict(profile)
    if profile.get("phone"):
        masked["phone"] = mask_phone(profile["phone"])
    if profile.get("email"):
        masked["email"] = mask_email(profile["email"])
    masked["name_masked"] = mask_name(profile.get("last_name", ""), profile.get("first_name", ""))
    return masked

