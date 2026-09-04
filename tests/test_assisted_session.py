from __future__ import annotations

import json
import inspect
from pathlib import Path

import pytest

from kensho_assistant.app.assisted_session import (
    classify_completion_snapshot,
    clear_extension_control_token,
    clear_assisted_session_action,
    load_assisted_session_state,
    request_assisted_session_action,
    register_extension_control_token,
    issue_extension_capability,
    run_assisted_application_session,
    save_assisted_session_state,
    validate_extension_control_token,
)


def test_extension_capability_requires_canonical_origin_fingerprint_and_state(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    base = {
        "workflow_state": "MAPPING_CONFIRMED",
        "session_id": "session-1",
        "active_candidate_id": "candidate-1",
        "current_url": "https://example.invalid/apply",
        "form_fingerprint": "fingerprint-1",
        "confirmed_profile_keys": ["email"],
        "submitted_count_auto": 0,
    }
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session._EXTENSION_BRIDGE.start",
        lambda: ("127.0.0.1", 45678),
    )
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session._EXTENSION_BRIDGE.issue",
        lambda **_kwargs: {"token": "safe-token"},
    )

    save_assisted_session_state(base)
    issued = issue_extension_capability(
        session_id="session-1",
        candidate_id="candidate-1",
        origin="https://example.invalid",
        fingerprint="fingerprint-1",
        profile={"email": "fixture@example.invalid"},
        profile_keys=["email"],
    )
    assert issued["token"] == "safe-token"

    with pytest.raises(ValueError, match="invalid_capability_payload"):
        issue_extension_capability(
            session_id="session-1", candidate_id="candidate-1",
            origin="https://example.invalid", fingerprint="fingerprint-1",
            profile={"phone": "00000000000"}, profile_keys=["phone"],
        )

    for changed in (
        {"origin": "https://other.invalid"},
        {"fingerprint": "fingerprint-2"},
    ):
        with pytest.raises(ValueError, match="invalid_capability_binding"):
            issue_extension_capability(
                session_id="session-1",
                candidate_id="candidate-1",
                origin=changed.get("origin", "https://example.invalid"),
                fingerprint=changed.get("fingerprint", "fingerprint-1"),
                profile={"email": "fixture@example.invalid"},
                profile_keys=["email"],
            )

    save_assisted_session_state({**base, "workflow_state": "HUMAN_ACTION_REQUIRED"})
    with pytest.raises(ValueError, match="invalid_capability_binding"):
        issue_extension_capability(
            session_id="session-1",
            candidate_id="candidate-1",
            origin="https://example.invalid",
            fingerprint="fingerprint-1",
            profile={"email": "fixture@example.invalid"},
            profile_keys=["email"],
        )


def test_assisted_session_runner_has_no_direct_profile_fill_path() -> None:
    source = inspect.getsource(run_assisted_application_session)

    assert "load_profile()" not in source
    assert 'AutoApplyEngine("dry_run"),\n                                page,\n                                campaign,\n                                load_profile()' not in source


def test_candidate_lock_discards_previous_mapping_binding() -> None:
    from kensho_assistant.app.assisted_session import _begin_candidate_workflow

    previous = {
        "workflow_state": "HELD", "active_candidate_id": "old",
        "session_id": "session", "form_fingerprint": "old-fingerprint",
        "confirmed_profile_keys": ["email"],
    }
    current = _begin_candidate_workflow(previous, session_id="session", candidate_id="new")
    assert current["active_candidate_id"] == "new"
    assert not current.get("form_fingerprint")
    assert not current.get("confirmed_profile_keys")
    assert previous["form_fingerprint"] == "old-fingerprint"


def test_extension_control_token_is_memory_only_and_clearable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON",
        tmp_path / "session.json",
    )
    token = register_extension_control_token("session-control")
    validate_extension_control_token("session-control", token)
    save_assisted_session_state({"session_id": "session-control", "submitted_count_auto": 0})
    assert token not in (tmp_path / "session.json").read_text(encoding="utf-8")
    clear_extension_control_token("session-control")
    with pytest.raises(ValueError, match="invalid_extension_control_token"):
        validate_extension_control_token("session-control", token)


def test_assisted_session_state_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    path = save_assisted_session_state(
        {
            "status": "AWAITING_USER_SUBMIT",
            "current_campaign_id": "abc",
            "submitted_count_auto": 0,
        }
    )
    data = load_assisted_session_state()
    assert path.exists()
    assert data["status"] == "AWAITING_USER_SUBMIT"
    assert data["submitted_count_auto"] == 0


def test_assisted_session_action_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    request_assisted_session_action("submitted_next", queue_id="abc", note="manual submit acknowledged")
    data = load_assisted_session_state()
    assert data["requested_action"] == "submitted_next"
    assert data["requested_queue_id"] == "abc"
    clear_assisted_session_action()
    cleared = load_assisted_session_state()
    assert cleared["requested_action"] == ""


