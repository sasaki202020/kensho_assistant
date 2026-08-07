from __future__ import annotations

from collections.abc import Mapping

from .form_filler import plan_field_filling_with_age
from .models import DetectedField
from .site_templates import SiteTemplate


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
    "age",
    "birth_year",
    "birth_month",
    "birth_day",
    "age_group",
    "occupation",
    "marital_status",
    "children",
    "survey_choice",
    "prize_choice",
    "entry_count",
}

AUTO_FILL_BLOCKED_FIELDS = {
    "consent",
    "quiz_answer",
    "newsletter",
    "dm_opt_in",
    "sns_account",
    "password",
    "login",
    "captcha",
    "submit",
    "confirm",
    "login_id",
    "search",
}


def _override_value(answer_overrides: Mapping[str, str] | None, field_name: str) -> str:
    if not answer_overrides:
        return ""
    return str(answer_overrides.get(field_name, "")).strip()


class FieldMapper:
    def map_fields(
        self,
        fields: list[DetectedField],
        profile: Mapping[str, str],
        allow_birthdate_fill: bool = True,
        site_template: SiteTemplate | None = None,
        answer_overrides: Mapping[str, str] | None = None,
        allow_ai_answer_fill: bool = False,
    ) -> list[DetectedField]:
        planned = plan_field_filling_with_age(
            fields,
            profile,
            allow_age_fill=allow_birthdate_fill,
            answer_overrides=answer_overrides,
            allow_ai_answer_fill=allow_ai_answer_fill,
        )
        force_fill_fields = set(site_template.force_fill_fields) if site_template else set()
        for field in planned:
            if field.field_name in AUTO_FILL_BLOCKED_FIELDS:
                ai_override = field.field_name == "quiz_answer" and allow_ai_answer_fill and bool(_override_value(answer_overrides, field.field_name))
                if ai_override and not field.skip_reason:
                    field.will_fill = True
                    continue
                field.will_fill = False
                field.value_preview = ""
                field.skip_reason = field.skip_reason or "自動入力しない項目のため"
            elif force_fill_fields and field.field_name in force_fill_fields and not field.skip_reason:
                field.will_fill = True
        return planned
