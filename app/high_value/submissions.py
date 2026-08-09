from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from ..paths import HIGH_VALUE_SUBMISSIONS_JSON


class ManualSubmissionStoreError(RuntimeError):
    pass


def load_manual_submissions(path: Path = HIGH_VALUE_SUBMISSIONS_JSON) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManualSubmissionStoreError("high_value_submission_store_unreadable") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ManualSubmissionStoreError("high_value_submission_store_invalid")
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        raise ManualSubmissionStoreError("high_value_submission_store_invalid")
    result: dict[str, dict[str, str]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        campaign_id = str(record.get("campaign_id", "")).strip()
        if not campaign_id:
            continue
        result[campaign_id] = {
            "campaign_id": campaign_id,
            "manual_submitted_at": str(record.get("manual_submitted_at", "")),
            "application_mode": str(record.get("application_mode", "")),
        }
    return result


def _write_records(records: Iterable[Mapping[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "records": sorted(
            [
                {
                    "campaign_id": str(record.get("campaign_id", "")),
                    "manual_submitted_at": str(record.get("manual_submitted_at", "")),
                    "application_mode": str(record.get("application_mode", "")),
                }
                for record in records
                if str(record.get("campaign_id", "")).strip()
            ],
            key=lambda record: record["campaign_id"],
        ),
    }
    fd, temp_name = tempfile.mkstemp(prefix="high-value-submissions-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def mark_manual_submitted(
    campaign_id: str,
    application_mode: str,
    path: Path = HIGH_VALUE_SUBMISSIONS_JSON,
) -> tuple[bool, dict[str, str]]:
    normalized_id = str(campaign_id or "").strip()
    if not normalized_id:
        return False, {}
    records = load_manual_submissions(path)
    existing = records.get(normalized_id)
    if existing:
        return False, existing
    record = {
        "campaign_id": normalized_id,
        "manual_submitted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "application_mode": str(application_mode or "REVIEW_REQUIRED").strip(),
    }
    records[normalized_id] = record
    _write_records(records.values(), path)
    return True, record
