from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
from datetime import date
import importlib
import hashlib

import pytest
from fastapi.testclient import TestClient

import kensho_assistant.main as cli
from kensho_assistant.app import apply_queue, assisted_session
from kensho_assistant.app import engine
from kensho_assistant.app.storage import write_csv_rows
from kensho_assistant.web.app import create_app


def candidate(**changes):
    return {
        "queue_id": "fixture", "campaign_id": "fixture",
        "campaign_name": "Fixture campaign", "queue_status": "APPROVED",
        "approved_by_user": "true", "deadline": "2099-12-31",
        **changes,
    }


@pytest.mark.parametrize("value", [True, "true", "TRUE", " true "])
def test_terms_restriction_blocks_prepare(value):
    assert apply_queue.queue_prepare_block_reason(candidate(terms_automation_restricted=value)) == "terms_prohibit_automation"


def test_terms_restriction_preserves_existing_reason_order():
    row = candidate(terms_automation_restricted="true", deadline="2000-01-01")
    assert apply_queue.queue_prepare_block_reason(row) == "campaign_expired"
    row["submission_method"] = "MANUAL"
    assert apply_queue.queue_prepare_block_reason(row) == "already_manually_submitted"


@pytest.mark.parametrize("value", [False, "false", "", None])
def test_uncertain_terms_do_not_block_prepare(value):
    assert apply_queue.queue_prepare_block_reason(candidate(
        terms_automation_restricted=value, terms_check_uncertain="true",
    )) == ""


def test_terms_inspection_reaches_queue_and_csv(tmp_path):
    rows = apply_queue.build_apply_queue(
        campaigns=[candidate(form_readiness_status="READY_FOR_FILL")],
        inspections={"fixture": {"terms_policy": {
            "restricted": True, "categories": ["automated_entry", "proxy_entry"],
            "uncertain": False, "checked_at": "2026-09-30T10:00:00+09:00",
        }}}, entries=[], existing_queue=[],
    )
    path = tmp_path / "queue.csv"
    apply_queue.save_apply_queue(rows, path)
    row = apply_queue.load_apply_queue(path)[0]
    assert row["terms_automation_restricted"] == "true"
    assert row["terms_restriction_categories"] == "automated_entry, proxy_entry"
    assert row["terms_check_uncertain"] == "false"
    assert row["terms_checked_at"] == "2026-09-30T10:00:00+09:00"
    assert row["auto_submit_allowed"] == "false"


def test_queue_rebuild_preserves_restriction_if_inspection_is_legacy():
    existing = candidate(terms_automation_restricted="true", terms_restriction_categories="proxy_entry")
    row = apply_queue.build_apply_queue(
        campaigns=[candidate(form_readiness_status="READY_FOR_FILL")],
        inspections={"fixture": {}}, entries=[], existing_queue=[existing],
    )[0]
    assert apply_queue.queue_prepare_block_reason(row) == "terms_prohibit_automation"


def test_terms_candidates_excluded_from_engine_and_assisted_selection(monkeypatch):
    rows = [candidate(terms_automation_restricted="true", queue_status="PREPARED"),
            candidate(campaign_id="open", queue_status="PREPARED", terms_check_uncertain="true")]
    before = deepcopy(rows)
    assert [r["campaign_id"] for r in apply_queue.approved_queue_rows(rows)] == ["open"]
    assert [r["campaign_id"] for r in apply_queue.approved_queue_pending_rows(rows)] == ["open"]
    monkeypatch.setattr(assisted_session, "approved_queue_rows", lambda: rows)
    assert [r["campaign_id"] for r in assisted_session._load_session_candidates("PREPARED", 1)] == ["open"]
    monkeypatch.setattr(engine, "load_apply_queue", lambda _path: rows)
    calls = []
    monkeypatch.setattr(engine, "run_prepared_campaign_dry_run", lambda cid, **kw: calls.append(cid) or {"campaign_id": cid})
    engine.run_prepared_campaigns_dry_run_all(limit=1)
    assert calls == ["open"]
    assert rows == before


