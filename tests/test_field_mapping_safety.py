from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
FIXTURES = ROOT / "tests" / "extension_fixtures"


def _load_scripts(page, *relative_paths: str) -> None:
    for relative_path in relative_paths:
        page.add_script_tag(path=EXTENSION / relative_path)


@pytest.mark.parametrize("option_case", ["label", "disabled", "disabled_group", "duplicate", "reset", "repeat"])
def test_select_uses_unique_enabled_option_and_verifies_internal_value(browser_page, option_case) -> None:
    browser_page.set_content('''<form>
      <label for="pref">都道府県</label>
      <select id="pref" autocomplete="address-level1">
        <option value="">選択してください</option>
        <option value="13">東京都</option><option value="27">大阪府</option>
      </select><button type="submit">応募する</button></form>''')
    _load_scripts(browser_page, "shared/config.js", "shared/redaction.js",
                  "shared/normalization.js", "shared/form-fingerprint.js",
                  "content/field-matcher.js", "content/form-detector.js", "content/form-filler.js")
    result = browser_page.evaluate('''async optionCase => {
      const select = document.querySelector('#pref');
      if (optionCase === 'disabled') select.options[1].disabled = true;
      if (optionCase === 'disabled_group') {
        const group = document.createElement('optgroup'); group.disabled = true;
        select.append(group); group.append(select.options[1]);
      }
      if (optionCase === 'duplicate') select.add(new Option('東京都', 'other'));
      if (optionCase === 'reset') select.addEventListener('change', () => {select.value = '27';});
      let changes = 0;
      select.addEventListener('input', () => {changes++;});
      const api = window.KenshoExtension;
      const analysis = api.FormDetector.scan(document);
      const profile = {prefecture: '東京都'};
      const decisions = Object.fromEntries(analysis.fields.map(f =>
        [f.fieldId, {action: 'approve', profileKey: f.fieldType}]));
      const preview = api.FormFiller.previewMasked(analysis, {prefecture: '***'},
        {templateApproved: true, mappingDecisions: decisions});
      let filled = await api.FormFiller.fillAndVerify(preview, profile, analysis,
        {templateApproved: true, mappingDecisions: decisions});
      if (optionCase === 'repeat') {
        const first = await api.FormFiller.rollbackAndVerifyLast();
        if (!first.rollbackComplete) throw new Error('first_rollback_failed');
        filled = await api.FormFiller.fillAndVerify(preview, profile, analysis,
          {templateApproved: true, mappingDecisions: decisions});
      }
      const inputEvents = changes;
      const correctValue = select.value === '13';
      const rolled = await api.FormFiller.rollbackAndVerifyLast();
      return {filled, correctValue, inputEvents, rolled, restored: select.value === ''};
    }''', option_case)
    if option_case in {"label", "repeat"}:
        assert result["filled"]["status"] == "POST_FILL_VERIFICATION_PASSED"
        assert result["filled"]["filledCount"] == 1
        assert result["correctValue"] is True
    else:
        assert result["filled"]["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLBACK_REQUIRED"
        if option_case != "reset":
            assert result["inputEvents"] == 0
    assert result["rolled"]["rollbackComplete"] is True
    assert result["restored"] is True
    assert result["filled"]["submitted_count_auto"] == 0


@pytest.fixture()
def browser_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


def test_contest_comparison_fixture_preserves_manual_fields_and_never_submits(browser_page) -> None:
    """Exercise AutoContest-style hazards through our existing browser adapter."""
    requests = []
    browser_page.on("request", lambda request: requests.append(request.method))
    browser_page.set_content('''
      <form id="search"><input type="search" name="q"><button>Search</button></form>
      <form id="entry">
        <label>Email<input id="email" type="email" autocomplete="email"></label>
        <label>都道府県<select id="pref" autocomplete="address-level1">
          <option value="">Choose</option><option value="13">東京都</option>
          <option value="27">大阪府</option></select></label>
        <input type="hidden" name="nonce" value="fixture-nonce">
        <label>同意<input id="consent" type="checkbox"></label>
        <label>賞品<select id="prize"><option value="">Choose</option>
          <option value="prize">Prize</option></select></label>
        <label>応募理由<textarea id="reason"></textarea></label>
        <input id="unknown" name="unclassified">
        <button type="submit">Submit</button>
      </form>''')
    _load_scripts(browser_page, "content/submit-guard.js", "content/isolated-guard.js",
                  "shared/config.js", "shared/redaction.js", "shared/normalization.js",
                  "shared/form-fingerprint.js", "content/field-matcher.js",
                  "content/form-detector.js", "content/form-filler.js")
    result = browser_page.evaluate('''async () => {
      const api = window.KenshoExtension;
      const controls = Array.from(document.querySelectorAll('input,select,textarea'));
      const state = () => controls.map(e => [e.value, e.checked, e.selectedIndex]);
      const before = JSON.stringify(state());
      let submits = 0;
      document.addEventListener('submit', () => {submits++;});
      const analysis = api.FormDetector.scan(document);
      const decisions = Object.fromEntries(analysis.fields
        .filter(f => ['email', 'prefecture'].includes(f.fieldType))
        .map(f => [f.fieldId, {action: 'approve', profileKey: f.fieldType}]));
      const preview = api.FormFiller.previewMasked(analysis,
        {email: '***', prefecture: '***'}, {templateApproved: true, mappingDecisions: decisions});
      const filled = await api.FormFiller.fillAndVerify(preview,
        {email: 'comparison@example.invalid', prefecture: '東京都'}, analysis,
        {templateApproved: true, mappingDecisions: decisions});
      const manualUnchanged = !document.querySelector('#consent').checked &&
        ['prize', 'reason', 'unknown'].every(id => document.getElementById(id).value === '') &&
        document.querySelector('[name=nonce]').value === 'fixture-nonce' &&
        document.querySelector('[name=q]').value === '';
      const rolled = await api.FormFiller.rollbackAndVerifyLast();
      return {status: filled.status, verification: {details: filled.verification, items: preview.items.map(i => [i.fieldId, i.fieldType, i.fillAllowed])}, count: filled.filledCount, manualUnchanged,
        rolledBack: rolled.rollbackComplete, restored: JSON.stringify(state()) === before,
        submits, submitted_count_auto: filled.submitted_count_auto,
        searchExcluded: !analysis.fields.some(f => f.name === 'q')};
    }''')
    verification = result.pop("verification")
    assert result == {
        "status": "POST_FILL_VERIFICATION_PASSED", "count": 2,
        "manualUnchanged": True, "rolledBack": True, "restored": True,
        "submits": 0, "submitted_count_auto": 0, "searchExcluded": True,
    }, verification
    assert requests == []


def test_first_seen_form_requires_explicit_mapping_before_real_fill(browser_page) -> None:
    browser_page.goto((FIXTURES / "mapping_safety_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.previewMasked(
            analysis,
            {email: "p***@example.invalid", full_name: "P***"},
            {templateApproved: false, mappingDecisions: {}}
          );
          const blocked = window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid", last_name: "Yamada", first_name: "Taro"},
            analysis,
            {templateApproved: false, mappingDecisions: {}}
          );
          return Promise.resolve(blocked);
        }"""
    )

    assert result["status"] == "HUMAN_MAPPING_REQUIRED"
    assert result["filledCount"] == 0
    assert browser_page.locator("#email").input_value() == ""
    assert browser_page.locator("#guardian-name").input_value() == ""


def test_post_fill_reset_rolls_back_every_changed_field(browser_page) -> None:
    browser_page.goto((FIXTURES / "mapping_safety_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const email = analysis.fields.find(field => field.fieldType === "email");
          const preview = window.KenshoExtension.FormFiller.preview(
            analysis,
            {email: "pii-test@example.invalid"}
          );
          const mappingDecisions = Object.fromEntries(
            preview.items.map(item => [item.fieldId, {action: "approve", profileKey: item.fieldType}])
          );
          const filled = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {templateApproved: true, mappingDecisions}
          );
          const rolled = await window.KenshoExtension.FormFiller.rollbackAndVerifyLast();
          return {filled, rolled};
        }"""
    )

    assert result["filled"]["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLBACK_REQUIRED"
    assert result["rolled"]["rollbackComplete"] is True
    assert browser_page.locator("#email").input_value() == ""


def test_form_fingerprint_change_rolls_back_and_blocks_fill(browser_page) -> None:
    browser_page.goto((FIXTURES / "mapping_safety_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.preview(
            analysis,
            {email: "pii-test@example.invalid"}
          );
          document.querySelector("#address-line-2").setAttribute("required", "true");
          const mappingDecisions = Object.fromEntries(
            preview.items.map(item => [item.fieldId, {action: "approve", profileKey: item.fieldType}])
          );
          const filled = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {templateApproved: true, mappingDecisions}
          );
          const rolled = await window.KenshoExtension.FormFiller.rollbackAndVerifyLast();
          return {filled, rolled};
        }"""
    )

    assert result["filled"]["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLBACK_REQUIRED"
    assert result["rolled"]["rollbackComplete"] is True
    assert browser_page.locator("#email").input_value() == ""


def test_mapping_analysis_never_serializes_fixture_pii(browser_page) -> None:
    browser_page.goto((FIXTURES / "mapping_safety_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "content/field-matcher.js",
        "content/form-detector.js",
    )
    analysis = browser_page.evaluate(
        """() => JSON.stringify(window.KenshoExtension.FormDetector.scan(document))"""
    )
    assert "pii-test@example.invalid" not in analysis
    assert "PII_TEST" not in analysis


def test_ambiguous_field_is_visible_and_uses_human_selected_profile_key(browser_page) -> None:
    browser_page.goto((FIXTURES / "mapping_safety_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = {
            fields: [{
              fieldId: "ambiguous-field",
              fieldType: "unknown",
              type: "text",
              confidence: 0.86,
              fillAllowed: false,
              label: "お名前",
              reasons: ["ambiguous_mapping"],
              required: true,
            }],
            manualReviewFields: [],
          };
          const maskedProfile = {
            email: "p***@example.invalid",
            full_name: "F***",
          };
          const before = window.KenshoExtension.FormFiller.previewMasked(
            analysis,
            maskedProfile,
            {templateApproved: false, mappingDecisions: {}}
          );
          const after = window.KenshoExtension.FormFiller.previewMasked(
            analysis,
            maskedProfile,
            {
              templateApproved: false,
              mappingDecisions: {
                "ambiguous-field": {action: "approve", profileKey: "email"},
              },
            }
          );
          const emailNode = document.querySelector("#email");
          emailNode.replaceWith(emailNode.cloneNode(true));
          const scanned = window.KenshoExtension.FormDetector.scan(document);
          const emailField = scanned.fields.find(field => field.fieldType === "email");
          const mappedAnalysis = {
            ...scanned,
            fields: [{...emailField, fieldType: "unknown", confidence: 0.86, fillAllowed: false}],
          };
          const mappedPreview = window.KenshoExtension.FormFiller.previewMasked(
            mappedAnalysis,
            maskedProfile,
            {
              templateApproved: false,
              mappingDecisions: {
                [emailField.fieldId]: {action: "approve", profileKey: "email"},
              },
            }
          );
          const filled = await window.KenshoExtension.FormFiller.fillAndVerify(
            mappedPreview,
            {email: "pii-test@example.invalid"},
            mappedAnalysis,
            {
              templateApproved: false,
              mappingDecisions: {
                [emailField.fieldId]: {action: "approve", profileKey: "email"},
              },
            }
          );
          return {before, after, filled};
        }"""
    )

    assert result["before"]["items"][0]["requiresHumanMapping"] is True
    assert result["before"]["items"][0]["fillAllowed"] is False
    assert result["after"]["items"][0]["maskedValue"] == "p***@example.invalid"
    assert result["filled"]["status"] == "POST_FILL_VERIFICATION_PASSED"
    assert browser_page.locator("#email").input_value() == "pii-test@example.invalid"


