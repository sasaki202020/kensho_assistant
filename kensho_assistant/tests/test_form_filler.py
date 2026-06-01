from kensho_assistant.app.form_filler import build_input_review, plan_field_filling, plan_field_filling_with_age
from kensho_assistant.app.models import DetectedField


def test_low_confidence_fields_are_skipped():
    fields = [
        DetectedField(field_name="email", selector="#email", label="メール", kind="input", confidence=0.74, required=True),
        DetectedField(field_name="email", selector="#email2", label="メール", kind="input", confidence=0.95, required=True),
    ]
    planned = plan_field_filling(fields, {"email": "kensho-test@example.com"})
    assert planned[0].will_fill is False
    assert planned[1].will_fill is True


def test_optional_phone_is_filled_but_other_optional_and_consent_fields_are_skipped():
    fields = [
        DetectedField(field_name="newsletter", selector="#newsletter", label="メルマガ", kind="checkbox", confidence=0.95, required=True),
        DetectedField(field_name="consent", selector="#consent", label="同意", kind="checkbox", confidence=0.95, required=True),
        DetectedField(field_name="free_text", selector="#comment", label="自由記述", kind="textarea", confidence=0.95, required=True),
        DetectedField(field_name="phone", selector="#phone", label="電話番号", kind="input", confidence=0.95, required=False),
    ]
    planned = plan_field_filling(fields, {"phone": "09000001234"})
    assert planned[0].will_fill is False
    assert planned[1].will_fill is False
    assert planned[2].will_fill is False
    assert planned[3].will_fill is True
    assert planned[3].value_preview == "090-****-1234"


def test_opinion_field_uses_default_text():
    fields = [
        DetectedField(field_name="opinion", selector="#comment", label="御意見、御感想", kind="textarea", confidence=0.95, required=True),
    ]
    planned = plan_field_filling(fields, {})
    assert planned[0].will_fill is True
    assert "本県の農林水産物" in planned[0].value_preview


def test_age_is_never_filled():
    fields = [DetectedField(field_name="age", selector="#age", label="年齢", kind="input", confidence=0.95, required=True)]
    planned = plan_field_filling(fields, {})
    assert planned[0].will_fill is False
    assert planned[0].skip_reason == "年齢情報のため自動入力しない"


def test_age_is_filled_only_when_explicitly_allowed():
    fields = [DetectedField(field_name="age", selector="#age", label="年齢", kind="input", confidence=0.95, required=True)]
    planned = plan_field_filling_with_age(fields, {"age": "35"}, allow_age_fill=True)
    assert planned[0].will_fill is True


def test_birthdate_fields_remain_skipped_without_permission():
    fields = [DetectedField(field_name="birth_year", selector="#birth_year", label="生年", kind="input", confidence=0.95, required=True)]
    planned = plan_field_filling_with_age(fields, {"birth_year": "1980"}, allow_age_fill=False)
    assert planned[0].will_fill is False


def test_quiz_answer_is_never_filled():
    fields = [DetectedField(field_name="quiz_answer", selector="#quiz", label="クイズ回答", kind="input", confidence=0.95, required=True)]
    planned = plan_field_filling(fields, {})
    assert planned[0].will_fill is False
    assert planned[0].skip_reason == "クイズ回答のため自動入力しない"


def test_review_distinguishes_duplicate_and_required_fields():
    fields = [
        DetectedField(field_name="gender", selector="#male", label="性別", kind="radio", confidence=0.95, required=False, reason="test"),
        DetectedField(field_name="gender", selector="#female", label="性別", kind="radio", confidence=0.95, required=False, reason="test"),
        DetectedField(field_name="postal_code", selector="#postal1", label="郵便番号", kind="input", confidence=0.95, required=True, reason="test"),
        DetectedField(field_name="postal_code", selector="#postal2", label="郵便番号", kind="input", confidence=0.95, required=False, reason="test"),
        DetectedField(field_name="address1", selector="#address1", label="住所", kind="input", confidence=0.95, required=False, reason="test"),
    ]
    planned = plan_field_filling(fields, {"postal_code": "100-0001", "address1": "千代田1-1"})
    review = build_input_review({"campaign_id": "x"}, planned, {}, "SAFE_TO_FILL", "")
    assert "gender[1:optional]" in review
    assert "gender[2:optional]" in review
    assert "postal_code[1:required]" in review
    assert "postal_code[2:optional]" in review
    assert "address1[optional]" in review
    assert planned[3].will_fill is False
    assert planned[4].will_fill is False


def test_duplicate_entry_review_is_de_emphasized():
    fields = [DetectedField(field_name="email", selector="#email", label="メール", kind="input", confidence=0.95, required=True, reason="test")]
    planned = plan_field_filling(fields, {"email": "kensho-test@example.com"})
    review = build_input_review({"campaign_id": "x"}, planned, {}, "DUPLICATE_ENTRY", "DUPLICATE_ENTRY")
    assert "重複の可能性あり" in review
    assert "注意: 似た候補が見つかっています。必要なら詳細を確認してください。" in review
    assert review.index("重複の可能性あり") < review.index("DUPLICATE_ENTRY")


def test_address_preview_is_masked():
    fields = [DetectedField(field_name="address1", selector="#address", label="住所", kind="input", confidence=0.95, required=True, reason="test")]
    planned = plan_field_filling(fields, {"address1": "secret address"})
    assert planned[0].value_preview == "***"
