from __future__ import annotations

import json
import hmac
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from .apply_queue import _deadline_bucket, approved_queue_rows, mark_hold, mark_manual_submitted, mark_skipped
from .auto_apply_engine import AutoApplyEngine
from .browser_manager import (
    clear_extension_control_token as clear_browser_extension_control_token,
    close_browser_safely,
    dedicated_extension_page_state,
    open_url_in_chrome,
    provision_extension_control_token,
    validate_dedicated_target_url,
)
from .entry_url_resolver import target_url_for_campaign
from .extension_bridge import ALLOWED_PAYLOAD_KEYS, CapabilityBridge
from .paths import ASSISTED_SESSION_DIR, ASSISTED_SESSION_STATE_JSON
from .paths import REAL_SITE_TRIAL_STEPS_JSONL, REAL_SITE_TRIALS_JSONL
from .privacy_guard import redact_personal_info
from .profile_manager import load_profile  # compatibility seam; runner never calls it
from .real_site_trials import (
    ErrorCategory,
    TrialStepLogger,
    TrialStore,
    build_trial_record,
    safe_site_identifier,
    trial_from_engine_result,
)
from .session_state_machine import (
    InvalidSessionTransition,
    SessionStateMachine,
    TERMINAL_WORKFLOW_STATES,
)


SESSION_STATUS_LABELS = {
    "IDLE": "未実行",
    "OPENING": "起動中",
    "FILLING": "入力中",
    "AWAITING_USER_SUBMIT": "送信待ち",
    "VERIFYING_COMPLETION": "送信後確認中",
    "AWAITING_USER_NEXT": "次へ待ち",
    "ADVANCING": "次へ進行中",
    "COMPLETED": "完了",
    "STOPPED": "停止",
    "ERROR": "異常",
}

SESSION_ACTIVE_STATUSES = {
    "OPENING",
    "FILLING",
    "AWAITING_USER_SUBMIT",
    "VERIFYING_COMPLETION",
    "AWAITING_USER_NEXT",
    "ADVANCING",
}

SESSION_STALE_SECONDS = 300

SESSION_HOLD_REASONS = [
    ("login_required", "ログインが必要"),
    ("captcha", "CAPTCHA"),
    ("expired", "期限切れ"),
    ("form_not_found", "フォームなし"),
    ("eligibility_mismatch", "応募条件不一致"),
    ("too_many_fields", "項目が多い"),
    ("social_application", "SNS応募"),
    ("possible_duplicate", "重複の可能性"),
    ("other", "その他"),
]

_STATE_LOCK = threading.RLock()
_SESSION_STATE_MACHINE = SessionStateMachine()
_EXTENSION_BRIDGE = CapabilityBridge(ttl_seconds=60)
_EXTENSION_CONTROL_TOKENS: dict[str, tuple[str, float]] = {}
_EXTENSION_PROGRESS_RESPONSES: dict[tuple[str, str], str] = {}


def register_extension_control_token(session_id: str) -> str:
    session = str(session_id or "").strip()
    if not session:
        raise ValueError("session_required")
    token = secrets.token_urlsafe(32)
    with _STATE_LOCK:
        _EXTENSION_CONTROL_TOKENS[session] = (token, time.monotonic() + 60)
    return token


def validate_extension_control_token(session_id: str, token: str) -> None:
    session = str(session_id or "").strip()
    supplied = str(token or "")
    with _STATE_LOCK:
        record = _EXTENSION_CONTROL_TOKENS.get(session)
    if (
        not record
        or time.monotonic() >= record[1]
        or not hmac.compare_digest(record[0], supplied)
    ):
        raise ValueError("invalid_extension_control_token")


def clear_extension_control_token(session_id: str) -> None:
    session = str(session_id or "").strip()
    with _STATE_LOCK:
        _EXTENSION_CONTROL_TOKENS.pop(session, None)
        for key in [key for key in _EXTENSION_PROGRESS_RESPONSES if key[0] == session]:
            _EXTENSION_PROGRESS_RESPONSES.pop(key, None)


COMPLETION_TERMS = (
    "応募完了",
    "受付完了",
    "送信完了",
    "登録完了",
    "申込完了",
    "申し込み完了",
    "完了しました",
)
UNCERTAIN_TERMS = (
    "ありがとうございました",
    "移動しました",
    "遷移しました",
)
CONFIRMATION_TERMS = (
    "確認画面",
    "内容確認",
    "最終確認",
    "送信前確認",
    "確認してください",
    "ご確認ください",
)


def default_assisted_session_state() -> dict[str, object]:
    return {
        "state_health": "missing",
        "load_error": "",
        "session_id": "",
        "workflow_state": "IDLE",
        "candidate_id": "",
        "active_candidate_id": "",
        "session_started_at": "",
        "session_finished_at": "",
        "candidate_started_at": "",
        "candidate_finished_at": "",
        "candidate_ids": [],
        "next_candidate_index": 1,
        "status": "IDLE",
        "status_label": SESSION_STATUS_LABELS["IDLE"],
        "final_status": "IDLE",
        "message": "応募セッションは未実行です。",
        "current_step": "",
        "current_campaign_id": "",
        "current_campaign_name": "",
        "current_queue_status": "",
        "current_index": 0,
        "total": 0,
        "done": 0,
        "ok": 0,
        "failed": 0,
        "processed": 0,
        "current_url": "",
        "current_title": "",
        "pre_submit_score": 0,
        "fill_completion_rate": 0,
        "unresolved_required_fields_count": 0,
        "review_items": [],
        "human_checklist": [],
        "ai_candidates": [],
        "submit_button_detected": False,
        "open_success": 0,
        "assist_success": 0,
        "hold_count": 0,
        "elapsed_seconds": 0,
        "hold_reason": "",
        "screenshot_path": "",
        "html_snapshot_path": "",
        "analysis_path": "",
        "check_path": "",
        "requested_action": "",
        "requested_queue_id": "",
        "requested_note": "",
        "requested_session_id": "",
        "requested_candidate_id": "",
        "requested_operation_id": "",
        "requested_hold_reason": "",
        "last_handled_operation_id": "",
        "last_handled_action": "",
        "last_handled_queue_id": "",
        "submitted_count_auto": 0,
        "started_at": "",
        "updated_at": "",
        "finished_at": "",
        "last_action": "",
        "last_reason": "",
    }


def extension_bridge_status() -> dict[str, object]:
    """Return non-PII bridge state for the management UI."""
    server = _EXTENSION_BRIDGE._server
    return {
        "running": server is not None,
        "host": _EXTENSION_BRIDGE.host if server is not None else "",
        "port": int(server.server_port) if server is not None else 0,
        "ttl_seconds": _EXTENSION_BRIDGE.ttl_seconds,
        "submitted_count_auto": 0,
    }


def issue_extension_capability(
    *,
    session_id: str,
    candidate_id: str,
    origin: str,
    fingerprint: str,
    profile: Mapping[str, object],
    profile_keys: list[str],
) -> dict[str, object]:
    """Issue a one-shot, mapping-scoped capability for the thin adapter."""
    state = load_assisted_session_state()
    if str(state.get("session_id", "") or "") != str(session_id or ""):
        raise ValueError("invalid_capability_binding")
    if str(state.get("active_candidate_id", "") or "") != str(candidate_id or ""):
        raise ValueError("invalid_capability_binding")
    if str(state.get("workflow_state", "") or "").upper() != "MAPPING_CONFIRMED":
        raise ValueError("invalid_capability_binding")
    current_url = urlsplit(str(state.get("current_url", "") or ""))
    supplied_origin = urlsplit(str(origin or "").strip())
    if (
        supplied_origin.scheme not in {"http", "https"}
        or not supplied_origin.netloc
        or supplied_origin.path not in {"", "/"}
        or supplied_origin.query
        or supplied_origin.fragment
        or (current_url.scheme, current_url.netloc)
        != (supplied_origin.scheme, supplied_origin.netloc)
    ):
        raise ValueError("invalid_capability_binding")
    expected_fingerprint = str(state.get("form_fingerprint", "") or "").strip()
    if not expected_fingerprint or not hmac.compare_digest(
        expected_fingerprint, str(fingerprint or "").strip()
    ):
        raise ValueError("invalid_capability_binding")
    keys = [str(key or "").strip() for key in profile_keys if str(key or "").strip()]
    if not keys or any(key not in ALLOWED_PAYLOAD_KEYS for key in keys):
        raise ValueError("invalid_capability_payload")
    payload: dict[str, str] = {}
    for key in keys:
        value = profile.get(key, "")
        if not isinstance(value, str):
            raise ValueError("invalid_capability_payload")
        payload[key] = value
    host, port = _EXTENSION_BRIDGE.start()
    issued = _EXTENSION_BRIDGE.issue(
        session_id=session_id,
        candidate_id=candidate_id,
        origin=origin,
        fingerprint=fingerprint,
        payload=payload,
    )
    return {"host": host, "port": port, **issued, "submitted_count_auto": 0}


