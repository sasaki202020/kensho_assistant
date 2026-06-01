import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel

from kensho_assistant.ui.data_loader import (
    approve_queue_item,
    approved_queue_rows,
    SAFE_CLI_ACTIONS,
    distribution_path_is_excluded,
    get_current_queue_item,
    get_next_queue_item,
    load_campaigns,
    load_auto_scan_report,
    load_apply_queue,
    load_form_inspections,
    load_release_report,
    mark_hold,
    mark_manual_submitted,
    mark_prepare_cancelled,
    mark_prepared,
    mark_skipped,
    set_age_fill_user_approved,
    summarize_apply_queue,
    update_apply_queue_status,
)
from kensho_assistant.ui.main_window import MainWindow
from kensho_assistant.ui.search_campaigns_page import (
    CATEGORY_LABELS,
    DEFAULT_FILTER_STATES,
    SearchCampaignsPage,
    _make_pill,
    save_campaign_exclusion,
    save_campaign_selection,
)
from kensho_assistant.ui.widgets import StatusPill
from kensho_assistant.app.apply_queue import build_apply_queue, build_apply_queue_report, save_apply_queue
from kensho_assistant.app.research_engine import build_research_report, calculate_opportunity_score, save_research_report


def test_data_loader_reads_release_report(tmp_path: Path):
    path = tmp_path / "release.json"
    path.write_text(json.dumps({"submitted_count": 0}), encoding="utf-8")
    assert load_release_report(path)["submitted_count"] == 0


def test_data_loader_reads_campaigns(tmp_path: Path):
    path = tmp_path / "campaigns.csv"
    path.write_text("campaign_id,campaign_name\nabc,test\n", encoding="utf-8")
    assert load_campaigns(path)[0]["campaign_id"] == "abc"


def test_data_loader_reads_form_inspections(tmp_path: Path):
    path = tmp_path / "forms.jsonl"
    path.write_text('{"campaign_id":"abc","readiness_status":"REVIEW_ONLY"}\n', encoding="utf-8")
    assert load_form_inspections(path)["abc"]["readiness_status"] == "REVIEW_ONLY"


def test_gui_never_exposes_submit_approved():
    flattened = " ".join(" ".join(command) for command in SAFE_CLI_ACTIONS.values())
    assert "submit-approved" not in flattened
    assert "fill" not in flattened
    assert "build-queue" in flattened


def test_distribution_excludes_sensitive_files():
    assert distribution_path_is_excluded(".env") is True
    assert distribution_path_is_excluded("kensho_assistant/config/profile.json") is True
    assert distribution_path_is_excluded("kensho_assistant/config/profile.enc") is True
    assert distribution_path_is_excluded("kensho_assistant/logs/run.jsonl") is True
    assert distribution_path_is_excluded("kensho_assistant/browser_profile/chrome_user_data/Default") is True


def test_send_button_is_disabled(qt_snapshot):
    window = MainWindow(qt_snapshot)
    assert window.send_button.isEnabled() is False


def test_submitted_count_is_zero_in_snapshot(qt_snapshot):
    assert qt_snapshot.release_report["submitted_count"] == 0


def test_profile_preview_is_masked(qt_snapshot):
    assert "***" in qt_snapshot.profile_preview["email"] or qt_snapshot.profile_preview["email"] == "未設定"
    assert "****" in qt_snapshot.profile_preview["phone"] or qt_snapshot.profile_preview["phone"] == "未設定"


def test_gui_status_text_mentions_human_confirmation(qt_snapshot):
    window = MainWindow(qt_snapshot)
    texts = []
    for page_index in range(window.stack.count()):
        page = window.stack.widget(page_index)
        texts.extend(label.text() for label in page.findChildren(QLabel))
    flattened = " ".join(texts)
    assert "本番送信は人間確認が必要" in flattened
    assert "本番profileテスト済み" in flattened
    assert "v0.4.2-beta" in flattened
    assert "対象サイト：懸賞生活 https://www.knshow.com/" in flattened
    assert "懸賞生活の公式ツールではありません" in flattened


