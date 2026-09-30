"""Real local API/worker/bridge round trip, without real candidates or profiles."""
from __future__ import annotations

import importlib
import hashlib
import json
import socket
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import uvicorn
import pytest

from kensho_assistant.app import assisted_session as session
from kensho_assistant.app import paths, browser_manager, form_template_store as template_store
from kensho_assistant.app.extension_bridge import CapabilityBridge
from kensho_assistant.app.browser_manager import launch_dedicated_kensho_context, close_browser_safely
from kensho_assistant.scripts.build_dedicated_extension import build_dedicated_extension
from kensho_assistant.scripts.run_extension_local_smoke import (
    _approve_all_visible_mappings,
    _build_smoke_extension,
    _fixture_server,
    _wait_for_worker,
    _worker_evaluate,
)

NO_INTERNET = "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"


@pytest.mark.parametrize("rejected_url,reason,safety_failure", [
    ("https://x.com/entry", "denied_domain", None),
    ("https://login.example.invalid/entry", "login_subdomain", None),
    ("http://example.invalid/entry", "https_required", None),
    ("https://x.com/entry", "denied_domain", "extension_state"),
    ("https://x.com/entry", "denied_domain", "origin_readback"),
    ("https://x.com/entry", "origin_policy_invalid", "policy_config"),
])
def test_rejected_origin_skips_candidate_without_queue_or_history_writes(
    tmp_path, monkeypatch, rejected_url, reason, safety_failure,
):
    state_path = tmp_path / "session.json"
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", state_path)
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(paths, "FORM_TEMPLATES_JSON", tmp_path / "form_templates.json")
    queue = tmp_path / "apply_queue.json"
    history = tmp_path / "history.json"
    history.write_text("[]", encoding="utf-8")
    snapshots, calls, launches, cleared = [], [], [], []
    save = session.save_assisted_session_state
    def observe_state(state):
        snapshots.append(dict(state))
        return save(state)
    monkeypatch.setattr(session, "save_assisted_session_state", observe_state)
    def forbidden(*_args, **_kwargs):
        pytest.fail("candidate/history writes and real profile reads are forbidden")
    for name in ("mark_hold", "mark_skipped", "mark_manual_submitted", "load_profile"):
        monkeypatch.setattr(session, name, forbidden)

    with _fixture_server() as origin:
        target = f"{origin}/extension_fixtures/standard_form.html"
        candidates = [
            {"campaign_id": "a", "campaign_name": "A", "queue_status": "APPROVED",
             "approved_by_user": "true", "resolved_entry_url": rejected_url},
            {"campaign_id": "b", "campaign_name": "B", "queue_status": "APPROVED",
             "approved_by_user": "true", "resolved_entry_url": target},
        ]
        queue.write_text(json.dumps(candidates), encoding="utf-8")
        def hashes():
            return [hashlib.sha256(path.read_bytes()).hexdigest() for path in (queue, history)]
        before = hashes()
        monkeypatch.setattr(session, "approved_queue_rows", lambda rows=None: json.loads(queue.read_text(encoding="utf-8")))
        monkeypatch.setattr(session, "target_url_for_campaign", lambda row: row["resolved_entry_url"])
        extension_dir = _build_smoke_extension(tmp_path, origin)
        build_dedicated_extension(source_dir=extension_dir, output_dir=tmp_path / "build" / "extension")
        def launch(playwright, url, browser, **_kwargs):
            assert url == "about:blank"
            launches.append(url)
            context, actual, _build = launch_dedicated_kensho_context(
                playwright, run_id="origin-skip", project_root=tmp_path,
                runtime_profiles_root=tmp_path / "runtime", headless=True,
                extra_args=(NO_INTERNET,),
            )
            try:
                context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
                worker = _wait_for_worker(context)
                assert _worker_evaluate(context, urlsplit(worker.url).netloc,
                    "async () => { await scheduleReconciliation(); return dedicatedRuntimeOriginMode() && !(await getActiveOrigin()) && (await chrome.scripting.getRegisteredContentScripts()).length === 0; }") is True
                if safety_failure == "policy_config":
                    paths.CONFIG_DIR.mkdir()
                    (paths.CONFIG_DIR / "origin_denylist.json").write_text('{"schema_version": 0}', encoding="utf-8")
                return context, context.pages[0], actual
            except Exception:
                close_browser_safely(context)
                raise
        monkeypatch.setattr(session, "open_url_in_chrome", launch)
        clear = session.clear_active_origin
        def observe_clear(context):
            clear(context)
            worker = browser_manager._runtime_origin_worker(context)
            assert worker.evaluate("async () => (await chrome.scripting.getRegisteredContentScripts()).length") == 0
            cleared.append(True)
        monkeypatch.setattr(session, "clear_active_origin", observe_clear)
        def unsafe_extension(*_args, **_kwargs):
            raise RuntimeError("dedicated_extension_state_invalid")
        if safety_failure == "extension_state":
            monkeypatch.setattr(session, "dedicated_extension_page_state", unsafe_extension)
        elif safety_failure == "origin_readback":
            activate = session.set_active_origin
            def unsafe_readback(*args, **kwargs):
                activate(*args, **kwargs)
                raise RuntimeError("active_origin_readback_mismatch")
            monkeypatch.setattr(session, "set_active_origin", unsafe_readback)
        def analysis_boundary(_engine, page, campaign, profile, **_kwargs):
            assert campaign["campaign_id"] == "b" and page.url == target and profile == {}
            assert hashes() == before
            skipped = [state for state in snapshots if state.get("last_action") == "DEDICATED_ORIGIN_NOT_APPROVED"
                       and state.get("current_campaign_id") == "a" and state.get("workflow_state") == "SKIPPED"]
            assert skipped and skipped[-1]["workflow_state"] == "SKIPPED"
            assert skipped[-1]["last_reason"] == reason
            assert skipped[-1]["failed"] == 1 and skipped[-1]["skip_count"] == 1
            assert skipped[-1]["next_candidate_index"] == 2
            assert len(cleared) >= 3
            calls.append(campaign["campaign_id"])
            return {"record": {"status": "AWAITING_USER_SUBMIT", "submitted_count_auto": 0,
                               "submit_button_detected": True}}
        monkeypatch.setattr(session, "_run_session_engine", analysis_boundary)
        monkeypatch.setattr(session, "_wait_for_user_decision", lambda **_kwargs: ("stop", {}))
        result = session.run_assisted_application_session(
            allow_loopback_http_for_tests=True, limit=2, keep_open=False, poll_interval_sec=0.01,
        )
        if safety_failure:
            assert calls == [] and result["status"] == "stopped"
            assert result["processed"] == 0
            assert result["failed"] == (1 if safety_failure == "policy_config" else 2)
            state = session.load_assisted_session_state()
            assert state["current_step"] == ("origin_not_approved" if safety_failure == "policy_config" else "navigation_failed")
            assert state["skip_count"] == (0 if safety_failure == "policy_config" else 1)
            if safety_failure == "policy_config":
                assert state["workflow_state"] == "FAILED_SAFE"
                assert state["last_reason"] == "origin_policy_invalid"
            assert hashes() == before and result["submitted_count_auto"] == 0
            assert launches == ["about:blank"]
            assert not list((tmp_path / "runtime").iterdir())
            return
        assert calls == ["b"]
        assert launches == ["about:blank"]
        assert result["processed"] == 1 and result["failed"] == 1
        assert result["submitted_count_auto"] == 0
        assert session.load_assisted_session_state()["skip_count"] == 1
        assert session.load_assisted_session_state()["origin_skip_reasons"] == [reason]
        assert hashes() == before
        assert not list((tmp_path / "runtime").iterdir())


