from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from .paths import CHROME_USER_DATA_DIR, PACKAGE_ROOT
from .pilot_network_monitor import live_extension_worker, evaluate_worker


_OWNED_RUNTIME_PROFILES: dict[int, Path] = {}
_DEDICATED_BUILDS: dict[int, dict[str, object]] = {}


def _runtime_origin_worker(context):
    """Read-only readiness retries before any origin mutation is attempted."""
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        worker = live_extension_worker(context, "chrome-extension://", timeout=min(2.0, deadline - time.monotonic()))
        if worker is not None:
            try:
                if evaluate_worker(worker, "() => dedicatedRuntimeOriginMode()", timeout=2.0) is True:
                    return worker
            except Exception:
                pass
        time.sleep(0.05)
    raise RuntimeError("dedicated_extension_worker_mismatch")


def set_active_origin(context, origin: str, session_id: str, *, allow_loopback_http: bool = False) -> None:
    """Privileged, bounded worker operation; navigation requires exact readback."""
    from .origin_policy import normalize_origin, is_origin_allowed
    if not is_origin_allowed(origin, allow_loopback_http=allow_loopback_http)[0]:
        raise ValueError("dedicated_target_not_allowed")
    expected = {"originPattern": normalize_origin(origin) + "/*", "sessionId": session_id}
    try:
        worker = _runtime_origin_worker(context)
        actual = evaluate_worker(worker, """async expected => {
          await setActiveOrigin(expected.originPattern, expected.sessionId);
          const active = await getActiveOrigin();
          const scripts = (await chrome.scripting.getRegisteredContentScripts()).filter(isManagedScript);
          if (scripts.length !== 2 || scripts.some(s => s.matches.length !== 1 ||
              s.matches[0] !== expected.originPattern || s.persistAcrossSessions))
            throw new Error('active_origin_registration_mismatch');
          return active;
        }""", expected, timeout=2.0)
        if actual != expected:
            raise RuntimeError("active_origin_readback_mismatch")
    except Exception:
        # A timeout does not cancel JS; close the owned context before it can navigate.
        close_browser_safely(context)
        raise RuntimeError("active_origin_unverified") from None


def clear_active_origin(context) -> None:
    worker = _runtime_origin_worker(context)
    cleared = evaluate_worker(worker, """async () => {
      await clearActiveOrigin();
      return !(await getActiveOrigin()) &&
        !(await chrome.scripting.getRegisteredContentScripts()).some(isManagedScript);
    }""", timeout=2.0)
    if cleared is not True:
        raise RuntimeError("active_origin_cleanup_unverified")


def seed_form_templates(context, target_url: str) -> list[dict[str, object]]:
    """Normal-session only: seed verified value-free metadata before navigation."""
    from . import form_template_store as store
    store._guard()
    build = _DEDICATED_BUILDS.get(id(context))
    if not build:
        return []
    parsed = urlsplit(target_url)
    try:
        templates = store.get_templates_for_origin(
            f"{parsed.scheme}://{parsed.netloc}", extension_version=build["version"],
            build_sha256=build["build_sha256"],
        )
    except (OSError, ValueError):
        return []
    if not templates:
        return []
    worker = live_extension_worker(context, "chrome-extension://", timeout=2.0)
    if worker is None:
        return []
    # Only metadata reaches this evaluation. No storage.session/profile reads.
    projected = [{k: v for k, v in item.items() if k not in {"savedAt", "extension_build_sha256"}}
        for item in templates]
    try:
        verified = evaluate_worker(worker, """async templates => {
          const values = {};
          for (const item of templates) {
            const key = templateStorageKey(item.origin + item.pathname);
            if (!key || item.extensionVersion !== chrome.runtime.getManifest().version)
              throw new Error('seed_invalid');
            values[key] = templateApi().sanitizeTemplate(item);
          }
          const keys = Object.keys(values);
          try {
            await chrome.storage.local.set(values);
            const readback = await chrome.storage.local.get(keys);
            if (keys.some(key => JSON.stringify(templateApi().sanitizeTemplate(readback[key])) !== JSON.stringify(values[key])))
              throw new Error('seed_readback_failed');
            return true;
          } catch (_) { await chrome.storage.local.remove(keys); return false; }
        }""", projected, timeout=2.0)
        if verified is True:
            return templates
    except TimeoutError:
        # Cancellation of the Python wait does not cancel pending JS writes.
        # Close this context without navigating; readback cannot prove quiescence.
        raise RuntimeError("form_template_seed_cleanup_unverified") from None
    except Exception:
        # Completed failures can fall back only after removal and readback.
        pass
    try:
        cleared = evaluate_worker(worker, """async templates => {
          const keys = templates.map(t => templateStorageKey(t.origin + t.pathname));
          await chrome.storage.local.remove(keys);
          const readback = await chrome.storage.local.get(keys);
          return keys.every(key => !readback[key]);
        }""", projected, timeout=2.0)
        if cleared is True:
            return []
    except Exception:
        pass
    raise RuntimeError("form_template_seed_cleanup_unverified")


