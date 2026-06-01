from pathlib import Path

import pytest

from kensho_assistant.app.knshow_scraper import build_keyword_search_url, collect_by_keyword, save_campaigns
from kensho_assistant.app.models import CAMPAIGN_HEADERS
from kensho_assistant.app.storage import read_csv_rows, write_csv_rows


def test_save_campaigns_preserves_existing_rows_and_enrichment(tmp_path: Path):
    path = tmp_path / "campaigns.csv"
    write_csv_rows(
        path,
        [
            {
                "campaign_id": "keep",
                "campaign_name": "old only",
                "resolved_entry_url": "https://entry.example.com/keep",
                "form_readiness_status": "READY_FOR_FILL",
            },
            {
                "campaign_id": "refresh",
                "campaign_name": "before",
                "resolved_entry_url": "https://entry.example.com/form",
                "form_readiness_status": "READY_FOR_FILL",
            },
        ],
        CAMPAIGN_HEADERS,
    )

    save_campaigns(
        [
            {
                "campaign_id": "refresh",
                "campaign_name": "after",
                "entry_url": "https://www.knshow.com/rd/refresh",
            }
        ],
        path,
    )

    saved = {row["campaign_id"]: row for row in read_csv_rows(path)}
    assert set(saved) == {"keep", "refresh"}
    assert saved["refresh"]["campaign_name"] == "after"
    assert saved["refresh"]["resolved_entry_url"] == "https://entry.example.com/form"
    assert saved["refresh"]["form_readiness_status"] == "READY_FOR_FILL"


def test_build_keyword_search_url_encodes_keyword():
    assert build_keyword_search_url("ビール") == "https://www.knshow.com/search?do=true&keyword=%E3%83%93%E3%83%BC%E3%83%AB"


def test_collect_by_keyword_requires_positive_limit():
    with pytest.raises(ValueError):
        collect_by_keyword("ビール", limit=0)