def test_normal_session_uuid_is_not_redacted_as_postal_code(tmp_path, monkeypatch):
    # A normal runner UUID can contain a seven-digit run. Corrupting that ID
    # makes the unchanged control/capability binding reject the valid session.
    monkeypatch.setattr(session, "ASSISTED_SESSION_DIR", tmp_path)
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", tmp_path / "session.json")
    identifier = "a1234567babcdef0a1234567babcdef0"
    session.save_assisted_session_state({"session_id": identifier})
    assert session.load_assisted_session_state()["session_id"] == identifier
    monkeypatch.setattr(session, "_PILOT_STORAGE", object())
    assert session._normalize_state({"session_id": identifier})["session_id"] == "a123-****babcdef0a123-****babcdef0"


@contextmanager
def local_management_api(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "local management API did not start"
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


@pytest.mark.parametrize("mutation,cleanup", [(None, "rollback"), (None, "clear"),
    ("form_changed", "rollback"), ("template_unconfirmed", "rollback"),
    ("version_changed", "rollback"), ("duplicate_tab", "rollback"),
    ("document_changed", "rollback"), ("after_provision_reload", "rollback")])
def test_real_assisted_mapping_bridge_fill_rollback(tmp_path, monkeypatch, caplog, mutation, cleanup):
    monkeypatch.setattr(template_store, "ALLOW_LOOPBACK_HTTP_FOR_TESTS", True)
    monkeypatch.setattr(paths, "FORM_TEMPLATES_JSON", tmp_path / "form_templates.json")
    web = importlib.import_module("kensho_assistant.web.app")
    state_path = tmp_path / "session.json"
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", state_path)
    monkeypatch.setattr(session, "_EXTENSION_BRIDGE", CapabilityBridge())
    monkeypatch.setattr(session, "_EXTENSION_CONTROL_TOKENS", {})
    monkeypatch.setattr(session, "_EXTENSION_PROGRESS_RESPONSES", {})
    profile = {
        "last_name": "LOCAL-SENTINEL-92741", "first_name": "FIXTURE",
        "email": "local-sentinel-92741@example.invalid", "phone": "00000000000",
        "postal_code": "0000000", "prefecture": "福岡県", "city": "架空市",
        "street": "LOCAL-SENTINEL-92741", "building": "FIXTURE",
    }
    profile_loads = []
    def dummy_profile():
        profile_loads.append(True)
        return dict(profile)
    monkeypatch.setattr(
        web,
        "load_profile",
        lambda: pytest.fail("real profile loader must not run in fixture integration"),
    )
    # Normal history must never be touched, even if a regression takes a wrong branch.
    def forbidden_history(*_args, **_kwargs):
        raise AssertionError("normal candidate/history write attempted")
    for name in ("mark_hold", "mark_skipped", "mark_manual_submitted"):
        monkeypatch.setattr(session, name, forbidden_history)

    observed = {"post_fill": False, "rollback": False, "clear": False}
    requests = []
    errors = []
    page_holder = {}
    api_requests = []
    consumed = []
    consume = session._EXTENSION_BRIDGE.consume
    def observe_consume(**kwargs):
        result = consume(**kwargs)
        consumed.append(True)
        with pytest.raises(ValueError, match="invalid_capability"):
            consume(**kwargs)
        return result
    monkeypatch.setattr(session._EXTENSION_BRIDGE, "consume", observe_consume)
    app = web.create_app(profile_loader=dummy_profile)
    @app.middleware("http")
    async def observe_api(request, call_next):
        response = await call_next(request)
        api_requests.append((request.url.path, request.method, response.status_code))
        return response

    with _fixture_server() as origin, local_management_api(app) as api:
        target = f"{origin}/extension_fixtures/standard_form.html"
        candidate = {
            "campaign_id": "local-integration", "campaign_name": "Local fixture",
            "queue_status": "APPROVED", "approved_by_user": "true",
            "resolved_entry_url": target,
            "terms_check_uncertain": "true",
        }
        monkeypatch.setattr(session, "approved_queue_rows", lambda rows=None: [candidate])
        monkeypatch.setattr(session, "load_apply_queue", lambda: [candidate])
        monkeypatch.setattr(session, "target_url_for_campaign", lambda row: row["resolved_entry_url"])
        def local_only(url, **kwargs):
            assert url == target
            return url
        monkeypatch.setattr(session, "validate_dedicated_target_url", local_only)

        extension_dir = _build_smoke_extension(tmp_path, origin)
        manifest_path = extension_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("version_name")  # No fixture-bridge bypass in this test.
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        worker_path = extension_dir / "service-worker.js"
        worker_path.write_text(
            worker_path.read_text(encoding="utf-8").replace("http://127.0.0.1:8787", api),
            encoding="utf-8",
        )
        config = tmp_path / "config" / "approved_origins.json"
        config.parent.mkdir()
        config.write_text(json.dumps({"schema_version": 1, "origins": [origin]}), encoding="utf-8")
        build_dedicated_extension(
            source_dir=extension_dir, output_dir=tmp_path / "build" / "extension",
            approved_origins_path=config,
        )

        def launch(playwright, _url, _browser, **_kwargs):
            context, browser, _build = launch_dedicated_kensho_context(
                playwright, run_id="local-integration", project_root=tmp_path,
                runtime_profiles_root=tmp_path / "runtime", headless=True,
                extra_args=(NO_INTERNET,),
            )
            def record(request):
                parsed = urlsplit(request.url)
                # Never retain request bodies, query strings or input values.
                requests.append((parsed.hostname, parsed.path, request.method))
            context.on("request", record)
            context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
            try:
                worker = browser_manager._runtime_origin_worker(context)
                assert worker.evaluate("async () => { await scheduleReconciliation(); return (await chrome.scripting.getRegisteredContentScripts()).length; }") == 0
                page = context.pages[0]
                page_holder.update(page=page, worker=worker)
                return context, page, browser
            except Exception:
                close_browser_safely(context)
                raise
        monkeypatch.setattr(session, "open_url_in_chrome", launch)

        # Legacy Python analysis is not the subject: stop at its real adapter boundary.
        # Mapping, state transitions, API endpoints, worker and bridge are not stubbed.
        def analysis_boundary(_engine, page, campaign, profile, **_kwargs):
            assert profile == {}
            return {"record": {
                "status": "AWAITING_USER_SUBMIT", "mapping_review_required": True,
                "submit_button_detected": True, "submitted_count_auto": 0,
            }}
        monkeypatch.setattr(session, "_run_session_engine", analysis_boundary)

        def human_mapping(**_kwargs):
            page = page_holder["page"]
            if mutation is None:
                page.evaluate("""() => {
                  const form = document.querySelector('#entry-form');
                  form.insertAdjacentHTML('beforeend', `
                    <fieldset><legend>クイズ回答</legend>
                      <label><input type="radio" name="quiz" required>選択肢A</label>
                      <label><input type="radio" name="quiz">選択肢B</label></fieldset>
                    <label>アンケート<textarea name="survey" required style=""></textarea></label>
                    <label>メルマガ選択<select name="newsletter" required style="outline:1px dotted blue!important">
                      <option value="">選択してください</option><option>不要</option></select></label>
                    <label>生年月日<input type="date" name="birthday" required></label>
                    <a href="/terms">利用規約</a><a href="#requirements">応募要項</a>`);
                  document.querySelector('#terms').required = true;
                  const spacer = document.createElement('div');
                  spacer.style.height = '1500px';
                  document.querySelector('[name="custom_required_answer"]').closest('label').before(spacer);
                  window.fixtureSubmitClicks = 0;
                  document.querySelector('#submit-button').addEventListener('click', () => window.fixtureSubmitClicks++);
                }""")
                observed["original_styles"] = page.locator("#entry-form").evaluate("f => Array.from(f.elements, e => e.getAttribute('style'))")
            host = page.locator("#kensho-assistant-overlay-host")
            assert host.locator("#pre-submit-review").is_hidden()
            host.locator("#analyze").click()
            page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus === 'analyzed'")
            host.locator("#preview-button").click()
            page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus === 'previewed'")
            if host.locator("#approve-safe").is_enabled():
                host.locator("#approve-safe").click()
            _approve_all_visible_mappings(host)
            host.locator("#save-template").click()
            page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('保存しました')")
            observed["before"] = page.locator("#entry-form").evaluate("f => Array.from(f.elements, e => [e.value, e.checked, e.selectedIndex])")
            if mutation == "form_changed":
                page.locator('[name="email"]').evaluate("e => e.required = !e.required")
            if mutation in {"template_unconfirmed", "version_changed"}:
                page_holder["worker"].evaluate("""async ({url, mutation}) => {
                  const key = templateStorageKey(url);
                  const template = (await chrome.storage.local.get(key))[key];
                  if (mutation === 'template_unconfirmed') template.humanConfirmedAt = '';
                  else template.extensionVersion = '0.0.0';
                  await chrome.storage.local.set({[key]: template});
                }""", {"url": target, "mutation": mutation})
            if mutation == "duplicate_tab":
                page.context.new_page().goto(target)
            return "mapping_confirmed", {}
        monkeypatch.setattr(session, "_wait_for_user_decision", human_mapping)
        provision = session.provision_extension_control_token
        def provision_after_navigation(*args, **kwargs):
            if mutation == "after_provision_reload":
                result = provision(*args, **kwargs)
                page_holder["page"].reload(wait_until="domcontentloaded")
                return result
            page_holder["page"].reload(wait_until="domcontentloaded")
            return provision(*args, **kwargs)
        if mutation in {"document_changed", "after_provision_reload"}:
            monkeypatch.setattr(session, "provision_extension_control_token", provision_after_navigation)

        def human_fill_and_rollback(**_kwargs):
            page, worker = page_holder["page"], page_holder["worker"]
            host = page.locator("#kensho-assistant-overlay-host")
            try:
                if mutation == "after_provision_reload":
                    page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus === 'analyzed'")
                    host.locator("#preview-button").click()
                    page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus === 'previewed'")
                if mutation is None:
                    assert page.locator("#entry-form").evaluate("f => Array.from(f.elements, e => e.getAttribute('style'))") == observed["original_styles"], "style_changed_before_fill"
                host.locator("#fill").click()
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('入力済み')", timeout=7000)
                state = session.load_assisted_session_state()
                assert state["workflow_state"] == "HUMAN_ACTION_REQUIRED"
                for key, value in profile.items():
                    assert page.locator(f'[name="{key}"]').input_value() == value
                assert state["submitted_count_auto"] == 0
                assert not page.locator("#terms").is_checked()
                assert state["terms_check_uncertain"] is True
                review = host.locator("#pre-submit-review")
                assert review.is_visible()
                review_text = review.text_content()
                assert "送信前確認" in review_text
                assert "内容を確認し、送信ボタンはご自身で押してください" in review_text
                assert "規約に自動応募に関する記載あり・要確認" in review_text
                for value in profile.values():
                    assert value not in review_text
                for label in ("姓", "メールアドレス", "確認用の独自必須項目", "クイズ回答", "アンケート", "メルマガ選択", "生年月日", "利用規約に同意する"):
                    assert label in review_text
                assert review.locator("a").count() == 2
                assert review.locator('button[type="submit"], input, select, textarea').count() == 0
                assert review.locator("button").count() == 1
                assert page.evaluate("window.fixtureSubmitClicks") == 0
                assert page.locator("#entry-form").evaluate("f => Array.from(f.elements).filter(e => e.style.outline.includes('#c77600') || e.style.outline.includes('199, 118, 0')).length") == 7
                page.evaluate("window.scrollTo(0, 0)")
                review.locator("button").click()
                assert page.evaluate("window.scrollY") > 0
                assert page.locator('[name="custom_required_answer"]').evaluate("e => {const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight}")
                assert page.evaluate("window.fixtureSubmitClicks") == 0
                observed["post_fill"] = True
                host.locator("#rollback" if cleanup == "rollback" else "#clear").click()
                page.wait_for_function("text => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes(text)",
                                       arg="元に戻しました" if cleanup == "rollback" else "消去済み")
                assert page.locator("#entry-form").evaluate("f => Array.from(f.elements, e => [e.value, e.checked, e.selectedIndex])") == observed["before"]
                restored_styles = page.locator("#entry-form").evaluate("f => Array.from(f.elements, e => e.getAttribute('style'))")
                assert restored_styles == observed["original_styles"], "review_style_restore_mismatch"
                assert review.is_hidden()
                assert review.text_content() == ""
                assert page.locator("#entry-form").evaluate("f => Array.from(f.elements).filter(e => e.style.outline.includes('#c77600') || e.style.outline.includes('199, 118, 0')).length") == 0
                observed["rollback"] = True
                if cleanup == "rollback":
                    host.locator("#clear").click()
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('消去')")
                persisted = worker.evaluate("async () => [await chrome.storage.local.get(null), await chrome.storage.sync.get(null), await chrome.storage.session.get(null)]")
                assert "LOCAL-SENTINEL-92741" not in json.dumps(persisted)
                assert profile["email"] not in json.dumps(persisted)
                assert not persisted[2].get("kenshoBridgeCapability")
                assert not persisted[2].get("kenshoProgressCapability")
                assert not persisted[2].get("kenshoControlCapability")
                assert page.url == target
                guard = page.evaluate("() => window.__KENSHO_SUBMIT_GUARD__.state()")
                assert guard["submitted_count_auto"] == 0
                assert guard["blockedAttempts"] == 0
                observed["clear"] = True
            except Exception as error:
                errors.append((type(error).__name__, error.__traceback__.tb_lineno))
                observed["stop_reason"] = host.locator("#status").text_content()
                raise
            return {}, "stop", {}
        monkeypatch.setattr(session, "_wait_for_extension_verified_result", human_fill_and_rollback)

        result = session.run_assisted_application_session(allow_loopback_http_for_tests=True, limit=1, keep_open=False, poll_interval_sec=0.01)

    if mutation:
        assert not observed["post_fill"]
        assert not profile_loads and not consumed
        assert session.load_assisted_session_state()["workflow_state"] == "FAILED_SAFE"
        assert not any(path == "/api/session/extension-capability" for path, _method, _code in api_requests)
        assert result["submitted_count_auto"] == 0
        assert not list((tmp_path / "runtime").iterdir())
        return
    assert observed["post_fill"], (observed.get("stop_reason"), errors, result["message"])
    assert observed["rollback"] and observed["clear"], (observed.get("stop_reason"), errors)
    assert result["submitted_count_auto"] == 0
    assert result["ok"] == 0
    assert not list((tmp_path / "runtime").iterdir())
    assert consumed == [True]
    assert profile_loads == [True]
    assert all(host == "127.0.0.1" for host, _path, _method in requests)
    for endpoint in ("/api/session/extension-capability", "/api/session/extension-progress", "/api/session/extension-capability/revoke"):
        assert any(path == endpoint and method == "POST" and code == 200 for path, method, code in api_requests), endpoint
    for sentinel in (profile["email"], profile["last_name"]):
        assert sentinel not in state_path.read_text(encoding="utf-8")
        assert sentinel not in caplog.text
        for path in tmp_path.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                assert sentinel.encode() not in content, path.name
                assert sentinel.encode("utf-16-le") not in content, path.name


@pytest.mark.parametrize("second", ["matched", "form_changed", "path_changed", "version_changed", "build_changed", "expired", "seed_readback_failed", "verification_failed"])
def test_templates_survive_new_dedicated_profile(tmp_path, monkeypatch, caplog, second):
    """Real normal-session approvals, bridge verification, and fresh-profile reuse."""
    web = importlib.import_module("kensho_assistant.web.app")
    state_path = tmp_path / "session.json"
    store_path = tmp_path / "form_templates.json"
    monkeypatch.setattr(template_store, "ALLOW_LOOPBACK_HTTP_FOR_TESTS", True)
    monkeypatch.setattr(paths, "FORM_TEMPLATES_JSON", store_path)
    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(session, "ASSISTED_SESSION_STATE_JSON", state_path)
    monkeypatch.setattr(session, "_EXTENSION_BRIDGE", CapabilityBridge())
    monkeypatch.setattr(session, "_EXTENSION_CONTROL_TOKENS", {})
    monkeypatch.setattr(session, "_EXTENSION_PROGRESS_RESPONSES", {})
    monkeypatch.setattr(web, "load_profile", lambda: pytest.fail("real profile forbidden"))
    profile = {"last_name": "PERSIST-SENTINEL-92741", "first_name": "FIXTURE",
        "email": "persist-sentinel-92741@example.invalid", "phone": "00000000000",
        "postal_code": "0000000", "prefecture": "福岡県", "city": "架空市",
        "street": "PERSIST-SENTINEL-92741", "building": "FIXTURE"}
    app = web.create_app(profile_loader=lambda: dict(profile))
    holder = {}
    human_calls = []
    filled = []
    cycle = [0]
    real_wait = session._wait_for_extension_verified_result
    real_evaluate = browser_manager.evaluate_worker
    def corrupt_seed_readback(worker, expression, arg=None, **kwargs):
        if cycle[0] == 1 and second == "seed_readback_failed" and "const values = {};" in expression:
            expression = expression.replace("if (keys.some", "delete readback[keys[0]]; if (keys.some")
        return real_evaluate(worker, expression, arg, **kwargs)
    monkeypatch.setattr(browser_manager, "evaluate_worker", corrupt_seed_readback)
    def forbidden(*args, **kwargs):
        pytest.fail("normal history must remain untouched")
    for name in ("mark_hold", "mark_skipped", "mark_manual_submitted"):
        monkeypatch.setattr(session, name, forbidden)
    with _fixture_server() as origin, local_management_api(app) as api:
        target = f"{origin}/extension_fixtures/standard_form.html"
        candidate = {"campaign_id": "persist-fixture", "campaign_name": "Local fixture",
            "queue_status": "APPROVED", "approved_by_user": "true", "resolved_entry_url": target}
        monkeypatch.setattr(session, "approved_queue_rows", lambda rows=None: [candidate])
        monkeypatch.setattr(session, "load_apply_queue", lambda: [candidate])
        monkeypatch.setattr(session, "target_url_for_campaign", lambda row: target)
        monkeypatch.setattr(session, "validate_dedicated_target_url", lambda url, **kwargs: url if url == target else pytest.fail("nonfixture URL"))
        extension_dir = _build_smoke_extension(tmp_path, origin)
        manifest_path = extension_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("version_name")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        worker_path = extension_dir / "service-worker.js"
        worker_path.write_text(worker_path.read_text(encoding="utf-8").replace("http://127.0.0.1:8787", api), encoding="utf-8")
        config = paths.CONFIG_DIR / "approved_origins.json"
        config.parent.mkdir()
        config.write_text(json.dumps({"schema_version": 1, "origins": [origin]}), encoding="utf-8")
        build = build_dedicated_extension(source_dir=extension_dir, output_dir=tmp_path / "build" / "extension", approved_origins_path=config)
        def launch(playwright, *args, **kwargs):
            context, browser, _ = launch_dedicated_kensho_context(
                playwright, run_id=f"persist-{cycle[0]}", project_root=tmp_path,
                runtime_profiles_root=tmp_path / "runtime", headless=True, extra_args=(NO_INTERNET,))
            context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
            worker = browser_manager._runtime_origin_worker(context)
            assert worker.evaluate("async () => { await scheduleReconciliation(); return (await chrome.scripting.getRegisteredContentScripts()).length; }") == 0
            page = context.pages[0]
            holder.update(page=page, worker=worker)
            if cycle[0] == 2 or (cycle[0] == 1 and second == "form_changed"):
                page.add_init_script("document.addEventListener('DOMContentLoaded', () => document.querySelector('[name=email]').required = true)")
            return context, page, browser
        monkeypatch.setattr(session, "open_url_in_chrome", launch)
        monkeypatch.setattr(session, "_run_session_engine", lambda *a, **k: {"record": {
            "status": "AWAITING_USER_SUBMIT", "mapping_review_required": True,
            "submit_button_detected": True, "submitted_count_auto": 0}})
        def human_mapping(**kwargs):
            page = holder["page"]
            host = page.locator("#kensho-assistant-overlay-host")
            if session.load_assisted_session_state()["current_step"] != "mapping_review":
                return "stop", {}
            human_calls.append(cycle[0])
            if cycle[0] > 0 and (cycle[0] == 2 or second == "form_changed"):
                assert "フォーム変更" in host.locator("#status").text_content()
                assert page.locator('[name=email]').input_value() == ""
                # The initial button can be enabled, but its handler must refuse
                # filling without a matching preview/capability.
                host.locator("#fill").click()
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('入力前確認が必要')")
                assert page.locator('[name=email]').input_value() == ""
                return "stop", {}
            if page.evaluate("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus") != "previewed":
                host.locator("#analyze").click()
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus === 'analyzed'")
                host.locator("#preview-button").click()
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus === 'previewed'")
            if cycle[0] > 0:
                if second != "form_changed":
                    assert holder["worker"].evaluate("async url => !(await chrome.storage.local.get(templateStorageKey(url)))[templateStorageKey(url)]", target)
                assert page.locator('[name=email]').input_value() == ""
                assert host.locator("#fill").is_disabled()
                return "stop", {}
            if host.locator("#approve-safe").is_enabled():
                host.locator("#approve-safe").click()
            _approve_all_visible_mappings(host)
            host.locator("#save-template").click()
            page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('保存しました')")
            return "mapping_confirmed", {}
        monkeypatch.setattr(session, "_wait_for_user_decision", human_mapping)
        def fill(**kwargs):
            page = holder["page"]
            if second == "verification_failed":
                page.evaluate("() => document.querySelector('[name=email]').addEventListener('input', e => e.target.value = 'FIXTURE-MISMATCH')")
            if cycle[0] == 0:
                page.locator("#kensho-assistant-overlay-host").locator("#fill").click()
            if second == "verification_failed":
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('ロールバック')")
                return real_wait(**kwargs, timeout_sec=5)
            # Pump Playwright's loop while the loopback-only route handles bridge
            # requests, just like the existing fill/rollback integration test.
            try:
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('入力済み')", timeout=10000)
                result = real_wait(**kwargs, timeout_sec=10)
            except Exception as error:
                holder["failure"] = (type(error).__name__, page.locator("#kensho-assistant-overlay-host").locator("#status").text_content())
                raise
            assert page.locator('[name=email]').input_value() == profile["email"]
            assert not page.locator("#terms").is_checked()
            assert page.locator("#kensho-assistant-overlay-host").locator("#pre-submit-review").is_visible()
            assert "規約に自動応募に関する記載あり・要確認" not in page.locator("#kensho-assistant-overlay-host").locator("#pre-submit-review").text_content()
            assert session.load_assisted_session_state()["unrelated_changed_count"] == 0
            filled.append(cycle[0])
            return result
        monkeypatch.setattr(session, "_wait_for_extension_verified_result", fill)
        session.run_assisted_application_session(allow_loopback_http_for_tests=True, limit=1, poll_interval_sec=0.01)
        if second == "verification_failed":
            assert not store_path.exists()
            assert filled == []
            assert session.load_assisted_session_state()["workflow_state"] == "FAILED_SAFE"
            for sentinel in (profile["email"], profile["last_name"]):
                assert sentinel not in caplog.text
                for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
                    assert sentinel.encode(encoding) not in state_path.read_bytes()
            assert not list((tmp_path / "runtime").iterdir())
            return
        assert human_calls == [0] and filled == [0], holder.get("failure", session.load_assisted_session_state()["last_reason"])
        records = template_store.load_templates()
        assert len(records) == 1 and records[0]["extension_build_sha256"] == build.build_sha256
        if second in {"path_changed", "version_changed", "build_changed", "expired"}:
            records[0][{"path_changed": "pathname", "version_changed": "extensionVersion",
                "build_changed": "extension_build_sha256", "expired": "humanConfirmedAt"}[second]] = {
                    "path_changed": "/other", "version_changed": "0.0.0", "build_changed": "b" * 64,
                    "expired": "2020-01-01T00:00:00Z"}[second]
            store_path.write_text(json.dumps(records), encoding="utf-8")
        before = store_path.read_bytes()
        state_path.unlink()
        cycle[0] = 1
        session.run_assisted_application_session(allow_loopback_http_for_tests=True, limit=1, poll_interval_sec=0.01)
        assert store_path.read_bytes() == before
        if second == "matched":
            assert human_calls == [0] and filled == [0, 1], holder.get("failure")
            state_path.unlink()
            cycle[0] = 2
            session.run_assisted_application_session(allow_loopback_http_for_tests=True, limit=1, poll_interval_sec=0.01)
            assert human_calls == [0, 2] and filled == [0, 1]
        else:
            assert human_calls == [0, 1] and filled == [0]
        assert not list((tmp_path / "runtime").iterdir())
        for sentinel in (profile["email"], profile["last_name"]):
            assert sentinel not in caplog.text
            for path in (store_path, state_path):
                for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
                    assert sentinel.encode(encoding) not in path.read_bytes()
