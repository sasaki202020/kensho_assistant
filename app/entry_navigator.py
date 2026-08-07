from __future__ import annotations

from dataclasses import dataclass


ENTRY_TERMS = (
    "応募フォームへ",
    "応募画面へ",
)

FINAL_TERMS = (
    "応募を確定",
    "応募完了",
    "送信する",
    "申し込む",
    "この内容で送信",
    "submit",
)

MAJOR_FIELD_SELECTOR = ", ".join(
    [
        'input[type="email"]',
        'input[type="tel"]',
        'input[autocomplete*="name" i]',
        'input[autocomplete*="postal" i]',
        'input[autocomplete*="address" i]',
        'input[name*="name" i]',
        'input[name*="mail" i]',
        'input[name*="email" i]',
        'input[name*="address" i]',
        'input[name*="postal" i]',
        'input[name*="zip" i]',
        'input[name*="phone" i]',
        'input[name*="tel" i]',
    ]
)


@dataclass(frozen=True)
class EntryNavigationResult:
    reached_form: bool
    clicked_count: int
    stop_reason: str


def _has_entry_form(page) -> bool:
    try:
        return page.locator(MAJOR_FIELD_SELECTOR).count() > 0
    except Exception:
        return False


def _candidate(page):
    locator = page.locator('a, button, input[type="button"], input[type="submit"]')
    try:
        items = locator.evaluate_all(
            """nodes => nodes.map((node, index) => ({
                index,
                text: (node.innerText || node.value || node.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim(),
                disabled: Boolean(node.disabled),
                insideForm: Boolean(node.closest('form')),
                tag: node.tagName.toLowerCase(),
                type: (node.getAttribute('type') || '').toLowerCase()
            }))"""
        )
    except Exception:
        return None
    for item in items:
        text = str(item.get("text", "")).casefold()
        if not text or item.get("disabled"):
            continue
        if item.get("type") == "submit":
            continue
        if any(term.casefold() in text for term in FINAL_TERMS):
            continue
        if not any(term.casefold() in text for term in ENTRY_TERMS):
            continue
        if item.get("insideForm") and item.get("tag") != "a":
            continue
        return locator.nth(int(item["index"]))
    return None


def advance_to_entry_form(page, max_steps: int = 2) -> EntryNavigationResult:
    clicked = 0
    for _ in range(max(int(max_steps), 0) + 1):
        if _has_entry_form(page):
            return EntryNavigationResult(True, clicked, "entry_form_detected")
        if clicked >= max_steps:
            break
        candidate = _candidate(page)
        if candidate is None:
            break
        candidate.click()
        clicked += 1
        try:
            page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
    return EntryNavigationResult(_has_entry_form(page), clicked, "entry_form_not_reached")
