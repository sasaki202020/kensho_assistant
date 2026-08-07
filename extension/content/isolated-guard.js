(function installIsolatedGuard() {
  "use strict";

  if (globalThis.__KENSHO_ISOLATED_GUARD__) return;
  let blockedAttempts = 0;

  function isSubmitControl(element) {
    return Boolean(
      element?.form &&
        element.matches?.(
          'button[type="submit"],input[type="submit"],input[type="image"],button:not([type])'
        )
    );
  }

  function block(reason, event) {
    blockedAttempts += 1;
    event.preventDefault();
    event.stopImmediatePropagation();
    document.dispatchEvent(
      new CustomEvent("kensho-isolated-submit-blocked", {
        detail: { reason, blockedAttempts },
      })
    );
  }

  document.addEventListener("submit", (event) => block("isolated_submit", event), true);
  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Enter" && event.target?.form) block("isolated_enter", event);
    },
    true
  );
  document.addEventListener(
    "click",
    (event) => {
      if (event.composedPath().some(isSubmitControl)) block("isolated_click", event);
    },
    true
  );

  globalThis.__KENSHO_ISOLATED_GUARD__ = Object.freeze({
    state: () => ({
      locked: true,
      blockedAttempts,
      submitted_count_auto: 0,
    }),
  });
})();
