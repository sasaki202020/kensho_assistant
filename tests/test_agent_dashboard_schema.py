from __future__ import annotations

from kensho_assistant.app.agent_dashboard.schema import (
    AGENT_ROLE_LABELS,
    AGENT_ROLE_ORDER,
    ALLOWED_AGENT_STATUSES,
    canonical_agent_record,
    default_agent_records,
    display_agent_status,
    normalize_agent_status,
)


def test_agent_dashboard_schema_defaults_are_safe() -> None:
    records = default_agent_records()
    assert len(records) == len(AGENT_ROLE_ORDER)
    roles = [record["role"] for record in records]
    assert roles == AGENT_ROLE_ORDER
    safety = next(record for record in records if record["role"] == "safety_reviewer")
    assert safety["safety_checks"]["auto_submit"] is False
    assert safety["safety_checks"]["profile_enc_read"] is False
    assert safety["safety_checks"]["pii_logged"] is False
    assert safety["safety_checks"]["x_action_automated"] is False


def test_agent_dashboard_schema_invalid_status_becomes_error() -> None:
    record = canonical_agent_record({"role": "queue_manager", "display_name": "担当", "status": "unexpected"})
    assert record["status"] == "error"
    assert normalize_agent_status("broken") == "error"
    assert display_agent_status("passed") == "completed"
    assert display_agent_status("pending") == "idle"
    assert display_agent_status("failed") == "error"
    assert "queue_manager" in AGENT_ROLE_LABELS
    assert {"pending", "running", "passed", "warning", "failed"}.issubset(ALLOWED_AGENT_STATUSES)
