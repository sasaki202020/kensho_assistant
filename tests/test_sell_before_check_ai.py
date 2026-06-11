"""sell_before_check_ai のテスト。

py -3 -m pytest tests/test_sell_before_check_ai.py -q
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sell_before_check_ai.app import app
from sell_before_check_ai.logic import CHECK_TYPES, evaluate, load_rules

client = TestClient(app)

LEVEL_LABELS = ["問題なさそう", "確認推奨", "即決注意", "相談推奨"]


def test_rules_define_exactly_four_levels():
    rules = load_rules()
    assert [lv["label"] for lv in rules["levels"]] == LEVEL_LABELS


def test_evaluate_ok_level_for_plain_text():
    verdict = evaluate("古いテレビを処分したいと思っています。", "item", [])
    assert verdict["level_label"] == "問題なさそう"
    assert verdict["score"] == 0
    assert verdict["stored"] is False


def test_evaluate_check_level_for_single_mild_keyword():
    verdict = evaluate("高価買取のチラシが入っていた", "flyer", [])
    assert verdict["level_label"] == "確認推奨"


def test_evaluate_caution_level_for_rush_keywords():
    verdict = evaluate("本日限り! 今だけのチャンス!", "flyer", [])
    assert verdict["level_label"] == "即決注意"


def test_evaluate_consult_level_for_stacked_signals():
    verdict = evaluate("本日限り、キャンセル不可と言われた", "quote", ["visit", "rush"])
    assert verdict["level_label"] == "相談推奨"
    assert verdict["score"] >= 5


def test_evaluate_expanded_keywords_hit():
    # v0.3.0 で拡充したキーワードが判定に反映されること
    assert evaluate("本日中なら特別価格です", "quote", [])["score"] >= 4
    assert evaluate("古銭と記念硬貨と腕時計を売りたい", "item", [])["score"] >= 3
    assert evaluate("出張費無料・査定額アップ", "flyer", [])["score"] >= 2


def test_evaluate_keywords_respect_check_type_targets():
    # 「一式」は見積もり向けキーワードであり、チラシ判定では加点しない
    assert evaluate("一式", "quote", [])["score"] > 0
    assert evaluate("一式", "flyer", [])["score"] == 0


def test_evaluate_never_returns_label_outside_four_levels():
    samples = ["", "貴金属 着物 形見", "本日限り キャンセル不可 その場で現金 一式"]
    for check_type in CHECK_TYPES:
        for text in samples:
            verdict = evaluate(text, check_type, ["visit", "rush", "extra_item"])
            assert verdict["level_label"] in LEVEL_LABELS


def test_home_page_links_to_all_checks():
    res = client.get("/")
    assert res.status_code == 200
    for path in ["/flyer-check", "/item-check", "/quote-check",
                 "/refusal-examples", "/market-links", "/hotline-188"]:
        assert path in res.text


@pytest.mark.parametrize("path,title", [
    ("/flyer-check", "チラシチェック"),
    ("/item-check", "商品チェック"),
    ("/quote-check", "見積もりチェック"),
])
def test_check_pages_render(path, title):
    res = client.get(path)
    assert res.status_code == 200
    assert title in res.text


def test_result_post_renders_verdict_and_aids():
    res = client.post("/result", data={
        "check_type": "flyer",
        "text": "本日限り! どんなものでも高価買取!",
        "flags": ["visit"],
    })
    assert res.status_code == 200
    assert "診断結果" in res.text
    assert any(label in res.text for label in LEVEL_LABELS)
    assert "断り文例" in res.text
    assert "188" in res.text
    assert "保証" in res.text  # 免責文言


def test_result_get_shows_sample():
    res = client.get("/result")
    assert res.status_code == 200
    assert "サンプル" in res.text


@pytest.mark.parametrize("view", ["home", "flyer", "item", "quote", "result"])
def test_mobile_preview_views(view):
    res = client.get(f"/mobile-preview?view={view}")
    assert res.status_code == 200
    assert "iframe" in res.text


def test_info_pages_render():
    assert "188" in client.get("/hotline-188").text
    assert "免責" in client.get("/disclaimer").text
    assert "プライバシー" in client.get("/privacy").text
    assert "削除" in client.get("/settings").text
    assert "コピー" in client.get("/refusal-examples").text
    assert "相場" in client.get("/market-links").text


def test_api_check_returns_verdict_json():
    res = client.post("/api/check", json={
        "check_type": "quote",
        "text": "買取一式 30000円 キャンセル不可",
        "flags": ["no_doc"],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["level_label"] in LEVEL_LABELS
    assert body["stored"] is False
    assert body["hits"]


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_no_prohibited_accusatory_wording_in_rules():
    # 特定業者を断定する表現を判定文言に含めない
    raw = json.dumps(load_rules(), ensure_ascii=False)
    for ng in ["悪徳", "詐欺業者", "違法業者"]:
        assert ng not in raw


def test_ios_rules_copy_is_in_sync():
    # iOSアプリ(Capacitor www)に同梱するルールがPython側と一致していること
    www_rules = Path(__file__).parent.parent / "ios_app" / "www" / "rules.js"
    assert www_rules.exists(), "scripts/sync_ios_assets.py を実行してください"
    text = www_rules.read_text(encoding="utf-8")
    payload = text[text.index("{"): text.rindex("}") + 1]
    assert json.loads(payload) == load_rules()
