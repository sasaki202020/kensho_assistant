from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

from playwright.sync_api import sync_playwright


DEFAULT_TARGET = "https://www.epinard.jp/presentquiz/"


def default_runtime_profiles_root() -> Path:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / "kensho_assistant" / "chrome-runs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the isolated kensho Chrome profile")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--runtime-profiles-root", type=Path, default=default_runtime_profiles_root())
    parser.add_argument("--url", default=DEFAULT_TARGET)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        raise SystemExit("diagnostic_runner_requires_verify_only")
    root = args.project_root.resolve()
    sys.path.insert(0, str(root.parent))
    from kensho_assistant.app.browser_manager import (
        close_browser_safely,
        dedicated_extension_page_state,
        launch_dedicated_kensho_context,
        validate_dedicated_target_url,
    )

    target_url = validate_dedicated_target_url(args.url)

    with sync_playwright() as playwright:
        context = None
        try:
            context, _actual_browser, verified = launch_dedicated_kensho_context(
                playwright,
                run_id=f"diagnostic-{uuid.uuid4().hex}",
                project_root=root,
                runtime_profiles_root=args.runtime_profiles_root,
                headless=args.headless,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1_500)
            state = dedicated_extension_page_state(page)
            status = "PASS" if state.pop("status") == "PASS" else "BLOCKED_AUTO_INJECTION_REAL_SITE"
            print(json.dumps({
                "status": status,
                "url": page.url,
                "extension_version": verified["version"],
                "build_sha256": verified["build_sha256"],
                **state,
            }, ensure_ascii=False))
            return 0 if status == "PASS" else 2
        finally:
            if context is not None:
                close_browser_safely(context)


if __name__ == "__main__":
    raise SystemExit(main())