def prepare_seeded_mapping(context, page, extension_id: str, expected_url: str, templates) -> bool:
    """Use only the existing panel; the strict mapping check remains mandatory."""
    from . import form_template_store as store
    store._guard()
    parsed = urlsplit(expected_url)
    if not any(item["pathname"] == parsed.path for item in templates):
        return False
    try:
        host = page.locator("#kensho-assistant-overlay-host")
        host.locator("#analyze").click(timeout=2000)
        page.wait_for_function("() => ['analyzed', 'blocked'].includes(document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus)", timeout=5000)
        if host.get_attribute("data-kensho-status") != "analyzed":
            return False
        host.locator("#preview-button").click(timeout=2000)
        page.wait_for_function("() => document.querySelector('[data-kensho-extension-root]')?.dataset.kenshoStatus === 'previewed'", timeout=5000)
        binding = confirmed_extension_mapping(context, page, extension_id, expected_url)
        return any(item["pathname"] == parsed.path and item["fingerprint"] == binding["fingerprint"] for item in templates)
    except Exception:
        return False


def persist_verified_form_template(context, page, state) -> str:
    """Only a real successful progress event may promote a human confirmation."""
    from . import form_template_store as store
    store._guard()
    build = _DEDICATED_BUILDS.get(id(context))
    if not build:
        return "unavailable"
    if (state.get("workflow_state") != "HUMAN_ACTION_REQUIRED"
        or state.get("current_step") != "post_fill_verified"
        or state.get("last_action") != "POST_FILL_VERIFIED"
        or state.get("submitted_count_auto") != 0
        or state.get("unrelated_changed_count") != 0
        or not state.get("filled_field_count")):
        return "not_verified"
    expected_url = state.get("current_url", "")
    if page.url != expected_url:
        return "page_changed"
    try:
        extension_state = dedicated_extension_page_state(page, require_ready=True)
        if (extension_state.get("submitted_count_auto") != 0
            or extension_state.get("auto_submit_detected") != 0
            or extension_state.get("extension_id") != state.get("extension_id")):
            return "not_verified"
        worker = live_extension_worker(context,
            f"chrome-extension://{state['extension_id']}/service-worker.js", timeout=2.0)
        if worker is None:
            return "unavailable"
        template = evaluate_worker(worker, """async url => {
          const key = templateStorageKey(url);
          const value = (await chrome.storage.local.get(key))[key];
          return value ? templateApi().sanitizeTemplate(value) : null;
        }""", expected_url, timeout=2.0)
        template = store.from_extension(template)
        parsed = urlsplit(expected_url)
        if (template["origin"] != f"{parsed.scheme}://{parsed.netloc}"
            or template["pathname"] != parsed.path
            or template["fingerprint"] != state.get("form_fingerprint")
            or template["extensionVersion"] != build["version"]):
            return "not_verified"
        return store.save_template(template, build_sha256=build["build_sha256"])
    except Exception:
        # Exception text can contain page data. Return a fixed metadata status.
        return "unavailable"


