from __future__ import annotations

from typing import Mapping

from .form_detector import detect_fields
from .form_filler import (
    apply_field_plan_with_overrides,
    plan_field_filling_with_age,
)
from .models import FillResult
from .submission_guard import submission_guard_snapshot


HUMAN_HANDOFF_SCRIPT = r"""
(() => {
  const existing = document.querySelector('[data-kensho-human-handoff]');
  if (existing) return true;
  const host = document.createElement('div');
  host.setAttribute('data-kensho-human-handoff', 'locked');
  host.style.cssText = [
    'position:fixed',
    'right:16px',
    'bottom:16px',
    'z-index:2147483647',
    'width:280px',
    'height:52px'
  ].join(';');
  const shadow = host.attachShadow({mode: 'closed'});
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = '本人操作へ切り替える（送信ロック解除）';
  button.setAttribute('aria-label', '本人操作へ切り替える');
  button.style.cssText = [
    'width:100%',
    'height:100%',
    'border:0',
    'border-radius:6px',
    'background:#111827',
    'color:#fff',
    'font:600 14px sans-serif',
    'cursor:pointer',
    'box-shadow:0 4px 16px rgba(0,0,0,.25)'
  ].join(';');
  button.addEventListener('click', event => {
    if (!event.isTrusted) return;
    const guard = window.__kenshoSubmitGuard;
    if (!guard?.active || typeof guard.release !== 'function') {
      button.textContent = '送信ガードを確認できません';
      return;
    }
    guard.release();
    host.setAttribute('data-kensho-human-handoff', 'released');
    button.textContent = '本人操作モード：最終送信は本人が行ってください';
    button.disabled = true;
    button.style.background = '#166534';
  });
  shadow.append(button);
  document.documentElement.append(host);
  return true;
})()
"""


def prepare_page_without_submit(
    page,
    profile: Mapping[str, str],
    *,
    prize_choice: str = "",
    free_text: str = "",
) -> FillResult:
    guard = submission_guard_snapshot(page)
    if not page.evaluate("Boolean(window.__kenshoSubmitGuard?.active)"):
        raise RuntimeError("submission_guard_not_active")

    runtime_profile = {str(key): str(value) for key, value in profile.items()}
    if prize_choice:
        runtime_profile["prize_choice"] = prize_choice
    answer_overrides = {
        "opinion": free_text,
        "free_text": free_text,
    }
    fields = plan_field_filling_with_age(
        detect_fields(page),
        runtime_profile,
        allow_age_fill=True,
        answer_overrides=answer_overrides,
        allow_ai_answer_fill=bool(free_text),
    )
    filled_fields, missing_fields = apply_field_plan_with_overrides(
        page,
        fields,
        runtime_profile,
        answer_overrides=answer_overrides,
        allow_ai_answer_fill=bool(free_text),
    )
    after_guard = submission_guard_snapshot(page)
    if int(after_guard.get("blockedAttempts", 0)) != int(
        guard.get("blockedAttempts", 0)
    ):
        raise RuntimeError("unexpected_submit_attempt")

    return FillResult(
        campaign_id="direct-url",
        decision="fill",
        filled_fields=filled_fields,
        missing_fields=missing_fields,
        submitted=False,
        notes="direct URL prepared without submission",
    )


def install_human_handoff_control(page) -> None:
    installed = page.evaluate(HUMAN_HANDOFF_SCRIPT)
    if installed is not True:
        raise RuntimeError("human_handoff_control_install_failed")
