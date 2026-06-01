from kensho_assistant.app.campaign_classifier import classify_campaign


def test_x_campaign_is_detected():
    row = {"entry_type_raw": "X懸賞(Twitter懸賞)", "campaign_name": "テスト", "description": ""}
    assert classify_campaign(row).entry_type == "X_CAMPAIGN"


def test_line_campaign_is_detected():
    row = {"entry_type_raw": "LINE懸賞", "campaign_name": "テスト", "description": ""}
    assert classify_campaign(row).entry_type == "LINE_CAMPAIGN"


def test_instagram_campaign_is_detected():
    row = {"entry_type_raw": "Instagram懸賞", "campaign_name": "テスト", "description": ""}
    assert classify_campaign(row).entry_type == "INSTAGRAM_CAMPAIGN"


def test_captcha_is_detected():
    row = {"entry_type_raw": "", "campaign_name": "テスト", "description": "reCAPTCHA を確認"}
    assert classify_campaign(row).entry_type == "CAPTCHA_REQUIRED"

