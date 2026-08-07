from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from ..privacy_guard import redact_personal_info
from ..paths import AGENT_CONTROL_STATUS_JSON
from ..later_queue import add_later_queue, bridge_later_queue_to_campaign, list_later_queue, normalize_url, update_later_queue_status
from .agents import default_agent_action, get_agent_definition, list_agent_definitions
from .job_store import (
    append_control_event,
    build_agent_control_status_payload,
    load_control_events,
    load_job_rows,
    load_latest_job_by_id,
    load_latest_job_for_agent,
    load_agent_control_status,
    save_agent_control_status,
    save_job_record,
)
from .report import build_agent_control_report
from .safety import evaluate_control_job, sanitize_target_url
from ..release_report import latest_inspections


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _job_id() -> str:
    return f"job-{uuid4().hex[:12]}"


def _persist_status() -> dict[str, Any]:
    payload = build_agent_control_status_payload()
    payload["daily_report"] = build_agent_control_report(list(payload.get("jobs", [])))
    payload["recent_events"] = load_control_events(limit=20)
    payload["human_review_jobs"] = list_human_review_items(limit=20)
    save_agent_control_status(payload, AGENT_CONTROL_STATUS_JSON)
    return payload


def list_agent_control_agents() -> list[dict[str, Any]]:
    status = _persist_status()
    return list(status.get("agents", []))


def list_agent_control_jobs(limit: int | None = None) -> list[dict[str, Any]]:
    rows = load_job_rows()
    return rows if limit is None or limit < 0 else rows[:limit]


def get_agent_control_status() -> dict[str, Any]:
    return _persist_status()


def get_latest_job_for_agent(agent_name: str) -> dict[str, Any]:
    return load_latest_job_for_agent(agent_name)


def get_agent_control_report() -> dict[str, Any]:
    status = _persist_status()
    return dict(status.get("daily_report", build_agent_control_report(list(status.get("jobs", [])))))


def list_agent_control_events(limit: int | None = 20) -> list[dict[str, Any]]:
    return load_control_events(limit=limit)


def _load_later_queue_rows() -> list[dict[str, str]]:
    return list_later_queue()


def _find_later_queue_row(*, queue_id: str = "", target_url: str = "") -> dict[str, str]:
    rows = _load_later_queue_rows()
    normalized_target = normalize_url(target_url) if target_url else ""
    for row in rows:
        if queue_id and row.get("id", "") == queue_id:
            return row
        if target_url and row.get("normalized_url", "") == normalized_target:
            return row
    return {}


def _inspection_summary_for_campaign(campaign: dict[str, str]) -> dict[str, str]:
    campaign_id = campaign.get("campaign_id", "")
    inspections = latest_inspections()
    inspection = inspections.get(campaign_id, {}) if campaign_id else {}
    manual = inspection.get("manual_review_required_fields", "")
    blocked = inspection.get("blocked_auto_fill_fields", "")
    skipped = inspection.get("required_but_skipped_fields", "")
    readiness = campaign.get("form_readiness_status", "") or inspection.get("readiness_status", "") or "UNKNOWN"
    reason = campaign.get("form_readiness_reason", "") or inspection.get("readiness_reason", "") or "existing form_readiness / review needed"
    next_action = inspection.get("next_action", "") or "人間確認へ回す"
    summary_parts = [
        f"readiness={readiness}",
        f"reason={reason}",
        f"manual_review_required_fields={manual or 'none'}",
        f"blocked_auto_fill_fields={blocked or 'none'}",
        f"required_but_skipped_fields={skipped or 'none'}",
        f"next_action={next_action}",
    ]
    return {
        "readiness_status": readiness,
        "readiness_reason": reason,
        "manual_review_required_fields": str(manual or ""),
        "blocked_auto_fill_fields": str(blocked or ""),
        "required_but_skipped_fields": str(skipped or ""),
        "next_action": str(next_action or "人間確認へ回す"),
        "form_check_summary": " | ".join(summary_parts),
        "official_confidence": str(inspection.get("confidence", "unknown") or "unknown"),
    }


