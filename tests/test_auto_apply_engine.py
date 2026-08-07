from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from kensho_assistant.app.answer_assistant import build_answer_pack
from kensho_assistant.app.auto_apply_engine import AutoApplyEngine
from kensho_assistant.app.pre_submit_verifier import _body_requires_login
from kensho_assistant.app.apply_run_logger import append_apply_run
from kensho_assistant.app.paths import APPLY_RUNS_DIR, FORM_ANALYSIS_DIR, PRE_SUBMIT_CHECKS_DIR
from kensho_assistant.app.site_templates import match_site_template
from kensho_assistant.app.submit_adapters.mock_submit import MockSubmitAdapter
from kensho_assistant.app.submit_adapters.real_submit import RealSubmitAdapter
from kensho_assistant.main import _print_apply_result
from kensho_assistant.web.app import _review_item_summary


PROFILE = {
    "last_name": "山田",
    "first_name": "太郎",
    "postal_code": "100-0001",
    "prefecture": "東京都",
    "city": "千代田区",
    "address1": "千代田1-1",
    "phone": "09000001234",
    "email": "test@example.com",
    "gender": "男性",
    "birth_year": "1980",
    "birth_month": "1",
    "birth_day": "1",
    "age_group": "30代",
    "occupation": "会社員",
    "marital_status": "未婚",
    "children": "なし",
    "survey_choice": "A",
    "prize_choice": "2",
    "entry_count": "1",
}


def _form_url(name: str) -> str:
    return (Path(__file__).parent / "mock_forms" / name).resolve().as_uri()


def _campaign(name: str) -> dict[str, str]:
    return {"campaign_id": Path(name).stem, "campaign_name": name, "resolved_entry_url": _form_url(name)}


def test_mock_mode_submits_basic_form_only():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("basic.html"))
        result = AutoApplyEngine("mock").run(page, _campaign("basic.html"), PROFILE)
        assert result["record"]["auto_submitted"] is True
        assert result["record"]["status"] == "MOCK_SUBMITTED"
        assert "submitted.html" in page.url
        browser.close()


def test_mock_mode_does_not_submit_danger_or_review_forms():
    for form in ["quiz.html", "consent.html", "captcha.html", "login.html"]:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(_form_url(form))
            result = AutoApplyEngine("mock").run(page, _campaign(form), PROFILE)
            assert result["record"]["auto_submitted"] is False
            assert "submitted.html" not in page.url
            browser.close()


def test_ai_answer_pack_generates_quiz_and_comment_candidates():
    campaign = {
        "campaign_id": "quiz-ai",
        "campaign_name": "福岡県産品キャンペーン",
        "prize": "特産品",
        "provider": "福岡県",
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("quiz_ai.html"))
        answer_pack = build_answer_pack(page, campaign, PROFILE, match_site_template(page.url))
        browser.close()
    assert answer_pack["quiz_answer"] == "福岡県"
    assert "福岡県産の農林水産物" in answer_pack["comment_text"]
    assert answer_pack["quiz_suggestions"]
    assert answer_pack["quiz_suggestions"][0]["suggested_answer"] == "福岡県"


def test_mock_mode_ai_forms_submit_when_candidates_are_confident():
    campaign = {
        "campaign_id": "quiz-ai",
        "campaign_name": "福岡県産品キャンペーン",
        "prize": "特産品",
        "provider": "福岡県",
    }
    for form in ["quiz_ai.html", "comment.html"]:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(_form_url(form))
            result = AutoApplyEngine("mock").run(page, campaign, PROFILE)
            record = result["record"]
            assert record["auto_submitted"] is True
            assert record["status"] == "MOCK_SUBMITTED"
            assert "submitted.html" in page.url
            assert record["filled_fields_count"] >= 1
            if form == "quiz_ai.html":
                assert record["ai_quiz_resolved"] is True
                quiz_item = next(item for item in result["pre_submit_check"]["review_items"] if isinstance(item, dict) and item.get("kind") == "quiz")
                assert any(
                    isinstance(item, dict) and item.get("suggested_answer") == "福岡県"
                    for item in result["pre_submit_check"]["review_items"]
                )
                assert "候補=福岡県" in _review_item_summary(quiz_item)
            else:
                assert record["ai_comment_resolved"] is True
                comment_item = next(item for item in result["pre_submit_check"]["review_items"] if isinstance(item, dict) and item.get("kind") == "free_text")
                assert any(
                    isinstance(item, dict) and str(item.get("suggested_text", "")).strip()
                    for item in result["pre_submit_check"]["review_items"]
                )
                assert "候補=" in _review_item_summary(comment_item)
            browser.close()


