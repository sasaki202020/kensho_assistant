from __future__ import annotations

import json
from pathlib import Path

from kensho_assistant.app.harness import kensho_harness as harness
from kensho_assistant import main as cli


def test_kensho_harness_prepared_writes_outputs_and_masks_pii(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "kensho_harness"
    campaign_row = {
        "campaign_id": "camp-1",
        "campaign_name": "Prepared Campaign",
        "provider": "sample",
        "resolved_entry_url": "https://example.com/form",
        "entry_url": "https://example.com/form",
        "queue_status": "PREPARED",
        "form_readiness_status": "READY_FOR_FILL",
        "notes": "contact me@example.com 090-1234-5678",
    }
    queue_row = {
        "campaign_id": "camp-1",
        "queue_id": "camp-1",
        "queue_status": "PREPARED",
        "form_readiness_status": "READY_FOR_FILL",
    }

    def fake_read_csv_rows(path):  # noqa: ANN001
        if path == harness.CAMPAIGNS_CSV:
            return [campaign_row]
        if path == harness.APPLY_QUEUE_CSV:
            return [queue_row]
        return []

    captured = {}

    def fake_run_engine(url, campaign_id, run_mode="dry_run", keep_open=False):  # noqa: ANN001
        captured["url"] = url
        captured["campaign_id"] = campaign_id
        captured["run_mode"] = run_mode
        captured["keep_open"] = keep_open
        return {
            "campaign_id": campaign_id,
            "ok": True,
            "run_mode": run_mode,
            "status": "PRE_SUBMIT_READY",
            "filled_fields_count": 6,
            "total_fields_count": 8,
            "fill_completion_rate": 75.0,
            "submit_attempted": False,
            "submit_clicked": False,
            "auto_submitted": False,
            "needs_review_reasons": ["確認前で停止"],
            "review_items": [{"kind": "comment", "value": "hello"}],
            "pre_submit_score": 95,
            "unresolved_required_fields_count": 0,
            "submit_button_detected": True,
            "screenshot_path": "C:/tmp/before_submit.png",
            "html_snapshot_path": "C:/tmp/before_submit.html",
            "analysis_path": "C:/tmp/form_analysis.json",
            "check_path": "C:/tmp/pre_submit_check.json",
        }

    dry_run_updates = []

    def fake_mark_dry_run_result(*args, **kwargs):  # noqa: ANN001
        dry_run_updates.append((args, kwargs))
        return True

    monkeypatch.setattr(harness, "read_csv_rows", fake_read_csv_rows)
    monkeypatch.setattr(harness, "run_engine", fake_run_engine)
    monkeypatch.setattr(harness, "load_form_analysis", lambda campaign_id: {"campaign_id": campaign_id, "note": "me@example.com"})
    monkeypatch.setattr(harness, "load_pre_submit_check", lambda campaign_id: {"campaign_id": campaign_id, "review_items": ["090-1234-5678"]})
    monkeypatch.setattr(harness, "mark_dry_run_result", fake_mark_dry_run_result)

    result = harness.run_kensho_harness(campaign_id="camp-1", mode="dry_run", output_root=out_root)

    output_dir = Path(result.output_dir)
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))
    campaign_json = (output_dir / "campaign.json").read_text(encoding="utf-8")
    analysis_json = (output_dir / "form_analysis.json").read_text(encoding="utf-8")
    check_json = (output_dir / "pre_submit_check.json").read_text(encoding="utf-8")

    assert result.status == "success"
    assert captured["campaign_id"] == "camp-1"
    assert captured["run_mode"] == "dry_run"
    assert report["submitted_count_auto"] == 0
    assert report["submit_clicked"] is False
    assert report["auto_submitted"] is False
    assert report["source"] == "prepared"
    assert report["mode"] == "dry_run"
    assert "me@example.com" not in campaign_json
    assert "090-1234-5678" not in check_json
    assert "me@example.com" not in analysis_json
    assert dry_run_updates