def test_terms_rejected_before_engine_profile_access(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "read_csv_rows", lambda _path: [candidate()])
    monkeypatch.setattr(engine, "load_apply_queue", lambda _path: [candidate(terms_automation_restricted="true")])
    monkeypatch.setattr(engine, "load_profile", lambda: calls.append("profile") or {})
    with pytest.raises(ValueError, match="terms_prohibit_automation"):
        engine.run_prepared_campaign_dry_run("fixture")
    assert calls == []


def test_terms_restriction_does_not_block_manual_submission_record(tmp_path):
    path = tmp_path / "queue.csv"
    apply_queue.save_apply_queue([candidate(terms_automation_restricted="true")], path)
    assert apply_queue.mark_manual_submitted("fixture", path)
    saved = apply_queue.load_apply_queue(path)[0]
    assert saved["submission_method"] == "MANUAL"
    assert saved["manual_submitted_at"]
    assert saved["terms_automation_restricted"] == "true"


@pytest.mark.parametrize("route", [
    "/api/queue/fixture/prepare", "/api/approved/fixture/prepare",
    "/queue/fixture/chrome-prepare", "/queue/session/fixture/chrome-prepare",
    "/queue/fixture/prepare", "/queue/session/fixture/prepare",
])
def test_terms_web_prepare_never_launches_or_changes_state(monkeypatch, route):
    calls = []
    row = candidate(terms_automation_restricted="true")
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda _id: row)
    monkeypatch.setattr("kensho_assistant.web.app._start_chrome_prepare", lambda *a, **k: calls.append("launch"))
    monkeypatch.setattr("kensho_assistant.web.app.mark_prepared", lambda *a: calls.append("prepared"))
    monkeypatch.setattr("kensho_assistant.web.app.set_age_fill_user_approved", lambda *a: calls.append("age"))
    with TestClient(create_app()) as client:
        response = client.post(route + "?allow_age_fill=true", follow_redirects=False)
    assert calls == []
    if route.startswith("/api/"):
        assert response.json()["blocked_reason"] == "terms_prohibit_automation"
        assert response.json()["submitted_count_auto"] == 0
        assert response.json()["message"] == "規約で自動入力禁止（手動で応募してください）"


def test_terms_assisted_capability_rechecks_current_queue(monkeypatch):
    monkeypatch.setattr(assisted_session, "load_apply_queue", lambda: [candidate(terms_automation_restricted="true")])
    with pytest.raises(ValueError, match="terms_prohibit_automation"):
        assisted_session.validate_extension_candidate("fixture")


@pytest.mark.parametrize("deadline", [
    "2000/01/01 17:00 (remaining 6 days)",
    "2000-01-01T23:59:00+09:00",
    "締切: 2000.01.01 17:00",
    "2000-01-01（本日中）",
    "2000年1月1日（明日まで）",
    "2000/01/01 詳細説明 締切: 1月1日 17:00（残り6日）",
    "2000-01-01 / 2000-01-01 / 2000-01-01",
])
def test_deadline_text_does_not_hide_expired_absolute_date(deadline):
    assert apply_queue._deadline_bucket(deadline, today=date(2026, 9, 13))[0] == 4


def test_saved_approved_queue_filters_expired_without_mutating_rows():
    rows = [candidate(deadline="2000-01-01"), candidate(campaign_id="open")]
    before = deepcopy(rows)
    assert [r["campaign_id"] for r in apply_queue.approved_queue_rows(rows)] == ["open"]
    assert [r["campaign_id"] for r in apply_queue.approved_queue_pending_rows(rows)] == ["open"]
    assert rows == before


def test_manual_submission_is_not_requeued_just_because_status_is_prepared():
    rows = [candidate(queue_status="PREPARED", submission_method="MANUAL")]
    assert apply_queue.approved_queue_rows(rows) == []


def test_assisted_selection_rechecks_deadline_before_applying_limit(monkeypatch):
    monkeypatch.setattr(assisted_session, "approved_queue_rows", lambda: [
        candidate(deadline="2000-01-01"), candidate(campaign_id="open"),
    ])
    result = assisted_session._load_session_candidates("APPROVED,PREPARED", 2)
    assert [r["campaign_id"] for r in result] == ["open"]


def test_yearless_expired_date_is_not_rolled_into_next_year():
    assert apply_queue._deadline_bucket("1月31日", today=date(2026, 9, 13))[0] == 4


