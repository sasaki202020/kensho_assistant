from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
FIXTURES = ROOT / "tests" / "extension_fixtures"


def test_manifest_v3_uses_minimum_permissions() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) == {"activeTab", "scripting", "storage"}
    assert "host_permissions" not in manifest
    assert set(manifest["optional_host_permissions"]) == {
        "http://*/*",
        "https://*/*",
    }
    assert "<all_urls>" not in json.dumps(manifest)
    assert manifest["background"]["service_worker"] == "service-worker.js"


def test_overlay_exposes_stable_codex_actions_and_origin_permission_controls() -> None:
    overlay = (EXTENSION / "content" / "overlay.js").read_text(encoding="utf-8")

    assert '"data-kensho-extension-root", "true"' in overlay
    assert 'data-kensho-action="analyze"' in overlay
    assert 'aria-label="懸賞フォームを解析"' in overlay
    assert 'data-kensho-action="preview"' in overlay
    assert 'data-kensho-action="fill"' in overlay
    assert 'data-kensho-action="rollback"' in overlay
    assert 'data-kensho-action="open-profile"' in overlay
    assert 'data-kensho-action="enable-origin"' in overlay
    assert 'data-kensho-action="disable-origin"' in overlay
    assert 'data-kensho-extension-ready' in overlay
    assert 'data-kensho-status' in overlay


def test_different_extension_instance_blocks_all_fill_controls_without_profile_request(
    browser_page,
) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    _load_scripts(browser_page, "content/submit-guard.js")
    browser_page.evaluate(
        """() => {
          const oldHost = document.createElement("div");
          oldHost.id = "kensho-assistant-overlay-host";
          oldHost.setAttribute("data-kensho-extension-root", "true");
          oldHost.setAttribute("data-kensho-extension-id", "old-extension-id");
          oldHost.setAttribute("data-kensho-extension-version", "0.1.0");
          const shadow = oldHost.attachShadow({mode: "open"});
          shadow.innerHTML = `
            <button id="analyze" data-kensho-action="analyze">解析</button>
            <button id="fill" data-kensho-action="fill">入力</button>`;
          document.documentElement.appendChild(oldHost);
          window.profileRequestCount = 0;
          window.duplicateMessages = [];
          window.chrome = {
            runtime: {
              id: "new-extension-id",
              getManifest() { return {version: "0.2.0"}; },
              sendMessage(message, callback) {
                if ([
                  "GET_PROFILE_PREVIEW",
                  "CONSUME_SESSION_PROFILE",
                  "CONSUME_BRIDGE_PROFILE",
                  "REQUEST_BRIDGE_CAPABILITY"
                ].includes(message.type)) {
                  window.profileRequestCount += 1;
                }
                window.duplicateMessages.push(message.type);
                callback({ok: true, duplicate: true});
              }
            }
          };
        }"""
    )

    _load_scripts(browser_page, "content/overlay.js")

    result = browser_page.evaluate(
        """() => {
          const host = document.querySelector('[data-kensho-extension-root="true"]');
          return {
            duplicate: document.documentElement.getAttribute(
              "data-kensho-duplicate-extension"
            ),
            hostDuplicate: host.getAttribute("data-kensho-duplicate-extension"),
            analyzeDisabled: host.shadowRoot.querySelector("#analyze").disabled,
            fillDisabled: host.shadowRoot.querySelector("#fill").disabled,
            profileRequestCount: window.profileRequestCount,
            duplicateMessages: window.duplicateMessages,
            guard: window.__KENSHO_SUBMIT_GUARD__.state()
          };
        }"""
    )

    assert result["duplicate"] == "true"
    assert result["hostDuplicate"] == "true"
    assert result["analyzeDisabled"] is True
    assert result["fillDisabled"] is True
    assert result["profileRequestCount"] == 0
    assert "DUPLICATE_EXTENSION_BLOCKED" in result["duplicateMessages"]
    assert result["guard"]["locked"] is True


