from __future__ import annotations

import argparse
import time
from urllib.parse import urlsplit

from kensho_assistant.app.browser_manager import (
    close_browser_safely,
    launch_chrome_headed,
)
from kensho_assistant.app.direct_prepare import (
    install_human_handoff_control,
    prepare_page_without_submit,
)
from kensho_assistant.app.profile_manager import (
    load_profile,
    profile_missing_fields,
)
from kensho_assistant.app.submission_guard import (
    install_submission_guard,
    install_submission_guard_on_context,
    submission_guard_snapshot,
)


def _validated_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("URLはhttpまたはhttpsの応募ページを指定してください")
    return value.strip()


def _has_captcha(page) -> bool:
    return (
        page.locator(
            'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], '
            '.g-recaptcha, .h-captcha, [class*="turnstile"]'
        ).count()
        > 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="暗号化プロフィールから応募フォームを準備し、最終送信前で停止します"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--browser", choices=("chrome", "chromium"), default="chrome")
    parser.add_argument("--prize-choice", default="")
    parser.add_argument("--free-text", default="")
    args = parser.parse_args()

    target_url = _validated_url(args.url)
    profile = load_profile(encrypted=True)
    missing = profile_missing_fields(profile)
    if missing:
        raise SystemExit("暗号化プロフィールに不足項目があります")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit("Playwrightを利用できません") from exc

    context = None
    with sync_playwright() as playwright:
        try:
            context, actual_browser = launch_chrome_headed(playwright, args.browser)
            install_submission_guard_on_context(context)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            install_submission_guard(page)
            result = prepare_page_without_submit(
                page,
                profile,
                prize_choice=args.prize_choice,
                free_text=args.free_text,
            )
            install_human_handoff_control(page)
            guard = submission_guard_snapshot(page)
            print(f"browser: {actual_browser}")
            print(f"filled_fields_count: {len(result.filled_fields)}")
            print(f"missing_fields_count: {len(result.missing_fields)}")
            print(f"captcha_requires_human: {_has_captcha(page)}")
            print(f"submit_guard_active: {guard.get('blockedAttempts', 0) == 0}")
            print("submitted_count_auto: 0")
            print("auto_submitted: false")
            print("最終送信は行っていません。ブラウザ上で内容を確認してください。")

            while context.pages:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            if context is not None:
                close_browser_safely(context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