@pytest.mark.parametrize("deadline", [
    "2026-09-01～2026-09-30", "2026/09/01 ~ 2026/09/30",
    "2026年9月1日から9月30日まで",
])
def test_deadline_range_uses_end_not_start(deadline):
    assert apply_queue._deadline_bucket(deadline, today=date(2026, 9, 13))[0] != 4


def test_ambiguous_multiple_dates_do_not_assume_first_is_deadline():
    assert apply_queue._deadline_bucket(
        "公開2026-09-01 / 日程2026-09-30", today=date(2026, 9, 13)
    ) == (3, "期限不明")


@pytest.mark.parametrize("route", [
    "/api/queue/fixture/prepare", "/api/approved/fixture/prepare",
    "/queue/fixture/chrome-prepare", "/queue/session/fixture/chrome-prepare",
    "/queue/fixture/prepare", "/queue/session/fixture/prepare",
])
def test_expired_web_prepare_never_launches_or_changes_state(monkeypatch, route):
    calls = []
    row = candidate(deadline="2000-01-01")
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda _id: row)
    monkeypatch.setattr("kensho_assistant.web.app._start_chrome_prepare", lambda *a, **k: calls.append("launch") or "started")
    monkeypatch.setattr("kensho_assistant.web.app.mark_prepared", lambda *a: calls.append("prepared"))
    monkeypatch.setattr("kensho_assistant.web.app.set_age_fill_user_approved", lambda *a: calls.append("age"))
    with TestClient(create_app()) as client:
        response = client.post(route + "?allow_age_fill=true", follow_redirects=False)
    assert calls == []
    if route.startswith("/api/"):
        assert response.json()["ok"] is False
        assert response.json()["blocked_reason"] == "campaign_expired"
        assert response.json()["submitted_count_auto"] == 0


def test_web_launch_acceptance_does_not_claim_fill_completion(monkeypatch):
    calls = []
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda _id: candidate())
    monkeypatch.setattr("kensho_assistant.web.app._start_chrome_prepare", lambda *a, **k: "started")
    monkeypatch.setattr("kensho_assistant.web.app.mark_prepared", lambda *a: calls.append("prepared"))
    with TestClient(create_app()) as client:
        result = client.post("/api/queue/fixture/prepare").json()
    assert result["ok"] is True
    assert result["action"] == "prepare_started"
    assert result["queue_status"] == "APPROVED"
    assert result["preparation_verified"] is False
    assert calls == []


def test_cli_expired_candidate_rejected_before_profile_access(monkeypatch, capsys):
    profile_reads = []
    monkeypatch.setattr(cli, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(cli, "_load_profile_or_fail", lambda: profile_reads.append(True) or {})
    monkeypatch.setattr(cli, "_campaign_rows", lambda: [candidate(status="BLOCKED_FIXTURE")])
    monkeypatch.setattr(cli, "read_csv_rows", lambda _path: [candidate(deadline="2000-01-01")])
    result = cli.cmd_prepare(Namespace(campaign_id="fixture", require_user_approved=True))
    assert result == 1
    assert profile_reads == []
    assert "campaign_expired" in capsys.readouterr().out


def test_approved_web_listing_excludes_expired_but_preserves_queue(monkeypatch):
    rows = [candidate(campaign_name="EXPIRED_FIXTURE", deadline="2000-01-01"), candidate(campaign_id="open", campaign_name="OPEN_FIXTURE")]
    before = deepcopy(rows)
    monkeypatch.setattr("kensho_assistant.web.app.load_apply_queue", lambda: rows)
    with TestClient(create_app()) as client:
        response = client.get("/approved")
    assert response.status_code == 200
    assert "EXPIRED_FIXTURE" not in response.text
    assert "OPEN_FIXTURE" in response.text
    assert rows == before


@pytest.mark.parametrize("route", ["/queue/fixture/prepare", "/queue/session/fixture/prepare"])
@pytest.mark.parametrize("approved", [True, False])
def test_legacy_prepare_requires_approval_and_never_marks_completion(monkeypatch, route, approved):
    calls = []
    row = candidate(approved_by_user="true" if approved else "false")
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda _id: row)
    monkeypatch.setattr("kensho_assistant.web.app.load_apply_queue", lambda: [row])
    monkeypatch.setattr("kensho_assistant.web.app._start_chrome_prepare", lambda *a, **k: calls.append("launch") or "started")
    monkeypatch.setattr("kensho_assistant.web.app.mark_prepared", lambda *a: calls.append("prepared"))
    monkeypatch.setattr("kensho_assistant.web.app.mark_selected", lambda *a, **k: calls.append("selected"))
    with TestClient(create_app()) as client:
        response = client.post(route, follow_redirects=False)
    assert response.status_code == 303
    assert calls == (["launch"] if approved else [])


