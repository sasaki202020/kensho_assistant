from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

import kensho_assistant.main as main_cli
from kensho_assistant.app.auto_apply_engine import AutoApplyEngine
from kensho_assistant.app.entry_history import load_entry_history
from kensho_assistant.app.field_mapper import FieldMapper
from kensho_assistant.app.form_detector import detect_fields
from kensho_assistant.app.form_readiness import evaluate_form_readiness
from kensho_assistant.app import entry_history as entry_history_mod
from kensho_assistant.app import later_queue as later_queue_mod
from kensho_assistant.app.submit_adapters import dry_run_submit as dry_run_submit_mod
from kensho_assistant.web.app import create_app


PROFILE = {
    "last_name": "山田",
    "first_name": "太郎",
    "full_name": "山田 太郎",
    "postal_code": "100-0001",
    "prefecture": "東京都",
    "city": "千代田区",
    "address1": "千代田1-1",
    "phone": "09000001234",
    "email": "test@example.com",
    "gender": "男性",
    "birth_year": "1980",
    "birth_month": "1",
    "birth_day": "1",
    "age_group": "30代",
    "occupation": "会社員",
    "marital_status": "未婚",
    "children": "なし",
    "survey_choice": "口コミ",
    "prize_choice": "A賞",
    "entry_count": "1",
    "opinion": "テスト感想",
}

FORM_NAMES = [
    "confirmation_flow_mock.html",
    "multi_radio_group_mock.html",
    "required_checkbox_mock.html",
    "free_text_mock.html",
    "quiz_multi_question_mock.html",
    "weird_select_mock.html",
    "changing_button_text_mock.html",
    "confusing_submit_mock.html",
]

EXPECTED_STATUSES = {
    "confirmation_flow_mock.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
    "multi_radio_group_mock.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
    "required_checkbox_mock.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
    "free_text_mock.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
    "quiz_multi_question_mock.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
    "weird_select_mock.html": {"PRE_SUBMIT_READY", "REVIEW_FILL_READY"},
    "changing_button_text_mock.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
    "confusing_submit_mock.html": {"REVIEW_FILL_READY", "MANUAL_ASSIST_READY"},
}


def _form_url(name: str) -> str:
    return (Path(__file__).parent / "mock_forms" / name).resolve().as_uri()


def _campaign(name: str) -> dict[str, str]:
    stem = Path(name).stem
    return {"campaign_id": stem, "campaign_name": stem.replace("_", " "), "resolved_entry_url": _form_url(name)}