def test_search_page_defaults_and_categories(qt_snapshot):
    page = SearchCampaignsPage(qt_snapshot)
    assert [button.text() for button in page.category_buttons.values()] == CATEGORY_LABELS
    assert DEFAULT_FILTER_STATES["exclude_x"] is True
    assert page.filter_boxes["exclude_x"].isChecked() is True
    assert page.filter_boxes["exclude_instagram"].isChecked() is True
    assert page.filter_boxes["exclude_line"].isChecked() is True
    assert page.filter_boxes["exclude_app"].isChecked() is True
    assert page.filter_boxes["exclude_receipt"].isChecked() is True
    assert page.filter_boxes["exclude_purchase"].isChecked() is True
    assert page.filter_boxes["include_review_only"].isChecked() is True
    assert page.safe_submit_button.isEnabled() is False
    assert "送信（無効）" in page.safe_submit_button.text()


def test_main_window_sidebar_includes_search_page(qt_snapshot):
    window = MainWindow(qt_snapshot)
    labels = [window.nav.item(index).text() for index in range(window.nav.count())]
    assert "懸賞を探す" in labels
    assert "応募履歴" in labels
    assert "AI担当者" in labels
    assert "AI司令塔" in labels
    assert "ヘルプ・使い方" in labels


def test_selected_and_excluded_saved(tmp_path: Path):
    campaign = {
        "campaign_id": "abc",
        "campaign_name": "test",
        "collected_at": "2026-01-01T00:00:00+09:00",
        "entry_url": "https://entry.example.com/form",
        "form_readiness_status": "REVIEW_ONLY",
    }
    selected_path = save_campaign_selection(campaign, tmp_path / "selected_campaigns.csv")
    excluded_path = save_campaign_exclusion(campaign, tmp_path / "selected_campaigns.csv")
    assert selected_path.exists()
    assert excluded_path.exists()


def test_status_pill_color_mapping():
    pill = _make_pill("READY_FOR_FILL", "pillGreen")
    assert isinstance(pill, StatusPill)
    assert pill.objectName() == "pillGreen"
    assert _make_pill("REVIEW_ONLY", "pillBlue").objectName() == "pillBlue"


def test_auto_scan_report_loading_zero(tmp_path: Path):
    path = tmp_path / "auto_scan_latest.json"
    path.write_text(json.dumps({"submitted_count": 0}), encoding="utf-8")
    assert load_auto_scan_report(path)["submitted_count"] == 0


def test_auto_scan_bat_excludes_fill_and_submit_approved():
    content = Path("auto_scan.bat").read_text(encoding="utf-8")
    assert "fill" not in content
    assert "submit-approved" not in content
    assert "collect --limit 30" in content
    assert "build-queue --limit 30" in content
    assert "research-report" in content


def test_apply_queue_build_and_update(tmp_path: Path):
    campaigns = [
        {
            "campaign_id": "ready",
            "campaign_name": "READY",
            "prize": "Prize A",
            "provider": "Provider A",
            "deadline": "明日まで",
            "resolved_entry_url": "https://example.com/ready",
            "form_readiness_status": "READY_FOR_FILL",
            "form_readiness_score": "0.95",
            "status": "SAFE_TO_FILL",
        },
        {
            "campaign_id": "review",
            "campaign_name": "REVIEW",
            "prize": "Prize B",
            "provider": "Provider B",
            "deadline": "今日まで",
            "resolved_entry_url": "https://example.com/review",
            "form_readiness_status": "REVIEW_ONLY",
            "form_readiness_score": "0.50",
            "status": "SAFE_TO_FILL",
        },
        {
            "campaign_id": "blocked",
            "campaign_name": "BLOCKED",
            "prize": "Prize C",
            "provider": "Provider C",
            "deadline": "今週まで",
            "resolved_entry_url": "https://example.com/blocked",
            "form_readiness_status": "READY_FOR_FILL",
            "form_readiness_score": "0.80",
            "status": "BLOCKED_X",
        },
    ]
    inspections = {
        "ready": {"manual_review_required_fields": ["age"], "readiness_reason": "安全"},
        "review": {"manual_review_required_fields": ["consent"], "readiness_reason": "要確認"},
    }
    queue_rows = build_apply_queue(campaigns, inspections, entries=[{"campaign_id": "skip", "status": "SUBMITTED"}], existing_queue=[{"campaign_id": "review", "queue_status": "PREPARED"}], limit=30)
    assert [row["campaign_id"] for row in queue_rows] == ["review", "ready"]
    assert queue_rows[0]["queue_status"] == "PREPARED"
    assert queue_rows[1]["queue_status"] == "QUEUED"
    assert queue_rows[0]["auto_submit_allowed"] == "false"
    assert "age" in queue_rows[1]["manual_review_required_fields"]
    assert summarize_apply_queue(queue_rows)["total"] == 2
    assert build_apply_queue_report(queue_rows)["submitted_count_auto"] == 0

    csv_path = tmp_path / "apply_queue.csv"
    save_apply_queue(queue_rows, csv_path)
    assert load_apply_queue(csv_path)[0]["campaign_id"] == "review"
    assert update_apply_queue_status("ready", "HOLD", csv_path) is True
    assert load_apply_queue(csv_path)[1]["queue_status"] == "HOLD"