def test_legacy_session_selection_excludes_expired_and_manual_without_mutation():
    web = importlib.import_module("kensho_assistant.web.app")
    rows = [candidate(queue_status="PREPARED", deadline="2000-01-01"),
            candidate(queue_status="PREPARED", submission_method="MANUAL"),
            candidate(campaign_id="open", queue_status="PREPARED")]
    before = deepcopy(rows)
    assert [r["campaign_id"] for r in web._queue_session_rows(rows)] == ["open"]
    assert rows == before


@pytest.mark.parametrize("changes,reason", [
    ({"deadline": "2000-01-01"}, "campaign_expired"),
    ({"submission_method": "MANUAL"}, "already_manually_submitted"),
    ({"approved_by_user": "false"}, "candidate_not_approved"),
    (None, "candidate_missing"),
])
def test_capability_rechecks_current_queue_before_profile_or_bridge(monkeypatch, changes, reason):
    state = {
        "session_id": "fixture-session", "active_candidate_id": "fixture",
        "workflow_state": "MAPPING_CONFIRMED", "extension_id": "a" * 32,
        "current_url": "https://example.invalid/apply", "form_fingerprint": "fixture-fp",
        "confirmed_profile_keys": ["email"],
    }
    rows = [] if changes is None else [candidate(**changes)]
    # Patch the repository function used by the new recheck, never real candidate data.
    monkeypatch.setattr(assisted_session, "load_apply_queue", lambda: rows, raising=False)
    monkeypatch.setattr(assisted_session, "load_assisted_session_state", lambda: state)
    calls = []
    monkeypatch.setattr(assisted_session._EXTENSION_BRIDGE, "start", lambda: calls.append("start") or ("127.0.0.1", 45678))
    monkeypatch.setattr(assisted_session._EXTENSION_BRIDGE, "issue", lambda **kwargs: calls.append("issue") or {})
    with pytest.raises(ValueError, match=reason):
        assisted_session.issue_extension_capability(
            session_id="fixture-session", candidate_id="fixture", origin="https://example.invalid",
            fingerprint="fixture-fp", profile={"email": "fixture@example.invalid"}, profile_keys=["email"],
        )
    assert calls == []
    web = importlib.import_module("kensho_assistant.web.app")
    monkeypatch.setattr(web, "load_assisted_session_state", lambda: state)
    monkeypatch.setattr(web, "validate_extension_control_token", lambda *a: None)
    monkeypatch.setattr(web, "load_profile", lambda: calls.append("profile") or {})
    with TestClient(create_app(), client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/session/extension-capability",
            headers={"Origin": "chrome-extension://" + "a" * 32},
            json={"session_id": "fixture-session", "candidate_id": "fixture", "origin": "https://example.invalid",
                  "fingerprint": "fixture-fp", "profile_keys": ["email"], "control_token": "fixture-token"})
    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize("changes,reason", [
    ({"deadline": "2000-01-01"}, "campaign_expired"),
    ({"submission_method": "MANUAL"}, "already_manually_submitted"),
])
def test_legacy_dry_run_rechecks_before_profile(monkeypatch, changes, reason):
    calls = []
    monkeypatch.setattr(engine, "_campaign_for_id", lambda _id: candidate(queue_status="PREPARED", **changes))
    monkeypatch.setattr(engine, "load_profile", lambda: calls.append("profile") or {})
    monkeypatch.setattr(engine, "build_profile_readiness", lambda _p: (_ for _ in ()).throw(ValueError("unsafe_test_execution")))
    with pytest.raises(ValueError, match=reason):
        engine.run_prepared_campaign_dry_run("fixture")
    assert calls == []


