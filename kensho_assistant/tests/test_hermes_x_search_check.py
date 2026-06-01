from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from subprocess import TimeoutExpired

import scripts.check_hermes_x_search as check_cli
import scripts.research_x_kensho as research_x_cli
from kensho_assistant.app.research import hermes_x_search as hermes_mod


def _patch_diag_path(monkeypatch, tmp_path: Path) -> Path:
    output_file = tmp_path / "data" / "research" / "x_harness" / "diagnostics" / "hermes_x_search_check.json"
    monkeypatch.setattr(hermes_mod, "RESEARCH_X_DIAGNOSTICS_JSON", output_file)
    monkeypatch.setattr(hermes_mod, "RESEARCH_X_HARNESS_DIAGNOSTICS_JSON", output_file)
    return output_file


def test_check_success_saves_masked_output_and_cli_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    output_file = _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):  # noqa: ANN001
        if command[:4] == ["wsl", "-d", "Ubuntu", "--"]:
            assert command[4:7] == ["/home/goo10/.local/bin/hermes", "chat", "-q"]
        elif command[:3] == ["wsl", "bash", "-lc"]:
            assert "hermes chat -q" in command[3]
        else:
            assert command[:4] == ["wsl", "hermes", "chat", "-q"]
        return SimpleNamespace(
            returncode=0,
            stdout='[{"author":"a","handle":"@a","post_url":"https://x.com/a/1","text":"hello"}]',
            stderr="contact user@example.com token=abc123 api_key=sk-live-123",
        )

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_hermes_x_search_check(timeout_sec=120)
    exit_code = check_cli.main(["--timeout-sec", "120"])
    captured = capsys.readouterr().out
    saved = json.loads(output_file.read_text(encoding="utf-8"))

    assert report["status"] == "success"
    assert report["reason"] == "ok"
    assert exit_code == 0
    assert "### Hermes X Search Check" in captured
    assert "status: success" in captured
    assert str(output_file) in captured
    assert "next_action:" in captured
    assert "user@example.com" not in saved["stderr_masked"]
    assert "token=abc123" not in saved["stderr_masked"]
    assert "api_key=sk-live-123" not in saved["stderr_masked"]
    assert "user@example.com" not in saved["stdout_masked"]


def test_check_command_not_found(tmp_path: Path, monkeypatch) -> None:
    _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError("hermes")

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_hermes_x_search_check(command="hermes chat -q", timeout_sec=120)
    assert report["status"] == "failed"
    assert report["reason"] == "command_not_found"
    assert report["exit_code"] == 127


def test_check_wsl_not_found(tmp_path: Path, monkeypatch) -> None:
    _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise FileNotFoundError("wsl")

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_hermes_x_search_check(timeout_sec=120)
    assert report["status"] == "failed"
    assert report["reason"] == "wsl_not_found"


def test_check_timeout(tmp_path: Path, monkeypatch) -> None:
    _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise TimeoutExpired(cmd=["wsl", "hermes"], timeout=5)

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_hermes_x_search_check(timeout_sec=5)
    assert report["status"] == "failed"
    assert report["reason"] == "timeout"
    assert report["exit_code"] == 124


def test_harness_check_x_search_timeout(tmp_path: Path, monkeypatch) -> None:
    _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(*args, **kwargs):  # noqa: ANN001
        raise TimeoutExpired(cmd=["wsl", "hermes"], timeout=300)

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_x_research_harness_check(timeout_sec=300)
    assert report["status"] == "failed"
    assert report["reason"] == "x_search_timeout"
    assert report["timeout_sec"] == 300


def test_check_x_search_disabled(tmp_path: Path, monkeypatch) -> None:
    _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):  # noqa: ANN001
        return SimpleNamespace(returncode=1, stdout="[]", stderr="x_search is disabled in Hermes tools")

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_hermes_x_search_check(timeout_sec=120)
    assert report["status"] == "failed"
    assert report["reason"] == "x_search_disabled"


def test_check_xai_auth_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):  # noqa: ANN001
        return SimpleNamespace(returncode=1, stdout="[]", stderr="xai oauth required: unauthorized")

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_hermes_x_search_check(timeout_sec=120)
    assert report["status"] == "failed"
    assert report["reason"] == "xai_auth_missing"


def test_check_invalid_json(tmp_path: Path, monkeypatch) -> None:
    _patch_diag_path(monkeypatch, tmp_path)

    def fake_run(command, capture_output, text, encoding=None, errors=None, timeout=None, check=False):  # noqa: ANN001
        return SimpleNamespace(returncode=0, stdout="not json", stderr="")

    monkeypatch.setattr(hermes_mod.subprocess, "run", fake_run)
    report = hermes_mod.run_hermes_x_search_check(timeout_sec=120)
    assert report["status"] == "failed"
    assert report["reason"] == "invalid_json"


def test_research_cli_check_hermes_switches_to_diagnostic(monkeypatch) -> None:
    called = {}

    def fake_check(**kwargs):  # noqa: ANN001
        called["kwargs"] = kwargs
        return {"status": "success", "reason": "ok", "output_file": "x.json"}

    def fail_search(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("search should not run when --check-hermes is set")

    monkeypatch.setattr(research_x_cli, "run_hermes_x_search_check", fake_check)
    monkeypatch.setattr(research_x_cli, "research_x_campaigns", fail_search)
    exit_code = research_x_cli.main(["--check-hermes", "--timeout-sec", "15", "--command", "wsl hermes chat -q"])
    assert exit_code == 0
    assert called["kwargs"] == {"command": "wsl hermes chat -q", "timeout_sec": 15}

