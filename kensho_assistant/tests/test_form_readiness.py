from kensho_assistant.app.form_detector import extract_quiz_items_from_text
from kensho_assistant.app.form_readiness import evaluate_form_readiness
from kensho_assistant.app.models import DetectedField


def _field(name: str, confidence: float = 0.95, will_fill: bool = True, placeholder: str = "") -> DetectedField:
    return DetectedField(
        field_name=name,
        selector=f"#{name}",
        label=name,
        kind="input",
        placeholder=placeholder,
        confidence=confidence,
        required=True,
        will_fill=will_fill,
    )


def test_entry_like_form_is_ready_for_fill():
    fields = [
        _field("full_name", 0.80),
        _field("postal_code", 0.80),
        _field("prefecture", 0.80),
        _field("address1", 0.75),
        _field("email", 0.95),
        _field("phone", 0.80),
    ]
    result = evaluate_form_readiness(
        fields=fields,
        detected_forms_count=1,
        submit_button_detected=True,
        landing_links_detected=False,
        safety_status="SAFE_TO_FILL",
    )
    assert result.readiness_status == "READY_FOR_FILL"


def test_no_form_is_no_form():
    result = evaluate_form_readiness(
        fields=[],
        detected_forms_count=0,
        submit_button_detected=False,
        landing_links_detected=False,
        safety_status="SAFE_TO_FILL",
    )
    assert result.readiness_status == "NO_FORM"


def test_search_only_is_search_only():
    result = evaluate_form_readiness(
        fields=[_field("unknown_1", 0.0, False, "検索キーワード")],
        detected_forms_count=1,
        submit_button_detected=True,
        landing_links_detected=False,
        safety_status="SAFE_TO_FILL",
    )
    assert result.readiness_status == "SEARCH_ONLY"


def test_landing_page_is_landing_page():
    result = evaluate_form_readiness(
        fields=[],
        detected_forms_count=0,
        submit_button_detected=False,
        landing_links_detected=True,
        safety_status="SAFE_TO_FILL",
    )
    assert result.readiness_status == "LANDING_PAGE"


def test_low_confidence_is_low_confidence():
    result = evaluate_form_readiness(
        fields=[_field("email", 0.65, False)],
        detected_forms_count=1,
        submit_button_detected=True,
        landing_links_detected=False,
        safety_status="SAFE_TO_FILL",
    )
    assert result.readiness_status == "LOW_CONFIDENCE"


def test_safety_block_is_blocked():
    for status in ("X_ACTION_REQUIRED", "LINE_ACTION_REQUIRED", "INSTAGRAM_ACTION_REQUIRED", "LOGIN_REQUIRED", "CAPTCHA_REQUIRED"):
        result = evaluate_form_readiness(
            fields=[_field("email")],
            detected_forms_count=1,
            submit_button_detected=True,
            landing_links_detected=False,
            safety_status=status,
        )
        assert result.readiness_status == "BLOCKED_BY_SAFETY"


def test_required_age_is_review_only():
    result = evaluate_form_readiness(
        fields=[
            _field("full_name", 0.80),
            _field("email", 0.95),
            _field("postal_code", 0.80),
            _field("phone", 0.80),
            _field("age", 0.95, False),
        ],
        detected_forms_count=1,
        submit_button_detected=True,
        landing_links_detected=False,
        safety_status="SAFE_TO_FILL",
    )
    assert result.readiness_status == "REVIEW_ONLY"


def test_quiz_required_is_review_only():
    result = evaluate_form_readiness(
        fields=[_field("full_name", 0.80), _field("email", 0.95)],
        detected_forms_count=1,
        submit_button_detected=True,
        landing_links_detected=False,
        safety_status="SAFE_TO_FILL",
        quiz_required=True,
    )
    assert result.readiness_status == "REVIEW_ONLY"
    assert result.quiz_required is True


def test_quiz_text_extracts_question_and_choices():
    items = extract_quiz_items_from_text(
        "クイズ\n「高倉びわ」の始まりの地はどれでしょうか。\n福岡市\n岡垣町\n広川町\n",
        source_hint_url="https://example.com/present",
    )
    assert items
    assert items[0]["auto_fill_allowed"] is False
    assert items[0]["manual_required"] is True
    assert "どれでしょうか" in items[0]["question_text"]
    assert "福岡市" in items[0]["choices"]
