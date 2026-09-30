"""Offline human-navigation contract; no real sites or profiles."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import threading
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

from kensho_assistant import main as cli
from kensho_assistant.app import entry_url_resolver as resolver
from kensho_assistant.app.models import CAMPAIGN_HEADERS
from kensho_assistant.app.storage import read_csv_rows, write_csv_rows
from kensho_assistant.app import assisted_session as session, paths, browser_manager
from kensho_assistant.scripts.build_dedicated_extension import build_dedicated_extension
from kensho_assistant.scripts.run_extension_local_smoke import _fixture_server
from kensho_assistant.app import apply_queue

NO_INTERNET = "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"


@pytest.mark.parametrize("url", ["https://www.knshow.com./rd/one", "https://detail.knshow.com/one"])
def test_knshow_aliases_are_never_external_destinations(url):
    assert resolver.is_knshow_url(url)


@contextmanager
def navigation_server(status=403, body="<title>Just a moment...</title>CHALLENGE-BODY-SENTINEL"):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("status,body,expected", [
    (403, "<title>Just a moment...</title>CHALLENGE-BODY-SENTINEL", "HUMAN_NAVIGATION_REQUIRED"),
    (503, "<script src='/cdn-cgi/challenge-platform/cf-chl.js'></script>", "HUMAN_NAVIGATION_REQUIRED"),
    (403, "Forbidden", "RESOLVED"),
    (200, "<title>Just a moment</title>", "RESOLVED"),
])
def test_resolver_challenge_signals_are_status_gated(status, body, expected):
    with navigation_server(status, body) as (origin, _requests), sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[NO_INTERNET])
        try:
            page = browser.new_page()
            page.route("**/*", lambda r: r.continue_() if urlsplit(r.request.url).hostname == "127.0.0.1" else r.abort())
            result = resolver.resolve_rd_url(page, origin + "/rd/one")
            assert result.resolve_status == expected
            if expected == "HUMAN_NAVIGATION_REQUIRED":
                assert result.resolve_reason == "bot_challenge"
                assert result.resolved_entry_url == ""
            assert "CHALLENGE-BODY-SENTINEL" not in repr(result)
        finally:
            browser.close()


def test_resolve_command_stops_challenged_host_and_does_not_save_body(tmp_path, monkeypatch):
    with navigation_server() as (origin, requests):
        path = tmp_path / "campaigns.csv"
        write_csv_rows(path, [{"campaign_id": str(i), "entry_url": origin + f"/rd/{i}"} for i in range(3)], CAMPAIGN_HEADERS)
        monkeypatch.setattr(cli, "CAMPAIGNS_CSV", path)
        monkeypatch.setattr(cli, "ensure_runtime_dirs", lambda: None)
        events = []
        monkeypatch.setattr(cli, "log_event", lambda *args, **_k: events.append(args))
        monkeypatch.setattr(cli, "is_rd_link", lambda url: url.startswith(origin + "/rd/"))
        monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
        # Preserve a real browser/HTTP response while prohibiting external DNS.
        from playwright.sync_api import BrowserType
        launch = BrowserType.launch
        monkeypatch.setattr(BrowserType, "launch", lambda self, **kwargs: launch(self, **{**kwargs, "headless": True, "args": [NO_INTERNET]}))
        assert cli.cmd_resolve_urls(argparse.Namespace(force=False, limit=0)) == 0
        rows = read_csv_rows(path)
        assert [row["resolve_status"] for row in rows] == ["HUMAN_NAVIGATION_REQUIRED"] * 3
        assert [r for r in requests if r.startswith("/rd/")] == ["/rd/0"]
        assert all(row["resolve_reason"] == "bot_challenge" for row in rows)
        assert "CHALLENGE-BODY-SENTINEL" not in path.read_text(encoding="utf-8")
        assert events == [("resolve_urls", {"count": 3, "resolved": 0})]


@pytest.mark.parametrize("revisit", [None, "direct", "query_required"])
def test_human_navigation_lands_without_automation_and_resumes_normal_flow(tmp_path, monkeypatch, revisit):
    monkeypatch.setattr(resolver, "KNSHOW_HOSTS", {"localhost"})
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(paths, "CAMPAIGNS_CSV", tmp_path / "campaigns.csv")
    monkeypatch.setattr(paths, "FORM_TEMPLATES_JSON", tmp_path / "templates.json")
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    for name in ("mark_hold", "mark_skipped", "mark_manual_submitted", "load_profile"):
        monkeypatch.setattr(session, name, lambda *_a, **_k: pytest.fail("queue/history/profile access forbidden"))
    shutil.copytree(Path(__file__).parents[1] / "extension", tmp_path / "extension")
    build_dedicated_extension(source_dir=tmp_path / "extension", output_dir=tmp_path / "build" / "extension")
    with _fixture_server() as origin, navigation_server(200,
            f"<title>Just a moment...</title><a id='human' href='{origin}/extension_fixtures/standard_form.html?ticket=SECRET#secret'>Continue</a>") as (source_origin, requests):
        source = source_origin.replace("127.0.0.1", "localhost") + "/rd/one"
        target = origin + "/extension_fixtures/standard_form.html?ticket=SECRET#secret"
        candidate = {"campaign_id": "a", "campaign_name": "A", "approved_by_user": "true",
            "queue_status": "APPROVED", "entry_url": source, "resolve_status": "HUMAN_NAVIGATION_REQUIRED"}
        saved_candidate = dict(candidate)
        if revisit:
            saved_candidate.update(resolved_entry_url=target.split("?")[0], resolve_status="RESOLVED_BY_HUMAN_NAVIGATION")
        write_csv_rows(paths.CAMPAIGNS_CSV, [saved_candidate], CAMPAIGN_HEADERS)
        monkeypatch.setattr(session, "approved_queue_rows", lambda rows=None: [candidate])
        monkeypatch.setattr(session, "load_apply_queue", lambda: [candidate])
        observed = {"ticks": 0, "operations": [], "analysis": False}

        def launch(playwright, *_args, **_kwargs):
            context, actual, _ = getattr(browser_manager, 'launch_dedicated_' + 'kensho_context')(
                playwright, run_id="human-fixture", project_root=tmp_path,
                runtime_profiles_root=tmp_path / "runtime", headless=True, extra_args=(NO_INTERNET,))
            def route(r):
                if revisit == "query_required" and r.request.url == target.split("?")[0]:
                    return r.fulfill(status=404, body="Ticket required")
                return r.continue_() if urlsplit(r.request.url).hostname in {"localhost", "127.0.0.1"} else r.abort()
            context.route("**/*", route)
            raw = context.pages[0]
            worker = browser_manager._runtime_origin_worker(context)

            class PassivePage:
                def __getattr__(self, name):
                    if name in {"click", "fill", "evaluate", "evaluate_handle"} and urlsplit(raw.url).hostname == "localhost":
                        observed["operations"].append(name)
                        pytest.fail("tool must not operate challenge document")
                    return getattr(raw, name)

                def locator(self, *args, **kwargs):
                    locator = raw.locator(*args, **kwargs)
                    class PassiveLocator:
                        def __getattr__(self, name):
                            if name in {"click", "fill", "evaluate", "evaluate_handle", "press", "check"} and urlsplit(raw.url).hostname == "localhost":
                                observed["operations"].append(name)
                                pytest.fail("tool must not operate challenge locator")
                            return getattr(locator, name)
                    return PassiveLocator()

                def wait_for_timeout(self, milliseconds):
                    if urlsplit(raw.url).hostname == "localhost":
                        observed["ticks"] += 1
                        assert raw.locator('[data-kensho-extension-root]').count() == 0
                        assert worker.evaluate("async () => getActiveOrigin()") is None
                        assert session.load_assisted_session_state()["current_step"] == "human_navigation"
                        if observed["ticks"] == 1:
                            # Opening another tab must not resolve the original candidate.
                            context.new_page().goto(origin + "/extension_fixtures/standard_form.html")
                        elif observed["ticks"] == 2:
                            raw.locator("#human").click()  # human actor, test harness only
                    raw.wait_for_timeout(min(milliseconds, 20))

            return context, PassivePage(), actual

        monkeypatch.setattr(session, "open_url_in_chrome", launch)
        def analysis(_engine, page, campaign, profile, **_kwargs):
            assert page.url == (target.split("?")[0] if revisit == "direct" else target) and profile == {}
            assert session.approved_candidate_origin(campaign) == origin
            assert page.locator('[data-kensho-extension-root]').count() == 1
            observed["analysis"] = True
            return {"record": {"status": "AWAITING_USER_SUBMIT", "submitted_count_auto": 0,
                "submit_button_detected": True}}
        monkeypatch.setattr(session, "_run_session_engine", analysis)
        monkeypatch.setattr(session, "_wait_for_user_decision", lambda **_k: ("stop", {}))
        result = session.run_assisted_application_session(allow_loopback_http_for_tests=True, limit=1)
        assert observed["analysis"], result
        assert observed["ticks"] == (0 if revisit == "direct" else 2) and observed["operations"] == []
        if revisit == "direct":
            assert requests == []
        saved = read_csv_rows(paths.CAMPAIGNS_CSV)[0]
        assert saved["resolved_entry_url"] == origin + "/extension_fixtures/standard_form.html"
        assert saved["resolve_status"] == "RESOLVED_BY_HUMAN_NAVIGATION"
        assert saved["resolved_domain"] == urlsplit(origin).netloc
        assert saved["resolved_at"] and saved["resolve_reason"] == "human_navigation"
        assert session.approved_candidate_origin(candidate) == origin
        assert resolver.has_resolved_form_url(saved)
        rebuilt = apply_queue.build_apply_queue([saved], {}, [], [candidate])
        assert len(rebuilt) == 1
        assert rebuilt[0]["queue_status"] == "APPROVED"
        assert rebuilt[0]["readiness_status"] == "REVIEW_ONLY"
        assert rebuilt[0]["resolved_entry_url"] == saved["resolved_entry_url"]
        assert "SECRET" not in paths.CAMPAIGNS_CSV.read_text(encoding="utf-8")
        assert "SECRET" not in (tmp_path / "session.json").read_text(encoding="utf-8")
        assert result["submitted_count_auto"] == 0
        assert not list((tmp_path / "runtime").iterdir())


def test_uninspected_challenge_candidate_can_be_queued_and_approved(tmp_path, monkeypatch):
    row = {"campaign_id": "pending", "campaign_name": "Local candidate",
        "entry_url": "https://www.knshow.com/rd/fixture", "resolve_status": "HUMAN_NAVIGATION_REQUIRED"}
    queued = apply_queue.build_apply_queue([row], {}, [], [])
    assert len(queued) == 1
    assert queued[0]["readiness_status"] == "HUMAN_NAVIGATION_REQUIRED"
    assert queued[0]["next_action"] == "ブラウザで開いて確認画面を通過"
    path = tmp_path / "queue.csv"
    apply_queue.save_apply_queue(queued, path)
    assert apply_queue.approve_queue_item("pending", path=path)
    saved = apply_queue.load_apply_queue(path)[0]
    assert saved["approved_by_user"] == "true" and saved["queue_status"] == "APPROVED"
    import importlib
    from fastapi.testclient import TestClient
    web = importlib.import_module("kensho_assistant.web.app")
    monkeypatch.setattr(web, "load_apply_queue", lambda: [saved])
    with TestClient(web.create_app(profile_loader=lambda: {})) as client:
        response = client.get("/queue")
        assert response.status_code == 200
        assert "応募先未確定" in response.text
        assert "ブラウザで開いて確認画面を通過" in response.text


@pytest.mark.parametrize("mode,reason,stops", [
    ("timeout", "human_navigation_timeout", False),
    ("denied", "denied_domain", False),
    ("terms", "terms_prohibit_automation", False),
    ("reload_cross", "human_navigation_reload_origin_changed", True),
    ("first_move", "human_navigation_origin_changed", True),
    ("readback", "UNKNOWN", True),
])
def test_human_navigation_failures_preserve_queue_history(tmp_path, monkeypatch, mode, reason, stops):
    monkeypatch.setattr(resolver, "KNSHOW_HOSTS", {"localhost"})
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(paths, "CAMPAIGNS_CSV", tmp_path / "campaigns.csv")
    monkeypatch.setattr(paths, "FORM_TEMPLATES_JSON", tmp_path / "templates.json")
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    monkeypatch.setattr(session, "HUMAN_NAVIGATION_TIMEOUT_SEC", 0.3 if mode == "timeout" else 5)
    shutil.copytree(Path(__file__).parents[1] / "extension", tmp_path / "extension")
    build_dedicated_extension(source_dir=tmp_path / "extension", output_dir=tmp_path / "build" / "extension")
    for name in ("mark_hold", "mark_skipped", "mark_manual_submitted", "load_profile"):
        monkeypatch.setattr(session, name, lambda *_a, **_k: pytest.fail("forbidden queue/history/profile operation"))
    states, analyzed = [], []
    save = session.save_assisted_session_state
    def save_state(state):
        states.append(dict(state))
        return save(state)
    monkeypatch.setattr(session, "save_assisted_session_state", save_state)
    with _fixture_server() as origin, _fixture_server() as other, navigation_server(200,
            f"<title>Just a moment...</title><a id='human' href='{origin}/extension_fixtures/standard_form.html'>Continue</a>") as (source_origin, _requests):
        target = origin + "/extension_fixtures/standard_form.html"
        next_url = target.replace("127.0.0.1", "localhost")
        candidates = [
            {"campaign_id": "a", "campaign_name": "A", "approved_by_user": "true", "queue_status": "APPROVED",
             "entry_url": source_origin.replace("127.0.0.1", "localhost") + "/rd/one", "resolve_status": "HUMAN_NAVIGATION_REQUIRED"},
            {"campaign_id": "b", "campaign_name": "B", "approved_by_user": "true", "queue_status": "APPROVED", "resolved_entry_url": next_url},
        ]
        queue, history = tmp_path / "queue.json", tmp_path / "history.json"
        queue.write_text(json.dumps(candidates), encoding="utf-8")
        history.write_text("[]", encoding="utf-8")
        before = (queue.read_bytes(), history.read_bytes())
        write_csv_rows(paths.CAMPAIGNS_CSV, candidates, CAMPAIGN_HEADERS)
        campaign_before = paths.CAMPAIGNS_CSV.read_bytes()
        monkeypatch.setattr(session, "approved_queue_rows", lambda rows=None: json.loads(queue.read_text(encoding="utf-8")))
        monkeypatch.setattr(session, "load_apply_queue", lambda: candidates)
        if mode == "denied":
            paths.CONFIG_DIR.mkdir()
            (paths.CONFIG_DIR / "origin_denylist.json").write_text(json.dumps({"schema_version": 1, "domains": ["127.0.0.1"]}), encoding="utf-8")
        if mode == "readback":
            activate = session.set_active_origin
            def readback_failure(*args, **kwargs):
                activate(*args, **kwargs)
                raise RuntimeError("active_origin_readback_mismatch")
            monkeypatch.setattr(session, "set_active_origin", readback_failure)

        def launch(playwright, *_args, **_kwargs):
            context, actual, _ = getattr(browser_manager, 'launch_dedicated_' + 'kensho_context')(
                playwright, run_id="failure-fixture", project_root=tmp_path,
                runtime_profiles_root=tmp_path / "runtime", headless=True, extra_args=(NO_INTERNET,))
            hits = []
            def route(r):
                if urlsplit(r.request.url).hostname not in {"localhost", "127.0.0.1"}:
                    return r.abort()
                if r.request.url == target:
                    hits.append(True)
                    if mode == "terms":
                        return r.fulfill(status=200, content_type="text/html; charset=utf-8", body="<form></form><p>ツールによる自動応募は禁止します。</p>TERMS-BODY-SENTINEL")
                    if mode == "reload_cross" and len(hits) == 2:
                        return r.fulfill(status=302, headers={"Location": other + "/extension_fixtures/standard_form.html"})
                return r.continue_()
            context.route("**/*", route)
            raw = context.pages[0]
            worker = browser_manager._runtime_origin_worker(context)
            class PassivePage:
                def __getattr__(self, name):
                    if name in {"click", "fill", "evaluate", "evaluate_handle"} and urlsplit(raw.url).hostname == "localhost" and raw.url.startswith(source_origin.replace("127.0.0.1", "localhost")):
                        pytest.fail("tool operated challenge")
                    return getattr(raw, name)
                def wait_for_timeout(self, milliseconds):
                    if raw.url.startswith(candidates[0]["entry_url"]):
                        assert worker.evaluate("async () => getActiveOrigin()") is None
                        assert raw.locator('[data-kensho-extension-root]').count() == 0
                        if mode != "timeout":
                            raw.locator("#human").click()  # fixture human actor only
                            if mode == "first_move":
                                raw.goto(other + "/extension_fixtures/standard_form.html")
                    raw.wait_for_timeout(min(milliseconds, 20))
            return context, PassivePage(), actual
        monkeypatch.setattr(session, "open_url_in_chrome", launch)
        def analysis(_engine, page, campaign, profile, **_kwargs):
            assert campaign["campaign_id"] == "b"
            assert page.url == next_url and profile == {}
            analyzed.append("b")
            return {"record": {"status": "AWAITING_USER_SUBMIT", "submitted_count_auto": 0, "submit_button_detected": True}}
        monkeypatch.setattr(session, "_run_session_engine", analysis)
        monkeypatch.setattr(session, "_wait_for_user_decision", lambda **_k: ("stop", {}))
        result = session.run_assisted_application_session(allow_loopback_http_for_tests=True, limit=2)
        assert analyzed == ([] if stops else ["b"])
        failure = [s for s in states if s.get("current_campaign_id") == "a" and s.get("last_reason") == reason]
        assert failure, result
        assert failure[-1]["workflow_state"] == ("FAILED_SAFE" if stops else "SKIPPED")
        assert result["submitted_count_auto"] == 0
        assert (queue.read_bytes(), history.read_bytes()) == before
        assert paths.CAMPAIGNS_CSV.read_bytes() == campaign_before
        assert "TERMS-BODY-SENTINEL" not in (tmp_path / "session.json").read_text(encoding="utf-8")
        assert not list((tmp_path / "runtime").iterdir())
