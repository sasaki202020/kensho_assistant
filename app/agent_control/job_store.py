from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ..paths import AGENT_CONTROL_DIR, AGENT_CONTROL_EVENTS_JSONL, AGENT_CONTROL_JOBS_JSONL, AGENT_CONTROL_STATUS_JSON, ensure_runtime_dirs
from ..privacy_guard import redact_personal_info, sanitize_log_payload
from .schema import AGENT_CONTROL_AGENT_DEFINITIONS, AgentControlJob, canonical_agent_control_job, normalize_agent_control_status


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _today_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10]


def ensure_agent_control_dirs() -> None:
    ensure_runtime_dirs()
    AGENT_CONTROL_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_path(path: Path | None, default_path: Path) -> Path:
    return path if path is not None else default_path


def load_job_rows(path: Path | None = None) -> list[AgentControlJob]:
    path = _resolve_path(path, AGENT_CONTROL_JOBS_JSONL)
    rows = _load_jsonl(path)
    latest: dict[str, AgentControlJob] = {}
    for row in rows:
        job = canonical_agent_control_job(row, default_agent_name=row.get("agent_name"))
        job_id = str(job.get("job_id", "")).strip()
        if not job_id:
            continue
        latest[job_id] = job
    return sorted(latest.values(), key=lambda item: (str(item.get("updated_at", "")), str(item.get("job_id", ""))), reverse=True)


def save_job_record(record: dict[str, Any], path: Path | None = None) -> AgentControlJob:
    ensure_agent_control_dirs()
    path = _resolve_path(path, AGENT_CONTROL_JOBS_JSONL)
    safe_record = canonical_agent_control_job(sanitize_log_payload(record), default_agent_name=record.get("agent_name"))
    safe_record["submit_attempted"] = False
    _append_jsonl(path, dict(safe_record))
    return safe_record


def append_control_event(event_type: str, detail: dict[str, Any], path: Path | None = None) -> None:
    ensure_agent_control_dirs()
    path = _resolve_path(path, AGENT_CONTROL_EVENTS_JSONL)
    payload = {
        "event_type": redact_personal_info(str(event_type)),
        "created_at": _now(),
        "detail": sanitize_log_payload(detail),
    }
    _append_jsonl(path, payload)


def load_latest_job_by_id(job_id: str, path: Path | None = None) -> AgentControlJob:
    for row in load_job_rows(path):
        if str(row.get("job_id", "")) == job_id:
            return row
    return {}


def load_latest_job_for_agent(agent_name: str, path: Path | None = None) -> AgentControlJob:
    for row in load_job_rows(path):
        if str(row.get("agent_name", "")) == agent_name:
            return row
    return {}


def list_job_rows(path: Path | None = None, *, limit: int | None = None) -> list[AgentControlJob]:
    path = _resolve_path(path, AGENT_CONTROL_JOBS_JSONL)
    rows = load_job_rows(path)
    if limit is None or limit < 0:
        return rows
    return rows[:limit]


def load_control_events(path: Path | None = None, *, limit: int | None = None) -> list[dict[str, Any]]:
    path = _resolve_path(path, AGENT_CONTROL_EVENTS_JSONL)
    rows = _load_jsonl(path)
    if limit is not None and limit >= 0:
        rows = rows[-limit:]
    return rows


def _count_status(rows: Iterable[AgentControlJob], status: str) -> int:
    return sum(1 for row in rows if str(row.get("status", "")) == status)


