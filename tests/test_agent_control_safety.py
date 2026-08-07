from __future__ import annotations

import json

from kensho_assistant.app.agent_control.safety import evaluate_control_job


def test_agent_control_safety_blocks_dangerous_actions() -> None:
    result = evaluate_control_job("SafetyAgent", "submit_now", "javascript:alert(1)")
    assert result["status"] == "blocked"
    assert result["pii_detected"] is False
    assert result["submit_attempted"] is False


def test_agent_control_safety_needs_review_for_human_review() -> None:
    result = evaluate_control_job("HumanReviewAgent", "human_review", "https://example.com/campaign")
    assert result["status"] == "needs_review"
    assert result["human_review_required"] is True
    assert result["submit_attempted"] is False


def test_agent_control_safety_redacts_pii_like_input() -> None:
    result = evaluate_control_job("ResearchAgent", "collect_candidates", "https://example.com/?email=test@example.com&phone=090-1234-5678")
    flat = json.dumps(result, ensure_ascii=False)
    assert result["status"] == "blocked"
    assert result["pii_detected"] is True
    assert "test@example.com" not in flat
    assert "090-1234-5678" not in flat
    assert "submit_attempted" in result and result["submit_attempted"] is False
