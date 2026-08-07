from __future__ import annotations

from kensho_assistant.app.models import DetectedField
from kensho_assistant.app.pre_submit_verifier import CAPTCHA_TERMS, PreSubmitVerifier


def test_required_radio_options_count_as_one_question() -> None:
    fields = [
        DetectedField(
            field_name=f"unknown_{index}",
            selector=f'input[name="survey_choice"]:nth-of-type({index})',
            label=f"Choice {index}",
            kind="input",
            input_type="radio",
            name="survey_choice",
            required=True,
            will_fill=False,
        )
        for index in range(1, 6)
    ]

    summary = PreSubmitVerifier()._summarize_field_questions(fields)

    assert summary["total_fields_count"] == 1
    assert summary["filled_fields_count"] == 0
    assert summary["required_unfilled"] == ["survey_choice"]


def test_unconfigured_survey_and_select_remain_separate_questions() -> None:
    fields = [
        DetectedField("unknown_a", 'input[name="survey"]:nth-of-type(1)', "A", "input", input_type="radio", name="survey", required=True),
        DetectedField("unknown_b", 'input[name="survey"]:nth-of-type(2)', "B", "input", input_type="radio", name="survey", required=True),
        DetectedField("unknown_select", 'select[name="prize"]', "Prize", "select", name="prize", required=True),
    ]

    summary = PreSubmitVerifier()._summarize_field_questions(fields)

    assert summary["total_fields_count"] == 2
    assert summary["required_unfilled"] == ["survey", "unknown_select"]


def test_generic_authentication_copy_is_not_treated_as_captcha() -> None:
    assert not PreSubmitVerifier._contains("メール認証に関するご案内", CAPTCHA_TERMS)
    assert PreSubmitVerifier._contains("画像認証を入力してください", CAPTCHA_TERMS)