def build_agent_control_status_payload(path: Path | None = None, *, updated_at: str | None = None) -> dict[str, Any]:
    path = _resolve_path(path, AGENT_CONTROL_JOBS_JSONL)
    jobs = load_job_rows(path)
    timestamp = updated_at or _now()
    today = timestamp[:10]
    recent_events = load_control_events(limit=20)
    today_queue_adds = sum(
        1
        for row in jobs
        if str(row.get("agent_name", "")) == "QueueAgent"
        and _today_key(row.get("created_at", "")) == today
        and str(row.get("action", "")) in {"register_url", "queue_register"}
        and str(row.get("status", "")) in {"done", "needs_review", "blocked"}
    )
    duplicate_skips = sum(
        1
        for row in jobs
        if str(row.get("agent_name", "")) == "QueueAgent"
        and (
            "duplicate" in str(row.get("result_summary", "")).casefold()
            or "duplicate" in str(row.get("safety_memo", "")).casefold()
            or "重複" in str(row.get("result_summary", ""))
        )
    )
    form_checks = sum(
        1
        for row in jobs
        if str(row.get("agent_name", "")) == "FormCheckAgent"
        and str(row.get("status", "")) in {"done", "needs_review", "blocked", "failed"}
    )
    agents: list[dict[str, Any]] = []
    for agent in AGENT_CONTROL_AGENT_DEFINITIONS:
        latest = load_latest_job_for_agent(agent["agent_name"], path)
        status = normalize_agent_control_status(latest.get("status") or "pending") if latest else "pending"
        if not latest:
            status = "pending"
        agents.append(
            {
                "agent_name": agent["agent_name"],
                "display_name": agent["display_name"],
                "role": agent["role"],
                "purpose": agent["purpose"],
                "status": status if latest else "idle",
                "latest_job_id": latest.get("job_id", ""),
                "last_run_at": latest.get("updated_at", ""),
                "latest_result": latest.get("result_summary", "") or ("未実行" if not latest else ""),
                "latest_safety_memo": latest.get("safety_memo", "") or "",
                "pending_count": _count_status(jobs, "pending"),
                "running_count": _count_status(jobs, "running"),
                "needs_review_count": _count_status(jobs, "needs_review"),
                "blocked_count": _count_status(jobs, "blocked"),
                "done_count": _count_status(jobs, "done"),
                "failed_count": _count_status(jobs, "failed"),
                "cancelled_count": _count_status(jobs, "cancelled"),
                "submit_attempted": False,
                "safe_to_submit": False,
            }
        )
    summary = {
        "total_jobs": len(jobs),
        "pending_count": _count_status(jobs, "pending"),
        "running_count": _count_status(jobs, "running"),
        "needs_review_count": _count_status(jobs, "needs_review"),
        "blocked_count": _count_status(jobs, "blocked"),
        "done_count": _count_status(jobs, "done"),
        "failed_count": _count_status(jobs, "failed"),
        "cancelled_count": _count_status(jobs, "cancelled"),
        "pending": _count_status(jobs, "pending"),
        "running": _count_status(jobs, "running"),
        "needs_review": _count_status(jobs, "needs_review"),
        "blocked": _count_status(jobs, "blocked"),
        "done": _count_status(jobs, "done"),
        "failed": _count_status(jobs, "failed"),
        "cancelled": _count_status(jobs, "cancelled"),
        "submit_attempted_count": sum(1 for row in jobs if bool(row.get("submit_attempted", False))),
        "pii_detected_count": sum(1 for row in jobs if bool(row.get("pii_detected", False))),
        "today_added_url_count": today_queue_adds,
        "duplicate_skip_count": duplicate_skips,
        "form_diagnosed_count": form_checks,
    }
    return {
        "updated_at": timestamp,
        "submitted_count_auto": 0,
        "safe_to_submit": False,
        "status": "ok",
        "summary": summary,
        "agents": agents,
        "jobs": jobs,
        "recent_events": recent_events,
        "safety": {
            "auto_submit": False,
            "profile_enc_read": False,
            "pii_logged": False,
            "external_post": False,
            "x_action_automated": False,
        },
    }


def save_agent_control_status(payload: dict[str, Any], path: Path | None = None) -> Path:
    ensure_agent_control_dirs()
    path = _resolve_path(path, AGENT_CONTROL_STATUS_JSON)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_log_payload(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_agent_control_status(path: Path | None = None) -> dict[str, Any]:
    path = _resolve_path(path, AGENT_CONTROL_STATUS_JSON)
    if not path.exists():
        return build_agent_control_status_payload()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return build_agent_control_status_payload()
    if not isinstance(data, dict):
        return build_agent_control_status_payload()
    return data
