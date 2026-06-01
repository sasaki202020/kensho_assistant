from kensho_assistant.app.form_detector import detect_field_from_metadata
from kensho_assistant.app.form_filler import plan_field_filling


def _metadata(**overrides):
    base = {
        "tag_name": "input",
        "input_type": "text",
        "name": "",
        "id": "",
        "placeholder": "",
        "aria_label": "",
        "class_name": "",
        "label_text": "",
        "parent_text": "",
        "previous_cell_text": "",
        "previous_label_text": "",
        "nearby_text": "",
        "required": True,
        "selector": "#field",
    }
    base.update(overrides)
    return base


def test_email1_is_detected_as_email():
    field = detect_field_from_metadata(_metadata(input_type="email", name="email1"))
    assert field.field_name == "email"


def test_email2_is_detected_as_email_confirm():
    field = detect_field_from_metadata(_metadata(input_type="email", name="email2"))
    assert field.field_name == "email_confirm"


def test_email_name_has_high_confidence():
    field = detect_field_from_metadata(_metadata(input_type="email", name="email"))
    assert field.confidence >= 0.90


def test_placeholder_email_is_detected():
    field = detect_field_from_metadata(_metadata(placeholder="メールアドレス"))
    assert field.field_name == "email"


def test_postal_code_is_detected():
    field = detect_field_from_metadata(_metadata(label_text="郵便番号"))
    assert field.field_name == "postal_code"


def test_phone_is_detected():
    field = detect_field_from_metadata(_metadata(label_text="電話番号"))
    assert field.field_name == "phone"


def test_full_name_is_detected():
    field = detect_field_from_metadata(_metadata(label_text="お名前"))
    assert field.field_name == "full_name"


def test_full_name_kana_is_detected():
    field = detect_field_from_metadata(_metadata(label_text="フリガナ"))
    assert field.field_name == "full_name_kana"


def test_newsletter_checkbox_is_never_filled():
    field = detect_field_from_metadata(_metadata(input_type="checkbox", label_text="メルマガ登録"))
    planned = plan_field_filling([field], {})
    assert planned[0].will_fill is False


def test_consent_checkbox_is_never_filled():
    field = detect_field_from_metadata(_metadata(input_type="checkbox", label_text="利用規約に同意"))
    planned = plan_field_filling([field], {})
    assert planned[0].will_fill is False


def test_password_field_is_never_filled():
    field = detect_field_from_metadata(_metadata(input_type="password", name="password"))
    planned = plan_field_filling([field], {})
    assert planned[0].will_fill is False


def test_credit_card_field_is_never_filled():
    field = detect_field_from_metadata(_metadata(label_text="クレジットカード番号"))
    planned = plan_field_filling([field], {})
    assert planned[0].will_fill is False


def test_low_confidence_field_is_never_filled():
    field = detect_field_from_metadata(_metadata(nearby_text="メール"))
    planned = plan_field_filling([field], {"email": "kensho-test@example.com"})
    assert planned[0].confidence < 0.75
    assert planned[0].will_fill is False


def test_locality_is_detected_as_city():
    field = detect_field_from_metadata(_metadata(name="locality"))
    assert field.field_name == "city"


def test_region_is_detected_as_prefecture():
    field = detect_field_from_metadata(_metadata(name="region"))
    assert field.field_name == "prefecture"


def test_yourcode_is_detected_as_postal_code():
    field = detect_field_from_metadata(_metadata(id="yourcode"))
    assert field.field_name == "postal_code"
    assert field.confidence >= 0.75


def test_yourstate_is_detected_as_prefecture():
    field = detect_field_from_metadata(_metadata(id="yourstate"))
    assert field.field_name == "prefecture"
    assert field.confidence >= 0.75


def test_opinion_is_detected_separately_from_free_text():
    field = detect_field_from_metadata(_metadata(tag_name="textarea", label_text="御意見、御感想"))
    assert field.field_name == "opinion"
