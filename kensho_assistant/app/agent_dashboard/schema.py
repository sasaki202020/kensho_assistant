from __future__ import annotations

from typing import Any, Mapping, TypedDict

AGENT_ROLE_DEFINITIONS: list[tuple[str, str]] = [
    ("queue_manager", "キュー整理担当"),
    ("campaign_researcher", "応募条件調査担当"),
    ("form_diagnostician", "フォーム診断担当"),
    ("safety_reviewer", "安全確認担当"),
    ("test_runner", "テスト担当"),
    ("docs_writer", "ドキュメント担当"),
]

AGENT_ROLE_ORDER = [role for role, _ in AGENT_ROLE_DEFINITIONS]
AGENT_ROLE_LABELS = {role: label for role, label in AGENT_ROLE_DEFINITIONS}
ALLOWED_AGENT_STATUSES = {"idle", "pending", "running", "passed", "completed", "warning", "failed", "error"}
STATUS_DISPLAY_MAP = {
    "pending": "idle",
    "idle": "idle",
    "running": "running",
    "passed": "completed",
    "completed": "completed",
    "warning": "warning",
    "failed": "error",
    "error": "error",
}
DEFAULT_AGENT_LAST_MESSAGE = "agent_status.json 未検出"


class AgentSafetyChecks(TypedDict, total=False):
    auto_submit: bool
    profile_enc_read: bool
    pii_logged: bool
    x_action_automated: bool


class AgentRecord(TypedDict, total=False):
    role: str
    display_name: str
    team_id: str
    team_name: str
    team_purpose: str
    status: str
    progress_percent: int
    total_tasks: int
    completed_tasks: int
    warning_count: int
    error_count: int
    last_message: str
    updated_at: str
    safety_checks: AgentSafetyChecks


def normalize_agent_status(value: object) -> str:
    text = str(value or "idle").strip().casefold()
    return text if text in ALLOWED_AGENT_STATUSES else "error"


def display_agent_status(value: object) -> str:
    return STATUS_DISPLAY_MAP.get(normalize_agent_status(value), "error")


def _to_non_negative_int(value: object, default: int = 0) -> int:
    try:
        number = int(float(str(value)))
    except (TypeError, ValueError):
        return default
    return max(number, 0)


def _clamp_percent(value: object) -> int:
    return min(max(_to_non_negative_int(value), 0), 100)


def _default_safety_checks() -> AgentSafetyChecks:
    return {
        "auto_submit": False,
        "profile_enc_read": False,
        "pii_logged": False,
        "x_action_automated": False,
    }


def canonical_agent_record(raw: Mapping[str, Any], default_role: str | None = None) -> AgentRecord:
    role = str(raw.get("role") or default_role or "unknown").strip() or "unknown"
    status = normalize_agent_status(raw.get("status"))
    record: AgentRecord = {
        "role": role,
        "display_name": str(raw.get("display_name") or AGENT_ROLE_LABELS.get(role, role)),
        "team_id": str(raw.get("team_id") or ""),
        "team_name": str(raw.get("team_name") or ""),
        "team_purpose": str(raw.get("team_purpose") or ""),
        "status": status,
        "status_display": display_agent_status(status),
        "progress_percent": _clamp_percent(raw.get("progress_percent", 0)),
        "total_tasks": _to_non_negative_int(raw.get("total_tasks", 0)),
        "completed_tasks": _to_non_negative_int(raw.get("completed_tasks", 0)),
        "warning_count": _to_non_negative_int(raw.get("warning_count", 0)),
        "error_count": _to_non_negative_int(raw.get("error_count", 0)),
        "last_message": str(raw.get("last_message") or DEFAULT_AGENT_LAST_MESSAGE),
        "updated_at": str(raw.get("updated_at") or ""),
    }
    safety_checks = raw.get("safety_checks")
    if isinstance(safety_checks, Mapping):
        record["safety_checks"] = {
            "auto_submit": bool(safety_checks.get("auto_submit", False)),
            "profile_enc_read": bool(safety_checks.get("profile_enc_read", False)),
            "pii_logged": bool(safety_checks.get("pii_logged", False)),
            "x_action_automated": bool(safety_checks.get("x_action_automated", False)),
        }
    elif role == "safety_reviewer":
        record["safety_checks"] = _default_safety_checks()
    return record


def default_agent_records() -> list[AgentRecord]:
    return [
        canonical_agent_record(
            {
                "role": role,
                "display_name": label,
                "status": "idle",
                "progress_percent": 0,
                "total_tasks": 0,
                "completed_tasks": 0,
                "warning_count": 0,
                "error_count": 0,
                "last_message": DEFAULT_AGENT_LAST_MESSAGE,
                "updated_at": "",
                "safety_checks": _default_safety_checks() if role == "safety_reviewer" else None,
            },
            default_role=role,
        )
        for role, label in AGENT_ROLE_DEFINITIONS
    ]