def _resolve_campaign_for_url(target_url: str) -> dict[str, str]:
    campaign = bridge_later_queue_to_campaign(target_url)
    if campaign:
        return dict(campaign)
    return {}


def create_job(agent_name: str, action: str, target_url: str = "", extra_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    definition = get_agent_definition(agent_name)
    resolved_agent = definition.get("agent_name") or agent_name
    timestamp = _now()
    record = {
        "job_id": _job_id(),
        "agent_name": resolved_agent,
        "action": redact_personal_info(str(action or default_agent_action(resolved_agent))),
        "target_url": sanitize_target_url(target_url),
        "status": "pending",
        "created_at": timestamp,
        "updated_at": timestamp,
        "result_summary": "待機中",
        "safety_memo": "dry-run",
        "error_message": "",
        "pii_detected": False,
        "submit_attempted": False,
        "safe_to_submit": False,
        "human_review_required": False,
        "dry_run": True,
    }
    if extra_fields:
        record.update(extra_fields)
    saved = save_job_record(record)
    append_control_event("job_created", saved)
    _persist_status()
    return saved


def start_job(job_id: str, *, extra_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    current = load_latest_job_by_id(job_id)
    if not current:
        return {}
    current["status"] = "running"
    current["updated_at"] = _now()
    current["result_summary"] = current.get("result_summary") or "実行中"
    current["submit_attempted"] = False
    current["safe_to_submit"] = False
    if extra_fields:
        current.update(extra_fields)
    saved = save_job_record(current)
    append_control_event("job_running", saved)
    _persist_status()
    return saved


def complete_job(
    job_id: str,
    *,
    status: str,
    result_summary: str,
    safety_memo: str = "",
    error_message: str = "",
    pii_detected: bool = False,
    human_review_required: bool = False,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = load_latest_job_by_id(job_id)
    if not current:
        return {}
    current["status"] = status
    current["updated_at"] = _now()
    current["result_summary"] = redact_personal_info(result_summary)
    current["safety_memo"] = redact_personal_info(safety_memo)
    current["error_message"] = redact_personal_info(error_message)
    current["pii_detected"] = bool(pii_detected)
    current["submit_attempted"] = False
    current["safe_to_submit"] = False
    current["human_review_required"] = bool(human_review_required)
    if extra_fields:
        current.update(extra_fields)
    saved = save_job_record(current)
    append_control_event("job_finished", saved)
    _persist_status()
    return saved


def cancel_job(job_id: str | None = None, agent_name: str = "") -> dict[str, Any]:
    current = load_latest_job_by_id(job_id) if job_id else {}
    if not current and agent_name:
        current = load_latest_job_for_agent(agent_name)
    if not current:
        return {}
    current["status"] = "cancelled"
    current["updated_at"] = _now()
    current["result_summary"] = "キャンセルしました"
    current["safety_memo"] = "dry-run cancelled"
    current["submit_attempted"] = False
    current["safe_to_submit"] = False
    saved = save_job_record(current)
    append_control_event("job_cancelled", saved)
    _persist_status()
    return saved


def list_human_review_items(limit: int | None = None) -> list[dict[str, Any]]:
    items = [
        job
        for job in load_job_rows()
        if str(job.get("status", "")) in {"needs_review", "blocked"} or bool(job.get("human_review_required", False))
    ]
    if limit is not None and limit >= 0:
        items = items[:limit]
    return items


def mark_job_reviewed(job_id: str, note: str = "") -> dict[str, Any]:
    current = load_latest_job_by_id(job_id)
    if not current:
        return {}
    current["status"] = "done"
    current["updated_at"] = _now()
    current["result_summary"] = redact_personal_info(note or current.get("result_summary") or "人間確認済み")
    current["safety_memo"] = "human_reviewed"
    current["error_message"] = ""
    current["review_required"] = False
    current["reviewed_by_human"] = True
    current["reviewed_at"] = _now()
    current["submit_attempted"] = False
    current["safe_to_submit"] = False
    saved = save_job_record(current)
    if current.get("queue_id"):
        update_later_queue_status(
            current["queue_id"],
            status="reviewing",
            review_note=note or "human reviewed",
            safety_memo="human_reviewed",
        )
    append_control_event("job_reviewed", saved)
    _persist_status()
    return saved


def register_url_candidate(target_url: str, *, action: str = "register_url") -> dict[str, Any]:
    added_row, created, reason = add_later_queue(target_url)
    queue_status = str(added_row.get("status", "queued") or "queued")
    final_status = "blocked" if queue_status == "blocked" else ("needs_review" if queue_status == "needs_review" else "done")
    result_summary = "候補URLを登録しました"
    safety_memo = "later queue registered"
    if not created and reason == "duplicate":
        result_summary = "重複URLのため既存候補を返しました"
        safety_memo = "duplicate skipped"
    elif queue_status == "needs_review":
        result_summary = "要確認として候補URLを登録しました"
        safety_memo = "needs_review"
    elif queue_status == "blocked":
        result_summary = "安全上の理由で候補URLをブロックしました"
        safety_memo = "blocked"
    extra = {
        "queue_id": added_row.get("id", ""),
        "normalized_url": added_row.get("normalized_url", ""),
        "duplicate_key": added_row.get("duplicate_key", ""),
        "source_type": added_row.get("source_type", "manual_url"),
        "official_confidence": "unknown",
        "review_required": queue_status == "needs_review",
        "blocked_reason": "duplicate" if not created and reason == "duplicate" else (safety_memo if queue_status == "blocked" else ""),
        "risk_level": "blocked" if queue_status == "blocked" else ("medium" if queue_status == "needs_review" else "low"),
        "safe_to_submit": False,
    }
    job = create_job("QueueAgent", action, target_url=target_url, extra_fields=extra)
    job = start_job(job["job_id"])
    if not job:
        return {}
    final = complete_job(
        job["job_id"],
        status=final_status,
        result_summary=result_summary,
        safety_memo=safety_memo,
        pii_detected=False,
        human_review_required=queue_status == "needs_review",
        extra_fields=extra,
    )
    return final


def run_form_check_job(target_url: str, *, queue_id: str = "", action: str = "form_check") -> dict[str, Any]:
    later_row = _find_later_queue_row(queue_id=queue_id, target_url=target_url)
    campaign = _resolve_campaign_for_url(target_url or later_row.get("url", ""))
    inspection = _inspection_summary_for_campaign(campaign)
    readiness = inspection.get("readiness_status", "UNKNOWN")
    status = "done"
    if readiness in {"REVIEW_ONLY", "LOW_CONFIDENCE", "SEARCH_ONLY", "LANDING_PAGE", "NO_FORM", "UNKNOWN"}:
        status = "needs_review"
    if readiness == "BLOCKED_BY_SAFETY":
        status = "blocked"
    extra = {
        "queue_id": later_row.get("id", queue_id),
        "normalized_url": later_row.get("normalized_url", normalize_url(target_url)),
        "duplicate_key": later_row.get("duplicate_key", ""),
        "source_type": later_row.get("source_type", "manual_url"),
        "official_confidence": inspection.get("official_confidence", "unknown"),
        "form_check_summary": inspection.get("form_check_summary", ""),
        "review_required": status == "needs_review",
        "blocked_reason": inspection.get("readiness_reason", "") if status == "blocked" else "",
        "risk_level": "blocked" if status == "blocked" else ("medium" if status == "needs_review" else "low"),
        "safe_to_submit": False,
    }
    job = create_job("FormCheckAgent", action, target_url=target_url, extra_fields=extra)
    job = start_job(job["job_id"])
    if not job:
        return {}
    if later_row:
        update_later_queue_status(
            later_row.get("id", ""),
            status="ready_for_fill" if status == "done" and readiness == "READY_FOR_FILL" else ("needs_review" if status == "needs_review" else "blocked"),
            review_note=inspection.get("form_check_summary", ""),
            safety_memo=inspection.get("form_check_summary", ""),
        )
    final = complete_job(
        job["job_id"],
        status=status,
        result_summary=inspection.get("form_check_summary", "") or inspection.get("readiness_reason", "") or "フォーム診断を記録しました",
        safety_memo="form_check",
        pii_detected=False,
        human_review_required=status == "needs_review",
        extra_fields=extra,
    )
    return final


def run_safety_check_job(target_url: str, *, queue_id: str = "", action: str = "safety_check") -> dict[str, Any]:
    later_row = _find_later_queue_row(queue_id=queue_id, target_url=target_url)
    campaign = _resolve_campaign_for_url(target_url or later_row.get("url", ""))
    inspection = _inspection_summary_for_campaign(campaign)
    title = campaign.get("campaign_name", "") or later_row.get("title", "")
    required_fields = inspection.get("manual_review_required_fields", "")
    optional_fields = inspection.get("required_but_skipped_fields", "")
    consent_fields = inspection.get("blocked_auto_fill_fields", "")
    result = evaluate_control_job(
        "SafetyAgent",
        action,
        target_url,
        {
            "title": title,
            "required_fields": required_fields,
            "optional_fields": optional_fields,
            "consent_fields": consent_fields,
            "review_reason": campaign.get("form_readiness_reason", "") or inspection.get("readiness_reason", ""),
            "blocked_reason": campaign.get("notes", "") or inspection.get("readiness_reason", ""),
            "official_confidence": inspection.get("official_confidence", "unknown"),
            "form_check_summary": inspection.get("form_check_summary", ""),
        },
    )
    extra = {
        "queue_id": later_row.get("id", queue_id),
        "normalized_url": later_row.get("normalized_url", normalize_url(target_url)),
        "duplicate_key": later_row.get("duplicate_key", ""),
        "source_type": later_row.get("source_type", "manual_url"),
        "official_confidence": inspection.get("official_confidence", "unknown"),
        "form_check_summary": inspection.get("form_check_summary", ""),
        "review_required": bool(result.get("human_review_required", False)),
        "blocked_reason": str(result.get("blocked_reason", "") or result.get("result_summary", "")),
        "risk_level": str(result.get("risk_level", "low") or "low"),
        "safe_to_submit": False,
    }
    job = create_job("SafetyAgent", action, target_url=target_url, extra_fields=extra)
    job = start_job(job["job_id"])
    if not job:
        return {}
    if later_row:
        next_status = "blocked" if result.get("status") == "blocked" else ("needs_review" if result.get("status") == "needs_review" else "reviewing")
        update_later_queue_status(
            later_row.get("id", ""),
            status=next_status,
            review_note=str(result.get("result_summary", "")),
            safety_memo=str(result.get("safety_memo", "")),
        )
    final = complete_job(
        job["job_id"],
        status=str(result.get("status", "done")),
        result_summary=str(result.get("result_summary", "安全確認を記録しました")),
        safety_memo=str(result.get("safety_memo", "")),
        error_message=str(result.get("error_message", "")),
        pii_detected=bool(result.get("pii_detected", False)),
        human_review_required=bool(result.get("human_review_required", False)),
        extra_fields=extra,
    )
    return final


def run_human_review_job(target_url: str = "", *, queue_id: str = "", action: str = "human_review") -> dict[str, Any]:
    later_row = _find_later_queue_row(queue_id=queue_id, target_url=target_url)
    review_items = list_human_review_items(limit=20)
    result_summary = f"人間確認待ち {len(review_items)} 件を確認できます"
    if later_row:
        result_summary = f"{later_row.get('title', 'unknown')} を人間確認待ちにしました"
    extra = {
        "queue_id": later_row.get("id", queue_id),
        "normalized_url": later_row.get("normalized_url", normalize_url(target_url)),
        "duplicate_key": later_row.get("duplicate_key", ""),
        "source_type": later_row.get("source_type", "manual_url"),
        "official_confidence": "unknown",
        "review_required": True,
        "blocked_reason": "",
        "risk_level": "medium",
        "safe_to_submit": False,
    }
    job = create_job("HumanReviewAgent", action, target_url=target_url, extra_fields=extra)
    job = start_job(job["job_id"])
    if not job:
        return {}
    if later_row and later_row.get("status", "") in {"blocked", "needs_review"}:
        update_later_queue_status(
            later_row.get("id", ""),
            status="reviewing",
            review_note="human review requested",
            safety_memo="human review requested",
        )
    final = complete_job(
        job["job_id"],
        status="needs_review",
        result_summary=result_summary,
        safety_memo="human_review",
        pii_detected=False,
        human_review_required=True,
        extra_fields=extra,
    )
    return final


def mark_reviewed_job(job_id: str, note: str = "") -> dict[str, Any]:
    return mark_job_reviewed(job_id, note=note)


def run_daily_report_job(action: str = "report") -> dict[str, Any]:
    report = get_agent_control_report()
    result_summary = (
        f"今日の候補数={report.get('today_added_url_count', 0)} / "
        f"重複スキップ={report.get('duplicate_skip_count', 0)} / "
        f"フォーム診断={report.get('form_diagnosed_count', 0)} / "
        f"needs_review={report.get('counts', {}).get('needs_review', 0)} / "
        f"blocked={report.get('counts', {}).get('blocked', 0)} / "
        f"done={report.get('counts', {}).get('done', 0)} / "
        f"failed={report.get('counts', {}).get('failed', 0)}"
    )
    job = create_job("ReportAgent", action, extra_fields={"risk_level": "low", "official_confidence": "unknown", "safe_to_submit": False})
    job = start_job(job["job_id"])
    if not job:
        return {}
    final = complete_job(
        job["job_id"],
        status="done",
        result_summary=result_summary,
        safety_memo="daily report",
        pii_detected=False,
        human_review_required=False,
        extra_fields={
            "risk_level": "low",
            "official_confidence": "unknown",
            "safe_to_submit": False,
        },
    )
    return final


def run_agent_job(agent_name: str, action: str | None = None, target_url: str = "") -> dict[str, Any]:
    definition = get_agent_definition(agent_name)
    resolved_action = action or definition.get("default_action") or default_agent_action(agent_name)
    if agent_name == "QueueAgent" or resolved_action == "register_url":
        return register_url_candidate(target_url, action=resolved_action)
    if agent_name == "FormCheckAgent" or resolved_action == "form_check":
        return run_form_check_job(target_url, action=resolved_action)
    if agent_name == "SafetyAgent" or resolved_action == "safety_check":
        return run_safety_check_job(target_url, action=resolved_action)
    if agent_name == "HumanReviewAgent" or resolved_action == "human_review":
        return run_human_review_job(target_url, action=resolved_action)
    if agent_name == "ReportAgent" or resolved_action == "report":
        return run_daily_report_job(action=resolved_action)
    job = create_job(agent_name, resolved_action, target_url=target_url)
    job = start_job(job["job_id"])
    if not job:
        return {}
    result = evaluate_control_job(agent_name, resolved_action, target_url)
    final = complete_job(
        job["job_id"],
        status=result["status"],
        result_summary=result["result_summary"],
        safety_memo=result["safety_memo"],
        error_message=result.get("error_message", ""),
        pii_detected=result["pii_detected"],
        human_review_required=result["human_review_required"],
    )
    return final
