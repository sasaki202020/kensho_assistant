from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..app.paths import AUTO_SCAN_JSON, APPLY_QUEUE_CSV, CAMPAIGNS_CSV, FORM_INSPECTIONS_JSONL, RELEASE_REPORT_JSON, RESEARCH_REPORT_JSON, RUN_LOG, PROFILE_JSON
from ..app.privacy_guard import mask_email, mask_name, mask_phone
from ..app.profile_manager import PROFILE_ENC, load_profile
from ..app.research.hermes_x_search import (
    available_x_campaign_days,
    latest_x_campaign_day,
    load_x_campaign_candidates,
    load_x_campaign_queue_export,
    load_x_campaign_quality_report,
    load_x_campaign_run,
)
from ..app.apply_queue import (
    get_current_queue_item as _get_current_queue_item,
    get_next_queue_item as _get_next_queue_item,
    load_apply_queue as _load_apply_queue,
    mark_hold as _mark_hold,
    mark_manual_submitted as _mark_manual_submitted,
    approve_queue_item as _approve_queue_item,
    mark_prepare_cancelled as _mark_prepare_cancelled,
    mark_prepared as _mark_prepared,
    mark_skipped as _mark_skipped,
    approved_queue_rows as _approved_queue_rows,
    approved_queue_pending_rows as _approved_queue_pending_rows,
    set_age_fill_user_approved as _set_age_fill_user_approved,
    summarize_apply_queue as _summarize_apply_queue,
    update_apply_queue_status as _update_apply_queue_status,
)
from ..app.storage import ensure_csv, read_csv_rows, write_csv_rows
from ..app.models import CAMPAIGN_HEADERS


SAFE_CLI_ACTIONS = {
    "collect": ["collect", "--limit", "20"],
    "analyze": ["analyze"],
    "resolve": ["resolve-urls", "--limit", "20"],
    "inspect": ["inspect-form", "--limit", "5"],
    "review": ["review", "--limit", "5"],
    "release": ["release-report"],
    "research": ["research", "--limit", "30"],
    "research_report": ["research-report"],
    "auto_scan": ["auto-scan", "--limit", "30"],
    "build_queue": ["build-queue", "--limit", "30"],
    "profile": ["profile", "check"],
    "doctor": ["doctor"],
}


EXCLUDED_DISTRIBUTION_NAMES = {".env", "profile.json", "profile.enc"}
EXCLUDED_DISTRIBUTION_DIRS = {"logs", "screenshots", "data", "browser_profile"}
SELECTED_CAMPAIGNS_HEADERS = [
    "campaign_id",
    "campaign_name",
    "selected_by_user",
    "selected_at",
    "selection_reason",
    "excluded_by_user",
    "excluded_reason",
]

EMAIL_CAMPAIGN_HEADERS = CAMPAIGN_HEADERS


@dataclass
class AppSnapshot:
    release_report: dict[str, Any]
    campaigns: list[dict[str, str]]
    apply_queue: list[dict[str, str]]
    inspections: dict[str, dict[str, Any]]
    activity: list[str]
    profile_preview: dict[str, str]


def load_release_report(path: Path = RELEASE_REPORT_JSON) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_auto_scan_report(path: Path = AUTO_SCAN_JSON) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_research_report(path: Path = RESEARCH_REPORT_JSON) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_x_campaign_candidates_for_day(day: str | None = None) -> list[dict[str, Any]]:
    candidates = load_x_campaign_candidates(day if day else None)
    queue_rows = load_x_campaign_queue_export(day if day else None)
    by_id = {str(row.get("candidate_id", "")): row for row in queue_rows if str(row.get("candidate_id", ""))}
    by_post_url = {str(row.get("post_url", "")): row for row in queue_rows if str(row.get("post_url", ""))}
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        overlay = by_id.get(str(candidate.get("candidate_id", ""))) or by_post_url.get(str(candidate.get("post_url", "")))
        if overlay:
            candidate = {**candidate, **{key: value for key, value in overlay.items() if key in {"status", "queue_status", "queue_reason", "selected_at", "prepared_at", "notes"}}}
        merged.append(candidate)
    return merged


def load_x_campaign_queue_for_day(day: str | None = None) -> list[dict[str, Any]]:
    return load_x_campaign_queue_export(day if day else None)


def load_x_campaign_run_for_day(day: str | None = None) -> dict[str, Any]:
    return load_x_campaign_run(day if day else None)


def load_x_campaign_report_for_day(day: str | None = None) -> dict[str, Any]:
    return load_x_campaign_quality_report(day if day else None)


def load_latest_x_campaign_day() -> str:
    return latest_x_campaign_day()


def load_x_campaign_days() -> list[str]:
    return available_x_campaign_days()


def load_apply_queue(path: Path = APPLY_QUEUE_CSV) -> list[dict[str, str]]:
    return _load_apply_queue(path)


def load_campaigns(path: Path = CAMPAIGNS_CSV) -> list[dict[str, str]]:
    return read_csv_rows(path)


