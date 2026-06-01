from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from .entry_history import mark_entry_applied
from .models import LATER_QUEUE_HEADERS
from .paths import CAMPAIGNS_CSV, LATER_QUEUE_JSONL
from .privacy_guard import redact_personal_info, sanitize_log_payload
from .storage import read_csv_rows


LATER_QUEUE_STATUSES = (
    "queued",
    "needs_review",
    "reviewing",
    "ready_for_fill",
    "applied_manual",
    "skipped",
    "expired",
    "blocked",
)

LATER_QUEUE_TERMINAL_STATUSES = {"applied_manual", "skipped", "expired", "blocked"}
LATER_QUEUE_SOURCE_TYPES = ("manual_url", "auto_scan", "mail_import")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _collapse(value: object) -> str:
    return " ".join(str(value or "").split())


def _resolve_path(path: Path | None, default: Path) -> Path:
    return path if path is not None else default


def _ensure_scheme(url: str) -> str:
    text = _collapse(url)
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    return text


def normalize_url(url: str) -> str:
    text = _ensure_scheme(url)
    if not text:
        return ""
    parts = urlsplit(text)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = re.sub(r"/+$", "", parts.path or "")
    if not netloc and path:
        return path.casefold()
    return urlunsplit((scheme, netloc, path, "", ""))


def build_duplicate_key(normalized_url: str) -> str:
    text = normalize_url(normalized_url)
    return f"url:{text.casefold()}" if text else ""


def _deadline_bucket(value: str) -> tuple[int, str]:
    text = _collapse(value)
    if not text or text.casefold() == "unknown":
        return (9999, "unknown")
    today = date.today()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(text, fmt).date()
            delta = (dt - today).days
            return (delta, text)
        except ValueError:
            continue
    if any(keyword in text for keyword in ("今日", "本日")):
        return (0, text)
    if any(keyword in text for keyword in ("明日",)):
        return (1, text)
    if any(keyword in text for keyword in ("今週", "週末")):
        return (7, text)
    return (9999, text)


def _effective_status(row: Mapping[str, object]) -> str:
    status = _collapse(row.get("status", "")).casefold() or "queued"
    if status in LATER_QUEUE_TERMINAL_STATUSES:
        return status
    deadline_bucket, _ = _deadline_bucket(str(row.get("deadline", "")))
    if deadline_bucket == 9999:
        return status
    if deadline_bucket == 0 and str(row.get("deadline", "")).casefold() in {"unknown", ""}:
        return status
    if deadline_bucket < 0:
        return "expired"
    return status


def _campaign_rows() -> list[dict[str, str]]:
    if not CAMPAIGNS_CSV.exists():
        return []
    return read_csv_rows(CAMPAIGNS_CSV)


def _campaign_from_url(url: str) -> dict[str, str]:
    normalized = normalize_url(url)
    if not normalized:
        return {}
    for row in _campaign_rows():
        candidates = [row.get("resolved_entry_url", ""), row.get("entry_url", ""), row.get("knshow_url", "")]
        for candidate in candidates:
            if candidate and normalize_url(candidate) == normalized:
                return row
    return {}


def _is_public_host(host: str) -> bool:
    text = _collapse(host).casefold()
    if not text or text in {"localhost", "localhost.localdomain"} or text.endswith(".local"):
        return False
    try:
        infos = socket.getaddrinfo(text, None)
    except Exception:
        return False
    saw_ip = False
    for family, _, _, _, sockaddr in infos:
        ip_text = sockaddr[0] if sockaddr else ""
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        saw_ip = True
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return saw_ip