def _assert_no_plaintext_pii(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for secret in ("test@example.com", "09000001234", "山田 太郎", "山田太郎"):
        assert secret not in text


def _engine_context(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    analysis_dir = tmp_path / "form_analysis"
    checks_dir = tmp_path / "pre_submit_checks"
    screenshots_dir = tmp_path / "dry_run_screenshots"
    snapshots_dir = tmp_path / "dry_run_snapshots"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    checks_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("kensho_assistant.app.form_analyzer.FORM_ANALYSIS_DIR", analysis_dir)
    monkeypatch.setattr("kensho_assistant.app.pre_submit_verifier.PRE_SUBMIT_CHECKS_DIR", checks_dir)
    monkeypatch.setattr("kensho_assistant.app.auto_apply_engine.FORM_ANALYSIS_DIR", analysis_dir)
    monkeypatch.setattr("kensho_assistant.app.auto_apply_engine.PRE_SUBMIT_CHECKS_DIR", checks_dir)
    monkeypatch.setattr("kensho_assistant.app.submit_adapters.dry_run_submit.DRY_RUN_SCREENSHOTS_DIR", screenshots_dir)
    monkeypatch.setattr("kensho_assistant.app.submit_adapters.dry_run_submit.DRY_RUN_SNAPSHOTS_DIR", snapshots_dir)
    monkeypatch.setattr("kensho_assistant.web.app.FORM_ANALYSIS_DIR", analysis_dir)
    monkeypatch.setattr("kensho_assistant.web.app.PRE_SUBMIT_CHECKS_DIR", checks_dir)
    return analysis_dir, checks_dir, screenshots_dir, snapshots_dir


def test_v044_mock_forms_keep_dry_run_safe_and_relevant(monkeypatch, tmp_path: Path) -> None:
    _engine_context(monkeypatch, tmp_path)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for form_name in FORM_NAMES:
                profile = dict(PROFILE)
                if form_name == "free_text_mock.html":
                    profile["opinion"] = ""
                page = browser.new_page()
                page.goto(_form_url(form_name))
                detected_fields = detect_fields(page)
                mapped_fields = FieldMapper().map_fields(
                    detected_fields,
                    profile,
                    allow_birthdate_fill=True,
                    answer_overrides={},
                    allow_ai_answer_fill=False,
                )
                readiness = evaluate_form_readiness(
                    fields=mapped_fields,
                    detected_forms_count=page.locator("form").count(),
                    submit_button_detected=bool(page.locator('button, input[type="submit"], input[type="button"], input[type="image"]').count()),
                    landing_links_detected=bool(page.locator("a").count()),
                    safety_status="SAFE_TO_FILL",
                    quiz_required=form_name == "quiz_multi_question_mock.html",
                )
                assert readiness.readiness_status
                result = AutoApplyEngine("dry_run").run(page, _campaign(form_name), profile)
                record = result["record"]
                pre_submit_check = result["pre_submit_check"]
                assert record["status"] in EXPECTED_STATUSES[form_name]
                assert pre_submit_check["status"] == record["status"]
                assert record["submit_attempted"] is False
                assert record["submit_clicked"] is False
                assert record["auto_submitted"] is False
                assert isinstance(record["pre_submit_score"], (int, float))
                assert result["analysis"]["submit_button_candidates"]
                assert Path(record["analysis_path"]).exists()
                assert Path(record["check_path"]).exists()
                assert Path(record["screenshot_path"]).exists()
                assert Path(record["html_snapshot_path"]).exists()
                _assert_no_plaintext_pii(Path(record["check_path"]))
                _assert_no_plaintext_pii(Path(record["html_snapshot_path"]))
                if record["status"] == "PRE_SUBMIT_READY":
                    assert not str(pre_submit_check["skip_reason"]).strip()
                else:
                    assert str(pre_submit_check["skip_reason"]).strip() or str(pre_submit_check["safety_memo"]).strip()

                if form_name == "confirmation_flow_mock.html":
                    texts = [str(candidate.get("text", "")) for candidate in result["analysis"]["submit_button_candidates"]]
                    assert any("確認画面へ" in text or "内容を確認" in text for text in texts)
                    assert "confirm_button_candidate" in pre_submit_check["review_reasons"]
                    assert page.url.endswith("confirmation_flow_mock.html")
                elif form_name == "multi_radio_group_mock.html":
                    assert page.locator('input[name="gender"][value="male"]').is_checked()
                    assert page.locator('input[name="age_group"][value="30代"]').is_checked()
                    assert page.locator('input[name="motivation"][value="口コミ"]').is_checked()
                    assert page.locator('input[name="newsletter"]:checked').count() == 0
                    assert "newsletter" in pre_submit_check["required_radio_unselected"]
                elif form_name == "required_checkbox_mock.html":
                    assert page.locator('input[type="checkbox"]:checked').count() == 0
                    assert pre_submit_check["required_checkbox_unchecked"] >= 3
                    assert any(item.get("kind") == "checkbox" for item in pre_submit_check["review_items"])
                elif form_name == "free_text_mock.html":
                    assert page.locator('textarea[name="free_text"]').input_value() == ""
                    assert page.locator('textarea[name="opinion"]').input_value() == ""
                    assert page.locator('textarea[name="comment"]').input_value() == ""
                    assert any(item.get("kind") == "free_text" for item in pre_submit_check["review_items"])
                    assert any(item.get("kind") == "free_text" for item in pre_submit_check["review_items"] if item.get("suggested_text"))
                elif form_name == "quiz_multi_question_mock.html":
                    assert len([item for item in pre_submit_check["review_items"] if item.get("kind") == "quiz"]) >= 2
                    assert pre_submit_check["needs_review_reasons"]
                    assert not page.locator('select[name="quiz_answer_1"]').input_value()
                    assert not page.locator('select[name="quiz_answer_2"]').input_value()
                elif form_name == "weird_select_mock.html":
                    assert page.locator('select[name="prefecture"]').input_value() == "13"
                    assert page.locator('select[name="age_group"]').input_value() == "30"
                    assert page.locator('select[name="prize_choice"]').input_value() == "a"
                    assert record["pre_submit_score"] >= 90
                    assert record["status"] == "PRE_SUBMIT_READY"
                elif form_name == "changing_button_text_mock.html":
                    texts = [str(candidate.get("text", "")) for candidate in result["analysis"]["submit_button_candidates"]]
                    assert any("確認する" in text or "内容を確認" in text or "応募内容確認" in text for text in texts)
                    assert any("送信する" in text or "応募する" in text for text in texts)
                    assert "confirm_button_candidate" in pre_submit_check["review_reasons"]
                elif form_name == "confusing_submit_mock.html":
                    texts = [str(candidate.get("text", "")) for candidate in result["analysis"]["submit_button_candidates"]]
                    assert any("戻る" in text for text in texts)
                    assert any("確認" in text for text in texts)
                    assert any("送信" in text for text in texts)
                    assert any("応募" in text for text in texts)
                    assert "confirm_button_candidate" in pre_submit_check["review_reasons"]
                page.close()
        finally:
            browser.close()


def test_v044_confirmation_flow_uses_separate_confirmation_page(monkeypatch, tmp_path: Path) -> None:
    _engine_context(monkeypatch, tmp_path)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(_form_url("confirmation_flow_mock.html"))
            result = AutoApplyEngine("dry_run").run(page, _campaign("confirmation_flow_mock.html"), PROFILE)
            assert result["record"]["submit_clicked"] is False
            assert "confirm_button_candidate" in result["pre_submit_check"]["review_reasons"]
            assert page.url.endswith("confirmation_flow_mock.html")
            page.close()

            confirm_page = browser.new_page()
            confirm_page.goto(_form_url("confirmation_flow_mock_confirmation.html"))
            confirm_result = AutoApplyEngine("dry_run").run(
                confirm_page,
                _campaign("confirmation_flow_mock_confirmation.html"),
                PROFILE,
            )
            assert confirm_result["record"]["status"] == "SKIPPED"
            assert confirm_result["record"]["submit_clicked"] is False
            assert confirm_result["pre_submit_check"]["submit_button_detected"] is True
            assert confirm_result["pre_submit_check"]["skip_reason"]
            _assert_no_plaintext_pii(Path(confirm_result["record"]["check_path"]))
            _assert_no_plaintext_pii(Path(confirm_result["record"]["html_snapshot_path"]))
            confirm_page.close()
        finally:
            browser.close()


def test_v044_sites_dashboard_and_later_queue_surface_mock_diagnostics(monkeypatch, tmp_path: Path) -> None:
    analysis_dir, checks_dir, _, _ = _engine_context(monkeypatch, tmp_path)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            free_page = browser.new_page()
            free_page.goto(_form_url("free_text_mock.html"))
            free_result = AutoApplyEngine("dry_run").run(free_page, _campaign("free_text_mock.html"), PROFILE)
            free_page.close()

            quiz_page = browser.new_page()
            quiz_page.goto(_form_url("quiz_multi_question_mock.html"))
            quiz_result = AutoApplyEngine("dry_run").run(quiz_page, _campaign("quiz_multi_question_mock.html"), PROFILE)
            quiz_page.close()
        finally:
            browser.close()

    free_campaign_id = Path("free_text_mock.html").stem
    quiz_campaign_id = Path("quiz_multi_question_mock.html").stem
    free_record = free_result["record"]
    quiz_record = quiz_result["record"]

    campaign_rows = [
        {
            "campaign_id": free_campaign_id,
            "campaign_name": "free text mock",
            "prize": "賞品A",
            "provider": "Mock Forms",
            "deadline": "2026-06-30",
            "resolved_entry_url": _form_url("free_text_mock.html"),
            "entry_url": _form_url("free_text_mock.html"),
            "form_readiness_status": "REVIEW_ONLY",
            "form_readiness_reason": "自由記述は人間確認",
            "resolve_status": "RESOLVED",
            "status": "SAFE_TO_FILL",
        },
        {
            "campaign_id": quiz_campaign_id,
            "campaign_name": "quiz mock",
            "prize": "賞品B",
            "provider": "Mock Forms",
            "deadline": "2026-06-30",
            "resolved_entry_url": _form_url("quiz_multi_question_mock.html"),
            "entry_url": _form_url("quiz_multi_question_mock.html"),
            "form_readiness_status": "REVIEW_ONLY",
            "form_readiness_reason": "クイズは人間確認",
            "resolve_status": "RESOLVED",
            "status": "SAFE_TO_FILL",
        },
    ]
    queue_rows = [
        {
            "campaign_id": free_campaign_id,
            "campaign_name": "free text mock",
            "prize": "賞品A",
            "provider": "Mock Forms",
            "deadline": "2026-06-30",
            "queue_status": "APPROVED",
            "dry_run_status": free_record["status"],
            "dry_run_pre_submit_score": str(free_record["pre_submit_score"]),
            "dry_run_fill_completion_rate": str(free_record["fill_completion_rate"]),
            "dry_run_unresolved_required_fields_count": str(free_record["unresolved_required_fields_count"]),
            "dry_run_total_fields_count": str(free_record["total_fields_count"]),
            "dry_run_submit_button_detected": str(free_record["submit_button_detected"]).lower(),
            "dry_run_reason_summary": free_result["pre_submit_check"]["skip_reason"],
            "skip_reason_summary": free_result["pre_submit_check"]["skip_reason"],
            "manual_review_required_fields": ", ".join(free_result["pre_submit_check"]["unresolved_required_fields"]),
            "dry_run_review_items": json.dumps(free_result["pre_submit_check"]["review_items"], ensure_ascii=False),
            "dry_run_analysis_path": str(free_record["analysis_path"]),
            "dry_run_check_path": str(free_record["check_path"]),
            "dry_run_screenshot_path": str(free_record["screenshot_path"]),
            "dry_run_html_snapshot_path": str(free_record["html_snapshot_path"]),
        },
        {
            "campaign_id": quiz_campaign_id,
            "campaign_name": "quiz mock",
            "prize": "賞品B",
            "provider": "Mock Forms",
            "deadline": "2026-06-30",
            "queue_status": "APPROVED",
            "dry_run_status": quiz_record["status"],
            "dry_run_pre_submit_score": str(quiz_record["pre_submit_score"]),
            "dry_run_fill_completion_rate": str(quiz_record["fill_completion_rate"]),
            "dry_run_unresolved_required_fields_count": str(quiz_record["unresolved_required_fields_count"]),
            "dry_run_total_fields_count": str(quiz_record["total_fields_count"]),
            "dry_run_submit_button_detected": str(quiz_record["submit_button_detected"]).lower(),
            "dry_run_reason_summary": quiz_result["pre_submit_check"]["skip_reason"],
            "skip_reason_summary": quiz_result["pre_submit_check"]["skip_reason"],
            "manual_review_required_fields": ", ".join(quiz_result["pre_submit_check"]["unresolved_required_fields"]),
            "dry_run_review_items": json.dumps(quiz_result["pre_submit_check"]["review_items"], ensure_ascii=False),
            "dry_run_analysis_path": str(quiz_record["analysis_path"]),
            "dry_run_check_path": str(quiz_record["check_path"]),
            "dry_run_screenshot_path": str(quiz_record["screenshot_path"]),
            "dry_run_html_snapshot_path": str(quiz_record["html_snapshot_path"]),
        },
    ]
    later_rows = [
        {
            "id": "later-free-text",
            "title": "free text mock",
            "site_name": "Mock Forms",
            "url": _form_url("free_text_mock.html"),
            "normalized_url": _form_url("free_text_mock.html"),
            "duplicate_key": f"url:{_form_url('free_text_mock.html')}",
            "deadline": "2026-06-30",
            "status": "ready_for_fill",
            "source_type": "manual_url",
            "safety_memo": "unknown 項目は推測しない",
            "review_note": "確認中",
            "created_at": "2026-06-04T10:00:00+09:00",
            "updated_at": "2026-06-04T10:05:00+09:00",
        }
    ]
    inspections = {
        free_campaign_id: {
            "campaign_id": free_campaign_id,
            "detected_forms_count": 1,
            "detected_fields": free_result["analysis"]["fields"],
            "analysis_path": str(free_record["analysis_path"]),
            "check_path": str(free_record["check_path"]),
            "html_snapshot_path": str(free_record["html_snapshot_path"]),
            "manual_review_required_fields": free_result["pre_submit_check"]["unresolved_required_fields"],
            "readiness_status": free_result["record"]["status"],
            "readiness_reason": free_result["pre_submit_check"]["skip_reason"],
            "skip_reason_summary": free_result["pre_submit_check"]["skip_reason"],
            "safety_memo": free_result["pre_submit_check"]["safety_memo"],
            "review_items": free_result["pre_submit_check"]["review_items"],
            "ai_candidates": free_result["pre_submit_check"]["ai_candidates"],
            "human_checklist": free_result["pre_submit_check"]["human_checklist"],
        },
        quiz_campaign_id: {
            "campaign_id": quiz_campaign_id,
            "detected_forms_count": 1,
            "detected_fields": quiz_result["analysis"]["fields"],
            "analysis_path": str(quiz_record["analysis_path"]),
            "check_path": str(quiz_record["check_path"]),
            "html_snapshot_path": str(quiz_record["html_snapshot_path"]),
            "manual_review_required_fields": quiz_result["pre_submit_check"]["unresolved_required_fields"],
            "readiness_status": quiz_result["record"]["status"],
            "readiness_reason": quiz_result["pre_submit_check"]["skip_reason"],
            "skip_reason_summary": quiz_result["pre_submit_check"]["skip_reason"],
            "safety_memo": quiz_result["pre_submit_check"]["safety_memo"],
            "review_items": quiz_result["pre_submit_check"]["review_items"],
            "ai_candidates": quiz_result["pre_submit_check"]["ai_candidates"],
            "human_checklist": quiz_result["pre_submit_check"]["human_checklist"],
        },
    }

    monkeypatch.setattr("kensho_assistant.web.app.load_campaigns", lambda: campaign_rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_apply_queue", lambda: queue_rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_form_inspections", lambda: inspections)
    monkeypatch.setattr("kensho_assistant.web.app.list_later_queue", lambda: later_rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_entry_history", lambda: [])
    monkeypatch.setattr("kensho_assistant.web.app.load_masked_profile_preview", lambda: {"name": "山田**", "postal_code": "100-****", "email": "te***@example.com", "phone": "090-****-1234"})
    monkeypatch.setattr("kensho_assistant.web.app.profile_storage_state", lambda: {"profile_enc": "保存済み", "profile_json": "検出"})
    monkeypatch.setattr("kensho_assistant.web.app.bridge_later_queue_to_campaign", lambda url: {"campaign_id": free_campaign_id} if url == _form_url("free_text_mock.html") else {})

    app = create_app()
    with TestClient(app) as client:
        sites = client.get(f"/sites?campaign_id={free_campaign_id}")
        later = client.get("/later-queue?selected=later-free-text")
        snapshot = client.get(f"/api/approved/{free_campaign_id}/html-snapshot")
        analysis_json = client.get(f"/api/approved/{free_campaign_id}/analysis")
        check_json = client.get(f"/api/approved/{free_campaign_id}/pre-submit-check")

    assert sites.status_code == 200
    assert later.status_code == 200
    assert snapshot.status_code == 200
    assert analysis_json.status_code == 200
    assert check_json.status_code == 200
    assert "AI候補" in sites.text
    assert "人間確認 checklist" in sites.text
    assert "pre_submit_score" in sites.text
    assert "skip_reason" in sites.text
    assert "safety_memo" in sites.text
    assert "送信前チェックJSON" in sites.text
    assert "<details" in sites.text
    assert "Sites診断で開く" in later.text
    assert "あとで応募" in later.text
    assert "ready_for_fill" in later.text or "登録済み" in later.text
    assert "<html" in snapshot.text.lower() or "<!doctype" in snapshot.text.lower()
    assert "test@example.com" not in snapshot.text
    assert "09000001234" not in snapshot.text
    assert "山田太郎" not in snapshot.text


def test_v044_later_queue_requires_applied_manual_before_history_sync(monkeypatch, tmp_path: Path) -> None:
    queue_path = tmp_path / "later_apply_queue.jsonl"
    history_path = tmp_path / "entry_history.jsonl"
    history_csv = tmp_path / "entry_history.csv"
    monkeypatch.setattr(later_queue_mod, "LATER_QUEUE_JSONL", queue_path)
    monkeypatch.setattr(entry_history_mod, "ENTRY_HISTORY_JSONL", history_path)
    monkeypatch.setattr(entry_history_mod, "ENTRY_HISTORY_CSV", history_csv)
    monkeypatch.setattr(later_queue_mod, "_parse_page_metadata", lambda url: {"title": "Mock Later", "site_name": "Mock Forms", "deadline": "2026-06-30"})

    row, created, reason = later_queue_mod.add_later_queue(_form_url("free_text_mock.html"))
    assert created is True
    assert reason == "created"
    assert row["status"] in {"queued", "needs_review"}
    assert load_entry_history(history_path) == []

    updated = later_queue_mod.update_later_queue_status(row["id"], status="ready_for_fill", review_note="診断待ち", path=queue_path)
    assert updated and updated["status"] == "ready_for_fill"
    assert load_entry_history(history_path) == []

    result = main_cli.cmd_later_mark_applied_manual(type("Args", (), {"id": row["id"]})())
    assert result == 0
    history_rows = load_entry_history(history_path)
    assert history_rows
    assert history_rows[0]["campaign_id"] == row["id"]
