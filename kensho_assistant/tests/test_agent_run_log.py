from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.agent_dashboard import service


def test_agent_status_run_appends_safe_jsonl(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "agent_run_log.jsonl"
    status_path = tmp_path / "agent_status.json"
    monkeypatch.setattr(service, "AGENT_RUN_LOG_JSONL", log_path)
    payload = service.save_agent_status_run_payload("safe-agent-run email@example.com", status_path, mode="normal")
    assert status_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["run_mode"] == "safe-agent-run"
    assert record["mode"] == "normal"
    assert record["release_allowed"] is False
    assert record["safety"]["auto_submit"] is False
    assert record["safety"]["submitted_count_auto"] == 0
    assert record["safety"]["safe_to_submit"] is False
    assert record["verification"]["pytest"]["status"] == "not_run"
    assert record["verification"]["compileall"]["status"] == "not_run"
    assert record["verification"]["smoke_test"]["status"] == "not_run"
    flat = json.dumps(record, ensure_ascii=False).casefold()
    assert "email@example.com" not in flat
    assert "password" not in flat
    assert "profile.enc" not in flat.lower()
    assert payload["run_mode"] == "safe-agent-run"


def test_agent_status_run_log_appends_multiple_rows(tmp_path: Path, monkeypatch) -> None:
    log_path = tmp_path / "agent_run_log.jsonl"
    status_path = tmp_path / "agent_status.json"
    monkeypatch.setattr(service, "AGENT_RUN_LOG_JSONL", log_path)
    service.save_agent_status_run_payload("task one", status_path, mode="normal")
    service.save_agent_status_run_payload("task two", status_path, mode="release")
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["task"] == "task one"
    assert second["task"] == "task two"
    assert first["mode"] == "normal"
    assert second["mode"] == "release"
    assert isinstance(first["warnings"], list)
    assert isinstance(first["errors"], list)