def test_options_page_can_reload_the_unpacked_extension() -> None:
    html = (EXTENSION / "options" / "options.html").read_text(encoding="utf-8")
    script = (EXTENSION / "options" / "options.js").read_text(encoding="utf-8")

    assert 'id="reload-extension"' in html
    assert "chrome.runtime.reload()" in script


def test_extension_can_be_loaded_as_unpacked_manifest_v3(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(tmp_path / "profile"),
            channel="chromium",
            headless=True,
            args=[
                f"--disable-extensions-except={EXTENSION}",
                f"--load-extension={EXTENSION}",
            ],
        )
        try:
            if not context.service_workers:
                context.new_page().wait_for_timeout(1000)
            assert len(context.service_workers) == 1
            worker = context.service_workers[0]
            assert worker.url.startswith("chrome-extension://")
            assert worker.url.endswith("/service-worker.js")
            extension_id = worker.url.split("/")[2]
            options = context.new_page()
            options.goto(f"chrome-extension://{extension_id}/options/options.html")
            options.locator('input[name="email"]').fill("pii-test@example.invalid")
            options.locator('button[type="submit"]').click()
            stored = worker.evaluate(
                """async () => (await chrome.storage.session.get(
                  "kenshoSessionProfile"
                )).kenshoSessionProfile"""
            )
            assert stored == {"email": "pii-test@example.invalid"}
            options.locator("#clear").click()
            cleared = worker.evaluate(
                """async () => (await chrome.storage.session.get(
                  "kenshoSessionProfile"
                )).kenshoSessionProfile || null"""
            )
            assert cleared is None
            activated_tab_id = worker.evaluate(
                """async () => {
                  const tabs = await chrome.tabs.query({active: true});
                  const tab = tabs[0];
                  await chrome.storage.session.set({
                    kenshoSessionProfile: {email: "pii-test@example.invalid"},
                    kenshoActiveTabs: [tab.id]
                  });
                  return tab.id;
                }""",
            )
            assert isinstance(activated_tab_id, int)
            options.close()
            context.new_page().wait_for_timeout(300)
            removed = worker.evaluate(
                """async () => (await chrome.storage.session.get(
                  "kenshoSessionProfile"
                )).kenshoSessionProfile || null"""
            )
            assert removed is None
        finally:
            context.close()


def _load_scripts(page, *relative_paths: str) -> None:
    for relative_path in relative_paths:
        page.add_script_tag(path=EXTENSION / relative_path)


@pytest.fixture()
def browser_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_standard_form_analysis_fill_rollback_and_consent_safety(browser_page) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/field-types.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )
    profile = {
        "last_name": "PII_TEST_LAST",
        "first_name": "PII_TEST_FIRST",
        "email": "pii-test@example.invalid",
        "phone": "09000000000",
        "postal_code": "0000000",
        "prefecture": "福岡県",
        "city": "北九州市",
        "street": "TEST-1",
        "building": "TEST-BUILDING",
        "free_text": "テスト用コメント",
    }

    result = browser_page.evaluate(
        """profile => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.preview(analysis, profile);
          const filled = window.KenshoExtension.FormFiller.fill(preview, profile);
          return {analysis, preview, filled};
        }""",
        profile,
    )

    assert result["analysis"]["captchaDetected"] is False
    assert result["analysis"]["loginRequired"] is False
    assert result["filled"]["filledCount"] >= 9
    assert result["analysis"]["unresolvedRequiredCount"] == 1
    assert any(
        warning["reason"] == "未分類の必須項目"
        for warning in result["preview"]["warnings"]
    )
    assert browser_page.locator("#terms").is_checked() is False
    assert "pii-test@example.invalid" not in json.dumps(result["preview"], ensure_ascii=False)

    browser_page.evaluate("window.KenshoExtension.FormFiller.rollback()")
    assert browser_page.locator('input[name="email"]').input_value() == ""
    assert browser_page.locator("#terms").is_checked() is False