def test_cli_auto_apply_expired_rejected_before_profile(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(cli, "_load_profile_or_fail", lambda: calls.append("profile") or {})
    monkeypatch.setattr(cli, "_campaign_rows", lambda: [candidate()])
    monkeypatch.setattr(cli, "read_csv_rows", lambda _path: [candidate(deadline="2000-01-01")])
    monkeypatch.setattr(cli, "open_url_in_chrome", lambda *a: (_ for _ in ()).throw(ValueError("unsafe_test_execution")))
    assert cli.cmd_auto_apply(Namespace(run_mode="review", campaign_id="fixture", browser="chrome")) == 1
    assert calls == []


def test_legacy_web_review_rejects_expired_before_profile(monkeypatch):
    calls = []
    monkeypatch.setattr("kensho_assistant.web.app._queue_item_for_id", lambda _id: candidate(deadline="2000-01-01"))
    monkeypatch.setattr("kensho_assistant.web.app.load_campaigns", lambda: [candidate()])
    monkeypatch.setattr("kensho_assistant.web.app.load_profile", lambda: calls.append("profile") or {})
    monkeypatch.setattr("kensho_assistant.web.app.open_url_in_chrome", lambda *a: (_ for _ in ()).throw(ValueError("unsafe_test_execution")))
    with TestClient(create_app()) as client:
        result = client.post("/api/approved/fixture/review-run").json()
    assert result["ok"] is False
    assert result["blocked_reason"] == "campaign_expired"
    assert calls == []


def test_capability_eligibility_reloads_csv_without_writing_it(tmp_path, monkeypatch):
    path = tmp_path / "fixture-queue.csv"
    monkeypatch.setattr(assisted_session, "load_apply_queue", lambda: apply_queue.load_apply_queue(path))
    write_csv_rows(path, [candidate()], apply_queue.QUEUE_HEADERS)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assisted_session.validate_extension_candidate("fixture")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before

    # A separate manual action changes eligibility while mapping confirmation waits.
    write_csv_rows(path, [candidate(queue_status="PREPARED", submission_method="MANUAL")], apply_queue.QUEUE_HEADERS)
    changed = hashlib.sha256(path.read_bytes()).hexdigest()
    assert changed != before
    with pytest.raises(ValueError, match="already_manually_submitted"):
        assisted_session.validate_extension_candidate("fixture")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == changed


def test_capability_storage_failure_is_fail_closed_without_raw_error(monkeypatch):
    def unavailable():
        raise OSError("PRIVATE-FIXTURE-ERROR")
    monkeypatch.setattr(assisted_session, "load_apply_queue", unavailable)
    with pytest.raises(ValueError) as result:
        assisted_session.validate_extension_candidate("fixture")
    assert str(result.value) == "candidate_storage_unavailable"


def test_capability_duplicate_candidate_is_fail_closed(monkeypatch):
    monkeypatch.setattr(assisted_session, "load_apply_queue", lambda: [candidate(), candidate()])
    with pytest.raises(ValueError, match="candidate_ambiguous"):
        assisted_session.validate_extension_candidate("fixture")


@pytest.mark.parametrize("changes,reason", [
    ({"deadline": "2000-01-01"}, "campaign_expired"),
    ({"submission_method": "MANUAL"}, "already_manually_submitted"),
])
def test_queue_merge_does_not_erase_campaign_rejection(monkeypatch, changes, reason):
    calls = []
    monkeypatch.setattr(engine, "read_csv_rows", lambda _p: [candidate(**changes)])
    monkeypatch.setattr(engine, "load_apply_queue", lambda _p: [candidate(queue_status="PREPARED", deadline="", submission_method="")])
    monkeypatch.setattr(engine, "load_profile", lambda: calls.append("profile") or {})
    monkeypatch.setattr(engine, "build_profile_readiness", lambda _p: (_ for _ in ()).throw(ValueError("unsafe_test_execution")))
    with pytest.raises(ValueError, match=reason):
        engine.run_prepared_campaign_dry_run("fixture")
    assert calls == []
