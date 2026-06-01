from pathlib import Path

from kensho_assistant.app.entry_logger import load_entries, make_entry_id, upsert_entry


def test_upsert_entry_round_trip(tmp_path: Path):
    csv_path = tmp_path / "entries.csv"
    row = {
        "entry_id": make_entry_id("abc", "https://example.com"),
        "campaign_id": "abc",
        "source": "knshow",
        "campaign_name": "テスト",
        "prize": "景品",
        "winner_count": "1",
        "provider": "提供社",
        "deadline": "2026-05-12",
        "knshow_url": "https://example.com/detail",
        "entry_url": "https://example.com/apply",
        "entry_type": "WEB_FORM",
        "risk_level": "low",
        "risk_reason": "ok",
        "auto_submit_allowed": "true",
        "status": "READY_TO_FILL",
        "submitted_at": "",
        "screenshot_before": "",
        "screenshot_after": "",
        "notes": "",
        "created_at": "2026-05-12T00:00:00+09:00",
        "updated_at": "2026-05-12T00:00:00+09:00",
    }
    upsert_entry(row, path=csv_path)
    rows = load_entries(csv_path)
    assert len(rows) == 1
    assert rows[0]["campaign_id"] == "abc"

