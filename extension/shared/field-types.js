(function initializeFieldTypes(root) {
  "use strict";

  const FIELD_TYPES = Object.freeze([
    "last_name",
    "first_name",
    "full_name",
    "last_name_kana",
    "first_name_kana",
    "full_name_kana",
    "email",
    "phone",
    "postal_code",
    "prefecture",
    "city",
    "street",
    "building",
    "birth_date",
    "birth_year",
    "birth_month",
    "birth_day",
    "age",
    "gender",
    "free_text",
    "unknown",
  ]);

  const PROFILE_KEYS = Object.freeze(
    FIELD_TYPES.filter(
      (value) =>
        value !== "unknown" &&
        ![
          "full_name",
          "full_name_kana",
          "birth_year",
          "birth_month",
          "birth_day",
          "age",
        ].includes(value)
    )
  );
  const AUTO_FILL_THRESHOLD = 0.95;

  const api = Object.freeze({ FIELD_TYPES, PROFILE_KEYS, AUTO_FILL_THRESHOLD });
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.FieldTypes = api;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