def test_combined_japanese_fields_fill_without_prize_comment_or_submit(browser_page) -> None:
    browser_page.goto((FIXTURES / "combined_japanese_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
        "content/submit-guard.js",
    )
    profile = {
        "last_name": "山田",
        "first_name": "太郎",
        "last_name_kana": "ヤマダ",
        "first_name_kana": "タロウ",
        "postal_code": "0002741",
        "prefecture": "栃木県",
        "city": "テスト市",
        "street": "1-2-3",
        "building": "テストビル",
        "birth_date": "1990-04-01",
        "gender": "男性",
        "phone": "09000002741",
        "email": "pii-test@example.invalid",
    }

    result = browser_page.evaluate(
        """profile => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.preview(analysis, profile);
          const filled = window.KenshoExtension.FormFiller.fill(preview, profile);
          return {
            analysis: {
              fields: analysis.fields.map(field => ({
                fieldType: field.fieldType,
                confidence: field.confidence
              })),
              captchaDetected: analysis.captchaDetected
            },
            filled
          };
        }""",
        profile,
    )

    detected = {field["fieldType"] for field in result["analysis"]["fields"]}
    assert {
        "full_name",
        "full_name_kana",
        "postal_code",
        "prefecture",
        "city",
        "street",
        "building",
        "gender",
        "age",
        "phone",
        "email",
    } <= detected
    assert result["analysis"]["captchaDetected"] is True
    assert result["filled"]["filledCount"] >= 11
    assert browser_page.locator("#name").input_value() == "山田 太郎"
    assert browser_page.locator("#kana").input_value() == "ヤマダ タロウ"
    assert browser_page.locator("#age").input_value().isdigit()
    assert browser_page.get_by_label("男性").is_checked() is True
    assert browser_page.get_by_label("商品A").is_checked() is False
    assert browser_page.get_by_label("商品B").is_checked() is False
    assert browser_page.locator('textarea[name="applicant[comment]"]').input_value() == ""
    assert browser_page.url.endswith("combined_japanese_form.html")


def test_captcha_and_login_stop_before_fill(browser_page) -> None:
    browser_page.goto((FIXTURES / "security_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/field-types.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    analysis = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )

    assert analysis["captchaDetected"] is True
    assert analysis["loginRequired"] is True


def test_open_shadow_iframe_and_redraw_are_reanalyzed(browser_page) -> None:
    browser_page.goto((FIXTURES / "complex_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/field-types.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    before = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )
    browser_page.evaluate("window.redraw()")
    after = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )

    before_types = {field["fieldType"] for field in before["fields"]}
    after_types = {field["fieldType"] for field in after["fields"]}
    assert {"last_name", "email", "phone"} <= before_types
    assert {"last_name", "email", "phone"} <= after_types


def test_submit_guard_blocks_all_submission_paths(browser_page) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    _load_scripts(browser_page, "content/submit-guard.js")

    browser_page.locator('input[name="last_name"]').press("Enter")
    browser_page.evaluate("document.querySelector('#entry-form').submit()")
    browser_page.evaluate("document.querySelector('#entry-form').requestSubmit()")
    browser_page.locator("#submit-button").click()
    browser_page.evaluate("document.querySelector('#submit-button').click()")

    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")
    assert state["locked"] is True
    assert state["blockedAttempts"] >= 5
    assert browser_page.url.endswith("standard_form.html")


def test_submit_guard_blocks_same_origin_iframe(browser_page) -> None:
    browser_page.goto((FIXTURES / "complex_form.html").as_uri())
    frame = browser_page.frame_locator("#same-origin-frame")
    frame.locator("body").evaluate(
        """body => {
          const form = document.createElement("form");
          form.id = "frame-form";
          form.innerHTML = '<input name="email"><button type="submit">送信</button>';
          body.appendChild(form);
        }"""
    )
    iframe = next(
        child for child in browser_page.frames if child != browser_page.main_frame
    )
    iframe.add_script_tag(path=EXTENSION / "content/submit-guard.js")
    frame.locator('#frame-form input[name="email"]').press("Enter")
    frame.locator("#frame-form").evaluate("form => form.submit()")
    frame.locator("#frame-form").evaluate("form => form.requestSubmit()")

    state = frame.locator("body").evaluate(
        "body => body.ownerDocument.defaultView.__KENSHO_SUBMIT_GUARD__.state()"
    )
    assert state["blockedAttempts"] >= 3
    assert state["submitted_count_auto"] == 0


def test_isolated_world_guard_blocks_dom_submission_events(browser_page) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    _load_scripts(browser_page, "content/isolated-guard.js")

    browser_page.locator('input[name="last_name"]').press("Enter")
    browser_page.locator("#submit-button").click()
    state = browser_page.evaluate(
        "window.__KENSHO_ISOLATED_GUARD__.state()"
    )

    assert state["blockedAttempts"] >= 2
    assert state["submitted_count_auto"] == 0
    assert browser_page.url.endswith("standard_form.html")


def test_submit_guard_blocks_open_and_new_closed_shadow_forms(browser_page) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    _load_scripts(browser_page, "content/submit-guard.js")

    result = browser_page.evaluate(
        """() => {
          const openHost = document.createElement("div");
          document.body.appendChild(openHost);
          const openRoot = openHost.attachShadow({mode: "open"});
          openRoot.innerHTML = '<form><input><button type="submit">送信</button></form>';
          openRoot.querySelector("button").click();

          const closedHost = document.createElement("div");
          document.body.appendChild(closedHost);
          const closedRoot = closedHost.attachShadow({mode: "closed"});
          closedRoot.innerHTML = '<form><input><button type="submit">送信</button></form>';
          closedRoot.querySelector("button").click();
          return window.__KENSHO_SUBMIT_GUARD__.state();
        }"""
    )

    assert result["blockedAttempts"] >= 2
    assert result["submitted_count_auto"] == 0


def test_late_guard_is_not_trusted_when_page_saved_native_submit(browser_page) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    browser_page.evaluate(
        "() => { window.savedNativeSubmit = HTMLFormElement.prototype.submit; }"
    )
    _load_scripts(browser_page, "content/submit-guard.js")

    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")

    assert state["installedAtDocumentStart"] is False
    assert state["integrity"] is True


def test_submit_guard_blocks_prototype_replacement_without_losing_integrity(browser_page) -> None:
    browser_page.add_init_script(path=EXTENSION / "content/submit-guard.js")
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())

    browser_page.evaluate(
        "HTMLFormElement.prototype.submit = function compromisedSubmit() {}"
    )
    browser_page.wait_for_timeout(300)
    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")

    descriptor = browser_page.evaluate(
        """() => {
          const value = Object.getOwnPropertyDescriptor(
            HTMLFormElement.prototype,
            "submit"
          );
          return {
            configurable: value.configurable,
            hasSetter: typeof value.set === "function",
            guardedName: HTMLFormElement.prototype.submit.name,
          };
        }"""
    )

    assert state["integrity"] is True
    assert state["blockedAttempts"] == 0
    assert state["guardWriteBlockedAttempts"] == 1
    assert "guard_write_blocked:submit" in state["guardWriteReasons"]
    assert descriptor == {
        "configurable": False,
        "hasSetter": True,
        "guardedName": "guardedSubmit",
    }


def test_submit_guard_blocks_delayed_dynamic_and_prototype_call(browser_page) -> None:
    browser_page.add_init_script(path=EXTENSION / "content/submit-guard.js")
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())

    browser_page.evaluate(
        """() => {
          const form = document.createElement("form");
          form.id = "dynamic-form";
          form.innerHTML = '<input><button type="submit">送信</button>';
          document.body.appendChild(form);
          setTimeout(() => form.requestSubmit(), 50);
          HTMLFormElement.prototype.submit.call(form);
          form.querySelector("button").dispatchEvent(
            new MouseEvent("click", {bubbles: true, composed: true})
          );
        }"""
    )
    browser_page.wait_for_timeout(150)
    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")

    assert state["blockedAttempts"] >= 3
    assert state["submitted_count_auto"] == 0
    assert browser_page.url.endswith("standard_form.html")


def test_submit_guard_survives_spa_navigation(browser_page) -> None:
    browser_page.add_init_script(path=EXTENSION / "content/submit-guard.js")
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())

    browser_page.evaluate(
        """() => {
          history.pushState({}, "", "#confirmation");
          document.body.innerHTML =
            '<form id="spa-form"><input><button type="submit">確定</button></form>';
          document.querySelector("#spa-form").requestSubmit();
        }"""
    )
    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")

    assert state["blockedAttempts"] >= 1
    assert state["integrity"] is True
    assert browser_page.url.endswith("standard_form.html#confirmation")


def test_confirmation_screen_remains_locked(browser_page) -> None:
    browser_page.goto((FIXTURES / "confirmation_form.html").as_uri())
    _load_scripts(browser_page, "content/submit-guard.js")

    browser_page.locator("#confirm-button").click()

    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")
    assert state["blockedAttempts"] >= 1
    assert browser_page.url.endswith("confirmation_form.html")


def test_overlay_preview_fill_and_session_clear(browser_page) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    browser_page.evaluate(
        """() => {
          let sessionProfile = {
            last_name: "PII_TEST_LAST",
            first_name: "PII_TEST_FIRST",
            email: "pii-test@example.invalid"
          };
          window.chrome = {
            runtime: {
                  sendMessage(message, callback) {
                    if (message.type === "GET_SESSION_STATUS") {
                      callback({ok: true, profileLoaded: true, workerEpoch: "worker-1"});
                    } else if (message.type === "GET_PROFILE_PREVIEW") {
                      callback({
                        ok: true,
                        profile: {
                          last_name: "P***",
                          first_name: "P***",
                          email: "p***@example.invalid"
                        },
                        workerEpoch: "worker-1"
                      });
                    } else if (message.type === "CONSUME_SESSION_PROFILE") {
                      const profile = sessionProfile;
                      sessionProfile = null;
                      callback({ok: true, profile, workerEpoch: "worker-1"});
                    } else if (message.type === "CLEAR_SESSION_PROFILE") {
                      sessionProfile = null;
                      callback({ok: true});
                } else {
                  callback({ok: false});
                }
              }
                }
              };
              document.addEventListener("kensho-guard-status-request", () => {
                document.dispatchEvent(new CustomEvent("kensho-guard-status", {
                  detail: {integrity: true, installedAtDocumentStart: true}
                }));
              });
            }"""
    )
    _load_scripts(
        browser_page,
        "shared/field-types.js",
        "shared/redaction.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
        "content/overlay.js",
    )
    panel = browser_page.locator("#kensho-assistant-overlay-host")
    panel.locator("#analyze").click()
    panel.locator("#preview-button").click()
    mapping_buttons = panel.locator('button[data-kensho-mapping-action="approve"]')
    for _ in range(mapping_buttons.count()):
        panel.locator('button[data-kensho-mapping-action="approve"]').first.click()
    panel_text = panel.evaluate("host => host.shadowRoot.textContent")
    assert "pii-test@example.invalid" not in panel_text
    assert "p***@example.invalid" in panel_text
    panel.locator("#fill").click()
    assert browser_page.locator('input[name="email"]').input_value() == "pii-test@example.invalid"
    panel.locator("#clear").click()
    assert browser_page.locator('input[name="email"]').input_value() == ""
    panel_text = panel.evaluate("host => host.shadowRoot.textContent")
    assert "セッション情報消去済み" in panel_text


def test_overlay_buttons_work_while_submit_guard_is_active(browser_page) -> None:
    browser_page.add_init_script(path=EXTENSION / "content/submit-guard.js")
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    browser_page.evaluate(
        """() => {
          window.chrome = {
            runtime: {
                  sendMessage(message, callback) {
                    if (message.type === "GET_SESSION_STATUS") {
                      callback({ok: true, profileLoaded: true, workerEpoch: "worker-1"});
                    } else {
                      callback({ok: true, profile: {}, workerEpoch: "worker-1"});
                    }
              }
            }
          };
        }"""
    )
    _load_scripts(
        browser_page,
        "content/submit-guard.js",
        "shared/field-types.js",
        "shared/redaction.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
        "content/overlay.js",
    )
    panel = browser_page.locator("#kensho-assistant-overlay-host")
    panel.locator("#analyze").click()

    panel_text = panel.evaluate("host => host.shadowRoot.textContent")
    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")
    assert "解析済み" in panel_text
    assert state["blockedAttempts"] == 0


def test_guard_write_attempt_is_not_reported_as_auto_submit(browser_page) -> None:
    browser_page.add_init_script(path=EXTENSION / "content/submit-guard.js")
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    browser_page.evaluate(
        """() => {
          window.chrome = {
            runtime: {
              sendMessage(message, callback) {
                if (message.type === "GET_SESSION_STATUS") {
                  callback({ok: true, profileLoaded: true, workerEpoch: "worker-1"});
                } else {
                  callback({ok: true, profile: {}, workerEpoch: "worker-1"});
                }
              }
            }
          };
        }"""
    )
    _load_scripts(
        browser_page,
        "shared/field-types.js",
        "shared/redaction.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
        "content/overlay.js",
    )

    browser_page.evaluate(
        "HTMLFormElement.prototype.submit = function siteSubmitWrapper() {}"
    )
    browser_page.wait_for_timeout(300)

    panel = browser_page.locator("#kensho-assistant-overlay-host")
    status_text = panel.evaluate("host => host.shadowRoot.querySelector('#status').textContent")
    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")
    assert "自動送信を遮断" not in status_text
    assert state["integrity"] is True
    assert state["blockedAttempts"] == 0
    assert state["guardWriteBlockedAttempts"] == 1


def test_captcha_stops_before_any_profile_fill(
    browser_page,
) -> None:
    browser_page.add_init_script(path=EXTENSION / "content/submit-guard.js")
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    browser_page.evaluate(
        """() => {
          const captcha = document.createElement("div");
          captcha.className = "g-recaptcha";
          captcha.textContent = "私はロボットではありません";
          document.querySelector("#entry-form").appendChild(captcha);
          let sessionProfile = {
            last_name: "PII_TEST_LAST",
            first_name: "PII_TEST_FIRST",
            email: "pii-test@example.invalid"
          };
          window.chrome = {
            runtime: {
              sendMessage(message, callback) {
                if (message.type === "GET_SESSION_STATUS") {
                  callback({ok: true, profileLoaded: true, workerEpoch: "worker-1"});
                } else if (message.type === "GET_PROFILE_PREVIEW") {
                  callback({
                    ok: true,
                    profile: {
                      last_name: "P***",
                      first_name: "P***",
                      email: "p***@example.invalid"
                    },
                    workerEpoch: "worker-1"
                  });
                } else if (message.type === "CONSUME_SESSION_PROFILE") {
                  const profile = sessionProfile;
                  sessionProfile = null;
                  callback({ok: true, profile, workerEpoch: "worker-1"});
                } else {
                  callback({ok: true});
                }
              }
            }
          };
        }"""
    )
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
        "content/overlay.js",
    )

    panel = browser_page.locator("#kensho-assistant-overlay-host")
    panel.locator("#analyze").click()
    assert "CAPTCHA検出・本人確認が必要" in panel.evaluate(
        "host => host.shadowRoot.querySelector('#status').textContent"
    )

    panel.locator("#preview-button").click()
    browser_page.wait_for_function(
        """() => document.querySelector("#kensho-assistant-overlay-host")
          ?.shadowRoot?.querySelector("#status")
          ?.textContent?.includes("CAPTCHA検出")"""
    )

    assert (
        browser_page.locator('input[name="email"]').input_value()
        == ""
    )
    assert browser_page.locator("#terms").is_checked() is False
    assert "CAPTCHA検出" in panel.evaluate(
        "host => host.shadowRoot.querySelector('#status').textContent"
    )
    state = browser_page.evaluate("window.__KENSHO_SUBMIT_GUARD__.state()")
    assert state["locked"] is True
    assert state["submitted_count_auto"] == 0


