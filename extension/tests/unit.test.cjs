const test = require("node:test");
const assert = require("node:assert/strict");

function reviewControl({type = "text", label = "項目", value = "", required = true,
  checked = false, name = "", style = null, disabled = false, readOnly = false} = {}) {
  const attributes = new Map(style === null ? [] : [["style", style]]);
  const labelNode = {cloneNode: () => ({textContent: label, querySelectorAll: () => []})};
  return {type, labels: [labelNode], value, required, checked, name, disabled, readOnly,
    getAttribute: key => attributes.get(key) ?? null,
    setAttribute: (key, val) => attributes.set(key, val),
    removeAttribute: key => attributes.delete(key),
    matches: () => false, closest: () => null,
    style: {setProperty: (key, val, priority) =>
      attributes.set("style", `${attributes.get("style") || ""};${key}:${val}!${priority}`)},
  };
}

test("pre-submit filled rows use existing masks and contain no raw values", () => {
  const {maskedFilled} = require("../content/overlay.js");
  const {maskValue} = require("../shared/redaction.js");
  const controls = {
    email: reviewControl({label: "メール", value: "review-sentinel@example.invalid"}),
    name: reviewControl({label: "氏名", value: "LOCAL-REVIEW-SENTINEL"}),
    birthday: reviewControl({value: "2000-01-01"}),
  };
  const items = Object.keys(controls).map(fieldId => ({fieldId, fieldType: fieldId}));
  const rows = maskedFilled(items, ["email", "name"], id => controls[id], maskValue);
  assert.deepEqual(rows, [
    {label: "メール", maskedValue: maskValue("email", controls.email.value)},
    {label: "氏名", maskedValue: maskValue("name", controls.name.value)},
  ]);
  for (const control of Object.values(controls)) assert.ok(!JSON.stringify(rows).includes(control.value));
});

test("required extraction handles radio groups, consent, survey, select and birthdays without values", () => {
  const {missingRequired} = require("../content/overlay.js");
  const controls = [
    reviewControl({label: "クイズ", type: "radio", name: "quiz", value: "SECRET-OPTION"}),
    reviewControl({type: "radio", name: "quiz", required: false}),
    reviewControl({label: "同意", type: "checkbox", value: "SECRET-CONSENT"}),
    reviewControl({label: "アンケート"}),
    reviewControl({label: "メルマガ", type: "select-one"}),
    reviewControl({label: "生年月日", type: "date"}),
    reviewControl({required: false}), reviewControl({value: "FILLED-SENTINEL"}),
    reviewControl({type: "hidden"}), reviewControl({disabled: true}), reviewControl({readOnly: true}),
  ];
  const missing = missingRequired({elements: controls});
  assert.deepEqual(missing.map(row => row.label), ["クイズ", "同意", "アンケート", "メルマガ", "生年月日"]);
  assert.equal(missing[0].elements.length, 2);
  assert.ok(missing.every(row => Object.keys(row).sort().join() === "elements,label"));
  controls[1].checked = true;
  controls[2].checked = true;
  assert.deepEqual(missingRequired({elements: controls}).map(row => row.label), ["アンケート", "メルマガ", "生年月日"]);
  controls[1].name = "other-quiz";
  assert.equal(missingRequired({elements: controls})[0].label, "クイズ");
});

test("highlight cleanup restores exact absent, empty and important inline styles and never values", () => {
  const {createHighlights} = require("../content/overlay.js");
  const controls = [null, "", "color:red;outline:1px dotted blue!important"].map(style =>
    reviewControl({style, value: "UNCHANGED-SENTINEL"}));
  const originals = controls.map(control => control.getAttribute("style"));
  const entries = [{elements: controls}];
  const highlights = createHighlights();
  highlights.apply(entries);
  highlights.apply(entries);
  for (const control of controls) assert.ok(control.getAttribute("style").includes("3px solid #c77600"));
  highlights.clear();
  highlights.clear();
  assert.deepEqual(controls.map(control => control.getAttribute("style")), originals);
  assert.ok(controls.every(control => control.value === "UNCHANGED-SENTINEL"));
});

test("terms list excludes script URLs and query credentials and opens nothing", () => {
  const {termsLinks} = require("../content/overlay.js");
  const links = [
    ["規約", "/terms"], ["応募要項", "#requirements"], ["プライバシー", "javascript:alert(1)"],
    ["注意事項", "/terms?token=SECRET"], ["通常リンク", "/other"],
  ].map(([label, href]) => ({...reviewControl({label}), cloneNode: () =>
    ({textContent: label, querySelectorAll: () => []}), getAttribute: () => href}));
  assert.deepEqual(termsLinks({baseURI: "http://127.0.0.1/form", querySelectorAll: () => links}), [
    {label: "規約", href: "http://127.0.0.1/terms"},
    {label: "応募要項", href: "http://127.0.0.1/form#requirements"},
    {label: "注意事項", href: null},
  ]);
});

test("highlight cleanup also removes Chromium's lazily serialized empty style attribute", () => {
  const {createHighlights} = require("../content/overlay.js");
  const element = reviewControl();
  const remove = element.removeAttribute;
  let pending = true;
  element.removeAttribute = key => {
    if (pending) {element.setAttribute(key, ""); pending = false;}
    else remove(key);
  };
  const highlights = createHighlights();
  highlights.apply([{elements: [element]}]);
  highlights.clear();
  assert.equal(element.getAttribute("style"), null);
});

