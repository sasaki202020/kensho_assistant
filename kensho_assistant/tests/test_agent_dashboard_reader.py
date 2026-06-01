from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.agent_dashboard.result_reader import load_agent_status_payload
from kensho_assistant.app.agent_dashboard.schema import AGENT_ROLE_ORDER


def test_agent_dashboard_reader_reads_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "agent_status.json"
    path.write_text(
        json.dumps(
            {
                "updated_at": "2026-05-24T15:20:00+09:00",
                "agents": [
                    {
                        "role": "queue_manager",
                        "display_name": "キュー整理担当",
                        "status": "running",
                        "progress_percent": 50,
                        "total_tasks": 2,
                        "completed_tasks": 1,
                        "warning_count": 0,
                        "error_count": 0,
                        "last_message": "整理中",
                        "updated_at": "2026-05-24T15:20:00+09:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    payload = load_agent_status_payload(path)
    assert payload["source_state"] == "json"
    assert payload["updated_at"] == "2026-05-24T15:20:00+09:00"
    assert payload["agents"][0]["role"] == "queue_manager"
    assert payload["agents"][0]["status"] == "running"


def test_agent_dashboard_reader_missing_file_returns_default(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    payload = load_agent_status_payload(path)
    assert payload["source_state"] == "missing"
    assert [agent["role"] for agent in payload["agents"]] == AGENT_ROLE_ORDER
    assert all(agent["status"] == "idle" for agent in payload["agents"])


def test_agent_dashboard_reader_broken_json_returns_default(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    payload = load_agent_status_payload(path)
    assert payload["source_state"] == "invalid"
    assert len(payload["agents"]) == len(AGENT_ROLE_ORDER)


def test_agent_dashboard_reader_invalid_status_becomes_error(tmp_path: Path) -> None:
    path = tmp_path / "agent_status.json"
    path.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "role": "safety_reviewer",
                        "display_name": "安全確認担当",
                        "status": "not-a-status",
                        "progress_percent": 100,
                        "total_tasks": 4,
                        "completed_tasks": 4,
                        "warning_count": 0,
                        "error_count": 0,
                        "last_message": "確認中",
                        "updated_at": "2026-05-24T15:20:00+09:00",
                        "safety_checks": {
                            "auto_submit": False,
                            "profile_enc_read": False,
                            "pii_logged": False,
                            "x_action_automated": False,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    payload = load_agent_status_payload(path)
    assert payload["agents"][0]["status"] == "error"
    assert payload["agents"][0]["safety_checks"]["auto_submit"] is False

