from __future__ import annotations

import pytest

from kensho_assistant.app.session_state_machine import (
    InvalidSessionTransition,
    SessionStateMachine,
)
from kensho_assistant.app.assisted_session import (
    _begin_candidate_workflow,
    load_assisted_session_state,
    mark_extension_coordination_failed,
    record_extension_progress,
    save_assisted_session_state,
)


@pytest.mark.parametrize("workflow_state", ["HUMAN_ACTION_REQUIRED", "ROLLBACK_REQUIRED"])
def test_coordination_failure_downgrades_submission_wait_to_failed_safe(
    monkeypatch, tmp_path, workflow_state
) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.revoke_extension_capabilities",
        lambda _session: 1,
    )
    save_assisted_session_state(
        {
            "workflow_state": workflow_state,
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
            "candidate_id": "candidate-1",
            "current_url": "https://example.invalid/apply",
            "form_fingerprint": "fingerprint-1",
            "submitted_count_auto": 0,
        }
    )
    state = mark_extension_coordination_failed(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.invalid",
        fingerprint="fingerprint-1",
    )
    assert state["workflow_state"] == "FAILED_SAFE"
    assert state["candidate_marked_submitted"] is False
    assert state["submitted_count_auto"] == 0
    assert load_assisted_session_state()["workflow_state"] == "FAILED_SAFE"


@pytest.fixture(autouse=True)
def _accept_fixture_progress_capability(monkeypatch):
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session._EXTENSION_BRIDGE.validate_progress",
        lambda **_kwargs: None,
    )


def test_state_machine_requires_human_action_before_completion() -> None:
    machine = SessionStateMachine()
    state = {"workflow_state": "IDLE", "active_candidate_id": ""}

    state = machine.lock_candidate(state, "candidate-1")
    for event, expected in (
        ("page_opened", "PAGE_OPENED"),
        ("submit_guard_ready", "SUBMIT_GUARD_READY"),
        ("form_analyzed", "FORM_ANALYZED"),
        ("mapping_confirmed", "MAPPING_CONFIRMED"),
        ("filled", "FILLED"),
        ("post_fill_verified", "POST_FILL_VERIFIED"),
        ("human_action_required", "HUMAN_ACTION_REQUIRED"),
        ("user_reported_submitted", "USER_REPORTED_SUBMITTED"),
        ("completed", "COMPLETED"),
    ):
        state = machine.transition(
            state,
            event,
            session_id="session-1",
            candidate_id="candidate-1",
        )
        assert state["workflow_state"] == expected

    assert state["active_candidate_id"] == ""


def test_second_candidate_cannot_be_locked_while_one_is_active() -> None:
    machine = SessionStateMachine()
    state = machine.lock_candidate(
        {"workflow_state": "IDLE", "active_candidate_id": ""},
        "candidate-1",
    )

    with pytest.raises(InvalidSessionTransition, match="active_candidate"):
        machine.lock_candidate(state, "candidate-2")


def test_invalid_transition_is_rejected() -> None:
    machine = SessionStateMachine()

    with pytest.raises(InvalidSessionTransition):
        machine.transition(
            {"workflow_state": "IDLE", "active_candidate_id": ""},
            "filled",
            session_id="session-1",
            candidate_id="candidate-1",
        )


def test_same_candidate_lock_is_idempotent_and_release_is_bound() -> None:
    machine = SessionStateMachine()
    state = machine.lock_candidate(
        {"workflow_state": "IDLE", "active_candidate_id": ""},
        "candidate-1",
    )
    assert machine.lock_candidate(state, "candidate-1") == state
    released = machine.release_candidate(state, "candidate-1")
    assert released["active_candidate_id"] == ""
    assert released["candidate_id"] == ""


def test_mapping_review_is_a_hard_gate_before_fill() -> None:
    machine = SessionStateMachine()
    state = machine.lock_candidate(
        {"workflow_state": "IDLE", "active_candidate_id": ""},
        "candidate-1",
    )
    for event in ("page_opened", "submit_guard_ready", "form_analyzed"):
        state = machine.transition(state, event, session_id="session-1", candidate_id="candidate-1")
    state = machine.transition(
        state,
        "mapping_review_required",
        session_id="session-1",
        candidate_id="candidate-1",
    )
    assert state["workflow_state"] == "MAPPING_REVIEW_REQUIRED"
    with pytest.raises(InvalidSessionTransition):
        machine.transition(state, "filled", session_id="session-1", candidate_id="candidate-1")
    state = machine.transition(
        state,
        "mapping_confirmed",
        session_id="session-1",
        candidate_id="candidate-1",
    )
    assert state["workflow_state"] == "MAPPING_CONFIRMED"


def test_skip_after_form_analysis_is_recorded_without_fill() -> None:
    machine = SessionStateMachine()
    state = machine.lock_candidate(
        {"workflow_state": "IDLE", "active_candidate_id": ""},
        "candidate-1",
    )
    for event in ("page_opened", "submit_guard_ready", "form_analyzed"):
        state = machine.transition(state, event, session_id="session-1", candidate_id="candidate-1")
    state = machine.transition(state, "skipped", session_id="session-1", candidate_id="candidate-1")
    assert state["workflow_state"] == "SKIPPED"


