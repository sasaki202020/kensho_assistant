from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .entry_logger import load_entries
from .entry_history import build_duplicate_key
from .paths import APPLY_QUEUE_CSV, APPLY_QUEUE_JSON, APPLY_QUEUE_MD, CAMPAIGNS_CSV, FORM_INSPECTIONS_JSONL
from .release_report import latest_inspections
from .storage import ensure_csv, read_csv_rows, write_csv_rows


QUEUE_HEADERS = [
    "queue_id",
    "campaign_id",
    "campaign_name",
    "prize",
    "provider",
    "deadline",
    "resolved_entry_url",
    "readiness_status",
    "readiness_score",
    "risk_level",
    "opportunity_score",
    "opportunity_rank",
    "opportunity_reason",
    "risk_reasons",
    "recommendation_reason",
    "next_action",
    "quiz_required",
    "quiz_summary",
    "quiz_manual_required",
    "manual_review_required_fields",
    "skip_reason_summary",
    "queue_status",
    "last_action",
    "approved_by_user",
    "approved_at",
    "approved_note",
    "age_fill_user_approved",
    "terms_user_acknowledged",
    "quiz_user_acknowledged",
    "approved_session_order",
    "auto_submit_allowed",
    "submission_method",
    "manual_submitted_at",
    "prepared_at",
    "dry_run_status",
    "dry_run_at",
    "dry_run_screenshot_path",
    "dry_run_check_path",
    "dry_run_analysis_path",
    "created_at",
    "updated_at",
]


def load_apply_queue(path: Path = APPLY_QUEUE_CSV) -> list[dict[str, str]]:
    return read_csv_rows(path)


def _deadline_bucket(text: str) -> tuple[int, str]:
    value = (text or "").strip()
    if not value:
        return 3, "期限不明"
    if any(keyword in value for keyword in ("期限切れ", "締切終了", "終了")):
        return 4, "期限切れ"
    if any(keyword in value for keyword in ("今日まで", "本日まで", "本日中", "本日締切", "当日", "今日")):
        return 0, "今日まで"
    if any(keyword in value for keyword in ("明日まで", "明日中", "明日締切")):
        return 1, "明日まで"
    if any(keyword in value for keyword in ("今週まで", "今週中", "週末まで")):
        return 2, "今週まで"
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(value, fmt).date()
            delta = (dt - date.today()).days
            if delta < 0:
                return 4, "期限切れ"
            if delta == 0:
                return 0, "今日まで"
            if delta == 1:
                return 1, "明日まで"
            if delta <= 7:
                return 2, "今週まで"
            return 3, "期限不明"
        except ValueError:
            continue
    return 3, "期限不明"


def _queue_priority(row: dict[str, str]) -> tuple[int, int, int, str]:
    deadline_bucket, _ = _deadline_bucket(row.get("deadline", ""))
    approved_priority = 0 if row.get("approved_by_user", "") == "true" or row.get("queue_status", "") in {"APPROVED", "PREPARED"} else 1
    score_text = row.get("opportunity_score", row.get("readiness_score", "0"))
    try:
        score = int(float(score_text))
    except ValueError:
        score = 0
    readiness_priority = 0 if row.get("readiness_status") == "READY_FOR_FILL" else 1
    return approved_priority, -score, deadline_bucket, readiness_priority, row.get("campaign_name", "")


def _manual_review_fields(inspection: dict[str, object]) -> str:
    value = inspection.get("manual_review_required_fields", "")
    if isinstance(value, list):
        fields = [str(item) for item in value if str(item).strip()]
    else:
        fields = [str(value)] if str(value or "").strip() else []
    if inspection.get("quiz_required") and "quiz" not in fields:
        fields.append("quiz")
    return ", ".join(fields)


def _skip_reason_summary(inspection: dict[str, object], row: dict[str, str]) -> str:
    for key in ("readiness_reason", "resolve_reason", "notes"):
        value = str(inspection.get(key, "") or row.get(key, ""))
        if value.strip():
            return value.strip().split("。", 1)[0][:80]
    return ""


def _is_manual_submission_recorded(row: dict[str, str]) -> bool:
    return bool(
        row.get("manual_submitted_at", "").strip()
        or row.get("submission_method", "").strip().upper() == "MANUAL"
        or row.get("queue_status", "") == "MANUALLY_SUBMITTED"
    )


