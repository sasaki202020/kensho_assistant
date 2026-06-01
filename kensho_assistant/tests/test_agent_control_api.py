from __future__ import annotations

from fastapi.testclient import TestClient

from kensho_assistant.web.app import create_app


def test_agent_control_api_endpoints_return_json(monkeypatch) -> None:
    app = create_app()
    monkeypatch.setattr("kensho_assistant.web.app.get_agent_control_status", lambda: {"summary": {"pending_count": 1}, "submitted_count_auto": 0, "safe_to_submit": False})
    monkeypatch.setattr("kensho_assistant.web.app.get_agent_control_report", lambda: {"counts": {"pending": 1}, "release_allowed": False, "submitted_count_auto": 0, "safe_to_submit": False})
    monkeypatch.setattr("kensho_assistant.web.app.list_agent_control_jobs", lambda limit=50: [{"job_id": "job-1", "agent_name": "ResearchAgent", "status": "pending", "created_at": "2026-05-24T00:00:00+09:00", "target_url": "", "safety_memo": "dry-run", "result_summary": "待機中"}])
    monkeypatch.setattr("kensho_assistant.web.app.list_agent_control_agents", lambda: [{"agent_name": "ResearchAgent", "display_name": "ResearchAgent", "role": "懸賞URL候補の収集・整理", "purpose": "候補URLを安全に整理する", "status": "idle", "latest_job_id": "", "last_run_at": "", "latest_result": "未実行", "latest_safety_memo": "", "blocked_count": 0, "failed_count": 0}])
    monkeypatch.setattr("kensho_assistant.web.app.run_agent_job", lambda agent_name, action="", target_url="": {"job_id": "job-2", "status": "done", "result_summary": "ok", "submit_attempted": False})
    monkeypatch.setattr("kensho_assistant.web.app.cancel_agent_control_job", lambda job_id=None, agent_name="": {"job_id": job_id or "job-1", "status": "cancelled", "result_summary": "cancelled", "submit_attempted": False})

    with TestClient(app) as client:
        status = client.get("/api/agent-control/status")
        jobs = client.get("/api/agent-control/jobs")
        report = client.get("/api/agent-control/report")
        run = client.post("/api/agent-control/run", data={"agent_name": "ResearchAgent", "action": "collect_candidates", "target_url": "https://example.com"})
        cancel = client.post("/api/agent-control/cancel", data={"agent_name": "ResearchAgent", "job_id": "job-1"})

    assert status.status_code == 200
    assert status.json()["submitted_count_auto"] == 0
    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["agent_name"] == "ResearchAgent"
    assert report.status_code == 200
    assert report.json()["release_allowed"] is False
    assert run.status_code == 200
    assert run.json()["status"] == "done"
    assert run.json()["submitted_count_auto"] == 0
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
