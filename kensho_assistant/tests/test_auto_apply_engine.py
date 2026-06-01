from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from kensho_assistant.app.auto_apply_engine import AutoApplyEngine
from kensho_assistant.app.apply_run_logger import append_apply_run
from kensho_assistant.app.paths import APPLY_RUNS_DIR, FORM_ANALYSIS_DIR, PRE_SUBMIT_CHECKS_DIR
from kensho_assistant.app.submit_adapters.mock_submit import MockSubmitAdapter
from kensho_assistant.app.submit_adapters.real_submit import RealSubmitAdapter
from kensho_assistant.main import _print_apply_result


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


def test_dry_run_never_clicks_submit_and_saves_artifacts():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(_form_url("basic.html"))
        result = AutoApplyEngine("dry_run").run(page, _campaign("dry_real_site.html"), PROFILE)
        record = result["record"]
        assert record["submit_attempted"] is False
        assert record["submit_clicked"] is False
        assert record["auto_submitted"] is False
        assert "submitted.html" not in page.url
        assert (FORM_ANALYSIS_DIR / "dry_real_site.json").exists()
        assert (PRE_SUBMIT_CHECKS_DIR / "dry_real_site.json").exists()
        assert Path(str(record["screenshot_path"])).exists()
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
