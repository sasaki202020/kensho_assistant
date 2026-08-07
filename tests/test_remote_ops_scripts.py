from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _script(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_start_remote_ops_uses_owned_pid_and_health_check() -> None:
    text = _script("start_remote_ops.ps1")
    assert "web_app.pid" in text
    assert "Get-OwnedProcess" in text
    assert "127.0.0.1:8787/health" in text
    assert "submitted_count_auto" in text
    assert "Get-NetTCPConnection" in text
    assert "kensho_assistant.run_web" in text
    assert "kensho-remote-ops" in text
    assert "open_url_in_chrome" not in text


def test_stop_remote_ops_only_stops_owned_web_process() -> None:
    text = _script("stop_remote_ops.ps1")
    assert "web_app.pid" in text
    assert "CommandLine" in text
    assert "kensho_assistant.run_web" in text
    assert "kensho-remote-ops" in text
    assert "Stop-Process -Name" not in text
    assert "taskkill" not in text.casefold()
    assert "chrome" not in text.casefold()


def test_remote_readiness_checks_required_safety_boundaries() -> None:
    text = _script("check_remote_readiness.ps1")
    for expected in (
        "localhost_bind",
        "submitted_count_auto",
        "tailscale_status",
        "tailscale_serve",
        "chrome_remote_desktop",
        "session_state",
        "playwright_profile",
        "READY",
        "DEGRADED",
        "BLOCKED",
    ):
        assert expected in text