def test_extension_sources_do_not_persist_or_log_pii() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in EXTENSION.rglob("*")
        if path.is_file() and path.suffix in {".js", ".html", ".json"}
    )

    assert "chrome.storage.local" in source
    assert "kenshoFormTemplate:" in source
    assert "chrome.storage.sync" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "indexedDB" not in source
    assert "console.log" not in source
    assert "TRUSTED_AND_UNTRUSTED_CONTEXTS" not in source
    assert '"TRUSTED_CONTEXTS"' in source
    assert "submitted_count_auto" in source


def test_content_scripts_cannot_call_the_loopback_bridge_directly() -> None:
    content_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (EXTENSION / "content").glob("*.js")
    )

    assert "127.0.0.1" not in content_source
    assert "fetch(" not in content_source


def test_sensitive_honeypot_and_consent_fields_are_manual_review_only(
    browser_page,
) -> None:
    browser_page.goto((FIXTURES / "safety_fields.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    analysis = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )

    reasons = {item["reason"] for item in analysis["manualReviewFields"]}
    assert {
        "hidden_or_honeypot",
        "file_upload",
        "login_or_password",
        "disabled_or_readonly",
        "sensitive_or_consent",
    } <= reasons
    assert all(
        field["fillAllowed"] is False
        for field in analysis["fields"]
        if field["fieldType"] == "free_text"
    )


def test_japanese_split_form_uses_previewed_normalization(browser_page) -> None:
    browser_page.goto((FIXTURES / "japanese_split_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )
    profile = {
        "last_name_kana": "やまだ",
        "first_name_kana": "ハナコ",
        "phone": "０９０-１２３４-５６７８",
        "postal_code": "０００-２７４１",
        "birth_date": "1990-04-01",
    }
    masked = {
        key: "設定済み"
        for key in profile
    }

    result = browser_page.evaluate(
        """({profile, masked}) => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.previewMasked(
            analysis, masked
          );
          const filled = window.KenshoExtension.FormFiller.fill(preview, profile);
          return {analysis, preview, filled};
        }""",
        {"profile": profile, "masked": masked},
    )

    assert result["filled"]["filledCount"] == 10
    assert browser_page.locator('input[name="last_name_kana"]').input_value() == "ヤマダ"
    assert browser_page.locator('input[name="first_name_kana"]').input_value() == "はなこ"
    assert [
        browser_page.locator(f'input[name="phone{index}"]').input_value()
        for index in range(1, 4)
    ] == ["090", "1234", "5678"]
    assert [
        browser_page.locator(f'input[name="zip{index}"]').input_value()
        for index in range(1, 3)
    ] == ["000", "2741"]


def test_opaque_iframe_is_fail_closed_without_external_network(browser_page) -> None:
    browser_page.goto((FIXTURES / "opaque_iframe_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    analysis = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )

    assert analysis["unsupportedIframes"] == 1


def test_hidden_tracking_iframe_outside_form_does_not_block_analysis(browser_page) -> None:
    browser_page.goto((FIXTURES / "hidden_tracking_iframe_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    analysis = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )

    assert analysis["unsupportedIframes"] == 0
    assert analysis["ignoredHiddenTrackingIframes"] == 1
    assert analysis["detectedFieldCount"] == 1


@pytest.mark.parametrize("title", ["", "external application form"])
def test_hidden_opaque_iframe_without_tracking_evidence_remains_blocked(
    browser_page, title: str
) -> None:
    browser_page.goto((FIXTURES / "opaque_iframe_form.html").as_uri())
    browser_page.locator("iframe").evaluate(
        "(frame, title) => { frame.hidden = true; frame.title = title; }", title
    )
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    analysis = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )

    assert analysis["unsupportedIframes"] == 1
    assert analysis["ignoredHiddenTrackingIframes"] == 0


def test_hidden_tracking_iframe_becoming_visible_is_blocked_on_recheck(browser_page) -> None:
    browser_page.goto((FIXTURES / "hidden_tracking_iframe_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "shared/redaction.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )
    initial = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )
    browser_page.locator("#tracking-frame").evaluate(
        "frame => { frame.hidden = false; frame.style.display = 'block'; }"
    )
    result = browser_page.evaluate(
        """async analysis => {
          const profile = {email: "fixture@example.invalid"};
          const preview = window.KenshoExtension.FormFiller.previewMasked(
            analysis, {email: "f***@example.invalid"}
          );
          return window.KenshoExtension.FormFiller.fillAndVerify(
            preview, profile, analysis, {templateApproved: true}
          );
        }""",
        initial,
    )

    assert initial["unsupportedIframes"] == 0
    assert result["status"] == "SAFE_STOP_HUMAN_REVIEW_REQUIRED"
    assert result["filledCount"] == 0
    assert browser_page.locator('input[name="email"]').input_value() == ""


def test_worker_epoch_change_stops_old_analysis_before_profile_delivery(
    browser_page,
) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    browser_page.evaluate(
        """() => {
          window.chrome = {
            runtime: {
              sendMessage(message, callback) {
                if (message.type === "GET_SESSION_STATUS") {
                  callback({ok: true, profileLoaded: true, workerEpoch: "worker-1"});
                } else if (message.type === "GET_PROFILE_PREVIEW") {
                  callback({
                    ok: true,
                    profile: {email: "p***@example.invalid"},
                    workerEpoch: "worker-2"
                  });
                } else {
                  callback({ok: false});
                }
              }
            }
          };
          document.addEventListener("kensho-guard-status-request", () => {
            document.dispatchEvent(new CustomEvent("kensho-guard-status", {
              detail: {integrity: true, installedAtDocumentStart: true}
            }));
          });
        }"""
    )
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
        "content/overlay.js",
    )
    panel = browser_page.locator("#kensho-assistant-overlay-host")
    panel.locator("#analyze").click()
    panel.locator("#preview-button").click()

    panel_text = panel.evaluate("host => host.shadowRoot.textContent")
    assert "プロフィールの再読込が必要" in panel_text
    assert browser_page.locator('input[name="email"]').input_value() == ""


def test_react_and_vue_controlled_inputs_are_detected_but_require_revalidation(
    browser_page,
) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    browser_page.evaluate(
        """() => {
          document.querySelector('input[name="email"]')._valueTracker = {};
          document.querySelector('input[name="phone"]').__vue__ = {};
        }"""
    )
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    analysis = browser_page.evaluate(
        "window.KenshoExtension.FormDetector.scan(document)"
    )

    email = next(field for field in analysis["fields"] if field["fieldType"] == "email")
    phone = next(field for field in analysis["fields"] if field["fieldType"] == "phone")
    assert email["frameworkControlled"] is True
    assert phone["frameworkControlled"] is True
    assert "framework_revalidation_required" in email["warnings"]
    assert "framework_revalidation_required" in phone["warnings"]
    assert browser_page.locator('input[name="email"]').input_value() == ""
    assert browser_page.locator('input[name="phone"]').input_value() == ""


def test_extension_overlay_shadow_dom_is_excluded_from_form_fingerprint(browser_page) -> None:
    browser_page.goto((FIXTURES / "standard_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/field-types.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )

    result = browser_page.evaluate(
        """() => {
          const before = window.KenshoExtension.FormDetector.scan(document);
          const host = document.createElement("div");
          host.setAttribute("data-kensho-extension-root", "true");
          const shadow = host.attachShadow({mode: "open"});
          shadow.innerHTML = '<select><option>欄対応</option></select>';
          document.body.appendChild(host);
          const after = window.KenshoExtension.FormDetector.scan(document);
          return {
            before: before.formFingerprint,
            after: after.formFingerprint,
            fieldCount: after.detectedFieldCount,
          };
        }"""
    )

    assert result["before"] == result["after"]
    assert result["fieldCount"] > 0