test("overlay capability keys include only approved fillable mappings", () => {
  const fs = require("node:fs");
  const vm = require("node:vm");
  const source = fs.readFileSync(require.resolve("../content/overlay.js"), "utf8");
  const fn = source.slice(source.indexOf("  function confirmedProfileKeys()"),
    source.indexOf("  function mappingPreviewProfile()"));
  const fields = [
    {fieldId: "name", fieldType: "full_name", confidence: 1},
    {fieldId: "kana", fieldType: "full_name_kana", confidence: 1},
    {fieldId: "mail", fieldType: "email", confidence: 1},
    {fieldId: "phone", fieldType: "phone", confidence: 1},
    {fieldId: "birthday", fieldType: "birth_date", confidence: 1},
    {fieldId: "radio", fieldType: "gender", type: "radio", confidence: 1},
  ];
  const mappingDecisions = {name: {action: "approve"}, kana: {action: "approve"},
    phone: {action: "skip"}, radio: {action: "approve"}};
  const {previewMasked} = require("../content/form-filler.js");
  const masked = {last_name: "***", first_name: "***", last_name_kana: "***",
    first_name_kana: "***", email: "***", phone: "***", birth_date: "***", gender: "***"};
  for (const templateApproved of [false, true]) {
    const previewResult = previewMasked({fields}, masked, {templateApproved, mappingDecisions});
    const keys = vm.runInNewContext(fn + "confirmedProfileKeys()", {previewResult, mappingDecisions});
    assert.deepEqual(Array.from(keys), ["last_name", "first_name", "last_name_kana", "first_name_kana"]);
  }
  const legacy = previewMasked({fields}, masked);
  assert.equal(legacy.items.find(item => item.fieldId === "mail").fillAllowed, true);
  assert.equal(legacy.templateApproved, true);
});

test("autocomplete tokens distinguish full names, split birthdays and unsupported parts", () => {
  const {matchField} = require("../content/field-matcher.js");
  for (const [autocomplete, expected] of [
    ["section-entry shipping name", "full_name"],
    ["section-entry bday-year", "birth_year"],
    ["section-entry bday-month", "birth_month"],
    ["section-entry bday-day", "birth_day"],
  ]) {
    const result = matchField({type: "text", autocomplete});
    assert.equal(result.fieldType, expected);
    assert.ok(result.confidence >= 0.95);
  }
  const partial = matchField({type: "text", autocomplete: "tel-national"});
  assert.ok(partial.confidence < 0.75);
});

test("placeholder synonyms alone never authorize a mapping", () => {
  const {matchField} = require("../content/field-matcher.js");
  const result = matchField({type: "text", placeholder: "address-line1 street 住所 番地 町名"});
  assert.ok(result.confidence < 0.75);
});

test("extension identity messages are stable and PII-free", () => {
  const messages = require("../shared/messages.js");
  delete global.chrome;
  delete require.cache[require.resolve("../service-worker.js")];
  const {isDuplicateExtensionIdentity} = require("../service-worker.js");

  assert.equal(messages.GET_EXTENSION_ID, "GET_EXTENSION_ID");
  assert.equal(messages.EXTENSION_INSTANCE_HELLO, "EXTENSION_INSTANCE_HELLO");
  assert.equal(messages.DUPLICATE_EXTENSION_BLOCKED, "DUPLICATE_EXTENSION_BLOCKED");
  assert.equal(
    isDuplicateExtensionIdentity(
      {extensionId: "new-id", version: "0.2.0"},
      {extensionId: "new-id", version: "0.2.0"}
    ),
    false
  );
  assert.equal(
    isDuplicateExtensionIdentity(
      {extensionId: "new-id", version: "0.2.0"},
      {extensionId: "old-id", version: "0.2.0"}
    ),
    true
  );
});

test("field matcher favors autocomplete and rejects ambiguous fields", () => {
  const { matchField } = require("../content/field-matcher.js");

  const email = matchField({
    type: "email",
    autocomplete: "email",
    name: "contact",
    id: "",
    label: "連絡先",
    placeholder: "",
    ariaLabel: "",
    surroundingText: "",
    tagName: "input",
  });
  const unknown = matchField({
    type: "text",
    autocomplete: "",
    name: "answer",
    id: "answer",
    label: "回答",
    placeholder: "",
    ariaLabel: "",
    surroundingText: "",
    tagName: "input",
  });

  assert.equal(email.fieldType, "email");
  assert.ok(email.confidence >= 0.9);
  assert.equal(unknown.fieldType, "unknown");
  assert.ok(unknown.confidence < 0.75);
});

test("field matcher distinguishes split names and kana labels", () => {
  const { matchField } = require("../content/field-matcher.js");
  const base = {
    type: "text",
    autocomplete: "",
    id: "",
    placeholder: "",
    ariaLabel: "",
    surroundingText: "",
    tagName: "input",
  };

  assert.equal(matchField({...base, name: "sei", label: "姓"}).fieldType, "last_name");
  assert.equal(matchField({...base, name: "mei", label: "名"}).fieldType, "first_name");
  assert.equal(
    matchField({...base, name: "sei_kana", label: "姓カナ"}).fieldType,
    "last_name_kana"
  );
  assert.equal(
    matchField({...base, name: "mei_kana", label: "名カナ"}).fieldType,
    "first_name_kana"
  );
});

test("field matcher recognizes strong combined Japanese identity fields", () => {
  const { matchField } = require("../content/field-matcher.js");
  const base = {
    type: "text",
    autocomplete: "",
    name: "",
    id: "",
    placeholder: "",
    ariaLabel: "",
    surroundingText: "",
    selectOptions: [],
    tagName: "input",
  };

  const fullName = matchField({...base, autocomplete: "name", label: "お名前 必須"});
  const fullKana = matchField({...base, id: "kana", label: "フリガナ"});
  const age = matchField({...base, id: "age", label: "年齢 必須"});
  const email = matchField({...base, id: "email", label: "メールアドレス"});

  assert.deepEqual(
    [fullName.fieldType, fullKana.fieldType, age.fieldType, email.fieldType],
    ["full_name", "full_name_kana", "age", "email"]
  );
  assert.ok([fullName, fullKana, age, email].every((item) => item.confidence >= 0.95));
});