def test_duplicate_operation_id_does_not_replace_pending_action(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    request_assisted_session_action(
        "submitted_next",
        queue_id="candidate-1",
        note="first",
        session_id="session-1",
        candidate_id="candidate-1",
        operation_id="operation-1",
    )
    request_assisted_session_action(
        "submitted_next",
        queue_id="candidate-1",
        note="duplicate",
        session_id="session-1",
        candidate_id="candidate-1",
        operation_id="operation-1",
    )

    state = load_assisted_session_state()
    assert state["requested_note"] == "first"
    assert state["requested_operation_id"] == "operation-1"


def test_assisted_session_corrupt_state_is_detected(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / "session.json"
    state_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", state_path)
    data = load_assisted_session_state()
    assert data["status"] == "ERROR"
    assert data["state_health"] == "corrupt"
    assert "状態ファイル" in data["message"]


def test_completion_classifier_distinguishes_complete_confirm_and_uncertain() -> None:
    complete = classify_completion_snapshot("https://example.com/thanks", "受付完了", "応募を受け付けました")
    confirm = classify_completion_snapshot("https://example.com/confirm", "確認画面", "内容を確認してください")
    uncertain = classify_completion_snapshot("https://example.com/next", "移動しました", "ありがとうございました")
    assert complete["state"] == "COMPLETED"
    assert confirm["state"] == "AWAITING_USER_SUBMIT"
    assert uncertain["state"] == "AWAITING_USER_NEXT"


def test_session_runner_processes_only_approved_prepared_rows(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    browser_launches: list[dict[str, object]] = []
    profile_loads: list[bool] = []
    control_states = iter(
        [
            {"status": "IDLE", "state_health": "ok", "updated_at": "2026-06-10T00:00:00+09:00"},
            {"requested_action": "submitted_next", "requested_queue_id": "a"},
            {"requested_action": "stop", "requested_queue_id": "b"},
        ]
    )

    class FakeLocator:
        def __init__(self, text: str = "") -> None:
            self._text = text

        def count(self) -> int:
            return 1

        def inner_text(self, timeout: int = 5000) -> str:
            return self._text

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://example.com/form"
            self._title = "応募フォーム"
            self._body = "入力画面"

        def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
            self.url = url

        def title(self) -> str:
            return self._title

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self._body)

        def screenshot(self, path: str, full_page: bool = True) -> None:
            Path(path).write_bytes(b"png")

        def content(self) -> str:
            return "<html><body>入力画面</body></html>"

    class FakeContext:
        def __init__(self, page: FakePage) -> None:
            self.pages = [page]
            self.closed = False

        def new_page(self) -> FakePage:
            return self.pages[0]

        def close(self) -> None:
            self.closed = True

    class FakeEngine:
        def __init__(self, mode: str) -> None:
            self.mode = mode

        def run(self, page, campaign, profile):
            calls.append(campaign["campaign_id"])
            return {
                "record": {
                    "campaign_id": campaign["campaign_id"],
                    "status": "AWAITING_USER_SUBMIT",
                    "submitted_count_auto": 0,
                    "needs_review_reasons": [],
                    "review_items": [],
                    "pre_submit_score": 95,
                    "unresolved_required_fields_count": 0,
                    "submit_button_detected": True,
                    "screenshot_path": str(tmp_path / f"{campaign['campaign_id']}.png"),
                    "html_snapshot_path": str(tmp_path / f"{campaign['campaign_id']}.html"),
                    "analysis_path": str(tmp_path / f"{campaign['campaign_id']}.analysis.json"),
                    "check_path": str(tmp_path / f"{campaign['campaign_id']}.check.json"),
                },
                "analysis": {},
                "pre_submit_check": {"status": "AWAITING_USER_SUBMIT"},
                "filled_fields": [],
                "missing_fields": [],
                "submit_result": {"status": "DRY_RUN_COMPLETED"},
            }

    def fake_load_state():
        return next(control_states, {"requested_action": ""})

    def fake_open_browser(playwright, url, browser_name="chrome", **kwargs):
        browser_launches.append({"url": url, "browser_name": browser_name, **kwargs})
        return FakeContext(FakePage()), FakePage(), browser_name

    monkeypatch.setattr("kensho_assistant.app.assisted_session.approved_queue_rows", lambda rows=None: [
        {"campaign_id": "a", "campaign_name": "A", "queue_status": "APPROVED", "approved_by_user": "true", "resolved_entry_url": "https://example.com/a"},
        {"campaign_id": "b", "campaign_name": "B", "queue_status": "PREPARED", "approved_by_user": "true", "resolved_entry_url": "https://example.com/b"},
        {"campaign_id": "c", "campaign_name": "C", "queue_status": "QUEUED", "approved_by_user": "false", "resolved_entry_url": "https://example.com/c"},
    ])
    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    monkeypatch.setattr("kensho_assistant.app.assisted_session.load_assisted_session_state", fake_load_state)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.clear_assisted_session_action", lambda: Path("session.json"))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.request_assisted_session_action", lambda action, queue_id="", note="": Path("session.json"))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.classify_completion_snapshot", lambda current_url, title, body_text, baseline_url="": {"state": "AWAITING_USER_SUBMIT", "manual_submit_observed": False, "completion_confirmed": False, "reason": ""})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.AutoApplyEngine", lambda mode: FakeEngine(mode))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.mark_manual_submitted", lambda queue_id: True)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.load_profile", lambda: profile_loads.append(True) or {"first_name": "太郎"})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.target_url_for_campaign", lambda campaign: campaign["resolved_entry_url"])
    monkeypatch.setattr("kensho_assistant.app.assisted_session.validate_dedicated_target_url", lambda url: url)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.dedicated_extension_page_state", lambda page, require_ready=False: {"status": "PASS"})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.open_url_in_chrome", fake_open_browser)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.sync_playwright", lambda: __import__("contextlib").nullcontext(object()))

    result = run_assisted_application_session(status_filter="APPROVED,PREPARED", limit=2, browser="chrome", keep_open=False)
    assert calls == ["a", "b"]
    assert browser_launches[0]["url"] == "about:blank"
    assert browser_launches[0]["use_dedicated_extension"] is True
    assert browser_launches[0]["run_id"] == result["session_id"]
    assert profile_loads == []
    assert result["processed"] == 2
    assert result["submitted_count_auto"] == 0
    assert result["status"] in {"completed", "stopped"}


