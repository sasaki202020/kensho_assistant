"""Browser stage of ``pilot-nonsubmit`` (Phase 5A: fake sentinel, one candidate, no submit).

Order, fail-closed at every step (cleanup always runs):

1. ``service_worker_network_events()`` wraps ``sync_playwright()``; the
   dedicated extension context is launched exactly like the dedicated path
   (verified build, fresh temporary profile, no real Chrome profile/cookies);
   ``SentinelNetworkMonitor.start()`` runs before any navigation.
2. Navigate; strict ``dedicated_extension_page_state``; extension analysis;
   ``prefill_blocking_reasons`` plus the extension's CAPTCHA/login/iframe
   detectors.  Any reason stops before mapping, profile or capability.
3. Value-free mapping table from the extension panel (フォーム解析 → 入力内容を確認),
   confirmed by the human per field (default "no").  There is no "approve all";
   ``phone``/``postal_code`` are forced to "do not fill" unless
   ``allow_undetectable`` is set, which makes the result UNVERIFIED.
4. ``assisted_session.confirm_pilot_mapping`` reaches MAPPING_CONFIRMED with
   the human-approved keys; the extension performs 入力を実行 through the pilot
   web app capability (fake profile loader only); post-fill verification.
5. Extension rollback, session clear, ``end_pilot_session``, quiet period,
   residue check, lock release, context close (temporary profile removed).

Only counts, fixed reason codes, form labels and profile-key names leave this
module.  The sentinel nonce and values stay in memory; this module never
clicks submit/confirm/consent/CAPTCHA controls.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from . import assisted_session
from . import browser_manager
from .browser_manager import (
    close_browser_safely,
    dedicated_extension_page_state,
    launch_dedicated_kensho_context,
    validate_dedicated_target_url,
)
from .extension_bridge import ALLOWED_PAYLOAD_KEYS
from .pilot_network_monitor import SentinelNetworkMonitor, service_worker_network_events
from .pilot_residue import check_sentinel_residue

PASS = "PASS"
FAIL = "FAIL"
STOPPED = "STOPPED"
UNVERIFIED = "UNVERIFIED"
NOT_RUN = "NOT_RUN"

STAGE_STEPS = (
    "launch",
    "monitor_before_navigation",
    "navigate",
    "dedicated_page_state",
    "prefill_checks",
    "form_fingerprint",
    "mapping_human_confirmation",
    "mapping_confirmed",
    "fill",
    "post_fill_verification",
    "rollback",
    "session_clear",
    "quiet_period",
    "residue",
    "lock_release",
    "context_close",
)

_HOST = "#kensho-assistant-overlay-host"
_SAFE_CODE = re.compile(r"[A-Za-z0-9_:.\-]{1,96}")
_FIELD_ID = re.compile(r"[A-Za-z0-9_:.\-]{1,128}")
_PROFILE_KEY = re.compile(r"[a-z][a-z_]{0,39}")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2066-\u2069]")

_SENSITIVE_EXTENSION_KEYS = (
    "kenshoSessionProfile",
    "kenshoBridgeCapability",
    "kenshoControlCapability",
    "kenshoProgressCapability",
)


class _Stop(Exception):
    def __init__(self, step: str, reason: str, status: str = FAIL) -> None:
        super().__init__(reason)
        self.step = step
        self.reason = reason
        self.status = status


def _code(exc: BaseException) -> str:
    """A reason code that can never carry page content or values."""
    text = str(exc)
    if isinstance(exc, (RuntimeError, ValueError)) and _SAFE_CODE.fullmatch(text):
        return text
    return type(exc).__name__


def interactive_mapping_confirmer(field: Mapping[str, object]) -> bool:
    """CLI confirmer: one field at a time, only an explicit ``y`` approves."""
    print(
        f"[{field.get('index')}/{field.get('total')}] "
        f"欄ラベル: {field.get('label')} / 分類: {field.get('field_type')} / "
        f"入力種別: {field.get('input_type')} / 提案キー: {field.get('proposed_profile_key')}"
    )
    try:
        answer = input("  この欄にだけ架空センチネルを入力しますか？ [y/N]: ")
    except EOFError:
        return False
    return str(answer).strip().lower() == "y"


# ----------------------------------------------------------------- panel I/O

def _extension_worker(context, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for worker in list(context.service_workers):
            url = str(worker.url or "")
            if url.startswith("chrome-extension://") and url.endswith("/service-worker.js"):
                return worker
        try:
            context.wait_for_event("serviceworker", timeout=500)
        except Exception:
            pass
    raise RuntimeError("extension_worker_not_found")


def _wait_for_registration(context, timeout: float = 10.0):
    """Wait for both content-script registrations; return the live worker.

    The first worker instance seen right after launch can be closed and
    restarted by Chromium, so the worker is re-acquired on every attempt.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            worker = _extension_worker(context, timeout=max(deadline - time.monotonic(), 0.1))
            count = worker.evaluate(
                """async () => {
                  if (!chrome.scripting?.getRegisteredContentScripts) return 0;
                  const scripts = await chrome.scripting.getRegisteredContentScripts();
                  return scripts.filter(item => item.id.startsWith("kensho-")).length;
                }"""
            )
        except Exception:
            count = None
        if count == 2:
            return worker
        time.sleep(0.05)
    raise RuntimeError("dynamic_registration_timeout")