def test_kensho_harness_later_bridges_campaign_without_queue_update(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "kensho_harness"
    later_row = {
        "id": "later-1",
        "title": "Later Campaign",
        "site_name": "sample",
        "url": "https://example.com/form",
        "status": "ready_for_fill",
        "review_note": "contact me@example.com",
    }
    campaign_row = {
        "campaign_id": "camp-2",
        "campaign_name": "Later Campaign",
        "provider": "sample",
        "resolved_entry_url": "https://example.com/form",
        "entry_url": "https://example.com/form",
        "queue_status": "",
        "form_readiness_status": "READY_FOR_FILL",
        "notes": "call 090-1234-5678",
    }

    def fake_read_csv_rows(path):  # noqa: ANN001
        if path == harness.CAMPAIGNS_CSV:
            return [campaign_row]
        if path == harness.APPLY_QUEUE_CSV:
            return []
        return []

    captured = {}

    def fake_run_engine(url, campaign_id, run_mode="dry_run", keep_open=False):  # noqa: ANN001
        captured["url"] = url
        captured["campaign_id"] = campaign_id
        captured["run_mode"] = run_mode
        return {
            "campaign_id": campaign_id,
            "ok": True,
            "run_mode": run_mode,
            "status": "REVIEW_FILL_READY",
            "filled_fields_count": 5,
            "total_fields_count": 7,
            "fill_completion_rate": 71.43,
            "submit_attempted": False,
            "submit_clicked": False,
            "auto_submitted": False,
            "needs_review_reasons": ["人間確認が必要"],
            "review_items": [{"kind": "quiz", "value": "候補"}],
            "pre_submit_score": 80,
            "unresolved_required_fields_count": 1,
            "submit_button_detected": True,
            "screenshot_path": "C:/tmp/later_before_submit.png",
            "html_snapshot_path": "C:/tmp/later_before_submit.html",
            "analysis_path": "C:/tmp/later_form_analysis.json",
            "check_path": "C:/tmp/later_pre_submit_check.json",
        }

    monkeypatch.setattr(harness, "list_later_queue", lambda: [later_row])
    monkeypatch.setattr(harness, "bridge_later_queue_to_campaign", lambda url: campaign_row)
    monkeypatch.setattr(harness, "read_csv_rows", fake_read_csv_rows)
    monkeypatch.setattr(harness, "run_engine", fake_run_engine)
    monkeypatch.setattr(harness, "load_form_analysis", lambda campaign_id: {"campaign_id": campaign_id, "note": "me@example.com"})
    monkeypatch.setattr(harness, "load_pre_submit_check", lambda campaign_id: {"campaign_id": campaign_id, "review_items": ["090-1234-5678"]})

    mark_calls = []
    monkeypatch.setattr(harness, "mark_dry_run_result", lambda *args, **kwargs: mark_calls.append((args, kwargs)) or True)

    result = harness.run_kensho_harness(later_id="later-1", mode="review", output_root=out_root)

    output_dir = Path(result.output_dir)
    report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))
    later_bridge = (output_dir / "later_bridge.json").read_text(encoding="utf-8")

    assert result.status == "success"
    assert captured["campaign_id"] == "camp-2"
    assert captured["run_mode"] == "review"
    assert report["source"] == "later"
    assert report["mode"] == "review"
    assert report["later_bridge"]["later_id"] == "later-1"
    assert report["submitted_count_auto"] == 0
    assert "me@example.com" not in later_bridge
    assert mark_calls == []


