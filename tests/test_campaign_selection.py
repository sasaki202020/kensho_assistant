import kensho_assistant.main as cli


def test_campaign_id_filter_returns_single_row():
    rows = [{"campaign_id": "a"}, {"campaign_id": "b"}]
    assert cli._campaigns_by_id(rows, "b") == [{"campaign_id": "b"}]


def test_ready_for_fill_is_the_only_default_fill_candidate():
    rows = [
        {"campaign_id": "ready", "status": "SAFE_TO_FILL", "resolved_entry_url": "https://a", "resolve_status": "RESOLVED", "form_readiness_status": "READY_FOR_FILL"},
        {"campaign_id": "search", "status": "SAFE_TO_FILL", "resolved_entry_url": "https://b", "resolve_status": "RESOLVED", "form_readiness_status": "SEARCH_ONLY"},
        {"campaign_id": "landing", "status": "SAFE_TO_FILL", "resolved_entry_url": "https://c", "resolve_status": "RESOLVED", "form_readiness_status": "LANDING_PAGE"},
    ]
    selected = [
        row
        for row in rows
        if row.get("status") == "SAFE_TO_FILL"
        and row.get("resolve_status") == "RESOLVED"
        and row.get("form_readiness_status") == "READY_FOR_FILL"
    ]
    assert [row["campaign_id"] for row in selected] == ["ready"]
