from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping

from .campaign_classifier import classify_campaign
from .entry_logger import load_entries
from .models import ClassificationResult
from .paths import CAMPAIGNS_CSV, ENTRIES_CSV
from .safety_checker import evaluate_safety
from .storage import read_csv_rows


def _parse_relative_deadline(text: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    text = text or ""
    if "本日締切" in text:
        return now
    if "明日締切" in text:
        return now + timedelta(days=1)
    if "明後日締切" in text:
        return now + timedelta(days=2)
    return None


def generate_report(campaigns_path: str | Path | None = None, entries_path: str | Path | None = None) -> str:
    campaigns = read_csv_rows(Path(campaigns_path) if campaigns_path else CAMPAIGNS_CSV)
    entries = load_entries(Path(entries_path) if entries_path else ENTRIES_CSV)
    statuses = Counter(row.get("status", "") for row in campaigns)
    entry_statuses = Counter(row.get("status", "") for row in entries)
    categories = Counter(row.get("category", "") for row in campaigns if row.get("category"))
    blocked = Counter(
        row.get("status", "")
        for row in campaigns
        if row.get("status", "").startswith(("BLOCKED", "CAPTCHA", "LOGIN", "X_", "INSTAGRAM_", "LINE_", "FACEBOOK_", "AGE_", "PURCHASE_", "RECEIPT_", "BARCODE_"))
        or row.get("status", "") == "DUPLICATE_ENTRY"
    )
    due_soon = 0
    for row in campaigns:
        deadline = row.get("deadline", "")
        parsed = _parse_relative_deadline(deadline)
        if parsed and parsed <= datetime.now() + timedelta(days=3):
            due_soon += 1
    lines = [
        "# Kensho assistant report",
        f"- collected: {len(campaigns)}",
        f"- entries: {len(entries)}",
        f"- fillable: {statuses.get('SAFE_TO_FILL', 0)}",
        f"- blocked: {sum(v for k, v in statuses.items() if k.startswith(('BLOCKED', 'CAPTCHA', 'LOGIN', 'X_', 'INSTAGRAM_', 'LINE_', 'FACEBOOK_', 'AGE_', 'PURCHASE_', 'RECEIPT_', 'BARCODE_', 'AUTO_ENTRY_FORBIDDEN')) or k == 'DUPLICATE_ENTRY')}",
        f"- submitted: {entry_statuses.get('SUBMITTED', 0)}",
        f"- hold: {entry_statuses.get('HOLD', 0)}",
        f"- due soon: {due_soon}",
        "",
        "## category counts",
    ]
    for category, count in categories.most_common(10):
        lines.append(f"- {category}: {count}")
    lines.append("")
    lines.append("## blocked reasons")
    for status, count in blocked.most_common(10):
        lines.append(f"- {status}: {count}")
    lines.append("")
    lines.append("## need review")
    for row in campaigns:
        if row.get("status") in {"NEEDS_HUMAN_REVIEW", "SAFE_TO_REVIEW_ONLY", "RULES_UNCLEAR"}:
            lines.append(f"- {row.get('campaign_name', '')} | {row.get('status', '')} | {row.get('deadline', '')}")
    return "\n".join(lines).strip() + "\n"


def status_summary(campaigns_path: str | Path | None = None, entries_path: str | Path | None = None) -> str:
    campaigns = read_csv_rows(Path(campaigns_path) if campaigns_path else CAMPAIGNS_CSV)
    entries = load_entries(Path(entries_path) if entries_path else ENTRIES_CSV)
    status_counts = Counter(row.get("status", "") for row in campaigns)
    entry_counts = Counter(row.get("status", "") for row in entries)
    lines = [
        f"collected: {len(campaigns)}",
        f"entries: {len(entries)}",
        f"fillable: {status_counts.get('SAFE_TO_FILL', 0)}",
        f"blocked: {sum(v for k, v in status_counts.items() if k.startswith(('BLOCKED', 'CAPTCHA', 'LOGIN', 'X_', 'INSTAGRAM_', 'LINE_', 'FACEBOOK_', 'AGE_', 'PURCHASE_', 'RECEIPT_', 'BARCODE_', 'AUTO_ENTRY_FORBIDDEN')) or k == 'DUPLICATE_ENTRY')}",
        f"submitted: {entry_counts.get('SUBMITTED', 0)}",
        f"hold: {entry_counts.get('HOLD', 0)}",
    ]
    return "\n".join(lines) + "\n"
