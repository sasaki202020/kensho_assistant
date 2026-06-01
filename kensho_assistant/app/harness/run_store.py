from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from kensho_assistant.app.paths import RESEARCH_X_HARNESS_DIR

from .safety_rules import sanitize_output


def day_key(run_date: date | None = None) -> str:
    return (run_date or date.today()).strftime("%Y%m%d")


def slugify(value: str) -> str:
    digest = hashlib.sha1((value or "x-research").encode("utf-8")).hexdigest()[:10]
    text = re.sub(r"[^0-9A-Za-z]+", "-", (value or "").strip().casefold())
    text = re.sub(r"-+", "-", text).strip("-")
    if text:
        return f"{text[:60]}-{digest}"
    return f"x-research-{digest}"


def build_output_dir(query: str, *, output_root: Path | None = None, run_date: date | None = None) -> Path:
    root = output_root or RESEARCH_X_HARNESS_DIR
    safe_query = str(sanitize_output(query))
    return root / day_key(run_date) / slugify(safe_query)


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = sanitize_output(payload)
    path.write_text(json.dumps(safe_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(sanitize_output(text)).rstrip() + "\n", encoding="utf-8")
    return path


def write_json_raw(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_sources_csv(path: Path, posts: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["author", "handle", "post_url", "engagement_hint"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for post in posts:
            row = sanitize_output({name: post.get(name, "") for name in fieldnames})
            writer.writerow(row)
    return path


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