def test_apply_queue_session_helpers_and_state_updates(tmp_path: Path):
    rows = [
        {
            "queue_id": "ready",
            "campaign_id": "ready",
            "campaign_name": "READY",
            "deadline": "明日まで",
            "readiness_status": "READY_FOR_FILL",
            "queue_status": "QUEUED",
        },
        {
            "queue_id": "review",
            "campaign_id": "review",
            "campaign_name": "REVIEW",
            "deadline": "今日まで",
            "readiness_status": "REVIEW_ONLY",
            "queue_status": "HOLD",
        },
        {
            "queue_id": "done",
            "campaign_id": "done",
            "campaign_name": "DONE",
            "deadline": "今日まで",
            "readiness_status": "REVIEW_ONLY",
            "queue_status": "MANUALLY_SUBMITTED",
        },
        {
            "queue_id": "approved",
            "campaign_id": "approved",
            "campaign_name": "APPROVED",
            "deadline": "今日まで",
            "readiness_status": "READY_FOR_FILL",
            "queue_status": "APPROVED",
        },
    ]
    csv_path = tmp_path / "apply_queue.csv"
    save_apply_queue(rows, csv_path)
    loaded = load_apply_queue(csv_path)
    assert get_current_queue_item(loaded, 0)["campaign_id"] == "ready"
    assert get_next_queue_item(loaded, "ready")["campaign_id"] == "review"
    assert mark_prepared("ready", csv_path) is True
    assert mark_hold("review", csv_path) is True
    assert mark_skipped("ready", csv_path) is True
    assert mark_manual_submitted("ready", csv_path) is True
    updated = load_apply_queue(csv_path)
    assert any(row["queue_status"] == "MANUALLY_SUBMITTED" for row in updated)
    assert any(row.get("submission_method") == "MANUAL" for row in updated)
    assert any(row.get("manual_submitted_at") for row in updated)
    approved_rows = approved_queue_rows(updated)
    assert {row["queue_status"] for row in approved_rows} == {"PREPARED", "HOLD", "APPROVED"}
    assert all(row["queue_status"] != "MANUALLY_SUBMITTED" for row in approved_rows)


def test_prepare_state_updates_and_cancellation(tmp_path: Path):
    rows = [
        {
            "queue_id": "ready",
            "campaign_id": "ready",
            "campaign_name": "READY",
            "deadline": "明日まで",
            "readiness_status": "READY_FOR_FILL",
            "queue_status": "QUEUED",
            "last_action": "",
            "prepared_at": "",
        }
    ]
    csv_path = tmp_path / "apply_queue.csv"
    save_apply_queue(rows, csv_path)
    assert mark_prepared("ready", csv_path) is True
    prepared = load_apply_queue(csv_path)[0]
    assert prepared["queue_status"] == "PREPARED"
    assert prepared["last_action"] == "PREPARED_WITH_CHROME"
    assert prepared["prepared_at"]

    assert mark_prepare_cancelled("ready", "QUEUED", csv_path) is True
    cancelled = load_apply_queue(csv_path)[0]
    assert cancelled["queue_status"] == "QUEUED"
    assert cancelled["last_action"] == "PREPARE_CANCELLED_BY_USER"


