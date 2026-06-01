from kensho_assistant.app.campaign_classifier import classify_campaign
from kensho_assistant.app.safety_checker import evaluate_safety


def test_web_form_safe_to_fill():
    row = {"campaign_id": "abc", "entry_type_raw": "カンタン応募", "campaign_name": "フォーム応募", "description": "Webフォーム"}
    decision = evaluate_safety(row, classify_campaign(row), existing_entries=[])
    assert decision.status == "SAFE_TO_FILL"


def test_age_restricted_is_blocked():
    row = {"campaign_id": "abc", "entry_type_raw": "20歳以上限定", "campaign_name": "年齢制限", "description": ""}
    decision = evaluate_safety(row, classify_campaign(row), existing_entries=[])
    assert decision.status == "AGE_RESTRICTED"


def test_purchase_required_is_blocked():
    row = {"campaign_id": "abc", "entry_type_raw": "購入必須", "campaign_name": "購入条件", "description": ""}
    decision = evaluate_safety(row, classify_campaign(row), existing_entries=[])
    assert decision.status == "PURCHASE_REQUIRED"


def test_receipt_required_is_blocked():
    row = {"campaign_id": "abc", "entry_type_raw": "レシート応募", "campaign_name": "レシート条件", "description": ""}
    decision = evaluate_safety(row, classify_campaign(row), existing_entries=[])
    assert decision.status == "RECEIPT_REQUIRED"

