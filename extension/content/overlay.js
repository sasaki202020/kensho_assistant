(function initializeOverlay(root) {
  "use strict";

  const INSTANCE_EVENT = "kensho-extension-instance-hello";
  const extensionId = String(root.chrome?.runtime?.id || "extension-id-unavailable");
  const extensionVersion = String(
    root.chrome?.runtime?.getManifest?.()?.version || "0.2.0"
  );

  function disableInstance(instanceHost) {
    if (!instanceHost) return;
    instanceHost.setAttribute("data-kensho-duplicate-extension", "true");
    instanceHost.setAttribute("data-kensho-status", "blocked");
    for (const button of instanceHost.shadowRoot?.querySelectorAll(
      "button[data-kensho-action]"
    ) || []) {
      button.disabled = true;
    }
    const instanceStatus = instanceHost.shadowRoot?.getElementById("status");
    if (instanceStatus) {
      instanceStatus.textContent = "拡張機能の二重起動を検出・安全停止・送信ロック中";
      instanceStatus.classList.add("warning");
    }
  }

  function notifyDuplicate(otherExtensionId, otherVersion) {
    try {
      root.chrome?.runtime?.sendMessage?.(
        {
          type: "DUPLICATE_EXTENSION_BLOCKED",
          extensionId,
          version: extensionVersion,
          otherExtensionId: String(otherExtensionId || "unknown"),
          otherVersion: String(otherVersion || "unknown"),
        },
        () => void root.chrome?.runtime?.lastError
      );
    } catch (_error) {
      // The DOM remains fail-closed even if the worker is unavailable.
    }
  }

  function announceInstance() {
    document.dispatchEvent(
      new CustomEvent(INSTANCE_EVENT, {
        detail: JSON.stringify({extensionId, version: extensionVersion}),
      })
    );
  }

  const existingHost = document.getElementById("kensho-assistant-overlay-host");
  if (existingHost) {
    const existingId = existingHost.getAttribute("data-kensho-extension-id") || "unknown";
    const existingVersion =
      existingHost.getAttribute("data-kensho-extension-version") || "unknown";
    if (existingId === extensionId && existingVersion === extensionVersion) return;
    document.documentElement.setAttribute("data-kensho-duplicate-extension", "true");
    disableInstance(existingHost);
    announceInstance();
    notifyDuplicate(existingId, existingVersion);
    return;
  }

  const host = document.createElement("div");
  host.id = "kensho-assistant-overlay-host";
  host.setAttribute("data-kensho-extension-root", "true");
  host.setAttribute("data-kensho-extension-id", extensionId);
  host.setAttribute("data-kensho-extension-version", extensionVersion);
  host.setAttribute("data-kensho-status", "ready");
  host.style.cssText = "all:initial;position:fixed;right:16px;bottom:16px;z-index:2147483647";
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host{all:initial}
      .panel{width:320px;background:#fff;color:#151515;border:1px solid #ccc;border-radius:8px;
        box-shadow:0 8px 28px rgba(0,0,0,.22);font:14px/1.45 system-ui,sans-serif;padding:14px}
      h2{font-size:17px;margin:0 0 8px}.status{background:#f3f6f4;border-left:4px solid #18864b;
        padding:8px;margin:0 0 10px}.warning{border-left-color:#c22;background:#fff2f2}
      .actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
      button{min-height:38px;border:1px solid #777;background:#fff;color:#111;border-radius:6px;cursor:pointer}
      button.primary{background:#146c43;color:#fff;border-color:#146c43}
      button.danger{color:#a40000}.preview{max-height:180px;overflow:auto;margin:10px 0}
      .item{border-top:1px solid #ddd;padding:6px 0}.meta{color:#555;font-size:12px}
      .mapping-actions{display:flex;gap:5px;align-items:center;margin-top:5px}
      .mapping-actions select{min-height:28px;flex:1}
      .mapping-actions button{min-height:28px;font-size:12px;padding:2px 5px}
    </style>
    <section class="panel" aria-label="懸賞入力補助">
      <h2>懸賞入力補助</h2>
      <div id="status" class="status">未解析・送信ロック中</div>
      <div id="preview" class="preview"></div>
      <div class="actions">
        <button type="button" id="analyze" class="primary"
          data-kensho-action="analyze" aria-label="懸賞フォームを解析">フォーム解析</button>
        <button type="button" id="preview-button"
          data-kensho-action="preview" aria-label="入力予定内容を確認">入力内容を確認</button>
        <button type="button" id="approve-safe"
          data-kensho-action="approve-safe" aria-label="高信頼の入力欄を一括承認">高信頼の欄を一括承認</button>
        <button type="button" id="fill" class="primary"
          data-kensho-action="fill" aria-label="確認済み情報を入力">入力を実行</button>
        <button type="button" id="save-template"
          data-kensho-action="save-template" aria-label="確認済みの欄対応を保存">欄対応を保存</button>
        <button type="button" id="rollback"
          data-kensho-action="rollback" aria-label="入力を元に戻す">入力を元に戻す</button>
        <button type="button" id="open-profile"
          data-kensho-action="open-profile" aria-label="一時プロフィールを読み込む">プロフィールを読み込む</button>
        <button type="button" id="enable-origin"
          data-kensho-action="enable-origin" aria-label="このサイトで常に有効にする">このサイトで常に有効にする</button>
        <button type="button" id="disable-origin"
          data-kensho-action="disable-origin" aria-label="このサイトで自動起動しない">このサイトで自動起動しない</button>
        <button type="button" id="stop" class="danger"
          data-kensho-action="stop" aria-label="問題を検出して停止">問題あり・停止</button>
        <button type="button" id="clear"
          data-kensho-action="clear-session" aria-label="一時セッション情報を消去">セッション情報を消去</button>
      </div>
    </section>`;
  document.documentElement.appendChild(host);
  document.documentElement.setAttribute("data-kensho-extension-ready", "true");

  const status = shadow.getElementById("status");
  const previewBox = shadow.getElementById("preview");
  const approveSafeButton = shadow.getElementById("approve-safe");
  const fillButton = shadow.getElementById("fill");
  const saveTemplateButton = shadow.getElementById("save-template");
  let analysis = null;
  let previewResult = null;
  let maskedProfile = null;
  let mappingDecisions = {};
  let templateState = "none";
  let stopped = false;
  let captchaPending = false;
  let workerEpoch = null;
  let guardState = null;

  function machineStatusFor(text, warning) {
    if (/入力済み/.test(text)) return "filled";
    if (/入力前確認/.test(text)) return "previewed";
    if (/解析済み|CAPTCHA検出・基本情報/.test(text)) return "analyzed";
    if (/人間確認|CAPTCHA|ログイン/.test(text)) return "human-review-required";
    if (/停止|遮断|未確認|必要|エラー/.test(text) || warning) return "blocked";
    return "ready";
  }

  function setStatus(text, warning = false, machineStatus = null) {
    status.textContent = `${text}・送信ロック中`;
    status.classList.toggle("warning", warning);
    host.setAttribute(
      "data-kensho-status",
      machineStatus || machineStatusFor(text, warning)
    );
  }

  function sendMessage(message) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, (response) => resolve(response || {}));
    });
  }

  document.addEventListener(INSTANCE_EVENT, (event) => {
    let other = null;
    try {
      other = JSON.parse(String(event.detail || ""));
    } catch (_error) {
      other = null;
    }
    if (
      !other ||
      (other.extensionId === extensionId && other.version === extensionVersion)
    ) {
      return;
    }
    stopped = true;
    document.documentElement.setAttribute("data-kensho-duplicate-extension", "true");
    disableInstance(host);
    notifyDuplicate(other.extensionId, other.version);
  });
  announceInstance();

  function requestGuardState() {
    document.dispatchEvent(new CustomEvent("kensho-guard-status-request"));
  }

  async function refreshOriginAccess() {
    const response = await sendMessage({ type: "GET_ORIGIN_ACCESS" });
    const enabled = Boolean(response.ok && response.allowed);
    shadow.getElementById("enable-origin").disabled = enabled;
    shadow.getElementById("disable-origin").disabled = !enabled;
    shadow.getElementById("enable-origin").textContent = enabled
      ? "このサイトでは自動起動中"
      : "このサイトで常に有効にする";
  }

  async function refreshSessionStatus() {
    const response = await sendMessage({ type: "GET_SESSION_STATUS" });
    if (response.ok && !response.profileLoaded && !analysis) {
      setStatus("プロフィール未設定・読み込みが必要", true);
    }
  }

  document.addEventListener("kensho-guard-status", (event) => {
    try {
      guardState =
        typeof event.detail === "string"
          ? JSON.parse(event.detail)
          : event.detail || null;
    } catch (_error) {
      guardState = null;
    }
    if (!guardState?.integrity) {
      stopped = true;
      setStatus("送信ガード改変を検出・安全停止", true);
    }
  });
  document.addEventListener("kensho-isolated-submit-blocked", (event) => {
    stopped = true;
    setStatus(`自動送信を遮断（${event.detail?.reason || "isolated"}）`, true);
  });
  requestGuardState();
  refreshOriginAccess().catch(() => {
    setStatus("サイト権限を確認できません", true);
  });
  refreshSessionStatus().catch(() => {
    setStatus("プロフィール状態を確認できません", true);
  });

  function mappingComplete() {
    return Boolean(
      previewResult &&
        previewResult.items.every(
          (item) => !item.requiresHumanMapping || Boolean(mappingDecisions[item.fieldId])
        )
    );
  }

  function confirmedProfileKeys() {
    if (!previewResult) return [];
    const keys = [];
    const appendKey = (key) => {
      if (key && key !== "unknown" && !keys.includes(key)) keys.push(key);
    };
    for (const item of previewResult.items || []) {
      const decision = mappingDecisions[item.fieldId];
      if (decision?.action === "skip") continue;
      const key = decision?.profileKey || item.profileKey || item.fieldType;
      if (key === "full_name") {
        appendKey("last_name");
        appendKey("first_name");
        continue;
      }
      if (key === "full_name_kana") {
        appendKey("last_name_kana");
        appendKey("first_name_kana");
        continue;
      }
      appendKey(key);
    }
    return keys;
  }

  function renderPreview(result) {
    previewBox.replaceChildren();
    for (const item of result.items || []) {
      const row = document.createElement("div");
      row.className = "item";
      row.setAttribute("data-kensho-field-id", item.fieldId);
      const title = document.createElement("div");
      title.textContent = `${item.fieldType}: ${item.maskedValue}`;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent =
        `対象: ${item.label} / 信頼度: ${item.confidence} / ` +
        `根拠: ${(item.evidence || []).join(", ") || "要確認"}`;
      row.append(title, meta);
      if (item.requiresHumanMapping) {
        const actions = document.createElement("div");
        actions.className = "mapping-actions";
        const select = document.createElement("select");
        select.setAttribute("data-kensho-mapping-action", "select");
        select.setAttribute("data-field-id", item.fieldId);
        for (const key of [item.fieldType, "last_name", "first_name", "email", "phone", "postal_code", "prefecture", "city", "street", "building", "birth_date", "gender"]) {
          if (key === "unknown") continue;
          if (Array.from(select.options).some((option) => option.value === key)) continue;
          const option = document.createElement("option");
          option.value = key;
          option.textContent = key;
          select.appendChild(option);
        }
        const approve = document.createElement("button");
        approve.type = "button";
        approve.textContent = "この対応を承認";
        approve.setAttribute("data-kensho-mapping-action", "approve");
        approve.setAttribute("data-field-id", item.fieldId);
        const skip = document.createElement("button");
        skip.type = "button";
        skip.textContent = "入力しない";
        skip.setAttribute("data-kensho-mapping-action", "skip");
        skip.setAttribute("data-field-id", item.fieldId);
        actions.append(select, approve, skip);
        row.appendChild(actions);
      }
      previewBox.appendChild(row);
    }
    for (const warning of result.warnings || []) {
      const row = document.createElement("div");
      row.className = "item meta";
      row.textContent = `要確認: ${warning.reason}`;
      previewBox.appendChild(row);
    }
    fillButton.disabled = Boolean(!mappingComplete() || result.blocked || captchaPending || stopped);
    saveTemplateButton.disabled = Boolean(!mappingComplete() || result.blocked || captchaPending || stopped);
    approveSafeButton.disabled = Boolean(
      stopped ||
        result.blocked ||
        captchaPending ||
        !(result.items || []).some(
          (item) =>
            item.requiresHumanMapping &&
            item.confidence >= 0.95 &&
            item.fieldType !== "unknown"
        )
    );
  }

  async function analyzeForm() {
    if (stopped) return;
    const session = await sendMessage({ type: "GET_SESSION_STATUS" });
    workerEpoch = session.workerEpoch || null;
    requestGuardState();
    if (!guardState?.integrity || !guardState?.installedAtDocumentStart) {
      stopped = true;
      setStatus("ページ再読込後の再有効化が必要", true);
      return;
    }
    analysis = root.KenshoExtension.FormDetector.scan(document);
    host.setAttribute(
      "data-kensho-form-fingerprint",
      String(analysis.formFingerprint || "")
    );
    previewResult = null;
    maskedProfile = null;
    mappingDecisions = {};
    captchaPending = Boolean(analysis.captchaDetected);
    previewBox.replaceChildren();
    if (analysis.loginRequired) {
      stopped = true;
      setStatus("ログイン必要・人間確認待ち", true);
      return;
    }
    if (analysis.unsupportedIframes > 0) {
      stopped = true;
      setStatus("iframe非対応・人間確認待ち", true);
      return;
    }
    if (analysis.unsupportedForm) {
      stopped = true;
      setStatus("解析不能フォーム・人間確認待ち", true);
      return;
    }
    if (!analysis.fields.length && !analysis.manualReviewFields.length) {
      setStatus("入力欄を検出できません・再解析してください", true, "blocked");
      return;
    }
    const template = await sendMessage({
      type: "GET_FORM_TEMPLATE",
      fingerprint: analysis.formFingerprint,
    });
    templateState = template.status || "none";
    if (templateState === "matched") {
      for (const saved of template.fields || []) {
        const field = analysis.fields.find((candidate) => candidate.path === saved.path);
        if (field) {
          mappingDecisions[field.fieldId] = {
            action: "approve",
            profileKey: saved.approvedProfileKey || field.fieldType,
          };
        }
      }
      setStatus(`解析済み（${analysis.detectedFieldCount}項目）・確認済みフォーム`);
    } else if (templateState === "changed") {
      setStatus("フォーム変更・欄対応の再確認が必要", true);
    } else if (captchaPending) {
      setStatus("CAPTCHA検出・本人確認が必要", true);
    } else {
      setStatus(`解析済み（${analysis.detectedFieldCount}項目）・初回欄対応確認`);
    }
  }

  shadow.getElementById("analyze").addEventListener("click", () => {
    analyzeForm().catch(() =>
      setStatus("フォーム解析に失敗しました・再解析してください", true)
    );
  });

  shadow.getElementById("preview-button").addEventListener("click", async () => {
    if (stopped || !analysis) {
      setStatus("先にフォーム解析が必要", true);
      return;
    }
    const response = await sendMessage({ type: "GET_PROFILE_PREVIEW" });
    if (workerEpoch && response.workerEpoch !== workerEpoch) {
      await sendMessage({ type: "CLEAR_SESSION_PROFILE" });
      stopped = true;
      setStatus("プロフィールの再読込が必要", true);
      return;
    }
    if (!response.ok || !response.profile) {
      setStatus("一時プロフィール未設定", true);
      return;
    }
    maskedProfile = response.profile;
    previewResult = root.KenshoExtension.FormFiller.previewMasked(
      analysis,
      maskedProfile,
      {templateApproved: templateState === "matched", mappingDecisions}
    );
    renderPreview(previewResult);
    if (templateState === "changed") {
      setStatus("フォーム変更・欄対応の再確認が必要", true);
    } else if (captchaPending) {
      setStatus("CAPTCHA検出・本人確認が必要", true);
    } else {
      setStatus(
        previewResult.warnings.length
          ? "入力前確認・欄対応または警告あり"
          : "入力前確認"
      );
    }
  });

  previewBox.addEventListener("click", async (event) => {
    const button = event.target.closest?.("button[data-kensho-mapping-action]");
    if (!button || !previewResult) return;
    const fieldId = button.getAttribute("data-field-id");
    const action = button.getAttribute("data-kensho-mapping-action");
    if (!fieldId || !["approve", "skip"].includes(action)) return;
    const select = previewBox.querySelector(
      `select[data-kensho-mapping-action="select"][data-field-id="${CSS.escape(fieldId)}"]`
    );
    mappingDecisions[fieldId] = {
      action,
      profileKey: select?.value || null,
    };
    previewResult = root.KenshoExtension.FormFiller.previewMasked(
      analysis,
      maskedProfile,
      {templateApproved: templateState === "matched", mappingDecisions}
    );
    renderPreview(previewResult);
    setStatus("欄対応を更新しました・入力前確認", false, "previewed");
  });

  approveSafeButton.addEventListener("click", () => {
    if (!previewResult || !maskedProfile || stopped) return;
    for (const item of previewResult.items || []) {
      if (
        item.requiresHumanMapping &&
        item.confidence >= 0.95 &&
        item.fieldType !== "unknown"
      ) {
        mappingDecisions[item.fieldId] = {
          action: "approve",
          profileKey: item.profileKey || item.fieldType,
        };
      }
    }
    previewResult = root.KenshoExtension.FormFiller.previewMasked(
      analysis,
      maskedProfile,
      {templateApproved: templateState === "matched", mappingDecisions}
    );
    renderPreview(previewResult);
    setStatus("高信頼の欄を承認しました・残りを確認してください", false, "previewed");
  });

  saveTemplateButton.addEventListener("click", async () => {
    if (!analysis || !mappingComplete()) {
      setStatus("全ての入力候補の欄対応を確認してください", true);
      return;
    }
    const template = root.KenshoExtension.FormDetector.templateFromAnalysis(
      analysis,
      mappingDecisions
    );
    const response = await sendMessage({type: "SAVE_FORM_TEMPLATE", template});
    if (!response.ok || !response.saved) {
      setStatus("欄対応を保存できません・安全停止", true);
      return;
    }
    templateState = "matched";
    previewResult = root.KenshoExtension.FormFiller.previewMasked(
      analysis,
      maskedProfile,
      {templateApproved: true, mappingDecisions}
    );
    renderPreview(previewResult);
    setStatus("欄対応を保存しました・入力前確認", false, "previewed");
  });

  shadow.getElementById("fill").addEventListener("click", async () => {
    if (stopped || !previewResult) {
      setStatus("入力前確認が必要", true);
      return;
    }
    requestGuardState();
    if (!guardState?.integrity || !guardState?.installedAtDocumentStart) {
      stopped = true;
      setStatus("送信ガード未確認・安全停止", true);
      return;
    }
    let bridgeStatus = await sendMessage({type: "GET_BRIDGE_CAPABILITY_STATUS"});
    if (!bridgeStatus?.available) {
      const requested = await sendMessage({
        type: "REQUEST_BRIDGE_CAPABILITY",
        fingerprint: analysis.formFingerprint,
        profileKeys: confirmedProfileKeys(),
      });
      if (requested?.ok) {
        bridgeStatus = await sendMessage({type: "GET_BRIDGE_CAPABILITY_STATUS"});
      }
    }
    const response = bridgeStatus?.available
      ? await sendMessage({
          type: "CONSUME_BRIDGE_PROFILE",
          origin: window.location.origin,
          fingerprint: analysis.formFingerprint,
        })
      : await sendMessage({type: "CONSUME_SESSION_PROFILE"});
    if (workerEpoch && response.workerEpoch !== workerEpoch) {
      stopped = true;
      setStatus("Service Worker再起動・安全停止", true);
      return;
    }
    if (!response.ok || !response.profile) {
      setStatus("一時プロフィール未設定", true);
      return;
    }
    const filled = await root.KenshoExtension.FormFiller.fillAndVerify(
      previewResult,
      response.profile,
      analysis,
      {templateApproved: templateState === "matched", mappingDecisions}
    );
    response.profile = null;
    host.setAttribute(
      "data-kensho-verification",
      JSON.stringify(filled.verification || {})
    );
    if (filled.status === "POST_FILL_VERIFICATION_PASSED") {
      setStatus(`入力済み（${filled.filledCount}項目）・人間確認待ち`);
    } else if (filled.status === "HUMAN_MAPPING_REQUIRED") {
      setStatus("入力前確認が必要・欄対応を承認してください", true);
    } else if (filled.status.includes("ROLLED_BACK")) {
      setStatus("入力検証不一致・全項目をロールバックしました", true);
    } else {
      stopped = true;
      setStatus("安全停止・人間確認が必要", true);
    }
  });

  shadow.getElementById("rollback").addEventListener("click", () => {
    const result = root.KenshoExtension.FormFiller.rollback();
    setStatus(`入力を元に戻しました（${result.restoredCount}項目）`);
  });

  shadow.getElementById("open-profile").addEventListener("click", async () => {
    const response = await sendMessage({ type: "OPEN_PROFILE_OPTIONS" });
    if (!response.ok) setStatus("プロフィール画面を開けません", true);
  });

  shadow.getElementById("stop").addEventListener("click", () => {
    stopped = true;
    setStatus("問題あり・停止", true);
  });

  shadow.getElementById("clear").addEventListener("click", async () => {
    root.KenshoExtension.FormFiller.rollback();
    await sendMessage({ type: "CLEAR_SESSION_PROFILE" });
    analysis = null;
    previewResult = null;
    maskedProfile = null;
    mappingDecisions = {};
    templateState = "none";
    captchaPending = false;
    stopped = true;
    previewBox.replaceChildren();
    setStatus("セッション情報消去済み・停止");
  });

  shadow.getElementById("enable-origin").addEventListener("click", async () => {
    setStatus("サイト権限を確認中");
    const response = await sendMessage({ type: "REQUEST_ORIGIN_ACCESS" });
    if (!response.ok || !response.granted) {
      setStatus("サイト権限が許可されませんでした", true);
      return;
    }
    setStatus("サイト権限を保存済み・自動再読込します");
  });

  shadow.getElementById("disable-origin").addEventListener("click", async () => {
    root.KenshoExtension.FormFiller.rollback();
    const response = await sendMessage({ type: "DISABLE_ORIGIN_ACCESS" });
    if (!response.ok || !response.removed) {
      setStatus("サイト権限を解除できません", true);
      return;
    }
    document.documentElement.removeAttribute("data-kensho-extension-ready");
    host.remove();
  });

  function scheduleAutomaticAnalysis() {
    let attempts = 0;
    const attempt = () => {
      if (analysis || stopped) return;
      requestGuardState();
      if (!guardState?.integrity || !guardState?.installedAtDocumentStart) {
        attempts += 1;
        if (attempts < 6) {
          setTimeout(attempt, 50);
          return;
        }
        stopped = true;
        setStatus("送信ガード未確認・フォーム解析を開始できません", true);
        return;
      }
      analyzeForm().catch(() =>
        setStatus("フォーム解析に失敗しました・再解析してください", true)
      );
    };
    setTimeout(attempt, 0);
  }

  scheduleAutomaticAnalysis();

  document.addEventListener("kensho-submit-blocked", (event) => {
    stopped = true;
    setStatus(`自動送信を遮断（${event.detail?.reason || "unknown"}）`, true);
  });
})(typeof globalThis !== "undefined" ? globalThis : this);
