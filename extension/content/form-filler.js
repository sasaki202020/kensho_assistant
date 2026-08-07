(function initializeFormFiller(root) {
  "use strict";

  const originals = new Map();
  const threshold = 0.75;
  let verificationBlocked = false;

  function profileValueForField(fieldType, profile) {
    if (fieldType === "full_name") {
      return [profile.last_name, profile.first_name].filter(Boolean).join(" ");
    }
    if (fieldType === "full_name_kana") {
      return [profile.last_name_kana, profile.first_name_kana]
        .filter(Boolean)
        .join(" ");
    }
    if (["birth_year", "birth_month", "birth_day", "age"].includes(fieldType)) {
      return profile.birth_date || "";
    }
    return profile[fieldType];
  }

  function isForbiddenField(field) {
    return [
      "free_text",
      "manual_review",
      "prize",
      "consent",
    ].includes(field.fieldType);
  }

  function preview(analysis, profile) {
    const items = [];
    const warnings = [];
    for (const field of analysis.fields || []) {
      const value = profileValueForField(field.fieldType, profile);
      if (
        field.fieldType === "unknown" ||
        field.confidence < threshold ||
        value === undefined ||
        value === ""
      ) {
        if (field.required) {
          warnings.push({
            fieldId: field.fieldId,
            reason:
              field.fieldType === "unknown"
                ? "未分類の必須項目"
                : "入力値または信頼度が不足",
          });
        }
        continue;
      }
      items.push({
        fieldId: field.fieldId,
        fieldType: field.fieldType,
        type: field.type,
        profileKey: field.fieldType,
        confidence: field.confidence,
        evidence: field.reasons || [],
        warnings: [],
        fillAllowed: field.fillAllowed !== false && !isForbiddenField(field),
        valueTransform: field.valueTransform || "none",
        maskedValue: root.KenshoExtension.Redaction.maskValue(field.fieldType, value),
        label: field.label || field.placeholder || field.name || field.fieldType,
      });
    }
    return {
      items,
      warnings,
      blocked: Boolean(
        analysis.loginRequired ||
          analysis.unsupportedIframes > 0 ||
          analysis.unsupportedForm
      ),
      submitted_count_auto: 0,
    };
  }

  function previewMasked(analysis, maskedProfile, options = {}) {
    const items = [];
    const warnings = [];
    const legacyPreview = options.templateApproved === undefined;
    const templateApproved = legacyPreview || options.templateApproved === true;
    const mappingDecisions = options.mappingDecisions || {};
    for (const field of analysis.fields || []) {
      const decision = mappingDecisions[field.fieldId] || null;
      const confidence = Number(field.confidence || 0);
      const selectedProfileKey = decision?.profileKey || field.fieldType;
      const maskedValue =
        selectedProfileKey && selectedProfileKey !== "unknown"
          ? profileValueForField(selectedProfileKey, maskedProfile)
          : "";
      const mappable =
        confidence >=
          (root.KenshoExtension.Config?.confidence?.manualReview || threshold) &&
        !isForbiddenField(field) &&
        String(field.type || "").toLowerCase() !== "radio";
      const fillAllowed =
        mappable &&
        (decision?.action === "approve" ||
          (legacyPreview && field.fillAllowed !== false));
      const requiresHumanMapping =
        !legacyPreview && !templateApproved && mappable && !decision;
      const visibleUnknown = field.fieldType === "unknown" && mappable;
      if ((maskedValue || visibleUnknown) && !isForbiddenField(field)) {
        items.push({
          fieldId: field.fieldId,
          fieldType: field.fieldType,
          type: field.type,
          profileKey: decision?.profileKey || field.fieldType,
          confidence,
          evidence: field.reasons || [],
          warnings: field.warnings || [],
          fillAllowed,
          requiresHumanMapping,
          mappingDecision: decision,
          valueTransform: field.valueTransform || "none",
          maskedValue: maskedValue || "要確認",
          label: field.label || field.placeholder || field.name || field.fieldType,
        });
      }
      if (field.required && (!maskedValue || !mappable)) {
        warnings.push({
          fieldId: field.fieldId,
          reason:
            field.fieldType === "unknown"
              ? "未分類または自動入力禁止の項目"
              : "人間確認が必要な信頼度または入力値不足",
        });
      } else if (requiresHumanMapping) {
        warnings.push({fieldId: field.fieldId, reason: "欄対応の人間確認が必要"});
      }
    }
    for (const manual of analysis.manualReviewFields || []) {
      warnings.push({fieldId: null, reason: manual.reason});
    }
    return {
      items,
      warnings,
      blocked: Boolean(
        analysis.loginRequired ||
          analysis.unsupportedIframes > 0 ||
          analysis.unsupportedForm
      ),
      templateApproved,
      submitted_count_auto: 0,
    };
  }

  function nativeValueSetter(element) {
    const prototype = Object.getPrototypeOf(element);
    return Object.getOwnPropertyDescriptor(prototype, "value")?.set || null;
  }

  function dispatchInputEvents(element) {
    for (const type of ["input", "change", "blur"]) {
      element.dispatchEvent(new Event(type, {bubbles: true, composed: true}));
    }
  }

  function setElementValue(element, value, emitEvents = false) {
    if (!originals.has(element)) {
      originals.set(element, {
        value: element.value,
        checked: Boolean(element.checked),
      });
    }
    const tagName = String(element.tagName || "").toLowerCase();
    const type = String(element.type || "").toLowerCase();
    if (["checkbox", "file", "password"].includes(type)) return false;

    if (type === "radio") {
      const requested = String(value || "").trim().toLowerCase();
      const label = Array.from(element.labels || [])
        .map((item) => String(item.textContent || "").trim().toLowerCase())
        .join(" ");
      const aliases = {
        男性: ["男性", "男", "male", "m"],
        女性: ["女性", "女", "female", "f"],
        その他: ["その他", "other"],
        回答しない: ["回答しない", "無回答", "prefer not to say"],
      };
      const matchedByLabel = Object.entries(aliases).some(
        ([canonical, values]) =>
          values.includes(requested) && label.includes(canonical.toLowerCase())
      );
      if (String(element.value) !== String(value) && !matchedByLabel) return false;
      element.checked = true;
    } else if (tagName === "select") {
      const matchingOption = Array.from(element.options || []).find(
        (option) =>
          option.value === String(value) ||
          String(option.textContent || "").trim() === String(value)
      );
      if (!matchingOption) return false;
      element.value = matchingOption.value;
    } else {
      const setter = nativeValueSetter(element);
      if (setter) setter.call(element, String(value));
      else element.value = String(value);
    }
    if (emitEvents) dispatchInputEvents(element);
    return true;
  }

  function valueForItem(item, profile) {
    const normalization = root.KenshoExtension.Normalization;
    const transform = item.valueTransform || "none";
    const profileKey = item.profileKey || item.fieldType;
    if (profileKey && profileKey !== item.fieldType && transform === "none") {
      return profile[profileKey];
    }
    if (transform === "hiragana") return normalization.toHiragana(profile[profileKey]);
    if (transform === "katakana") return normalization.toKatakana(profile[profileKey]);
    if (transform === "postal_hyphen") return normalization.postalCode(profile.postal_code, true);
    if (transform.startsWith("postal_part_")) {
      const digits = normalization.postalCode(profile.postal_code);
      return transform.endsWith("1") ? digits.slice(0, 3) : digits.slice(3);
    }
    if (transform.startsWith("phone_part_")) {
      const index = Number(transform.slice(-1)) - 1;
      return normalization.phoneParts(profile.phone)[index] || "";
    }
    if (transform.startsWith("birth_")) {
      return (
        normalization.birthDateParts(profile.birth_date)?.[
          transform.slice("birth_".length)
        ] || ""
      );
    }
    if (transform === "age_from_birth_date") {
      return normalization.ageFromBirthDate(profile.birth_date);
    }
    if (item.fieldType === "full_name") {
      return [profile.last_name, profile.first_name].filter(Boolean).join(" ");
    }
    if (item.fieldType === "full_name_kana") {
      return [profile.last_name_kana, profile.first_name_kana]
        .filter(Boolean)
        .join(" ");
    }
    if (item.fieldType === "phone") return normalization.asDigits(profile.phone);
    if (item.fieldType === "postal_code") return normalization.postalCode(profile.postal_code);
    return profile[profileKey];
  }

  function fill(previewResult, profile) {
    if (previewResult.blocked) {
      return {filledCount: 0, blocked: true, submitted_count_auto: 0};
    }
    let filledCount = 0;
    for (const item of previewResult.items || []) {
      if (
        item.fillAllowed === false &&
        String(item.type || "").toLowerCase() !== "radio"
      ) continue;
      const element = root.KenshoExtension.FormDetector.resolveElement(item.fieldId);
      if (!element) continue;
      const value = valueForItem(item, profile);
      if (value !== "" && setElementValue(element, value, true)) filledCount += 1;
    }
    return {filledCount, blocked: false, submitted_count_auto: 0};
  }

  function controlSnapshot() {
    return Array.from(document.querySelectorAll("input,select,textarea")).map(
      (element) => ({
        element,
        value: element.value,
        checked: Boolean(element.checked),
        disabled: Boolean(element.disabled),
        readOnly: Boolean(element.readOnly),
      })
    );
  }

  function currentFingerprint() {
    const detector = root.KenshoExtension.FormDetector;
    return detector?.scan ? detector.scan(document).formFingerprint : "";
  }

  function rollback() {
    let restoredCount = 0;
    for (const [element, original] of originals.entries()) {
      const setter = nativeValueSetter(element);
      if (setter) setter.call(element, original.value);
      else element.value = original.value;
      if ("checked" in element) element.checked = original.checked;
      restoredCount += 1;
    }
    originals.clear();
    return {restoredCount, rollbackComplete: true, submitted_count_auto: 0};
  }

  function rollbackAndVerify(snapshot) {
    const result = rollback();
    let restoreFailed = false;
    for (const before of snapshot || []) {
      const element = before.element;
      try {
        const setter = nativeValueSetter(element);
        if (setter) setter.call(element, before.value);
        else element.value = before.value;
        if ("checked" in element) element.checked = before.checked;
        if ("disabled" in element) element.disabled = before.disabled;
        if ("readOnly" in element) element.readOnly = before.readOnly;
      } catch (_error) {
        restoreFailed = true;
      }
    }
    const incomplete = (snapshot || []).some(
      (before) =>
        before.element.value !== before.value ||
        Boolean(before.element.checked) !== before.checked ||
        Boolean(before.element.disabled) !== before.disabled ||
        Boolean(before.element.readOnly) !== before.readOnly
    );
    result.rollbackComplete = !restoreFailed && !incomplete;
    return result;
  }

  async function fillAndVerify(previewResult, profile, analysis, options = {}) {
    if (verificationBlocked) {
      return {
        status: "ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED",
        filledCount: 0,
        rollbackComplete: false,
        submitted_count_auto: 0,
      };
    }
    if (
      previewResult?.blocked ||
      analysis?.captchaDetected ||
      analysis?.loginRequired ||
      analysis?.unsupportedIframes > 0 ||
      analysis?.unsupportedForm
    ) {
      return {status: "SAFE_STOP_HUMAN_REVIEW_REQUIRED", filledCount: 0, submitted_count_auto: 0};
    }
    const templateApproved = options.templateApproved === true;
    const mappingDecisions = options.mappingDecisions || {};
    const unresolved = (previewResult?.items || []).some(
      (item) =>
        item.requiresHumanMapping && !mappingDecisions[item.fieldId]
    );
    if (!templateApproved && unresolved) {
      return {status: "HUMAN_MAPPING_REQUIRED", filledCount: 0, submitted_count_auto: 0};
    }
    const snapshot = controlSnapshot();
    let filledCount = 0;
    for (const item of previewResult?.items || []) {
      const decision = mappingDecisions[item.fieldId];
      if (item.fillAllowed === false && decision?.action !== "approve") continue;
      if (item.fillAllowed !== true) continue;
      const element = root.KenshoExtension.FormDetector.resolveElement(item.fieldId);
      if (!element || element.disabled || element.readOnly) continue;
      const value = valueForItem(item, profile);
      if (value === undefined || value === "") continue;
      if (!setElementValue(element, value, true)) {
        const rolled = rollbackAndVerify(snapshot);
        if (!rolled.rollbackComplete) verificationBlocked = true;
        return {
          status: rolled.rollbackComplete
            ? "POST_FILL_VERIFICATION_FAILED_ROLLED_BACK"
            : "ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED",
          filledCount,
          rollbackComplete: rolled.rollbackComplete,
          submitted_count_auto: 0,
        };
      }
      filledCount += 1;
    }
    const targetIds = new Set(
      (previewResult?.items || [])
        .filter(
          (item) =>
            item.fillAllowed !== false ||
            mappingDecisions[item.fieldId]?.action === "approve"
        )
        .map((item) => item.fieldId)
    );
    const itemElements = new Map(
      [...targetIds]
        .map((fieldId) => [
          fieldId,
          root.KenshoExtension.FormDetector.resolveElement(fieldId),
        ])
        .filter(([, element]) => Boolean(element))
    );
    const targetElements = new Set(
      [...itemElements.values()]
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    const current = currentFingerprint();
    const fingerprintChanged =
      analysis?.formFingerprint && current && analysis.formFingerprint !== current;
    const targetMismatchFieldIds = (previewResult?.items || [])
      .filter((item) => {
      if (!targetIds.has(item.fieldId)) return false;
      const element = itemElements.get(item.fieldId);
      if (!element) return true;
      const expected = String(valueForItem(item, profile) ?? "");
      if (String(element.type || "").toLowerCase() === "radio") return !element.checked;
      return String(element.value) !== expected;
      })
      .map((item) => item.fieldId);
    const unrelatedChangedCount = snapshot.filter(
      (before) =>
        !targetElements.has(before.element) &&
        (before.element.value !== before.value ||
          Boolean(before.element.checked) !== before.checked ||
          Boolean(before.element.disabled) !== before.disabled ||
          Boolean(before.element.readOnly) !== before.readOnly)
    ).length;
    const verification = {
      fingerprintChanged: Boolean(fingerprintChanged),
      targetMismatchFieldIds: targetMismatchFieldIds.slice(),
      unrelatedChangedCount,
    };
    if (fingerprintChanged || targetMismatchFieldIds.length || unrelatedChangedCount) {
      const rolled = rollbackAndVerify(snapshot);
      if (!rolled.rollbackComplete) verificationBlocked = true;
      return {
        status: rolled.rollbackComplete
          ? "POST_FILL_VERIFICATION_FAILED_ROLLED_BACK"
            : "ROLLBACK_INCOMPLETE_HUMAN_REVIEW_REQUIRED",
        filledCount,
        rollbackComplete: rolled.rollbackComplete,
        verification,
        submitted_count_auto: 0,
      };
    }
    return {
      status: "POST_FILL_VERIFICATION_PASSED",
      filledCount,
      rollbackComplete: false,
      verification: {
        fingerprintChanged: false,
        targetMismatchFieldIds: [],
        unrelatedChangedCount: 0,
      },
      submitted_count_auto: 0,
    };
  }

  const api = Object.freeze({
    preview,
    previewMasked,
    fill,
    fillAndVerify,
    rollback,
    valueForItem,
    profileValueForField,
  });
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.FormFiller = api;

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