def build_apply_queue(
    campaigns: Iterable[dict[str, str]] | None = None,
    inspections: dict[str, dict[str, object]] | None = None,
    entries: Iterable[dict[str, str]] | None = None,
    existing_queue: Iterable[dict[str, str]] | None = None,
    limit: int | None = None,
) -> list[dict[str, str]]:
    from .research_engine import calculate_opportunity_score

    campaign_rows = list(campaigns) if campaigns is not None else read_csv_rows(CAMPAIGNS_CSV)
    inspection_rows = inspections if inspections is not None else latest_inspections(FORM_INSPECTIONS_JSONL)
    entry_rows = list(entries) if entries is not None else load_entries()
    queue_rows = list(existing_queue) if existing_queue is not None else load_apply_queue()
    existing_by_id = {row.get("campaign_id", ""): row for row in queue_rows}

    blocked_entry_ids = {
        row.get("campaign_id", "")
        for row in entry_rows
        if row.get("status", "").upper() in {"SUBMITTED", "MANUALLY_SUBMITTED", "APPLIED", "RESULT_CHECKED", "PENDING_RESULT"}
    }
    blocked_duplicate_keys = {
        str(row.get("duplicate_key", "")).strip()
        for row in entry_rows
        if str(row.get("duplicate_key", "")).strip()
    }

    rows: list[dict[str, str]] = []
    seen_campaign_ids: set[str] = set()
    for row in campaign_rows:
        campaign_id = row.get("campaign_id", "")
        if not campaign_id or campaign_id in seen_campaign_ids:
            continue
        seen_campaign_ids.add(campaign_id)
        readiness_status = row.get("form_readiness_status", "")
        if readiness_status not in {"REVIEW_ONLY", "READY_FOR_FILL"}:
            continue
        if row.get("excluded_by_user") == "true":
            continue
        if row.get("status", "").startswith("BLOCKED"):
            continue
        if row.get("resolve_status", "").startswith("BLOCKED"):
            continue
        if campaign_id in blocked_entry_ids:
            continue
        duplicate_key = build_duplicate_key(
            {
                "campaign_id": campaign_id,
                "title": row.get("campaign_name", ""),
                "url": row.get("resolved_entry_url", "") or row.get("entry_url", "") or row.get("knshow_url", ""),
                "prize": row.get("prize", ""),
                "deadline": row.get("deadline", ""),
            }
        )
        if duplicate_key and duplicate_key in blocked_duplicate_keys:
            continue
        inspection = inspection_rows.get(campaign_id, {})
        existing = existing_by_id.get(campaign_id, {})
        queue_status = existing.get("queue_status", "") or "QUEUED"
        if queue_status == "MANUALLY_SUBMITTED":
            continue
        research_metrics = calculate_opportunity_score(row, inspection)
        created_at = existing.get("created_at", "") or row.get("collected_at", "") or datetime.now().astimezone().isoformat(timespec="seconds")
        updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        rows.append(
            {
                "queue_id": campaign_id,
                "campaign_id": campaign_id,
                "campaign_name": row.get("campaign_name", ""),
                "prize": row.get("prize", ""),
                "provider": row.get("provider", ""),
                "deadline": row.get("deadline", ""),
                "resolved_entry_url": row.get("resolved_entry_url", ""),
                "readiness_status": readiness_status,
                "readiness_score": row.get("form_readiness_score", ""),
                "risk_level": str(research_metrics["risk_level"]),
                "opportunity_score": str(research_metrics["opportunity_score"]),
                "opportunity_rank": existing.get("opportunity_rank", ""),
                "opportunity_reason": str(research_metrics["opportunity_reason"]),
                "risk_reasons": str(research_metrics["risk_reasons"]),
                "recommendation_reason": str(research_metrics["recommendation_reason"]),
                "next_action": str(research_metrics["next_action"]),
                "quiz_required": str(bool(inspection.get("quiz_required"))).lower(),
                "quiz_summary": str(inspection.get("quiz_summary", "")),
                "quiz_manual_required": str(bool(inspection.get("quiz_required"))).lower(),
                "manual_review_required_fields": _manual_review_fields(inspection),
                "skip_reason_summary": _skip_reason_summary(inspection, row),
                "queue_status": queue_status,
                "last_action": existing.get("last_action", ""),
                "approved_by_user": existing.get("approved_by_user", "false"),
                "approved_at": existing.get("approved_at", ""),
                "approved_note": existing.get("approved_note", ""),
                "age_fill_user_approved": existing.get("age_fill_user_approved", "false"),
                "terms_user_acknowledged": existing.get("terms_user_acknowledged", "false"),
                "quiz_user_acknowledged": existing.get("quiz_user_acknowledged", "false"),
                "approved_session_order": existing.get("approved_session_order", ""),
                "auto_submit_allowed": "false",
                "submission_method": existing.get("submission_method", ""),
                "manual_submitted_at": existing.get("manual_submitted_at", ""),
                "prepared_at": existing.get("prepared_at", ""),
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

    rows.sort(key=_queue_priority)
    for index, row in enumerate(rows, start=1):
        row["opportunity_rank"] = str(index)
    if limit is not None:
        rows = rows[:limit]
    return rows


def summarize_apply_queue(rows: Iterable[dict[str, str]] | None = None) -> dict[str, int]:
    queue_rows = list(rows) if rows is not None else load_apply_queue()
    summary = Counter(row.get("queue_status", "QUEUED") or "QUEUED" for row in queue_rows)
    summary["MANUALLY_SUBMITTED"] = sum(1 for row in queue_rows if _is_manual_submission_recorded(row))
    summary["total"] = len(queue_rows)
    summary["today"] = sum(1 for row in queue_rows if _deadline_bucket(row.get("deadline", ""))[0] == 0)
    summary["tomorrow"] = sum(1 for row in queue_rows if _deadline_bucket(row.get("deadline", ""))[0] == 1)
    summary["this_week"] = sum(1 for row in queue_rows if _deadline_bucket(row.get("deadline", ""))[0] == 2)
    summary["unknown"] = sum(1 for row in queue_rows if _deadline_bucket(row.get("deadline", ""))[0] == 3)
    summary["expired"] = sum(1 for row in queue_rows if _deadline_bucket(row.get("deadline", ""))[0] == 4)
    return dict(summary)


def render_apply_queue_report(report: dict[str, object]) -> str:
    lines = [
        "# Apply queue latest",
        f"- generated_at: {report['generated_at']}",
        f"- warning: {report['warning']}",
        f"- total: {report['total']}",
        f"- submitted_count_auto: {report['submitted_count_auto']}",
        f"- queued: {report['queued']}",
        f"- prepared: {report['prepared']}",
        f"- manually_submitted: {report['manually_submitted']}",
        f"- skipped: {report['skipped']}",
        f"- hold: {report['hold']}",
        f"- blocked: {report['blocked']}",
        f"- today: {report['today']}",
        f"- tomorrow: {report['tomorrow']}",
        f"- this_week: {report['this_week']}",
        f"- unknown: {report['unknown']}",
        f"- expired: {report['expired']}",
        "",
        "## 今日の応募候補",
    ]
    for row in report["candidates"]:
        lines.append(
            f"- {row['deadline'] or '期限不明'} / {row['campaign_name']} / {row['queue_status']} / {row['readiness_status']}"
        )
    lines.extend(["", "## 人間確認が必要な項目"])
    lines.extend(f"- {item}" for item in report["need_human_review"])
    lines.extend(["", "## 次のおすすめアクション"])
    lines.extend(f"- {item}" for item in report["next_actions"])
    if report["warning"] == "WARNING":
        lines.extend(["", "## WARNING", "- submitted_count が 0 ではありません"])
    return "\n".join(lines) + "\n"


def save_apply_queue(rows: list[dict[str, str]], path: Path = APPLY_QUEUE_CSV) -> Path:
    ensure_csv(path, QUEUE_HEADERS)
    write_csv_rows(path, rows, QUEUE_HEADERS)
    return path


def build_apply_queue_report(rows: list[dict[str, str]]) -> dict[str, object]:
    summary = summarize_apply_queue(rows)
    candidates = [
        {
            "queue_id": row.get("queue_id", ""),
            "campaign_name": row.get("campaign_name", ""),
            "deadline": row.get("deadline", ""),
            "queue_status": row.get("queue_status", ""),
            "readiness_status": row.get("readiness_status", ""),
        }
        for row in rows[:10]
    ]
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "warning": "WARNING" if summary.get("MANUALLY_SUBMITTED", 0) else "OK",
        "submitted_count_auto": 0,
        "total": summary.get("total", 0),
        "queued": summary.get("QUEUED", 0),
        "prepared": summary.get("PREPARED", 0),
        "manually_submitted": summary.get("MANUALLY_SUBMITTED", 0),
        "skipped": summary.get("SKIPPED", 0),
        "hold": summary.get("HOLD", 0),
        "blocked": summary.get("BLOCKED", 0),
        "today": summary.get("today", 0),
        "tomorrow": summary.get("tomorrow", 0),
        "this_week": summary.get("this_week", 0),
        "unknown": summary.get("unknown", 0),
        "expired": summary.get("expired", 0),
        "candidates": candidates,
        "need_human_review": [
            "応募送信は行っていない",
            "REVIEW_ONLY は人間確認が必要",
            "年齢・同意・メルマガ・任意項目は自動入力しない",
        ],
        "next_actions": [
            "応募準備を確認する",
            "要確認を開く",
            "応募ページを人間確認する",
        ],
    }
    return report


def save_apply_queue_report(report: dict[str, object]) -> tuple[Path, Path]:
    APPLY_QUEUE_MD.write_text(render_apply_queue_report(report), encoding="utf-8")
    APPLY_QUEUE_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return APPLY_QUEUE_MD, APPLY_QUEUE_JSON


def update_apply_queue_status(queue_id: str, queue_status: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return update_apply_queue_fields(queue_id, {"queue_status": queue_status, "last_action": queue_status}, path)


def update_apply_queue_fields(queue_id: str, updates: dict[str, str], path: Path = APPLY_QUEUE_CSV) -> bool:
    rows = load_apply_queue(path)
    updated = False
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for row in rows:
        if row.get("queue_id", "") == queue_id or row.get("campaign_id", "") == queue_id:
            for key, value in updates.items():
                row[key] = value
            row["updated_at"] = now
            if row.get("queue_status", "") == "MANUALLY_SUBMITTED":
                row["submission_method"] = "MANUAL"
                row["manual_submitted_at"] = row.get("manual_submitted_at", "") or now
            updated = True
    if updated:
        save_apply_queue(rows, path)
    return updated


def get_current_queue_item(rows: Iterable[dict[str, str]], index: int) -> dict[str, str]:
    queue_rows = list(rows)
    if not queue_rows:
        return {}
    index = max(0, min(index, len(queue_rows) - 1))
    return queue_rows[index]


def get_next_queue_item(rows: Iterable[dict[str, str]], current_id: str) -> dict[str, str]:
    queue_rows = list(rows)
    if not queue_rows:
        return {}
    eligible = [row for row in queue_rows if row.get("queue_status", "") not in {"MANUALLY_SUBMITTED", "SKIPPED", "BLOCKED"} and not _is_manual_submission_recorded(row)]
    if not eligible:
        return {}
    for index, row in enumerate(eligible):
        if row.get("campaign_id", "") == current_id or row.get("queue_id", "") == current_id:
            return eligible[min(index + 1, len(eligible) - 1)]
    return eligible[0]


def mark_prepared(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return update_apply_queue_fields(
        queue_id,
        {
            "queue_status": "PREPARED",
            "last_action": "PREPARED_WITH_CHROME",
            "next_action": "Chrome上で内容を確認し、送信した場合だけ『手動送信済みにする』を押してください。",
            "prepared_at": now,
        },
        path,
    )


def mark_prepare_cancelled(queue_id: str, previous_queue_status: str = "", path: Path = APPLY_QUEUE_CSV) -> bool:
    updates = {"last_action": "PREPARE_CANCELLED_BY_USER"}
    if previous_queue_status:
        updates["queue_status"] = previous_queue_status
    return update_apply_queue_fields(queue_id, updates, path)


def mark_dry_run_result(
    queue_id: str,
    status: str,
    screenshot_path: str = "",
    analysis_path: str = "",
    check_path: str = "",
    path: Path = APPLY_QUEUE_CSV,
) -> bool:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    next_action = {
        "DRY_RUN_COMPLETED": "送信せずdry_run完了。スクショと送信前チェックを確認してください。",
        "NEEDS_REVIEW": "人間確認が必要です。送信前チェックを確認してください。",
        "SKIPPED": "対象外または危険判定です。理由を確認してください。",
    }.get(status, "dry_run結果を確認してください。")
    return update_apply_queue_fields(
        queue_id,
        {
            "dry_run_status": status,
            "dry_run_at": now,
            "dry_run_screenshot_path": screenshot_path,
            "dry_run_analysis_path": analysis_path,
            "dry_run_check_path": check_path,
            "last_action": status,
            "next_action": next_action,
        },
        path,
    )


def _next_approved_session_order(rows: list[dict[str, str]]) -> str:
    orders: list[int] = []
    for row in rows:
        value = row.get("approved_session_order", "").strip()
        if not value:
            continue
        try:
            orders.append(int(value))
        except ValueError:
            continue
    return str(max(orders, default=0) + 1)


def approve_queue_item(
    queue_id: str,
    note: str = "",
    age_fill_user_approved: bool = False,
    path: Path = APPLY_QUEUE_CSV,
) -> bool:
    rows = load_apply_queue(path)
    if not any(row.get("queue_id", "") == queue_id or row.get("campaign_id", "") == queue_id for row in rows):
        campaign_rows = [row for row in read_csv_rows(CAMPAIGNS_CSV) if row.get("campaign_id", "") == queue_id]
        if campaign_rows:
            queue_rows = build_apply_queue(campaign_rows, latest_inspections(FORM_INSPECTIONS_JSONL), load_entries(), rows, limit=30)
            if queue_rows:
                rows = queue_rows + [row for row in rows if row.get("campaign_id", "") != queue_id and row.get("queue_id", "") != queue_id]
    matched = False
    next_order = _next_approved_session_order(rows)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for row in rows:
        if row.get("queue_id", "") == queue_id or row.get("campaign_id", "") == queue_id:
            row["queue_status"] = "APPROVED"
            row["last_action"] = "APPROVED_BY_USER"
            row["approved_by_user"] = "true"
            row["approved_at"] = now
            row["approved_note"] = note
            row["age_fill_user_approved"] = "true" if age_fill_user_approved else row.get("age_fill_user_approved", "false") or "false"
            row["terms_user_acknowledged"] = row.get("terms_user_acknowledged", "false") or "false"
            row["quiz_user_acknowledged"] = row.get("quiz_user_acknowledged", "false") or "false"
            row["approved_session_order"] = row.get("approved_session_order", "") or next_order
            row["auto_submit_allowed"] = "false"
            row["updated_at"] = now
            matched = True
    if matched:
        save_apply_queue(rows, path)
    return matched


def set_age_fill_user_approved(queue_id: str, approved: bool = True, path: Path = APPLY_QUEUE_CSV) -> bool:
    return update_apply_queue_fields(
        queue_id,
        {"age_fill_user_approved": "true" if approved else "false"},
        path,
    )


def approved_queue_rows(rows: Iterable[dict[str, str]] | None = None) -> list[dict[str, str]]:
    queue_rows = list(rows) if rows is not None else load_apply_queue()
    return [
        row
        for row in queue_rows
        if row.get("queue_status", "") in {"APPROVED", "PREPARED", "HOLD"}
    ]


def approved_queue_pending_rows(rows: Iterable[dict[str, str]] | None = None) -> list[dict[str, str]]:
    queue_rows = list(rows) if rows is not None else load_apply_queue()
    return [
        row
        for row in queue_rows
        if row.get("queue_status", "") not in {"MANUALLY_SUBMITTED", "SKIPPED", "BLOCKED"} and not _is_manual_submission_recorded(row)
    ]


def mark_manual_submitted(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return update_apply_queue_fields(
        queue_id,
        {
            "queue_status": "PREPARED",
            "last_action": "MANUAL_SUBMITTED_RECORDED",
            "next_action": "次の候補へ進んでください。",
            "submission_method": "MANUAL",
            "manual_submitted_at": now,
        },
        path,
    )


def mark_skipped(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return update_apply_queue_status(queue_id, "SKIPPED", path)


def mark_hold(queue_id: str, path: Path = APPLY_QUEUE_CSV) -> bool:
    return update_apply_queue_status(queue_id, "HOLD", path)
