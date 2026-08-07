from __future__ import annotations

from typing import Any


INSTALL_SCRIPT = r"""
(() => {
  if (window.__kenshoSubmitGuard?.active) return window.__kenshoSubmitGuard.snapshot();
  const state = { active: true, blockedAttempts: 0, reasons: [] };
  const block = (reason, event) => {
    state.blockedAttempts += 1;
    state.reasons.push(reason);
    if (event) { event.preventDefault(); event.stopImmediatePropagation(); }
    return false;
  };
  const onSubmit = (event) => block('submit_event', event);
  const onClick = (event) => {
    const target = event.target?.closest?.('button[type=submit], input[type=submit]');
    if (target) block('submit_control_click', event);
  };
  const onKeydown = (event) => {
    if (event.key === 'Enter' && event.target?.form) block('enter_key', event);
  };
  const originalSubmit = HTMLFormElement.prototype.submit;
  const originalRequestSubmit = HTMLFormElement.prototype.requestSubmit;
  HTMLFormElement.prototype.submit = function() { return block('form.submit'); };
  HTMLFormElement.prototype.requestSubmit = function() { return block('requestSubmit'); };
  document.addEventListener('submit', onSubmit, true);
  document.addEventListener('click', onClick, true);
  document.addEventListener('keydown', onKeydown, true);
  state.snapshot = () => ({ blockedAttempts: state.blockedAttempts, reasons: [...state.reasons] });
  state.release = () => {
    document.removeEventListener('submit', onSubmit, true);
    document.removeEventListener('click', onClick, true);
    document.removeEventListener('keydown', onKeydown, true);
    HTMLFormElement.prototype.submit = originalSubmit;
    HTMLFormElement.prototype.requestSubmit = originalRequestSubmit;
    state.active = false;
    return state.snapshot();
  };
  window.__kenshoSubmitGuard = state;
  return state.snapshot();
})()
"""


RELEASE_SCRIPT = r"""
(() => {
  if (!window.__kenshoSubmitGuard) return { blockedAttempts: 0, reasons: [] };
  return window.__kenshoSubmitGuard.release();
})()
"""

SNAPSHOT_SCRIPT = r"""
(() => {
  if (!window.__kenshoSubmitGuard) return { blockedAttempts: 0, reasons: [] };
  return window.__kenshoSubmitGuard.snapshot();
})()
"""


def install_submission_guard_on_context(context) -> None:
    """Install the guard in every document created by this context."""
    context.add_init_script(INSTALL_SCRIPT)


def install_submission_guard(page) -> dict[str, Any]:
    result = page.evaluate(INSTALL_SCRIPT)
    return result if isinstance(result, dict) else {"blockedAttempts": 0, "reasons": []}


def release_submission_guard(page) -> dict[str, Any]:
    result = page.evaluate(RELEASE_SCRIPT)
    return result if isinstance(result, dict) else {"blockedAttempts": 0, "reasons": []}


def submission_guard_snapshot(page) -> dict[str, Any]:
    result = page.evaluate(SNAPSHOT_SCRIPT)
    return result if isinstance(result, dict) else {"blockedAttempts": 0, "reasons": []}
