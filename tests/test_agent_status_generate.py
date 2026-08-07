from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import kensho_assistant.main as main_cli


def test_agent_status_generate_writes_safe_json(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "agent_status.json"
    result = main_cli.cmd_agent_status_generate(SimpleNamespace(output=str(output)))
    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["updated_at"]
    assert [agent["role"] for agent in payload["agents"]] == [
        "planner",
        "coder",
        "safety_reviewer",
        "tester",
        "release_manager",
    ]
    flat = json.dumps(payload, ensure_ascii=False).casefold()
    assert "profile" not in flat
    assert "address" not in flat
    assert "phone" not in flat
    assert "email" not in flat


def test_agent_status_generate_payload_schema_is_valid() -> None:
    payload = main_cli.build_agent_status_payload(updated_at="2026-05-24T15:20:00+09:00")
    assert payload["updated_at"] == "2026-05-24T15:20:00+09:00"
    assert len(payload["agents"]) == 5
    for agent in payload["agents"]:
        assert agent["status"] in {"pending", "running", "passed", "warning", "failed"}
        assert isinstance(agent["checks"], list)
        assert isinstance(agent["risks"], list)
        assert agent["updated_at"] == "2026-05-24T15:20:00+09:00"


def test_agent_status_generate_does_not_use_profile_data(tmp_path: Path) -> None:
    output = tmp_path / "agent_status.json"
    main_cli.cmd_agent_status_generate(SimpleNamespace(output=str(output)))
    text = output.read_text(encoding="utf-8")
    for keyword in ("profile.json", "address", "phone", "メール本文", "応募者"):
        assert keyword not in text
