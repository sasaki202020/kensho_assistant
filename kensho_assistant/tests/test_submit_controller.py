from pathlib import Path

import kensho_assistant.app.submit_controller as submit_controller
from kensho_assistant.app.models import FillResult


class _SubmitButton:
    def __init__(self) -> None:
        self.clicked = False

    def click(self) -> None:
        self.clicked = True


class _SubmitLocator:
    def __init__(self, button: _SubmitButton) -> None:
        self.button = button

    def count(self) -> int:
        return 1

    @property
    def first(self) -> _SubmitButton:
        return self.button


class _FakePage:
    def __init__(self) -> None:
        self.button = _SubmitButton()
        self.screenshot_called = False

    def locator(self, _selector: str) -> _SubmitLocator:
        return _SubmitLocator(self.button)

    def screenshot(self, **kwargs) -> None:
        self.screenshot_called = True
        self.screenshot_kwargs = kwargs


def test_second_confirmation_requires_submit(monkeypatch, tmp_path: Path):
    fake_page = _FakePage()

    def fake_fill_campaign_page(*args, **kwargs):
        return FillResult(campaign_id="abc", decision="fill", consent_fields=[])

    monkeypatch.setattr(submit_controller, "fill_campaign_page", fake_fill_campaign_page)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    result = submit_controller.approve_and_submit(
        fake_page,
        {"campaign_id": "abc", "campaign_name": "test", "entry_url": "https://example.com"},
        {},
        "SAFE_TO_FILL",
        "",
        screenshot_dir=tmp_path,
        save_screenshot=False,
    )
    assert result.submitted is False
    assert fake_page.button.clicked is False


def test_second_confirmation_with_submit_sends(monkeypatch, tmp_path: Path):
    fake_page = _FakePage()

    def fake_fill_campaign_page(*args, **kwargs):
        return FillResult(campaign_id="abc", decision="fill", consent_fields=[])

    monkeypatch.setattr(submit_controller, "fill_campaign_page", fake_fill_campaign_page)
    monkeypatch.setattr("builtins.input", lambda prompt="": "submit")
    result = submit_controller.approve_and_submit(
        fake_page,
        {"campaign_id": "abc", "campaign_name": "test", "entry_url": "https://example.com"},
        {},
        "SAFE_TO_FILL",
        "",
        screenshot_dir=tmp_path,
        save_screenshot=False,
    )
    assert result.submitted is True
    assert fake_page.button.clicked is True