def test_session_runner_handles_zero_candidates(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.load_assisted_session_state",
        lambda: {"status": "IDLE", "state_health": "missing", "updated_at": "2026-07-10T00:00:00+09:00"},
    )
    monkeypatch.setattr("kensho_assistant.app.assisted_session.approved_queue_rows", lambda rows=None: [])
    result = run_assisted_application_session(status_filter="APPROVED,PREPARED", limit=2, browser="chrome", keep_open=False)
    assert result["status"] == "completed"
    assert result["processed"] == 0
    assert result["submitted_count_auto"] == 0


def test_session_runner_skips_invalid_url_without_opening_form(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    class FakeLocator:
        def count(self) -> int:
            return 1

        def inner_text(self, timeout: int = 5000) -> str:
            return ""

    class FakePage:
        def __init__(self) -> None:
            self.url = "about:blank"

        def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
            calls.append(url)

        def title(self) -> str:
            return "応募フォーム"

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

    class FakeContext:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    context = FakeContext()

    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.load_assisted_session_state",
        lambda: {"status": "IDLE", "state_health": "missing", "updated_at": "2026-07-10T00:00:00+09:00"},
    )
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.approved_queue_rows",
        lambda rows=None: [
            {"campaign_id": "a", "campaign_name": "A", "queue_status": "APPROVED", "approved_by_user": "true", "resolved_entry_url": ""}
        ],
    )
    monkeypatch.setattr("kensho_assistant.app.assisted_session.mark_skipped", lambda queue_id, path=None: True)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.load_profile", lambda: {"first_name": "太郎"})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.target_url_for_campaign", lambda campaign: "")
    monkeypatch.setattr("kensho_assistant.app.assisted_session.open_url_in_chrome", lambda playwright, url, browser_name="chrome", **_kwargs: (context, FakePage(), browser_name))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.sync_playwright", lambda: __import__("contextlib").nullcontext(object()))

    result = run_assisted_application_session(status_filter="APPROVED,PREPARED", limit=1, browser="chrome", keep_open=False)
    assert result["status"] == "completed"
    assert result["processed"] == 0
    assert result["failed"] == 1
    assert calls == []


