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
