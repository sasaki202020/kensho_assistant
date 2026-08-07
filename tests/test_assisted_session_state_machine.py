from __future__ import annotations

import pytest

from kensho_assistant.app.session_state_machine import (
    InvalidSessionTransition,
    SessionStateMachine,
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
