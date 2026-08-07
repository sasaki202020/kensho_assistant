from __future__ import annotations

import json

from kensho_assistant.app.profile_manager import build_profile_readiness


def test_profile_readiness_reports_names_without_profile_values() -> None:
    profile = {
        "last_name": "SensitiveLast",
        "first_name": "SensitiveFirst",
        "last_name_kana": "SensitiveKanaLast",
        "first_name_kana": "SensitiveKanaFirst",
        "postal_code": "1234567",
        "prefecture": "SensitivePrefecture",
        "city": "SensitiveCity",
        "address1": "SensitiveStreet",
        "phone": "09012345678",
        "email": "sensitive@example.com",
    }

    result = build_profile_readiness(profile)
    serialized = json.dumps(result, ensure_ascii=False)

    assert result == {
        "status": "READY",
        "configured_fields": ["name", "name_kana", "postal_code", "address", "phone", "email"],
        "missing_fields": [],
        "configured_count": 6,
        "required_count": 6,
    }
    for value in profile.values():
        assert value not in serialized


def test_profile_readiness_does_not_guess_missing_values() -> None:
    result = build_profile_readiness({"full_name": "Configured Name", "email": "configured@example.com"})

    assert result["status"] == "MISSING_FIELDS"
    assert result["configured_fields"] == ["name", "email"]
    assert result["missing_fields"] == ["name_kana", "postal_code", "address", "phone"]