def _machine_status(page) -> str:
    try:
        return str(page.evaluate(
            "() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus || ''"
        ) or "")
    except Exception:
        return ""


def _wait_machine_status(page, allowed: list[str], timeout_ms: int = 10_000, *, not_in: bool = False) -> str:
    handle = page.wait_for_function(
        """([allowed, notIn]) => {
          const s = document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus || '';
          const hit = notIn ? (s && !allowed.includes(s)) : allowed.includes(s);
          return hit ? s : false;
        }""",
        arg=[allowed, not_in],
        timeout=timeout_ms,
    )
    return str(handle.json_value())


def _wait_status_text(page, needles: list[str], timeout_ms: int = 10_000) -> str:
    """Return the first matching fixed needle of the panel status line."""
    handle = page.wait_for_function(
        """needles => {
          const text = document.querySelector('#kensho-assistant-overlay-host')
            ?.shadowRoot?.querySelector('#status')?.textContent || '';
          return needles.find(needle => text.includes(needle)) || false;
        }""",
        arg=needles,
        timeout=timeout_ms,
    )
    return str(handle.json_value())


def _click(page, selector: str) -> None:
    page.locator(_HOST).locator(selector).click(timeout=10_000)


def _live_worker(context, extension_id: str):
    """The current worker of the pinned extension id (it may have restarted)."""
    worker = _extension_worker(context, timeout=5.0)
    if urlsplit(str(worker.url)).hostname != extension_id:
        raise RuntimeError("dedicated_extension_worker_mismatch")
    return worker


def _isolated_inspect(context, extension_id: str, url: str, field_ids: list[str]) -> dict[str, object] | None:
    """Security booleans and input types from the extension's isolated world."""
    try:
        return _live_worker(context, extension_id).evaluate(
            """async ({url, ids}) => {
              const tabs = (await chrome.tabs.query({})).filter(tab => tab.url === url);
              if (tabs.length !== 1) throw new Error('candidate_tab_not_unique');
              const [current] = await chrome.scripting.executeScript({
                target: {tabId: tabs[0].id, frameIds: [0]}, world: 'ISOLATED',
                func: ids => {
                  const api = globalThis.KenshoExtension?.FormDetector;
                  if (!api) return null;
                  const s = api.securityStatus(document);
                  const types = {};
                  for (const id of ids) {
                    const element = api.resolveElement(id);
                    types[id] = element ? String(element.type || element.tagName || '').toLowerCase() : '';
                  }
                  return {security: {
                    captcha: Boolean(s.captchaDetected), login: Boolean(s.loginRequired),
                    iframes: Number(s.unsupportedIframes || 0), canvas: Boolean(s.unsupportedCanvas),
                    closed_shadow: Boolean(s.closedShadowMarker)}, types};
                },
                args: [ids],
              });
              return current?.result || null;
            }""",
            {"url": url, "ids": field_ids},
        )
    except Exception:
        return None


