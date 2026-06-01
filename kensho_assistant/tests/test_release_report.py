import json
import re
from pathlib import Path

import kensho_assistant.main as cli
from kensho_assistant.app.models import CAMPAIGN_HEADERS, ENTRY_HEADERS
from kensho_assistant.app.auto_scan_report import build_auto_scan_report, render_auto_scan_report
from kensho_assistant.app.release_report import build_release_report, render_release_report
from kensho_assistant.app.storage import write_csv_rows


def _write_inspections(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "campaign_id": "review",
                "readiness_status": "REVIEW_ONLY",
                "readiness_reason": "年齢必須のため自動入力しない",
                "resolved_entry_url": "https://entry.example.com/form",
                "detected_fields": [
                    {"field_name": "age", "required": True, "will_fill": False},
                    {"field_name": "email", "required": True, "will_fill": True},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_review_only_is_counted_and_zero_ready_can_release(tmp_path: Path):
    campaigns = tmp_path / "campaigns.csv"
    entries = tmp_path / "entries.csv"
    inspections = tmp_path / "form_inspections.jsonl"
    write_csv_rows(campaigns, [{"campaign_id": "review", "status": "SAFE_TO_FILL"}], CAMPAIGN_HEADERS)
    write_csv_rows(entries, [], ENTRY_HEADERS)
    _write_inspections(inspections)
    report = build_release_report(campaigns, entries, inspections, version="v0.4.2-beta")
    assert report["ready_for_fill_count"] == 0
    assert report["review_only_count"] == 1
    assert report["release_status"] == "OK"
    assert report["version"] == "v0.4.2-beta"


def test_submitted_entries_make_release_ng(tmp_path: Path):
    campaigns = tmp_path / "campaigns.csv"
    entries = tmp_path / "entries.csv"
    inspections = tmp_path / "form_inspections.jsonl"
    write_csv_rows(campaigns, [], CAMPAIGN_HEADERS)
    write_csv_rows(entries, [{"entry_id": "x", "status": "SUBMITTED"}], ENTRY_HEADERS)
    inspections.write_text("", encoding="utf-8")
    report = build_release_report(campaigns, entries, inspections, version="v0.4.2-beta")
    assert report["release_status"] == "NG"


def test_release_report_mentions_profile_store_and_human_confirmation(tmp_path: Path, monkeypatch):
    campaigns = tmp_path / "campaigns.csv"
    entries = tmp_path / "entries.csv"
    inspections = tmp_path / "form_inspections.jsonl"
    write_csv_rows(campaigns, [], CAMPAIGN_HEADERS)
    write_csv_rows(entries, [], ENTRY_HEADERS)
    inspections.write_text("", encoding="utf-8")
    monkeypatch.setattr("kensho_assistant.app.release_report.PROFILE_ENC", tmp_path / "profile.enc")
    (tmp_path / "profile.enc").write_text("encrypted", encoding="utf-8")
    report = build_release_report(campaigns, entries, inspections, version="v0.4.2-beta")
    rendered = render_release_report(report)
    assert report["profile_store"] == "profile.enc"
    assert "本番送信は人間確認が必要" in rendered
    assert "auto_scan" in rendered


def test_review_command_prints_review_only(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_campaign_rows", lambda: [{"campaign_id": "review", "campaign_name": "test"}])
    monkeypatch.setattr(
        cli,
        "latest_inspections",
        lambda: {
            "review": {
                "campaign_id": "review",
                "resolved_entry_url": "https://entry.example.com/form",
                "readiness_status": "REVIEW_ONLY",
                "readiness_reason": "年齢必須のため自動入力しない",
                "detected_fields": [
                    {"field_name": "age", "required": True, "will_fill": False},
                    {"field_name": "consent", "required": True, "will_fill": False},
                ],
            }
        },
    )
    cli.cmd_review(type("Args", (), {"limit": 5})())
    output = capsys.readouterr().out
    assert "REVIEW_ONLY" in output
    assert "age" in output
    assert "review_only: 1" in output


def test_release_notes_and_readme_keep_personal_data_out():
    release_notes = Path("RELEASE_NOTES_v0.4.2.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "v0.4.2-beta" in release_notes
    assert "あとで応募" in release_notes
    assert "実名" in readme
    assert "伏せ字" in readme
    assert not re.search(r"\b\d{2,4}-\d{2,4}-\d{3,4}\b", release_notes)
    assert "@" not in release_notes


def test_release_report_includes_final_test_note(tmp_path: Path):
    campaigns = tmp_path / "campaigns.csv"
    entries = tmp_path / "entries.csv"
    inspections = tmp_path / "form_inspections.jsonl"
    write_csv_rows(campaigns, [], CAMPAIGN_HEADERS)
    write_csv_rows(entries, [], ENTRY_HEADERS)
    inspections.write_text("", encoding="utf-8")
    report = build_release_report(campaigns, entries, inspections, version="v0.4.2-beta")
    assert report["submitted_count"] == 0
    assert report["final_test_note"] == "本番profile相当テスト 1 件実施 / 応募送信なし"
    assert report["auto_scan_status"] in {"OK", "MISSING", "WARNING"}


def test_auto_scan_report_zero_submitted(tmp_path: Path):
    campaigns = tmp_path / "campaigns.csv"
    entries = tmp_path / "entries.csv"
    inspections = tmp_path / "form_inspections.jsonl"
    write_csv_rows(campaigns, [{"campaign_id": "a", "status": "SAFE_TO_FILL", "form_readiness_status": "REVIEW_ONLY"}], CAMPAIGN_HEADERS)
    write_csv_rows(entries, [], ENTRY_HEADERS)
    inspections.write_text('{"campaign_id":"a","readiness_status":"REVIEW_ONLY","detected_fields":[]}\n', encoding="utf-8")
    report = build_auto_scan_report(campaigns, entries, inspections)
    rendered = render_auto_scan_report(report)
    assert report["submitted_count"] == 0
    assert report["warning"] == "OK"
    assert "今日見るべき候補" in rendered
    assert "submitted_count" in rendered


def test_auto_scan_report_warning_when_submitted_nonzero(tmp_path: Path):
    campaigns = tmp_path / "campaigns.csv"
    entries = tmp_path / "entries.csv"
    inspections = tmp_path / "form_inspections.jsonl"
    write_csv_rows(campaigns, [{"campaign_id": "a", "status": "SAFE_TO_FILL", "form_readiness_status": "REVIEW_ONLY"}], CAMPAIGN_HEADERS)
    write_csv_rows(entries, [{"entry_id": "x", "status": "SUBMITTED"}], ENTRY_HEADERS)
    inspections.write_text("", encoding="utf-8")
    report = build_auto_scan_report(campaigns, entries, inspections)
    assert report["warning"] == "WARNING"
