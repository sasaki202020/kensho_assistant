from kensho_assistant.app.campaign_page_guard import evaluate_campaign_page


def test_guard_stops_expired_campaign_before_filling() -> None:
    result = evaluate_campaign_page(
        {"campaign_name": "季節のジェラート8個セット", "provider": "JA東京アグリパーク"},
        "JA東京アグリパーク プレゼント企画 応募は終了しました。",
        page_title="第24回プレゼント企画",
    )

    assert result.safe_to_fill is False
    assert result.reason == "campaign_ended"


def test_guard_stops_when_prize_no_longer_matches_page() -> None:
    result = evaluate_campaign_page(
        {"campaign_name": "BIGうまい棒10種40本入り", "provider": "KURU KURA"},
        "KURU KURA お散歩クイズ 今回の賞品は亀田のありがとうセット2026夏です。",
        page_title="KURU KURAお散歩クイズ",
    )

    assert result.safe_to_fill is False
    assert result.reason == "campaign_mismatch"


def test_guard_allows_matching_active_campaign() -> None:
    result = evaluate_campaign_page(
        {"campaign_name": "図書カードネットギフト2000円分", "provider": "日本図書普及"},
        "日本図書普及 今月のクイズ。図書カードネットギフト2000円分をプレゼント。",
        page_title="今月のクイズ",
    )

    assert result.safe_to_fill is True
    assert result.reason == "matched"
