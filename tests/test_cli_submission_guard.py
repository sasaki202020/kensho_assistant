from __future__ import annotations

import argparse
from types import SimpleNamespace

import kensho_assistant.main as main_cli


def test_legacy_fill_installs_submission_guards_before_fill(monkeypatch) -> None:
    events: list[str] = []
    recorded: list[dict[str, object]] = []

    campaign = {
        "campaign_id": "campaign-1",
        "campaign_name": "fixture campaign",
        "status": "SAFE_TO_FILL",
        "form_readiness_status": "READY_FOR_FILL",
        "resolved_entry_url": "https://example.invalid/form",
        "entry_url": "https://example.invalid/form",
        "source": "fixture",
        "prize": "fixture",
        "provider": "fixture",
        "deadline": "2099-01-01",
    }

    class FakePage:
        def goto(self, url: str, **_kwargs) -> None:
            events.append("goto")

    page = FakePage()

    class FakeContext:
        def new_page(self):
            events.append("new_page")
            return page

    class FakeBrowser:
        def new_context(self):
            events.append("new_context")
            return FakeContext()

        def close(self):
            events.append("close")

    class FakeChromium:
        def launch(self, **_kwargs):
            events.append("launch")
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightContext:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(main_cli, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(main_cli, "_load_profile_or_fail", lambda: {"email": "fixture@example.invalid"})
    monkeypatch.setattr(main_cli, "_campaign_rows", lambda: [campaign])
    monkeypatch.setattr(main_cli, "load_entries", lambda: [])
    monkeypatch.setattr(main_cli, "has_resolved_form_url", lambda _row: True)
    monkeypatch.setattr(main_cli, "target_url_for_campaign", lambda _row: "https://example.invalid/form")
    monkeypatch.setattr(main_cli, "upsert_entry", lambda record: recorded.append(dict(record)))
    monkeypatch.setattr(main_cli, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_cli, "install_submission_guard_on_context", lambda _context: events.append("context_guard"))
    monkeypatch.setattr(main_cli, "install_submission_guard", lambda _page: events.append("page_guard"))
    monkeypatch.setattr(main_cli, "fill_campaign_page", lambda *_args, **_kwargs: (events.append("fill") or SimpleNamespace(
        decision="fill",
        submitted=False,
        screenshot_before="",
        screenshot_after="",
        notes="",
    )))
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywrightContext())

    result = main_cli.cmd_fill(
        argparse.Namespace(campaign_id="campaign-1", force=False, limit=1, force_review=False)
    )

    assert result == 0
    assert events == [
        "launch",
        "new_context",
        "context_guard",
        "new_page",
        "goto",
        "page_guard",
        "fill",
        "close",
    ]
    assert recorded[0]["auto_submit_allowed"] == "false"
    assert recorded[0]["status"] == "FILLED_NEEDS_APPROVAL"
