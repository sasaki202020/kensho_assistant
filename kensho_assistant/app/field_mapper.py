from __future__ import annotations

from collections.abc import Mapping

from .form_filler import plan_field_filling_with_age
from .models import DetectedField


AUTO_FILL_ALLOWED_FIELDS = {
    "last_name",
    "first_name",
    "full_name",
    "last_name_kana",
    "first_name_kana",
    "full_name_kana",
    "postal_code",
    "prefecture",
    "city",
    "address1",
    "address2",
    "phone",
    "phone_confirm",
    "email",
    "email_confirm",
    "gender",
    "birth_year",
    "birth_month",
    "birth_day",
}

AUTO_FILL_BLOCKED_FIELDS = {
    "consent",
    "age",
    "quiz_answer",
    "free_text",
    "opinion",
    "newsletter",
    "dm_opt_in",
    "sns_account",
    "password",
    "login",
    "captcha",
    "submit",
    "confirm",
}


class FieldMapper:
    def map_fields(
        self,
        fields: list[DetectedField],
        profile: Mapping[str, str],
        allow_birthdate_fill: bool = True,
    ) -> list[DetectedField]:
        planned = plan_field_filling_with_age(fields, profile, allow_age_fill=allow_birthdate_fill)
        for field in planned:
            if field.field_name in AUTO_FILL_BLOCKED_FIELDS:
                field.will_fill = False
                field.value_preview = ""
                field.skip_reason = field.skip_reason or "自動入力しない項目のため"
        return planned