def test_session_runner_stops_when_candidate_is_removed(monkeypatch, tmp_path) -> None:
    queue_calls = iter(
        [
            [
                {"campaign_id": "a", "campaign_name": "A", "queue_status": "APPROVED", "approved_by_user": "true", "resolved_entry_url": "https://example.com/a"},
                {"campaign_id": "b", "campaign_name": "B", "queue_status": "APPROVED", "approved_by_user": "true", "resolved_entry_url": "https://example.com/b"},
            ],
            [],
        ]
    )

    class FakePage:
        def __init__(self) -> None:
            self.url = "about:blank"

        def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
            raise AssertionError("should stop before goto when candidate disappeared")

        def title(self) -> str:
            return "応募フォーム"

        def locator(self, selector: str):
            return __import__("types").SimpleNamespace(count=lambda: 1, inner_text=lambda timeout=5000: "入力画面")

    class FakeContext:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    context = FakeContext()

    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.load_assisted_session_state",
        lambda: {"status": "IDLE", "state_health": "missing", "updated_at": "2026-07-10T00:00:00+09:00"},
    )
    monkeypatch.setattr("kensho_assistant.app.assisted_session.approved_queue_rows", lambda rows=None: next(queue_calls, []))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.load_profile", lambda: {"first_name": "太郎"})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.target_url_for_campaign", lambda campaign: campaign["resolved_entry_url"])
    monkeypatch.setattr("kensho_assistant.app.assisted_session.validate_dedicated_target_url", lambda url: url)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.dedicated_extension_page_state", lambda page, require_ready=False: {"status": "PASS"})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.open_url_in_chrome", lambda playwright, url, browser_name="chrome", **_kwargs: (context, FakePage(), browser_name))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.sync_playwright", lambda: __import__("contextlib").nullcontext(object()))

    result = run_assisted_application_session(status_filter="APPROVED,PREPARED", limit=2, browser="chrome", keep_open=False)
    assert result["status"] == "stopped"
    assert result["failed"] == 1
    assert result["processed"] == 0
    assert context.closed is True


def test_session_runner_resumes_from_existing_state(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    resume_state = {
        "status": "AWAITING_USER_SUBMIT",
        "state_health": "ok",
        "session_id": "sess-1",
        "candidate_ids": ["a", "b"],
        "next_candidate_index": 2,
        "current_index": 1,
        "current_campaign_id": "a",
        "current_campaign_name": "A",
        "current_queue_status": "APPROVED",
        "updated_at": "2026-07-01T00:00:00+09:00",
        "session_started_at": "2026-07-01T00:00:00+09:00",
    }
    control_states = iter(
        [
            resume_state,
            {"requested_action": "submitted_next", "requested_queue_id": "b", "requested_session_id": "sess-1"},
        ]
    )

    class FakeLocator:
        def count(self) -> int:
            return 1

        def inner_text(self, timeout: int = 5000) -> str:
            return "入力画面"

    class FakePage:
        def __init__(self) -> None:
            self.url = "about:blank"

        def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000) -> None:
            self.url = url

        def title(self) -> str:
            return "応募フォーム"

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

    class FakeContext:
        def close(self) -> None:
            pass

    class FakeEngine:
        def __init__(self, mode: str) -> None:
            self.mode = mode

        def run(self, page, campaign, profile):
            calls.append(campaign["campaign_id"])
            return {
                "record": {
                    "campaign_id": campaign["campaign_id"],
                    "status": "AWAITING_USER_SUBMIT",
                    "submitted_count_auto": 0,
                    "needs_review_reasons": [],
                    "review_items": [],
                    "pre_submit_score": 95,
                    "unresolved_required_fields_count": 0,
                    "submit_button_detected": True,
                },
                "pre_submit_check": {"status": "AWAITING_USER_SUBMIT"},
            }

    monkeypatch.setattr("kensho_assistant.app.assisted_session.ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    monkeypatch.setattr("kensho_assistant.app.assisted_session.load_assisted_session_state", lambda: next(control_states, {"requested_action": ""}))
    monkeypatch.setattr(
        "kensho_assistant.app.assisted_session.approved_queue_rows",
        lambda rows=None: [
            {"campaign_id": "a", "campaign_name": "A", "queue_status": "APPROVED", "approved_by_user": "true", "resolved_entry_url": "https://example.com/a"},
            {"campaign_id": "b", "campaign_name": "B", "queue_status": "APPROVED", "approved_by_user": "true", "resolved_entry_url": "https://example.com/b"},
        ],
    )
    monkeypatch.setattr("kensho_assistant.app.assisted_session.AutoApplyEngine", lambda mode: FakeEngine(mode))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.mark_manual_submitted", lambda queue_id: True)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.load_profile", lambda: {"first_name": "太郎"})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.target_url_for_campaign", lambda campaign: campaign["resolved_entry_url"])
    monkeypatch.setattr("kensho_assistant.app.assisted_session.validate_dedicated_target_url", lambda url: url)
    monkeypatch.setattr("kensho_assistant.app.assisted_session.dedicated_extension_page_state", lambda page, require_ready=False: {"status": "PASS"})
    monkeypatch.setattr("kensho_assistant.app.assisted_session.open_url_in_chrome", lambda playwright, url, browser_name="chrome", **_kwargs: (FakeContext(), FakePage(), browser_name))
    monkeypatch.setattr("kensho_assistant.app.assisted_session.sync_playwright", lambda: __import__("contextlib").nullcontext(object()))

    result = run_assisted_application_session(status_filter="APPROVED,PREPARED", limit=2, browser="chrome", keep_open=False)
    assert calls == ["b"]
    assert result["session_id"] == "sess-1"
    assert result["processed"] == 1
    assert result["status"] in {"completed", "stopped"}
