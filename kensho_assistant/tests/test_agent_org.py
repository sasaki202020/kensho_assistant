from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.agent_dashboard.org import (
    default_agent_org_payload,
    get_mode_roles,
    group_agents_by_team,
    load_agent_org_payload,
    normalize_agent_org_mode,
)


def test_agent_org_reader_reads_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "agent_org.json"
    path.write_text(
        json.dumps(
            {
                "version": "0.4.4",
                "project": "kensho_assistant",
                "org_name": "Kensho Safe AI Team",
                "mission": "safe",
                "global_rules": ["safe"],
                "modes": {"normal": ["tech-lead"], "release": ["tech-lead", "backend-dev"]},
                "teams": [
                    {"id": "engineering", "name": "エンジニアリング", "purpose": "実装", "agents": [{"id": "tech-lead", "name": "tech-lead", "role": "実装方針", "checks": ["変更範囲"]}]}
                ],
            }
        ),
        encoding="utf-8",
    )
    payload = load_agent_org_payload(path)
    assert payload["source_state"] == "json"
    assert payload["org_name"] == "Kensho Safe AI Team"
    assert get_mode_roles(payload, "release") == ["tech-lead", "backend-dev"]
    grouped = group_agents_by_team(
        [{"role": "tech-lead", "display_name": "tech-lead", "status": "running", "progress_percent": 50, "total_tasks": 1, "completed_tasks": 0, "warning_count": 0, "error_count": 0, "last_message": "ok", "updated_at": "2026-05-24T15:20:00+09:00"}],
        payload,
        "normal",
    )
    assert grouped[0]["name"] == "エンジニアリング"


def test_agent_org_reader_missing_file_returns_default(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    payload = load_agent_org_payload(path)
    assert payload["source_state"] == "missing"
    assert payload["org_name"] == default_agent_org_payload()["org_name"]
    assert normalize_agent_org_mode("release") == "release"
    assert normalize_agent_org_mode("broken") == "normal"


def test_agent_org_reader_broken_json_returns_default(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    payload = load_agent_org_payload(path)
    assert payload["source_state"] == "invalid"
    assert payload["org_name"] == default_agent_org_payload()["org_name"]


def test_agent_org_reader_does_not_use_sample_as_primary(tmp_path: Path) -> None:
    actual = tmp_path / "agent_org.json"
    sample = tmp_path / "agent_org.sample.json"
    sample.write_text(json.dumps(default_agent_org_payload(), ensure_ascii=False), encoding="utf-8")
    payload = load_agent_org_payload(actual)
    assert payload["source_state"] == "missing"
    assert payload["org_name"] == default_agent_org_payload()["org_name"]
