(function initializeRedaction(root) {
  "use strict";

  function maskValue(fieldType, value) {
    const text = String(value || "");
    if (!text) return "";

    if (fieldType === "email" && text.includes("@")) {
      const [local, domain] = text.split("@", 2);
      return `${local.slice(0, 1) || "*"}***@${domain}`;
    }
    if (fieldType === "phone") {
      const digits = text.replace(/\D/g, "");
      return `***-***-${digits.slice(-4).padStart(4, "*")}`;
    }
    if (fieldType === "postal_code") {
      const digits = text.replace(/\D/g, "");
      return `***-${digits.slice(-4).padStart(4, "*")}`;
    }
    if (["prefecture", "city", "street", "building"].includes(fieldType)) {
      return `設定済み（${text.length}文字）`;
    }
    if (fieldType === "birth_date") {
      return "****-**-**";
    }
    if (fieldType === "gender") {
      return text ? "設定済み" : "";
    }
    if (fieldType === "free_text") {
      return `入力候補あり（${text.length}文字）`;
    }
    return `${text.slice(0, 1)}***`;
  }

  const api = Object.freeze({ maskValue });
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.Redaction = api;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
