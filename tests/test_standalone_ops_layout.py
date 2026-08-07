from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _script(*parts: str) -> str:
    return (ROOT / "scripts" / Path(*parts)).read_text(encoding="utf-8")


def test_remote_ops_scripts_are_self_contained_and_never_open_a_browser() -> None:
    start = _script("start_remote_ops.ps1")
    stop = _script("stop_remote_ops.ps1")
    readiness = _script("check_remote_readiness.ps1")

    for text in (start, stop, readiness):
        assert "kensho_assistant.run_web" in text
        assert "web_app.py" not in text
        assert "open_url_in_chrome" not in text
        assert "Start-Process chrome" not in text

    assert "--managed-by" in start
    assert "kensho-remote-ops" in start
    assert "127.0.0.1:8787/health" in start
    assert "submitted_count_auto" in readiness


def test_x_post_assistant_is_dry_run_only() -> None:
    text = _script("windows", "x_post_assistant.ps1")

    assert "kensho_assistant.scripts.x_post" in text
    assert "--dry-run" in text
    assert "--confirm-live" not in text
    assert "Invoke-WebRequest" not in text