def _security_reasons(inspected: Mapping[str, object] | None) -> list[str]:
    security = inspected.get("security") if isinstance(inspected, Mapping) else None
    if not isinstance(security, Mapping):
        return ["security_status_unavailable"]
    reasons = []
    if security.get("captcha"):
        reasons.append("captcha_detected")
    if security.get("login"):
        reasons.append("login_required")
    if security.get("iframes"):
        reasons.append("unsupported_iframe")
    if security.get("canvas"):
        reasons.append("unsupported_canvas")
    if security.get("closed_shadow"):
        reasons.append("closed_shadow_root")
    return reasons


def _mapping_rows(page) -> list[dict[str, object]]:
    rows = page.evaluate(
        """() => {
          const box = document.querySelector('#kensho-assistant-overlay-host')
            ?.shadowRoot?.querySelector('#preview');
          if (!box) return null;
          return Array.from(box.querySelectorAll('[data-kensho-field-id]'), row => {
            const title = row.firstElementChild?.textContent || '';
            const select = row.querySelector('select[data-kensho-mapping-action="select"]');
            return {
              field_id: row.getAttribute('data-kensho-field-id') || '',
              field_type: title.split(':')[0].trim(),
              meta: row.querySelector('.meta')?.textContent || '',
              proposed: select ? String(select.value || '') : '',
              human_mappable: Boolean(
                row.querySelector('button[data-kensho-mapping-action="approve"]') &&
                row.querySelector('button[data-kensho-mapping-action="skip"]') && select),
            };
          });
        }"""
    )
    if not isinstance(rows, list):
        raise RuntimeError("mapping_table_unavailable")
    parsed = []
    for row in rows:
        field_id = str(row.get("field_id", ""))
        if not _FIELD_ID.fullmatch(field_id):
            raise RuntimeError("mapping_field_id_invalid")
        meta = str(row.get("meta", ""))
        label = meta.split(" / 信頼度: ", 1)[0]
        label = label[len("対象: "):] if label.startswith("対象: ") else ""
        # Page-controlled text reaches the console: no control/bidi characters.
        label = _CONTROL_CHARS.sub(" ", label).strip()[:120]
        field_type = str(row.get("field_type", ""))
        field_type = field_type if _PROFILE_KEY.fullmatch(field_type) else "unknown"
        proposed = str(row.get("proposed") or field_type)
        proposed = proposed if _PROFILE_KEY.fullmatch(proposed) else "unknown"
        parsed.append({
            "field_id": field_id,
            "label": label,
            "field_type": field_type,
            "proposed_profile_key": proposed,
            "human_mappable": bool(row.get("human_mappable")),
        })
    return parsed


def _expand(key: str) -> list[str]:
    if key == "full_name":
        return ["last_name", "first_name"]
    if key == "full_name_kana":
        return ["last_name_kana", "first_name_kana"]
    return [key]


