from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.agent_control import job_store
from kensho_assistant.app.agent_control.controller import cancel_job, complete_job, create_job, get_agent_control_status, start_job


def _patch_store(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    jobs = tmp_path / "jobs.jsonl"
    status = tmp_path / "agent_status.json"
    events = tmp_path / "control_events.jsonl"
    monkeypatch.setattr(job_store, "AGENT_CONTROL_JOBS_JSONL", jobs)
    monkeypatch.setattr(job_store, "AGENT_CONTROL_STATUS_JSON", status)
    monkeypatch.setattr(job_store, "AGENT_CONTROL_EVENTS_JSONL", events)
    monkeypatch.setattr("kensho_assistant.app.agent_control.controller.AGENT_CONTROL_STATUS_JSON", status)
    return jobs, status, events


def test_agent_control_job_transitions_and_snapshot(tmp_path: Path, monkeypatch) -> None:
    jobs_path, status_path, events_path = _patch_store(monkeypatch, tmp_path)
    job = create_job("ResearchAgent", "collect_candidates", "https://example.com/campaign")
    assert job["status"] == "pending"
    assert job["submit_attempted"] is False
    running = start_job(job["job_id"])
    assert running["status"] == "running"
    done = complete_job(job["job_id"], status="done", result_summary="完了", safety_memo="dry-run")
    assert done["status"] == "done"
    assert done["submit_attempted"] is False
    assert jobs_path.exists()
    assert events_path.exists()
    lines = jobs_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    latest = json.loads(lines[-1])
    assert latest["status"] == "done"
    assert latest["submit_attempted"] is False
    snapshot = get_agent_control_status()
    assert snapshot["submitted_count_auto"] == 0
    assert snapshot["safe_to_submit"] is False
    assert snapshot["summary"]["done"] >= 1
    assert status_path.exists()


def test_agent_control_cancel_and_status_refresh(tmp_path: Path, monkeypatch) -> None:
    _patch_store(monkeypatch, tmp_path)
    job = create_job("QueueAgent", "queue_register", "https://example.com/queue")
    cancelled = cancel_job(job_id=job["job_id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["submit_attempted"] is False
    snapshot = get_agent_control_status()
    assert snapshot["summary"]["cancelled_count"] >= 1