def test_approve_queue_item_sets_approval_state(tmp_path: Path):
    rows = [
        {
            "queue_id": "ready",
            "campaign_id": "ready",
            "campaign_name": "READY",
            "deadline": "明日まで",
            "readiness_status": "READY_FOR_FILL",
            "queue_status": "QUEUED",
            "last_action": "",
            "approved_by_user": "false",
            "approved_at": "",
            "approved_note": "",
            "age_fill_user_approved": "false",
            "terms_user_acknowledged": "false",
            "quiz_user_acknowledged": "false",
            "approved_session_order": "",
            "auto_submit_allowed": "false",
        }
    ]
    csv_path = tmp_path / "apply_queue.csv"
    save_apply_queue(rows, csv_path)
    assert approve_queue_item("ready", note="manual note", age_fill_user_approved=True, path=csv_path) is True
    updated = load_apply_queue(csv_path)[0]
    assert updated["queue_status"] == "APPROVED"
    assert updated["approved_by_user"] == "true"
    assert updated["approved_note"] == "manual note"
    assert updated["age_fill_user_approved"] == "true"
    assert updated["auto_submit_allowed"] == "false"
    assert updated["approved_session_order"] == "1"
    assert set_age_fill_user_approved("ready", False, csv_path) is True
    assert load_apply_queue(csv_path)[0]["age_fill_user_approved"] == "false"


def test_opportunity_score_and_recommendation_reason():
    ready = {
        "campaign_id": "ready",
        "campaign_name": "Webフォーム応募",
        "prize": "Prize",
        "provider": "Provider",
        "deadline": "明日まで",
        "resolved_entry_url": "https://example.com/form",
        "form_readiness_status": "READY_FOR_FILL",
        "description": "Webフォーム応募",
        "entry_type_raw": "web",
        "status": "SAFE_TO_FILL",
    }
    risky = {
        "campaign_id": "risky",
        "campaign_name": "LINE応募",
        "prize": "Prize",
        "provider": "Provider",
        "deadline": "今日まで",
        "resolved_entry_url": "https://line.example.com",
        "form_readiness_status": "SEARCH_ONLY",
        "description": "LINE応募",
        "entry_type_raw": "LINE",
        "status": "BLOCKED_LINE",
    }
    ready_metrics = calculate_opportunity_score(ready, {"manual_review_required_fields": []})
    risky_metrics = calculate_opportunity_score(risky, {"manual_review_required_fields": ["quiz"]})
    assert ready_metrics["opportunity_score"] >= 80
    assert "Webフォーム応募" in ready_metrics["recommendation_reason"]
    assert ready_metrics["next_action"] == "応募キューに追加"
    assert risky_metrics["opportunity_score"] < ready_metrics["opportunity_score"]
    assert risky_metrics["next_action"] == "除外推奨"


def test_research_report_generation(tmp_path: Path, monkeypatch):
    rows = [
        {
            "campaign_id": "ready",
            "campaign_name": "Webフォーム応募",
            "prize": "Prize",
            "provider": "Provider",
            "deadline": "明日まで",
            "resolved_entry_url": "https://example.com/form",
            "form_readiness_status": "READY_FOR_FILL",
            "description": "Webフォーム応募",
            "entry_type_raw": "web",
            "status": "SAFE_TO_FILL",
        }
    ]
    monkeypatch.setattr("kensho_assistant.app.research_engine.RESEARCH_REPORT_MD", tmp_path / "research_report_latest.md")
    monkeypatch.setattr("kensho_assistant.app.research_engine.RESEARCH_REPORT_JSON", tmp_path / "research_report_latest.json")
    report = build_research_report(rows)
    md_path, json_path = save_research_report(report)
    assert report["total"] == 1
    assert report["score_bins"]["80_plus"] == 1
    assert report["top_candidates"][0]["campaign_id"] == "ready"
    assert md_path.exists()
    assert json_path.exists()


def test_research_report_does_not_touch_profile(monkeypatch):
    monkeypatch.setattr("kensho_assistant.app.profile_manager.load_profile", lambda: (_ for _ in ()).throw(AssertionError("profile should not be loaded")))
    report = build_research_report([])
    assert report["total"] == 0
