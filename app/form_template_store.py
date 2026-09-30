"""Value-free, approved-origin mappings; never used by the pilot."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from . import paths
from .extension_bridge import ALLOWED_PAYLOAD_KEYS
from kensho_assistant.scripts.build_dedicated_extension import load_approved_origins

TEMPLATE_MAX_AGE_DAYS = 180
_LOCK = threading.RLock()
_KEYS = frozenset({"origin", "pathname", "fingerprint", "structureFingerprint",
    "extensionVersion", "extension_build_sha256", "humanConfirmedAt", "savedAt", "fields"})
# The extension only needs structural path and the approved decision on reload.
_FIELD_KEYS = frozenset({"path", "approvedProfileKey", "confidenceBand", "disabled", "readOnly"})
_EXTENSION_FIELD_KEYS = _FIELD_KEYS | {"fieldId", "fieldType", "inputType", "labelHash",
    "attributeHash", "optionShapeHash", "required", "selectorCandidates"}
_PROFILE_KEYS = ALLOWED_PAYLOAD_KEYS | {"full_name", "full_name_kana"}
_DOM_PATH = r"(?:[a-z][a-z0-9]{0,20}\[[0-9]{1,5}\])(?:/[a-z][a-z0-9]{0,20}\[[0-9]{1,5}\])*"


def _guard():
    from .assisted_session import PilotIsolationError, pilot_storage_active
    if pilot_storage_active() is not None:
        raise PilotIsolationError("pilot_form_templates_forbidden")


def _string(value, pattern, limit=256):
    if not isinstance(value, str) or len(value) > limit or not re.fullmatch(pattern, value):
        raise ValueError("invalid_form_template")
    return value


def _timestamp(value):
    _string(value, r"[0-9T:.+Z-]+", 40)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError:
        raise ValueError("invalid_form_template") from None


def _validate(template):
    if not isinstance(template, dict) or set(template) - _KEYS:
        raise ValueError("invalid_form_template")
    if template.get("origin") not in load_approved_origins(paths.CONFIG_DIR / "approved_origins.json"):
        raise ValueError("unapproved_template_origin")
    origin = _string(template["origin"], r"https?://[a-zA-Z0-9.:[\]-]+", 255)
    pathname = _string(template.get("pathname"), r"/[a-zA-Z0-9_./-]*", 512)
    if re.search(r"\d{6,}|(?:^|/)\.\.?(?:/|$)", pathname) or "//" in pathname:
        raise ValueError("invalid_form_template")
    result = {"origin": origin, "pathname": pathname}
    for key in ("fingerprint", "structureFingerprint"):
        result[key] = _string(template.get(key), r"[a-f0-9]{8,64}", 64)
    result["extensionVersion"] = _string(template.get("extensionVersion"), r"[0-9]{1,5}(?:\.[0-9]{1,5}){1,3}", 24)
    result["extension_build_sha256"] = _string(template.get("extension_build_sha256"), r"[a-f0-9]{64}", 64)
    for key in ("humanConfirmedAt", "savedAt"):
        _timestamp(template.get(key))
        result[key] = template[key]
    if _timestamp(result["humanConfirmedAt"]) > datetime.now(timezone.utc):
        raise ValueError("invalid_form_template")
    fields = template.get("fields")
    if not isinstance(fields, list) or not 1 <= len(fields) <= 500:
        raise ValueError("invalid_form_template")
    result["fields"] = []
    seen = set()
    for field in fields:
        if not isinstance(field, dict) or set(field) - _FIELD_KEYS:
            raise ValueError("invalid_form_template")
        path = _string(field.get("path"), _DOM_PATH, 2048)
        if (path in seen or not isinstance(field.get("approvedProfileKey"), str)
            or field["approvedProfileKey"] not in _PROFILE_KEYS):
            raise ValueError("invalid_form_template")
        seen.add(path)
        for key in ("disabled", "readOnly"):
            if key in field and (type(field[key]) is not bool or field[key]):
                raise ValueError("invalid_form_template")
        if "confidenceBand" in field and (not isinstance(field["confidenceBand"], str)
            or field["confidenceBand"] not in {"high", "reviewed"}):
            raise ValueError("invalid_form_template")
        result["fields"].append(dict(field))
    return result


def from_extension(template):
    """Project sanitizer output; reject unknown keys before discarding metadata."""
    if not isinstance(template, dict) or set(template) - (_KEYS | {"schemaVersion"}):
        raise ValueError("invalid_form_template")
    if template.get("schemaVersion") != 1 or not isinstance(template.get("fields"), list):
        raise ValueError("invalid_form_template")
    fields = []
    for field in template["fields"]:
        if not isinstance(field, dict) or set(field) - _EXTENSION_FIELD_KEYS:
            raise ValueError("invalid_form_template")
        fields.append({key: field[key] for key in _FIELD_KEYS if key in field})
    return {**{key: value for key, value in template.items() if key != "schemaVersion"}, "fields": fields}


def _read_templates():
    _guard()
    path = paths.FORM_TEMPLATES_JSON
    if not path.exists():
        return []
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("invalid_form_template_store")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) > 1000:
        raise ValueError("invalid_form_template_store")
    return [_validate(item) for item in payload]


def load_templates():
    now = datetime.now(timezone.utc)
    return [item for item in _read_templates()
        if now - _timestamp(item["humanConfirmedAt"]) <= timedelta(days=TEMPLATE_MAX_AGE_DAYS)]


def get_templates_for_origin(origin, *, extension_version, build_sha256):
    return [item for item in load_templates() if item["origin"] == origin
        and item["extensionVersion"] == extension_version and item["extension_build_sha256"] == build_sha256]


def _write(records):
    path = paths.FORM_TEMPLATES_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".form-templates-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(records, stream, ensure_ascii=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_template(template, *, build_sha256):
    _guard()
    with _LOCK:
        if not isinstance(template, dict):
            raise ValueError("invalid_form_template")
        if "savedAt" in template:
            _timestamp(template["savedAt"])
        if "extension_build_sha256" in template and template["extension_build_sha256"] != build_sha256:
            raise ValueError("invalid_form_template")
        validated = _validate({**template, "extension_build_sha256": build_sha256,
            "savedAt": datetime.now(timezone.utc).isoformat()})
        records = load_templates()
        existing = next((item for item in records if (item["origin"], item["pathname"]) ==
            (validated["origin"], validated["pathname"])), None)
        if existing:
            content = lambda item: {k: v for k, v in item.items() if k not in {"humanConfirmedAt", "savedAt"}}
            return "unchanged" if content(existing) == content(validated) else "conflict"
        if len(records) >= 1000:
            raise ValueError("form_template_store_full")
        _write([*records, validated])
        return "saved"


def revoke(origin=None, pathname=None):
    _guard()
    with _LOCK:
        records = _read_templates()
        kept = [item for item in records if not ((origin is None or item["origin"] == origin)
            and (pathname is None or item["pathname"] == pathname))]
        removed = len(records) - len(kept)
        if paths.FORM_TEMPLATES_JSON.exists():
            _write(kept)
        return removed


def list_summaries():
    return [{"origin": item["origin"], "pathname": item["pathname"],
        "field_count": len(item["fields"]), "humanConfirmedAt": item["humanConfirmedAt"]}
        for item in load_templates()]