def test_dry_run_never_clicks_submit_and_saves_artifacts():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("quiz_ai.html"))
        result = AutoApplyEngine("dry_run").run(page, _campaign("dry_real_site.html"), PROFILE)
        record = result["record"]
        assert record["status"] == "REVIEW_FILL_READY"
        assert record["submit_attempted"] is False
        assert record["submit_clicked"] is False
        assert record["auto_submitted"] is False
        assert record["submit_button_detected"] is True
        assert record["pre_submit_score"] == 80
        assert "submitted.html" not in page.url
        assert (FORM_ANALYSIS_DIR / "dry_real_site.json").exists()
        check_path = PRE_SUBMIT_CHECKS_DIR / "dry_real_site.json"
        assert check_path.exists()
        check_data = json.loads(check_path.read_text(encoding="utf-8"))
        assert check_data["status"] == "REVIEW_FILL_READY"
        assert check_data["submit_button_detected"] is True
        assert check_data["html_snapshot_path"]
        assert any(
            isinstance(item, dict) and item.get("suggested_answer") == "福岡県"
            for item in check_data["review_items"]
        )
        assert Path(str(record["screenshot_path"])).exists()
        assert Path(str(record["html_snapshot_path"])).exists()
        browser.close()


def test_pilot_dry_run_does_not_persist_normal_artifacts(monkeypatch, tmp_path):
    analysis_dir = tmp_path / "analysis"
    check_dir = tmp_path / "checks"
    apply_runs: list[dict[str, object]] = []
    monkeypatch.setattr("kensho_assistant.app.form_analyzer.FORM_ANALYSIS_DIR", analysis_dir)
    monkeypatch.setattr("kensho_assistant.app.pre_submit_verifier.PRE_SUBMIT_CHECKS_DIR", check_dir)
    monkeypatch.setattr("kensho_assistant.app.auto_apply_engine.append_apply_run", lambda record: apply_runs.append(record))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("selects.html"))
        result = AutoApplyEngine("dry_run").run(
            page,
            _campaign("pilot-no-persist.html"),
            PROFILE,
            persist_artifacts=False,
        )
        browser.close()

    record = result["record"]
    assert record["submit_clicked"] is False
    assert record["auto_submitted"] is False
    assert record["screenshot_path"] == ""
    assert record["html_snapshot_path"] == ""
    assert record["analysis_path"] == ""
    assert record["check_path"] == ""
    assert not analysis_dir.exists()
    assert not check_dir.exists()
    assert apply_runs == []


def test_dry_run_advances_from_landing_page_but_never_submits():
    campaign = {
        "campaign_id": "entry-navigation",
        "campaign_name": "図書カードプレゼント",
        "resolved_entry_url": _form_url("entry_landing.html"),
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("entry_landing.html"))
        result = AutoApplyEngine("dry_run").run(page, campaign, PROFILE)
        record = result["record"]

        assert record["entry_navigation_clicked_count"] == 1
        assert record["filled_fields_count"] >= 1
        assert page.locator("#last_name").input_value() == PROFILE["last_name"]
        assert record["submit_clicked"] is False
        assert record["auto_submitted"] is False
        assert "submitted.html" not in page.url
        browser.close()


def test_dry_run_does_not_fill_expired_campaign():
    campaign = {
        "campaign_id": "expired-entry",
        "campaign_name": "図書カードプレゼント",
        "provider": "テスト提供元",
        "resolved_entry_url": _form_url("expired_entry_form.html"),
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("expired_entry_form.html"))
        result = AutoApplyEngine("dry_run").run(page, campaign, PROFILE)
        record = result["record"]

        assert page.locator("#email").input_value() == ""
        assert record["status"] == "SKIPPED"
        assert "campaign_ended" in record["needs_review_reasons"]
        assert record["submit_clicked"] is False
        assert record["auto_submitted"] is False
        browser.close()


