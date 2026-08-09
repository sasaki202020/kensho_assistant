from kensho_assistant.app.high_value.ranking import (
    assess_campaign,
    application_mode,
    canonical_campaign_key,
    filter_high_value_campaigns,
    recommendation_tier,
)
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


def test_high_value_display_keeps_manual_routes_visible():
    rows = [
        {"campaign_id": "sns", "campaign_name": "現金10万円", "status": "X_ACTION_REQUIRED", "prize": "現金10万円"},
        {"campaign_id": "member", "campaign_name": "旅行券", "status": "MEMBER_REGISTRATION_REQUIRED", "prize": "旅行券10万円"},
        {"campaign_id": "purchase", "campaign_name": "新車", "status": "PURCHASE_REQUIRED", "prize": "購入支援30万円"},
    ]

    assessed = filter_high_value_campaigns(rows)

    assert {row["campaign_id"] for row in assessed} == {"sns", "member", "purchase"}
    assert {row["application_mode"] for row in assessed} == {"X_MANUAL", "MEMBER_REGISTRATION_REQUIRED", "PURCHASE_REQUIRED"}
    assert all(row["discovery_status"] == "DISPLAY" for row in assessed)


def test_only_explicitly_ready_form_is_auto_fill_available():
    assert application_mode({"form_readiness_status": "READY_FOR_FILL"}) == "AUTO_FILL_AVAILABLE"
    assert application_mode({"status": "SAFE_TO_FILL", "form_readiness_status": "NO_FORM"}) == "UNSUPPORTED"
    assert application_mode({"status": "SAFE_TO_FILL"}) == "REVIEW_REQUIRED"


def test_manual_routes_never_become_fill_queue_route():
    for status in ("X_ACTION_REQUIRED", "INSTAGRAM_ACTION_REQUIRED", "LINE_ACTION_REQUIRED", "MEMBER_REGISTRATION_REQUIRED", "PURCHASE_REQUIRED"):
        assert application_mode({"status": status, "form_readiness_status": "READY_FOR_FILL"}) != "AUTO_FILL_AVAILABLE"


def test_recommendation_requires_verified_application_url_without_hiding_campaign():
    row = assess_campaign({
        "campaign_id": "manual",
        "campaign_name": "現金10万円",
        "status": "X_ACTION_REQUIRED",
        "entry_url": "https://example.invalid/entry",
        "prize": "現金10万円",
    })

    assert row["is_high_value"] is True
    assert row["application_mode"] == "X_MANUAL"
    assert row["recommendation_tier"] == "skip"
    assert row["recommendation_reason"] == "公式応募URLが未確認"


def test_verified_manual_campaign_is_conditional_and_deadline_bucket_is_visible():
    row = assess_campaign({
        "campaign_id": "manual",
        "campaign_name": "旅行券10万円",
        "status": "X_ACTION_REQUIRED",
        "official_campaign_url_raw": "https://example.invalid/campaign",
        "prize": "旅行券10万円",
        "deadline": "8月10日（残り 1日）",
    })

    assert recommendation_tier(row)[0] == "conditional"
    assert row["recommendation_label"] == "条件付き"
    assert row["deadline_bucket"] == "tomorrow"
    assert row["deadline_label"] == "あと1日"


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