def test_kensho_harness_later_runs_unmatched_url_without_persisting_campaign(tmp_path: Path, monkeypatch) -> None:
    out_root = tmp_path / "data" / "research" / "kensho_harness"
    later_row = {
        "id": "later-new",
        "title": "New Official Campaign",
        "site_name": "official.example",
        "url": "https://official.example/present/form",
        "deadline": "2026-08-31",
        "status": "queued",
        "review_note": "",
    }
    captured = {}

    def fake_run_engine(url, campaign_id, run_mode="dry_run", keep_open=False, campaign=None):  # noqa: ANN001
        captured.update(url=url, campaign_id=campaign_id, run_mode=run_mode)
        captured["campaign"] = campaign
        return {
            "campaign_id": campaign_id,
            "status": "REVIEW_FILL_READY",
            "filled_fields_count": 4,
            "total_fields_count": 6,
            "fill_completion_rate": 66.67,
            "submit_attempted": False,
            "submit_clicked": False,
            "auto_submitted": False,
            "needs_review_reasons": ["人間確認が必要"],
            "review_items": [],
            "pre_submit_score": 70,
            "unresolved_required_fields_count": 1,
            "submit_button_detected": True,
            "screenshot_path": "C:/tmp/new.png",
            "html_snapshot_path": "C:/tmp/new.html",
            "analysis_path": "C:/tmp/new-analysis.json",
            "check_path": "C:/tmp/new-check.json",
        }

    monkeypatch.setattr(harness, "list_later_queue", lambda: [later_row])
    monkeypatch.setattr(
        harness,
        "bridge_later_queue_to_campaign",
        lambda url: {"resolved_entry_url": url, "campaign_id": ""},
    )
    monkeypatch.setattr(harness, "read_csv_rows", lambda path: [])
    monkeypatch.setattr(harness, "run_engine", fake_run_engine)
    monkeypatch.setattr(harness, "load_form_analysis", lambda campaign_id: {"campaign_id": campaign_id})
    monkeypatch.setattr(harness, "load_pre_submit_check", lambda campaign_id: {"campaign_id": campaign_id})

    result = harness.run_kensho_harness(later_id="later-new", mode="dry_run", output_root=out_root)

    report = json.loads((Path(result.output_dir) / "run_report.json").read_text(encoding="utf-8"))
    assert result.status == "success"
    assert captured == {
        "url": "https://official.example/present/form",
        "campaign_id": "later-new",
        "run_mode": "dry_run",
        "campaign": {
            "campaign_id": "later-new",
            "campaign_name": "New Official Campaign",
            "provider": "official.example",
            "deadline": "2026-08-31",
            "resolved_entry_url": "https://official.example/present/form",
            "entry_url": "https://official.example/present/form",
            "queue_status": "",
            "form_readiness_status": "NEEDS_REVIEW",
            "source": "later_queue",
        },
    }
    assert report["source"] == "later"
    assert report["submitted_count_auto"] == 0
    assert report["submit_clicked"] is False
    assert report["auto_submitted"] is False


def test_harness_timeout_writes_safe_evidence(tmp_path: Path, monkeypatch) -> None:
    later_row = {
        "id": "later-timeout",
        "title": "Slow Campaign",
        "site_name": "official.example",
        "url": "https://official.example/slow-form",
        "status": "queued",
    }
    monkeypatch.setattr(harness, "list_later_queue", lambda: [later_row])

    result = harness.write_harness_timeout(
        later_id="later-timeout",
        mode="dry_run",
        timeout_sec=60,
        output_root=tmp_path,
    )

    report = json.loads((Path(result.output_dir) / "run_report.json").read_text(encoding="utf-8"))
    assert result.status == "TIMEOUT"
    assert report["status"] == "TIMEOUT"
    assert report["reason"] == "timeout"
    assert report["timeout_sec"] == 60
    assert report["url"] == "https://official.example/slow-form"
    assert report["submit_attempted"] is False
    assert report["submit_clicked"] is False
    assert report["auto_submitted"] is False
    assert report["submitted_count_auto"] == 0


def test_harness_cli_timeout_defaults_to_sixty_seconds() -> None:
    args = cli.build_parser().parse_args(["harness", "run", "--later-id", "later-1"])
    assert args.timeout_sec == 60
