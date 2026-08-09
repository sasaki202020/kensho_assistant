import json

import pytest

from kensho_assistant.app.high_value.submissions import ManualSubmissionStoreError, load_manual_submissions, mark_manual_submitted


def test_manual_submission_record_is_pii_free_and_idempotent(tmp_path):
    path = tmp_path / "high_value_manual_submissions.json"

    created, first = mark_manual_submitted("campaign-1", "X_MANUAL", path)
    repeated, second = mark_manual_submitted("campaign-1", "X_MANUAL", path)

    assert created is True
    assert repeated is False
    assert first == second
    assert set(first) == {"campaign_id", "manual_submitted_at", "application_mode"}
    assert load_manual_submissions(path)["campaign-1"]["application_mode"] == "X_MANUAL"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert "email" not in json.dumps(payload)
    assert "phone" not in json.dumps(payload)


def test_corrupt_manual_submission_store_fails_closed(tmp_path):
    path = tmp_path / "high_value_manual_submissions.json"
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(ManualSubmissionStoreError):
        load_manual_submissions(path)
