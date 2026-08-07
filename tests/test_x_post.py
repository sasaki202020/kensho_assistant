from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import scripts.x_post as x_post_cli
from kensho_assistant.app.integrations.x_post import XPostConfig, _text_hash, create_post


class FakeResponse:
    def __init__(self, *, status_code: int = 201, payload: dict[str, object] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url, headers=None, json=None, timeout=None):  # noqa: ANN001
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.response


def _config(tmp_path: Path, **kwargs) -> XPostConfig:
    base = XPostConfig(
        enabled=True,
        dry_run=True,
        auth_mode="oauth2",
        client_id="client-id",
        client_secret="client-secret",
        callback_url="https://callback.example.com",
        access_token="access-token-123",
        refresh_token="refresh-token-123",
        api_key="api-key-123",
        api_secret="api-secret-123",
        access_token_secret="access-token-secret-123",
        history_path=tmp_path / "history.jsonl",
    )
    return replace(base, **kwargs)


def test_dry_run_does_not_call_api_and_returns_preview(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse())
    config = _config(tmp_path, dry_run=True)

    result = create_post("Hello X", confirm_live=True, config=config, session=session)

    assert result["status"] == "success"
    assert result["reason"] == "dry_run"
    assert result["sent"] is False
    assert session.calls == []
    assert result["preview"]["text_preview"] == "Hello X"


def test_confirm_live_is_required_for_live_post(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse())
    config = _config(tmp_path, dry_run=False, enabled=True)

    result = create_post("Hello X", confirm_live=False, config=config, session=session)

    assert result["status"] == "failed"
    assert result["reason"] == "confirm_live_required"
    assert session.calls == []


def test_disabled_blocks_live_post(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse())
    config = _config(tmp_path, dry_run=False, enabled=False)

    result = create_post("Hello X", confirm_live=True, config=config, session=session)

    assert result["status"] == "failed"
    assert result["reason"] == "auto_post_disabled"
    assert session.calls == []


def test_empty_text_is_blocked(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse())
    config = _config(tmp_path, dry_run=True)

    result = create_post("   ", confirm_live=True, config=config, session=session)

    assert result["status"] == "failed"
    assert result["reason"] == "empty_text"
    assert session.calls == []


def test_too_long_text_is_blocked(tmp_path: Path) -> None:
    session = FakeSession(FakeResponse())
    config = _config(tmp_path, dry_run=True)

    result = create_post("a" * (config.max_chars + 1), confirm_live=True, config=config, session=session)

    assert result["status"] == "failed"
    assert result["reason"] == "post_too_long"
    assert session.calls == []


def test_duplicate_recent_post_blocks_live_post(tmp_path: Path) -> None:
    now = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    config = _config(tmp_path, dry_run=False, enabled=True)
    history_text = "same text"
    config.history_path.parent.mkdir(parents=True, exist_ok=True)
    config.history_path.write_text(
        json.dumps(
            {
                "posted_at": "2026-06-18T08:30:00+00:00",
                "status": "posted",
                "text_hash": _text_hash(history_text),
                "text_preview": "same text",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    session = FakeSession(FakeResponse())

    result = create_post(history_text, confirm_live=True, config=config, session=session, now=now)

    assert result["status"] == "failed"
    assert result["reason"] == "duplicate_post"
    assert session.calls == []


def test_oauth2_live_post_sends_payload_and_writes_history(tmp_path: Path) -> None:
    response = FakeResponse(status_code=201, payload={"data": {"id": "1234567890", "text": "Hello X"}})
    session = FakeSession(response)
    config = _config(tmp_path, dry_run=False, enabled=True, auth_mode="oauth2")

    result = create_post("Hello X", confirm_live=True, config=config, session=session)

    assert result["status"] == "success"
    assert result["sent"] is True
    assert result["tweet_id"] == "1234567890"
    assert session.calls[0]["url"] == "https://api.x.com/2/tweets"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer access-token-123"
    assert session.calls[0]["json"] == {"text": "Hello X"}
    history_text = config.history_path.read_text(encoding="utf-8")
    assert "access-token-123" not in history_text
    assert "Hello X" in history_text


def test_oauth1a_live_post_builds_authorization_header(tmp_path: Path) -> None:
    response = FakeResponse(status_code=201, payload={"data": {"id": "9876543210"}})
    session = FakeSession(response)
    config = _config(tmp_path, dry_run=False, enabled=True, auth_mode="oauth1a")

    result = create_post("Hello X", confirm_live=True, config=config, session=session)

    assert result["status"] == "success"
    assert session.calls[0]["headers"]["Authorization"].startswith("OAuth ")
    assert "api-key-123" not in json.dumps(result, ensure_ascii=False)


def test_rate_limited_error_is_safely_summarized(tmp_path: Path) -> None:
    response = FakeResponse(
        status_code=429,
        payload={"title": "Too Many Requests", "detail": "access_token=secret-token-123", "type": "about:blank"},
        text="access_token=secret-token-123",
    )
    session = FakeSession(response)
    config = _config(tmp_path, dry_run=False, enabled=True)

    result = create_post("Hello X", confirm_live=True, config=config, session=session)

    assert result["status"] == "failed"
    assert result["reason"] == "rate_limited"
    assert "secret-token-123" not in result["error_summary"]


def test_cli_dry_run_entrypoint(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("X_DRY_RUN", "true")
    monkeypatch.setenv("X_AUTO_POST_ENABLED", "false")
    monkeypatch.setenv("X_POST_HISTORY_PATH", str(tmp_path / "history.jsonl"))

    exit_code = x_post_cli.main(["--text", "Hello X", "--dry-run"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "status: success" in out
    assert "payload_preview:" in out
