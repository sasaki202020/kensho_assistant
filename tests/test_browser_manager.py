from pathlib import Path

import pytest

from kensho_assistant.app.browser_manager import (
    check_browser_doctor,
    dedicated_extension_page_state,
    get_browser_profile_dir,
    open_url_in_chrome,
    provision_extension_control_token,
)


def test_browser_profile_uses_dedicated_dir():
    path = get_browser_profile_dir()
    assert isinstance(path, Path)
    assert "browser_profile" in path.parts
    assert path.name == "chrome_user_data"


def test_browser_doctor_has_expected_shape():
    result = check_browser_doctor()
    assert set(result) == {
        "playwright",
        "chrome_channel",
        "dedicated_profile",
        "headed_launch",
        "keep_open_supported",
        "fallback_browser",
    }


def test_dedicated_navigation_failure_closes_owned_context(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingPage:
        def goto(self, *_args, **_kwargs):
            raise RuntimeError("navigation failed")

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [FailingPage()]
            self.closed = False

        def close(self) -> None:
            self.closed = True

    context = FakeContext()
    monkeypatch.setattr(
        "kensho_assistant.app.browser_manager.launch_dedicated_kensho_context",
        lambda *_args, **_kwargs: (context, "chromium", {}),
    )

    with pytest.raises(RuntimeError, match="navigation failed"):
        open_url_in_chrome(
            object(),
            "about:blank",
            use_dedicated_extension=True,
            run_id="run-1",
        )

    assert context.closed is True


def test_dedicated_page_state_requires_exactly_one_panel_and_guard() -> None:
    class FakePage:
        def evaluate(self, _script):
            return {
                "ready": True,
                "panel_count": 2,
                "submit_guard_count": 1,
                "guard_state": {"submitted_count_auto": 0, "blockedAttempts": 0},
            }

    with pytest.raises(RuntimeError, match="dedicated_extension_not_ready"):
        dedicated_extension_page_state(FakePage(), require_ready=True)


def test_control_token_is_provisioned_directly_to_service_worker() -> None:
    calls = []

    class Worker:
        url = "chrome-extension://extension-id/service-worker.js"

        def evaluate(self, script, payload):
            calls.append((script, payload))

    class Context:
        service_workers = [Worker()]

    provision_extension_control_token(
        Context(), "session-1", "secret-token", "extension-id"
    )
    assert calls[0][1] == {"sessionId": "session-1", "token": "secret-token"}
    assert "chrome.storage.session.set" in calls[0][0]
    assert "chrome.tabs.query" in calls[0][0]
    assert "tab_id: tabId" in calls[0][0]


def _verified_page_state():
    return {
        "ready": True,
        "panel_count": 1,
        "extension_id": "extension-id",
        "submit_guard_count": 1,
        "guard_state": {
            "locked": True,
            "integrity": True,
            "installedAtDocumentStart": True,
            "submitted_count_auto": 0,
            "blockedAttempts": 0,
        },
    }


class _GuardPage:
    def __init__(self, state):
        self.state = state

    def wait_for_function(self, *_args, **_kwargs):
        return None

    def evaluate(self, _script):
        return {**self.state}


def test_dedicated_page_state_accepts_only_verified_guard():
    result = dedicated_extension_page_state(_GuardPage(_verified_page_state()), require_ready=True)
    assert result["status"] == "PASS"
    assert result["guard_verified"] is True
    assert result["submitted_count_auto"] == 0
    assert result["auto_submit_detected"] == 0


@pytest.mark.parametrize("guard_state", [None, {}, [], "unverified"])
def test_dedicated_page_state_never_reports_unknown_counters_as_zero(guard_state):
    state = _verified_page_state()
    state["guard_state"] = guard_state
    result = dedicated_extension_page_state(_GuardPage(state))
    assert result["status"] == "BLOCKED"
    assert result["submitted_count_auto"] is None
    assert result["auto_submit_detected"] is None
    with pytest.raises(RuntimeError, match="dedicated_extension_not_ready"):
        dedicated_extension_page_state(_GuardPage(state), require_ready=True)


@pytest.mark.parametrize("key", ["locked", "integrity", "installedAtDocumentStart"])
@pytest.mark.parametrize("value", [False, None, "true", 1])
def test_dedicated_page_state_requires_explicit_guard_health(key, value):
    state = _verified_page_state()
    state["guard_state"][key] = value
    assert dedicated_extension_page_state(_GuardPage(state))["status"] == "BLOCKED"
    with pytest.raises(RuntimeError, match="dedicated_extension_not_ready"):
        dedicated_extension_page_state(_GuardPage(state), require_ready=True)


@pytest.mark.parametrize("key", ["submitted_count_auto", "blockedAttempts"])
@pytest.mark.parametrize("value", [None, "", "0", False, -1, 0.0, {}, 1])
def test_dedicated_page_state_rejects_missing_malformed_or_nonzero_counters(key, value):
    state = _verified_page_state()
    state["guard_state"][key] = value
    result = dedicated_extension_page_state(_GuardPage(state))
    assert result["status"] == "BLOCKED"
    result_key = "submitted_count_auto" if key == "submitted_count_auto" else "auto_submit_detected"
    assert result[result_key] == (value if type(value) is int and value >= 0 else None)
    with pytest.raises(RuntimeError, match="dedicated_extension_not_ready"):
        dedicated_extension_page_state(_GuardPage(state), require_ready=True)


def test_dedicated_guard_inspection_failure_is_sanitized():
    class FailedPage(_GuardPage):
        def evaluate(self, _script):
            raise RuntimeError("TEST_PRIVATE_PAGE_EXCEPTION_DO_NOT_PERSIST")

    result = dedicated_extension_page_state(FailedPage({}))
    assert result["status"] == "BLOCKED"
    assert result["blocked_reason"] == "guard_inspection_failed"
    assert result["submitted_count_auto"] is None
    assert "TEST_PRIVATE_PAGE" not in str(result)
    with pytest.raises(RuntimeError, match="^dedicated_extension_not_ready$"):
        dedicated_extension_page_state(FailedPage({}), require_ready=True)


@pytest.mark.parametrize("guard_timing", ["missing", "late", "document_start"])
def test_dedicated_readiness_checks_real_browser_guard_not_dom_markers(guard_timing):
    from playwright.sync_api import sync_playwright

    guard = Path(__file__).parents[1] / "extension" / "content" / "submit-guard.js"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            if guard_timing == "document_start":
                page.add_init_script(path=str(guard))
            page.goto('data:text/html,<form><input name="email"></form>')
            if guard_timing == "late":
                page.add_script_tag(path=str(guard))
            page.evaluate("""() => {
                document.documentElement.dataset.kenshoExtensionReady = 'true';
                document.documentElement.dataset.kenshoSubmitGuard = 'true';
                const root = document.createElement('div');
                root.dataset.kenshoExtensionRoot = 'true';
                root.dataset.kenshoExtensionId = 'test-extension';
                document.body.append(root);
            }""")
            result = dedicated_extension_page_state(page)
            assert result["status"] == ("PASS" if guard_timing == "document_start" else "BLOCKED")
            assert result["guard_verified"] is (guard_timing == "document_start")
            assert result["submitted_count_auto"] == (None if guard_timing == "missing" else 0)
        finally:
            browser.close()