test("field matcher uses select options for prefecture and gender", () => {
  const { matchField } = require("../content/field-matcher.js");
  const base = {
    type: "select-one",
    autocomplete: "",
    name: "choice",
    id: "",
    label: "",
    placeholder: "",
    ariaLabel: "",
    surroundingText: "",
    tagName: "select",
  };

  assert.equal(
    matchField({
      ...base,
      selectOptions: ["選択してください", "東京都", "大阪府", "福岡県"],
    }).fieldType,
    "prefecture"
  );
  assert.equal(
    matchField({...base, selectOptions: ["選択してください", "男性", "女性"]}).fieldType,
    "gender"
  );
});

test("redaction never returns the complete source value", () => {
  const { maskValue } = require("../shared/redaction.js");

  assert.equal(maskValue("email", "guest@example.com"), "g***@example.com");
  assert.equal(maskValue("phone", "09012345678"), "***-***-5678");
  assert.notEqual(maskValue("address", "福岡県北九州市小倉北区"), "福岡県北九州市小倉北区");
  assert.equal(maskValue("prefecture", "福岡県"), "設定済み（3文字）");
});

test("forgetting an activated tab clears its session profile", async () => {
  const values = {
    kenshoActiveTabs: [42],
    kenshoSessionProfile: {email: "pii-test@example.invalid"},
  };
  global.chrome = {
    storage: {
      session: {
        get: async (key) => ({[key]: values[key]}),
        set: async (next) => Object.assign(values, next),
        remove: async (key) => delete values[key],
      },
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const { forgetActiveTab } = require("../service-worker.js");

  await forgetActiveTab(42);

  assert.deepEqual(values.kenshoActiveTabs, []);
  assert.equal(values.kenshoSessionProfile, undefined);
  delete global.chrome;
});

test("service worker storage policy only allows session storage", () => {
  const { validateProfile, SESSION_PROFILE_KEY } = require("../service-worker.js");

  assert.equal(SESSION_PROFILE_KEY, "kenshoSessionProfile");
  assert.deepEqual(validateProfile({ email: "test@example.invalid" }), {
    email: "test@example.invalid",
  });
  assert.throws(() => validateProfile({ password: "secret" }), /forbidden/);
});

test("service worker injects the guard in every frame before the overlay", async () => {
  const calls = [];
  global.chrome = {
    scripting: {
      executeScript: async (request) => calls.push(request),
    },
  };
  const { injectIntoTab } = require("../service-worker.js");

  await injectIntoTab(42);

  assert.equal(calls.length, 2);
  assert.equal(calls[0].world, "MAIN");
  assert.equal(calls[0].target.allFrames, false);
  assert.deepEqual(calls[0].files, ["content/submit-guard.js"]);
  assert.equal(calls[1].world, "ISOLATED");
  assert.ok(calls[1].files.includes("content/isolated-guard.js"));
  assert.ok(calls[1].files.includes("content/overlay.js"));
  delete global.chrome;
});

test("approved origin includes a MAIN guard at document_start", async () => {
  const registrations = [];
  global.chrome = {
    scripting: {
      getRegisteredContentScripts: async () => [],
      registerContentScripts: async (scripts) => registrations.push(...scripts),
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const { registerOriginGuard } = require("../service-worker.js");

  await registerOriginGuard("https://example.invalid/*");

  const main = registrations.find((item) => item.world === "MAIN");
  assert.equal(registrations.length, 2);
  assert.equal(main.runAt, "document_start");
  assert.equal(main.allFrames, false);
  assert.deepEqual(main.matches, ["https://example.invalid/*"]);
  delete global.chrome;
});

test("approved origin registers persistent MAIN and ISOLATED scripts once", async () => {
  const registrations = [];
  global.chrome = {
    scripting: {
      getRegisteredContentScripts: async () => [],
      registerContentScripts: async (scripts) => registrations.push(...scripts),
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const { registerOriginScripts } = require("../service-worker.js");

  await registerOriginScripts("https://example.invalid/*");

  assert.equal(registrations.length, 2);
  const main = registrations.find((item) => item.world === "MAIN");
  const isolated = registrations.find((item) => item.world === "ISOLATED");
  assert.equal(main.runAt, "document_start");
  assert.equal(main.persistAcrossSessions, true);
  assert.equal(main.allFrames, false);
  assert.deepEqual(main.js, ["content/submit-guard.js"]);
  assert.equal(isolated.runAt, "document_idle");
  assert.equal(isolated.persistAcrossSessions, true);
  assert.equal(isolated.allFrames, false);
  assert.ok(isolated.js.includes("content/overlay.js"));
  assert.notEqual(main.id, isolated.id);
  delete global.chrome;
});

test("registration reconciliation restores missing scripts and removes stale scripts", async () => {
  const registrations = [];
  const removals = [];
  global.chrome = {
    permissions: {
      getAll: async () => ({origins: ["https://allowed.invalid/*"]}),
    },
    scripting: {
      getRegisteredContentScripts: async (query) =>
        query?.ids
          ? []
          : [
              {
                id: "kensho-main-stale",
                matches: ["https://stale.invalid/*"],
              },
            ],
      registerContentScripts: async (scripts) => registrations.push(...scripts),
      unregisterContentScripts: async ({ids}) => removals.push(...ids),
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const { reconcileOriginScripts } = require("../service-worker.js");

  await reconcileOriginScripts();

  assert.equal(registrations.length, 2);
  assert.deepEqual(removals, ["kensho-main-stale"]);
  delete global.chrome;
});

test("disabling an origin unregisters both scripts before removing permission", async () => {
  const actions = [];
  delete global.chrome;
  delete require.cache[require.resolve("../service-worker.js")];
  const { disableOrigin } = require("../service-worker.js");
  global.chrome = {
    runtime: {getManifest: () => ({version_name: "production"})},
    storage: {
      session: {
        get: async (key) => ({
          [key]: key === "kenshoControlCapability"
            ? {session_id: "session-1", token: "control-token", tab_id: 7, document_id: "doc-1"}
            : null,
        }),
        remove: async (key) => actions.push(`storage:${key}`),
      },
    },
    scripting: {
      unregisterContentScripts: async ({ids}) =>
        actions.push(`scripts:${ids.sort().join(",")}`),
    },
    permissions: {
      remove: async ({origins}) => {
        actions.push(`permission:${origins[0]}`);
        return true;
      },
    },
  };
  global.fetch = async (url) => {
    if (String(url).endsWith("/api/session/status")) {
      return {ok: true, json: async () => ({session_id: "session-1"})};
    }
    actions.push("server:revoke");
    return {ok: true, json: async () => ({ok: true, revoked_count: 1})};
  };
  const result = await disableOrigin(
    "https://example.invalid/apply?secret=1",
    {tab: {id: 7}, documentId: "doc-1"}
  );

  assert.equal(result.removed, true);
  assert.equal(actions[0], "server:revoke");
  assert.match(actions[1], /^scripts:/);
  assert.equal(actions[2], "permission:https://example.invalid/*");
  assert.equal(actions[3], "storage:kenshoSessionProfile");
  delete global.fetch;
  delete global.chrome;
});

test("origin permission patterns are exact and non-web schemes are rejected", () => {
  delete global.chrome;
  delete require.cache[require.resolve("../service-worker.js")];
  const { originPatternForUrl } = require("../service-worker.js");

  assert.equal(
    originPatternForUrl("https://example.invalid/apply?secret=1"),
    "https://example.invalid/*"
  );
  assert.equal(originPatternForUrl("file:///C:/fixture/form.html"), null);
  assert.equal(originPatternForUrl("chrome://extensions"), null);
});

test("script IDs depend only on the normalized origin", () => {
  delete global.chrome;
  delete require.cache[require.resolve("../service-worker.js")];
  const { scriptIdsForOrigin, originPatternForUrl } =
    require("../service-worker.js");

  const first = scriptIdsForOrigin(
    originPatternForUrl("https://example.invalid/a?email=one@example.invalid")
  );
  const second = scriptIdsForOrigin(
    originPatternForUrl("https://example.invalid/b#private")
  );

  assert.deepEqual(first, second);
  assert.match(first.main, /^kensho-main-[a-f0-9]{8}$/);
  assert.match(first.isolated, /^kensho-isolated-[a-f0-9]{8}$/);
});

test("origin access is requested only for the exact sender origin", async () => {
  const requested = [];
  const registrations = [];
  global.chrome = {
    permissions: {
      request: async ({origins}) => {
        requested.push(...origins);
        return true;
      },
    },
    scripting: {
      getRegisteredContentScripts: async () => [],
      registerContentScripts: async (scripts) => registrations.push(...scripts),
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const { requestOriginAccess } = require("../service-worker.js");

  const result = await requestOriginAccess(
    "https://example.invalid/apply?email=pii@example.invalid#secret"
  );

  assert.equal(result.granted, true);
  assert.deepEqual(requested, ["https://example.invalid/*"]);
  assert.equal(registrations.length, 2);
  assert.equal(JSON.stringify({requested, registrations}).includes("pii@"), false);
  delete global.chrome;
});

test("denied or unsupported origin access never registers scripts", async () => {
  let registrationCount = 0;
  let requestCount = 0;
  global.chrome = {
    permissions: {
      request: async () => {
        requestCount += 1;
        return false;
      },
    },
    scripting: {
      getRegisteredContentScripts: async () => [],
      registerContentScripts: async () => {
        registrationCount += 1;
      },
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const { requestOriginAccess } = require("../service-worker.js");

  const denied = await requestOriginAccess("https://denied.invalid/form");
  const unsupported = await requestOriginAccess("file:///C:/private/form.html");

  assert.equal(denied.granted, false);
  assert.equal(unsupported.granted, false);
  assert.equal(requestCount, 1);
  assert.equal(registrationCount, 0);
  delete global.chrome;
});

test("toolbar bootstrap injects temporary UI without requesting origin permission", async () => {
  let actionListener = null;
  let permissionRequests = 0;
  const injections = [];
  const values = {};
  const event = {addListener: () => {}};
  global.chrome = {
    runtime: {
      onInstalled: event,
      onStartup: event,
      onMessage: event,
    },
    action: {
      onClicked: {
        addListener: (listener) => {
          actionListener = listener;
        },
      },
    },
    tabs: {
      onUpdated: event,
      onRemoved: event,
    },
    permissions: {
      getAll: async () => ({origins: []}),
      request: async () => {
        permissionRequests += 1;
        return true;
      },
    },
    scripting: {
      getRegisteredContentScripts: async () => [],
      executeScript: async (request) => injections.push(request),
    },
    storage: {
      session: {
        get: async (key) => ({[key]: values[key]}),
        set: async (next) => Object.assign(values, next),
        setAccessLevel: async () => {},
      },
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  require("../service-worker.js");

  await actionListener({id: 42, url: "https://example.invalid/form"});

  assert.equal(permissionRequests, 0);
  assert.equal(injections.length, 2);
  delete global.chrome;
});

test("profile remains reusable only in trusted session storage", async () => {
  const values = {
    kenshoSessionProfile: {
      email: "pii-test@example.invalid",
      phone: "09012345678",
    },
  };
  global.chrome = {
    storage: {
      session: {
        get: async (key) => ({[key]: values[key]}),
        remove: async (key) => delete values[key],
      },
    },
  };
  global.KenshoExtension = {
    Redaction: require("../shared/redaction.js"),
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const { profilePreview, consumeProfile } = require("../service-worker.js");

  const preview = await profilePreview();
  const consumed = await consumeProfile();
  const second = await consumeProfile();

  assert.equal(preview.email, "p***@example.invalid");
  assert.equal(preview.phone, "***-***-5678");
  assert.deepEqual(consumed, {
    email: "pii-test@example.invalid",
    phone: "09012345678",
  });
  assert.deepEqual(second, consumed);
  delete global.chrome;
  delete global.KenshoExtension;
});

test("worker epoch changes after service worker restart", () => {
  delete global.chrome;
  delete require.cache[require.resolve("../service-worker.js")];
  const first = require("../service-worker.js").WORKER_EPOCH;
  delete require.cache[require.resolve("../service-worker.js")];
  const second = require("../service-worker.js").WORKER_EPOCH;

  assert.notEqual(first, second);
});

test("bridge capability requests include only confirmed profile keys", async () => {
  delete global.chrome;
  delete require.cache[require.resolve("../service-worker.js")];
  const {requestBridgeCapability} = require("../service-worker.js");
  const stored = {};
  let capabilityBody = null;
  global.chrome = {
    runtime: {id: "extension-id"},
    storage: {
      session: {
        set: async (value) => Object.assign(stored, value),
        get: async (key) => ({
          [key]: key === "kenshoControlCapability"
            ? {session_id: "session-1", token: "fixture-control-token", tab_id: 7, document_id: "doc-1"}
            : stored[key],
        }),
      },
    },
  };
  global.fetch = async (url, options = {}) => {
    if (String(url).endsWith("/api/session/status")) {
      return {
        ok: true,
        json: async () => ({
          session_id: "session-1",
          active_candidate_id: "candidate-1",
        }),
      };
    }
    capabilityBody = JSON.parse(options.body);
    return {
      ok: true,
      json: async () => ({
        token: "one-shot-token",
        host: "127.0.0.1",
        port: 45678,
        origin: "https://example.invalid",
        session_id: "session-1",
        candidate_id: "candidate-1",
        fingerprint: "fingerprint-1",
      }),
    };
  };

  await requestBridgeCapability(
    {url: "https://example.invalid/apply", tab: {id: 7}, documentId: "doc-1"},
    "fingerprint-1",
    ["email", "postal_code"]
  );

  assert.deepEqual(capabilityBody.profile_keys, ["email", "postal_code"]);
  assert.equal(capabilityBody.control_token, "fixture-control-token");
  assert.equal(JSON.stringify(capabilityBody).includes("phone"), false);
  delete global.fetch;
  delete global.chrome;
});

test("bridge allowlist excludes free text and other manual-only fields", () => {
  delete global.chrome;
  delete require.cache[require.resolve("../service-worker.js")];
  const {ALLOWED_PROFILE_KEYS} = require("../service-worker.js");

  assert.equal(ALLOWED_PROFILE_KEYS.has("free_text"), false);
  assert.equal(ALLOWED_PROFILE_KEYS.has("consent"), false);
  assert.equal(ALLOWED_PROFILE_KEYS.has("manual_review"), false);
});

test("production overlay has no legacy session-profile fallback", () => {
  const fs = require("node:fs");
  const overlaySource = fs.readFileSync(
    require.resolve("../content/overlay.js"),
    "utf8"
  );

  assert.equal(overlaySource.includes("CONSUME_SESSION_PROFILE"), false);
  assert.match(overlaySource, /bridge[^\n]*\u5b89\u5168\u505c\u6b62|bridge[^\n]*fail/i);
});

test("legacy session-profile messages are unavailable in the production worker", () => {
  const fs = require("node:fs");
  const workerSource = fs.readFileSync(require.resolve("../service-worker.js"), "utf8");

  assert.equal(workerSource.includes('message?.type === "SET_SESSION_PROFILE"'), false);
  assert.equal(workerSource.includes('message?.type === "CONSUME_SESSION_PROFILE"'), false);
});

test("mapping preview is PII-free and does not read a legacy profile", () => {
  const fs = require("node:fs");
  const workerSource = fs.readFileSync(require.resolve("../service-worker.js"), "utf8");
  const overlaySource = fs.readFileSync(
    require.resolve("../content/overlay.js"),
    "utf8"
  );

  assert.equal(workerSource.includes('message?.type === "GET_PROFILE_PREVIEW"'), false);
  assert.equal(overlaySource.includes('type: "GET_PROFILE_PREVIEW"'), false);
  assert.match(overlaySource, /function mappingPreviewProfile\(\)/);
});

test("verified fill reports only PII-free progress through the service worker", async () => {
  const requests = [];
  const stored = {
    kenshoControlCapability: {
      session_id: "session-1",
      token: "fixture-control-token",
      tab_id: 7,
      document_id: "doc-1",
    },
    kenshoProgressCapability: {
      token: "fixture-progress-token",
      session_id: "session-1",
      candidate_id: "candidate-1",
      origin: "https://example.invalid",
      fingerprint: "fingerprint-1",
    },
  };
  global.chrome = {
    storage: {
      session: {
        get: async (key) => ({[key]: stored[key]}),
        set: async (value) => Object.assign(stored, value),
        remove: async (key) => { delete stored[key]; },
      },
    },
  };
  global.fetch = async (url, options = {}) => {
    requests.push({url, options});
    if (String(url).endsWith("/api/session/status")) {
      return {
        ok: true,
        json: async () => ({session_id: "session-1", active_candidate_id: "candidate-1"}),
      };
    }
    return {
      ok: true,
      json: async () => ({
        ok: true,
        workflow_state: "HUMAN_ACTION_REQUIRED",
        progress_token: "rollback-progress-token",
      }),
    };
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const {reportExtensionProgress} = require("../service-worker.js");

  const result = await reportExtensionProgress(
    {url: "https://example.invalid/apply", tab: {id: 7}, documentId: "doc-1"},
    "fingerprint-1",
    "post_fill_verified",
    {filled_count: 3, unrelated_changed_count: 0}
  );

  assert.equal(result.workflow_state, "HUMAN_ACTION_REQUIRED");
  const body = JSON.parse(requests[1].options.body);
  assert.deepEqual(body.details, {filled_count: 3, unrelated_changed_count: 0});
  assert.equal(body.control_token, "fixture-control-token");
  assert.equal(body.progress_token, "fixture-progress-token");
  assert.equal(stored.kenshoProgressCapability.token, "rollback-progress-token");
  assert.equal(JSON.stringify(body).includes("example@example"), false);
  delete global.fetch;
  delete global.chrome;
});

test("overlay requires a confirmed template before requesting bridge PII", () => {
  const fs = require("node:fs");
  const source = fs.readFileSync(require.resolve("../content/overlay.js"), "utf8");
  const guardIndex = source.indexOf('templateState !== "matched"');
  const requestIndex = source.indexOf('type: "REQUEST_BRIDGE_CAPABILITY"');

  assert.notEqual(guardIndex, -1);
  assert.notEqual(requestIndex, -1);
  assert.ok(guardIndex < requestIndex);
});

test("manual rollback uses verified rollback and reports terminal state", () => {
  const fs = require("node:fs");
  const source = fs.readFileSync(require.resolve("../content/overlay.js"), "utf8");

  assert.match(source, /rollbackAndVerifyLast\(\)/);
  assert.match(source, /"rollback_complete"/);
  assert.match(source, /"rollback_incomplete"/);
});

test("expired coordination cannot prevent local rollback", () => {
  const fs = require("node:fs");
  const overlay = fs.readFileSync(require.resolve("../content/overlay.js"), "utf8");
  const required = overlay.indexOf('event: "rollback_required"');
  const rollback = overlay.indexOf("rollbackAndVerifyLast()", required);
  const coordinationFailure = overlay.indexOf("coordinationFailed: true", rollback);
  assert.ok(required >= 0);
  assert.ok(rollback > required);
  assert.ok(coordinationFailure > rollback);
});

test("control capability is bound to the active candidate tab", () => {
  const fs = require("node:fs");
  const worker = fs.readFileSync(require.resolve("../service-worker.js"), "utf8");
  assert.match(worker, /capability\.tab_id !== sender\?\.tab\?\.id/);
  assert.match(worker, /controlCapability\(state\.session_id, sender\)/);
});

test("bridge capability remains bound to the requesting tab through consume", () => {
  const fs = require("node:fs");
  const worker = fs.readFileSync(require.resolve("../service-worker.js"), "utf8");
  assert.match(worker, /tab_id: sender\?\.tab\?\.id/);
  assert.match(worker, /capability\.tab_id !== sender\?\.tab\?\.id/);
  assert.match(worker, /consumeBridgeProfile\(message, sender\)/);
});

test("a different tab cannot consume or erase the one-shot bridge capability", async () => {
  const capability = {
    token: "one-shot-token",
    host: "127.0.0.1",
    port: 45678,
    origin: "https://example.invalid",
    session_id: "session-1",
    candidate_id: "candidate-1",
    fingerprint: "fingerprint-1",
    tab_id: 7,
    document_id: "doc-1",
  };
  let removed = false;
  let requests = 0;
  global.chrome = {
    storage: {session: {
      get: async () => ({kenshoBridgeCapability: capability}),
      remove: async () => { removed = true; },
      set: async () => {},
    }},
  };
  global.fetch = async () => {
    requests += 1;
    return {
      ok: true,
      json: async () => ({
        payload: {email: "fixture@example.invalid"},
        progress_token: "progress-token",
      }),
    };
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const {consumeBridgeProfile} = require("../service-worker.js");

  await assert.rejects(
    consumeBridgeProfile(
      {fingerprint: "fingerprint-1"},
      {url: "https://example.invalid/apply", tab: {id: 8}, documentId: "doc-1"}
    ),
    /invalid_bridge_binding/
  );
  assert.equal(removed, false);
  assert.equal(requests, 0);
  await assert.rejects(
    consumeBridgeProfile(
      {fingerprint: "fingerprint-1"},
      {url: "https://example.invalid/apply", tab: {id: 7}, documentId: "doc-after-reload"}
    ),
    /invalid_bridge_binding/
  );
  assert.equal(removed, false);
  assert.equal(requests, 0);
  const profile = await consumeBridgeProfile(
    {fingerprint: "fingerprint-1"},
    {url: "https://example.invalid/apply", tab: {id: 7}, documentId: "doc-1"}
  );
  assert.equal(profile.email, "fixture@example.invalid");
  assert.equal(removed, true);
  assert.equal(requests, 1);
  delete global.fetch;
  delete global.chrome;
});

test("coordination safe stop validates the active tab binding", () => {
  const fs = require("node:fs");
  const worker = fs.readFileSync(require.resolve("../service-worker.js"), "utf8");
  const safeStop = worker.indexOf("async function reportCoordinationFailure");
  const validation = worker.indexOf("controlCapability(state.session_id, sender)", safeStop);
  const request = worker.indexOf("/api/session/extension-safe-stop", safeStop);
  assert.ok(validation > safeStop);
  assert.ok(request > validation);
});

test("expired rollback reports a canonical safe stop after local restoration", () => {
  const fs = require("node:fs");
  const overlay = fs.readFileSync(require.resolve("../content/overlay.js"), "utf8");
  const rollback = overlay.indexOf("rollbackAndVerifyLast()");
  const safeStop = overlay.indexOf('type: "REPORT_COORDINATION_FAILURE"', rollback);
  assert.ok(rollback >= 0);
  assert.ok(safeStop > rollback);
});

test("Japanese normalization formats kana, postal code, phone, and split birthday", () => {
  const normalization = require("../shared/normalization.js");

  assert.equal(normalization.toKatakana("やまだ"), "ヤマダ");
  assert.equal(normalization.toHiragana("ヤマダ"), "やまだ");
  assert.equal(normalization.asDigits("０９０-１２３４-５６７８"), "09012345678");
  assert.equal(normalization.postalCode("０００２７４１", true), "000-2741");
  assert.deepEqual(normalization.phoneParts("090-1234-5678"), ["090", "1234", "5678"]);
  assert.deepEqual(normalization.birthDateParts("1990-04-01"), {
    year: "1990",
    month: "04",
    day: "01",
  });
  assert.equal(
    normalization.ageFromBirthDate("1990-07-28", new Date("2026-07-27T00:00:00+09:00")),
    "35"
  );
});

test("audit records strip query fragment labels and values", () => {
  const { createRecord } = require("../shared/audit-log.js");
  const record = createRecord({
    extension_version: "0.2.0",
    site_id: "site-01",
    url: "https://example.invalid/apply?email=pii@example.invalid#secret",
    detected_field_count: 4,
    label: "メールアドレス",
    value: "pii@example.invalid",
  });

  assert.deepEqual(record, {
    extension_version: "0.2.0",
    site_id: "site-01",
    detected_field_count: 4,
    origin: "https://example.invalid",
    pathname: "/apply",
    auto_submit_detected: 0,
  });
  assert.equal(JSON.stringify(record).includes("pii@example.invalid"), false);
});

test("form fingerprints ignore required-mark wording but detect meaning and structure changes", () => {
  const {
    computeFormFingerprint,
    normalizeFieldLabel,
  } = require("../shared/form-fingerprint.js");
  const base = {
    fields: [
      {
        path: "form[0]/input[0]",
        tagName: "input",
        inputType: "text",
        nameHash: "name-hash",
        idHash: "id-hash",
        autocomplete: "name",
        label: "お名前 必須",
        ariaLabel: "",
        required: true,
        disabled: false,
        readOnly: false,
        optionShapeHash: "",
      },
    ],
  };

  assert.equal(normalizeFieldLabel("お名前 必須"), normalizeFieldLabel("名前"));
  const first = computeFormFingerprint(base).fingerprint;
  const minorCopy = computeFormFingerprint({
    fields: [{...base.fields[0], label: "名前 *"}],
  }).fingerprint;
  const meaningChange = computeFormFingerprint({
    fields: [{...base.fields[0], label: "保護者名"}],
  }).fingerprint;
  const structureChange = computeFormFingerprint({
    fields: [{...base.fields[0], required: false}],
  }).fingerprint;

  assert.equal(first, minorCopy);
  assert.notEqual(first, meaningChange);
  assert.notEqual(first, structureChange);
});

test("template sanitizer rejects values and preserves only PII-free mapping metadata", () => {
  const {sanitizeTemplate} = require("../shared/form-template.js");
  const template = sanitizeTemplate({
    schemaVersion: 1,
    origin: "https://example.invalid",
    pathname: "/apply",
    fingerprint: "abc12345",
    extensionVersion: "0.2.0",
    fields: [
      {
        fieldId: "field-1",
        fieldType: "email",
        path: "form[0]/input[0]",
        inputType: "email",
        labelHash: "label-hash",
        attributeHash: "attribute-hash",
        approvedProfileKey: "email",
      },
    ],
  });

  assert.equal(template.origin, "https://example.invalid");
  assert.equal(template.pathname, "/apply");
  assert.equal(template.fields[0].approvedProfileKey, "email");
  assert.equal(JSON.stringify(template).includes("pii-test"), false);
  assert.throws(
    () =>
      sanitizeTemplate({
        ...template,
        fields: [{...template.fields[0], value: "pii-test@example.invalid"}],
      }),
    /forbidden_template_value/
  );
  assert.throws(
    () => sanitizeTemplate({...template, pathname: "/account/0002741"}),
    /unsafe_template_pathname/
  );
  assert.throws(
    () => sanitizeTemplate({...template, pathname: "/account/%2e%2e/private"}),
    /unsafe_template_pathname/
  );
});

test("worker template storage is origin/path scoped, idempotent, and append-only", async () => {
  const values = {};
  global.chrome = {
    storage: {
      local: {
        get: async (key) => ({[key]: values[key]}),
        set: async (next) => Object.assign(values, next),
      },
    },
  };
  delete require.cache[require.resolve("../service-worker.js")];
  const {saveFormTemplate, getFormTemplate, templateStorageKey} =
    require("../service-worker.js");
  const template = {
    schemaVersion: 1,
    origin: "https://example.invalid",
    pathname: "/apply",
    fingerprint: "abc12345",
    extensionVersion: "0.2.0",
    fields: [
      {
        fieldId: "field-1",
        fieldType: "email",
        path: "form[0]/input[0]",
        inputType: "email",
        labelHash: "label-hash",
        attributeHash: "attribute-hash",
        approvedProfileKey: "email",
      },
    ],
  };
  const url = "https://example.invalid/apply?email=pii-test@example.invalid#private";

  const first = await saveFormTemplate(url, template);
  const second = await saveFormTemplate(url, template);
  const approved = await saveFormTemplate(url, {...template, humanConfirmedAt: "2026-09-04T01:00:00.000Z"});
  const approvedAgain = await saveFormTemplate(url, {...template, humanConfirmedAt: "2026-09-04T02:00:00.000Z"});
  const newDocument = await saveFormTemplate(url, {
    ...template, fields: template.fields.map(field => ({...field, fieldId: "new-document-field"})),
  });
  const read = await getFormTemplate(url, template.fingerprint);
  const conflict = await saveFormTemplate(url, {...template, fingerprint: "deadbeef"});

  assert.equal(first.saved, true);
  assert.equal(first.idempotent, false);
  assert.equal(second.idempotent, true);
  assert.equal(approved.saved, true);
  assert.equal(approvedAgain.idempotent, true);
  assert.equal(newDocument.idempotent, true);
  assert.equal(values[templateStorageKey(url)].humanConfirmedAt, "2026-09-04T01:00:00.000Z");
  assert.equal(read.status, "matched");
  assert.equal(conflict.saved, false);
  assert.equal(conflict.error, "template_conflict");
  assert.equal(Object.keys(values).length, 1);
  assert.match(Object.keys(values)[0], /^kenshoFormTemplate:[a-f0-9]{8}$/);
  assert.equal(JSON.stringify(values).includes("pii-test"), false);
  assert.equal(templateStorageKey(url), Object.keys(values)[0]);
  delete global.chrome;
});


test("dedicated reconciliation never consults broad permissions and transitions fail closed", async () => {
  const values = {};
  let scripts = [];
  let messageListener;
  let installListener;
  let accessLevel;
  let permissionReads = 0;
  const event = {addListener: () => {}};
  global.chrome = {
    runtime: {id: 'fixture-extension', getManifest: () => ({version: '0.2.0', version_name: 'dedicated-runtime-origin'}),
      onInstalled: {addListener: fn => { installListener = fn; }}, onStartup: event, onMessage: {addListener: fn => { messageListener = fn; }}},
    action: {onClicked: event}, tabs: {onUpdated: event, onRemoved: event},
    permissions: {getAll: async () => { permissionReads++; throw new Error('broad_permissions_must_not_be_read'); }},
    scripting: {
      getRegisteredContentScripts: async ({ids} = {}) => scripts.filter(s => !ids || ids.includes(s.id)),
      unregisterContentScripts: async ({ids}) => { scripts = scripts.filter(s => !ids.includes(s.id)); },
      registerContentScripts: async next => { scripts.push(...next); },
    },
    storage: {session: {
      get: async key => key === null ? {...values} : {[key]: values[key]},
      set: async next => Object.assign(values, next),
      clear: async () => { for (const k of Object.keys(values)) delete values[k]; },
      remove: async key => { for (const k of Array.isArray(key) ? key : [key]) delete values[k]; },
      setAccessLevel: async value => { accessLevel = value.accessLevel; },
    }},
  };
  delete require.cache[require.resolve('../service-worker.js')];
  const worker = require('../service-worker.js');
  try {
    await worker.scheduleReconciliation();
    assert.deepEqual(scripts, []);
    await worker.setActiveOrigin('https://campaign.test/*', 'session-one');
    installListener();
    await worker.scheduleReconciliation();
    assert.deepEqual(await worker.getActiveOrigin(), {originPattern:'https://campaign.test/*', sessionId:'session-one'});
    assert.equal(accessLevel, 'TRUSTED_CONTEXTS');
    assert.equal(permissionReads, 0);
    assert.deepEqual(scripts.map(s => s.matches), [['https://campaign.test/*'], ['https://campaign.test/*']]);
    assert.ok(scripts.every(s => s.persistAcrossSessions === false));
    const send = (type, url, extra = {}) => new Promise(resolve => messageListener({type, ...extra},
      {id:'fixture-extension', url, tab:{id:42, url}, frameId:0, documentId:'fixture-document'}, resolve));
    for (const type of ['SET_ACTIVE_ORIGIN', 'CLEAR_ACTIVE_ORIGIN', 'REQUEST_ORIGIN_ACCESS', 'DISABLE_ORIGIN_ACCESS']) {
      assert.equal((await send(type, 'https://campaign.test/form', {originPattern:'https://other.test/*'})).ok, false);
    }
    assert.deepEqual(await worker.getActiveOrigin(), {originPattern:'https://campaign.test/*', sessionId:'session-one'});
    for (const sender of [
      {id:'external-extension', url:'https://campaign.test/form', tab:{id:42, url:'https://campaign.test/form'}, frameId:0},
      {id:'fixture-extension', url:'https://campaign.test/form', tab:{id:42, url:'https://campaign.test/form'}, frameId:1},
      {id:'fixture-extension', url:'https://campaign.test/form', tab:{id:42, url:'https://other.test/form'}, frameId:0},
      {id:'fixture-extension', url:'https://campaign.test/form', frameId:0},
    ]) {
      const response = await new Promise(resolve => messageListener({type:'GET_SESSION_STATUS'}, sender, resolve));
      assert.deepEqual(response, {ok:false, error:'inactive_origin'});
    }
    for (const type of ['GET_SESSION_STATUS', 'CONSUME_BRIDGE_PROFILE', 'GET_BRIDGE_CAPABILITY_STATUS', 'GET_FORM_TEMPLATE', 'SAVE_FORM_TEMPLATE']) {
      assert.deepEqual(await send(type, 'https://other.test/form'), {ok:false, error:'inactive_origin'});
    }
    values.kenshoSessionProfile = {};
    values.kenshoBridgeCapability = {};
    await worker.setActiveOrigin('https://other.test/*', 'session-one');
    assert.equal(values.kenshoSessionProfile, undefined);
    assert.equal(values.kenshoBridgeCapability, undefined);
    assert.deepEqual(scripts.map(s => s.matches), [['https://other.test/*'], ['https://other.test/*']]);
    await assert.rejects(worker.setActiveOrigin('https://*/*', 'session-one'), /invalid_active_origin/);
    assert.deepEqual(scripts, []);
    assert.equal(await worker.getActiveOrigin(), null);
    await worker.setActiveOrigin('https://campaign.test/*', 'session-one');
    await worker.clearActiveOrigin();
    assert.deepEqual(scripts, []);
    assert.equal(await worker.getActiveOrigin(), null);
    assert.equal(permissionReads, 0);
  } finally {
    await worker.scheduleReconciliation();
    delete global.chrome;
  }
});