def test_unrelated_disabled_state_is_restored_during_rollback(browser_page) -> None:
    browser_page.goto((FIXTURES / "mapping_safety_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const email = analysis.fields.find(field => field.fieldType === "email");
          const preview = window.KenshoExtension.FormFiller.previewMasked(
            {...analysis, fields: [email]},
            {email: "p***@example.invalid"},
            {
              templateApproved: true,
              mappingDecisions: {
                [email.fieldId]: {action: "approve", profileKey: "email"}
              }
            }
          );
          document.querySelector("#email").addEventListener("input", () => {
            document.querySelector("#guardian-name").disabled = true;
          });
          const filled = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {
              templateApproved: true,
              mappingDecisions: {
                [email.fieldId]: {action: "approve", profileKey: "email"}
              }
            }
          );
          const rolled = await window.KenshoExtension.FormFiller.rollbackAndVerifyLast();
          return {filled, rolled};
        }"""
    )

    assert result["filled"]["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLBACK_REQUIRED"
    assert result["rolled"]["rollbackComplete"] is True
    assert browser_page.locator("#email").input_value() == ""
    assert browser_page.locator("#guardian-name").is_disabled() is False


def test_dynamic_form_change_is_treated_as_incomplete_rollback(browser_page) -> None:
    browser_page.goto((FIXTURES / "rollback_dynamic_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const email = analysis.fields.find(field => field.fieldType === "email");
          const scopedAnalysis = {...analysis, fields: [email]};
          const preview = window.KenshoExtension.FormFiller.preview(
            scopedAnalysis,
            {email: "pii-test@example.invalid"}
          );
          const first = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {templateApproved: true}
          );
          const rolled = await window.KenshoExtension.FormFiller.rollbackAndVerifyLast();
          const second = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {templateApproved: true}
          );
          return {
            first,
            rolled,
            second,
            emailValue: document.querySelector("#email").value,
            dynamicFieldExists: Boolean(document.querySelector("#dynamic-field")),
          };
        }"""
    )

    assert result["first"]["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLBACK_REQUIRED"
    assert result["rolled"]["rollbackComplete"] is False
    assert result["second"]["status"] == "ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED"
    assert result["second"]["filledCount"] == 0
    assert result["emailValue"] == ""
    assert result["dynamicFieldExists"] is True


def test_controlled_input_writeback_is_resynchronized_during_rollback(browser_page) -> None:
    browser_page.goto((FIXTURES / "rollback_controlled_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.preview(
            analysis,
            {email: "pii-test@example.invalid", phone: "09000002741"}
          );
          const mappingDecisions = Object.fromEntries(
            preview.items.map(item => [item.fieldId, {action: "approve", profileKey: item.fieldType}])
          );
          const filled = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid", phone: "09000002741"},
            analysis,
            {templateApproved: true, mappingDecisions}
          );
          const rolled = await window.KenshoExtension.FormFiller.rollbackAndVerifyLast();
          return {
            filled,
            rolled,
            emailValue: document.querySelector("#email").value,
            phoneValue: document.querySelector("#phone").value,
          };
        }"""
    )

    assert result["filled"]["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLBACK_REQUIRED"
    assert result["rolled"]["rollbackComplete"] is True
    assert result["emailValue"] == ""
    assert result["phoneValue"] == ""


def test_manual_rollback_resynchronizes_controlled_form(browser_page) -> None:
    browser_page.goto((FIXTURES / "rollback_controlled_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.preview(
            analysis,
            {email: "pii-test@example.invalid", phone: "09000002741"}
          );
          const filled = window.KenshoExtension.FormFiller.fill(
            preview,
            {email: "pii-test@example.invalid", phone: "09000002741"}
          );
          const rolled = await window.KenshoExtension.FormFiller.rollbackAndVerifyLast();
          return {
            filled,
            rolled,
            emailValue: document.querySelector("#email").value,
            phoneValue: document.querySelector("#phone").value,
          };
        }"""
    )

    assert result["filled"]["filledCount"] == 2
    assert result["rolled"]["rollbackComplete"] is True
    assert result["emailValue"] == ""
    assert result["phoneValue"] == ""