def _fetch_public_html(url: str, max_redirects: int = 3) -> tuple[str, str]:
    current = _ensure_scheme(url)
    for _ in range(max_redirects + 1):
        parts = urlsplit(current)
        if parts.scheme not in {"http", "https"} or not _is_public_host(parts.hostname or ""):
            raise ValueError("private_or_invalid_url")
        response = requests.get(
            current,
            timeout=10,
            allow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 KenshoAssistant/0.4.2"},
        )
        if 300 <= response.status_code < 400:
            location = response.headers.get("Location", "")
            if not location:
                raise ValueError("redirect_without_location")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        return response.text or "", response.url or current
    raise ValueError("too_many_redirects")


def _parse_page_metadata(url: str) -> dict[str, str]:
    metadata = {"title": "unknown", "site_name": "unknown", "deadline": "unknown"}
    target = _ensure_scheme(url)
    if not target:
        return metadata
    parts = urlsplit(target)
    metadata["site_name"] = parts.netloc or "unknown"
    if not parts.scheme or not parts.netloc:
        return metadata
    try:
        html, final_url = _fetch_public_html(target)
    except Exception:
        return metadata
    parts = urlsplit(final_url)
    metadata["site_name"] = parts.netloc or metadata["site_name"]
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        title = re.sub(r"\s+", " ", title_match.group(1)).strip()
        if title:
            metadata["title"] = title
    og_site = re.search(r'property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if og_site:
        metadata["site_name"] = re.sub(r"\s+", " ", og_site.group(1)).strip() or metadata["site_name"]
    og_title = re.search(r'property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if og_title and metadata["title"] == "unknown":
        title = re.sub(r"\s+", " ", og_title.group(1)).strip()
        if title:
            metadata["title"] = title
    deadline_patterns = [
        r"(?:締切|応募締切|応募期限|応募期間)[^0-9]{0,20}((?:20\d{2}[/-]\d{1,2}[/-]\d{1,2})|(?:\d{1,2}月\d{1,2}日))",
        r"((?:20\d{2}[/-]\d{1,2}[/-]\d{1,2})|(?:\d{1,2}月\d{1,2}日))\s*(?:締切|まで)",
    ]
    for pattern in deadline_patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            metadata["deadline"] = re.sub(r"\s+", " ", match.group(1)).strip()
            break
    return metadata


def build_later_queue_record(
    *,
    url: str,
    title: str = "",
    site_name: str = "",
    deadline: str = "",
    source_type: str = "manual_url",
    safety_memo: str = "",
    review_note: str = "",
) -> dict[str, str]:
    campaign = _campaign_from_url(url)
    metadata = _parse_page_metadata(url)
    normalized_url = normalize_url(campaign.get("resolved_entry_url", "") or url)
    duplicate_key = build_duplicate_key(normalized_url)
    target_host = urlsplit(_ensure_scheme(url)).hostname or ""
    inferred_title = title or campaign.get("campaign_name", "") or metadata["title"] or "unknown"
    inferred_site = site_name or campaign.get("provider", "") or campaign.get("source", "") or metadata["site_name"] or "unknown"
    inferred_deadline = deadline or campaign.get("deadline", "") or metadata["deadline"] or "unknown"
    safety_parts = [
        safety_memo.strip(),
        "当選・応募条件・締切日は自動抽出が不完全な場合があります",
    ]
    status = "queued"
    if target_host and not _is_public_host(target_host):
        safety_parts.insert(0, "要確認: private ローカル/非公開URLは自動取得しません")
        status = "blocked"
    if status != "blocked" and (inferred_title == "unknown" or inferred_site == "unknown" or inferred_deadline == "unknown"):
        safety_parts.insert(0, "要確認: unknown 項目があります")
        status = "needs_review"
    elif status != "blocked":
        status = "queued"
    if status == "queued" and (inferred_title == "unknown" or inferred_site == "unknown" or inferred_deadline == "unknown"):
        status = "needs_review"
    record = {
        "id": f"later-{hashlib.sha1(duplicate_key.encode('utf-8')).hexdigest()[:12]}" if duplicate_key else f"later-{hashlib.sha1(normalized_url.encode('utf-8')).hexdigest()[:12]}",
        "title": inferred_title,
        "site_name": inferred_site,
        "url": url,
        "normalized_url": normalized_url,
        "duplicate_key": duplicate_key,
        "deadline": inferred_deadline,
        "status": status,
        "source_type": source_type if source_type in LATER_QUEUE_SOURCE_TYPES else "manual_url",
        "safety_memo": " / ".join(part for part in safety_parts if part),
        "review_note": review_note.strip(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    return record


def _sanitize_record(record: Mapping[str, object]) -> dict[str, str]:
    payload = sanitize_log_payload(dict(record))
    cleaned: dict[str, str] = {}
    for key in LATER_QUEUE_HEADERS:
        value = payload.get(key, "")
        cleaned[key] = redact_personal_info(str(value or "")).strip()
    cleaned["status"] = cleaned.get("status", "").casefold() or "queued"
    if cleaned["status"] not in LATER_QUEUE_STATUSES:
        cleaned["status"] = "needs_review"
    cleaned["source_type"] = cleaned.get("source_type", "").casefold() or "manual_url"
    if cleaned["source_type"] not in LATER_QUEUE_SOURCE_TYPES:
        cleaned["source_type"] = "manual_url"
    cleaned["title"] = cleaned.get("title", "") or "unknown"
    cleaned["site_name"] = cleaned.get("site_name", "") or "unknown"
    cleaned["deadline"] = cleaned.get("deadline", "") or "unknown"
    cleaned["url"] = cleaned.get("url", "") or ""
    cleaned["normalized_url"] = cleaned.get("normalized_url", "") or normalize_url(cleaned["url"])
    cleaned["duplicate_key"] = cleaned.get("duplicate_key", "") or build_duplicate_key(cleaned["normalized_url"])
    cleaned["review_note"] = cleaned.get("review_note", "") or ""
    cleaned["safety_memo"] = cleaned.get("safety_memo", "") or ""
    cleaned["created_at"] = cleaned.get("created_at", "") or _now()
    cleaned["updated_at"] = _now()
    return cleaned


def ensure_later_queue_store(path: Path | None = None) -> None:
    path = _resolve_path(path, LATER_QUEUE_JSONL)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def load_later_queue(path: Path | None = None) -> list[dict[str, str]]:
    path = _resolve_path(path, LATER_QUEUE_JSONL)
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows.append({key: str(row.get(key, "")) for key in LATER_QUEUE_HEADERS})
    return rows


def save_later_queue(rows: Iterable[Mapping[str, object]], path: Path | None = None) -> None:
    path = _resolve_path(path, LATER_QUEUE_JSONL)
    ensure_later_queue_store(path)
    records = [_sanitize_record(row) for row in rows]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _find_later_row(rows: list[dict[str, str]], item_id: str) -> tuple[int, dict[str, str]] | tuple[None, None]:
    target = _collapse(item_id)
    if not target:
        return None, None
    for index, row in enumerate(rows):
        if row.get("id", "") == target:
            return index, row
        if row.get("duplicate_key", "") == target:
            return index, row
        if row.get("normalized_url", "") == normalize_url(target):
            return index, row
    return None, None


def list_later_queue(rows: Iterable[Mapping[str, object]] | None = None, path: Path | None = None) -> list[dict[str, str]]:
    source_rows = list(rows) if rows is not None else load_later_queue(path)
    return [dict(row, status=_effective_status(row)) for row in source_rows]


def upsert_later_queue(record: Mapping[str, object], path: Path | None = None) -> tuple[dict[str, str], bool]:
    path = _resolve_path(path, LATER_QUEUE_JSONL)
    rows = load_later_queue(path)
    row = _sanitize_record(record)
    duplicate_key = row.get("duplicate_key", "")
    updated = False
    for index, existing in enumerate(rows):
        if row.get("id", "") and existing.get("id", "") == row["id"]:
            rows[index] = {**existing, **row, "created_at": existing.get("created_at", row["created_at"]), "updated_at": _now()}
            row = rows[index]
            updated = True
            break
        if duplicate_key and existing.get("duplicate_key", "") == duplicate_key:
            rows[index] = {**existing, **row, "created_at": existing.get("created_at", row["created_at"]), "updated_at": _now()}
            row = rows[index]
            updated = True
            break
    if not updated:
        rows.append(row)
    save_later_queue(rows, path)
    return row, not updated


def add_later_queue(url: str, *, path: Path | None = None) -> tuple[dict[str, str], bool, str]:
    path = _resolve_path(path, LATER_QUEUE_JSONL)
    candidate = build_later_queue_record(url=url)
    rows = load_later_queue(path)
    for existing in rows:
        if existing.get("duplicate_key", "") and existing.get("duplicate_key", "") == candidate["duplicate_key"]:
            return existing, False, "duplicate"
    saved, created = upsert_later_queue(candidate, path)
    return saved, created, "created"


def update_later_queue_status(
    item_id: str,
    *,
    status: str,
    review_note: str = "",
    safety_memo: str = "",
    path: Path | None = None,
) -> dict[str, str] | None:
    path = _resolve_path(path, LATER_QUEUE_JSONL)
    rows = load_later_queue(path)
    index, row = _find_later_row(rows, item_id)
    if row is None or index is None:
        return None
    row = dict(row)
    row["status"] = status
    if review_note:
        row["review_note"] = review_note
    if safety_memo:
        row["safety_memo"] = safety_memo
    row["updated_at"] = _now()
    rows[index] = row
    save_later_queue(rows, path)
    return row


def remove_later_queue_item(item_id: str, path: Path | None = None) -> dict[str, str] | None:
    path = _resolve_path(path, LATER_QUEUE_JSONL)
    rows = load_later_queue(path)
    index, row = _find_later_row(rows, item_id)
    if row is None or index is None:
        return None
    removed = rows.pop(index)
    save_later_queue(rows, path)
    return removed


def search_later_queue(keyword: str, path: Path | None = None) -> list[dict[str, str]]:
    rows = list_later_queue(path=path)
    query = keyword.casefold().strip()
    if not query:
        return rows
    filtered: list[dict[str, str]] = []
    for row in rows:
        haystack = " ".join(
            row.get(field, "")
            for field in ("id", "title", "site_name", "url", "normalized_url", "deadline", "status", "source_type", "safety_memo", "review_note")
        ).casefold()
        if query in haystack:
            filtered.append(row)
    return filtered


def summarize_later_queue(rows: Iterable[Mapping[str, object]] | None = None, path: Path | None = None) -> dict[str, int]:
    source_rows = list(rows) if rows is not None else load_later_queue(path)
    summary = Counter(
        {
            "total": 0,
            "queued": 0,
            "needs_review": 0,
            "reviewing": 0,
            "ready_for_fill": 0,
            "applied_manual": 0,
            "skipped": 0,
            "expired": 0,
            "blocked": 0,
            "deadline_soon": 0,
        }
    )
    for row in source_rows:
        summary["total"] += 1
        status = _effective_status(row)
        summary[status] += 1
        deadline_bucket, _ = _deadline_bucket(str(row.get("deadline", "")))
        if 0 <= deadline_bucket <= 7:
            summary["deadline_soon"] += 1
    return dict(summary)


def bridge_later_queue_to_campaign(url: str) -> dict[str, str]:
    return _campaign_from_url(url)


def later_queue_to_entry_history(row: Mapping[str, object]) -> dict[str, str]:
    return mark_entry_applied(
        str(row.get("id", "")),
        url=str(row.get("url", "")),
        title=str(row.get("title", "")),
        source_site=str(row.get("site_name", "")),
        prize="unknown",
        deadline=str(row.get("deadline", "")),
        newsletter_status="unknown",
        memo=str(row.get("review_note", "")),
    )
