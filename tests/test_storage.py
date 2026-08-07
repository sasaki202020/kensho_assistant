from __future__ import annotations

from pathlib import Path

from kensho_assistant.app.storage import read_csv_rows


def test_read_csv_rows_falls_back_to_cp932(tmp_path: Path) -> None:
    path = tmp_path / "campaigns.csv"
    payload = "campaign_id,campaign_name\nabc,あいう\n".encode("cp932")
    path.write_bytes(payload)

    rows = read_csv_rows(path)

    assert rows == [{"campaign_id": "abc", "campaign_name": "あいう"}]