def _controls(page) -> list[list[object]]:
    """All page form controls (the extension panel is in a shadow root)."""
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('input, select, textarea'), e => [
          e.tagName.toLowerCase(), String(e.type || ''), String(e.name || e.id || ''),
          String(e.value ?? ''), Boolean(e.checked), Number(e.selectedIndex ?? -1)])"""
    )


def _contains(value: str, key: str, fake: Mapping[str, str], undetectable: set[str]) -> bool:
    expected = str(fake.get(key, "") or "")
    if not expected or not value:
        return False
    return value == expected if key in undetectable else expected in value


def _post_fill_counts(before, after, fake, approved_keys, undetectable) -> dict[str, object]:
    if len(before) != len(after) or any(b[:3] != a[:3] for b, a in zip(before, after)):
        return {"structure_unchanged": False, "changed_count": None,
                "target_matched_count": 0, "unrelated_changed_count": None,
                "unapproved_value_count": None}
    other_keys = [key for key in fake if key not in approved_keys]
    changed = [index for index, (b, a) in enumerate(zip(before, after)) if b != a]
    matched = 0
    for index in changed:
        b, a = before[index], after[index]
        same_state = b[4] == a[4]
        if same_state and any(_contains(str(a[3]), key, fake, undetectable) for key in approved_keys):
            matched += 1
    unapproved = sum(
        1 for control in after
        if any(_contains(str(control[3]), key, fake, undetectable) for key in other_keys)
    )
    return {
        "structure_unchanged": True,
        "changed_count": len(changed),
        "target_matched_count": matched,
        "unrelated_changed_count": len(changed) - matched,
        "unapproved_value_count": unapproved,
    }


# ------------------------------------------------------------------- stage

def run_browser_stage(
    ctx,
    cfg,
    preconditions: Mapping[str, object],
    *,
    approved_origins_path: Path,
) -> dict[str, object]:
    """Run the Phase 5A browser stage; returns only value-free evidence."""
    output: Callable[..., None] = cfg.output or print
    manifest = ctx.manifest
    url = manifest.url
    fake = ctx.fake_profile
    nonce = str(fake.nonce)
    fake_values = dict(fake.values)  # in memory only; never written
    undetectable = set(fake.undetectable_keys)
    run_dir = Path(ctx.storage.run_dir)

    steps = {name: NOT_RUN for name in STAGE_STEPS}
    evidence: dict[str, object] = {
        "steps": steps,
        "stop_reason": "",
        "failure_reasons": [],
        "form_fingerprint": "",
        "expected_fingerprint": manifest.expected_fingerprint,
        "mapping": [],
        "approved_profile_keys": [],
        "page_state": {},
        "prefill_blocking_reasons": [],
        "post_fill": {},
        "rollback": {},
        "session_clear": {},
        "monitor": {"status": NOT_RUN},
        "residue": {"status": NOT_RUN},
        "runtime_profile_removed": None,
    }

    def fail(step: str, reason: str, status: str = FAIL) -> None:
        steps[step] = status
        evidence["failure_reasons"].append(f"{step}:{reason}")

    context = None
    worker = None
    page = None
    monitor = None
    extension_id = ""
    fill_started = False
    mapping_confirmed = False
    before_controls: list[list[object]] | None = None
    navigations = {"count": 0, "armed": False}

    with service_worker_network_events(), sync_playwright() as playwright:
        try:
            # 1. launch + monitor before navigation ---------------------------
            try:
                validate_dedicated_target_url(url, approved_origins_path=approved_origins_path)
                context, _browser, verified = launch_dedicated_kensho_context(
                    playwright,
                    run_id=f"pilot-{ctx.pilot_run_id[:12]}",
                    project_root=Path(cfg.project_root),
                    runtime_profiles_root=cfg.runtime_profiles_root,
                    headless=bool(cfg.headless),
                    extra_args=tuple(cfg.browser_args),
                )
                if verified["build_sha256"] != preconditions["extension_build_sha256"]:
                    raise RuntimeError("extension_build_changed")
                worker = _wait_for_registration(context)
                extension_id = urlsplit(str(worker.url)).hostname or ""
            except Exception as exc:
                raise _Stop("launch", _code(exc)) from None
            steps["launch"] = PASS

            hash_candidates = [value for key, value in fake_values.items() if key not in undetectable]
            monitor = SentinelNetworkMonitor(
                nonce, sorted(undetectable), extension_id, hash_candidates=hash_candidates
            )
            monitor.start(context)
            steps["monitor_before_navigation"] = PASS

            # 2. navigate + readiness + prefill -------------------------------
            page = context.pages[0] if context.pages else context.new_page()

            def on_frame_navigated(frame) -> None:
                if navigations["armed"] and frame == page.main_frame:
                    navigations["count"] += 1
            page.on("framenavigated", on_frame_navigated)
            try:
                page.goto(url, wait_until="load", timeout=60_000)
            except Exception as exc:
                raise _Stop("navigate", _code(exc)) from None
            if str(page.url) != url:
                raise _Stop("navigate", "unexpected_url_after_navigation")
            steps["navigate"] = PASS

            state = dedicated_extension_page_state(page)
            evidence["page_state"] = {
                key: state.get(key)
                for key in ("ready", "panel_count", "submit_guard_count", "guard_verified",
                            "submitted_count_auto", "auto_submit_detected", "status",
                            "blocked_reason")
                if key in state
            }
            if (
                state.get("status") != "PASS"
                or state.get("panel_count") != 1
                or state.get("submit_guard_count") != 1
                or state.get("guard_verified") is not True
                or state.get("extension_id") != extension_id
            ):
                raise _Stop("dedicated_page_state", str(state.get("blocked_reason") or "dedicated_extension_not_ready"))
            steps["dedicated_page_state"] = PASS

            # Drop the status mirror so a stale value from the automatic
            # analysis cannot satisfy the wait for this explicit analysis.
            page.evaluate(
                "() => document.querySelector('[data-kensho-extension-root]')"
                "?.removeAttribute('data-kensho-status')"
            )
            _click(page, "#analyze")
            try:
                analysis_status = _wait_machine_status(
                    page, ["analyzed", "human-review-required", "blocked"], 10_000
                )
            except Exception:
                analysis_status = _machine_status(page) or "unknown"
            reasons = list(monitor.prefill_blocking_reasons(page))
            reasons += _security_reasons(_isolated_inspect(context, extension_id, url, []))
            if analysis_status != "analyzed":
                reasons.append("extension_analysis_not_ready")
            evidence["prefill_blocking_reasons"] = sorted(set(reasons))
            if reasons:
                raise _Stop("prefill_checks", "PREFILL_BLOCKED", STOPPED)
            steps["prefill_checks"] = PASS

            fingerprint = str(page.locator(_HOST).get_attribute("data-kensho-form-fingerprint") or "")
            evidence["form_fingerprint"] = fingerprint
            if not fingerprint:
                raise _Stop("form_fingerprint", "form_fingerprint_missing")
            if manifest.expected_fingerprint and manifest.expected_fingerprint != fingerprint:
                raise _Stop("form_fingerprint", "FORM_CHANGED_REVIEW_REQUIRED", STOPPED)
            steps["form_fingerprint"] = PASS

            # 3. value-free mapping table + per-field human confirmation -------
            _click(page, "#preview-button")
            try:
                _wait_machine_status(page, ["previewed"], 10_000)
            except Exception:
                raise _Stop("mapping_human_confirmation", "preview_not_ready") from None
            rows = _mapping_rows(page)
            inspected = _isolated_inspect(context, extension_id, url, [row["field_id"] for row in rows])
            types = inspected.get("types", {}) if isinstance(inspected, Mapping) else {}
            for row in rows:
                row["input_type"] = str(types.get(row["field_id"], "") or "unknown")[:32]
            confirmer = cfg.confirmer
            if confirmer is None:
                raise _Stop("mapping_human_confirmation", "confirmer_missing")
            output(f"フォームfingerprint: {fingerprint}")
            output("値は表示しません。欄ごとに y で承認します（既定は入力しない）。一括承認はありません。")
            askable = [row for row in rows if row["human_mappable"]]
            asked = 0
            mapping = []
            for row in rows:
                key = row["proposed_profile_key"]
                expanded = _expand(key)
                if not row["human_mappable"]:
                    decision, approved = "not_mappable", False
                elif any(item in undetectable for item in expanded) and not cfg.allow_undetectable:
                    decision, approved = "forced_skip_undetectable", False
                elif any(item not in ALLOWED_PAYLOAD_KEYS or item not in fake_values for item in expanded):
                    decision, approved = "forced_skip_no_fake_value", False
                else:
                    asked += 1
                    answer = confirmer({
                        "index": asked,
                        "total": len(askable),
                        "label": row["label"],
                        "field_type": row["field_type"],
                        "input_type": row["input_type"],
                        "proposed_profile_key": key,
                    })
                    approved = answer is True
                    decision = "human_approved" if approved else "human_rejected"
                mapping.append({**row, "approved": approved, "decision": decision})
            evidence["mapping"] = [
                {name: item[name] for name in ("field_id", "label", "field_type", "input_type",
                                               "proposed_profile_key", "human_mappable",
                                               "approved", "decision")}
                for item in mapping
            ]
            approved_rows = [item for item in mapping if item["approved"]]
            approved_keys = sorted({k for item in approved_rows for k in _expand(item["proposed_profile_key"])})
            evidence["approved_profile_keys"] = approved_keys
            if not approved_rows:
                raise _Stop("mapping_human_confirmation", "MAPPING_NOT_APPROVED", STOPPED)
            for item in mapping:
                if not item["human_mappable"]:
                    continue
                action = "approve" if item["approved"] else "skip"
                _click(page, f'button[data-kensho-mapping-action="{action}"][data-field-id="{item["field_id"]}"]')
            remaining = page.locator(_HOST).locator('button[data-kensho-mapping-action="approve"]').count()
            if remaining:
                raise _Stop("mapping_human_confirmation", "mapping_incomplete")
            _click(page, "#save-template")
            try:
                saved = _wait_status_text(page, ["欄対応を保存しました", "保存できません", "確認してください"])
            except Exception:
                saved = ""
            if saved != "欄対応を保存しました":
                raise _Stop("mapping_human_confirmation", "mapping_template_not_saved")
            steps["mapping_human_confirmation"] = PASS

            try:
                binding = assisted_session.confirm_pilot_mapping(
                    context, page, extension_id=extension_id, expected_url=url,
                    approved_profile_keys=approved_keys,
                )
            except Exception as exc:
                raise _Stop("mapping_confirmed", _code(exc)) from None
            mapping_confirmed = True
            if binding.get("fingerprint") != fingerprint:
                raise _Stop("mapping_confirmed", "binding_fingerprint_mismatch")
            session_state = assisted_session.load_assisted_session_state()
            if (
                str(session_state.get("workflow_state", "")).upper() != "MAPPING_CONFIRMED"
                or sorted(session_state.get("confirmed_profile_keys", [])) != approved_keys
            ):
                raise _Stop("mapping_confirmed", "mapping_state_mismatch")
            steps["mapping_confirmed"] = PASS

            # Re-check immediately before the fill.
            reasons = list(monitor.prefill_blocking_reasons(page))
            reasons += _security_reasons(_isolated_inspect(context, extension_id, url, []))
            if reasons:
                evidence["prefill_blocking_reasons"] = sorted(set(reasons))
                raise _Stop("fill", "PREFILL_BLOCKED", STOPPED)

            # 4. fill through the extension -----------------------------------
            before_controls = _controls(page)
            monitor.mark_fill_started(approved_keys)
            fill_started = True
            navigations["armed"] = True
            _click(page, "#fill")
            try:
                fill_status = _wait_machine_status(page, ["previewed"], 20_000, not_in=True)
            except Exception:
                fill_status = _machine_status(page) or "timeout"
            session_state = assisted_session.load_assisted_session_state()
            filled_count = int(session_state.get("filled_field_count", 0) or 0)
            if fill_status == "filled" and str(session_state.get("workflow_state", "")).upper() == "HUMAN_ACTION_REQUIRED":
                steps["fill"] = PASS
            else:
                fail("fill", "fill_not_verified_by_extension")

            after_controls = _controls(page)
            counts = _post_fill_counts(before_controls, after_controls, fake_values, approved_keys, undetectable)
            del after_controls
            guard = dedicated_extension_page_state(page)
            post = {
                "filled_count": filled_count,
                "expected_filled_count": len(approved_rows),
                **counts,
                "session_unrelated_changed_count": int(session_state.get("unrelated_changed_count", 0) or 0),
                "navigation_count": navigations["count"],
                "url_unchanged": str(page.url) == url,
                "submitted_count_auto": guard.get("submitted_count_auto"),
                "auto_submit_detected": guard.get("auto_submit_detected"),
                "session_submitted_count_auto": int(session_state.get("submitted_count_auto", 0) or 0),
            }
            evidence["post_fill"] = post
            if (
                steps["fill"] == PASS
                and post["filled_count"] == post["expected_filled_count"]
                and post["structure_unchanged"] is True
                and post["target_matched_count"] == post["expected_filled_count"]
                and post["unrelated_changed_count"] == 0
                and post["unapproved_value_count"] == 0
                and post["session_unrelated_changed_count"] == 0
                and post["navigation_count"] == 0
                and post["url_unchanged"] is True
                and post["submitted_count_auto"] == 0
                and post["auto_submit_detected"] == 0
                and post["session_submitted_count_auto"] == 0
            ):
                steps["post_fill_verification"] = PASS
            else:
                fail("post_fill_verification", "post_fill_mismatch")
        except _Stop as stop:
            fail(stop.step, stop.reason, stop.status)
            evidence["stop_reason"] = stop.reason
        except Exception as exc:  # never let page content escape
            evidence["stop_reason"] = evidence["stop_reason"] or "unexpected_error"
            current = next((name for name in STAGE_STEPS if steps[name] == NOT_RUN), "launch")
            fail(current, f"unexpected:{_code(exc)}")
        finally:
            _cleanup(
                ctx=ctx, cfg=cfg, evidence=evidence, steps=steps, context=context, worker=worker,
                page=page, monitor=monitor, nonce=nonce, fake_values=fake_values,
                undetectable=undetectable, extension_id=extension_id, run_dir=run_dir,
                fill_started=fill_started, mapping_confirmed=mapping_confirmed,
                before_controls=before_controls, fail=fail,
            )
    fake_values.clear()
    return evidence


def _cleanup(*, ctx, cfg, evidence, steps, context, worker, page, monitor, nonce, fake_values,
             undetectable, extension_id, run_dir, fill_started, mapping_confirmed,
             before_controls, fail) -> None:
    page_alive = page is not None and not page.is_closed()

    # 5a. rollback through the extension (only if a fill may have happened).
    if fill_started:
        rollback = {"rollback_complete": False, "restored_matches_snapshot": False, "workflow_state": ""}
        try:
            if not page_alive:
                raise RuntimeError("page_closed")
            _click(page, "#rollback")
            try:
                _wait_status_text(page, ["入力を元に戻しました", "ロールバック不完全", "確認できず"], 15_000)
            except Exception:
                pass
            restored = _controls(page) == before_controls
            state = assisted_session.load_assisted_session_state()
            operations = state.get("extension_operations", [])
            last_event = operations[-1].get("event") if isinstance(operations, list) and operations and isinstance(operations[-1], dict) else ""
            rollback.update(
                rollback_complete=last_event == "rollback_complete",
                restored_matches_snapshot=bool(restored),
                workflow_state=str(state.get("workflow_state", "") or ""),
            )
            steps["rollback"] = PASS if (rollback["rollback_complete"] and restored) else FAIL
            if steps["rollback"] != PASS:
                evidence["failure_reasons"].append("rollback:rollback_not_verified")
        except Exception as exc:
            fail("rollback", _code(exc))
        evidence["rollback"] = rollback

    # 5b. session clear: extension temporary profile/capabilities, then tokens.
    clear = {"panel_clear": NOT_RUN, "sensitive_extension_keys_remaining": None, "end_pilot_session": False}
    try:
        panel_ok = True
        if mapping_confirmed and page_alive:
            _click(page, "#clear")
            try:
                hit = _wait_status_text(page, ["セッション情報消去済み", "消去できず", "確認できず"], 15_000)
            except Exception:
                hit = ""
            panel_ok = hit == "セッション情報消去済み"
            clear["panel_clear"] = PASS if panel_ok else FAIL
        # Remove control/progress/bridge/profile keys on the verified extension
        # worker (browser_manager.clear_extension_control_token picks
        # service_workers[0], which can be a page Service Worker).
        if worker is not None:
            live = _live_worker(context, extension_id)
            clear["sensitive_extension_keys_remaining"] = int(live.evaluate(
                """async keys => {
                  await chrome.storage.session.remove(keys);
                  const stored = await chrome.storage.session.get(null);
                  return Object.keys(stored).filter(key => keys.includes(key)).length;
                }""",
                list(_SENSITIVE_EXTENSION_KEYS),
            ))
    except Exception as exc:
        panel_ok = False
        evidence["failure_reasons"].append(f"session_clear:{_code(exc)}")
    try:
        assisted_session.end_pilot_session()
        clear["end_pilot_session"] = True
    except Exception as exc:
        evidence["failure_reasons"].append(f"session_clear:{_code(exc)}")
    evidence["session_clear"] = clear
    if worker is None and context is None:
        steps["session_clear"] = PASS if clear["end_pilot_session"] else FAIL
    else:
        steps["session_clear"] = PASS if (
            panel_ok and clear["sensitive_extension_keys_remaining"] == 0 and clear["end_pilot_session"]
        ) else FAIL

    # 5c. keep observing after clear, then residue, then close the tabs.
    if monitor is not None:
        try:
            if fill_started:
                monitor.mark_cleared()
                monitor.wait_quiet(
                    min_seconds=float(cfg.quiet_min_seconds),
                    quiet_seconds=float(cfg.quiet_seconds),
                    close_pages=False,
                )
                residue = check_sentinel_residue(
                    context, nonce, extension_id=extension_id, evidence_dirs=[run_dir],
                    hash_candidates=[v for k, v in fake_values.items() if k not in undetectable],
                )
                evidence["residue"] = residue
                steps["residue"] = PASS if residue.get("status") == PASS else (
                    FAIL if residue.get("status") == FAIL else UNVERIFIED)
            monitor.close_pages()
            result = monitor.result()
            evidence["monitor"] = result
            if fill_started:
                steps["quiet_period"] = PASS if result.get("quiet_period_completed") else UNVERIFIED
        except Exception as exc:
            evidence["failure_reasons"].append(f"monitor:{_code(exc)}")
            if fill_started:
                steps["quiet_period"] = FAIL

    # 5d. release the single pilot lock.
    try:
        assisted_session.release_pilot_candidate()
        steps["lock_release"] = PASS
    except Exception as exc:
        fail("lock_release", _code(exc))

    # 5e. close the context; the temporary Chromium profile must be gone.
    if context is not None:
        profile_dir = browser_manager._OWNED_RUNTIME_PROFILES.get(id(context))
        try:
            close_browser_safely(context)
            removed = profile_dir is not None and not Path(profile_dir).exists()
        except Exception:
            removed = False
        evidence["runtime_profile_removed"] = removed
        steps["context_close"] = PASS if removed else FAIL
    else:
        evidence["runtime_profile_removed"] = None
