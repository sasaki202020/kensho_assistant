from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.agent_control import job_store
from kensho_assistant.app.agent_control.controller import run_agent_job


def test_agent_control_never_sets_submit_attempted(tmp_path: Path, monkeypatch) -> None:
    jobs_path = tmp_path / "jobs.jsonl"
    status_path = tmp_path / "agent_status.json"
    events_path = tmp_path / "control_events.jsonl"
    monkeypatch.setattr(job_store, "AGENT_CONTROL_JOBS_JSONL", jobs_path)
    monkeypatch.setattr(job_store, "AGENT_CONTROL_STATUS_JSON", status_path)
    monkeypatch.setattr(job_store, "AGENT_CONTROL_EVENTS_JSONL", events_path)
    monkeypatch.setattr("kensho_assistant.app.agent_control.controller.AGENT_CONTROL_STATUS_JSON", status_path)
    monkeypatch.setattr("kensho_assistant.app.profile_manager.load_profile", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("profile.enc should not be read")))

    job = run_agent_job("ReportAgent", action="report", target_url="https://example.com/report")
    assert job["submit_attempted"] is False
    assert job["status"] == "done"
    records = [json.loads(line) for line in jobs_path.read_text(encoding="utf-8").splitlines()]
    assert records
    assert all(record["submit_attempted"] is False for record in records)
    snapshot = json.loads(status_path.read_text(encoding="utf-8"))
    assert snapshot["submitted_count_auto"] == 0
    assert snapshot["safe_to_submit"] is False
    assert "profile.enc" not in jobs_path.read_text(encoding="utf-8")
