(function initializeFormTemplate(root) {
  "use strict";

  const FORBIDDEN_KEYS = new Set([
    "value",
    "inputValue",
    "rawValue",
    "profile",
    "email",
    "phone",
    "address",
    "postalCode",
    "birthDate",
    "cookie",
    "storage",
    "html",
    "screenshot",
    "trace",
  ]);
  const ALLOWED_FIELD_KEYS = new Set([
    "fieldId",
    "fieldType",
    "path",
    "inputType",
    "labelHash",
    "attributeHash",
    "optionShapeHash",
    "approvedProfileKey",
    "confidenceBand",
    "required",
    "disabled",
    "readOnly",
    "selectorCandidates",
  ]);

  function assertNoForbiddenKeys(value) {
    if (!value || typeof value !== "object") return;
    for (const [key, nested] of Object.entries(value)) {
      if (FORBIDDEN_KEYS.has(key) || /pii|secret|token|password/i.test(key)) {
        throw new Error("forbidden_template_value");
      }
      assertNoForbiddenKeys(nested);
    }
  }

  function normalizedLocation(origin, pathname) {
    const rawPathname = String(pathname || "/");
    const normalizedPathname = rawPathname.normalize("NFKC");
    if (
      !normalizedPathname.startsWith("/") ||
      normalizedPathname.includes("\\") ||
      normalizedPathname.includes("%") ||
      /[\u0000-\u001f]/.test(normalizedPathname) ||
      /@|\d{6,}/.test(normalizedPathname)
    ) {
      throw new Error("unsafe_template_pathname");
    }
    let url;
    try {
      url = new URL(`${origin}${normalizedPathname}`);
    } catch (_error) {
      throw new Error("invalid_template_location");
    }
    if (!/^https?:$/.test(url.protocol) || url.origin !== origin) {
      throw new Error("invalid_template_location");
    }
    if (url.search || url.hash) throw new Error("template_query_not_allowed");
    return {origin: url.origin, pathname: url.pathname || "/"};
  }

  function sanitizeTemplate(input) {
    if (!input || typeof input !== "object" || Array.isArray(input)) {
      throw new Error("invalid_template");
    }
    assertNoForbiddenKeys(input);
    const location = normalizedLocation(
      String(input.origin || ""),
      String(input.pathname || "/")
    );
    if (!String(input.fingerprint || "").match(/^[a-f0-9]{8,64}$/i)) {
      throw new Error("invalid_template_fingerprint");
    }
    const fields = Array.isArray(input.fields) ? input.fields : [];
    return {
      schemaVersion: 1,
      origin: location.origin,
      pathname: location.pathname,
      fingerprint: String(input.fingerprint),
      structureFingerprint: String(input.structureFingerprint || ""),
      extensionVersion: String(input.extensionVersion || ""),
      humanConfirmedAt: String(input.humanConfirmedAt || ""),
      fields: fields.map((field) => {
        if (!field || typeof field !== "object") throw new Error("invalid_template_field");
        for (const key of Object.keys(field)) {
          if (!ALLOWED_FIELD_KEYS.has(key)) throw new Error("forbidden_template_value");
        }
        return {
          fieldId: String(field.fieldId || ""),
          fieldType: String(field.fieldType || "unknown"),
          path: String(field.path || ""),
          inputType: String(field.inputType || ""),
          labelHash: String(field.labelHash || ""),
          attributeHash: String(field.attributeHash || ""),
          optionShapeHash: String(field.optionShapeHash || ""),
          approvedProfileKey: String(field.approvedProfileKey || ""),
          confidenceBand: String(field.confidenceBand || ""),
          required: Boolean(field.required),
          disabled: Boolean(field.disabled),
          readOnly: Boolean(field.readOnly),
          selectorCandidates: Array.isArray(field.selectorCandidates)
            ? field.selectorCandidates.map((value) => String(value)).slice(0, 3)
            : [],
        };
      }),
    };
  }

  const api = Object.freeze({sanitizeTemplate, FORBIDDEN_KEYS});
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.FormTemplate = api;

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
