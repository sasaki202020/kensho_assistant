from kensho_assistant.app.high_value.ranking import assess_campaign, canonical_campaign_key
from kensho_assistant.app.high_value.value_parser import extract_yen_amounts, max_individual_value


def test_parse_common_yen_units():
    assert extract_yen_amounts("賞品 30,000円相当")[0].yen == 30_000
    assert extract_yen_amounts("3万円")[0].yen == 30_000
    assert extract_yen_amounts("100万円")[0].yen == 1_000_000
    assert extract_yen_amounts("5千円")[0].yen == 5_000
    assert extract_yen_amounts("1.5万円")[0].yen == 15_000
    assert extract_yen_amounts("Amazonギフトカード5万円分")[0].yen == 50_000


def test_total_amount_is_not_an_individual_prize():
    values = extract_yen_amounts("賞品総額100万円")
    assert values[0].is_total_amount is True
    assert max_individual_value(values) is None


def test_max_individual_value_ignores_campaign_total():
    values = extract_yen_amounts("現金20万円を1名、商品券1万円を20名、総額40万円")
    assert max_individual_value(values) == 200_000


def test_high_value_boundary_and_unknown_category():
    assert assess_campaign({"prize": "商品券29,999円"})["is_high_value"] is False
    assert assess_campaign({"prize": "商品券30,000円"})["value_review_status"] == "CONFIRMED"
    unknown = assess_campaign({"prize": "新車プレゼント", "category": "車"})
    assert unknown["value_review_status"] == "NEEDS_REVIEW"
    assert unknown["is_high_value"] is True


def test_manual_value_is_supported_without_guessing():
    result = assess_campaign({"prize": "旅行", "manual_value_yen": "50000"})
    assert result["max_individual_prize_value_yen"] == 50_000
    assert result["value_basis"] == "manual"
    assert result["value_review_status"] == "CONFIRMED"


def test_priority_is_explainable_and_bounded():
    result = assess_campaign({"prize": "現金10万円", "winner_count": "5", "entry_url": "https://example.com/apply"})
    assert 0 <= result["priority_score"] <= 100
    assert result["priority_reasons"]
    assert "当選確率" not in result["priority_label"]


def test_canonical_key_keeps_raw_url_separate_and_removes_tracking():
    row = {
        "campaign_name": "同じ懸賞",
        "provider": "主催社",
        "deadline": "2026-09-01",
        "official_campaign_url_raw": "https://example.com/campaign?id=7&utm_source=site",
    }
    result = assess_campaign(row)
    assert result["official_campaign_url_raw"].endswith("utm_source=site")
    assert canonical_campaign_key(row) == canonical_campaign_key({**row, "official_campaign_url_raw": "https://example.com/campaign?id=7&utm_medium=x"})

