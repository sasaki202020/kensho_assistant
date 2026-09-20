from __future__ import annotations

from scripts.run_extension_local_smoke import run_smoke


def test_local_smoke_runs_without_toolbar_or_external_site() -> None:
    result = run_smoke(headless=True)

    assert result == {
        "status": "PASS",
        "fixture": "standard_form",
        "overlay_detected": True,
        "reload_success_count": 10,
        "same_origin_navigation": True,
        "service_worker_restart_recovered": True,
        "max_panel_count": 1,
        "max_guard_count": 1,
            "unapproved_origin_injections": 0,
            "analysis_completed": True,
            "auto_analysis_completed": True,
            "fill_completed": True,
        "combined_captcha_safe_stop": True,
        "submit_blocked": True,
        "auto_submit_detected": 0,
        "submitted_count_auto": 0,
        "session_cleared": True,
        "external_requests": 0,
        "sentinel_network_leak": 0,
        "extension_non_loopback_requests": 0,
    }
