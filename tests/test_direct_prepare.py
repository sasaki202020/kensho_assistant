from __future__ import annotations

from pathlib import Path

import pytest

from kensho_assistant.app.direct_prepare import (
    install_human_handoff_control,
    prepare_page_without_submit,
)
from kensho_assistant.app.submission_guard import (
    install_submission_guard_on_context,
    submission_guard_snapshot,
)


FIXTURE = (
    Path(__file__).resolve().parent
    / "extension_fixtures"
    / "combined_japanese_form.html"
)


def _dummy_profile() -> dict[str, str]:
    return {
        "last_name": "テスト",
        "first_name": "太郎",
        "last_name_kana": "テスト",
        "first_name_kana": "タロウ",
        "postal_code": "000-2741",
        "prefecture": "栃木県",
        "city": "宇都宮市",
        "address1": "テスト町1-2-3",
        "address2": "テストビル101",
        "phone": "090-0000-2741",
        "email": "pii-test-92741@example.invalid",
        "gender": "男性",
        "birth_year": "1990",
        "birth_month": "4",
        "birth_day": "1",
    }


def test_direct_prepare_fills_reviewable_fields_without_submitting() -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        install_submission_guard_on_context(context)
        page = context.new_page()
        page.goto(FIXTURE.as_uri(), wait_until="domcontentloaded")

        result = prepare_page_without_submit(
            page,
            _dummy_profile(),
            prize_choice="商品A",
            free_text="地域の情報を毎回楽しみにしています。",
        )

        assert result.submitted is False
        assert page.locator("#name").input_value() == "テスト 太郎"
        assert page.locator("#kana").input_value() == "テスト タロウ"
        assert page.locator("#zip").input_value() == "000-2741"
        assert page.locator("#age").input_value().isdigit()
        assert page.get_by_label("男性").is_checked()
        assert page.get_by_label("商品A").is_checked()
        assert (
            page.locator('textarea[name="applicant[comment]"]').input_value()
            == "地域の情報を毎回楽しみにしています。"
        )
        assert submission_guard_snapshot(page)["blockedAttempts"] == 0

        page.locator("#submit-button").click()
        assert submission_guard_snapshot(page)["blockedAttempts"] == 1
        assert page.url == FIXTURE.as_uri()
        context.close()
        browser.close()


def test_human_handoff_releases_guard_without_automatic_submission() -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        install_submission_guard_on_context(context)
        page = context.new_page()
        page.set_content(
            """
            <form id="entry"><button type="submit">送信</button></form>
            <script>
              window.submitEvents = 0;
              document.querySelector('#entry').addEventListener(
                'submit',
                event => { event.preventDefault(); window.submitEvents += 1; }
              );
            </script>
            """
        )

        install_human_handoff_control(page)
        host = page.locator("[data-kensho-human-handoff]")
        assert host.count() == 1
        box = host.bounding_box()
        assert box is not None

        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

        assert page.evaluate("window.__kenshoSubmitGuard.active") is False
        assert page.evaluate("window.submitEvents") == 0
        context.close()
        browser.close()
