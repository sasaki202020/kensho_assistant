from kensho_assistant.app.campaign_classifier import classify_campaign
from kensho_assistant.app.safety_checker import evaluate_safety


def test_duplicate_campaign_id_is_detected():
    row = {"campaign_id": "dup", "entry_type_raw": "カンタン応募", "campaign_name": "重複", "provider": "社", "deadline": "2026-05-12", "entry_url": "https://example.com/apply"}
    existing_entries = [{"campaign_id": "dup", "entry_url": "", "campaign_name": "", "provider": "", "deadline": ""}]
    decision = evaluate_safety(row, classify_campaign(row), existing_entries=existing_entries)
    assert decision.status == "DUPLICATE_ENTRY"

