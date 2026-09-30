"""Real fixed-build Chromium; loopback fixtures and metadata only."""
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
import pytest

from kensho_assistant.app.browser_manager import launch_dedicated_kensho_context

from kensho_assistant.app.browser_manager import close_browser_safely, _runtime_origin_worker
from kensho_assistant.scripts.build_dedicated_extension import build_dedicated_extension
from kensho_assistant.scripts.run_extension_local_smoke import _fixture_server

NO_INTERNET = "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"


@pytest.mark.parametrize('different_host', [True, False])
def test_runtime_origin_switch_clear_and_message_isolation(tmp_path, different_host):
    shutil.copytree(Path(__file__).parents[1] / 'extension', tmp_path / 'extension')
    build_dedicated_extension(source_dir=tmp_path / 'extension', output_dir=tmp_path / 'build' / 'extension')
    with _fixture_server() as a, _fixture_server() as second, sync_playwright() as playwright:
        b = a.replace('127.0.0.1', 'localhost') if different_host else second
        context, _, _ = launch_dedicated_kensho_context(playwright,
            run_id='origin-fixture', project_root=tmp_path, runtime_profiles_root=tmp_path / 'runtime',
            headless=True, extra_args=(NO_INTERNET,))
        context.route('**/*', lambda r: r.continue_() if urlsplit(r.request.url).hostname in {'127.0.0.1', 'localhost'} else r.abort())
        try:
            worker = _runtime_origin_worker(context)
            page_a, page_b = context.pages[0], context.new_page()
            path = '/extension_fixtures/standard_form.html'
            def registrations():
                return worker.evaluate('async () => { await scheduleReconciliation(); return chrome.scripting.getRegisteredContentScripts(); }')
            def absent(page, origin):
                page.goto(origin + path, wait_until='load')
                assert page.locator('[data-kensho-extension-root]').count() == 0
                assert page.evaluate("() => document.documentElement.dataset.kenshoSubmitGuard || ''") == ''
            def present(page, origin):
                page.goto(origin + path, wait_until='load')
                page.wait_for_selector('[data-kensho-extension-root]', timeout=5000)
                assert page.evaluate("() => document.documentElement.dataset.kenshoSubmitGuard") == 'true'
            assert registrations() == []
            absent(page_a, a)
            absent(page_b, b)
            assert worker.evaluate('async p => setActiveOrigin(p, "fixture-session")', a + '/*') == {'originPattern': a + '/*', 'sessionId': 'fixture-session'}
            assert [s['matches'] for s in registrations()] == [[a + '/*'], [a + '/*']]
            assert all(s['persistAcrossSessions'] is False for s in registrations())
            present(page_a, a)
            absent(page_b, b)
            # A page cannot reach worker globals or change them through window messages.
            assert page_a.evaluate("() => typeof setActiveOrigin") == 'undefined'
            page_a.evaluate("p => window.postMessage({type:'SET_ACTIVE_ORIGIN', originPattern:p}, '*')", b + '/*')
            # Simulate actual content-script messages in its isolated world.
            async_messages = """async ({url, types, pattern}) => {
              const tab = (await chrome.tabs.query({})).find(t => t.url === url);
              const [result] = await chrome.scripting.executeScript({target:{tabId:tab.id}, world:'ISOLATED',
                func: async (types, pattern) => {
                  const results = [];
                  for (const type of types) results.push(await chrome.runtime.sendMessage({type, originPattern:pattern}));
                  return results;
                }, args:[types, pattern]});
              return result.result;
            }"""
            denied = worker.evaluate(async_messages, {'url': b + path, 'types': ['SET_ACTIVE_ORIGIN', 'GET_SESSION_STATUS', 'CONSUME_BRIDGE_PROFILE', 'GET_BRIDGE_CAPABILITY_STATUS', 'GET_FORM_TEMPLATE'], 'pattern': b + '/*'})
            assert all(r == {'ok': False, 'error': 'inactive_origin'} for r in denied)
            identity = worker.evaluate(async_messages, {'url': a + path, 'types': ['GET_EXTENSION_ID'], 'pattern': b + '/*'})
            assert identity[0]['ok'] is True
            assert worker.evaluate("""async url => {
              const tab = (await chrome.tabs.query({})).find(t => t.url === url);
              const [result] = await chrome.scripting.executeScript({target:{tabId:tab.id}, world:'ISOLATED',
                func: async () => {
                  try { await chrome.storage.session.get('kenshoActiveOrigin'); return true; }
                  catch (_) { return false; }
                }});
              return result.result;
            }""", a + path) is False
            attack = worker.evaluate(async_messages, {'url': a + path, 'types': ['SET_ACTIVE_ORIGIN', 'CLEAR_ACTIVE_ORIGIN', 'REQUEST_ORIGIN_ACCESS', 'DISABLE_ORIGIN_ACCESS'], 'pattern': b + '/*'})
            assert all(r['ok'] is False for r in attack)
            assert worker.evaluate('async () => getActiveOrigin()')['originPattern'] == a + '/*'
            worker.evaluate('async p => setActiveOrigin(p, "fixture-session")', b + '/*')
            assert [s['matches'] for s in registrations()] == [[b + '/*'], [b + '/*']]
            revoked = worker.evaluate(async_messages, {'url': a + path, 'types': ['CONSUME_BRIDGE_PROFILE', 'GET_FORM_TEMPLATE'], 'pattern': a + '/*'})
            assert all(r == {'ok': False, 'error': 'inactive_origin'} for r in revoked)
            absent(page_a, a)
            present(page_b, b)
            worker.evaluate("async () => { await chrome.storage.session.set({kenshoSessionProfile:{}, kenshoBridgeCapability:{}, kenshoControlCapability:{}, kenshoProgressCapability:{}}); await clearActiveOrigin(); }")
            assert registrations() == []
            assert worker.evaluate("async () => Object.keys(await chrome.storage.session.get(null)).filter(k => /Profile|Capability|ActiveOrigin/.test(k))") == []
            absent(page_a, a)
            absent(page_b, b)
        finally:
            close_browser_safely(context)