def test_terminal_candidate_is_released_once_before_next_lock() -> None:
    state = {
        "workflow_state": "HELD",
        "active_candidate_id": "candidate-1",
        "candidate_id": "candidate-1",
        "session_id": "session-1",
    }

    next_state = _begin_candidate_workflow(
        state,
        session_id="session-1",
        candidate_id="candidate-2",
    )

    assert next_state["workflow_state"] == "CANDIDATE_LOCKED"
    assert next_state["active_candidate_id"] == "candidate-2"


def test_extension_progress_advances_only_verified_fill(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    save_assisted_session_state(
        {
            "workflow_state": "MAPPING_CONFIRMED",
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
            "candidate_id": "candidate-1",
            "current_url": "https://example.invalid/apply",
            "submitted_count_auto": 0,
        }
    )

    state = record_extension_progress(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.invalid",
        fingerprint="form-fingerprint-1",
        event="post_fill_verified",
        operation_id="operation-1",
        details={"filled_count": 4, "unrelated_changed_count": 0},
    )

    assert state["workflow_state"] == "HUMAN_ACTION_REQUIRED"
    assert state["form_fingerprint"] == "form-fingerprint-1"
    assert state["filled_field_count"] == 4
    assert state["submitted_count_auto"] == 0


def test_extension_progress_rejects_pii_and_replay(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    save_assisted_session_state(
        {
            "workflow_state": "MAPPING_CONFIRMED",
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
            "candidate_id": "candidate-1",
            "current_url": "https://example.invalid/apply",
            "submitted_count_auto": 0,
        }
    )

    with pytest.raises(ValueError, match="invalid_extension_progress"):
        record_extension_progress(
            session_id="session-1",
            candidate_id="candidate-1",
            origin="https://example.invalid",
            fingerprint="form-fingerprint-1",
            event="post_fill_verified",
            operation_id="operation-1",
            details={"email": "fictional@example.invalid"},
        )

    first = record_extension_progress(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.invalid",
        fingerprint="form-fingerprint-1",
        event="post_fill_verified",
        operation_id="operation-1",
        details={"filled_count": 1, "unrelated_changed_count": 0},
    )
    replay = record_extension_progress(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.invalid",
        fingerprint="form-fingerprint-1",
        event="post_fill_verified",
        operation_id="operation-1",
        details={"filled_count": 1, "unrelated_changed_count": 0},
    )
    assert replay["workflow_state"] == first["workflow_state"]


@pytest.mark.parametrize(
    "details",
    [
        {"filled_count": 0, "unrelated_changed_count": 0},
        {"filled_count": 1, "unrelated_changed_count": 1},
        {"filled_count": 1, "target_mismatch_count": 1},
        {"filled_count": -1, "unrelated_changed_count": 0},
    ],
)
def test_verified_fill_rejects_invalid_success_metrics(monkeypatch, tmp_path, details) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    save_assisted_session_state(
        {
            "workflow_state": "MAPPING_CONFIRMED",
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
            "candidate_id": "candidate-1",
            "current_url": "https://example.invalid/apply",
            "submitted_count_auto": 0,
        }
    )
    with pytest.raises(ValueError, match="invalid_extension_progress"):
        record_extension_progress(
            session_id="session-1",
            candidate_id="candidate-1",
            origin="https://example.invalid",
            fingerprint="form-fingerprint-1",
            event="post_fill_verified",
            operation_id="operation-invalid",
            details=details,
        )


def test_extension_rollback_invalidates_submission_ready_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    save_assisted_session_state(
        {
            "workflow_state": "HUMAN_ACTION_REQUIRED",
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
            "candidate_id": "candidate-1",
            "current_url": "https://example.invalid/apply",
            "form_fingerprint": "form-fingerprint-1",
            "submitted_count_auto": 0,
        }
    )
    state = record_extension_progress(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.invalid",
        fingerprint="form-fingerprint-1",
        event="rollback_required",
        operation_id="operation-rollback",
        details={"filled_count": 2, "rollback_complete": True},
    )
    assert state["workflow_state"] == "ROLLBACK_REQUIRED"
    assert state["submitted_count_auto"] == 0


def test_extension_rollback_completion_reaches_failed_safe(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    save_assisted_session_state(
        {
            "workflow_state": "ROLLBACK_REQUIRED",
            "session_id": "session-1",
            "active_candidate_id": "candidate-1",
            "candidate_id": "candidate-1",
            "current_url": "https://example.invalid/apply",
            "form_fingerprint": "form-fingerprint-1",
            "submitted_count_auto": 0,
        }
    )
    state = record_extension_progress(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.invalid",
        fingerprint="form-fingerprint-1",
        event="rollback_complete",
        operation_id="operation-rollback-complete",
        details={"filled_count": 2, "rollback_complete": True},
    )
    assert state["workflow_state"] == "FAILED_SAFE"
    assert state["submitted_count_auto"] == 0
