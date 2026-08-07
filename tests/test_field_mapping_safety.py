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


@pytest.fixture()
def browser_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


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
        """() => {
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
        """() => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const email = analysis.fields.find(field => field.fieldType === "email");
          const preview = window.KenshoExtension.FormFiller.preview(
            analysis,
            {email: "pii-test@example.invalid"}
          );
          const mappingDecisions = Object.fromEntries(
            preview.items.map(item => [item.fieldId, {action: "approve", profileKey: item.fieldType}])
          );
          return window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {templateApproved: true, mappingDecisions}
          );
        }"""
    )

    assert result["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLED_BACK"
    assert result["rollbackComplete"] is True
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
        """() => {
          const analysis = window.KenshoExtension.FormDetector.scan(document);
          const preview = window.KenshoExtension.FormFiller.preview(
            analysis,
            {email: "pii-test@example.invalid"}
          );
          document.querySelector("#address-line-2").setAttribute("required", "true");
          const mappingDecisions = Object.fromEntries(
            preview.items.map(item => [item.fieldId, {action: "approve", profileKey: item.fieldType}])
          );
          return window.KenshoExtension.FormFiller.fillAndVerify(
            preview,
            {email: "pii-test@example.invalid"},
            analysis,
            {templateApproved: true, mappingDecisions}
          );
        }"""
    )

    assert result["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLED_BACK"
    assert result["rollbackComplete"] is True
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
          return window.KenshoExtension.FormFiller.fillAndVerify(
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
        }"""
    )

    assert result["status"] == "POST_FILL_VERIFICATION_FAILED_ROLLED_BACK"
    assert result["rollbackComplete"] is True
    assert browser_page.locator("#email").input_value() == ""
    assert browser_page.locator("#guardian-name").is_disabled() is False


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
          return {first, second};
        }"""
    )

    assert result["first"]["status"] == "ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED"
    assert result["first"]["rollbackComplete"] is False
    assert result["second"]["status"] == "ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED"
    assert result["second"]["filledCount"] == 0
