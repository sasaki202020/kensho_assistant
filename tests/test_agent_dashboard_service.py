from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.agent_dashboard.service import (
    get_agent_by_role,
    get_agent_summary,
    list_agents,
    list_error_agents,
    list_warning_agents,
)


def test_agent_dashboard_service_summary_counts(tmp_path: Path) -> None:
    path = tmp_path / "agent_status.json"
    path.write_text(
        json.dumps(
            {
                "agents": [
                    {"role": "queue_manager", "display_name": "キュー整理担当", "status": "running", "progress_percent": 20, "total_tasks": 5, "completed_tasks": 1, "warning_count": 0, "error_count": 0, "last_message": "整理中", "updated_at": "2026-05-24T15:20:00+09:00"},
                    {"role": "campaign_researcher", "display_name": "応募条件調査担当", "status": "warning", "progress_percent": 40, "total_tasks": 5, "completed_tasks": 2, "warning_count": 1, "error_count": 0, "last_message": "要確認", "updated_at": "2026-05-24T15:20:00+09:00"},
                    {"role": "form_diagnostician", "display_name": "フォーム診断担当", "status": "completed", "progress_percent": 100, "total_tasks": 6, "completed_tasks": 6, "warning_count": 0, "error_count": 0, "last_message": "完了", "updated_at": "2026-05-24T15:20:00+09:00"},
                    {"role": "safety_reviewer", "display_name": "安全確認担当", "status": "error", "progress_percent": 80, "total_tasks": 2, "completed_tasks": 1, "warning_count": 0, "error_count": 1, "last_message": "確認エラー", "updated_at": "2026-05-24T15:20:00+09:00", "safety_checks": {"auto_submit": False, "profile_enc_read": False, "pii_logged": False, "x_action_automated": False}},
                ]
            }
        ),
        encoding="utf-8",
    )
    summary = get_agent_summary(path)
    assert summary["total_agents"] == 4
    assert summary["running_count"] == 1
    assert summary["warning_count"] == 1
    assert summary["error_count"] == 1
    assert summary["completed_count"] == 1
    assert get_agent_by_role("safety_reviewer", path)["safety_checks"]["pii_logged"] is False
    assert len(list_warning_agents(path)) == 1
    assert len(list_error_agents(path)) == 1


def test_agent_dashboard_service_defaults_do_not_use_sample(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    agents = list_agents(path)
    assert len(agents) == 6
    assert agents[0]["status"] == "idle"
    assert "safety_reviewer" in {agent["role"] for agent in agents}
