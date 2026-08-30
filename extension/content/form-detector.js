(function initializeFormDetector(root) {
  "use strict";

  const elementRegistry = new Map();
  let fieldSequence = 0;
  const sensitivePattern =
    /password|one-time-code|cc-|credit|card|bank|account|マイナンバー|本人確認|秘密の質問|規約|同意|メルマガ|第三者提供|応募理由|商品.*感想|アンケート/i;
  const manualChoicePattern =
    /規約|同意|メルマガ|newsletter|第三者提供|応募理由|商品.*感想|アンケート|賞品|プレゼント|景品|保護者|ハンドル|ニックネーム/i;

  function labelText(element) {
    if (element.labels && element.labels.length) {
      return Array.from(element.labels).map((label) => label.textContent || "").join(" ");
    }
    const parentLabel = element.closest ? element.closest("label") : null;
    return parentLabel ? parentLabel.textContent || "" : "";
  }

  function surroundingText(element) {
    const parent = element.parentElement;
    return parent ? String(parent.textContent || "").slice(0, 180) : "";
  }

  function tableGroupMetadata(element) {
    const row = element.closest?.("tr");
    if (!row) return {groupLabel: "", groupControlCount: 0};
    const headers = Array.from(row.children || []).filter(
      (child) => String(child.tagName || "").toLowerCase() === "th"
    );
    const controls = Array.from(row.querySelectorAll("input,select,textarea")).filter(
      (control) => String(control.type || "").toLowerCase() !== "hidden"
    );
    return {
      groupLabel: headers.map((header) => String(header.textContent || "").trim()).join(" "),
      groupControlCount: controls.length,
    };
  }

  function relativePath(element) {
    const segments = [];
    let current = element;
    while (current && current.nodeType === 1) {
      const tagName = String(current.tagName || "").toLowerCase();
      let siblingIndex = 0;
      let sibling = current.previousElementSibling;
      while (sibling) {
        if (String(sibling.tagName || "").toLowerCase() === tagName) {
          siblingIndex += 1;
        }
        sibling = sibling.previousElementSibling;
      }
      segments.unshift(`${tagName}[${siblingIndex}]`);
      current = current.parentElement;
    }
    return segments.join("/");
  }

  function metadataFor(element) {
    const tableGroup = tableGroupMetadata(element);
    const radioOptions =
      String(element.type || "").toLowerCase() === "radio" && element.name
        ? Array.from(
            element.ownerDocument?.querySelectorAll?.('input[type="radio"]') || []
          )
            .filter((candidate) => candidate.name === element.name)
            .map((candidate) => labelText(candidate).trim())
            .filter(Boolean)
        : [];
    return {
      tagName: String(element.tagName || "").toLowerCase(),
      type: String(element.type || "").toLowerCase(),
      inputType: String(element.type || "").toLowerCase(),
      name: element.getAttribute("name") || "",
      id: element.id || "",
      autocomplete: element.getAttribute("autocomplete") || "",
      ariaLabel: element.getAttribute("aria-label") || "",
      placeholder: element.getAttribute("placeholder") || "",
      label: labelText(element).trim(),
      ...tableGroup,
      surroundingText: surroundingText(element).trim(),
      required: Boolean(element.required),
      disabled: Boolean(element.disabled),
      readOnly: Boolean(element.readOnly),
      path: relativePath(element),
      selectOptions:
        String(element.tagName || "").toLowerCase() === "select"
          ? Array.from(element.options || []).map((option) =>
              String(option.textContent || "").trim()
            )
          : radioOptions,
    };
  }

  function valueTransform(metadata, fieldType) {
    const name = String(metadata.name || "").toLowerCase();
    const label = String(metadata.label || "");
    const phoneMatch = name.match(/(?:tel|phone)[-_]?([123])$/);
    if (fieldType === "phone" && phoneMatch) return `phone_part_${phoneMatch[1]}`;
    const postalMatch = name.match(/(?:zip|postal)[-_]?([12])$/);
    const japanesePostalMatch = name.match(/郵便番号[-_]?([12])$/);
    if (fieldType === "postal_code" && (postalMatch || japanesePostalMatch)) {
      return `postal_part_${(postalMatch || japanesePostalMatch)[1]}`;
    }
    if (fieldType === "last_name_kana" || fieldType === "first_name_kana") {
      return /かな|ひらがな/.test(label) ? "hiragana" : "katakana";
    }
    if (fieldType === "postal_code" && /[-ー]/.test(metadata.placeholder || "")) {
      return "postal_hyphen";
    }
    if (fieldType === "birth_year") return "birth_year";
    if (fieldType === "birth_month") return "birth_month";
    if (fieldType === "birth_day") return "birth_day";
    if (fieldType === "age") return "age_from_birth_date";
    return "none";
  }

  function rootsFromDocument(documentRoot) {
    const roots = [documentRoot];
    const queue = [documentRoot];
    while (queue.length) {
      const current = queue.shift();
      const elements = current.querySelectorAll ? current.querySelectorAll("*") : [];
      for (const element of elements) {
        if (element.getAttribute?.("data-kensho-extension-root") === "true") {
          continue;
        }
        if (element.shadowRoot) {
          roots.push(element.shadowRoot);
          queue.push(element.shadowRoot);
        }
        if (String(element.tagName || "").toLowerCase() === "iframe") {
          try {
            if (element.contentDocument) {
              roots.push(element.contentDocument);
              queue.push(element.contentDocument);
            }
          } catch (_error) {
            // Cross-origin iframe is intentionally unsupported.
          }
        }
      }
    }
    return roots;
  }

  function formScore(form) {
    const controls = Array.from(
      form.querySelectorAll?.("input,select,textarea,button") || []
    );
    let recognizedFields = 0;
    let requiredFields = 0;
    let submitControls = 0;
    for (const control of controls) {
      const type = String(control.type || "").toLowerCase();
      if (["submit", "image"].includes(type)) submitControls += 1;
      if (control.required) requiredFields += 1;
      if (["hidden", "file", "password", "checkbox", "submit", "button", "reset", "image"].includes(type)) {
        continue;
      }
      const match = root.KenshoExtension.FieldMatcher.matchField(metadataFor(control));
      if (match.fieldType !== "unknown" && match.fieldType !== "free_text") {
        recognizedFields += 1;
      }
    }
    return recognizedFields * 100 + requiredFields * 10 + submitControls * 5 + controls.length;
  }

  function formScopeRoots(roots) {
    const forms = [];
    const seen = new Set();
    for (const candidateRoot of roots) {
      for (const form of Array.from(candidateRoot.querySelectorAll?.("form") || [])) {
        if (form.closest?.('[data-kensho-extension-root="true"]') || seen.has(form)) continue;
        seen.add(form);
        forms.push(form);
      }
    }
    if (!forms.length) return roots;
    forms.sort((left, right) => formScore(right) - formScore(left));
    return [forms[0]];
  }

  function isExplicitlyHidden(frame) {
    for (let element = frame; element && element.nodeType === 1; element = element.parentElement) {
      if (element.hidden || element.getAttribute?.("aria-hidden") === "true") return true;
      const style = globalThis.getComputedStyle?.(element);
      if (style?.display === "none" || ["hidden", "collapse"].includes(style?.visibility)) {
        return true;
      }
    }
    return false;
  }

  function iframePurposeText(frame) {
    let pathname = "";
    try {
      const source = frame.getAttribute?.("src") || "";
      pathname = source ? new URL(source, globalThis.location?.href).pathname : "";
    } catch (_error) {
      pathname = "";
    }
    return [
      pathname,
      frame.getAttribute?.("title") || "",
      frame.getAttribute?.("name") || "",
      frame.getAttribute?.("id") || "",
      frame.getAttribute?.("class") || "",
    ]
      .join(" ")
      .toLowerCase();
  }

  function isIgnorableHiddenTrackingIframe(frame) {
    if (!isExplicitlyHidden(frame) || frame.closest?.("form")) return false;
    const purpose = iframePurposeText(frame);
    const applicationPurpose =
      /(?:^|[^a-z])(form|entry|apply|application|survey|login|auth|payment|captcha)(?:[^a-z]|$)/;
    const trackingPurpose =
      /(?:^|[^a-z])(beacon|pixel|analytics|tracking|measurement)(?:[^a-z]|$)|\/match\/iframe(?:[^a-z0-9]|$)/;
    return trackingPurpose.test(purpose) && !applicationPurpose.test(purpose);
  }

  function iframeSecurity(documentRoot, captchaSelector) {
    let ignoredHiddenTrackingIframes = 0;
    let unsupportedIframes = 0;
    for (const frame of Array.from(documentRoot.querySelectorAll("iframe"))) {
      if (frame.matches?.(captchaSelector)) continue;
      let opaque = false;
      try {
        opaque = !frame.contentDocument;
      } catch (_error) {
        opaque = true;
      }
      if (!opaque) continue;
      if (isIgnorableHiddenTrackingIframe(frame)) {
        ignoredHiddenTrackingIframes += 1;
      } else {
        unsupportedIframes += 1;
      }
    }
    return {unsupportedIframes, ignoredHiddenTrackingIframes};
  }

  function detectSecurity(documentRoot, roots) {
    const documents = roots.filter((candidate) => candidate.nodeType === 9);
    const text = documents
      .map((candidate) => String(candidate.body?.textContent || "").toLowerCase())
      .join(" ");
    const captchaSelector =
      '[class*="captcha" i], [id*="captcha" i], iframe[src*="captcha" i], iframe[src*="recaptcha" i], iframe[src*="hcaptcha" i], iframe[src*="turnstile" i]';
    const captchaDetected =
      /captcha|recaptcha|hcaptcha|turnstile|ロボットではありません|画像認証/.test(text) ||
      roots.some((candidate) => candidate.querySelector?.(captchaSelector));
    const loginRequired =
      roots.some((candidate) =>
        candidate.querySelector?.('input[type="password"], input[autocomplete="one-time-code"]')
      ) ||
      /ログイン|パスワード|ワンタイムコード|sms認証|メール認証/.test(text);
    const iframeState = iframeSecurity(documentRoot, captchaSelector);
    const unsupportedCanvas = roots.some((candidate) =>
      Boolean(candidate.querySelector?.("form canvas"))
    );
    const closedShadowMarker = roots.some((candidate) =>
      Boolean(candidate.querySelector?.("[data-kensho-closed-shadow]"))
    );
    return {
      captchaDetected: Boolean(captchaDetected),
      loginRequired: Boolean(loginRequired),
      ...iframeState,
      unsupportedCanvas,
      closedShadowMarker,
    };
  }

  function securityStatus(documentRoot) {
    return detectSecurity(documentRoot, rootsFromDocument(documentRoot));
  }

  function scan(documentRoot) {
    elementRegistry.clear();
    const roots = rootsFromDocument(documentRoot);
    const scopeRoots = formScopeRoots(roots);
    const fields = [];
    const manualReviewFields = [];
    const structuralFields = [];
    for (const candidateRoot of scopeRoots) {
      const elements = candidateRoot.querySelectorAll
        ? candidateRoot.querySelectorAll("input, select, textarea, button")
        : [];
      for (const element of elements) {
        const type = String(element.type || "").toLowerCase();
        const metadata = metadataFor(element);
        structuralFields.push(metadata);
        if (["submit", "button", "reset", "image"].includes(type)) continue;
        const frameworkControlled = Boolean(
          element._valueTracker ||
            element.__vnode ||
            element.__vue__ ||
            element.closest?.("[data-reactroot]")
        );
        const safetyText = [
          metadata.type,
          metadata.name,
          metadata.id,
          metadata.autocomplete,
          metadata.label,
          metadata.placeholder,
        ].join(" ");
        if (
          ["hidden", "file", "password", "checkbox"].includes(type) ||
          element.disabled ||
          element.readOnly ||
          sensitivePattern.test(safetyText) ||
          manualChoicePattern.test(safetyText)
        ) {
          manualReviewFields.push({
            fieldType: "manual_review",
            reason:
              type === "hidden"
                ? "hidden_or_honeypot"
                : type === "file"
                  ? "file_upload"
                : type === "password"
                  ? "login_or_password"
                  : type === "checkbox"
                    ? "consent_or_manual_checkbox"
                  : element.disabled || element.readOnly
                      ? "disabled_or_readonly"
                      : frameworkControlled
                        ? "framework_controlled"
                      : "sensitive_or_consent",
          });
          continue;
        }
        const match = root.KenshoExtension.FieldMatcher.matchField(metadata);
        const fieldId = `kensho-field-${++fieldSequence}`;
        elementRegistry.set(fieldId, element);
        fields.push({
          fieldId,
          ...metadata,
          fieldType: match.fieldType,
          confidence: match.confidence,
          reasons: match.reasons,
          evidence: match.reasons,
          frameworkControlled,
          warnings:
            [
              ...(match.confidence < 0.95 && match.confidence >= 0.75
                ? ["human_confirmation_required"]
                : []),
              ...(frameworkControlled ? ["framework_revalidation_required"] : []),
            ],
          fillAllowed:
            match.confidence >= 0.95 &&
            match.fieldType !== "unknown" &&
            match.fieldType !== "free_text" &&
            type !== "radio",
          valueTransform: valueTransform(metadata, match.fieldType),
        });
      }
    }
    const security = detectSecurity(documentRoot, roots);
    const fingerprintApi = root.KenshoExtension.FormFingerprint;
    const fingerprint = fingerprintApi
      ? fingerprintApi.computeFormFingerprint({fields: structuralFields})
      : {fingerprint: "", structureFingerprint: "", fields: []};
    const unsupportedForm = Boolean(
      security.unsupportedCanvas || security.closedShadowMarker
    );
    return {
      fields,
      manualReviewFields,
      fingerprintFields: fingerprint.fields,
      formFingerprint: fingerprint.fingerprint,
      structureFingerprint: fingerprint.structureFingerprint,
      detectedFieldCount: fields.length,
      unresolvedRequiredCount: fields.filter(
        (field) => field.required && field.fieldType === "unknown"
      ).length,
      ...security,
      unsupportedForm,
      submitted_count_auto: 0,
    };
  }

  function resolveElement(fieldId) {
    return elementRegistry.get(fieldId) || null;
  }

  function templateFromAnalysis(analysis, mappingDecisions, location = globalThis.location) {
    const fingerprintApi = root.KenshoExtension.FormFingerprint;
    const fields = (analysis?.fields || [])
      .map((field) => {
        const decision = mappingDecisions?.[field.fieldId];
        if (!decision || decision.action !== "approve") return null;
        const descriptor = (analysis.fingerprintFields || []).find(
          (candidate) => candidate.path === field.path
        );
        if (!descriptor || !fingerprintApi) return null;
        return {
          fieldId: field.fieldId,
          fieldType: field.fieldType,
          path: field.path,
          inputType: field.inputType,
          labelHash: descriptor.labelHash,
          attributeHash: descriptor.attributeHash,
          optionShapeHash: descriptor.optionShapeHash,
          approvedProfileKey: decision.profileKey || field.fieldType,
          confidenceBand: field.confidence >= 0.95 ? "high" : "reviewed",
          required: field.required,
          disabled: field.disabled,
          readOnly: field.readOnly,
          selectorCandidates: [field.path],
        };
      })
      .filter(Boolean);
    return {
      schemaVersion: 1,
      origin: location.origin,
      pathname: location.pathname || "/",
      fingerprint: analysis.formFingerprint,
      structureFingerprint: analysis.structureFingerprint,
      extensionVersion: "0.2.0",
      fields,
    };
  }

  const api = Object.freeze({scan, resolveElement, securityStatus, templateFromAnalysis});
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.FormDetector = api;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
