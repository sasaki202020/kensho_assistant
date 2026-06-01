from pathlib import Path

from kensho_assistant.app.entry_logger import log_event
from kensho_assistant.app.privacy_guard import (
    assert_no_personal_info,
    detect_birthdate,
    detect_email,
    detect_phone,
    detect_postal_code,
    mask_email,
    mask_phone,
    redact_personal_info,
    sanitize_exception_message,
)


def test_phone_is_masked():
    assert mask_phone("09000001234") == "090-****-1234"


def test_email_is_masked():
    assert mask_email("example@example.com") == "ex***@example.com"


def test_redaction_handles_contact_and_birthdate():
    text = "mail example@example.com phone 09000001234 postal 100-0001 born 1980/1/1"
    redacted = redact_personal_info(text)
    assert "example@example.com" not in redacted
    assert "09000001234" not in redacted
    assert "100-0001" not in redacted
    assert "1980/1/1" not in redacted


def test_detection_helpers_find_sensitive_values():
    assert detect_email("example@example.com")
    assert detect_phone("09000001234")
    assert detect_postal_code("100-0001")
    assert detect_birthdate("1980/1/1")


def test_exception_message_is_sanitized():
    message = sanitize_exception_message("failed: example@example.com 09000001234")
    assert "example@example.com" not in message
    assert "09000001234" not in message


def test_payload_rejects_personal_info():
    payload = {"email": "example@example.com", "phone": "09000001234"}
    try:
        assert_no_personal_info(payload)
    except ValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")


def test_profile_values_do_not_appear_in_logs(tmp_path: Path):
    log_path = tmp_path / "run.jsonl"
    log_event(
        "profile",
        {
            "last_name": "山田",
            "first_name": "太郎",
            "phone": "09000001234",
            "email": "example@example.com",
            "postal_code": "100-0001",
            "birth_day": "1980/1/1",
        },
        path=log_path,
    )
    text = log_path.read_text(encoding="utf-8")
    assert "山田" not in text
    assert "太郎" not in text
    assert "09000001234" not in text
    assert "example@example.com" not in text
    assert "100-0001" not in text
