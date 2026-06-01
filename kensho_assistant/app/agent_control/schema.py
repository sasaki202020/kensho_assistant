from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, TypedDict

from ..privacy_guard import redact_personal_info

AGENT_CONTROL_STATUSES = {"pending", "running", "needs_review", "blocked", "done", "failed", "cancelled"}
AGENT_CONTROL_AGENT_DEFINITIONS: list[dict[str, str]] = [
    {
        "agent_name": "ResearchAgent",
        "display_name": "ResearchAgent",
        "role": "懸賞URL候補の収集・整理",
        "purpose": "候補URLを安全に整理する",
        "default_action": "collect_candidates",
    },
    {
        "agent_name": "QueueAgent",
        "display_name": "QueueAgent",
        "role": "あとで応募キューへの登録",
        "purpose": "URL重複チェックと保存を行う",
        "default_action": "queue_register",
    },
    {
        "agent_name": "FormCheckAgent",
        "display_name": "FormCheckAgent",
        "role": "フォームの構造確認",
        "purpose": "readiness判定を行う",
        "default_action": "form_check",
    },
    {
        "agent_name": "SafetyAgent",
        "display_name": "SafetyAgent",
        "role": "危険判定",
        "purpose": "危険な応募ページや過剰な個人情報要求を検出する",
        "default_action": "safety_check",
    },
    {
        "agent_name": "ReportAgent",
        "display_name": "ReportAgent",
        "role": "集計レポート",
        "purpose": "今日の候補数と進捗をまとめる",
        "default_action": "report",
    },
    {
        "agent_name": "HumanReviewAgent",
        "display_name": "HumanReviewAgent",
        "role": "人間確認",
        "purpose": "人間確認が必要な案件だけを表示する",
        "default_action": "human_review",
    },
]
AGENT_CONTROL_AGENT_ORDER = [agent["agent_name"] for agent in AGENT_CONTROL_AGENT_DEFINITIONS]


class AgentControlJob(TypedDict, total=False):
    job_id: str
    agent_name: str
    action: str
    target_url: str
    queue_id: str
    normalized_url: str
    duplicate_key: str
    source_type: str
    official_confidence: str
    status: str
    created_at: str
    updated_at: str
    result_summary: str
    safety_memo: str
    error_message: str
    form_check_summary: str
    blocked_reason: str
    risk_level: str
    review_required: bool
    reviewed_by_human: bool
    reviewed_at: str
    pii_detected: bool
    submit_attempted: bool
    safe_to_submit: bool
    human_review_required: bool
    dry_run: bool


class AgentControlAgentCard(TypedDict, total=False):
    agent_name: str
    display_name: str
    role: str
    purpose: str
    status: str
    safe_to_submit: bool
    latest_job_id: str
    last_run_at: str
    latest_result: str
    latest_safety_memo: str
    pending_count: int
    running_count: int
    needs_review_count: int
    blocked_count: int
    done_count: int
    failed_count: int
    cancelled_count: int
    submit_attempted: bool


class AgentControlSafety(TypedDict, total=False):
    auto_submit: bool
    safe_to_submit: bool
    submitted_count_auto: int
    profile_enc_read: bool
    pii_logged: bool
    external_post: bool
    x_action_automated: bool


def normalize_agent_control_status(value: object) -> str:
    text = str(value or "pending").strip().casefold()
    return text if text in AGENT_CONTROL_STATUSES else "failed"


def _safe_text(value: object, default: str = "") -> str:
    text = redact_personal_info(str(value or default)).strip()
    return text or default


def _to_positive_int(value: object) -> int:
    try:
        return max(int(float(str(value))), 0)
    except (TypeError, ValueError):
        return 0


def canonical_agent_control_job(raw: Mapping[str, Any], default_agent_name: str | None = None) -> AgentControlJob:
    agent_name = _safe_text(raw.get("agent_name") or default_agent_name or "unknown", "unknown")
    status = normalize_agent_control_status(raw.get("status"))
    return {
        "job_id": _safe_text(raw.get("job_id"), ""),
        "agent_name": agent_name,
        "action": _safe_text(raw.get("action"), ""),
        "target_url": _safe_text(raw.get("target_url"), ""),
        "queue_id": _safe_text(raw.get("queue_id"), ""),
        "normalized_url": _safe_text(raw.get("normalized_url"), ""),
        "duplicate_key": _safe_text(raw.get("duplicate_key"), ""),
        "source_type": _safe_text(raw.get("source_type"), "manual_url"),
        "official_confidence": _safe_text(raw.get("official_confidence"), "unknown"),
        "status": status,
        "created_at": _safe_text(raw.get("created_at"), ""),
        "updated_at": _safe_text(raw.get("updated_at"), ""),
        "result_summary": _safe_text(raw.get("result_summary"), ""),
        "safety_memo": _safe_text(raw.get("safety_memo"), ""),
        "error_message": _safe_text(raw.get("error_message"), ""),
        "form_check_summary": _safe_text(raw.get("form_check_summary"), ""),
        "blocked_reason": _safe_text(raw.get("blocked_reason"), ""),
        "risk_level": _safe_text(raw.get("risk_level"), "low"),
        "review_required": bool(raw.get("review_required", False)),
        "reviewed_by_human": bool(raw.get("reviewed_by_human", False)),
        "reviewed_at": _safe_text(raw.get("reviewed_at"), ""),
        "pii_detected": bool(raw.get("pii_detected", False)),
        "submit_attempted": bool(raw.get("submit_attempted", False)),
        "safe_to_submit": False,
        "human_review_required": bool(raw.get("human_review_required", False)),
        "dry_run": bool(raw.get("dry_run", True)),
    }


def default_agent_control_jobs() -> list[AgentControlJob]:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return [
        canonical_agent_control_job(
            {
                "job_id": f"default-{index}",
                "agent_name": agent["agent_name"],
                "action": agent["default_action"],
                "target_url": "",
                "status": "pending",
                "created_at": timestamp,
                "updated_at": timestamp,
                "result_summary": "未実行",
                "safety_memo": "初期状態",
                "error_message": "",
                "form_check_summary": "",
                "blocked_reason": "",
                "risk_level": "low",
                "review_required": False,
                "reviewed_by_human": False,
                "reviewed_at": "",
                "pii_detected": False,
                "submit_attempted": False,
                "safe_to_submit": False,
                "human_review_required": agent["agent_name"] == "HumanReviewAgent",
                "dry_run": True,
            },
            default_agent_name=agent["agent_name"],
        )
        for index, agent in enumerate(AGENT_CONTROL_AGENT_DEFINITIONS)
    ]