_EXTENSION_PROGRESS_DETAIL_KEYS = frozenset(
    {
        "filled_count",
        "unrelated_changed_count",
        "target_mismatch_count",
        "rollback_complete",
    }
)


def record_extension_progress(
    *,
    session_id: str,
    candidate_id: str,
    origin: str,
    fingerprint: str,
    event: str,
    operation_id: str,
    progress_token: str = "",
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Record a PII-free, bound progress event from the extension adapter."""
    state = load_assisted_session_state()
    session = str(session_id or "").strip()
    candidate = str(candidate_id or "").strip()
    safe_origin = str(origin or "").strip()
    form_fingerprint = str(fingerprint or "").strip()
    operation = str(operation_id or "").strip()
    progress_event = str(event or "").strip().lower()
    progress_details = dict(details or {})
    if (
        not session
        or not candidate
        or not form_fingerprint
        or not operation
        or progress_event not in {
            "post_fill_verified",
            "rollback_required",
            "rollback_complete",
            "rollback_incomplete",
            "unsupported_form",
            "failed_safe",
        }
        or any(key not in _EXTENSION_PROGRESS_DETAIL_KEYS for key in progress_details)
    ):
        raise ValueError("invalid_extension_progress")
    if progress_event == "post_fill_verified":
        filled_count = progress_details.get("filled_count", 0)
        unrelated_count = progress_details.get("unrelated_changed_count", 0)
        mismatch_count = progress_details.get("target_mismatch_count", 0)
        if (
            isinstance(filled_count, bool)
            or isinstance(unrelated_count, bool)
            or isinstance(mismatch_count, bool)
            or not isinstance(filled_count, int)
            or not isinstance(unrelated_count, int)
            or not isinstance(mismatch_count, int)
            or not 1 <= filled_count <= 500
            or unrelated_count != 0
            or mismatch_count != 0
            or "rollback_complete" in progress_details
        ):
            raise ValueError("invalid_extension_progress")
    if progress_event in {"rollback_complete", "rollback_incomplete"}:
        expected_complete = progress_event == "rollback_complete"
        if progress_details.get("rollback_complete") is not expected_complete:
            raise ValueError("invalid_extension_progress")
    if str(state.get("session_id", "") or "") != session:
        raise ValueError("invalid_extension_progress_binding")
    if str(state.get("active_candidate_id", "") or "") != candidate:
        raise ValueError("invalid_extension_progress_binding")
    current_url = urlsplit(str(state.get("current_url", "") or ""))
    supplied_origin = urlsplit(safe_origin)
    if (
        supplied_origin.scheme not in {"http", "https"}
        or not supplied_origin.netloc
        or supplied_origin.path not in {"", "/"}
        or supplied_origin.query
        or supplied_origin.fragment
        or (current_url.scheme, current_url.netloc)
        != (supplied_origin.scheme, supplied_origin.netloc)
    ):
        raise ValueError("invalid_extension_progress_binding")
    existing_fingerprint = str(state.get("form_fingerprint", "") or "")
    if existing_fingerprint and existing_fingerprint != form_fingerprint:
        raise ValueError("invalid_extension_progress_binding")
    handled = state.get("extension_operation_ids", [])
    if not isinstance(handled, list):
        handled = []
    operation_records = state.get("extension_operations", [])
    if not isinstance(operation_records, list):
        operation_records = []
    prior = next(
        (
            item
            for item in operation_records
            if isinstance(item, dict) and item.get("operation_id") == operation
        ),
        None,
    )
    if operation in handled:
        if prior and prior.get("event") == progress_event:
            replay = dict(state)
            with _STATE_LOCK:
                replay_token = _EXTENSION_PROGRESS_RESPONSES.get((session, operation), "")
            if replay_token:
                replay["_extension_progress_token"] = replay_token
            return replay
        raise ValueError("duplicate_extension_progress")

    terminal_progress = progress_event != "rollback_required"
    _EXTENSION_BRIDGE.validate_progress(
        token=progress_token,
        session_id=session,
        candidate_id=candidate,
        origin=safe_origin,
        fingerprint=form_fingerprint,
        consume=terminal_progress,
    )

    updated = dict(state)
    if progress_event == "post_fill_verified":
        for transition_event in ("filled", "post_fill_verified", "human_action_required"):
            updated = _workflow_event(
                updated,
                transition_event,
                session_id=session,
                candidate_id=candidate,
            )
    elif progress_event == "rollback_required" and str(
        updated.get("workflow_state", "") or ""
    ).upper() == "MAPPING_CONFIRMED":
        updated = _workflow_event(
            updated,
            "filled",
            session_id=session,
            candidate_id=candidate,
        )
        updated = _workflow_event(
            updated,
            "rollback_required",
            session_id=session,
            candidate_id=candidate,
        )
    else:
        updated = _workflow_event(
            updated,
            progress_event,
            session_id=session,
            candidate_id=candidate,
        )
    updated["form_fingerprint"] = form_fingerprint
    updated["extension_operation_ids"] = [*handled[-31:], operation]
    updated["extension_operations"] = [
        *operation_records[-31:],
        {"operation_id": operation, "event": progress_event},
    ]
    updated["filled_field_count"] = int(progress_details.get("filled_count", 0) or 0)
    updated["unrelated_changed_count"] = int(
        progress_details.get("unrelated_changed_count", 0) or 0
    )
    updated["submitted_count_auto"] = 0
    updated["current_step"] = progress_event
    updated["last_action"] = progress_event.upper()
    updated["last_reason"] = ""
    if progress_event == "post_fill_verified":
        updated.update(
            status="AWAITING_USER_SUBMIT",
            status_label=SESSION_STATUS_LABELS["AWAITING_USER_SUBMIT"],
            final_status="HUMAN_ACTION_REQUIRED",
            message="拡張機能の入力後検証が完了しました。本人確認と手動送信を待っています。",
        )
    save_assisted_session_state(updated)
    if progress_event == "post_fill_verified":
        next_progress_token = _EXTENSION_BRIDGE.issue_progress(
            session_id=session,
            candidate_id=candidate,
            origin=safe_origin,
            fingerprint=form_fingerprint,
        )
        with _STATE_LOCK:
            _EXTENSION_PROGRESS_RESPONSES[(session, operation)] = next_progress_token
        updated["_extension_progress_token"] = next_progress_token
    return updated


def consume_extension_capability(**kwargs: str) -> dict[str, object]:
    """Consume a capability without exposing the bridge internals."""
    return _EXTENSION_BRIDGE.consume(**kwargs)


def revoke_extension_capabilities(session_id: str) -> int:
    return _EXTENSION_BRIDGE.revoke_session(session_id)


def mark_extension_coordination_failed(
    *, session_id: str, candidate_id: str, origin: str, fingerprint: str
) -> dict[str, object]:
    """Apply a monotonic safe-stop when short-lived coordination expires."""
    state = load_assisted_session_state()
    session = str(session_id or "").strip()
    candidate = str(candidate_id or "").strip()
    current_url = urlsplit(str(state.get("current_url", "") or ""))
    supplied_origin = urlsplit(str(origin or "").strip())
    if (
        str(state.get("session_id", "") or "") != session
        or str(state.get("active_candidate_id", "") or "") != candidate
        or supplied_origin.scheme not in {"http", "https"}
        or not supplied_origin.netloc
        or supplied_origin.path not in {"", "/"}
        or supplied_origin.query
        or supplied_origin.fragment
        or (current_url.scheme, current_url.netloc)
        != (supplied_origin.scheme, supplied_origin.netloc)
        or not hmac.compare_digest(
            str(state.get("form_fingerprint", "") or ""),
            str(fingerprint or "").strip(),
        )
    ):
        raise ValueError("invalid_coordination_failure_binding")
    current = str(state.get("workflow_state", "") or "").upper()
    if current != "FAILED_SAFE":
        state = _workflow_event(
            state, "failed_safe", session_id=session, candidate_id=candidate
        )
    state.update(
        status="STOPPED",
        status_label=SESSION_STATUS_LABELS["STOPPED"],
        final_status="FAILED_SAFE",
        current_step="extension_coordination_failed",
        last_action="EXTENSION_COORDINATION_FAILED",
        last_reason="extension_coordination_expired",
        message="拡張機能との安全な同期が失効したため停止しました。応募済みにはしていません。",
        submitted_count_auto=0,
        candidate_marked_submitted=False,
    )
    save_assisted_session_state(state)
    revoke_extension_capabilities(session)
    return state


def stop_extension_bridge() -> None:
    _EXTENSION_BRIDGE.stop()


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_personal_info(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    return value


def _now() -> datetime:
    return datetime.now().astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_iso_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _elapsed_seconds(started_at: str, finished_at: str = "") -> int:
    start = _parse_iso_datetime(started_at)
    end = _parse_iso_datetime(finished_at) or _now()
    if not start:
        return 0
    delta = end - start
    return max(0, int(delta.total_seconds()))


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(text, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass


def _normalize_state(state: Mapping[str, object] | None = None) -> dict[str, object]:
    payload = default_assisted_session_state()
    if state:
        for key, value in state.items():
            payload[key] = _redact_value(value)
    if not payload.get("state_health"):
        payload["state_health"] = "missing"
    payload["state_health"] = str(payload.get("state_health", "missing") or "missing").strip().lower()
    payload["load_error"] = str(payload.get("load_error", "") or "")
    payload["status"] = str(payload.get("status", "IDLE") or "IDLE").strip().upper()
    payload["status_label"] = SESSION_STATUS_LABELS.get(str(payload["status"]), str(payload["status"]) or "未実行")
    payload["final_status"] = str(payload.get("final_status", payload["status"]) or payload["status"]).strip().upper()
    payload["session_id"] = str(payload.get("session_id", "") or "")
    payload["workflow_state"] = str(payload.get("workflow_state", "IDLE") or "IDLE").strip().upper()
    payload["candidate_id"] = str(payload.get("candidate_id", "") or "")
    payload["active_candidate_id"] = str(payload.get("active_candidate_id", "") or "")
    payload["session_started_at"] = str(payload.get("session_started_at", "") or payload.get("started_at", "") or "")
    payload["session_finished_at"] = str(payload.get("session_finished_at", "") or payload.get("finished_at", "") or "")
    payload["candidate_started_at"] = str(payload.get("candidate_started_at", "") or "")
    payload["candidate_finished_at"] = str(payload.get("candidate_finished_at", "") or "")
    payload["started_at"] = str(payload.get("started_at", "") or payload["session_started_at"] or "")
    payload["finished_at"] = str(payload.get("finished_at", "") or payload["session_finished_at"] or "")
    payload["submitted_count_auto"] = int(payload.get("submitted_count_auto", 0) or 0)
    payload["current_index"] = int(payload.get("current_index", 0) or 0)
    payload["next_candidate_index"] = max(1, int(payload.get("next_candidate_index", 1) or 1))
    payload["total"] = int(payload.get("total", 0) or 0)
    payload["done"] = int(payload.get("done", 0) or 0)
    payload["ok"] = int(payload.get("ok", 0) or 0)
    payload["failed"] = int(payload.get("failed", 0) or 0)
    payload["processed"] = int(payload.get("processed", 0) or 0)
    payload["open_success"] = int(payload.get("open_success", 0) or 0)
    payload["assist_success"] = int(payload.get("assist_success", 0) or 0)
    payload["hold_count"] = int(payload.get("hold_count", 0) or 0)
    payload["elapsed_seconds"] = int(payload.get("elapsed_seconds", 0) or 0)
    payload["current_campaign_id"] = str(payload.get("current_campaign_id", "") or "")
    payload["current_campaign_name"] = str(payload.get("current_campaign_name", "") or "")
    payload["current_queue_status"] = str(payload.get("current_queue_status", "") or "")
    payload["current_step"] = str(payload.get("current_step", "") or "")
    payload["current_url"] = str(payload.get("current_url", "") or "")
    payload["current_title"] = str(payload.get("current_title", "") or "")
    payload["message"] = str(payload.get("message", "") or "")
    payload["current_step"] = str(payload.get("current_step", "") or "")
    payload["requested_action"] = str(payload.get("requested_action", "") or "")
    payload["requested_queue_id"] = str(payload.get("requested_queue_id", "") or "")
    payload["requested_note"] = str(payload.get("requested_note", "") or "")
    payload["requested_session_id"] = str(payload.get("requested_session_id", "") or "")
    payload["requested_candidate_id"] = str(payload.get("requested_candidate_id", "") or "")
    payload["requested_operation_id"] = str(payload.get("requested_operation_id", "") or "")
    payload["requested_hold_reason"] = str(payload.get("requested_hold_reason", "") or "")
    payload["last_handled_operation_id"] = str(payload.get("last_handled_operation_id", "") or "")
    payload["last_handled_action"] = str(payload.get("last_handled_action", "") or "")
    payload["last_handled_queue_id"] = str(payload.get("last_handled_queue_id", "") or "")
    payload["hold_reason"] = str(payload.get("hold_reason", "") or "")
    payload["started_at"] = str(payload.get("started_at", "") or "")
    payload["updated_at"] = str(payload.get("updated_at", "") or "")
    payload["finished_at"] = str(payload.get("finished_at", "") or "")
    payload["last_action"] = str(payload.get("last_action", "") or "")
    payload["last_reason"] = str(payload.get("last_reason", "") or "")
    candidate_ids = payload.get("candidate_ids", [])
    payload["candidate_ids"] = [str(item).strip() for item in candidate_ids] if isinstance(candidate_ids, list) else []
    payload["review_items"] = list(payload.get("review_items", []) or []) if isinstance(payload.get("review_items", []), list) else []
    payload["human_checklist"] = list(payload.get("human_checklist", []) or []) if isinstance(payload.get("human_checklist", []), list) else []
    payload["ai_candidates"] = list(payload.get("ai_candidates", []) or []) if isinstance(payload.get("ai_candidates", []), list) else []
    payload["state_health"] = "corrupt" if payload["state_health"] == "corrupt" else payload["state_health"]
    payload["final_status"] = payload["final_status"] or payload["status"]
    return payload


def load_assisted_session_state() -> dict[str, object]:
    with _STATE_LOCK:
        if not ASSISTED_SESSION_STATE_JSON.exists():
            return default_assisted_session_state()
        try:
            data = json.loads(ASSISTED_SESSION_STATE_JSON.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = default_assisted_session_state()
            payload.update(
                status="ERROR",
                status_label=SESSION_STATUS_LABELS["ERROR"],
                final_status="ERROR",
                state_health="corrupt",
                load_error=redact_personal_info(str(exc)),
                message="状態ファイルの読み込みに失敗しました。安全のため停止してください。",
            )
            return _normalize_state(payload)
        if not isinstance(data, dict):
            payload = default_assisted_session_state()
            payload.update(
                status="ERROR",
                status_label=SESSION_STATUS_LABELS["ERROR"],
                final_status="ERROR",
                state_health="corrupt",
                load_error="state payload is not a dict",
                message="状態ファイルが壊れています。安全のため停止してください。",
            )
            return _normalize_state(payload)
        payload = _normalize_state(data)
        if payload.get("state_health") == "missing":
            payload["state_health"] = "ok"
        payload["load_error"] = ""
        return payload


def save_assisted_session_state(payload: dict[str, object]) -> Path:
    with _STATE_LOCK:
        ASSISTED_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        data = _normalize_state(payload)
        now = _now_iso()
        data["updated_at"] = now
        if not data.get("started_at") and data.get("session_started_at"):
            data["started_at"] = str(data.get("session_started_at", "") or now)
        if not data.get("session_started_at") and data.get("started_at"):
            data["session_started_at"] = str(data.get("started_at", "") or now)
        if data.get("status") in SESSION_ACTIVE_STATUSES and not data.get("session_started_at"):
            data["session_started_at"] = now
            data["started_at"] = now
        data["elapsed_seconds"] = _elapsed_seconds(str(data.get("session_started_at", "") or ""), str(data.get("session_finished_at", "") or ""))
        data["final_status"] = str(data.get("final_status", data.get("status", "IDLE")) or data.get("status", "IDLE")).strip().upper()
        _atomic_write_text(ASSISTED_SESSION_STATE_JSON, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return ASSISTED_SESSION_STATE_JSON


def request_assisted_session_action(
    action: str,
    queue_id: str = "",
    note: str = "",
    *,
    session_id: str = "",
    candidate_id: str = "",
    operation_id: str = "",
    hold_reason: str = "",
) -> Path:
    with _STATE_LOCK:
        state = load_assisted_session_state()
        normalized_operation_id = str(operation_id or "").strip()
        if normalized_operation_id and (
            str(state.get("requested_operation_id", "") or "") == normalized_operation_id
            or str(state.get("last_handled_operation_id", "") or "") == normalized_operation_id
        ):
            return ASSISTED_SESSION_STATE_JSON
        state["requested_action"] = str(action or "").strip().lower()
        state["requested_queue_id"] = str(queue_id or "").strip()
        state["requested_note"] = redact_personal_info(str(note or "").strip())
        state["requested_session_id"] = str(session_id or "").strip()
        state["requested_candidate_id"] = str(candidate_id or "").strip()
        state["requested_operation_id"] = normalized_operation_id
        state["requested_hold_reason"] = str(hold_reason or "").strip()
        state["updated_at"] = _now_iso()
        return save_assisted_session_state(state)


def clear_assisted_session_action() -> Path:
    with _STATE_LOCK:
        state = load_assisted_session_state()
        state["requested_action"] = ""
        state["requested_queue_id"] = ""
        state["requested_note"] = ""
        state["requested_session_id"] = ""
        state["requested_candidate_id"] = ""
        state["requested_operation_id"] = ""
        state["requested_hold_reason"] = ""
        state["updated_at"] = _now_iso()
        return save_assisted_session_state(state)


def classify_completion_snapshot(current_url: str, title: str, body_text: str, baseline_url: str = "") -> dict[str, object]:
    current_url = str(current_url or "").strip()
    title = str(title or "").strip()
    body_text = str(body_text or "").strip()
    baseline_url = str(baseline_url or "").strip()
    combined = "\n".join(part for part in [current_url, title, body_text] if part)
    has_completion = any(term in combined for term in COMPLETION_TERMS)
    has_confirmation = any(term in combined for term in CONFIRMATION_TERMS)
    url_changed = bool(baseline_url and current_url and current_url != baseline_url)

    if has_completion and not has_confirmation:
        state = "COMPLETED"
        reason = "完了表示を検知しました"
    elif has_confirmation:
        state = "AWAITING_USER_SUBMIT"
        reason = "確認画面を検知しました"
    elif url_changed or any(term in combined for term in UNCERTAIN_TERMS):
        state = "AWAITING_USER_NEXT"
        reason = "URL が変わりましたが完了表示は未確認です"
    else:
        state = "AWAITING_USER_SUBMIT"
        reason = "送信待ちのままです"

    return {
        "state": state,
        "manual_submit_observed": bool(has_completion or url_changed),
        "completion_confirmed": bool(has_completion and not has_confirmation),
        "reason": reason,
        "current_url": current_url,
        "title": title,
    }


def _is_session_active(state: Mapping[str, object]) -> bool:
    return str(state.get("status", "")).strip().upper() in SESSION_ACTIVE_STATUSES


def _is_session_fresh(state: Mapping[str, object], stale_seconds: int = SESSION_STALE_SECONDS) -> bool:
    updated_at = _parse_iso_datetime(str(state.get("updated_at", "") or ""))
    if not updated_at:
        return False
    return (_now() - updated_at) <= timedelta(seconds=max(int(stale_seconds), 1))


def _candidate_ids_from_rows(rows: list[dict[str, str]]) -> list[str]:
    return [str(row.get("campaign_id", "")).strip() for row in rows if str(row.get("campaign_id", "")).strip()]


def _candidate_row_by_id(rows: list[dict[str, str]], campaign_id: str) -> dict[str, str]:
    for row in rows:
        if str(row.get("campaign_id", "")).strip() == str(campaign_id or "").strip():
            return row
    return {}


def _begin_candidate_workflow(
    state: Mapping[str, object],
    *,
    session_id: str,
    candidate_id: str,
) -> dict[str, object]:
    """Release a terminal prior candidate and acquire the next exclusive lock."""
    result = dict(state)
    active = str(result.get("active_candidate_id", "") or "").strip()
    candidate = str(candidate_id or "").strip()
    if active and active != candidate:
        workflow_state = str(result.get("workflow_state", "IDLE") or "IDLE").upper()
        if workflow_state not in TERMINAL_WORKFLOW_STATES:
            raise InvalidSessionTransition("active_candidate_locked")
        result = _SESSION_STATE_MACHINE.release_candidate(result, active)
    elif active:
        result = _SESSION_STATE_MACHINE.release_candidate(result, active)
    result["workflow_state"] = "IDLE"
    result["session_id"] = str(session_id or "").strip()
    return _SESSION_STATE_MACHINE.lock_candidate(result, candidate)


def _workflow_event(
    state: Mapping[str, object],
    event: str,
    *,
    session_id: str,
    candidate_id: str,
) -> dict[str, object]:
    """Apply a guarded event; callers must fail safe on a rejected transition."""
    return _SESSION_STATE_MACHINE.transition(
        state,
        event,
        session_id=session_id,
        candidate_id=candidate_id,
    )


def _run_session_engine(
    engine,
    page,
    campaign: Mapping[str, object],
    profile: Mapping[str, object],
    *,
    mapping_confirmed: bool,
) -> dict[str, object]:
    """Run the existing engine with the assisted-session mapping gate.

    Older test doubles and integrations may not accept the new keyword.  That
    compatibility path is limited to non-production doubles; the real engine
    always receives the mapping gate.
    """
    try:
        return engine.run(
            page,
            campaign,
            profile,
            require_mapping_confirmation=True,
            mapping_confirmed=mapping_confirmed,
        )
    except TypeError as exc:
        if "require_mapping_confirmation" not in str(exc) and "mapping_confirmed" not in str(exc):
            raise
        return engine.run(page, campaign, profile)


def _record_engine_workflow_state(
    state: dict[str, object],
    result: Mapping[str, object],
    *,
    session_id: str,
    candidate_id: str,
) -> dict[str, object]:
    """Mirror the existing engine checkpoints into the session state machine."""
    current = state
    record = result.get("record", {}) if isinstance(result, Mapping) else {}
    status = str(record.get("status", "") or "").upper()
    workflow_state = str(current.get("workflow_state", "IDLE") or "IDLE").upper()
    if workflow_state == "CANDIDATE_LOCKED":
        current = _workflow_event(current, "page_opened", session_id=session_id, candidate_id=candidate_id)
        workflow_state = "PAGE_OPENED"
    if workflow_state == "PAGE_OPENED":
        current = _workflow_event(current, "submit_guard_ready", session_id=session_id, candidate_id=candidate_id)
        current = _workflow_event(current, "form_analyzed", session_id=session_id, candidate_id=candidate_id)
        workflow_state = "FORM_ANALYZED"
    if status == "SKIPPED":
        return _workflow_event(current, "skipped", session_id=session_id, candidate_id=candidate_id)
    if bool(record.get("mapping_review_required", False)):
        if str(current.get("workflow_state", "") or "").upper() == "MAPPING_REVIEW_REQUIRED":
            return current
        return _workflow_event(current, "mapping_review_required", session_id=session_id, candidate_id=candidate_id)
    workflow_state = str(current.get("workflow_state", "") or "").upper()
    if workflow_state in {"FORM_ANALYZED", "MAPPING_REVIEW_REQUIRED"}:
        current = _workflow_event(current, "mapping_confirmed", session_id=session_id, candidate_id=candidate_id)
    workflow_state = str(current.get("workflow_state", "") or "").upper()
    if workflow_state == "MAPPING_CONFIRMED":
        current = _workflow_event(current, "filled", session_id=session_id, candidate_id=candidate_id)
    workflow_state = str(current.get("workflow_state", "") or "").upper()
    if workflow_state == "FILLED":
        current = _workflow_event(current, "post_fill_verified", session_id=session_id, candidate_id=candidate_id)
    workflow_state = str(current.get("workflow_state", "") or "").upper()
    if workflow_state == "POST_FILL_VERIFIED":
        return _workflow_event(current, "human_action_required", session_id=session_id, candidate_id=candidate_id)
    if workflow_state == "HUMAN_ACTION_REQUIRED":
        return current
    raise InvalidSessionTransition(f"engine_result_unhandled:{workflow_state}")


def _session_action_key(session_id: str, queue_id: str, action: str, operation_id: str = "", hold_reason: str = "") -> str:
    return "|".join(
        [
            str(session_id or "").strip(),
            str(queue_id or "").strip(),
            str(action or "").strip().lower(),
            str(operation_id or "").strip(),
            str(hold_reason or "").strip().lower(),
        ]
    )


def _record_handled_action(
    state: dict[str, object],
    *,
    action: str,
    queue_id: str,
    snapshot: Mapping[str, object],
) -> dict[str, object]:
    operation_id = str(snapshot.get("operation_id", "") or "").strip()
    if operation_id:
        state["last_handled_operation_id"] = operation_id
        state["last_handled_action"] = str(action or "").strip().lower()
        state["last_handled_queue_id"] = str(queue_id or "").strip()
    return state


def _is_valid_target_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _session_sort_key(row: Mapping[str, object]) -> tuple[int, int, int, str]:
    deadline_bucket, _ = _deadline_bucket(str(row.get("deadline", "")))
    readiness = 0 if str(row.get("readiness_status", "")) == "READY_FOR_FILL" else 1
    order = {"APPROVED": 0, "PREPARED": 1, "HOLD": 2}
    return (deadline_bucket, readiness, order.get(str(row.get("queue_status", "")).upper(), 9), str(row.get("campaign_name", "")))


def _load_session_candidates(status_filter: str, limit: int) -> list[dict[str, str]]:
    statuses = {
        part.strip().upper()
        for part in str(status_filter or "APPROVED,PREPARED").split(",")
        if part.strip()
    }
    if not statuses:
        statuses = {"APPROVED", "PREPARED"}
    candidates = [
        row
        for row in approved_queue_rows()
        if str(row.get("queue_status", "")).strip().upper() in statuses
        and str(row.get("approved_by_user", "")).strip().lower() == "true"
        and str(row.get("campaign_id", "")).strip()
    ]
    candidates = sorted(candidates, key=_session_sort_key)
    return candidates[: max(int(limit), 0)]


def _page_title(page) -> str:
    try:
        return str(page.title() or "")
    except Exception:
        return ""


def _page_body_text(page) -> str:
    try:
        locator = page.locator("body")
        if locator.count():
            return str(locator.inner_text(timeout=5000) or "")
    except Exception:
        pass
    return ""


def _record_state_from_result(
    *,
    state: dict[str, object],
    result: dict[str, object],
    page,
    campaign: Mapping[str, object],
    index: int,
    total: int,
) -> dict[str, object]:
    record = result.get("record", {}) if isinstance(result, dict) else {}
    pre_submit_check = result.get("pre_submit_check", {}) if isinstance(result, dict) else {}
    review_items = record.get("review_items", [])
    if not isinstance(review_items, list):
        review_items = []
    state.update(
        status=str(record.get("status", "AWAITING_USER_SUBMIT") or "AWAITING_USER_SUBMIT").strip().upper(),
        current_step="awaiting_user",
        current_index=index,
        total=total,
        processed=index,
        current_campaign_id=str(campaign.get("campaign_id", "") or ""),
        current_campaign_name=str(campaign.get("campaign_name", "") or ""),
        current_queue_status=str(campaign.get("queue_status", "") or ""),
        current_url=str(getattr(page, "url", "") or ""),
        current_title=_page_title(page),
        pre_submit_score=int(record.get("pre_submit_score", 0) or 0),
        fill_completion_rate=float(record.get("fill_completion_rate", 0) or 0),
        unresolved_required_fields_count=int(record.get("unresolved_required_fields_count", 0) or 0),
        review_items=review_items,
        human_checklist=list(pre_submit_check.get("human_checklist", []) if isinstance(pre_submit_check, dict) else []),
        ai_candidates=list(pre_submit_check.get("ai_candidates", []) if isinstance(pre_submit_check, dict) else []),
        submit_button_detected=bool(record.get("submit_button_detected", False)),
        screenshot_path=str(record.get("screenshot_path", "") or ""),
        html_snapshot_path=str(record.get("html_snapshot_path", "") or ""),
        analysis_path=str(record.get("analysis_path", "") or ""),
        check_path=str(record.get("check_path", "") or ""),
        submitted_count_auto=0,
        message=f"[{index}/{total}] {str(campaign.get('campaign_name', '') or campaign.get('campaign_id', ''))} を確認中です。",
        last_action="INPUT_REVIEW_COMPLETE",
        last_reason=str(record.get("skip_reason", "") or ""),
    )
    return state


def _wait_for_user_decision(
    *,
    page,
    baseline_url: str,
    campaign: Mapping[str, object],
    session_id: str,
    index: int,
    total: int,
    poll_interval_sec: float,
) -> tuple[str, dict[str, object]]:
    while True:
        state = load_assisted_session_state()
        if str(state.get("state_health", "ok")) == "corrupt" or str(state.get("status", "")).strip().upper() == "ERROR":
            return "stop", {
                "state": "ERROR",
                "manual_submit_observed": False,
                "completion_confirmed": False,
                "reason": str(state.get("message", "状態ファイルが壊れています。")) or "状態ファイルが壊れています。",
            }
        requested_action = str(state.get("requested_action", "") or "").strip().lower()
        requested_session_id = str(state.get("requested_session_id", "") or "")
        requested_queue_id = str(state.get("requested_queue_id", "") or "")
        current_campaign_id = str(campaign.get("campaign_id", "") or "")
        if requested_action in {"mapping_confirmed", "submitted_next", "hold", "stop"}:
            if requested_session_id and requested_session_id != session_id:
                clear_assisted_session_action()
                continue
            if requested_queue_id and requested_queue_id != current_campaign_id:
                clear_assisted_session_action()
                continue
            clear_assisted_session_action()
            return requested_action, {
                "state": "MAPPING_CONFIRMED" if requested_action == "mapping_confirmed" else ("COMPLETED" if requested_action == "submitted_next" else ("AWAITING_USER_NEXT" if requested_action == "hold" else "STOPPED")),
                "manual_submit_observed": requested_action == "submitted_next",
                "completion_confirmed": requested_action == "submitted_next",
                "reason": f"user requested {requested_action}",
                "hold_reason": str(state.get("requested_hold_reason", "") or ""),
                "operation_id": str(state.get("requested_operation_id", "") or ""),
            }

        snapshot = classify_completion_snapshot(
            getattr(page, "url", ""),
            _page_title(page),
            _page_body_text(page),
            baseline_url=baseline_url,
        )
        if snapshot.get("completion_confirmed"):
            snapshot = dict(snapshot)
            snapshot["state"] = "AWAITING_USER_NEXT"
            snapshot["completion_confirmed"] = False
            snapshot["reason"] = "完了表示を検知しました。本人が「送信済み・次へ」を押すまで待機します。"
        mapping_review_active = str(state.get("workflow_state", "") or "").upper() == "MAPPING_REVIEW_REQUIRED"
        state.update(
            current_index=index,
            total=total,
            current_campaign_id=current_campaign_id,
            current_campaign_name=str(campaign.get("campaign_name", "") or ""),
            current_queue_status=str(campaign.get("queue_status", "") or ""),
            current_url=str(getattr(page, "url", "") or ""),
            current_title=_page_title(page),
            message=snapshot.get("reason", ""),
            status=snapshot.get("state", "AWAITING_USER_SUBMIT"),
            status_label=SESSION_STATUS_LABELS.get(str(snapshot.get("state", "AWAITING_USER_SUBMIT")), str(snapshot.get("state", ""))),
            submitted_count_auto=0,
            last_reason=snapshot.get("reason", ""),
            final_status=str(snapshot.get("state", "AWAITING_USER_SUBMIT") or "AWAITING_USER_SUBMIT"),
        )
        if mapping_review_active:
            state.update(
                status="AWAITING_USER_SUBMIT",
                status_label=SESSION_STATUS_LABELS["AWAITING_USER_SUBMIT"],
                current_step="mapping_review",
                message="項目対応を確認してください。確認後に入力を実行します。",
                last_action="MAPPING_REVIEW_REQUIRED",
                last_reason="MAPPING_REVIEW_REQUIRED",
                final_status="MAPPING_REVIEW_REQUIRED",
            )
        save_assisted_session_state(state)
        time.sleep(max(float(poll_interval_sec), 0.0))


def _wait_for_extension_verified_result(
    *,
    campaign: Mapping[str, object],
    poll_interval_sec: float,
    timeout_sec: float = 1800.0,
) -> tuple[dict[str, object], str, dict[str, object]]:
    """Wait for the extension's PII-free verified-fill event."""
    deadline = time.monotonic() + max(float(timeout_sec), 1.0)
    while time.monotonic() < deadline:
        state = load_assisted_session_state()
        requested_action = str(state.get("requested_action", "") or "").strip().lower()
        if requested_action in {"stop", "hold"}:
            clear_assisted_session_action()
            return {}, requested_action, {
                "reason": f"user requested {requested_action}",
                "hold_reason": str(state.get("requested_hold_reason", "") or ""),
                "operation_id": str(state.get("requested_operation_id", "") or ""),
            }
        workflow_state = str(state.get("workflow_state", "") or "").upper()
        if workflow_state == "HUMAN_ACTION_REQUIRED":
            filled_count = int(state.get("filled_field_count", 0) or 0)
            return (
                {
                    "record": {
                        "campaign_id": str(campaign.get("campaign_id", "") or ""),
                        "status": "AWAITING_USER_SUBMIT",
                        "submitted_count_auto": 0,
                        "mapping_review_required": False,
                        "filled_field_count": filled_count,
                        "unresolved_required_fields_count": 0,
                        "review_items": [],
                        "needs_review_reasons": [],
                    },
                    "filled_fields": ["verified"] * filled_count,
                    "missing_fields": [],
                    "pre_submit_check": {"status": "AWAITING_USER_SUBMIT"},
                },
                "",
                {},
            )
        if workflow_state in {"ROLLBACK_REQUIRED", "UNSUPPORTED_FORM", "FAILED_SAFE"}:
            raise InvalidSessionTransition(f"extension_progress_failed:{workflow_state}")
        time.sleep(max(float(poll_interval_sec), 0.1))
    raise TimeoutError("extension_progress_timeout")


def run_assisted_application_session(
    *,
    status_filter: str = "APPROVED,PREPARED",
    limit: int = 12,
    browser: str = "chrome",
    keep_open: bool = False,
    poll_interval_sec: float = 0.5,
    record_trials: bool = False,
) -> dict[str, object]:
    now = _now_iso()
    existing_state = load_assisted_session_state()
    if str(existing_state.get("state_health", "")).strip().lower() == "corrupt" or str(existing_state.get("status", "")).strip().upper() == "ERROR":
        error_state = default_assisted_session_state()
        error_state.update(
            status="ERROR",
            status_label=SESSION_STATUS_LABELS["ERROR"],
            final_status="ERROR",
            state_health="corrupt",
            load_error=str(existing_state.get("load_error", "") or "状態ファイルが壊れています。"),
            message="状態ファイルが壊れています。安全のため新しい処理は開始しません。",
            session_finished_at=now,
            finished_at=now,
        )
        save_assisted_session_state(error_state)
        return {
            "status": "error",
            "processed": 0,
            "ok": 0,
            "failed": 0,
            "submitted_count_auto": 0,
            "message": error_state["message"],
            "state_path": str(ASSISTED_SESSION_STATE_JSON),
            "browser": browser,
            "actual_browser": "",
            "session_id": "",
        }

    if _is_session_active(existing_state) and _is_session_fresh(existing_state):
        return {
            "status": "running",
            "processed": int(existing_state.get("processed", 0) or 0),
            "ok": int(existing_state.get("ok", 0) or 0),
            "failed": int(existing_state.get("failed", 0) or 0),
            "submitted_count_auto": 0,
            "message": "既存のセッションが実行中です。",
            "state_path": str(ASSISTED_SESSION_STATE_JSON),
            "browser": browser,
            "actual_browser": "",
            "session_id": str(existing_state.get("session_id", "") or ""),
        }

    resume_state = existing_state if _is_session_active(existing_state) else default_assisted_session_state()
    resume_mode = _is_session_active(existing_state) and not _is_session_fresh(existing_state)
    candidates = _load_session_candidates(status_filter, limit)
    candidate_ids = _candidate_ids_from_rows(candidates)
    if resume_mode:
        session_id = str(resume_state.get("session_id", "") or uuid.uuid4().hex)
        stored_ids = [str(item).strip() for item in resume_state.get("candidate_ids", [])] if isinstance(resume_state.get("candidate_ids", []), list) else []
        if stored_ids:
            candidate_ids = stored_ids
        start_index = max(1, _safe_int(resume_state.get("next_candidate_index", 0) or resume_state.get("current_index", 0) or 1, 1))
        session_state = _normalize_state(resume_state)
        session_state.update(
            session_id=session_id,
            state_health="ok",
            load_error="",
            status="OPENING",
            status_label=SESSION_STATUS_LABELS["OPENING"],
            current_step="resuming",
            message=f"前回のセッションを再開します。{len(candidate_ids)}件の候補を確認します。",
            total=len(candidate_ids),
            candidate_ids=candidate_ids,
            next_candidate_index=start_index,
            submitted_count_auto=0,
            final_status="OPENING",
        )
    else:
        session_id = uuid.uuid4().hex
        start_index = 1
        session_state = default_assisted_session_state()
        session_state.update(
            session_id=session_id,
            state_health="ok",
            load_error="",
            status="OPENING",
            status_label=SESSION_STATUS_LABELS["OPENING"],
            current_step="select_candidates",
            message=f"{len(candidate_ids)}件の候補を順に処理します。",
            total=len(candidate_ids),
            candidate_ids=candidate_ids,
            next_candidate_index=1,
            session_started_at=now,
            started_at=now,
            submitted_count_auto=0,
            final_status="OPENING",
        )
    save_assisted_session_state(session_state)
    if not candidate_ids:
        session_state.update(
            status="COMPLETED",
            status_label=SESSION_STATUS_LABELS["COMPLETED"],
            final_status="COMPLETED",
            message="対象の候補はありません。",
            candidate_finished_at=now,
            session_finished_at=now,
            finished_at=now,
            submitted_count_auto=0,
        )
        save_assisted_session_state(session_state)
        return {
            "status": "completed",
            "processed": 0,
            "ok": 0,
            "failed": 0,
            "submitted_count_auto": 0,
            "message": "対象の候補はありません。",
            "state_path": str(ASSISTED_SESSION_STATE_JSON),
            "browser": browser,
            "actual_browser": "",
            "session_id": session_id,
        }

    processed = int(session_state.get("processed", 0) or 0)
    failed = int(session_state.get("failed", 0) or 0)
    hold_count = int(session_state.get("hold_count", 0) or 0)
    open_success = int(session_state.get("open_success", 0) or 0)
    assist_success = int(session_state.get("assist_success", 0) or 0)
    done = int(session_state.get("done", 0) or 0)
    stop_requested = False
    browser_context = None
    actual_browser = browser
    trial_store = TrialStore(REAL_SITE_TRIALS_JSONL) if record_trials else None
    trial_steps = TrialStepLogger(REAL_SITE_TRIAL_STEPS_JSONL) if record_trials else None
    candidate_ids = [candidate_id for candidate_id in candidate_ids if candidate_id]
    start_index = min(max(int(start_index), 1), len(candidate_ids))

    with sync_playwright() as playwright:
        context, page, actual_browser = open_url_in_chrome(
            playwright,
            "about:blank",
            browser,
            use_dedicated_extension=True,
            run_id=session_id,
        )
        browser_context = context
        try:
            for index in range(start_index, len(candidate_ids) + 1):
                candidate_id = candidate_ids[index - 1]
                candidate_queue_rows = {row.get("campaign_id", ""): row for row in approved_queue_rows()}
                campaign = candidate_queue_rows.get(candidate_id, {})
                if not campaign:
                    session_state.update(
                        status="STOPPED",
                        status_label=SESSION_STATUS_LABELS["STOPPED"],
                        final_status="STOPPED",
                        current_step="candidate_missing",
                        current_index=index,
                        next_candidate_index=index,
                        current_campaign_id=candidate_id,
                        current_campaign_name="",
                        current_queue_status="",
                        message="候補が途中で削除されたため安全のため停止しました。",
                        last_action="CANDIDATE_MISSING",
                        last_reason="candidate removed",
                        session_finished_at=_now_iso(),
                        finished_at=_now_iso(),
                        candidate_finished_at=_now_iso(),
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break

                campaign_id = str(campaign.get("campaign_id", "") or "").strip()
                campaign_name = str(campaign.get("campaign_name", "") or "")
                try:
                    session_state = _begin_candidate_workflow(
                        session_state,
                        session_id=session_id,
                        candidate_id=campaign_id,
                    )
                except InvalidSessionTransition:
                    session_state.update(
                        status="STOPPED",
                        status_label=SESSION_STATUS_LABELS["STOPPED"],
                        workflow_state="FAILED_SAFE",
                        final_status="STOPPED",
                        current_step="candidate_lock_failed",
                        current_campaign_id=campaign_id,
                        message="候補ロックを取得できないため安全停止しました。",
                        last_action="CANDIDATE_LOCK_FAILED",
                        last_reason="active_candidate_locked",
                        session_finished_at=_now_iso(),
                        finished_at=_now_iso(),
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break
                target_url = target_url_for_campaign(campaign)
                candidate_started_at = _now_iso()
                session_state.update(
                    status="FILLING",
                    status_label=SESSION_STATUS_LABELS["FILLING"],
                    current_step="preparing",
                    current_index=index,
                    total=len(candidate_ids),
                    next_candidate_index=index,
                    current_campaign_id=campaign_id,
                    current_campaign_name=campaign_name,
                    current_queue_status=str(campaign.get("queue_status", "") or ""),
                    current_url=str(target_url or ""),
                    current_title=campaign_name,
                    candidate_started_at=candidate_started_at,
                    candidate_finished_at="",
                    message=f"[{index}/{len(candidate_ids)}] {campaign_name or campaign_id} を入力補助しています。",
                    submitted_count_auto=0,
                    open_success=open_success,
                    assist_success=assist_success,
                    hold_count=hold_count,
                    done=done,
                    ok=done,
                    processed=processed,
                    session_id=session_id,
                    candidate_ids=candidate_ids,
                    final_status="FILLING",
                )
                save_assisted_session_state(session_state)
                if trial_steps:
                    trial_steps.log(site_id=safe_site_identifier(target_url), step="candidate_started", status="ok")

                if not _is_valid_target_url(target_url):
                    failed += 1
                    done += 1
                    mark_skipped(campaign_id)
                    try:
                        session_state = _workflow_event(
                            session_state,
                            "skipped",
                            session_id=session_id,
                            candidate_id=campaign_id,
                        )
                    except InvalidSessionTransition:
                        session_state.update(workflow_state="FAILED_SAFE")
                    candidate_finished_at = _now_iso()
                    session_state.update(
                        status="ADVANCING",
                        status_label=SESSION_STATUS_LABELS["ADVANCING"],
                        current_step="invalid_url",
                        candidate_finished_at=candidate_finished_at,
                        next_candidate_index=index + 1,
                        message="URL が空または不正のためスキップしました。",
                        last_action="INVALID_URL",
                        last_reason="URL が空または不正です。",
                        final_status="ADVANCING",
                        submitted_count_auto=0,
                        failed=failed,
                        done=done,
                        ok=done,
                    )
                    save_assisted_session_state(session_state)
                    continue

                try:
                    validate_dedicated_target_url(target_url)
                except ValueError:
                    candidate_finished_at = _now_iso()
                    session_state.update(
                        status="STOPPED",
                        status_label=SESSION_STATUS_LABELS["STOPPED"],
                        final_status="STOPPED",
                        current_step="origin_not_approved",
                        candidate_finished_at=candidate_finished_at,
                        session_finished_at=candidate_finished_at,
                        finished_at=candidate_finished_at,
                        message="このサイトは専用拡張の許可originに含まれないため停止しました。",
                        last_action="DEDICATED_ORIGIN_NOT_APPROVED",
                        last_reason="DEDICATED_ORIGIN_NOT_APPROVED",
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break

                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    extension_state = dedicated_extension_page_state(page, require_ready=True)
                    session_state["extension_id"] = str(
                        extension_state.get("extension_id", "") or ""
                    )
                    save_assisted_session_state(session_state)
                except Exception as exc:
                    candidate_finished_at = _now_iso()
                    if trial_store:
                        trial_store.append(build_trial_record(
                            site_id=safe_site_identifier(target_url),
                            url=target_url,
                            started_at=candidate_started_at,
                            finished_at=candidate_finished_at,
                            recognized_fields=0,
                            filled_fields=0,
                            unfilled_fields=0,
                            manual_interventions=1,
                            final_step="NAVIGATION_FAILED",
                            error_category=ErrorCategory.NAVIGATION_TIMEOUT.value if "timeout" in str(exc).casefold() else ErrorCategory.UNKNOWN.value,
                            recoverable=False,
                            unintended_submission=False,
                            last_successful_step="candidate_selected",
                            manual_action_fields=["ページを手動で開く"],
                        ))
                    session_state.update(
                        status="STOPPED",
                        status_label=SESSION_STATUS_LABELS["STOPPED"],
                        final_status="STOPPED",
                        current_step="navigation_failed",
                        candidate_finished_at=candidate_finished_at,
                        session_finished_at=candidate_finished_at,
                        message="ページを開けませんでした。再試行、手動継続、中止を選んでください。",
                        last_action="NAVIGATION_FAILED",
                        last_reason="NAVIGATION_TIMEOUT" if "timeout" in str(exc).casefold() else "UNKNOWN",
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break
                open_success += 1
                session_state = _workflow_event(
                    session_state,
                    "page_opened",
                    session_id=session_id,
                    candidate_id=campaign_id,
                )
                session_state.update(
                    current_step="filling",
                    open_success=open_success,
                    current_url=str(getattr(page, "url", "") or target_url),
                    current_title=_page_title(page),
                    message=f"[{index}/{len(candidate_ids)}] {campaign_name or campaign_id} を入力補助しています。",
                    session_id=session_id,
                    candidate_ids=candidate_ids,
                    final_status="FILLING",
                )
                save_assisted_session_state(session_state)

                try:
                    result = _run_session_engine(
                        AutoApplyEngine("dry_run"),
                        page,
                        campaign,
                        {},
                        mapping_confirmed=False,
                    )
                except Exception as exc:
                    candidate_finished_at = _now_iso()
                    if trial_store:
                        trial_store.append(build_trial_record(
                            site_id=safe_site_identifier(str(getattr(page, "url", "") or target_url)),
                            url=str(getattr(page, "url", "") or target_url),
                            started_at=candidate_started_at,
                            finished_at=candidate_finished_at,
                            recognized_fields=0,
                            filled_fields=0,
                            unfilled_fields=0,
                            manual_interventions=1,
                            final_step="ASSIST_FAILED",
                            error_category=ErrorCategory.DYNAMIC_FIELD_TIMEOUT.value if "timeout" in str(exc).casefold() else ErrorCategory.UNKNOWN.value,
                            recoverable=False,
                            unintended_submission=False,
                            last_successful_step="page_opened",
                            manual_action_fields=["フォームを手動で確認する"],
                        ))
                    session_state.update(
                        status="STOPPED",
                        status_label=SESSION_STATUS_LABELS["STOPPED"],
                        final_status="STOPPED",
                        current_step="assist_failed",
                        candidate_finished_at=candidate_finished_at,
                        session_finished_at=candidate_finished_at,
                        message="入力補助を完了できませんでした。入力済み画面を維持して停止しました。再試行、手動継続、中止を選んでください。",
                        last_action="ASSIST_FAILED",
                        last_reason="DYNAMIC_FIELD_TIMEOUT" if "timeout" in str(exc).casefold() else "UNKNOWN",
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break
                processed += 1
                assist_success += 1
                try:
                    session_state = _record_engine_workflow_state(
                        session_state,
                        result,
                        session_id=session_id,
                        candidate_id=campaign_id,
                    )
                except InvalidSessionTransition:
                    session_state.update(
                        status="STOPPED",
                        status_label=SESSION_STATUS_LABELS["STOPPED"],
                        workflow_state="FAILED_SAFE",
                        final_status="STOPPED",
                        current_step="workflow_transition_failed",
                        message="応募準備の状態遷移を検証できないため安全停止しました。",
                        last_action="WORKFLOW_TRANSITION_FAILED",
                        last_reason="invalid_session_transition",
                        session_finished_at=_now_iso(),
                        finished_at=_now_iso(),
                        candidate_finished_at=_now_iso(),
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break
                session_state = _record_state_from_result(
                    state=session_state,
                    result=result,
                    page=page,
                    campaign=campaign,
                    index=index,
                    total=len(candidate_ids),
                )
                session_state.update(
                    session_id=session_id,
                    candidate_ids=candidate_ids,
                    next_candidate_index=index,
                    candidate_started_at=candidate_started_at,
                    candidate_finished_at="",
                    session_started_at=str(session_state.get("session_started_at", "") or session_state.get("started_at", "") or now),
                    open_success=open_success,
                    assist_success=assist_success,
                    hold_count=hold_count,
                    done=done,
                    ok=done,
                    processed=processed,
                    state_health="ok",
                    load_error="",
                    final_status=str(session_state.get("status", "AWAITING_USER_SUBMIT") or "AWAITING_USER_SUBMIT"),
                )
                save_assisted_session_state(session_state)

                record = result.get("record", {}) if isinstance(result, dict) else {}
                record_status = str(record.get("status", "") or "").strip().upper()
                decision = ""
                snapshot: dict[str, object] = {}
                if bool(record.get("mapping_review_required", False)):
                    session_state.update(
                        status="AWAITING_USER_SUBMIT",
                        status_label=SESSION_STATUS_LABELS["AWAITING_USER_SUBMIT"],
                        current_step="mapping_review",
                        message="項目対応を確認してください。確認後に入力を実行します。",
                        last_action="MAPPING_REVIEW_REQUIRED",
                        last_reason="MAPPING_REVIEW_REQUIRED",
                        final_status="MAPPING_REVIEW_REQUIRED",
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    decision, snapshot = _wait_for_user_decision(
                        page=page,
                        baseline_url=str(session_state.get("current_url", "") or ""),
                        campaign=campaign,
                        session_id=session_id,
                        index=index,
                        total=len(candidate_ids),
                        poll_interval_sec=poll_interval_sec,
                    )
                    if decision == "mapping_confirmed":
                        session_state = _record_handled_action(
                            session_state,
                            action=decision,
                            queue_id=campaign_id,
                            snapshot=snapshot,
                        )
                        try:
                            session_state = _workflow_event(
                                session_state,
                                "mapping_confirmed",
                                session_id=session_id,
                                candidate_id=campaign_id,
                            )
                            session_state.update(
                                status="FILLING",
                                status_label=SESSION_STATUS_LABELS["FILLING"],
                                current_step="extension_fill",
                                final_status="MAPPING_CONFIRMED",
                                message="拡張機能で「入力を実行」を押してください。入力後検証が完了するまで待機します。",
                                submitted_count_auto=0,
                            )
                            save_assisted_session_state(session_state)
                            control_token = register_extension_control_token(session_id)
                            provision_extension_control_token(
                                browser_context,
                                session_id,
                                control_token,
                                str(session_state.get("extension_id", "") or ""),
                            )
                            result, extension_decision, extension_snapshot = (
                                _wait_for_extension_verified_result(
                                    campaign=campaign,
                                    poll_interval_sec=poll_interval_sec,
                                )
                            )
                            if extension_decision:
                                decision = extension_decision
                                snapshot = extension_snapshot
                                record = {}
                                record_status = ""
                                continue_after_extension = False
                            else:
                                continue_after_extension = True
                                session_state = load_assisted_session_state()
                            record = result.get("record", {}) if isinstance(result, dict) else {}
                            if continue_after_extension:
                                session_state = _record_state_from_result(
                                    state=session_state,
                                    result=result,
                                    page=page,
                                    campaign=campaign,
                                    index=index,
                                    total=len(candidate_ids),
                                )
                                session_state["workflow_state"] = "HUMAN_ACTION_REQUIRED"
                                save_assisted_session_state(session_state)
                                record_status = str(record.get("status", "") or "").strip().upper()
                                decision = ""
                                snapshot = {}
                        except Exception:
                            session_state.update(
                                status="STOPPED",
                                status_label=SESSION_STATUS_LABELS["STOPPED"],
                                workflow_state="FAILED_SAFE",
                                final_status="STOPPED",
                                current_step="mapping_confirmation_failed",
                                message="項目対応の確認後に安全に入力できなかったため停止しました。",
                                last_action="MAPPING_CONFIRMATION_FAILED",
                                last_reason="mapping_confirmation_not_applied",
                                candidate_finished_at=_now_iso(),
                                session_finished_at=_now_iso(),
                                finished_at=_now_iso(),
                                submitted_count_auto=0,
                            )
                            save_assisted_session_state(session_state)
                            failed += 1
                            stop_requested = True
                            break

                if trial_store:
                    trial_finished_at = _now_iso()
                    trial = trial_from_engine_result(
                        campaign=campaign,
                        url=str(getattr(page, "url", "") or target_url),
                        result=result,
                        started_at=candidate_started_at,
                        finished_at=trial_finished_at,
                    )
                    trial_store.append(trial)
                    if trial_steps:
                        trial_steps.log(
                            site_id=trial.site_id,
                            step="human_handoff",
                            status=trial.grade,
                            details={"error_category": trial.error_category, "final_step": trial.final_step},
                        )
                if record_status == "SKIPPED":
                    reason = str(record.get("skip_reason", "") or record.get("needs_review_reasons", "") or "SKIPPED")
                    try:
                        transitioned_state = session_state
                        if str(session_state.get("workflow_state", "") or "").upper() != "SKIPPED":
                            transitioned_state = _workflow_event(
                                session_state,
                                "skipped",
                                session_id=session_id,
                                candidate_id=campaign_id,
                            )
                    except InvalidSessionTransition:
                        session_state.update(
                            status="STOPPED",
                            workflow_state="FAILED_SAFE",
                            final_status="STOPPED",
                            last_reason="invalid_session_transition",
                            submitted_count_auto=0,
                        )
                        save_assisted_session_state(session_state)
                        failed += 1
                        stop_requested = True
                        break
                    if not mark_skipped(campaign_id):
                        session_state.update(
                            status="STOPPED",
                            workflow_state="FAILED_SAFE",
                            final_status="STOPPED",
                            last_reason="candidate_update_failed",
                            submitted_count_auto=0,
                        )
                        save_assisted_session_state(session_state)
                        failed += 1
                        stop_requested = True
                        break
                    session_state = transitioned_state
                    failed += 1
                    done += 1
                    candidate_finished_at = _now_iso()
                    session_state.update(
                        status="ADVANCING",
                        status_label=SESSION_STATUS_LABELS["ADVANCING"],
                        current_step="skipped",
                        candidate_finished_at=candidate_finished_at,
                        next_candidate_index=index + 1,
                        message="入力補助結果がスキップだったため次へ進みます。",
                        last_action="SKIPPED",
                        last_reason=reason,
                        final_status="ADVANCING",
                        submitted_count_auto=0,
                        failed=failed,
                        done=done,
                        ok=done,
                    )
                    save_assisted_session_state(session_state)
                    continue

                if not decision:
                    decision, snapshot = _wait_for_user_decision(
                        page=page,
                        baseline_url=str(session_state.get("current_url", "") or ""),
                        campaign=campaign,
                        session_id=session_id,
                        index=index,
                        total=len(candidate_ids),
                        poll_interval_sec=poll_interval_sec,
                    )
                candidate_finished_at = _now_iso()
                session_state = _record_handled_action(
                    session_state,
                    action=decision,
                    queue_id=campaign_id,
                    snapshot=snapshot,
                )

                if decision == "stop":
                    stop_requested = True
                    try:
                        session_state = _workflow_event(
                            session_state,
                            "failed_safe",
                            session_id=session_id,
                            candidate_id=campaign_id,
                        )
                    except InvalidSessionTransition:
                        session_state.update(workflow_state="FAILED_SAFE")
                    session_state.update(
                        status="STOPPED",
                        status_label=SESSION_STATUS_LABELS["STOPPED"],
                        final_status="STOPPED",
                        message="ユーザーが停止しました。",
                        current_step="stopped",
                        last_action="STOP",
                        last_reason=str(snapshot.get("reason", "") or ""),
                        hold_reason=str(snapshot.get("hold_reason", "") or ""),
                        candidate_finished_at=candidate_finished_at,
                        session_finished_at=candidate_finished_at,
                        finished_at=candidate_finished_at,
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    break

                if decision == "hold":
                    try:
                        transitioned_state = _workflow_event(
                            session_state,
                            "held",
                            session_id=session_id,
                            candidate_id=campaign_id,
                        )
                    except InvalidSessionTransition:
                        session_state.update(
                            status="STOPPED",
                            workflow_state="FAILED_SAFE",
                            final_status="STOPPED",
                            last_reason="invalid_session_transition",
                            submitted_count_auto=0,
                        )
                        save_assisted_session_state(session_state)
                        failed += 1
                        stop_requested = True
                        break
                    if not mark_hold(campaign_id):
                        session_state.update(
                            status="STOPPED",
                            workflow_state="FAILED_SAFE",
                            final_status="STOPPED",
                            last_reason="candidate_update_failed",
                            submitted_count_auto=0,
                        )
                        save_assisted_session_state(session_state)
                        failed += 1
                        stop_requested = True
                        break
                    session_state = transitioned_state
                    hold_count += 1
                    done += 1
                    session_state.update(
                        status="ADVANCING",
                        status_label=SESSION_STATUS_LABELS["ADVANCING"],
                        final_status="ADVANCING",
                        message=f"[{index}/{len(candidate_ids)}] 保留しました。次へ進みます。",
                        current_step="held",
                        last_action="HOLD",
                        last_reason=str(snapshot.get("reason", "") or ""),
                        hold_reason=str(snapshot.get("hold_reason", "") or ""),
                        candidate_finished_at=candidate_finished_at,
                        next_candidate_index=index + 1,
                        hold_count=hold_count,
                        done=done,
                        ok=done,
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    continue

                try:
                    transitioned_state = _workflow_event(
                        session_state,
                        "user_reported_submitted",
                        session_id=session_id,
                        candidate_id=campaign_id,
                    )
                    transitioned_state = _workflow_event(
                        transitioned_state,
                        "completed",
                        session_id=session_id,
                        candidate_id=campaign_id,
                    )
                except InvalidSessionTransition:
                    session_state.update(
                        status="STOPPED",
                        workflow_state="FAILED_SAFE",
                        final_status="STOPPED",
                        last_reason="invalid_session_transition",
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break
                if not mark_manual_submitted(campaign_id):
                    session_state.update(
                        status="STOPPED",
                        workflow_state="FAILED_SAFE",
                        final_status="STOPPED",
                        last_reason="candidate_update_failed",
                        submitted_count_auto=0,
                    )
                    save_assisted_session_state(session_state)
                    failed += 1
                    stop_requested = True
                    break
                session_state = transitioned_state
                done += 1
                session_state.update(
                    status="ADVANCING",
                    status_label=SESSION_STATUS_LABELS["ADVANCING"],
                    final_status="ADVANCING",
                    message=f"[{index}/{len(candidate_ids)}] 手動送信を記録して次へ進みます。",
                    current_step="submitted_next",
                    last_action="SUBMITTED_NEXT",
                    last_reason=str(snapshot.get("reason", "") or ""),
                    candidate_finished_at=candidate_finished_at,
                    next_candidate_index=index + 1,
                    done=done,
                    ok=done,
                    submitted_count_auto=0,
                )
                save_assisted_session_state(session_state)

            if not stop_requested:
                finished_at = _now_iso()
                session_state.update(
                    status="COMPLETED",
                    status_label=SESSION_STATUS_LABELS["COMPLETED"],
                    final_status="COMPLETED",
                    message="セッションが完了しました。",
                    current_step="completed",
                    session_finished_at=finished_at,
                    finished_at=finished_at,
                    candidate_finished_at=str(session_state.get("candidate_finished_at", "") or finished_at),
                    next_candidate_index=len(candidate_ids) + 1,
                    submitted_count_auto=0,
                )
                save_assisted_session_state(session_state)
        finally:
            clear_extension_control_token(session_id)
            stop_extension_bridge()
            if browser_context:
                try:
                    clear_browser_extension_control_token(browser_context)
                except Exception:
                    pass
            if browser_context:
                close_browser_safely(browser_context)

    return {
        "status": str(session_state.get("status", "COMPLETED") or "COMPLETED").lower(),
        "processed": processed,
        "ok": done,
        "failed": failed,
        "submitted_count_auto": 0,
        "current_campaign_id": session_state.get("current_campaign_id", ""),
        "current_campaign_name": session_state.get("current_campaign_name", ""),
        "message": session_state.get("message", ""),
        "state_path": str(ASSISTED_SESSION_STATE_JSON),
        "browser": browser,
        "actual_browser": actual_browser,
        "session_id": session_id,
        "open_success": open_success,
        "assist_success": assist_success,
        "hold_count": hold_count,
        "final_status": session_state.get("final_status", ""),
    }
