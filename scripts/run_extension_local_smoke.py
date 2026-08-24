from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import threading
import uuid
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
FIXTURE_ROOT = ROOT / "tests"
FIXTURE_PATH = "extension_fixtures/standard_form.html"

class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def _fixture_server() -> Iterator[str]:
    handler = lambda *args, **kwargs: _QuietHandler(  # noqa: E731
        *args,
        directory=str(FIXTURE_ROOT),
        **kwargs,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _build_smoke_extension(destination: Path, origin: str) -> Path:
    extension_dir = destination / "extension"
    shutil.copytree(EXTENSION, extension_dir)
    manifest_path = extension_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # The temporary build models one explicit prior origin grant. Injection still
    # comes only from the production dynamic registration path.
    manifest["host_permissions"] = [f"{origin}/*"]
    manifest.pop("content_scripts", None)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return extension_dir


def _wait_for_worker(context):
    if context.service_workers:
        return context.service_workers[0]
    return context.wait_for_event("serviceworker", timeout=10_000)


def _approve_all_visible_mappings(host) -> None:
    initial_count = host.locator(
        'button[data-kensho-mapping-action="approve"]'
    ).count()
    for _ in range(initial_count):
        host.locator(
            'button[data-kensho-mapping-action="approve"]'
        ).first.click()


def run_smoke(*, headless: bool = True) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="kensho-extension-smoke-") as temp:
        temp_path = Path(temp)
        profile_dir = temp_path / "chrome-profile"

        with _fixture_server() as origin, sync_playwright() as playwright:
            extension_dir = _build_smoke_extension(temp_path, origin)
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel="chromium",
                headless=headless,
                args=[
                    f"--disable-extensions-except={extension_dir}",
                    f"--load-extension={extension_dir}",
                ],
            )
            try:
                worker = _wait_for_worker(context)
                marker = uuid.uuid4().hex

                page = context.pages[0] if context.pages else context.new_page()
                external_requests: list[str] = []

                def record_request(request) -> None:
                    if not (
                        request.url.startswith("http://127.0.0.1:")
                        or request.url.startswith("chrome-extension://")
                    ):
                        external_requests.append(request.url)

                page.on("request", record_request)
                worker.evaluate(
                    """async () => {
                      const deadline = Date.now() + 10000;
                      while (Date.now() < deadline) {
                        if (!chrome.scripting?.getRegisteredContentScripts) {
                          await new Promise(resolve => setTimeout(resolve, 50));
                          continue;
                        }
                        const scripts = await chrome.scripting.getRegisteredContentScripts();
                        if (scripts.filter(item => item.id.startsWith("kensho-")).length === 2) {
                          return;
                        }
                        await new Promise(resolve => setTimeout(resolve, 50));
                      }
                      throw new Error("dynamic_registration_timeout");
                    }"""
                )
                page.goto(f"{origin}/{FIXTURE_PATH}", wait_until="domcontentloaded")

                host = page.locator("#kensho-assistant-overlay-host")
                host.wait_for(state="attached", timeout=10_000)
                page.wait_for_function(
                    """() => document.querySelector("#kensho-assistant-overlay-host")
                      ?.shadowRoot?.querySelector("#status")
                      ?.textContent?.includes("解析済み")"""
                )
                auto_analysis_completed = True
                reload_success_count = 0
                max_panel_count = 0
                max_guard_count = 0
                for _ in range(10):
                    page.reload(wait_until="domcontentloaded")
                    host.wait_for(state="attached", timeout=10_000)
                    panel_count = page.locator(
                        '[data-kensho-extension-root="true"]'
                    ).count()
                    guard_count = page.locator(
                        'html[data-kensho-submit-guard="true"]'
                    ).count()
                    max_panel_count = max(max_panel_count, panel_count)
                    max_guard_count = max(max_guard_count, guard_count)
                    if panel_count == 1 and guard_count == 1:
                        reload_success_count += 1

                page.goto(
                    f"{origin}/extension_fixtures/complex_form.html",
                    wait_until="domcontentloaded",
                )
                host.wait_for(state="attached", timeout=10_000)
                same_origin_navigation = (
                    page.locator('[data-kensho-extension-root="true"]').count() == 1
                    and page.locator('html[data-kensho-submit-guard="true"]').count()
                    == 1
                )
                page.goto(f"{origin}/{FIXTURE_PATH}", wait_until="domcontentloaded")
                host.wait_for(state="attached", timeout=10_000)

                worker.evaluate(
                    """profile => chrome.storage.session.set({
                      kenshoSessionProfile: profile
                    })""",
                    {
                        "last_name": f"TEST-{marker[:8]}",
                        "first_name": "LOCAL",
                        "last_name_kana": "テスト",
                        "first_name_kana": "ローカル",
                        "email": f"{marker}@example.invalid",
                        "phone": "00000000000",
                        "postal_code": "0000000",
                        "prefecture": "福岡県",
                        "city": "テスト市",
                        "street": "TEST-1",
                        "building": "TEST",
                        "birth_date": "1990-04-01",
                        "gender": "男性",
                    },
                )
                profile_is_ready = worker.evaluate(
                    """async () => Boolean(
                      (await chrome.storage.session.get("kenshoSessionProfile"))
                        .kenshoSessionProfile
                    )"""
                )
                if not profile_is_ready:
                    raise RuntimeError("temporary profile was not available")

                cdp = context.new_cdp_session(page)
                targets = cdp.send("Target.getTargets")["targetInfos"]
                service_worker_target = next(
                    target
                    for target in targets
                    if target["type"] == "service_worker"
                    and target["url"].endswith("/service-worker.js")
                )
                cdp.send(
                    "Target.closeTarget",
                    {"targetId": service_worker_target["targetId"]},
                )
                page.wait_for_timeout(300)
                page.reload(wait_until="domcontentloaded")
                host.wait_for(state="attached", timeout=10_000)
                restart_recovered = (
                    page.locator('[data-kensho-extension-root="true"]').count() == 1
                    and page.locator('html[data-kensho-submit-guard="true"]').count()
                    == 1
                )
                host.locator("#analyze").click()
                page.wait_for_function(
                    """() => document.querySelector("#kensho-assistant-overlay-host")
                      ?.shadowRoot?.querySelector("#status")
                      ?.textContent?.includes("解析済み")"""
                )
                host.locator("#preview-button").click()
                page.wait_for_timeout(300)
                page.wait_for_function(
                    """() => document.querySelector("#kensho-assistant-overlay-host")
                      ?.shadowRoot?.querySelector("#status")
                      ?.textContent?.includes("入力前確認")"""
                )
                if host.locator("#approve-safe").is_enabled():
                    host.locator("#approve-safe").click()
                _approve_all_visible_mappings(host)
                host.locator("#fill").click()
                page.wait_for_timeout(1500)
                fill_status = host.locator("#status").text_content() or ""
                if "入力済み" not in fill_status:
                    raise RuntimeError(
                        "fill_status="
                        + fill_status
                        + ";fill_enabled="
                        + str(host.locator("#fill").is_enabled())
                        + ";mapping_buttons="
                        + str(host.locator('button[data-kensho-mapping-action="approve"]').count())
                        + ";verification="
                        + (host.get_attribute("data-kensho-verification") or "{}")
                    )

                fill_completed = bool(
                    page.locator('input[name="email"]').input_value()
                )
                before_url = page.url
                host.locator("#rollback").click()
                page.locator("#submit-button").click()
                guard_state = page.evaluate(
                    "() => window.__KENSHO_SUBMIT_GUARD__.state()"
                )
                submit_blocked = (
                    page.url == before_url
                    and guard_state["blockedAttempts"] >= 1
                    and guard_state["submitted_count_auto"] == 0
                )

                page.goto(
                    f"{origin}/extension_fixtures/combined_japanese_form.html",
                    wait_until="domcontentloaded",
                )
                host.wait_for(state="attached", timeout=10_000)
                host.locator("#analyze").click()
                page.wait_for_function(
                    """() => document.querySelector("#kensho-assistant-overlay-host")
                      ?.shadowRoot?.querySelector("#status")
                      ?.textContent?.includes("CAPTCHA検出")"""
                )
                host.locator("#preview-button").click()
                page.wait_for_function(
                    """() => document.querySelector("#kensho-assistant-overlay-host")
                      ?.shadowRoot?.querySelector("#status")
                      ?.textContent?.includes("CAPTCHA検出")"""
                )
                combined_captcha_safe_stop = all(
                    [
                        page.locator("#name").input_value() == "",
                        page.locator("#kana").input_value() == "",
                        page.locator("#age").input_value() == "",
                        not page.get_by_label("男性").is_checked(),
                        not page.get_by_label("商品A").is_checked(),
                        not page.get_by_label("商品B").is_checked(),
                        page.locator(
                            'textarea[name="applicant[comment]"]'
                        ).input_value()
                        == "",
                    ]
                )
                host.locator("#rollback").click()
                host.locator("#clear").click()
                page.wait_for_timeout(100)
                session_cleared = (
                    page.locator("#email").input_value() == ""
                    and "セッション情報消去済み"
                    in host.locator("#status").text_content()
                )
                with _fixture_server() as unapproved_origin:
                    page.goto(
                        f"{unapproved_origin}/{FIXTURE_PATH}",
                        wait_until="domcontentloaded",
                    )
                    page.wait_for_timeout(300)
                    unapproved_origin_injections = page.locator(
                        '[data-kensho-extension-root="true"]'
                    ).count()

                return {
                    "status": "PASS"
                    if all(
                        [
                            fill_completed,
                            auto_analysis_completed,
                            combined_captcha_safe_stop,
                            submit_blocked,
                            session_cleared,
                            reload_success_count == 10,
                            same_origin_navigation,
                            restart_recovered,
                            max_panel_count == 1,
                            max_guard_count == 1,
                            unapproved_origin_injections == 0,
                            not external_requests,
                        ]
                    )
                    else "FAIL",
                    "fixture": "standard_form",
                    "overlay_detected": True,
                    "reload_success_count": reload_success_count,
                    "same_origin_navigation": same_origin_navigation,
                    "service_worker_restart_recovered": restart_recovered,
                    "max_panel_count": max_panel_count,
                    "max_guard_count": max_guard_count,
                    "unapproved_origin_injections": unapproved_origin_injections,
                    "analysis_completed": True,
                    "auto_analysis_completed": auto_analysis_completed,
                    "fill_completed": fill_completed,
                    "combined_captcha_safe_stop": combined_captcha_safe_stop,
                    "submit_blocked": submit_blocked,
                    "auto_submit_detected": 0,
                    "submitted_count_auto": guard_state[
                        "submitted_count_auto"
                    ],
                    "session_cleared": session_cleared,
                    "external_requests": len(external_requests),
                }
            finally:
                context.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Chrome extension against a local fixture only."
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the isolated temporary Chromium window.",
    )
    args = parser.parse_args()
    result = run_smoke(headless=not args.headed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
