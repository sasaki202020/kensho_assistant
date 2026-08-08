from kensho_assistant.app.high_value.sources import SOURCE_LAYOUT_CHANGED, parse_listing
from kensho_assistant.app.high_value.importer import merge_imported_campaigns


def test_knshow_fixture_adapter_returns_candidates():
    html = '<ol class="KnshowList"><li><h3 class="listTitle"><a href="/detail/a.html">商品券5万円</a></h3><div class="listP">提供：主催社 締切：2026-09-01</div><a href="/rd/a">応募</a></li></ol>'
    rows = parse_listing("knshow", html, "https://www.knshow.com/list/s4/")
    assert rows[0]["source"] == "knshow"
    assert rows[0]["campaign_name"] == "商品券5万円"


def test_chance_fixture_adapter_is_user_initiated_only():
    html = '<article class="campaign"><a class="title" href="https://chance.com/c/1">旅行券10万円</a><span class="deadline">締切：2026-09-02</span><span class="sponsor">提供：旅行社</span></article>'
    rows = parse_listing("chance", html, "https://chance.com/list")
    assert rows[0]["source"] == "chance"
    assert rows[0]["source_mode"] == "user_initiated"


def test_kenkaku_fixture_adapter_is_user_initiated_only():
    html = '<div class="entry"><h2><a href="/campaign/2">車プレゼント</a></h2><p class="prize">賞品：車</p><p class="deadline">締切：2026-09-03</p></div>'
    rows = parse_listing("ken-kaku", html, "https://ken-kaku.com/list")
    assert rows[0]["source"] == "ken-kaku"
    assert rows[0]["source_mode"] == "user_initiated"


def test_unknown_or_empty_layout_fails_closed():
    try:
        parse_listing("chance", "<html></html>", "https://chance.com/list")
    except SOURCE_LAYOUT_CHANGED as exc:
        assert str(exc) == "SOURCE_LAYOUT_CHANGED"
    else:
        raise AssertionError("layout change must fail closed")


def test_same_official_campaign_from_two_sources_is_merged():
    existing = [{
        "campaign_id": "one",
        "campaign_name": "同じ懸賞",
        "provider": "主催社",
        "deadline": "2026-09-01",
        "official_campaign_url_raw": "https://example.com/campaign?id=7&utm_source=knshow",
        "source_urls": "https://knshow.com/detail/1",
    }]
    imported = [{
        "campaign_id": "two",
        "campaign_name": "同じ懸賞",
        "provider": "主催社",
        "deadline": "2026-09-01",
        "official_campaign_url_raw": "https://example.com/campaign?id=7&utm_source=chance",
        "source_url": "https://chance.com/list",
    }]
    rows = merge_imported_campaigns(existing, imported)
    assert len(rows) == 1
    assert "https://chance.com/list" in rows[0]["source_urls"]
