from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class InvalidSessionTransition(ValueError):
    """Raised when a session event would cross a safety boundary."""


SESSION_STATES = (
    "IDLE",
    "CANDIDATE_LOCKED",
    "PAGE_OPENED",
    "SUBMIT_GUARD_READY",
    "FORM_ANALYZED",
    "MAPPING_REVIEW_REQUIRED",
    "MAPPING_CONFIRMED",
    "FILLED",
    "POST_FILL_VERIFIED",
    "HUMAN_ACTION_REQUIRED",
    "USER_REPORTED_SUBMITTED",
    "COMPLETED",
    "HELD",
    "SKIPPED",
    "FAILED_SAFE",
    "ROLLBACK_REQUIRED",
    "UNSUPPORTED_FORM",
)

TERMINAL_WORKFLOW_STATES = frozenset(
    {
        "COMPLETED",
        "HELD",
        "SKIPPED",
        "FAILED_SAFE",
        "UNSUPPORTED_FORM",
        "ROLLBACK_REQUIRED",
    }
)


_EVENT_TARGETS: dict[str, dict[str, str]] = {
    "IDLE": {"candidate_locked": "CANDIDATE_LOCKED"},
    "CANDIDATE_LOCKED": {
        "page_opened": "PAGE_OPENED",
        "failed_safe": "FAILED_SAFE",
        "held": "HELD",
        "skipped": "SKIPPED",
    },
    "PAGE_OPENED": {
        "submit_guard_ready": "SUBMIT_GUARD_READY",
        "failed_safe": "FAILED_SAFE",
        "held": "HELD",
        "skipped": "SKIPPED",
    },
    "SUBMIT_GUARD_READY": {
        "form_analyzed": "FORM_ANALYZED",
        "skipped": "SKIPPED",
        "failed_safe": "FAILED_SAFE",
    },
    "FORM_ANALYZED": {
        "mapping_review_required": "MAPPING_REVIEW_REQUIRED",
        "mapping_confirmed": "MAPPING_CONFIRMED",
        "skipped": "SKIPPED",
        "unsupported_form": "UNSUPPORTED_FORM",
        "failed_safe": "FAILED_SAFE",
    },
    "MAPPING_REVIEW_REQUIRED": {
        "mapping_confirmed": "MAPPING_CONFIRMED",
        "unsupported_form": "UNSUPPORTED_FORM",
        "failed_safe": "FAILED_SAFE",
        "held": "HELD",
    },
    "MAPPING_CONFIRMED": {
        "filled": "FILLED",
        "skipped": "SKIPPED",
        "unsupported_form": "UNSUPPORTED_FORM",
        "failed_safe": "FAILED_SAFE",
    },
    "FILLED": {
        "post_fill_verified": "POST_FILL_VERIFIED",
        "rollback_required": "ROLLBACK_REQUIRED",
        "failed_safe": "FAILED_SAFE",
    },
    "POST_FILL_VERIFIED": {
        "human_action_required": "HUMAN_ACTION_REQUIRED",
        "rollback_required": "ROLLBACK_REQUIRED",
        "failed_safe": "FAILED_SAFE",
    },
    "HUMAN_ACTION_REQUIRED": {
        "user_reported_submitted": "USER_REPORTED_SUBMITTED",
        "held": "HELD",
        "skipped": "SKIPPED",
        "failed_safe": "FAILED_SAFE",
    },
    "USER_REPORTED_SUBMITTED": {"completed": "COMPLETED"},
    "ROLLBACK_REQUIRED": {
        "rollback_complete": "FAILED_SAFE",
        "rollback_incomplete": "ROLLBACK_REQUIRED",
    },
    "UNSUPPORTED_FORM": {"held": "HELD", "skipped": "SKIPPED"},
    "HELD": {"candidate_locked": "CANDIDATE_LOCKED"},
    "SKIPPED": {"candidate_locked": "CANDIDATE_LOCKED"},
    "FAILED_SAFE": {"candidate_locked": "CANDIDATE_LOCKED"},
    "COMPLETED": {"candidate_locked": "CANDIDATE_LOCKED"},
}


def _copy_state(state: Mapping[str, object]) -> dict[str, object]:
    return dict(state)


@dataclass(frozen=True)
class SessionStateMachine:
    """Small, side-effect-free state and candidate-lock boundary."""

    def is_transition_allowed(self, current: str, event: str) -> bool:
        return event in _EVENT_TARGETS.get(str(current or "IDLE").upper(), {})

    def lock_candidate(
        self,
        state: Mapping[str, object],
        candidate_id: str,
    ) -> dict[str, object]:
        candidate = str(candidate_id or "").strip()
        if not candidate:
            raise InvalidSessionTransition("candidate_required")
        current_active = str(state.get("active_candidate_id", "") or "").strip()
        if current_active and current_active != candidate:
            raise InvalidSessionTransition("active_candidate_locked")
        result = _copy_state(state)
        result["active_candidate_id"] = candidate
        result["candidate_id"] = candidate
        result.setdefault("workflow_state", "IDLE")
        if result["workflow_state"] == "IDLE":
            result["workflow_state"] = "CANDIDATE_LOCKED"
        return result

    def release_candidate(
        self,
        state: Mapping[str, object],
        candidate_id: str,
    ) -> dict[str, object]:
        candidate = str(candidate_id or "").strip()
        active = str(state.get("active_candidate_id", "") or "").strip()
        if not candidate or active != candidate:
            raise InvalidSessionTransition("candidate_lock_mismatch")
        result = _copy_state(state)
        result["active_candidate_id"] = ""
        result["candidate_id"] = ""
        return result

    def transition(
        self,
        state: Mapping[str, object],
        event: str,
        *,
        session_id: str,
        candidate_id: str,
    ) -> dict[str, object]:
        session = str(session_id or "").strip()
        candidate = str(candidate_id or "").strip()
        if not session or not candidate:
            raise InvalidSessionTransition("session_and_candidate_required")
        current = str(state.get("workflow_state", "IDLE") or "IDLE").upper()
        target = _EVENT_TARGETS.get(current, {}).get(str(event or "").strip())
        if not target:
            raise InvalidSessionTransition(f"invalid_transition:{current}:{event}")
        active = str(state.get("active_candidate_id", "") or "").strip()
        if active and active != candidate:
            raise InvalidSessionTransition("active_candidate_locked")
        result = _copy_state(state)
        result["workflow_state"] = target
        result["session_id"] = session
        result["candidate_id"] = candidate
        if target == "CANDIDATE_LOCKED":
            result["active_candidate_id"] = candidate
        if target == "COMPLETED":
            result["active_candidate_id"] = ""
            result["candidate_id"] = ""
        return result


__all__ = [
    "InvalidSessionTransition",
    "SESSION_STATES",
    "SessionStateMachine",
    "TERMINAL_WORKFLOW_STATES",
]
