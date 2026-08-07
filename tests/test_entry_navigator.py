from pathlib import Path

from playwright.sync_api import sync_playwright

from kensho_assistant.app.entry_navigator import advance_to_entry_form


def _url(name: str) -> str:
    return (Path(__file__).parent / "mock_forms" / name).resolve().as_uri()


def test_navigator_clicks_intermediate_entry_link_and_stops_before_submit() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(_url("entry_landing.html"))

        result = advance_to_entry_form(page, max_steps=2)

        assert result.reached_form is True
        assert result.clicked_count == 1
        assert page.locator("#last_name").count() == 1
        assert "submitted.html" not in page.url
        browser.close()


def test_navigator_never_clicks_final_submit_button() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(_url("entry_form.html"))

        result = advance_to_entry_form(page, max_steps=2)

        assert result.reached_form is True
        assert result.clicked_count == 0
        assert "submitted.html" not in page.url
        browser.close()
