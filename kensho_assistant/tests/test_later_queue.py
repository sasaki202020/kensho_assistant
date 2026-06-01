from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import kensho_assistant.main as main_cli
from kensho_assistant.app import entry_history as entry_history_mod
from kensho_assistant.app import later_queue as later_queue_mod
from kensho_assistant.app.entry_history import load_entry_history
from kensho_assistant.web.app import create_app


def _args(**kwargs):
    return type("Args", (), kwargs)()


def test_later_queue_url_registration_and_duplicate_key(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "later_apply_queue.jsonl"
    monkeypatch.setattr(later_queue_mod, "LATER_QUEUE_JSONL", queue_path)
    monkeypatch.setattr(later_queue_mod, "_parse_page_metadata", lambda url: {"title": "キャンペーンA", "site_name": "Example", "deadline": "2026-06-01"})

    row, created, reason = later_queue_mod.add_later_queue("https://example.com/campaign?utm=1")
    assert created is True
    assert reason == "created"
    assert row["title"] == "キャンペーンA"
    assert row["site_name"] == "Example"
    assert row["normalized_url"] == "https://example.com/campaign"
    assert row["duplicate_key"] == "url:https://example.com/campaign"

    duplicate, created2, reason2 = later_queue_mod.add_later_queue("https://example.com/campaign/")
    assert created2 is False
    assert reason2 == "duplicate"
    assert duplicate["id"] == row["id"]
    assert len(later_queue_mod.load_later_queue(queue_path)) == 1


def test_later_queue_jsonl_save_and_unknown_values(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "later_apply_queue.jsonl"
    monkeypatch.setattr(later_queue_mod, "LATER_QUEUE_JSONL", queue_path)
    monkeypatch.setattr(later_queue_mod, "_parse_page_metadata", lambda url: {"title": "unknown", "site_name": "unknown", "deadline": "unknown"})
    row = later_queue_mod.build_later_queue_record(
        url="https://example.com/campaign",
        review_note="連絡先 090-1234-5678 / test@example.com",
        safety_memo="応募条件は unknown",
    )
    later_queue_mod.save_later_queue([row], queue_path)
    text = queue_path.read_text(encoding="utf-8")
    assert "test@example.com" not in text
    assert "090-1234-5678" not in text
    assert "090-****-5678" in text
    rows = later_queue_mod.load_later_queue(queue_path)
    assert rows[0]["title"] == "unknown"
    assert rows[0]["site_name"] == "unknown"
    assert rows[0]["deadline"] == "unknown"


def test_later_queue_skips_private_host_fetch(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "later_apply_queue.jsonl"
    monkeypatch.setattr(later_queue_mod, "LATER_QUEUE_JSONL", queue_path)

    def fail_get(*args, **kwargs):
        raise AssertionError("requests.get should not be called for private hosts")

    monkeypatch.setattr(later_queue_mod.requests, "get", fail_get)
    row = later_queue_mod.build_later_queue_record(url="http://127.0.0.1:8123/campaign")
    assert row["title"] == "unknown"
    assert row["site_name"] == "127.0.0.1:8123"
    assert "private" in row["safety_memo"] or "unknown" in row["safety_memo"]


def test_later_queue_status_transitions_and_entry_sync(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "later_apply_queue.jsonl"
    history_path = tmp_path / "entry_history.jsonl"
    campaigns_path = tmp_path / "campaigns.csv"
    campaigns_path.write_text("campaign_id,campaign_name,source,prize,deadline,entry_url,resolved_entry_url,knshow_url\n", encoding="utf-8")
    monkeypatch.setattr(later_queue_mod, "LATER_QUEUE_JSONL", queue_path)
    monkeypatch.setattr(later_queue_mod, "CAMPAIGNS_CSV", campaigns_path)
    monkeypatch.setattr(entry_history_mod, "CAMPAIGNS_CSV", campaigns_path)
    monkeypatch.setattr(entry_history_mod, "ENTRY_HISTORY_JSONL", history_path)
    monkeypatch.setattr(entry_history_mod, "ENTRY_HISTORY_CSV", tmp_path / "entry_history.csv")
    monkeypatch.setattr(later_queue_mod, "_parse_page_metadata", lambda url: {"title": "キャンペーンB", "site_name": "Example", "deadline": "2026-06-01"})

    row, created, _ = later_queue_mod.add_later_queue("https://example.com/b")
    assert created is True
    reviewing = later_queue_mod.update_later_queue_status(row["id"], status="reviewing", review_note="確認中", path=queue_path)
    assert reviewing and reviewing["status"] == "reviewing"
    ready = later_queue_mod.update_later_queue_status(row["id"], status="ready_for_fill", review_note="入力準備", path=queue_path)
    assert ready and ready["status"] == "ready_for_fill"
    applied = later_queue_mod.update_later_queue_status(row["id"], status="applied_manual", review_note="手動応募済み", path=queue_path)
    assert applied and applied["status"] == "applied_manual"
    entry_record = later_queue_mod.later_queue_to_entry_history(applied)
    assert entry_record["campaign_id"] == row["id"]
    assert entry_record["status"] == "APPLIED"
    assert entry_record["url"] == "https://example.com/b"

    later_queue_mod.save_later_queue([applied], queue_path)
    assert queue_path.exists()
    saved_entries = load_entry_history(history_path)
    assert saved_entries
    assert saved_entries[0]["campaign_id"] == row["id"]
    assert saved_entries[0]["status"] == "APPLIED"

    skipped_row = later_queue_mod.build_later_queue_record(url="https://example.com/c", title="別案件", site_name="Example", deadline="unknown")
    later_queue_mod.save_later_queue([applied, skipped_row], queue_path)
    later_queue_mod.update_later_queue_status(skipped_row["id"], status="skipped", review_note="スキップ", path=queue_path)
    rows = later_queue_mod.load_later_queue(queue_path)
    assert any(row["status"] == "skipped" for row in rows)


def test_later_queue_cli_commands_round_trip(tmp_path: Path, monkeypatch, capsys):
    queue_path = tmp_path / "later_apply_queue.jsonl"
    history_path = tmp_path / "entry_history.jsonl"
    csv_path = tmp_path / "entry_history.csv"
    campaigns_path = tmp_path / "campaigns.csv"
    campaigns_path.write_text("campaign_id,campaign_name,source,prize,deadline,entry_url,resolved_entry_url,knshow_url\n", encoding="utf-8")
    monkeypatch.setattr(later_queue_mod, "LATER_QUEUE_JSONL", queue_path)
    monkeypatch.setattr(entry_history_mod, "ENTRY_HISTORY_JSONL", history_path)
    monkeypatch.setattr(entry_history_mod, "ENTRY_HISTORY_CSV", csv_path)
    monkeypatch.setattr(entry_history_mod, "CAMPAIGNS_CSV", campaigns_path)
    monkeypatch.setattr(later_queue_mod, "_parse_page_metadata", lambda url: {"title": "CLI案件", "site_name": "Example", "deadline": "2026-06-01"})
    monkeypatch.setattr(main_cli, "bridge_later_queue_to_campaign", lambda url: {"campaign_id": "abc", "form_readiness_status": "READY_FOR_FILL", "next_action": "inspect-form"})

    add_args = _args(url="https://example.com/campaign")
    assert main_cli.cmd_later_add_url(add_args) == 0
    out = capsys.readouterr().out
    assert "queued" in out or "needs_review" in out

    assert main_cli.cmd_later_list(_args(limit=30)) == 0
    out = capsys.readouterr().out
    assert "total:" in out
    assert "CLI案件" in out

    rows = later_queue_mod.load_later_queue(queue_path)
    item_id = rows[0]["id"]

    assert main_cli.cmd_later_review(_args(id=item_id)) == 0
    out = capsys.readouterr().out
    assert "reviewing" in out
    assert "READY_FOR_FILL" in out

    assert main_cli.cmd_later_prepare_fill(_args(id=item_id)) == 0
    out = capsys.readouterr().out
    assert "ready_for_fill" in out
    assert "bridge_command" in out

    assert main_cli.cmd_later_mark_applied_manual(_args(id=item_id)) == 0
    out = capsys.readouterr().out
    assert "entry_history_synced" in out

    second, _, _ = later_queue_mod.add_later_queue("https://example.com/other")
    assert main_cli.cmd_later_skip(_args(id=second["id"])) == 0
    out = capsys.readouterr().out
    assert "skipped" in out

    assert main_cli.cmd_later_remove(_args(id=second["id"])) == 0
    out = capsys.readouterr().out
    assert "removed" in out


def test_later_queue_web_smoke_and_immediate_reflect(tmp_path: Path, monkeypatch):
    queue_path = tmp_path / "later_apply_queue.jsonl"
    monkeypatch.setattr(later_queue_mod, "LATER_QUEUE_JSONL", queue_path)
    monkeypatch.setattr(later_queue_mod, "_parse_page_metadata", lambda url: {"title": "Web案件", "site_name": "Example", "deadline": "2026-06-01"})
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/later-queue")
        assert response.status_code == 200
        assert "あとで応募" in response.text
        assert "自動送信しません" in response.text
        assert "個人情報はこのキューには保存しません" in response.text
        post = client.post("/later-queue/add-url", data={"url": "https://example.com/web-campaign"}, follow_redirects=False)
        assert post.status_code == 303
        page = client.get("/later-queue").text
        assert "Web案件" in page
        assert "登録済み" in page or "needs_review" in page