def get_campaign_by_id(campaign_id: str, path: Path = CAMPAIGNS_CSV) -> dict[str, str]:
    for row in load_campaigns(path):
        if row.get("campaign_id") == campaign_id:
            return row
    return {}


def load_form_inspections(path: Path = FORM_INSPECTIONS_JSONL) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            latest[str(row.get("campaign_id", ""))] = row
    return latest


def load_recent_activity(path: Path = RUN_LOG, limit: int = 5) -> list[str]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    safe: list[str] = []
    for line in lines[-limit:]:
        try:
            row = json.loads(line)
            safe.append(str(row.get("event", "activity")))
        except json.JSONDecodeError:
            continue
    return safe


def load_masked_profile_preview() -> dict[str, str]:
    try:
        profile = load_profile()
    except Exception:
        profile = {}
    return {
        "name": mask_name(profile.get("last_name", ""), profile.get("first_name", "")) or "未設定",
        "postal_code": f"{profile.get('postal_code', '')[:3]}-****" if profile.get("postal_code") else "未設定",
        "email": mask_email(profile.get("email", "")) or "未設定",
        "phone": mask_phone(profile.get("phone", "")) or "未設定",
    }


def distribution_path_is_excluded(path: str | Path) -> bool:
    parts = Path(path).parts
    if Path(path).name in EXCLUDED_DISTRIBUTION_NAMES:
        return True
    return any(part in EXCLUDED_DISTRIBUTION_DIRS for part in parts)


def load_app_snapshot() -> AppSnapshot:
    return AppSnapshot(
        release_report=load_release_report(),
        campaigns=load_campaigns(),
        apply_queue=load_apply_queue(),
        inspections=load_form_inspections(),
        activity=load_recent_activity(),
        profile_preview=load_masked_profile_preview(),
    )


def summarize_campaigns(path: Path = CAMPAIGNS_CSV) -> dict[str, int]:
    rows = load_campaigns(path)
    summary = {
        "count": len(rows),
        "review_only": 0,
        "ready_for_fill": 0,
        "landing_page": 0,
        "search_only": 0,
        "low_confidence": 0,
        "resolved": 0,
        "blocked": 0,
        "submitted": 0,
    }
    for row in rows:
        status = row.get("form_readiness_status", "") or row.get("resolve_status", "") or row.get("status", "")
        if status == "REVIEW_ONLY":
            summary["review_only"] += 1
        elif status == "READY_FOR_FILL":
            summary["ready_for_fill"] += 1
        elif status == "LANDING_PAGE":
            summary["landing_page"] += 1
        elif status == "SEARCH_ONLY":
            summary["search_only"] += 1
        elif status == "LOW_CONFIDENCE":
            summary["low_confidence"] += 1
        elif status == "RESOLVED":
            summary["resolved"] += 1
        elif status.startswith("BLOCKED"):
            summary["blocked"] += 1
        if row.get("status") == "SUBMITTED":
            summary["submitted"] += 1
    return summary


def summarize_apply_queue(rows_or_path: Path | list[dict[str, str]] | None = None) -> dict[str, int]:
    if isinstance(rows_or_path, list):
        return _summarize_apply_queue(rows_or_path)
    path = rows_or_path or APPLY_QUEUE_CSV
    return _summarize_apply_queue(load_apply_queue(path))


def _selection_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_csv_rows(path)


def mark_selected(campaign_id: str, reason: str = "", path: Path = CAMPAIGNS_CSV) -> None:
    rows = load_campaigns(path)
    updated: list[dict[str, str]] = []
    for row in rows:
        if row.get("campaign_id") == campaign_id:
            row = dict(row)
            row["selected_by_user"] = "true"
            row["selected_at"] = row.get("selected_at", "") or row.get("collected_at", "")
            row["selection_reason"] = reason
        updated.append(row)
    if updated:
        ensure_csv(path, CAMPAIGN_HEADERS)
        write_csv_rows(path, updated, CAMPAIGN_HEADERS)


def mark_excluded(campaign_id: str, reason: str = "", path: Path = CAMPAIGNS_CSV) -> None:
    rows = load_campaigns(path)
    updated: list[dict[str, str]] = []
    for row in rows:
        if row.get("campaign_id") == campaign_id:
            row = dict(row)
            row["excluded_by_user"] = "true"
            row["excluded_reason"] = reason
        updated.append(row)
    if updated:
        ensure_csv(path, CAMPAIGN_HEADERS)
        write_csv_rows(path, updated, CAMPAIGN_HEADERS)


