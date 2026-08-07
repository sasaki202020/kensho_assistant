(function installSubmitGuard() {
  "use strict";

  if (window.__KENSHO_SUBMIT_GUARD__?.state) {
    document.documentElement?.setAttribute("data-kensho-submit-guard", "true");
    return;
  }

  let blockedAttempts = 0;
  const reasons = [];
  let integrity = true;
  const installedAtDocumentStart = document.readyState === "loading";
  const guardedRoots = new WeakSet();
  const submitSelector =
    'button[type="submit"], input[type="submit"], input[type="image"], button:not([type])';
  const originalSubmit = HTMLFormElement.prototype.submit;
  const originalRequestSubmit = HTMLFormElement.prototype.requestSubmit;
  const originalClick = HTMLElement.prototype.click;
  const originalAttachShadow = Element.prototype.attachShadow;

  function record(reason, event) {
    blockedAttempts += 1;
    reasons.push(reason);
    if (event) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
    document.dispatchEvent(
      new CustomEvent("kensho-submit-blocked", {
        detail: { reason, blockedAttempts },
      })
    );
    return false;
  }

  function isSubmitControl(element) {
    if (!element || !element.matches) return false;
    return Boolean(element.form && element.matches(submitSelector));
  }

  function onSubmit(event) {
    record("submit_event", event);
  }

  function onKeydown(event) {
    if (event.key === "Enter" && event.target?.form) {
      record("enter_key", event);
    }
  }

  function onClick(event) {
    const submitControl = event
      .composedPath()
      .find((candidate) => isSubmitControl(candidate));
    if (submitControl) record("submit_click", event);
  }

  function guardRoot(root) {
    if (!root || guardedRoots.has(root)) return;
    guardedRoots.add(root);
    root.addEventListener("submit", onSubmit, true);
    root.addEventListener("keydown", onKeydown, true);
    root.addEventListener("click", onClick, true);

    for (const element of root.querySelectorAll?.("*") || []) {
      if (element.shadowRoot) guardRoot(element.shadowRoot);
    }
  }

  const guardedSubmit = function guardedSubmit() {
    return record("form.submit");
  };
  const guardedRequestSubmit = function guardedRequestSubmit() {
    return record("form.requestSubmit");
  };
  const guardedClick = function guardedClick() {
    if (isSubmitControl(this)) return record("automatic_submit_click");
    return originalClick.call(this);
  };
  const guardedAttachShadow = function guardedAttachShadow(init) {
    const shadowRoot = originalAttachShadow.call(this, init);
    guardRoot(shadowRoot);
    return shadowRoot;
  };

  function lockMethod(prototype, name, guardedMethod) {
    Object.defineProperty(prototype, name, {
      configurable: false,
      enumerable: false,
      get() {
        return guardedMethod;
      },
      set() {
        if (integrity) {
          integrity = false;
          record(`guard_modified:${name}`);
        }
      },
    });
  }

  lockMethod(HTMLFormElement.prototype, "submit", guardedSubmit);
  lockMethod(HTMLFormElement.prototype, "requestSubmit", guardedRequestSubmit);
  lockMethod(HTMLElement.prototype, "click", guardedClick);
  lockMethod(Element.prototype, "attachShadow", guardedAttachShadow);

  guardRoot(document);

  const observer = new MutationObserver((records) => {
    for (const recordEntry of records) {
      for (const node of recordEntry.addedNodes) {
        if (!(node instanceof Element)) continue;
        if (node.shadowRoot) guardRoot(node.shadowRoot);
        for (const descendant of node.querySelectorAll?.("*") || []) {
          if (descendant.shadowRoot) guardRoot(descendant.shadowRoot);
        }
      }
    }
  });
  observer.observe(document, { childList: true, subtree: true });

  function state() {
    return {
      locked: true,
      integrity,
      installedAtDocumentStart,
      blockedAttempts,
      reasons: reasons.slice(),
      submitted_count_auto: 0,
    };
  }

  function announceState() {
    document.dispatchEvent(
      new CustomEvent("kensho-guard-status", {
        detail: JSON.stringify(state()),
      })
    );
  }

  document.addEventListener("kensho-guard-status-request", announceState);

  const integrityMonitor = setInterval(() => {
    const modified =
      HTMLFormElement.prototype.submit !== guardedSubmit ||
      HTMLFormElement.prototype.requestSubmit !== guardedRequestSubmit ||
      HTMLElement.prototype.click !== guardedClick ||
      Element.prototype.attachShadow !== guardedAttachShadow;
    if (!modified) return;
    integrity = false;
    clearInterval(integrityMonitor);
    record("guard_modified");
    announceState();
  }, 200);

  window.__KENSHO_SUBMIT_GUARD__ = Object.freeze({
    state,
    originalsPresent: Boolean(originalSubmit && originalRequestSubmit && originalClick),
  });
  document.documentElement?.setAttribute("data-kensho-submit-guard", "true");
  document.documentElement?.setAttribute("data-kensho-extension-version", "0.2.0");
  announceState();
})();
