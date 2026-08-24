from __future__ import annotations

from pathlib import Path

import pytest

from kensho_assistant.app.form_detector import detect_fields


FIXTURES = Path(__file__).resolve().parent / "mock_forms"


@pytest.fixture()
def browser_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_detect_fields_uses_application_form_scope(browser_page) -> None:
    browser_page.goto((FIXTURES / "form_scope_noise.html").as_uri(), wait_until="domcontentloaded")

    fields = detect_fields(browser_page)

    assert {field.element_id for field in fields} == {
        "last-name",
        "first-name",
        "application-email",
    }


def test_detect_fields_fails_closed_when_application_form_scope_is_ambiguous(browser_page) -> None:
    browser_page.goto((FIXTURES / "form_scope_ambiguous.html").as_uri(), wait_until="domcontentloaded")

    assert detect_fields(browser_page) == []
