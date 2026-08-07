from pathlib import Path

import kensho_assistant.main as cli
from kensho_assistant.app.entry_logger import log_event
from kensho_assistant.app.entry_url_resolver import (
    classify_resolution,
    has_resolved_form_url,
    is_rd_link,
    target_url_for_campaign,
)
from kensho_assistant.app.models import CAMPAIGN_HEADERS, DetectedField
from kensho_assistant.app.storage import read_csv_rows, write_csv_rows


def test_rd_link_is_detected():
    assert is_rd_link("https://www.knshow.com/rd/abc123") is True


def test_resolved_entry_url_is_preferred_for_target():
    row = {
        "resolved_entry_url": "https://entry.example.com/form",
        "entry_url": "https://www.knshow.com/rd/abc",
        "knshow_url": "https://www.knshow.com/detail/abc.html",
    }
    assert target_url_for_campaign(row) == "https://entry.example.com/form"
    assert has_resolved_form_url({**row, "resolve_status": "RESOLVED"}) is True


def test_unresolved_rd_link_is_not_fill_target():
    row = {
        "resolved_entry_url": "",
        "entry_url": "https://www.knshow.com/rd/abc",
        "resolve_status": "",
    }
    assert has_resolved_form_url(row) is False


def test_resolve_statuses_can_be_saved(tmp_path: Path):
    path = tmp_path / "campaigns.csv"
    rows = [
        {"campaign_id": "a", "resolve_status": "RESOLVED", "resolved_entry_url": "https://entry.example.com/form"},
        {"campaign_id": "b", "resolve_status": "BLOCKED_X", "resolved_entry_url": ""},
        {"campaign_id": "c", "resolve_status": "BLOCKED_LINE", "resolved_entry_url": ""},
    ]
    write_csv_rows(path, rows, CAMPAIGN_HEADERS)
    saved = read_csv_rows(path)
    assert [row["resolve_status"] for row in saved] == ["RESOLVED", "BLOCKED_X", "BLOCKED_LINE"]


def test_classify_resolution_blocks_social_destinations():
    assert classify_resolution("https://x.com/example")[0] == "BLOCKED_X"
    assert classify_resolution("https://line.me/R/ti/p/example")[0] == "BLOCKED_LINE"


def test_log_payload_redacts_cookie_session_and_html(tmp_path: Path):
    path = tmp_path / "run.jsonl"
    log_event(
        "resolver",
        {
            "cookie": "abc",
            "session": "def",
            "html": "<html>secret</html>",
            "email": "example@example.com",
        },
        path=path,
    )
    text = path.read_text(encoding="utf-8")
    assert "abc" not in text
    assert "def" not in text
    assert "<html>" not in text
    assert "example@example.com" not in text


def test_inspection_record_only_reads_fields(monkeypatch):
    class FakeLocator:
        def count(self):
            return 1

    class FakePage:
        def locator(self, selector):
            assert selector in {
                "form",
                'button[type="submit"], input[type="submit"]',
                'a:has-text("応募"), a:has-text("詳しくはこちら"), a:has-text("キャンペーン詳細")',
            }
            return FakeLocator()

    fields = [
        DetectedField(
            field_name="email",
            selector="#email",
            label="email",
            kind="input",
            input_type="email",
            confidence=0.95,
            required=True,
        )
    ]
    monkeypatch.setattr(cli, "detect_fields", lambda page: fields)
    record = cli._inspection_record(
        {"campaign_id": "abc", "campaign_name": "test", "resolved_entry_url": "https://entry.example.com"},
        FakePage(),
        {"email": "kensho-test@example.com"},
    )
    assert record["detected_forms_count"] == 1
    assert record["detected_fields"][0]["will_fill"] is True
    assert record["readiness_status"] in {"REVIEW_ONLY", "UNKNOWN"}
