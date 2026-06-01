from __future__ import annotations

from pathlib import Path

from .paths import CHROME_USER_DATA_DIR


def get_browser_profile_dir() -> Path:
    CHROME_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return CHROME_USER_DATA_DIR


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


def open_url_in_chrome(playwright, url: str, browser_name: str = "chrome"):
    context, actual_browser = launch_chrome_headed(playwright, browser_name)
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    return context, page, actual_browser


def close_browser_safely(context) -> None:
    try:
        context.close()
    except Exception:
        pass


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
