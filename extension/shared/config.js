(function initializeConfig(root) {
  "use strict";

  const config = Object.freeze({
    confidence: Object.freeze({
      autoFill: 0.95,
      manualReview: 0.75,
    }),
    submitted_count_auto: 0,
  });

  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.Config = config;
  if (typeof module !== "undefined" && module.exports) module.exports = config;
})(typeof globalThis !== "undefined" ? globalThis : this);
