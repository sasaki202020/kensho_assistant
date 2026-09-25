(function initializeFieldMatcher(root) {
  "use strict";

  const SIGNALS = Object.freeze({
    full_name: ["full_name", "fullname", "氏名", "お名前", "名前"],
    last_name: ["family-name", "last_name", "lastname", "姓", "苗字", "名字"],
    first_name: ["given-name", "first_name", "firstname", "名"],
    full_name_kana: [
      "full_name_kana",
      "fullname_kana",
      "フリガナ",
      "ふりがな",
      "氏名カナ",
    ],
    last_name_kana: ["family-name-kana", "last_name_kana", "姓カナ", "セイ", "姓かな"],
    first_name_kana: ["given-name-kana", "first_name_kana", "名カナ", "メイ", "名かな"],
    email: ["email", "e-mail", "mail", "メールアドレス"],
    phone: ["tel", "phone", "telephone", "電話番号", "携帯番号"],
    postal_code: ["postal-code", "zipcode", "zip", "郵便番号"],
    prefecture: ["address-level1", "prefecture", "都道府県", "県名"],
    city: ["address-level2", "city", "市区町村"],
    street: ["address-line1", "street", "住所", "番地", "町名"],
    building: ["address-line2", "building", "建物名", "マンション"],
    birth_date: ["bday", "birth", "birthday", "生年月日"],
    birth_year: ["bday-year", "birth_year", "birthyear", "誕生年", "生年", "年"],
    birth_month: ["bday-month", "birth_month", "birthmonth", "誕生月", "生月", "月"],
    birth_day: ["bday-day", "birth_day", "birthday_day", "誕生日", "生日", "日"],
    age: ["age", "年齢", "年代"],
    gender: ["sex", "gender", "性別"],
    free_text: [
      "comment",
      "message",
      "opinion",
      "ご意見",
      "ご感想",
      "ご要望",
      "自由記入",
      "紙面の感想",
      "コメント",
    ],
  });

  const FORBIDDEN = [
    "password",
    "passcode",
    "otp",
    "認証コード",
    "利用規約",
    "プライバシー",
    "同意",
    "メルマガ",
    "newsletter",
    "captcha",
    "保護者",
    "ハンドル",
    "ニックネーム",
    "賞品",
    "プレゼント",
    "景品",
    "応募理由",
    "ご意見",
    "ご感想",
    "ご要望",
    "コメント",
    "アンケート",
  ];

  const AUTOCOMPLETE_FIELDS = Object.freeze({
    name: "full_name", "family-name": "last_name", "given-name": "first_name",
    email: "email", tel: "phone", "postal-code": "postal_code",
    "address-level1": "prefecture", "address-level2": "city",
    "address-line1": "street", "address-line2": "building",
    bday: "birth_date", "bday-year": "birth_year", "bday-month": "birth_month",
    "bday-day": "birth_day", sex: "gender",
  });

  function autocompleteField(value) {
    const tokens = String(value || "").trim().toLowerCase().split(/\s+/);
    if (tokens[0]?.startsWith("section-")) tokens.shift();
    if (["shipping", "billing"].includes(tokens[0])) tokens.shift();
    if (["home", "work", "mobile", "fax", "pager"].includes(tokens[0])) tokens.shift();
    if (tokens[tokens.length - 1] === "webauthn") tokens.pop();
    return tokens.length === 1 ? AUTOCOMPLETE_FIELDS[tokens[0]] : undefined;
  }

  function normalized(metadata) {
    return [
      metadata.type,
      metadata.name,
      metadata.id,
      metadata.autocomplete,
      metadata.ariaLabel,
      metadata.placeholder,
      metadata.label,
      metadata.groupLabel,
      metadata.surroundingText,
      ...(metadata.selectOptions || []),
    ]
      .map((value) => String(value || "").toLowerCase())
      .join(" ");
  }

  function scoreField(fieldType, metadata, haystack) {
    let score = 0;
    const reasons = [];
    const autocomplete = String(metadata.autocomplete || "").toLowerCase();
    const type = String(metadata.type || "").toLowerCase();
    const label = String(metadata.label || "").toLowerCase().replace(/[\s:：*＊必須]/g, "");
    const ariaLabel = String(metadata.ariaLabel || "")
      .toLowerCase()
      .replace(/[\s:：*＊必須]/g, "");
    const placeholder = String(metadata.placeholder || "")
      .toLowerCase()
      .replace(/[\s:：*＊必須]/g, "");
    const name = String(metadata.name || "").toLowerCase().replace(/[\s:：*＊必須]/g, "");
    const groupLabel = String(metadata.groupLabel || "")
      .toLowerCase()
      .replace(/[\s:：*＊必須]/g, "");
    const identityText = [metadata.name, metadata.id, metadata.autocomplete]
      .map((value) => String(value || "").toLowerCase())
      .join(" ");

    for (const signal of SIGNALS[fieldType]) {
      const normalizedSignal = signal.toLowerCase();
      if (!haystack.includes(normalizedSignal)) continue;
      score += 0.18;
      reasons.push(signal);
      const compactSignal = normalizedSignal.replace(/[\s:：*＊必須]/g, "");
      if (label === compactSignal) {
        score = Math.max(score, 0.97);
        reasons.push("exact_label");
      }
      if (ariaLabel === compactSignal) {
        score = Math.max(score, 0.97);
        reasons.push("exact_aria_label");
      }
      if (placeholder === compactSignal) {
        score = Math.max(score, 0.74);
        reasons.push("placeholder_only_review");
      }
      if (name === compactSignal) {
        score = Math.max(score, 0.78);
        reasons.push("exact_name_review");
      }
      if (groupLabel === compactSignal) {
        const samePurposeIdentity = identityText.includes(normalizedSignal);
        score = Math.max(
          score,
          Number(metadata.groupControlCount || 0) === 1 || samePurposeIdentity ? 0.97 : 0.7
        );
        reasons.push(
          Number(metadata.groupControlCount || 0) === 1 || samePurposeIdentity
            ? "table_group_label"
            : "table_group_label_review"
        );
      }
    }
    const autocompleteMatches = autocompleteField(autocomplete) === fieldType;
    if (autocomplete && autocompleteMatches) {
      score = Math.max(score, 0.99);
      reasons.push("autocomplete");
    }
    if (fieldType === "email" && type === "email") {
      score += 0.58;
      reasons.push("input_type");
    }
    if (fieldType === "phone" && type === "tel") {
      score += 0.58;
      reasons.push("input_type");
    }
    if (fieldType === "birth_date" && type === "date") {
      score += 0.4;
      reasons.push("input_type");
    }
    const rawName = String(metadata.name || "").toLowerCase();
    if (fieldType === "phone" && /(?:tel|phone)[-_]?[123]$/.test(rawName)) {
      score += 0.4;
      reasons.push("split_phone_name");
    }
    if (
      fieldType === "postal_code" &&
      /(?:(?:zip|postal)[-_]?[12]|郵便番号[-_]?[12])$/.test(rawName)
    ) {
      score += 0.6;
      reasons.push("split_postal_name");
    }
    const selectOptions = (metadata.selectOptions || []).map((value) =>
      String(value || "").toLowerCase()
    );
    if (
      fieldType === "prefecture" &&
      ["東京都", "大阪府", "福岡県", "北海道"].filter((value) =>
        selectOptions.some((option) => option.includes(value.toLowerCase()))
      ).length >= 2
    ) {
      score += 0.72;
      reasons.push("select_options");
    }
    if (
      fieldType === "gender" &&
      ["男性", "女性"].every((value) =>
        selectOptions.some((option) => option.includes(value))
      )
    ) {
      score = Math.max(score, 0.97);
      reasons.push("select_options");
    }
    const supportedEvidence = reasons.some((reason) => [
      "exact_label", "exact_aria_label", "exact_name_review", "autocomplete",
      "table_group_label", "input_type", "split_phone_name", "split_postal_name",
      "select_options",
    ].includes(reason));
    return { score: Math.min(score, supportedEvidence ? 0.99 : 0.74), reasons };
  }

  function matchField(metadata) {
    const haystack = normalized(metadata);
    const safetyHaystack = [
      metadata.type,
      metadata.name,
      metadata.id,
      metadata.autocomplete,
      metadata.ariaLabel,
      metadata.placeholder,
      metadata.label,
      metadata.groupLabel,
      ...(metadata.selectOptions || []),
    ]
      .map((value) => String(value || "").toLowerCase())
      .join(" ");
    if (FORBIDDEN.some((term) => safetyHaystack.includes(term))) {
      return { fieldType: "unknown", confidence: 0, reasons: ["forbidden"] };
    }

    const candidates = [];
    for (const fieldType of Object.keys(SIGNALS)) {
      const result = scoreField(fieldType, metadata, haystack);
      candidates.push({
        fieldType,
        confidence: Number(result.score.toFixed(2)),
        reasons: result.reasons,
      });
    }
    candidates.sort((left, right) => right.confidence - left.confidence);
    const best = candidates[0] || {fieldType: "unknown", confidence: 0, reasons: []};
    if (best.confidence < 0.35) {
      return { fieldType: "unknown", confidence: best.confidence, reasons: [] };
    }
    const second = candidates[1];
    if (
      second &&
      best.confidence >= 0.75 &&
      Math.abs(best.confidence - second.confidence) < 0.05
    ) {
      return {
        fieldType: "unknown",
        confidence: best.confidence,
        reasons: ["ambiguous_mapping", best.fieldType, second.fieldType],
      };
    }
    return best;
  }

  const api = Object.freeze({ matchField, SIGNALS, FORBIDDEN });
  root.KenshoExtension = root.KenshoExtension || {};
  root.KenshoExtension.FieldMatcher = api;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