def confirmed_extension_mapping(context, page, extension_id: str, expected_url: str) -> dict[str, object]:
    """Read only confirmed, non-PII mapping metadata from the dedicated worker."""
    if str(page.url) != expected_url:
        raise RuntimeError("extension_mapping_page_changed")
    state = dedicated_extension_page_state(page, require_ready=True)
    if state.get("extension_id") != extension_id:
        raise RuntimeError("dedicated_extension_worker_mismatch")
    worker = live_extension_worker(context, f"chrome-extension://{extension_id}/service-worker.js", timeout=2.0)
    if worker is None:
        raise RuntimeError("dedicated_extension_worker_mismatch")
    try:
        return evaluate_worker(worker,
            """async url => {
              const tabs = (await chrome.tabs.query({})).filter(tab => tab.url === url);
              if (tabs.length !== 1) throw new Error('candidate_tab_not_unique');
              const [current] = await chrome.scripting.executeScript({
                target: {tabId: tabs[0].id, frameIds: [0]}, world: 'ISOLATED',
                func: expected => {
                  const root = document.querySelector('[data-kensho-extension-root]');
                  const fp = globalThis.KenshoExtension?.FormDetector?.fingerprint(document);
                  if (location.href !== expected || !fp ||
                      root?.dataset.kenshoFormFingerprint !== fp ||
                      root?.dataset.kenshoStatus !== 'previewed') return null;
                  return fp;
                }, args: [url]
              });
              if (!current?.result || !current.documentId) throw new Error('mapping_page_changed');
              const key = templateStorageKey(url);
              const stored = (await chrome.storage.local.get(key))[key];
              const template = templateApi().sanitizeTemplate(stored);
              const location = new URL(url);
              if (template.origin !== location.origin || template.pathname !== location.pathname ||
                  template.fingerprint !== current.result ||
                  template.extensionVersion !== chrome.runtime.getManifest().version ||
                  !template.humanConfirmedAt || !Number.isFinite(Date.parse(template.humanConfirmedAt)) ||
                  !template.fields.length) throw new Error('mapping_not_confirmed');
              const keys = [];
              for (const field of template.fields) {
                if (field.disabled || field.readOnly ||
                    !['high', 'reviewed'].includes(field.confidenceBand)) throw new Error('invalid_mapping');
                const key = field.approvedProfileKey;
                const expanded = key === 'full_name' ? ['last_name', 'first_name'] :
                  key === 'full_name_kana' ? ['last_name_kana', 'first_name_kana'] : [key];
                if (expanded.some(value => !ALLOWED_PROFILE_KEYS.has(value))) throw new Error('invalid_mapping');
                keys.push(...expanded);
              }
              return {tab_id: tabs[0].id, document_id: current.documentId,
                fingerprint: current.result, profile_keys: [...new Set(keys)].sort()};
            }""",
            expected_url,
        )
    except Exception:
        raise RuntimeError("extension_mapping_not_confirmed") from None


def provision_extension_control_token(
    context,
    session_id: str,
    token: str,
    extension_id: str,
    *,
    binding: dict[str, object] | None = None,
    expected_url: str = "",
) -> None:
    """Place a short-lived control token directly in the dedicated worker session."""
    expected_prefix = f"chrome-extension://{str(extension_id or '').strip()}/"
    worker = live_extension_worker(context, expected_prefix, timeout=2.0)
    if worker is None:
        raise RuntimeError("dedicated_extension_worker_mismatch")
    evaluate_worker(worker,
        """async ({sessionId, token, binding, expectedUrl}) => {
          const tabs = await chrome.tabs.query({active: true, currentWindow: true});
          const tabId = binding ? binding.tab_id : tabs[0]?.id;
          if (!Number.isInteger(tabId)) throw new Error('active_tab_binding_unavailable');
          if (binding) {
            const [current] = await chrome.scripting.executeScript({
              target: {tabId, documentIds: [binding.document_id]}, world: 'ISOLATED',
              func: (url, fp) => location.href === url &&
                document.documentElement.dataset.kenshoExtensionReady === 'true' &&
                globalThis.KenshoExtension?.FormDetector?.fingerprint(document) === fp,
              args: [expectedUrl, binding.fingerprint]
            });
            if (current?.result !== true || current.documentId !== binding.document_id) {
              throw new Error('mapping_page_changed');
            }
          }
          await chrome.storage.session.set({
            kenshoControlCapability: {session_id: sessionId, token, tab_id: tabId,
              document_id: binding?.document_id || ''}
          });
        }""",
        {"sessionId": str(session_id), "token": str(token),
         **({"binding": binding, "expectedUrl": expected_url} if binding else {})},
    )


def clear_extension_control_token(context) -> None:
    worker = live_extension_worker(context, "chrome-extension://", timeout=2.0)
    if worker is None:
        return
    evaluate_worker(worker,
        "async () => chrome.storage.session.remove(['kenshoControlCapability', 'kenshoProgressCapability'])"
    )


def get_browser_profile_dir() -> Path:
    CHROME_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return CHROME_USER_DATA_DIR


def create_dedicated_runtime_profile(
    run_id: str,
    *,
    runtime_profiles_root: Path | None = None,
) -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    root = runtime_profiles_root or local_app_data / "kensho_assistant" / "chrome-runs"
    root.mkdir(parents=True, exist_ok=True)
    safe_run_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(run_id or "run")).strip("-")[:48] or "run"
    return Path(tempfile.mkdtemp(prefix=f"{safe_run_id}-", dir=root))


