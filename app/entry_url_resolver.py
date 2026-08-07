from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


KNSHOW_HOSTS = {"knshow.com", "www.knshow.com"}
SENSITIVE_QUERY_KEYS = {"cookie", "session", "sessionid", "csrf", "xsrf", "token"}


@dataclass
class ResolveResult:
    resolved_entry_url: str
    resolved_domain: str
    resolve_status: str
    resolve_reason: str
    resolved_at: str


def is_rd_link(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.netloc.casefold() in KNSHOW_HOSTS and parsed.path.startswith("/rd/")


def is_external_url(url: str) -> bool:
    host = urlparse(url or "").netloc.casefold()
    return bool(host and host not in KNSHOW_HOSTS)


def classify_resolution(url: str, has_captcha: bool = False) -> tuple[str, str]:
    lowered = (url or "").casefold()
    host = urlparse(url or "").netloc.casefold()
    if "x.com" in host or "twitter.com" in host:
        return "BLOCKED_X", "x domain"
    if "line.me" in host or "line.naver.jp" in host:
        return "BLOCKED_LINE", "line domain"
    if "instagram.com" in host:
        return "BLOCKED_INSTAGRAM", "instagram domain"
    if "apps.apple.com" in host or "play.google.com" in host or "app" in lowered and "download" in lowered:
        return "BLOCKED_APP", "app required"
    if any(token in lowered for token in ("login", "signin", "sign-in", "auth")):
        return "BLOCKED_LOGIN", "login required"
    if has_captcha or any(token in lowered for token in ("captcha", "recaptcha", "hcaptcha")):
        return "BLOCKED_CAPTCHA", "captcha detected"
    if is_external_url(url):
        return "RESOLVED", "external destination"
    return "UNRESOLVED", "final url remained on knshow"


def sanitize_resolved_url(url: str) -> str:
    parsed = urlparse(url or "")
    safe_query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.casefold() not in SENSITIVE_QUERY_KEYS]
    )
    return urlunparse(parsed._replace(query=safe_query, fragment=""))


def resolve_rd_url(page, rd_url: str, timeout_ms: int = 60000) -> ResolveResult:
    page.goto(rd_url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_timeout(2500)
    except Exception:
        pass
    final_url = sanitize_resolved_url(page.url)
    has_captcha = False
    try:
        has_captcha = page.locator('iframe[src*="captcha"], [name*="captcha"], [id*="captcha"]').count() > 0
    except Exception:
        has_captcha = False
    status, reason = classify_resolution(final_url, has_captcha=has_captcha)
    return ResolveResult(
        resolved_entry_url=final_url if status == "RESOLVED" else "",
        resolved_domain=urlparse(final_url).netloc.casefold() if final_url else "",
        resolve_status=status,
        resolve_reason=reason,
        resolved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def target_url_for_campaign(campaign: dict[str, str]) -> str:
    return campaign.get("resolved_entry_url", "") or campaign.get("entry_url", "") or campaign.get("knshow_url", "")


def has_resolved_form_url(campaign: dict[str, str]) -> bool:
    return bool(campaign.get("resolved_entry_url", "")) and campaign.get("resolve_status", "") == "RESOLVED"