def test_dry_run_treats_site_search_only_page_as_no_form():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("search_only.html"))
        result = AutoApplyEngine("dry_run").run(page, _campaign("search_only.html"), PROFILE)
        record = result["record"]

        assert record["status"] == "SKIPPED"
        assert record["filled_fields_count"] == 0
        assert "no_form" in record["needs_review_reasons"]
        assert record["submit_clicked"] is False
        browser.close()


def test_pre_submit_statuses_cover_review_manual_and_skip():
    cases = {
        "quiz.html": "REVIEW_FILL_READY",
        "consent.html": "REVIEW_FILL_READY",
        "login.html": "MANUAL_ASSIST_READY",
        "captcha.html": "SKIPPED",
    }
    for form, expected_status in cases.items():
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(_form_url(form))
            result = AutoApplyEngine("dry_run").run(page, _campaign(form), PROFILE)
            assert result["record"]["status"] == expected_status
            assert result["record"]["submit_clicked"] is False
            assert result["record"]["auto_submitted"] is False
            browser.close()


def test_authentication_and_captcha_pages_stop_before_profile_fill():
    for form in ["captcha.html", "login.html"]:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(_form_url(form))
            result = AutoApplyEngine("dry_run").run(
                page,
                _campaign(form),
                PROFILE,
                persist_artifacts=False,
            )
            assert page.locator('input[type="email"]').input_value() == ""
            assert result["record"]["filled_fields_count"] == 0
            assert result["record"]["page_guard_reason"] in {"captcha_detected", "login_required"}
            browser.close()


def test_select_form_fills_choice_fields_and_scores_high():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("selects.html"))
        result = AutoApplyEngine("dry_run").run(page, _campaign("selects.html"), PROFILE)
        record = result["record"]
        assert record["status"] == "PRE_SUBMIT_READY"
        assert record["filled_fields_count"] >= 7
        assert record["fill_completion_rate"] >= 60
        assert record["pre_submit_score"] >= 90
        assert record["submit_button_detected"] is True
        browser.close()


def test_fuzzy_choice_form_matches_partial_and_alias_values():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("fuzzy_choices.html"))
        result = AutoApplyEngine("dry_run").run(page, _campaign("fuzzy_choices.html"), PROFILE)
        record = result["record"]
        assert record["status"] == "PRE_SUBMIT_READY"
        assert record["filled_fields_count"] >= 6
        assert record["unresolved_required_fields_count"] == 0
        assert record["submit_button_detected"] is True
        assert record["submit_clicked"] is False
        assert record["auto_submitted"] is False
        browser.close()


def test_site_template_match_and_recording():
    template = match_site_template("https://www.fs-fukuoka.com/enjoy/present")
    assert template.template_id == "fs_fukuoka_present"
    assert "年齢" in template.manual_review_terms
    soft_matched = match_site_template(
        "https://www.fs-fukuoka.com/other/path",
        page_text="福岡県産の農林水産物 / 確認画面へ / 送信",
    )
    assert soft_matched.template_id == "fs_fukuoka_present"
    assert soft_matched.signal_score("福岡県産の農林水産物 / 確認画面へ / 送信")[0] > 0
    template_match = match_site_template("https://form.run/other", page_text="応募口数 / 回答を送信")
    assert template_match.template_id == "formrun_campaign"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("basic.html"))
        result = AutoApplyEngine("mock").run(page, _campaign("basic.html"), PROFILE)
        assert result["record"]["site_template_id"] == "generic"
        assert result["record"]["site_template_label"]
        assert "site_name" in result["record"]
        assert "confirmation_button_texts" in result["analysis"]
        browser.close()


