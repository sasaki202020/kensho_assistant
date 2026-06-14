from __future__ import annotations

from daily_run import should_skip_phase


def test_should_skip_odds_before_schedule() -> None:
    skip, reason = should_skip_phase(
        "odds",
        {
            "next_action": "wait_for_odds_refresh",
            "next_action_reason": "Official odds refresh is scheduled after 18:00.",
        },
    )

    assert skip is True
    assert "18:00" in reason


def test_should_allow_odds_when_due() -> None:
    skip, reason = should_skip_phase(
        "odds",
        {
            "next_action": "run_odds_refresh",
            "next_action_reason": "Rows miss official odds.",
        },
    )

    assert skip is False
    assert reason == ""


def test_should_skip_odds_after_settlement_exists() -> None:
    skip, reason = should_skip_phase(
        "odds",
        {
            "next_action": "paper_trade_only",
            "settlement": {"exists": True},
        },
    )

    assert skip is True
    assert "Settlement already exists" in reason


def test_should_skip_odds_when_night_settlement_is_due() -> None:
    skip, reason = should_skip_phase(
        "odds",
        {
            "next_action": "run_night_after_results",
            "next_action_reason": "Settlement window has arrived.",
        },
    )

    assert skip is True
    assert "run night" in reason


def test_ignore_schedule_does_not_bypass_night_priority_for_odds() -> None:
    skip, reason = should_skip_phase(
        "odds",
        {
            "next_action": "run_night_after_results",
            "next_action_reason": "Settlement window has arrived.",
        },
        ignore_schedule=True,
    )

    assert skip is True
    assert "run night" in reason


def test_should_skip_night_until_settlement_window() -> None:
    skip, reason = should_skip_phase(
        "night",
        {
            "next_action": "wait_for_night_settlement",
            "next_action_reason": "Night settlement is scheduled after 21:30.",
        },
    )

    assert skip is True
    assert "21:30" in reason


def test_should_allow_night_when_due_even_if_odds_are_missing() -> None:
    skip, reason = should_skip_phase(
        "night",
        {
            "next_action": "run_night_after_results",
            "next_action_reason": "Settlement window has arrived; run night even though rows still miss official win odds.",
        },
    )

    assert skip is False
    assert reason == ""


def test_ignore_schedule_bypasses_skip() -> None:
    skip, reason = should_skip_phase(
        "night",
        {
            "next_action": "wait_for_night_settlement",
            "next_action_reason": "Night settlement is scheduled after 21:30.",
        },
        ignore_schedule=True,
    )

    assert skip is False
    assert reason == ""


def test_ignore_schedule_does_not_bypass_missing_morning_predictions() -> None:
    skip, reason = should_skip_phase(
        "night",
        {
            "next_action": "run_morning",
            "next_action_reason": "Morning predictions are missing.",
        },
        ignore_schedule=True,
    )

    assert skip is True
    assert "Morning predictions" in reason
