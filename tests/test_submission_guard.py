from __future__ import annotations

from playwright.sync_api import sync_playwright

from kensho_assistant.app.submission_guard import (
    install_submission_guard,
    install_submission_guard_on_context,
    release_submission_guard,
)


class FakePage:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def evaluate(self, script: str):
        self.scripts.append(script)
        return {"blockedAttempts": 0}


class FakeContext:
    def __init__(self) -> None:
        self.init_scripts: list[str] = []

    def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)


def test_guard_can_be_registered_before_navigation_on_browser_context() -> None:
    context = FakeContext()
    install_submission_guard_on_context(context)
    assert len(context.init_scripts) == 1
    assert "__kenshoSubmitGuard" in context.init_scripts[0]


def test_guard_blocks_all_automatic_submission_paths_during_fill() -> None:
    page = FakePage()
    install_submission_guard(page)
    script = page.scripts[-1]
    assert "keydown" in script
    assert "Enter" in script
    assert "requestSubmit" in script
    assert "HTMLFormElement.prototype.submit" in script
    assert "button[type=submit]" in script
    assert "preventDefault" in script


def test_guard_can_be_released_for_explicit_human_handoff() -> None:
    page = FakePage()
    install_submission_guard(page)
    release_submission_guard(page)
    assert "release" in page.scripts[-1]


def test_guard_blocks_browser_submission_paths_until_human_handoff() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            """
            <form id="entry">
              <input id="name" name="name">
              <button id="submit-button" type="submit">送信</button>
            </form>
            <script>
              window.humanSubmitEvents = 0;
              document.querySelector('#entry').addEventListener('submit', (event) => {
                event.preventDefault();
                window.humanSubmitEvents += 1;
              });
            </script>
            """
        )
        install_submission_guard(page)

        page.click("#submit-button")
        page.press("#name", "Enter")
        page.evaluate("document.querySelector('#entry').submit()")
        page.evaluate("document.querySelector('#entry').requestSubmit()")

        snapshot = page.evaluate("window.__kenshoSubmitGuard.snapshot()")
        assert snapshot["blockedAttempts"] == 4
        assert set(snapshot["reasons"]) == {
            "submit_control_click",
            "enter_key",
            "form.submit",
            "requestSubmit",
        }
        assert page.evaluate("window.humanSubmitEvents") == 0

        release_submission_guard(page)
        page.evaluate("document.querySelector('#entry').requestSubmit()")
        assert page.evaluate("window.humanSubmitEvents") == 1
        browser.close()


def test_context_guard_survives_navigation_and_blocks_iframe_submission() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        install_submission_guard_on_context(context)
        page = context.new_page()
        page.set_content(
            """
            <iframe id="child" srcdoc="
              <form id='entry' action='data:text/plain,submitted'>
                <input id='name' name='name'>
                <button id='submit-button' type='submit'>送信</button>
              </form>">
            </iframe>
            """
        )
        frame = page.frame_locator("#child")
        frame.locator("#submit-button").click()
        frame.locator("#name").press("Enter")
        frame.locator("#entry").evaluate("form => form.submit()")
        frame.locator("#entry").evaluate("form => form.requestSubmit()")

        snapshot = page.frames[1].evaluate("window.__kenshoSubmitGuard.snapshot()")
        assert snapshot["blockedAttempts"] == 4
        assert page.frames[1].url == "about:srcdoc"
        context.close()
        browser.close()
