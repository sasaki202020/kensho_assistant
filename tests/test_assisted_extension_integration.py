"""Real local API/worker/bridge round trip, without real candidates or profiles."""
from __future__ import annotations

import importlib
import json
import socket
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import uvicorn
import pytest

from kensho_assistant.app import assisted_session as session
from kensho_assistant.app.extension_bridge import CapabilityBridge
from kensho_assistant.app.browser_manager import launch_dedicated_kensho_context, close_browser_safely
from kensho_assistant.scripts.build_dedicated_extension import build_dedicated_extension
from kensho_assistant.scripts.run_extension_local_smoke import (
    _approve_all_visible_mappings,
    _build_smoke_extension,
    _fixture_server,
    _wait_for_worker,
)


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


@pytest.mark.parametrize("mutation", [None, "form_changed", "template_unconfirmed", "version_changed", "duplicate_tab", "document_changed", "after_provision_reload"])
def test_real_assisted_mapping_bridge_fill_rollback(tmp_path, monkeypatch, caplog, mutation):
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
        }
        monkeypatch.setattr(session, "approved_queue_rows", lambda rows=None: [candidate])
        monkeypatch.setattr(session, "load_apply_queue", lambda: [candidate])
        monkeypatch.setattr(session, "target_url_for_campaign", lambda row: row["resolved_entry_url"])
        def local_only(url):
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
            )
            def record(request):
                parsed = urlsplit(request.url)
                # Never retain request bodies, query strings or input values.
                requests.append((parsed.hostname, parsed.path, request.method))
            context.on("request", record)
            context.route("**/*", lambda route: route.continue_() if urlsplit(route.request.url).hostname == "127.0.0.1" else route.abort())
            try:
                worker = _wait_for_worker(context)
                deadline = time.monotonic() + 10
                while worker.evaluate("async () => chrome.scripting ? (await chrome.scripting.getRegisteredContentScripts()).length : 0") != 2:
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
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
            host = page.locator("#kensho-assistant-overlay-host")
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
                host.locator("#fill").click()
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('入力済み')", timeout=7000)
                state = session.load_assisted_session_state()
                assert state["workflow_state"] == "HUMAN_ACTION_REQUIRED"
                for key, value in profile.items():
                    assert page.locator(f'[name="{key}"]').input_value() == value
                assert state["submitted_count_auto"] == 0
                assert not page.locator("#terms").is_checked()
                observed["post_fill"] = True
                host.locator("#rollback").click()
                page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.shadowRoot.querySelector('#status').textContent.includes('元に戻しました')")
                assert page.locator("#entry-form").evaluate("f => Array.from(f.elements, e => [e.value, e.checked, e.selectedIndex])") == observed["before"]
                observed["rollback"] = True
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
                errors.append(type(error).__name__)
                observed["stop_reason"] = host.locator("#status").text_content()
                raise
            return {}, "stop", {}
        monkeypatch.setattr(session, "_wait_for_extension_verified_result", human_fill_and_rollback)

        result = session.run_assisted_application_session(limit=1, keep_open=False, poll_interval_sec=0.01)

    if mutation:
        assert not observed["post_fill"]
        assert not profile_loads and not consumed
        assert session.load_assisted_session_state()["workflow_state"] == "FAILED_SAFE"
        assert not any(path == "/api/session/extension-capability" for path, _method, _code in api_requests)
        assert result["submitted_count_auto"] == 0
        assert not list((tmp_path / "runtime").iterdir())
        return
    assert observed["post_fill"], (observed.get("stop_reason"), errors, result["message"])
    assert observed["rollback"] and observed["clear"]
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