def test_unrestorable_unrelated_state_blocks_all_future_fill(browser_page) -> None:
    browser_page.goto((FIXTURES / "mapping_safety_form.html").as_uri())
    _load_scripts(
        browser_page,
        "shared/config.js",
        "shared/redaction.js",
        "shared/normalization.js",
        "shared/form-fingerprint.js",
        "content/field-matcher.js",
        "content/form-detector.js",
        "content/form-filler.js",
    )

    result = browser_page.evaluate(
        """async () => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const email = analysis.fields.find(field => field.fieldType === "email");
          const preview = window.KenshoExtension.FormFiller.previewMasked(
            {...analysis, fields: [email]},
            {email: "p***@example.invalid"},
            {
              templateApproved: true,
              mappingDecisions: {
                [email.fieldId]: {action: "approve", profileKey: "email"}
              }
            }
          );
          const guardian = document.querySelector("#guardian-name");
          let forcedDisabled = false;
          Object.defineProperty(guardian, "disabled", {
            configurable: true,
            get: () => forcedDisabled,
            set: value => { if (value) forcedDisabled = true; }
          });
          document.querySelector("#email").addEventListener("input", () => {
            guardian.disabled = true;
          });
          const first = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {
              templateApproved: true,
              mappingDecisions: {
                [email.fieldId]: {action: "approve", profileKey: "email"}
              }
            }
          );
          const rolled = await window.KenshoExtension.FormFiller.rollbackAndVerifyLast();
          const second = await window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {
              templateApproved: true,
              mappingDecisions: {
                [email.fieldId]: {action: "approve", profileKey: "email"}
              }
            }
          );
          return {first, rolled, second};
        }"""
    )

    assert result["first"]["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLBACK_REQUIRED"
    assert result["rolled"]["rollbackComplete"] is False
    assert result["second"]["status"] == "ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED"
    assert result["second"]["filledCount"] == 0
