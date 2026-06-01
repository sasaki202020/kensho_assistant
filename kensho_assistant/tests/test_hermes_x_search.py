from __future__ import annotations

from pathlib import Path
from subprocess import TimeoutExpired

import pytest

from kensho_assistant.app.research import hermes_x_search as hermes


class FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_hermes_x_search_parses_markdown_json_and_masks_secrets(monkeypatch) -> None:
    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):
        del command, capture_output, text, encoding, errors, timeout, check
        return FakeCompleted(
            0,
            stdout='before\n```json\n[{"author":"a","handle":"@a","post_url":"https://x.com/a/1","text":"hello"}]\n```\nafter',
            stderr="token=abc123 me@example.com",
        )

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    result = hermes.run_hermes_x_search("AI駆動開発")

    assert result["status"] == "success"
    assert result["reason"] == "ok"
    assert result["response"]["related_posts"][0]["text"] == "hello"
    assert "abc123" not in result["stdout"]
    assert "me@example.com" not in result["stderr"]
    assert "token=abc123" not in result["stderr"]


@pytest.mark.parametrize(
    "response_factory, expected_reason",
    [
        (lambda: FakeCompleted(0, stdout="", stderr=""), "empty_result"),
        (lambda: FakeCompleted(127, stdout="", stderr="command not found"), "hermes_not_found"),
        (lambda: FakeCompleted(1, stdout="{}", stderr="x_search disabled"), "x_search_disabled"),
        (lambda: FakeCompleted(1, stdout="{}", stderr="authentication required"), "xai_auth_missing"),
        (lambda: FakeCompleted(1, stdout="not json", stderr=""), "invalid_json"),
    ],
)
def test_hermes_x_search_classifies_common_failures(monkeypatch, response_factory, expected_reason) -> None:
    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):
        del command, capture_output, text, encoding, errors, timeout, check
        return response_factory()

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    result = hermes.run_hermes_x_search("AI駆動開発")

    assert result["status"] == "failed"
    assert result["reason"] == expected_reason
    assert result["error_type"] == expected_reason


def test_hermes_x_search_timeout_and_missing_command_classification() -> None:
    timeout_reason, timeout_label = hermes._classify_hermes_failure(
        command=["wsl", "hermes", "chat", "-q"],
        stdout="",
        stderr="",
        timed_out=True,
    )
    missing_reason, missing_label = hermes._classify_hermes_failure(
        command=["hermes", "chat", "-q"],
        stdout="",
        stderr="command not found",
        returncode=127,
    )
    assert timeout_reason == "timeout"
    assert "タイムアウト" in timeout_label
    assert missing_reason == "hermes_not_found"
    assert missing_label


def test_run_hermes_x_search_check_writes_report(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "hermes_x_search_check.json"
    monkeypatch.setattr(hermes, "RESEARCH_X_HARNESS_DIAGNOSTICS_JSON", report_path)

    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):
        del command, capture_output, text, encoding, errors, timeout, check
        return FakeCompleted(0, stdout='[{"author":"a","handle":"@a","post_url":"https://x.com/a/1","text":"hello"}]', stderr="")

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    report = hermes.run_x_research_harness_check(query="AI駆動開発 Codex サブエージェント レビュー")

    assert report_path.exists()
    saved = report_path.read_text(encoding="utf-8")
    assert '"status": "success"' in saved
    assert report["status"] == "success"
    assert report["reason"] == "ok"
    assert report["next_action"]


def test_hermes_x_search_classifies_command_and_hermes_missing(monkeypatch) -> None:
    def fake_run_missing(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):
        del command, capture_output, text, encoding, errors, timeout, check
        raise FileNotFoundError("missing")

    monkeypatch.setattr(hermes.subprocess, "run", fake_run_missing)
    command_missing = hermes.run_hermes_x_search("AI駆動開発", command="hermes chat -q")
    wsl_missing = hermes.run_hermes_x_search("AI駆動開発", command="wsl hermes chat -q")

    assert command_missing["reason"] == "command_not_found"
    assert command_missing["error_type"] == "command_not_found"
    assert wsl_missing["reason"] == "wsl_not_found"
    assert wsl_missing["error_type"] == "wsl_not_found"


def test_hermes_x_search_classifies_hermes_not_found(monkeypatch) -> None:
    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):
        del command, capture_output, text, encoding, errors, timeout, check
        return FakeCompleted(127, stdout="", stderr="hermes: command not found")

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    result = hermes.run_hermes_x_search("AI駆動開発", command="wsl hermes chat -q")

    assert result["reason"] == "hermes_not_found"
    assert result["error_type"] == "hermes_not_found"


def test_hermes_output_masking_masks_personal_data() -> None:
    masked = hermes.mask_hermes_output("me@example.com token=abc123 api key sk-1234567890")
    assert "me@example.com" not in masked
    assert "abc123" not in masked
    assert "sk-1234567890" not in masked


def test_hermes_x_search_extracts_json_array_from_decorated_stdout(monkeypatch) -> None:
    decorated = """
Query:
x_searchを使って「Hermes Agent」をXで1件だけ検索してください。
Initializing agent...
────────────────────────────────
[{"post_url":"https://x.com/sample/status/1","summary":"Hermes Agentの話題"}]
Resume this session with:
Session: abc
Duration: 47s
Messages: 3
"""

    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):
        del command, capture_output, text, encoding, errors, timeout, check
        return FakeCompleted(0, stdout=decorated, stderr="")

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    result = hermes.run_hermes_x_search(
        "Hermes Agent",
        prompt=hermes.build_hermes_x_search_diagnostic_prompt("Hermes Agent"),
        prefer_array=True,
    )

    assert result["status"] == "success"
    assert result["response"]["related_posts"][0]["post_url"] == "https://x.com/sample/status/1"
    assert result["response"]["related_posts"][0]["summary"] == "Hermes Agentの話題"


def test_hermes_x_search_uses_env_timeout(monkeypatch) -> None:
    seen = {}

    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):
        del command, capture_output, text, encoding, errors, check
        seen["timeout"] = timeout
        return FakeCompleted(0, stdout='[{"post_url":"https://x.com/sample/status/1","summary":"ok"}]', stderr="")

    monkeypatch.setenv("X_RESEARCH_HERMES_TIMEOUT_SEC", "300")
    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    result = hermes.run_hermes_x_search(
        "Hermes Agent",
        prompt=hermes.build_hermes_x_search_diagnostic_prompt("Hermes Agent"),
        prefer_array=True,
    )

    assert result["status"] == "success"
    assert seen["timeout"] == 300


def test_hermes_x_search_timeout_is_x_search_timeout(monkeypatch) -> None:
    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise TimeoutExpired(cmd=["wsl", "hermes"], timeout=300)

    monkeypatch.setattr(hermes.subprocess, "run", fake_run)
    result = hermes.run_hermes_x_search(
        "Hermes Agent",
        prompt=hermes.build_hermes_x_search_diagnostic_prompt("Hermes Agent"),
        prefer_array=True,
    )

    assert result["status"] == "failed"
    assert result["reason"] == "x_search_timeout"
    assert result["error_type"] == "x_search_timeout"

