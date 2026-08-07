(function initializeNormalization(root) {
  "use strict";

  function asDigits(value) {
    return String(value || "")
      .replace(/[０-９]/g, (character) =>
        String.fromCharCode(character.charCodeAt(0) - 0xfee0)
      )
      .replace(/\D/g, "");
  }

  function toKatakana(value) {
    return String(value || "").replace(/[\u3041-\u3096]/g, (character) =>
      String.fromCharCode(character.charCodeAt(0) + 0x60)
    );
  }

  function toHiragana(value) {
    return String(value || "").replace(/[\u30a1-\u30f6]/g, (character) =>
      String.fromCharCode(character.charCodeAt(0) - 0x60)
    );
  }

  function postalCode(value, withHyphen = false) {
    const digits = asDigits(value).slice(0, 7);
    return withHyphen && digits.length === 7
      ? `${digits.slice(0, 3)}-${digits.slice(3)}`
      : digits;
  }

  function phoneParts(value) {
    const digits = asDigits(value);
    if (digits.length === 11) return [digits.slice(0, 3), digits.slice(3, 7), digits.slice(7)];
    if (digits.length === 10) return [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6)];
    return [digits];
  }

  function birthDateParts(value) {
    const match = String(value || "").match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
    if (!match) return null;
    return {
      year: match[1],
      month: match[2].padStart(2, "0"),
      day: match[3].padStart(2, "0"),
    };
  }

  function ageFromBirthDate(value, referenceDate = new Date()) {
    const parts = birthDateParts(value);
    if (!parts) return "";
    const birthYear = Number(parts.year);
    const birthMonth = Number(parts.month);
    const birthDay = Number(parts.day);
    let age = referenceDate.getFullYear() - birthYear;
    const beforeBirthday =
      referenceDate.getMonth() + 1 < birthMonth ||
      (referenceDate.getMonth() + 1 === birthMonth &&
        referenceDate.getDate() < birthDay);
    if (beforeBirthday) age -= 1;
    return age >= 0 && age <= 130 ? String(age) : "";
  }

  const api = Object.freeze({
    asDigits,
    toKatakana,
    toHiragana,
    postalCode,
    phoneParts,
    birthDateParts,
    ageFromBirthDate,
  });
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.Normalization = api;

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
