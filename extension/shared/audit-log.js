(function initializeAuditLog(root) {
  "use strict";

  const allowedKeys = new Set([
    "extension_version",
    "site_id",
    "origin",
    "pathname",
    "form_count",
    "detected_field_count",
    "high_confidence_fields",
    "manual_review_fields",
    "skipped_fields",
    "filled_field_count",
    "warning_count",
    "captcha_detected",
    "login_detected",
    "submit_blocked",
    "auto_submit_detected",
    "rollback_used",
  ]);

  function safeLocation(urlValue) {
    const url = new URL(urlValue);
    return { origin: url.origin, pathname: url.pathname || "/" };
  }

  function createRecord(input) {
    const record = {};
    for (const [key, value] of Object.entries(input || {})) {
      if (allowedKeys.has(key)) record[key] = value;
    }
    if (input?.url) Object.assign(record, safeLocation(input.url));
    record.auto_submit_detected = Number(record.auto_submit_detected || 0);
    return Object.freeze(record);
  }

  const api = Object.freeze({ createRecord, safeLocation });
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.AuditLog = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
