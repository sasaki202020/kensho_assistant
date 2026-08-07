from __future__ import annotations

from kensho_assistant.pilot.preflight import run_preflight


def test_offline_pilot_preflight_is_ready_and_has_required_contract(tmp_path) -> None:
    result = run_preflight(work_root=tmp_path)
    assert result == {
        "pilot_storage_isolated": True,
        "pii_persistence_check": True,
        "candidate_state_immutable": True,
        "auto_submit_guard": True,
        "submitted_count_auto": 0,
        "playwright_trace_policy": "DISABLED",
        "screenshot_policy": "DISABLED",
        "result": "READY_FOR_5_SITE_PILOT",
    }