def validate_dedicated_target_url(
    url: str, *, approved_candidate_origin: str | None = None,
    allow_loopback_http: bool = False,
    approved_origins_path: Path | None = None,
) -> str:
    from .origin_policy import normalize_origin, is_origin_allowed
    raw = str(url or "").strip()
    try:
        parsed = urlsplit(raw)
        origin = normalize_origin(raw)
        approved = normalize_origin(approved_candidate_origin)
        if (parsed.query or parsed.fragment or "?" in raw or "#" in raw
            or origin != approved
            or not is_origin_allowed(origin, allow_loopback_http=allow_loopback_http)[0]):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("dedicated_target_not_allowed") from None
    return raw


def verify_dedicated_extension_build(
    *,
    project_root: Path = PACKAGE_ROOT,
    approved_origins_path: Path | None = None,
    isolated_files: list[str] | None = None,
) -> dict[str, object]:
    from kensho_assistant.scripts.build_dedicated_extension import (
        build_hash,
        build_dedicated_extension,
        DEDICATED_HOST_PERMISSIONS,
        DEDICATED_RUNTIME_MODE,
    )

    root = project_root.resolve()
    source_dir = root / "extension"
    build_dir = root / "build" / "extension"
    manifest_path = build_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("dedicated_extension_build_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    expected_permissions = DEDICATED_HOST_PERMISSIONS
    if (
        manifest.get("version") != source_manifest.get("version")
        or manifest.get("host_permissions") != expected_permissions
        or "optional_host_permissions" in manifest
        or "content_scripts" in manifest
        or manifest.get("version_name") != DEDICATED_RUNTIME_MODE
    ):
        raise RuntimeError("dedicated_extension_build_stale")
    actual_hash = build_hash(build_dir)
    with tempfile.TemporaryDirectory(prefix="kensho-extension-verify-", dir=root / "build") as temp_dir:
        expected = build_dedicated_extension(
            source_dir=source_dir,
            output_dir=Path(temp_dir) / "extension",
            isolated_files=isolated_files,
        )
        if actual_hash != expected.build_sha256:
            raise RuntimeError("dedicated_extension_build_stale")
    return {
        "build_sha256": actual_hash,
        "version": str(manifest.get("version", "")),
        "runtime_origin_mode": True,
        "extension_dir": build_dir,
    }


def launch_dedicated_kensho_context(
    playwright,
    *,
    run_id: str,
    project_root: Path = PACKAGE_ROOT,
    runtime_profiles_root: Path | None = None,
    headless: bool = False,
    extra_args: tuple[str, ...] = (),
):
    """``extra_args`` is an in-process test seam (e.g. host-resolver rules)."""
    verified = verify_dedicated_extension_build(project_root=project_root)
    profile_dir = create_dedicated_runtime_profile(
        run_id,
        runtime_profiles_root=runtime_profiles_root,
    )
    source_extension_dir = Path(verified["extension_dir"])
    extension_dir = profile_dir / "extension"
    user_data_dir = profile_dir / "user-data"
    try:
        shutil.copytree(source_extension_dir, extension_dir)
        from kensho_assistant.scripts.build_dedicated_extension import build_hash

        if build_hash(extension_dir) != verified["build_sha256"]:
            raise RuntimeError("dedicated_extension_snapshot_mismatch")
        user_data_dir.mkdir()
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel="chromium",
            headless=headless,
            args=[
                f"--disable-extensions-except={extension_dir}",
                f"--load-extension={extension_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                *[str(arg) for arg in extra_args],
            ],
        )
    except Exception:
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise
    _OWNED_RUNTIME_PROFILES[id(context)] = profile_dir
    _DEDICATED_BUILDS[id(context)] = verified
    return context, "chromium", verified


