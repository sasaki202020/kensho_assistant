from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import kensho_assistant.main as main_cli
from kensho_assistant.app.agent_dashboard.service import build_agent_status_run_payload


def test_agent_status_run_writes_safe_json(tmp_path: Path) -> None:
    output = tmp_path / "agent_status.json"
    result = main_cli.cmd_agent_status_run(SimpleNamespace(task="safe-agent-run email@example.com", output=str(output)))
    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run_mode"] == "safe-agent-run"
    assert payload["mode"] == "normal"
    assert payload["organization"]["org_name"] == "Kensho Safe AI Team"
    assert payload["organization"]["mode_label"] == "通常モード"
    assert payload["task"]
    assert [agent["role"] for agent in payload["agents"]] == [
        "tech-lead",
        "backend-dev",
        "safety-director",
        "test-engineer",
        "release-gatekeeper",
    ]
    assert all(agent["status"] in {"pending", "running", "passed", "warning", "failed"} for agent in payload["agents"])
    assert payload["agents"][0]["team_name"] == "エンジニアリング"
    assert payload["agents"][2]["team_name"] == "安全・審査"
    flat = json.dumps(payload, ensure_ascii=False).casefold()
    assert "email@example.com" not in flat
    assert "address" not in flat
    assert "phone" not in flat


def test_agent_status_run_payload_schema_is_valid() -> None:
    payload = build_agent_status_run_payload("safe-agent-run", updated_at="2026-05-24T15:20:00+09:00")
    assert payload["updated_at"] == "2026-05-24T15:20:00+09:00"
    assert payload["task"] == "safe-agent-run"
    assert payload["run_mode"] == "safe-agent-run"
    assert payload["mode"] == "normal"
    assert payload["organization"]["mode"] == "normal"
    assert isinstance(payload["checks"], list)
    assert len(payload["agents"]) == 5
    for agent in payload["agents"]:
        assert {"role", "status", "summary", "checks", "risks", "updated_at", "team_id", "team_name"} <= set(agent)
        assert agent["status"] in {"pending", "running", "passed", "warning", "failed"}
        assert isinstance(agent["checks"], list)
        assert isinstance(agent["risks"], list)


def test_agent_status_run_release_mode_includes_release_roles() -> None:
    payload = build_agent_status_run_payload("safe-agent-run", mode="release", updated_at="2026-05-24T15:20:00+09:00")
    assert payload["mode"] == "release"
    assert payload["organization"]["mode_label"] == "リリース前モード"
    roles = [agent["role"] for agent in payload["agents"]]
    assert "frontend-dev" in roles
    assert "desktop-ui-dev" in roles
    assert "zip-auditor" in roles


def test_agent_status_run_does_not_expose_pii_like_keys(tmp_path: Path) -> None:
    output = tmp_path / "agent_status.json"
    main_cli.cmd_agent_status_run(SimpleNamespace(task="task with token=abc123", output=str(output)))
    text = output.read_text(encoding="utf-8")
    for keyword in ("profile.json", "password", "token=abc123", "@example.com"):
        assert keyword not in text
