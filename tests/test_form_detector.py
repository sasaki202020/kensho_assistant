from kensho_assistant.app.form_detector import detect_field_from_metadata
from kensho_assistant.app.field_mapper import FieldMapper
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


def test_apartment_room_placeholder_is_detected_as_address2():
    field = detect_field_from_metadata(
        _metadata(placeholder="例：〇〇マンション 101号室", nearby_text="住所 建物名・部屋番号")
    )
    assert field.field_name == "address2"


def test_apartment_survey_radio_is_not_detected_as_address2():
    field = detect_field_from_metadata(
        _metadata(input_type="radio", name="housing_type", label_text="賃貸マンション")
    )
    assert field.field_name != "address2"


def test_gaora_split_postal_fields_are_not_detected_as_phone():
    first = detect_field_from_metadata(
        _metadata(name="zip1", id="form_item_postal_code_sep0", nearby_text="郵便番号 電話番号")
    )
    second = detect_field_from_metadata(
        _metadata(name="zip2", id="form_item_postal_code_sep1", nearby_text="郵便番号 電話番号")
    )

    assert first.field_name == "postal_code"
    assert second.field_name == "postal_code"


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


def test_newsletter_radio_is_detected_and_skipped():
    field = detect_field_from_metadata(_metadata(input_type="radio", label_text="メルマガ可否"))
    planned = plan_field_filling([field], {})
    assert field.field_name == "newsletter"
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


def test_legacy_yuubin_name_is_detected_as_postal_code():
    field = detect_field_from_metadata(_metadata(name="yuubin", placeholder="123-4567"))
    assert field.field_name == "postal_code"


def test_user_kana_name_is_detected_as_full_name_kana():
    field = detect_field_from_metadata(_metadata(name="user_kana", placeholder="あつぎ たろう"))
    assert field.field_name == "full_name_kana"


def test_opinion_is_detected_separately_from_free_text():
    field = detect_field_from_metadata(_metadata(tag_name="textarea", label_text="御意見、御感想"))
    assert field.field_name == "opinion"


def test_application_reason_is_detected_as_free_text():
    field = detect_field_from_metadata(_metadata(tag_name="textarea", label_text="応募理由"))
    assert field.field_name == "free_text"


def test_motivation_radio_is_detected_as_survey_choice():
    field = detect_field_from_metadata(_metadata(input_type="radio", name="motivation", label_text="応募動機"))
    assert field.field_name == "survey_choice"


def test_site_search_is_classified_as_search_and_never_filled():
    field = detect_field_from_metadata(
        _metadata(input_type="search", name="q", label_text="サイト内検索", placeholder="検索キーワード")
    )
    planned = plan_field_filling([field], {"full_name": "テスト"})

    assert field.field_name == "search"
    assert planned[0].will_fill is False


def test_profile_aliases_fill_postal_phone_and_address():
    fields = [
        detect_field_from_metadata(_metadata(label_text="郵便番号", selector="#postal")),
        detect_field_from_metadata(_metadata(label_text="電話番号", selector="#phone")),
        detect_field_from_metadata(_metadata(label_text="住所", selector="#address")),
    ]
    planned = FieldMapper().map_fields(
        fields,
        {"zipcode": "1000001", "tel": "09000000000", "address": "東京都千代田区"},
    )

    assert [field.will_fill for field in planned] == [True, True, True]


def test_age_is_derived_from_birthdate_when_age_fill_is_allowed():
    field = detect_field_from_metadata(_metadata(input_type="number", label_text="年齢", selector="#age"))
    planned = FieldMapper().map_fields(
        [field],
        {"birth_year": "1980", "birth_month": "1", "birth_day": "1"},
        allow_birthdate_fill=True,
    )

    assert planned[0].will_fill is True
    assert planned[0].value_preview
