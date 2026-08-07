(function initializeFormFingerprint(root) {
  "use strict";

  function normalizeFieldLabel(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLowerCase()
      .replace(/[必須任意]/g, "")
      .replace(/[＊*:：]/g, "")
      .replace(/^お(?=名前|住所|電話|email|メール)/, "")
      .replace(/^ご(?=住所|意見|感想|要望)/, "")
      .replace(/[\s\u3000]+/g, "")
      .trim();
  }

  function stableHash(value) {
    const source = String(value || "");
    let hash = 0x811c9dc5;
    for (let index = 0; index < source.length; index += 1) {
      hash ^= source.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  function hashAttributes(field) {
    return stableHash(
      [field.name, field.id, field.autocomplete, field.inputType, field.tagName]
        .map((value) => String(value || "").normalize("NFKC").toLowerCase())
        .join("|")
    );
  }

  function hashLabel(field) {
    return stableHash(
      [normalizeFieldLabel(field.label), normalizeFieldLabel(field.ariaLabel)].join("|")
    );
  }

  function hashOptions(field) {
    const options = Array.isArray(field.selectOptions)
      ? field.selectOptions.map((value) => normalizeFieldLabel(value))
      : [];
    return stableHash(options.join("|"));
  }

  function descriptorFor(field) {
    return {
      path: String(field.path || ""),
      tagName: String(field.tagName || "").toLowerCase(),
      inputType: String(field.inputType || field.type || "").toLowerCase(),
      attributeHash: field.attributeHash || hashAttributes(field),
      labelHash: field.labelHash || hashLabel(field),
      optionShapeHash: field.optionShapeHash || hashOptions(field),
      required: Boolean(field.required),
      disabled: Boolean(field.disabled),
      readOnly: Boolean(field.readOnly),
    };
  }

  function computeFormFingerprint(input) {
    const descriptors = (input?.fields || []).map(descriptorFor);
    const exact = descriptors
      .map((descriptor) => JSON.stringify(descriptor))
      .join(";");
    const structure = descriptors
      .map(({labelHash, ...descriptor}) => JSON.stringify(descriptor))
      .join(";");
    return {
      fingerprint: stableHash(exact),
      structureFingerprint: stableHash(structure),
      fields: descriptors,
    };
  }

  const api = Object.freeze({
    computeFormFingerprint,
    descriptorFor,
    normalizeFieldLabel,
    stableHash,
  });
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.FormFingerprint = api;

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
