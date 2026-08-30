from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


DEFAULT_TARGET = "https://www.epinard.jp/presentquiz/"


def default_profile_dir() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / "kensho_assistant" / "chrome-profile"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated kensho Chrome profile")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--profile-dir", type=Path, default=default_profile_dir())
    parser.add_argument("--url", default=DEFAULT_TARGET)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    extension = (root / "build" / "extension").resolve()
    if not (extension / "manifest.json").is_file():
        raise SystemExit("dedicated_extension_build_missing")
    args.profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(args.profile_dir),
            channel="chromium",
            headless=args.headless,
            args=[
                f"--disable-extensions-except={extension}",
                f"--load-extension={extension}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1_500)
        state = page.evaluate(
            """() => ({
              ready: document.documentElement.dataset.kenshoExtensionReady === 'true',
              panel_count: document.querySelectorAll('[data-kensho-extension-root="true"]').length,
              submit_guard_count: document.documentElement.dataset.kenshoSubmitGuard === 'true' ? 1 : 0,
              submitted_count_auto: 0,
              auto_submit_detected: 0
            })"""
        )
        status = "PASS" if state["ready"] and state["panel_count"] == 1 and state["submit_guard_count"] == 1 else "BLOCKED_AUTO_INJECTION_REAL_SITE"
        print(json.dumps({"status": status, "url": page.url, **state}, ensure_ascii=False))
        if args.verify_only:
            context.close()
            return 0 if status == "PASS" else 2
        page.bring_to_front()
        page.wait_for_timeout(2_147_000_000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
