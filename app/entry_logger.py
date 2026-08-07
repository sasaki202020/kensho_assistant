from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from .models import ENTRY_HEADERS
from .paths import ENTRIES_CSV, RUN_LOG
from .privacy_guard import sanitize_log_payload, sanitize_exception_message
from .storage import ensure_csv, read_csv_rows, write_csv_rows


def make_entry_id(campaign_id: str, entry_url: str = "") -> str:
    payload = f"{campaign_id}|{entry_url}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def load_entries(path: str | Path | None = None) -> list[dict[str, str]]:
    entries_path = Path(path) if path else ENTRIES_CSV
    rows = read_csv_rows(entries_path)
    if path:
        return rows
    try:
        from .entry_history import load_entry_history

        history_rows = load_entry_history()
    except Exception:
        history_rows = []
    merged: dict[str, dict[str, str]] = {}
    for row in rows + history_rows:
        key = row.get("entry_id", "") or row.get("campaign_id", "") or row.get("entry_url", "") or row.get("url", "")
        if not key:
            key = str(len(merged))
        merged[key] = {**merged.get(key, {}), **row}
    return list(merged.values())


def save_entries(rows: Iterable[Mapping[str, object]], path: str | Path | None = None) -> None:
    write_csv_rows(Path(path) if path else ENTRIES_CSV, rows, ENTRY_HEADERS)


def ensure_entries_store(path: str | Path | None = None) -> None:
    ensure_csv(Path(path) if path else ENTRIES_CSV, ENTRY_HEADERS)


def is_duplicate_campaign(campaign: Mapping[str, str], entries: Iterable[Mapping[str, str]]) -> bool:
    campaign_id = campaign.get("campaign_id", "")
    entry_url = campaign.get("entry_url", "")
    name = campaign.get("campaign_name", "")
    provider = campaign.get("provider", "")
    deadline = campaign.get("deadline", "")
    for row in entries:
        if campaign_id and campaign_id == row.get("campaign_id", ""):
            return True
        if entry_url and entry_url == row.get("entry_url", ""):
            return True
        if name and provider and deadline and name == row.get("campaign_name", "") and provider == row.get("provider", "") and deadline == row.get("deadline", ""):
            return True
    return False


def upsert_entry(record: Mapping[str, object], path: str | Path | None = None) -> None:
    entries_path = Path(path) if path else ENTRIES_CSV
    ensure_entries_store(entries_path)
    rows = read_csv_rows(entries_path)
    keys = {
        "entry_id": record.get("entry_id", ""),
        "campaign_id": record.get("campaign_id", ""),
    }
    updated = False
    for row in rows:
        if row.get("entry_id") == keys["entry_id"] or row.get("campaign_id") == keys["campaign_id"]:
            row.update({key: str(value) for key, value in record.items()})
            updated = True
            break
    if not updated:
        rows.append({key: str(record.get(key, "")) for key in ENTRY_HEADERS})
    save_entries(rows, entries_path)


def log_event(event: str, payload: Mapping[str, object] | None = None, path: str | Path | None = None) -> None:
    log_path = Path(path) if path else RUN_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = payload or {}
    safe_payload = sanitize_log_payload(payload)
    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": event,
        "payload": safe_payload,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def safe_exception_message(error: BaseException | str) -> str:
    return sanitize_exception_message(error)
