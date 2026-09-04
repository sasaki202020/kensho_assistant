"use strict";

if (typeof importScripts === "function") {
  importScripts("shared/redaction.js");
  importScripts("shared/form-template.js");
}

const SESSION_PROFILE_KEY = "kenshoSessionProfile";
const BRIDGE_CAPABILITY_KEY = "kenshoBridgeCapability";
const CONTROL_CAPABILITY_KEY = "kenshoControlCapability";
const PROGRESS_CAPABILITY_KEY = "kenshoProgressCapability";
const ACTIVE_TABS_KEY = "kenshoActiveTabs";
const SCRIPT_PREFIXES = ["kensho-main-", "kensho-isolated-"];
const ISOLATED_SCRIPT_FILES = [
  "shared/messages.js",
  "shared/config.js",
  "shared/field-types.js",
  "shared/redaction.js",
  "shared/normalization.js",
  "shared/form-fingerprint.js",
  "shared/audit-log.js",
  "content/isolated-guard.js",
  "content/field-matcher.js",
  "content/form-detector.js",
  "content/form-filler.js",
  "content/overlay.js",
];
const WORKER_EPOCH =
  globalThis.crypto?.randomUUID?.() ||
  `worker-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const ALLOWED_PROFILE_KEYS = new Set([
  "last_name",
  "first_name",
  "last_name_kana",
  "first_name_kana",
  "email",
  "phone",
  "postal_code",
  "prefecture",
  "city",
  "street",
  "building",
  "birth_date",
  "gender",
]);
const FORBIDDEN_PROFILE_KEYS = /password|passcode|token|secret|cookie|otp|auth/i;
let reconciliationQueue = Promise.resolve();

function fixtureBridgeMode() {
  return chrome?.runtime?.getManifest?.()?.version_name === "fixture-bridge";
}
const TEMPLATE_STORAGE_PREFIX = "kenshoFormTemplate:";

function extensionIdentity(runtime = globalThis.chrome?.runtime) {
  return {
    extensionId: String(runtime?.id || "extension-id-unavailable"),
    version: String(runtime?.getManifest?.()?.version || "0.0.0"),
  };
}

function isDuplicateExtensionIdentity(current, incoming) {
  if (!incoming?.extensionId || !incoming?.version) return true;
  return (
    incoming.extensionId !== current.extensionId ||
    incoming.version !== current.version
  );
}

async function clearSensitiveSessionState() {
  await chrome.storage.session.remove(SESSION_PROFILE_KEY);
  await chrome.storage.session.remove(BRIDGE_CAPABILITY_KEY);
  await chrome.storage.session.remove(CONTROL_CAPABILITY_KEY);
  await chrome.storage.session.remove(PROGRESS_CAPABILITY_KEY);
}

function validateProfile(profile) {
  if (!profile || typeof profile !== "object" || Array.isArray(profile)) {
    throw new Error("invalid_profile");
  }
  const safe = {};
  for (const [key, value] of Object.entries(profile)) {
    if (FORBIDDEN_PROFILE_KEYS.test(key)) throw new Error("forbidden_profile_key");
    if (!ALLOWED_PROFILE_KEYS.has(key)) continue;
    if (typeof value !== "string") throw new Error("invalid_profile_value");
    if (value) safe[key] = value;
  }
  return safe;
}

async function activeTabIds() {
  const stored = await chrome.storage.session.get(ACTIVE_TABS_KEY);
  return Array.isArray(stored[ACTIVE_TABS_KEY]) ? stored[ACTIVE_TABS_KEY] : [];
}

async function rememberActiveTab(tabId) {
  const ids = await activeTabIds();
  if (!ids.includes(tabId)) ids.push(tabId);
  await chrome.storage.session.set({ [ACTIVE_TABS_KEY]: ids });
}

async function forgetActiveTab(tabId, clearProfile = true) {
  const ids = await activeTabIds();
  if (!ids.includes(tabId)) return;
  await chrome.storage.session.set({
    [ACTIVE_TABS_KEY]: ids.filter((id) => id !== tabId),
  });
  if (clearProfile) await chrome.storage.session.remove(SESSION_PROFILE_KEY);
}

async function injectIntoTab(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId, allFrames: false },
    world: "MAIN",
    files: ["content/submit-guard.js"],
    injectImmediately: true,
  });
  await chrome.scripting.executeScript({
    target: { tabId, allFrames: false },
    world: "ISOLATED",
    files: ISOLATED_SCRIPT_FILES,
  });
}

function stableOriginHash(value) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function scriptIdsForOrigin(originPattern) {
  const hash = stableOriginHash(originPattern);
  return {
    main: `kensho-main-${hash}`,
    isolated: `kensho-isolated-${hash}`,
  };
}

function originPatternForUrl(urlValue) {
  try {
    const url = new URL(urlValue);
    if (!["http:", "https:"].includes(url.protocol)) return null;
    if (!url.hostname || url.hostname === "*") return null;
    return `${url.origin}/*`;
  } catch (_error) {
    return null;
  }
}

function registrationsForOrigin(originPattern) {
  const ids = scriptIdsForOrigin(originPattern);
  return [
    {
      id: ids.main,
      matches: [originPattern],
      js: ["content/submit-guard.js"],
      allFrames: false,
      runAt: "document_start",
      world: "MAIN",
      persistAcrossSessions: true,
    },
    {
      id: ids.isolated,
      matches: [originPattern],
      js: ISOLATED_SCRIPT_FILES,
      allFrames: false,
      runAt: "document_idle",
      world: "ISOLATED",
      persistAcrossSessions: true,
    },
  ];
}

function isManagedScript(script) {
  return SCRIPT_PREFIXES.some((prefix) => script?.id?.startsWith(prefix));
}

function registrationMatches(actual, expected) {
  return (
    actual.id === expected.id &&
    JSON.stringify(actual.matches || []) === JSON.stringify(expected.matches) &&
    JSON.stringify(actual.js || []) === JSON.stringify(expected.js) &&
    actual.allFrames === expected.allFrames &&
    actual.runAt === expected.runAt &&
    actual.world === expected.world &&
    actual.persistAcrossSessions === expected.persistAcrossSessions
  );
}

async function registerOriginScripts(originPattern) {
  const expected = registrationsForOrigin(originPattern);
  const ids = expected.map((item) => item.id);
  const existing = await chrome.scripting.getRegisteredContentScripts({ ids });
  const staleIds = existing
    .filter((item) => {
      const wanted = expected.find((candidate) => candidate.id === item.id);
      return !wanted || !registrationMatches(item, wanted);
    })
    .map((item) => item.id);
  if (staleIds.length) {
    await chrome.scripting.unregisterContentScripts({ ids: staleIds });
  }
  const remainingIds = new Set(
    existing.filter((item) => !staleIds.includes(item.id)).map((item) => item.id)
  );
  const missing = expected.filter((item) => !remainingIds.has(item.id));
  if (missing.length) await chrome.scripting.registerContentScripts(missing);
  return scriptIdsForOrigin(originPattern);
}

async function registerOriginGuard(originPattern) {
  return (await registerOriginScripts(originPattern)).main;
}

async function grantedOriginPatterns() {
  const permissions = await chrome.permissions.getAll();
  return [...new Set((permissions.origins || []).map(originPatternForUrl).filter(Boolean))];
}

async function reconcileOriginScripts() {
  const origins = await grantedOriginPatterns();
  const desiredIds = new Set(
    origins.flatMap((origin) => Object.values(scriptIdsForOrigin(origin)))
  );
  const existing = await chrome.scripting.getRegisteredContentScripts();
  const staleIds = existing
    .filter((script) => isManagedScript(script) && !desiredIds.has(script.id))
    .map((script) => script.id);
  if (staleIds.length) {
    await chrome.scripting.unregisterContentScripts({ ids: staleIds });
  }
  for (const origin of origins) await registerOriginScripts(origin);
  return { origins: origins.length, removed: staleIds.length };
}

function scheduleReconciliation() {
  reconciliationQueue = reconciliationQueue
    .catch(() => {})
    .then(() => reconcileOriginScripts());
  return reconciliationQueue;
}

function redactionApi() {
  if (globalThis.KenshoExtension?.Redaction) return globalThis.KenshoExtension.Redaction;
  if (typeof require === "function") return require("./shared/redaction.js");
  throw new Error("redaction_unavailable");
}

function templateApi() {
  if (globalThis.KenshoExtension?.FormTemplate) {
    return globalThis.KenshoExtension.FormTemplate;
  }
  if (typeof require === "function") return require("./shared/form-template.js");
  throw new Error("form_template_unavailable");
}

function templateLocationForUrl(urlValue) {
  try {
    const url = new URL(urlValue);
    if (!/^https?:$/.test(url.protocol)) return null;
    return {origin: url.origin, pathname: url.pathname || "/"};
  } catch (_error) {
    return null;
  }
}

function templateStorageKey(urlValue) {
  const location = templateLocationForUrl(urlValue);
  if (!location) return null;
  return `${TEMPLATE_STORAGE_PREFIX}${stableOriginHash(
    `${location.origin}${location.pathname}`
  )}`;
}

async function getFormTemplate(senderUrl, fingerprint = "") {
  const location = templateLocationForUrl(senderUrl);
  const key = templateStorageKey(senderUrl);
  if (!location || !key) return {status: "unsupported_origin"};
  const stored = await chrome.storage.local.get(key);
  const value = stored[key];
  if (!value) return {status: "none", origin: location.origin, pathname: location.pathname};
  let template;
  try {
    template = templateApi().sanitizeTemplate(value);
  } catch (_error) {
    return {status: "invalid", origin: location.origin, pathname: location.pathname};
  }
  const status =
    template.origin === location.origin &&
    template.pathname === location.pathname &&
    (!fingerprint || template.fingerprint === fingerprint)
      ? "matched"
      : "changed";
  return {
    status,
    origin: location.origin,
    pathname: location.pathname,
    fingerprint: template.fingerprint,
    structureFingerprint: template.structureFingerprint,
    fields: template.fields,
  };
}

async function saveFormTemplate(senderUrl, input) {
  const location = templateLocationForUrl(senderUrl);
  const key = templateStorageKey(senderUrl);
  if (!location || !key) return {saved: false, error: "unsupported_origin"};
  const template = templateApi().sanitizeTemplate(input);
  if (template.origin !== location.origin || template.pathname !== location.pathname) {
    return {saved: false, error: "template_location_mismatch"};
  }
  const stored = await chrome.storage.local.get(key);
  const existing = stored[key];
  if (existing) {
    const normalizedExisting = templateApi().sanitizeTemplate(existing);
    // Approval time and per-document handles are not mapping content.
    const mappingContent = (value) => JSON.stringify({
      ...value, humanConfirmedAt: "",
      fields: value.fields.map(({fieldId, ...field}) => field),
    });
    if (mappingContent(normalizedExisting) !== mappingContent(template)) {
      return {saved: false, error: "template_conflict"};
    }
    if (!normalizedExisting.humanConfirmedAt && template.humanConfirmedAt &&
        Number.isFinite(Date.parse(template.humanConfirmedAt))) {
      await chrome.storage.local.set({[key]: {
        ...normalizedExisting, humanConfirmedAt: template.humanConfirmedAt,
      }});
    }
    return {saved: true, idempotent: true, fingerprint: template.fingerprint};
  }
  await chrome.storage.local.set({[key]: template});
  return {saved: true, idempotent: false, fingerprint: template.fingerprint};
}

async function profilePreview() {
  const stored = await chrome.storage.session.get(SESSION_PROFILE_KEY);
  const profile = stored[SESSION_PROFILE_KEY] || null;
  if (!profile) return null;
  const redaction = redactionApi();
  return Object.fromEntries(
    Object.entries(profile).map(([key, value]) => [key, redaction.maskValue(key, value)])
  );
}

async function consumeProfile() {
  const stored = await chrome.storage.session.get(SESSION_PROFILE_KEY);
  return stored[SESSION_PROFILE_KEY] || null;
}

async function consumeBridgeProfile(message, sender) {
  const senderUrl = sender?.url || sender?.tab?.url || "";
  const location = templateLocationForUrl(senderUrl || "");
  const stored = await chrome.storage.session.get(BRIDGE_CAPABILITY_KEY);
  const capability = stored[BRIDGE_CAPABILITY_KEY] || {};
  const host = String(capability.host || message?.host || "");
  const port = Number(capability.port || message?.port || 0);
  const origin = String(capability.origin || message?.origin || "");
  if (
    !location ||
    location.origin !== origin ||
    host !== "127.0.0.1" ||
    !Number.isInteger(port) ||
    port < 1 ||
    port > 65535 ||
    !Number.isInteger(capability.tab_id) ||
    capability.tab_id !== sender?.tab?.id ||
    !capability.document_id || capability.document_id !== sender?.documentId
  ) {
    throw new Error("invalid_bridge_binding");
  }
  await chrome.storage.session.remove(BRIDGE_CAPABILITY_KEY);
  const response = await fetch(`http://${host}:${port}/v1/capability/consume`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    cache: "no-store",
    body: JSON.stringify({
      token: String(capability.token || message.token || ""),
      session_id: String(capability.session_id || message.session_id || ""),
      candidate_id: String(capability.candidate_id || message.candidate_id || ""),
      origin,
      fingerprint: String(capability.fingerprint || message.fingerprint || ""),
    }),
  });
  if (!response.ok) throw new Error("bridge_rejected");
  const body = await response.json();
  const profile = validateProfile(body?.payload || {});
  if (!body?.progress_token) throw new Error("missing_progress_capability");
  await chrome.storage.session.set({
    [PROGRESS_CAPABILITY_KEY]: {
      token: String(body.progress_token),
      session_id: String(capability.session_id || ""),
      candidate_id: String(capability.candidate_id || ""),
      origin,
      fingerprint: String(capability.fingerprint || ""),
      document_id: sender.documentId,
    },
  });
  return profile;
}

async function controlCapability(sessionId, sender) {
  const stored = await chrome.storage.session.get(CONTROL_CAPABILITY_KEY);
  const capability = stored[CONTROL_CAPABILITY_KEY] || {};
  if (
    !capability.token ||
    String(capability.session_id || "") !== String(sessionId || "") ||
    !Number.isInteger(capability.tab_id) ||
    capability.tab_id !== sender?.tab?.id ||
    !capability.document_id || capability.document_id !== sender?.documentId
  ) {
    throw new Error("control_capability_unavailable");
  }
  return String(capability.token);
}

async function revokeBridgeCapabilities(sender) {
  const statusResponse = await fetch("http://127.0.0.1:8787/api/session/status", {
    method: "GET",
    cache: "no-store",
  });
  if (!statusResponse.ok) throw new Error("session_unavailable");
  const state = await statusResponse.json();
  const controlToken = await controlCapability(state.session_id, sender);
  const response = await fetch(
    "http://127.0.0.1:8787/api/session/extension-capability/revoke",
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      cache: "no-store",
      body: JSON.stringify({
        session_id: String(state.session_id || ""),
        control_token: controlToken,
      }),
    }
  );
  if (!response.ok) throw new Error("capability_revoke_failed");
  return response.json();
}

async function configureSessionStorage() {
  if (chrome.storage.session.setAccessLevel) {
    await chrome.storage.session.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
  }
}

async function setBridgeCapability(message, sender) {
  if (!sender?.id || sender.id !== chrome.runtime.id) throw new Error("extension_context_required");
  if (!Number.isInteger(sender?.tab?.id) || !sender?.documentId) throw new Error("invalid_bridge_binding");
  const token = String(message?.token || "");
  const origin = String(message?.origin || "");
  const host = String(message?.host || "");
  const port = Number(message?.port || 0);
  if (!token || host !== "127.0.0.1" || !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("invalid_bridge_capability");
  }
  if (!templateLocationForUrl(`${origin}/`)) throw new Error("invalid_bridge_capability");
  await chrome.storage.session.set({
    [BRIDGE_CAPABILITY_KEY]: {
      token,
      host,
      port,
      origin,
      session_id: String(message.session_id || ""),
      candidate_id: String(message.candidate_id || ""),
      fingerprint: String(message.fingerprint || ""),
      tab_id: sender?.tab?.id,
      document_id: sender.documentId,
    },
  });
  return {stored: true};
}

async function requestBridgeCapability(sender, fingerprint, profileKeys = []) {
  const senderUrl = sender?.url || sender?.tab?.url || "";
  const location = templateLocationForUrl(senderUrl || "");
  if (!location) throw new Error("invalid_bridge_binding");
  const requestedProfileKeys = [...new Set(profileKeys.map((key) => String(key || "").trim()))];
  if (
    !requestedProfileKeys.length ||
    requestedProfileKeys.some((key) => !ALLOWED_PROFILE_KEYS.has(key))
  ) {
    throw new Error("invalid_profile_keys");
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 1000);
  let statusResponse;
  try {
    statusResponse = await fetch("http://127.0.0.1:8787/api/session/status", {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
  if (!statusResponse.ok) throw new Error("session_unavailable");
  const state = await statusResponse.json();
  const controlToken = await controlCapability(state.session_id, sender);
  const capabilityController = new AbortController();
  const capabilityTimeoutId = setTimeout(() => capabilityController.abort(), 1000);
  let response;
  try {
    response = await fetch("http://127.0.0.1:8787/api/session/extension-capability", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      cache: "no-store",
      signal: capabilityController.signal,
      body: JSON.stringify({
        session_id: String(state.session_id || ""),
        candidate_id: String(state.active_candidate_id || state.candidate_id || ""),
        origin: location.origin,
        fingerprint: String(fingerprint || ""),
        profile_keys: requestedProfileKeys,
        control_token: controlToken,
      }),
    });
  } finally {
    clearTimeout(capabilityTimeoutId);
  }
  if (!response.ok) throw new Error("capability_unavailable");
  const capability = await response.json();
  await setBridgeCapability(capability, {id: chrome.runtime.id, tab: sender?.tab, documentId: sender?.documentId});
  return {available: true};
}

async function reportExtensionProgress(sender, fingerprint, event, details = {}) {
  const senderUrl = sender?.url || sender?.tab?.url || "";
  const location = templateLocationForUrl(senderUrl || "");
  const safeEvent = String(event || "");
  const allowedEvents = new Set([
    "post_fill_verified",
    "rollback_required",
    "rollback_complete",
    "rollback_incomplete",
    "unsupported_form",
    "failed_safe",
  ]);
  const allowedDetailKeys = new Set([
    "filled_count",
    "unrelated_changed_count",
    "target_mismatch_count",
    "rollback_complete",
  ]);
  if (
    !location ||
    !String(fingerprint || "") ||
    !allowedEvents.has(safeEvent) ||
    !details ||
    typeof details !== "object" ||
    Object.keys(details).some((key) => !allowedDetailKeys.has(key))
  ) {
    throw new Error("invalid_extension_progress");
  }
  const statusResponse = await fetch("http://127.0.0.1:8787/api/session/status", {
    method: "GET",
    cache: "no-store",
  });
  if (!statusResponse.ok) throw new Error("session_unavailable");
  const state = await statusResponse.json();
  const controlToken = await controlCapability(state.session_id, sender);
  const storedProgress = await chrome.storage.session.get(PROGRESS_CAPABILITY_KEY);
  const progress = storedProgress[PROGRESS_CAPABILITY_KEY] || {};
  if (
    !progress.token ||
    String(progress.session_id || "") !== String(state.session_id || "") ||
    String(progress.candidate_id || "") !== String(state.active_candidate_id || state.candidate_id || "") ||
    String(progress.origin || "") !== location.origin ||
    String(progress.fingerprint || "") !== String(fingerprint || "")
  ) {
    throw new Error("progress_capability_unavailable");
  }
  const operationId = globalThis.crypto?.randomUUID?.() ||
    `extension-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const request = {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    cache: "no-store",
    body: JSON.stringify({
      session_id: String(state.session_id || ""),
      candidate_id: String(state.active_candidate_id || state.candidate_id || ""),
      origin: location.origin,
      fingerprint: String(fingerprint || ""),
      event: safeEvent,
      operation_id: operationId,
      control_token: controlToken,
      progress_token: String(progress.token),
      details,
    }),
  };
  let response = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      response = await fetch("http://127.0.0.1:8787/api/session/extension-progress", request);
      if (response.ok || response.status < 500) break;
    } catch (_error) {
      response = null;
    }
    await new Promise((resolve) => setTimeout(resolve, 50 * (attempt + 1)));
  }
  if (!response) throw new Error("extension_progress_unavailable");
  if (!response.ok) throw new Error("extension_progress_rejected");
  const body = await response.json();
  if (safeEvent === "post_fill_verified" && body.progress_token) {
    await chrome.storage.session.set({
      [PROGRESS_CAPABILITY_KEY]: {...progress, token: String(body.progress_token)},
    });
  } else if (safeEvent !== "rollback_required") {
    await chrome.storage.session.remove(PROGRESS_CAPABILITY_KEY);
  }
  return body;
}

async function reportCoordinationFailure(sender, fingerprint) {
  const location = templateLocationForUrl(sender?.url || sender?.tab?.url || "");
  if (!location || !String(fingerprint || "")) throw new Error("invalid_safe_stop_binding");
  const statusResponse = await fetch("http://127.0.0.1:8787/api/session/status", {
    method: "GET", cache: "no-store",
  });
  if (!statusResponse.ok) throw new Error("session_unavailable");
  const state = await statusResponse.json();
  await controlCapability(state.session_id, sender);
  const response = await fetch("http://127.0.0.1:8787/api/session/extension-safe-stop", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    cache: "no-store",
    body: JSON.stringify({
      session_id: String(state.session_id || ""),
      candidate_id: String(state.active_candidate_id || state.candidate_id || ""),
      origin: location.origin,
      fingerprint: String(fingerprint || ""),
    }),
  });
  if (!response.ok) throw new Error("safe_stop_rejected");
  return response.json();
}

async function originAccessState(senderUrl) {
  const originPattern = originPatternForUrl(senderUrl);
  if (!originPattern) return { allowed: false, originPattern: null };
  const allowed = await chrome.permissions.contains({ origins: [originPattern] });
  return { allowed, originPattern };
}

async function requestOriginAccess(senderUrl, tabId) {
  const originPattern = originPatternForUrl(senderUrl);
  if (!originPattern) return { granted: false, error: "unsupported_origin" };
  const granted = await chrome.permissions.request({ origins: [originPattern] });
  if (!granted) return { granted: false, originPattern };
  await registerOriginScripts(originPattern);
  if (tabId) {
    setTimeout(() => chrome.tabs.reload(tabId).catch(() => {}), 100);
  }
  return { granted: true, originPattern };
}

async function disableOrigin(senderUrl, sender) {
  const originPattern = originPatternForUrl(senderUrl);
  if (!originPattern) return { removed: false, error: "unsupported_origin" };
  if (!fixtureBridgeMode()) {
    const revoked = await revokeBridgeCapabilities(sender);
    if (!revoked?.ok) return {removed: false, error: "capability_revoke_failed"};
  }
  const ids = Object.values(scriptIdsForOrigin(originPattern));
  await chrome.scripting.unregisterContentScripts({ ids }).catch(() => {});
  const removed = await chrome.permissions.remove({ origins: [originPattern] });
  await chrome.storage.session.remove(SESSION_PROFILE_KEY);
  await chrome.storage.session.remove(BRIDGE_CAPABILITY_KEY);
  await chrome.storage.session.remove(CONTROL_CAPABILITY_KEY);
  await chrome.storage.session.remove(PROGRESS_CAPABILITY_KEY);
  return { removed, originPattern };
}

if (typeof chrome !== "undefined" && chrome.runtime) {
  configureSessionStorage().catch(() => {});
  chrome.runtime.onInstalled.addListener(() => {
    chrome.storage.session.clear();
    configureSessionStorage();
    scheduleReconciliation().catch(() => {});
  });
  chrome.runtime.onStartup.addListener(() => {
    configureSessionStorage();
    scheduleReconciliation().catch(() => {});
  });
  scheduleReconciliation().catch(() => {});

  chrome.action.onClicked.addListener(async (tab) => {
    if (!tab.id) return;
    const originPattern = originPatternForUrl(tab.url || "");
    if (!originPattern) return;
    await rememberActiveTab(tab.id);
    await injectIntoTab(tab.id);
  });

  chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
    if (changeInfo.status !== "loading" && !changeInfo.url) return;
    await forgetActiveTab(tabId);
  });

  chrome.tabs.onRemoved.addListener(async (tabId) => {
    await forgetActiveTab(tabId);
  });

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    (async () => {
      if (message?.type === "GET_EXTENSION_ID") {
        sendResponse({ok: true, ...extensionIdentity()});
        return;
      }
      if (message?.type === "EXTENSION_INSTANCE_HELLO") {
        const identity = extensionIdentity();
        const duplicate = isDuplicateExtensionIdentity(identity, message);
        if (duplicate) await clearSensitiveSessionState();
        sendResponse({ok: true, ...identity, duplicate});
        return;
      }
      if (message?.type === "DUPLICATE_EXTENSION_BLOCKED") {
        await clearSensitiveSessionState();
        sendResponse({ok: true, duplicate: true});
        return;
      }
      if (message?.type === "CONSUME_BRIDGE_PROFILE") {
        if (fixtureBridgeMode()) {
          sendResponse({ok: true, profile: await consumeProfile(), workerEpoch: WORKER_EPOCH});
          return;
        }
        const profile = await consumeBridgeProfile(message, sender);
        sendResponse({ ok: true, profile, workerEpoch: WORKER_EPOCH });
        return;
      }
      if (message?.type === "SET_BRIDGE_CAPABILITY") {
        sendResponse({ok: true, ...(await setBridgeCapability(message, sender))});
        return;
      }
      if (message?.type === "REQUEST_BRIDGE_CAPABILITY") {
        if (fixtureBridgeMode()) {
          await chrome.storage.session.set({
            [BRIDGE_CAPABILITY_KEY]: {fixture: true, origin: sender?.url || sender?.tab?.url || ""},
          });
          sendResponse({ok: true, available: true});
          return;
        }
        sendResponse({
          ok: true,
          ...(await requestBridgeCapability(
            sender,
            message.fingerprint || "",
            Array.isArray(message.profileKeys) ? message.profileKeys : []
          )),
        });
        return;
      }
      if (message?.type === "REPORT_EXTENSION_PROGRESS") {
        if (fixtureBridgeMode()) {
          sendResponse({ok: true, workflow_state: "HUMAN_ACTION_REQUIRED", submitted_count_auto: 0});
          return;
        }
        sendResponse({
          ok: true,
          ...(await reportExtensionProgress(
            sender,
            message.fingerprint || "",
            message.event || "",
            message.details || {}
          )),
        });
        return;
      }
      if (message?.type === "REPORT_COORDINATION_FAILURE") {
        sendResponse({ok: true, ...(await reportCoordinationFailure(sender, message.fingerprint || ""))});
        return;
      }
      if (message?.type === "GET_BRIDGE_CAPABILITY_STATUS") {
        const stored = await chrome.storage.session.get(BRIDGE_CAPABILITY_KEY);
        sendResponse({ok: true, available: Boolean(stored[BRIDGE_CAPABILITY_KEY])});
        return;
      }
      if (message?.type === "CLEAR_SESSION_PROFILE") {
        let revoked = false;
        try {
          const result = fixtureBridgeMode()
            ? {ok: true}
            : await revokeBridgeCapabilities(sender);
          revoked = Boolean(result?.ok);
        } catch (_error) {
          revoked = false;
        }
        await chrome.storage.session.remove(SESSION_PROFILE_KEY);
        await chrome.storage.session.remove(BRIDGE_CAPABILITY_KEY);
        await chrome.storage.session.remove(CONTROL_CAPABILITY_KEY);
        await chrome.storage.session.remove(PROGRESS_CAPABILITY_KEY);
        sendResponse({ ok: revoked });
        return;
      }
      if (message?.type === "GET_FORM_TEMPLATE") {
        sendResponse({
          ok: true,
          ...(await getFormTemplate(
            sender?.url || sender?.tab?.url || "",
            message.fingerprint || ""
          )),
        });
        return;
      }
      if (message?.type === "SAVE_FORM_TEMPLATE") {
        sendResponse({
          ok: true,
          ...(await saveFormTemplate(
            sender?.url || sender?.tab?.url || "",
            message.template
          )),
        });
        return;
      }
      if (message?.type === "OPEN_PROFILE_OPTIONS") {
        await chrome.runtime.openOptionsPage();
        sendResponse({ ok: true });
        return;
      }
      if (message?.type === "GET_ORIGIN_ACCESS") {
        sendResponse({
          ok: true,
          ...(await originAccessState(sender?.url || sender?.tab?.url || "")),
        });
        return;
      }
      if (message?.type === "REQUEST_ORIGIN_ACCESS") {
        sendResponse({
          ok: true,
          ...(await requestOriginAccess(
            sender?.url || sender?.tab?.url || "",
            sender?.tab?.id
          )),
        });
        return;
      }
      if (message?.type === "DISABLE_ORIGIN_ACCESS") {
        const result = await disableOrigin(sender?.url || sender?.tab?.url || "", sender);
        if (result.removed && sender?.tab?.id) {
          setTimeout(() => chrome.tabs.reload(sender.tab.id).catch(() => {}), 100);
        }
        sendResponse({ ok: true, ...result });
        return;
      }
      if (message?.type === "GET_SESSION_STATUS") {
        const stored = await chrome.storage.session.get(SESSION_PROFILE_KEY);
        sendResponse({
          ok: true,
          profileLoaded: Boolean(stored[SESSION_PROFILE_KEY]),
          workerEpoch: WORKER_EPOCH,
          submitted_count_auto: 0,
        });
        return;
      }
      sendResponse({ ok: false, error: "unknown_message" });
    })().catch(() => sendResponse({ ok: false, error: "safe_failure" }));
    return true;
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    validateProfile,
    injectIntoTab,
    registerOriginGuard,
    registerOriginScripts,
    reconcileOriginScripts,
    scheduleReconciliation,
    disableOrigin,
    requestOriginAccess,
    originAccessState,
    originPatternForUrl,
    scriptIdsForOrigin,
    registrationsForOrigin,
    profilePreview,
    consumeProfile,
    consumeBridgeProfile,
    setBridgeCapability,
    requestBridgeCapability,
    reportExtensionProgress,
    reportCoordinationFailure,
    getFormTemplate,
    saveFormTemplate,
    templateLocationForUrl,
    templateStorageKey,
    TEMPLATE_STORAGE_PREFIX,
    forgetActiveTab,
    SESSION_PROFILE_KEY,
    BRIDGE_CAPABILITY_KEY,
    ALLOWED_PROFILE_KEYS,
    WORKER_EPOCH,
    extensionIdentity,
    isDuplicateExtensionIdentity,
    clearSensitiveSessionState,
  };
}
