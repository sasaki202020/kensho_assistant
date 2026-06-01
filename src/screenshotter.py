from __future__ import annotations

from pathlib import Path
from typing import Any

from .autopilot_shared import LeadRecord, ensure_dir, write_placeholder_png


def _placeholder_lines(lead: LeadRecord, reason: str, url: str = "") -> list[str]:
    lines = [
        f"company: {lead.company_name}",
        f"industry: {lead.industry}",
        f"area: {lead.area}",
    ]
    if url:
        lines.append(f"url: {url}")
    lines.append(f"reason: {reason}")
    return lines


def _capture_with_playwright(url: str, output_dir: Path) -> dict[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"status": f"playwright_missing: {exc}"}

    screenshots = {
        "desktop.png": "desktop",
        "mobile.png": "mobile",
        "contact_area.png": "contact_area",
    }
    results: dict[str, str] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 2200}, ignore_https_errors=True)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            results["desktop.png"] = "ok"
            page.screenshot(path=str(output_dir / "desktop.png"), full_page=True)

            mobile_context = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                ignore_https_errors=True,
            )
            mobile_page = mobile_context.new_page()
            mobile_page.goto(url, wait_until="domcontentloaded", timeout=45000)
            mobile_page.screenshot(path=str(output_dir / "mobile.png"), full_page=True)
            results["mobile.png"] = "ok"

            contact_candidates = [
                "a[href*='contact']",
                "a[href*='inquiry']",
                "button:has-text('お問い合わせ')",
                "a:has-text('お問い合わせ')",
                "text=/お問い合わせ|問合せ|Contact|予約|無料相談/",
            ]
            contact_locator = None
            for selector in contact_candidates:
                locator = page.locator(selector)
                if locator.count():
                    contact_locator = locator.first
                    break
            if contact_locator is None:
                page.screenshot(path=str(output_dir / "contact_area.png"), full_page=False)
            else:
                box = contact_locator.bounding_box()
                if box:
                    clip = {
                        "x": max(box["x"] - 24, 0),
                        "y": max(box["y"] - 24, 0),
                        "width": min(box["width"] + 48, 1440),
                        "height": min(box["height"] + 48, 900),
                    }
                    page.screenshot(path=str(output_dir / "contact_area.png"), clip=clip)
                else:
                    page.screenshot(path=str(output_dir / "contact_area.png"), full_page=False)
            results["contact_area.png"] = "ok"
            browser.close()
        return results
    except Exception as exc:
        return {"status": f"capture_failed: {exc}"}


def _capture_single(url: str, output_path: Path) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        write_placeholder_png(output_path, [f"url: {url}", f"reason: {exc}"])
        return f"playwright_missing: {exc}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.screenshot(path=str(output_path), full_page=True)
            browser.close()
            return "ok"
    except Exception as exc:
        write_placeholder_png(output_path, [f"url: {url}", f"reason: {exc}"])
        return f"capture_failed: {exc}"


def capture_screenshots(
    lead: LeadRecord,
    company_dir: Path,
    website_url: str,
    competitor_urls: list[str] | None = None,
    *,
    sample_mode: bool = False,
) -> dict[str, Any]:
    screenshots_dir = ensure_dir(company_dir / "screenshots")
    status: dict[str, str] = {}
    if sample_mode or not website_url:
        for name in ("desktop.png", "mobile.png", "contact_area.png"):
            write_placeholder_png(screenshots_dir / name, _placeholder_lines(lead, "sample_or_missing_url", website_url))
            status[name] = "placeholder"
    else:
        result = _capture_with_playwright(website_url, screenshots_dir)
        capture_status = result.pop("status", "")
        if capture_status:
            for name in ("desktop.png", "mobile.png", "contact_area.png"):
                write_placeholder_png(screenshots_dir / name, _placeholder_lines(lead, capture_status, website_url))
                status[name] = capture_status
        else:
            status.update(result)
    competitors = competitor_urls or []
    competitor_status: dict[str, str] = {}
    for index in range(1, 3):
        filename = f"competitor_{index}.png"
        competitor_url = competitors[index - 1] if index - 1 < len(competitors) else ""
        if not competitor_url or sample_mode:
            write_placeholder_png(screenshots_dir / filename, _placeholder_lines(lead, "competitor_placeholder", competitor_url))
            competitor_status[filename] = "placeholder"
            continue
        competitor_status[filename] = _capture_single(competitor_url, screenshots_dir / filename)
    return {
        "status": "placeholder"
        if sample_mode or not website_url
        else "ok"
        if not any(str(value).startswith(("capture_failed", "playwright_missing")) for value in {**status, **competitor_status}.values())
        else "partial",
        "screenshots_dir": str(screenshots_dir),
        "screenshot_status": {**status, **competitor_status},
    }