def dedicated_extension_page_state(page, *, require_ready: bool = False) -> dict[str, object]:
    inspection_failed = False
    try:
        try:
            page.wait_for_function(
                "() => document.documentElement.dataset.kenshoExtensionReady === 'true'",
                timeout=5_000,
            )
        except AttributeError:
            pass
        state = page.evaluate(
            """() => ({
              ready: document.documentElement.dataset.kenshoExtensionReady === 'true',
              panel_count: document.querySelectorAll('[data-kensho-extension-root="true"]').length,
              extension_id: document.querySelector('[data-kensho-extension-root="true"]')
                ?.getAttribute('data-kensho-extension-id') || '',
              submit_guard_count: document.documentElement.dataset.kenshoSubmitGuard === 'true' ? 1 : 0,
              guard_state: window.__KENSHO_SUBMIT_GUARD__?.state?.() || null
            })"""
        )
        if not isinstance(state, dict):
            state = {}
            inspection_failed = True
    except Exception:
        # Page exceptions may include page content. Never expose them in diagnostics.
        state = {}
        inspection_failed = True
    guard_state = state.pop("guard_state", None)
    if not isinstance(guard_state, dict):
        guard_state = {}
    for output_key, guard_key in (
        ("submitted_count_auto", "submitted_count_auto"),
        ("auto_submit_detected", "blockedAttempts"),
    ):
        value = guard_state.get(guard_key)
        state[output_key] = value if type(value) is int and value >= 0 else None
    state["guard_verified"] = all(
        guard_state.get(key) is True
        for key in ("locked", "integrity", "installedAtDocumentStart")
    ) and all(state[key] is not None for key in ("submitted_count_auto", "auto_submit_detected"))
    valid = (
        not inspection_failed
        and state.get("ready") is True
        and state.get("panel_count") == 1
        and state.get("submit_guard_count") == 1
        and state["guard_verified"]
        and state.get("submitted_count_auto") == 0
        and state.get("auto_submit_detected") == 0
    )
    if inspection_failed:
        state["blocked_reason"] = "guard_inspection_failed"
    elif not state["guard_verified"]:
        state["blocked_reason"] = "guard_state_unverified"
    elif not valid:
        state["blocked_reason"] = "dedicated_extension_not_ready"
    if require_ready and not valid:
        raise RuntimeError("dedicated_extension_not_ready") from None
    state["status"] = "PASS" if valid else "BLOCKED"
    return state


def _launch_context(playwright, browser_name: str = "chrome"):
    kwargs = {
        "user_data_dir": str(get_browser_profile_dir()),
        "headless": False,
    }
    if browser_name == "chrome":
        try:
            return playwright.chromium.launch_persistent_context(channel="chrome", **kwargs), "chrome"
        except Exception:
            pass
    try:
        return playwright.chromium.launch_persistent_context(**kwargs), "chromium"
    except Exception:
        browser = playwright.chromium.launch(headless=False)
        return browser.new_context(), "chromium"


def launch_chrome_headed(playwright, browser_name: str = "chrome"):
    return _launch_context(playwright, browser_name)


def open_url_in_chrome(
    playwright,
    url: str,
    browser_name: str = "chrome",
    *,
    use_dedicated_extension: bool = False,
    run_id: str = "",
    approved_candidate_origin: str | None = None,
):
    if use_dedicated_extension:
        if url != "about:blank":
            validate_dedicated_target_url(url, approved_candidate_origin=approved_candidate_origin)
        context, actual_browser, _verified = launch_dedicated_kensho_context(
            playwright,
            run_id=run_id,
        )
    else:
        context, actual_browser = launch_chrome_headed(playwright, browser_name)
    try:
        if use_dedicated_extension and url != "about:blank":
            set_active_origin(context, approved_candidate_origin, run_id)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        close_browser_safely(context)
        raise
    return context, page, actual_browser


def close_browser_safely(context) -> None:
    if id(context) in _DEDICATED_BUILDS:
        try:
            clear_active_origin(context)
        except Exception:
            # Closing the isolated profile is the mandatory fallback if worker
            # cleanup cannot be verified; no further navigation is permitted.
            pass
    _DEDICATED_BUILDS.pop(id(context), None)
    profile_dir = _OWNED_RUNTIME_PROFILES.pop(id(context), None)
    try:
        context.close()
    except Exception:
        pass
    if profile_dir is not None:
        for _attempt in range(20):
            shutil.rmtree(profile_dir, ignore_errors=True)
            if not profile_dir.exists():
                break
            time.sleep(0.1)
        if profile_dir.exists():
            raise RuntimeError("dedicated_profile_cleanup_failed")


def check_chrome_available() -> dict[str, str]:
    result = {
        "playwright": "missing",
        "chrome_channel": "unknown",
        "dedicated_profile": "missing",
        "headed_launch": "missing",
        "keep_open_supported": "ok",
        "fallback_browser": "",
    }
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return result
    result["playwright"] = "ok"
    try:
        get_browser_profile_dir()
        result["dedicated_profile"] = "ok"
    except Exception:
        return result
    try:
        with sync_playwright() as playwright:
            context, actual_browser = launch_chrome_headed(playwright, "chrome")
            result["headed_launch"] = "ok"
            result["chrome_channel"] = "ok" if actual_browser == "chrome" else "missing"
            result["fallback_browser"] = actual_browser
            close_browser_safely(context)
    except Exception:
        result["headed_launch"] = "missing"
    return result


def check_browser_doctor() -> dict[str, str]:
    return check_chrome_available()
