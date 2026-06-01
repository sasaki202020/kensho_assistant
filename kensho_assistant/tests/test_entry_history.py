from pathlib import Path

import kensho_assistant.main as cli
from kensho_assistant.app.entry_history import (
    build_duplicate_key,
    build_entry_record,
    duplicate_entry_groups,
    export_entry_history_csv,
    load_entry_history,
    mark_entry_applied,
    save_entry_history,
    summarize_entry_history,
)
from kensho_assistant.mail_importer import rescan_win_mail_candidates
from kensho_assistant.app.models import CAMPAIGN_HEADERS
from kensho_assistant.app.storage import write_csv_rows


def test_entry_history_round_trip_and_duplicate_summary(tmp_path: Path):
    path = tmp_path / "entry_history.jsonl"
    first = build_entry_record(
        campaign_id="abc",
        title="当選プレゼント",
        source_site="knshow",
        url="https://example.com/form",
        prize="賞品A",
        deadline="2026-05-23",
        applied_at="2026-05-20T10:00:00+09:00",
        status="APPLIED",
        newsletter_status="unsubscribe_needed",
        pii_used=True,
        memo="連絡先 090-1234-5678 / test@example.com",
    )
    second = build_entry_record(
        campaign_id="def",
        title="当選プレゼント",
        source_site="knshow",
        url="https://example.com/form",
        prize="賞品A",
        deadline="2026-05-23",
        status="PENDING_RESULT",
        newsletter_status="opt_in",
        memo="重複候補",
    )
    save_entry_history([first, second], path)
    rows = load_entry_history(path)
    assert len(rows) == 2
    assert rows[0]["newsletter_status"] == "unsubscribe_needed"
    assert "test@example.com" not in rows[0]["memo"]
    assert "090-1234-5678" not in rows[0]["memo"]
    assert "090-****-5678" in rows[0]["memo"]
    assert summarize_entry_history(rows)["applied"] == 1
    assert summarize_entry_history(rows)["result_pending"] == 2
    assert summarize_entry_history(rows)["newsletter_unsubscribe_needed"] == 1
    assert duplicate_entry_groups(rows)[0]["count"] == 2
    assert build_duplicate_key(first) == build_duplicate_key(second)

    csv_path = export_entry_history_csv(tmp_path / "entry_history.csv", path)
    assert csv_path.exists()
    assert "campaign_id" in csv_path.read_text(encoding="utf-8")


def test_mark_entry_applied_uses_campaign_lookup(tmp_path: Path, monkeypatch):
    campaigns = tmp_path / "campaigns.csv"
    history = tmp_path / "entry_history.jsonl"
    write_csv_rows(
        campaigns,
        [
            {
                "campaign_id": "abc",
                "campaign_name": "応募済み案件",
                "source": "knshow",
                "prize": "賞品B",
                "deadline": "2026-05-25",
                "entry_url": "https://example.com/form",
                "resolved_entry_url": "https://example.com/form",
            }
        ],
        CAMPAIGN_HEADERS,
    )
    monkeypatch.setattr("kensho_assistant.app.entry_history.CAMPAIGNS_CSV", campaigns)
    record = mark_entry_applied("abc", newsletter_status="opt_out", memo="個人情報 090-0000-0000", path=history)
    rows = load_entry_history(history)
    assert record["campaign_id"] == "abc"
    assert rows[0]["title"] == "応募済み案件"
    assert rows[0]["status"] == "APPLIED"
    assert rows[0]["newsletter_status"] == "opt_out"
    assert "090-0000-0000" not in rows[0]["memo"]
    assert "090-****-0000" in rows[0]["memo"]


def test_win_mail_candidates_are_saved_without_plain_pii(tmp_path: Path):
    sample = tmp_path / "mail.txt"
    sample.write_text(
        "Subject: 当選おめでとうございます\nFrom: winner@example.com\n\nプレゼント発送のご案内です。賞品の引換はこちら。\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "win_mail_candidates.jsonl"
    rows = rescan_win_mail_candidates(samples_dir=tmp_path, output_path=output_path)
    assert rows
    assert any("当選" in " ".join(row.get("keyword_hits", [])) for row in rows)
    assert output_path.exists()
    text = output_path.read_text(encoding="utf-8")
    assert "winner@example.com" not in text
    assert "当選" in text


def test_entries_cli_commands_round_trip(tmp_path: Path, monkeypatch, capsys):
    campaigns = tmp_path / "campaigns.csv"
    history = tmp_path / "entry_history.jsonl"
    csv_out = tmp_path / "entry_history.csv"
    write_csv_rows(
        campaigns,
        [
            {
                "campaign_id": "abc",
                "campaign_name": "CLI案件",
                "source": "knshow",
                "prize": "賞品C",
                "deadline": "2026-05-30",
                "entry_url": "https://example.com/form",
                "resolved_entry_url": "https://example.com/form",
            }
        ],
        CAMPAIGN_HEADERS,
    )
    monkeypatch.setattr("kensho_assistant.app.entry_history.CAMPAIGNS_CSV", campaigns)
    monkeypatch.setattr("kensho_assistant.app.entry_history.ENTRY_HISTORY_JSONL", history)
    monkeypatch.setattr("kensho_assistant.app.entry_history.ENTRY_HISTORY_CSV", csv_out)
    add_args = type(
        "Args",
        (),
        {
            "campaign_id": "abc",
            "title": "",
            "source_site": "",
            "url": "https://example.com/form",
            "prize": "",
            "deadline": "",
            "applied_at": "",
            "result_check_date": "",
            "status": "APPLIED",
            "newsletter_status": "unknown",
            "pii_used": False,
            "memo": "応募済み",
            "duplicate_key": "",
        },
    )()
    cli.cmd_entries_add(add_args)
    out = capsys.readouterr().out
    assert "abc" in out
    assert history.exists()

    cli.cmd_entries_list(type("Args", (), {"limit": 10})())
    out = capsys.readouterr().out
    assert "CLI案件" in out
    assert "total:" in out

    cli.cmd_entries_search(type("Args", (), {"keyword": "CLI案件", "limit": 10})())
    out = capsys.readouterr().out
    assert "matched:" in out

    cli.cmd_entries_duplicates(type("Args", (), {})())
    out = capsys.readouterr().out
    assert "duplicate_groups:" in out

    cli.cmd_entries_export_csv(type("Args", (), {})())
    out = capsys.readouterr().out
    assert str(csv_out) in out
    assert csv_out.exists()
