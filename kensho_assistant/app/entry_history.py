from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import ENTRY_HISTORY_HEADERS
from .paths import CAMPAIGNS_CSV, ENTRY_HISTORY_CSV, ENTRY_HISTORY_JSONL, WIN_MAIL_CANDIDATES_JSONL
from .privacy_guard import redact_personal_info, sanitize_log_payload
from .storage import read_csv_rows, write_csv_rows


NEWSLETTER_STATUSES = ("unknown", "opt_in", "opt_out", "unsubscribe_needed", "unsubscribed")
ENTRY_STATUSES = ("APPLIED", "PENDING_RESULT", "RESULT_CHECKED", "DUPLICATE", "SKIPPED", "HOLD")
ACTIVE_ENTRY_STATUSES = {"APPLIED", "PENDING_RESULT", "RESULT_CHECKED"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _collapse(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize_url(url: str) -> str:
    text = _collapse(url)
    if not text:
        return ""
    return text.rstrip("/").split("?", 1)[0]


def _duplicate_key(record: Mapping[str, object]) -> str:
    url = _normalize_url(str(record.get("url", "")))
    if url:
        return f"url:{url.casefold()}"
    title = _collapse(record.get("title", ""))
    deadline = _collapse(record.get("deadline", ""))
    prize = _collapse(record.get("prize", ""))
    basis = " | ".join(part for part in (title, deadline, prize) if part)
    if basis:
        return f"text:{basis.casefold()}"
    campaign_id = _collapse(record.get("campaign_id", ""))
    if campaign_id:
        return f"campaign:{campaign_id}"
    return ""


def _resolve_path(path: Path | None, default: Path) -> Path:
    return path if path is not None else default


def build_duplicate_key(record: Mapping[str, object]) -> str:
    return _duplicate_key(record)


def _sanitize_record(record: Mapping[str, object]) -> dict[str, str]:
    payload = sanitize_log_payload(dict(record))
    cleaned: dict[str, str] = {}
    for key in ENTRY_HISTORY_HEADERS:
        value = payload.get(key, "")
        if key == "pii_used":
            cleaned[key] = "true" if str(value).casefold() in {"true", "1", "yes"} else "false"
            continue
        cleaned[key] = redact_personal_info(str(value or "")).strip()
    cleaned["newsletter_status"] = cleaned.get("newsletter_status", "unknown") or "unknown"
    if cleaned["newsletter_status"] not in NEWSLETTER_STATUSES:
        cleaned["newsletter_status"] = "unknown"
    cleaned["status"] = cleaned.get("status", "").upper() or "APPLIED"
    if cleaned["status"] not in ENTRY_STATUSES:
        cleaned["status"] = cleaned["status"].upper() or "APPLIED"
    cleaned["duplicate_key"] = cleaned.get("duplicate_key", "") or _duplicate_key(cleaned)
    cleaned["created_at"] = cleaned.get("created_at", "") or _now()
    cleaned["updated_at"] = _now()
    if not cleaned["applied_at"] and cleaned["status"] == "APPLIED":
        cleaned["applied_at"] = _now()
    return cleaned


def ensure_entry_history_store(path: Path | None = None) -> None:
    path = _resolve_path(path, ENTRY_HISTORY_JSONL)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def load_entry_history(path: Path | None = None) -> list[dict[str, str]]:
    path = _resolve_path(path, ENTRY_HISTORY_JSONL)
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows.append({key: str(row.get(key, "")) for key in ENTRY_HISTORY_HEADERS})
    return rows


def save_entry_history(rows: Iterable[Mapping[str, object]], path: Path | None = None) -> None:
    path = _resolve_path(path, ENTRY_HISTORY_JSONL)
    ensure_entry_history_store(path)
    records = [_sanitize_record(row) for row in rows]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def upsert_entry_history(record: Mapping[str, object], path: Path | None = None) -> dict[str, str]:
    path = _resolve_path(path, ENTRY_HISTORY_JSONL)
    rows = load_entry_history(path)
    row = _sanitize_record(record)
    duplicate_key = row.get("duplicate_key", "")
    campaign_id = row.get("campaign_id", "")
    updated = False
    for index, existing in enumerate(rows):
        if campaign_id and existing.get("campaign_id") == campaign_id:
            rows[index] = {**existing, **row, "created_at": existing.get("created_at", row["created_at"]), "updated_at": _now()}
            updated = True
            row = rows[index]
            break
        if duplicate_key and existing.get("duplicate_key") == duplicate_key:
            rows[index] = {**existing, **row, "created_at": existing.get("created_at", row["created_at"]), "updated_at": _now()}
            updated = True
            row = rows[index]
            break
    if not updated:
        rows.append(row)
    save_entry_history(rows, path)
    return row


def _campaign_lookup() -> list[dict[str, str]]:
    if not CAMPAIGNS_CSV.exists():
        return []
    return read_csv_rows(CAMPAIGNS_CSV)


def _campaign_from_url(url: str) -> dict[str, str]:
    normalized = _normalize_url(url)
    if not normalized:
        return {}
    for row in _campaign_lookup():
        for candidate in (row.get("resolved_entry_url", ""), row.get("entry_url", ""), row.get("knshow_url", "")):
            if candidate and _normalize_url(candidate) == normalized:
                return row
    return {}


def _campaign_from_id(campaign_id: str) -> dict[str, str]:
    campaign_id = _collapse(campaign_id)
    if not campaign_id:
        return {}
    for row in _campaign_lookup():
        if row.get("campaign_id", "") == campaign_id:
            return row
    return {}


def build_entry_record(
    *,
    campaign_id: str = "",
    title: str = "",
    source_site: str = "",
    url: str = "",
    prize: str = "",
    deadline: str = "",
    applied_at: str = "",
    result_check_date: str = "",
    status: str = "APPLIED",
    newsletter_status: str = "unknown",
    pii_used: bool | str = False,
    memo: str = "",
    duplicate_key: str = "",
) -> dict[str, object]:
    campaign = _campaign_from_url(url) if url else _campaign_from_id(campaign_id)
    row = {
        "campaign_id": campaign_id or campaign.get("campaign_id", ""),
        "title": title or campaign.get("campaign_name", "") or url,
        "source_site": source_site or campaign.get("source", "") or "knshow",
        "url": url or campaign.get("resolved_entry_url", "") or campaign.get("entry_url", "") or campaign.get("knshow_url", ""),
        "prize": prize or campaign.get("prize", ""),
        "deadline": deadline or campaign.get("deadline", ""),
        "applied_at": applied_at,
        "result_check_date": result_check_date,
        "status": status or "APPLIED",
        "newsletter_status": newsletter_status or "unknown",
        "pii_used": pii_used,
        "memo": memo,
        "duplicate_key": duplicate_key or build_duplicate_key({
            "campaign_id": campaign_id or campaign.get("campaign_id", ""),
            "title": title or campaign.get("campaign_name", "") or url,
            "deadline": deadline or campaign.get("deadline", ""),
            "prize": prize or campaign.get("prize", ""),
            "url": url or campaign.get("resolved_entry_url", "") or campaign.get("entry_url", "") or campaign.get("knshow_url", ""),
        }),
    }
    return row


def add_entry_history(record: Mapping[str, object], path: Path | None = None) -> dict[str, str]:
    return upsert_entry_history(record, path)


def mark_entry_applied(
    campaign_id: str,
    *,
    url: str = "",
    title: str = "",
    source_site: str = "",
    prize: str = "",
    deadline: str = "",
    result_check_date: str = "",
    newsletter_status: str = "unknown",
    memo: str = "",
    pii_used: bool | str = False,
    path: Path | None = None,
) -> dict[str, str]:
    record = build_entry_record(
        campaign_id=campaign_id,
        title=title,
        source_site=source_site,
        url=url,
        prize=prize,
        deadline=deadline,
        result_check_date=result_check_date,
        status="APPLIED",
        newsletter_status=newsletter_status,
        pii_used=pii_used,
        memo=memo,
    )
    if not record.get("applied_at"):
        record["applied_at"] = _now()
    return upsert_entry_history(record, path)


def search_entry_history(keyword: str, path: Path | None = None) -> list[dict[str, str]]:
    path = _resolve_path(path, ENTRY_HISTORY_JSONL)
    query = keyword.casefold().strip()
    if not query:
        return load_entry_history(path)
    rows = load_entry_history(path)
    filtered: list[dict[str, str]] = []
    for row in rows:
        haystack = " ".join(
            row.get(field, "")
            for field in ("campaign_id", "title", "source_site", "url", "prize", "deadline", "status", "newsletter_status", "memo", "duplicate_key")
        ).casefold()
        if query in haystack:
            filtered.append(row)
    return filtered


def duplicate_entry_groups(rows: Iterable[Mapping[str, object]] | None = None, path: Path | None = None) -> list[dict[str, object]]:
    source_rows = list(rows) if rows is not None else load_entry_history(path)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        key = str(row.get("duplicate_key", "") or build_duplicate_key(row))
        if key:
            grouped[key].append({key_name: str(row.get(key_name, "")) for key_name in ENTRY_HISTORY_HEADERS})
    groups: list[dict[str, object]] = []
    for key, group_rows in grouped.items():
        if len(group_rows) <= 1:
            continue
        groups.append(
            {
                "duplicate_key": key,
                "count": len(group_rows),
                "items": group_rows,
            }
        )
    return sorted(groups, key=lambda row: (-int(row["count"]), str(row["duplicate_key"])))


def duplicate_entry_rows(rows: Iterable[Mapping[str, object]] | None = None) -> list[dict[str, str]]:
    groups = duplicate_entry_groups(rows)
    output: list[dict[str, str]] = []
    for group in groups:
        for row in group["items"]:
            item = dict(row)
            item["duplicate_count"] = str(group["count"])
            output.append(item)
    return output


def summarize_entry_history(rows: Iterable[Mapping[str, object]] | None = None, path: Path | None = None) -> dict[str, int]:
    source_rows = list(rows) if rows is not None else load_entry_history(path)
    summary = Counter(
        {
            "total": 0,
            "today_deadline": 0,
            "week_deadline": 0,
            "applied": 0,
            "result_pending": 0,
            "newsletter_unsubscribe_needed": 0,
            "newsletter_opt_out": 0,
            "duplicate_candidates": 0,
        }
    )
    duplicate_keys = Counter()
    for row in source_rows:
        summary["total"] += 1
        status = str(row.get("status", "")).upper()
        newsletter_status = str(row.get("newsletter_status", "unknown")).lower()
        deadline = _deadline_bucket(str(row.get("deadline", "")))
        if status == "APPLIED":
            summary["applied"] += 1
        if status in {"APPLIED", "PENDING_RESULT"}:
            summary["result_pending"] += 1
        if newsletter_status == "unsubscribe_needed":
            summary["newsletter_unsubscribe_needed"] += 1
        if newsletter_status == "opt_out":
            summary["newsletter_opt_out"] += 1
        if deadline == 0:
            summary["today_deadline"] += 1
        elif 0 < deadline <= 7:
            summary["week_deadline"] += 1
        duplicate_key = str(row.get("duplicate_key", "") or build_duplicate_key(row))
        if duplicate_key:
            duplicate_keys[duplicate_key] += 1
    summary["duplicate_candidates"] = sum(1 for count in duplicate_keys.values() if count > 1)
    return dict(summary)


def _deadline_bucket(value: str) -> int:
    text = _collapse(value)
    if not text:
        return 99
    today = date.today()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(text, fmt).date()
            delta = (dt - today).days
            if delta < 0:
                return 999
            return delta
        except ValueError:
            continue
    if "今日" in text or "本日" in text:
        return 0
    if "明日" in text:
        return 1
    if "今週" in text or "週末" in text:
        return 2
    m = json.dumps(text, ensure_ascii=False)
    if "期限切れ" in m or "終了" in m:
        return 999
    return 99


def export_entry_history_csv(output_path: Path | None = None, path: Path | None = None) -> Path:
    output_path = _resolve_path(output_path, ENTRY_HISTORY_CSV)
    rows = load_entry_history(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_rows(output_path, rows, ENTRY_HISTORY_HEADERS)
    return output_path


def load_win_mail_candidates(path: Path | None = None) -> list[dict[str, object]]:
    path = _resolve_path(path, WIN_MAIL_CANDIDATES_JSONL)
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows.append(row)
    return rows


def save_win_mail_candidates(rows: Iterable[Mapping[str, object]], path: Path | None = None) -> None:
    path = _resolve_path(path, WIN_MAIL_CANDIDATES_JSONL)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_rows = [sanitize_log_payload(dict(row)) for row in rows]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in safe_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_win_mail_candidates(rows: Iterable[Mapping[str, object]] | None = None, path: Path | None = None) -> dict[str, int]:
    source_rows = list(rows) if rows is not None else load_win_mail_candidates(path)
    summary = Counter({"total": len(source_rows), "candidate": 0, "danger": 0, "duplicate": 0})
    for row in source_rows:
        status = str(row.get("status", "candidate"))
        if status in summary:
            summary[status] += 1
        else:
            summary["candidate"] += 1
    return dict(summary)


def build_win_mail_candidate(mail_item: Mapping[str, object]) -> dict[str, object]:
    subject = str(mail_item.get("subject", ""))
    sender = str(mail_item.get("sender", ""))
    urls = mail_item.get("urls", [])
    if not isinstance(urls, list):
        urls = [str(urls)] if str(urls).strip() else []
    candidate_id = str(mail_item.get("mail_id", "")) or hashlib.sha1(f"{subject}|{sender}|{mail_item.get('received_at', '')}".encode("utf-8")).hexdigest()[:12]
    return {
        "candidate_id": f"mail-{candidate_id}",
        "mail_id": str(mail_item.get("mail_id", "")),
        "source_file": str(mail_item.get("source_file", "")),
        "subject": subject,
        "sender": sender,
        "received_at": str(mail_item.get("received_at", "")),
        "campaign_url": str(mail_item.get("campaign_url", "")),
        "deadline_text": str(mail_item.get("deadline_text", "")),
        "risk_level": str(mail_item.get("risk_level", "low")),
        "risk_reasons": list(mail_item.get("risk_reasons", []) or []),
        "status": str(mail_item.get("status", "candidate")),
        "keyword_hits": list(mail_item.get("keyword_hits", []) or []),
        "urls": [str(url) for url in urls if str(url).strip()],
        "updated_at": str(mail_item.get("updated_at", _now())),
    }