def update_apply_queue_status(queue_id: str, queue_status: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return _update_apply_queue_status(queue_id, queue_status, path)


def get_current_queue_item(rows: list[dict[str, str]], index: int) -> dict[str, str]:
    return _get_current_queue_item(rows, index)


def get_next_queue_item(rows: list[dict[str, str]], current_id: str) -> dict[str, str]:
    return _get_next_queue_item(rows, current_id)


def mark_prepared(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return _mark_prepared(queue_id, path)


def approve_queue_item(
    queue_id: str,
    note: str = "",
    age_fill_user_approved: bool = False,
    path: Path = APPLY_QUEUE_CSV,
) -> bool:
    return _approve_queue_item(queue_id, note=note, age_fill_user_approved=age_fill_user_approved, path=path)


def mark_prepare_cancelled(queue_id: str, previous_queue_status: str = "", path: Path = APPLY_QUEUE_CSV) -> bool:
    return _mark_prepare_cancelled(queue_id, previous_queue_status, path)


def mark_manual_submitted(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return _mark_manual_submitted(queue_id, path)


def mark_skipped(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return _mark_skipped(queue_id, path)


def mark_hold(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return _mark_hold(queue_id, path)


def set_age_fill_user_approved(queue_id: str, approved: bool = True, path: Path = APPLY_QUEUE_CSV) -> bool:
    return _set_age_fill_user_approved(queue_id, approved, path)


def approved_queue_rows(rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    return _approved_queue_rows(rows)


def approved_queue_pending_rows(rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    return _approved_queue_pending_rows(rows)


def profile_storage_state() -> dict[str, str]:
    return {
        "profile_enc": "保存済み" if PROFILE_ENC.exists() else "未検出",
        "profile_json": "検出" if PROFILE_JSON.exists() else "未検出",
    }


def register_email_campaign(mail_item: dict[str, object], path: Path = CAMPAIGNS_CSV) -> bool:
    mail_id = str(mail_item.get("mail_id", ""))
    if not mail_id:
        return False
    subject = str(mail_item.get("subject", ""))
    sender = str(mail_item.get("sender", ""))
    campaign_url = str(mail_item.get("campaign_url", ""))
    rows = load_campaigns(path)
    for row in rows:
        if row.get("campaign_id") == mail_id:
            row = dict(row)
            row.update(
                {
                    "source": "email",
                    "campaign_name": subject,
                    "prize": "",
                    "winner_count": "",
                    "provider": sender,
                    "deadline": str(mail_item.get("deadline_text", "")),
                    "knshow_url": "",
                    "entry_url": campaign_url,
                    "resolved_entry_url": campaign_url,
                    "resolved_domain": "",
                    "resolve_status": "RESOLVED" if campaign_url else "",
                    "resolve_reason": "メール本文から抽出",
                    "resolved_at": str(mail_item.get("updated_at", "")),
                    "form_readiness_status": "REVIEW_ONLY" if campaign_url else "",
                    "form_readiness_score": "0.5" if campaign_url else "",
                    "form_readiness_reason": "メール懸賞から登録",
                    "inspected_at": "",
                    "description": str(mail_item.get("body_excerpt", "")),
                    "category": "メール懸賞",
                    "entry_type_raw": "メール懸賞",
                    "collected_at": str(mail_item.get("received_at", "")),
                    "status": "MAIL_IMPORTED",
                    "notes": str(mail_item.get("body_excerpt", "")),
                    "selected_by_user": "true",
                    "selected_at": str(mail_item.get("updated_at", "")),
                    "selection_reason": "メール懸賞から追加",
                    "excluded_by_user": "false",
                    "excluded_reason": "",
                }
            )
            updated = [row if existing.get("campaign_id") == mail_id else existing for existing in rows]
            ensure_csv(path, CAMPAIGN_HEADERS)
            write_csv_rows(path, updated, CAMPAIGN_HEADERS)
            return True
    for row in rows:
        if campaign_url and row.get("entry_url") == campaign_url:
            return False
        if subject and sender and row.get("campaign_name") == subject and row.get("provider") == sender:
            return False
    updated: list[dict[str, str]] = []
    updated.append(
        {
            "campaign_id": mail_id,
            "source": "email",
            "campaign_name": subject,
            "prize": "",
            "winner_count": "",
            "provider": sender,
            "deadline": str(mail_item.get("deadline_text", "")),
            "knshow_url": "",
            "entry_url": campaign_url,
            "resolved_entry_url": campaign_url,
            "resolved_domain": "",
            "resolve_status": "RESOLVED" if campaign_url else "",
            "resolve_reason": "メール本文から抽出",
            "resolved_at": str(mail_item.get("updated_at", "")),
            "form_readiness_status": "REVIEW_ONLY" if campaign_url else "",
            "form_readiness_score": "0.5" if campaign_url else "",
            "form_readiness_reason": "メール懸賞から登録",
            "inspected_at": "",
            "description": str(mail_item.get("body_excerpt", "")),
            "category": "メール懸賞",
            "entry_type_raw": "メール懸賞",
            "collected_at": str(mail_item.get("received_at", "")),
            "status": "MAIL_IMPORTED",
            "notes": str(mail_item.get("body_excerpt", "")),
            "selected_by_user": "true",
            "selected_at": str(mail_item.get("updated_at", "")),
            "selection_reason": "メール懸賞から追加",
            "excluded_by_user": "false",
            "excluded_reason": "",
        }
    )
    ensure_csv(path, CAMPAIGN_HEADERS)
    write_csv_rows(path, updated, CAMPAIGN_HEADERS)
    return True
