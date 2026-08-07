from __future__ import annotations

from kensho_assistant.app.agent_control.schema import AGENT_CONTROL_AGENT_DEFINITIONS, AGENT_CONTROL_STATUSES, canonical_agent_control_job, default_agent_control_jobs


def test_agent_control_schema_defaults_are_safe() -> None:
    jobs = default_agent_control_jobs()
    assert len(jobs) == 6
    assert all(job["submit_attempted"] is False for job in jobs)
    assert all(job["status"] == "pending" for job in jobs)
    assert {"ResearchAgent", "QueueAgent", "FormCheckAgent", "SafetyAgent", "ReportAgent", "HumanReviewAgent"} <= {agent["agent_name"] for agent in AGENT_CONTROL_AGENT_DEFINITIONS}
    assert AGENT_CONTROL_STATUSES == {"pending", "running", "needs_review", "blocked", "done", "failed", "cancelled"}


def test_agent_control_schema_invalid_status_becomes_failed() -> None:
    job = canonical_agent_control_job({"job_id": "x", "agent_name": "ResearchAgent", "status": "unknown", "submit_attempted": True})
    assert job["status"] == "failed"
    assert job["submit_attempted"] is True