def test_mock_forms_cover_confirmation_radio_quiz_and_select_variants():
    cases = {
        "confirmation_screen.html": {"SKIPPED"},
        "multi_radio.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY", "PRE_SUBMIT_READY"},
        "required_checkbox.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
        "multi_quiz.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
        "weird_select.html": {"PRE_SUBMIT_READY", "REVIEW_FILL_READY"},
        "confirm_submit_confusing.html": {"PRE_SUBMIT_READY", "REVIEW_FILL_READY"},
        "alt_submit_text.html": {"REVIEW_FILL_READY", "PRE_SUBMIT_READY"},
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for form, expected_statuses in cases.items():
            page = browser.new_page()
            page.goto(_form_url(form))
            result = AutoApplyEngine("dry_run").run(page, _campaign(form), PROFILE)
            record = result["record"]
            assert record["submit_clicked"] is False
            assert record["auto_submitted"] is False
            assert record["submit_attempted"] is False
            assert record["status"] in expected_statuses
            if form == "confirmation_screen.html":
                assert "no_form" in record["skip_reason"] or record["status"] == "SKIPPED"
            elif form == "multi_radio.html":
                if record["status"] == "PRE_SUBMIT_READY":
                    assert record["unresolved_required_fields_count"] == 0
                    assert not result["pre_submit_check"]["required_radio_unselected"]
                else:
                    assert any(isinstance(item, dict) and item.get("kind") == "radio" for item in result["pre_submit_check"]["review_items"])
            elif form == "multi_quiz.html":
                assert any(isinstance(item, dict) and item.get("kind") == "quiz" for item in result["pre_submit_check"]["review_items"])
                assert result["pre_submit_check"]["human_checklist"] or result["pre_submit_check"]["ai_candidates"]
            elif form == "weird_select.html":
                assert record["unresolved_required_fields_count"] == 0
                assert record["pre_submit_score"] >= 90
            elif form == "confirm_submit_confusing.html":
                assert result["analysis"]["submit_button_candidates"]
                assert any("確認画面へ" in str(candidate.get("text", "")) for candidate in result["analysis"]["submit_button_candidates"])
                assert any("送信" in str(candidate.get("text", "")) for candidate in result["analysis"]["submit_button_candidates"])
            elif form == "alt_submit_text.html":
                assert result["analysis"]["submit_button_candidates"]
            page.close()
        browser.close()


def test_real_submit_adapter_is_disabled():
    try:
        RealSubmitAdapter().submit(None, {})
    except RuntimeError as exc:
        assert "not implemented" in str(exc)
    else:
        raise AssertionError("RealSubmitAdapter must raise")


def test_mock_submit_blocks_non_allowed_url():
    class Page:
        url = "https://example.com/form"

    try:
        MockSubmitAdapter().submit(Page(), {})
    except RuntimeError as exc:
        assert "blocked" in str(exc)
    else:
        raise AssertionError("non-allowed mock submit must raise")


def test_apply_run_logger_removes_pii_query_values(tmp_path, monkeypatch):
    monkeypatch.setattr("kensho_assistant.app.apply_run_logger.APPLY_RUNS_DIR", tmp_path)
    path = append_apply_run(
        {
            "campaign_id": "x",
            "title": "x",
            "url": "https://example.com/apply?email=test@example.com&name=山田太郎",
            "run_mode": "dry_run",
            "status": "DRY_RUN_COMPLETED",
        }
    )
    text = path.read_text(encoding="utf-8")
    assert "test@example.com" not in text
    assert "山田太郎" not in text
    assert "https://example.com/apply" in text


def test_print_apply_result_includes_review_reasons_and_paths(capsys):
    _print_apply_result(
        {
            "campaign_id": "campaign-1",
            "status": "DRY_RUN_COMPLETED",
            "filled_fields_count": 4,
            "submit_attempted": False,
            "submit_clicked": False,
            "auto_submitted": False,
            "needs_review_reasons": ["quiz detected", "manual consent required"],
            "screenshot_path": "screenshots/dry_run/campaign-1.png",
            "analysis_path": "data/form_analysis/campaign-1.json",
            "check_path": "data/pre_submit_checks/campaign-1.json",
        }
    )
    output = capsys.readouterr().out
    assert "needs_review_reasons: quiz detected; manual consent required" in output
    assert "screenshot_path: screenshots/dry_run/campaign-1.png" in output
    assert "analysis_path: data/form_analysis/campaign-1.json" in output
    assert "check_path: data/pre_submit_checks/campaign-1.json" in output
def test_login_detection_ignores_prize_redemption_membership_note():
    assert _body_requires_login("賞品の利用にあたって会員登録をしていただく必要があります") is False
    assert _body_requires_login("応募にはログインが必要です") is True
