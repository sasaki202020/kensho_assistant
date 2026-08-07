from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .paths import APPLY_RUNS_DIR
from .privacy_guard import redact_personal_info


def append_apply_run(record: dict[str, object]) -> Path:
    APPLY_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    path = APPLY_RUNS_DIR / f"{now.strftime('%Y-%m-%d')}.jsonl"
    payload = dict(record)
    payload["created_at"] = payload.get("created_at") or now.isoformat(timespec="seconds")
    if payload.get("url"):
        parts = urlsplit(str(payload["url"]))
        payload["url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    safe_text = redact_personal_info(json.dumps(payload, ensure_ascii=False))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(safe_text + "\n")
    return path
