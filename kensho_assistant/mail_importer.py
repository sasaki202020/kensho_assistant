from __future__ import annotations

import email
import hashlib
import json
import re
from datetime import date, datetime
from email import policy
from email.message import Message
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .app.entry_history import (
    build_win_mail_candidate,
    load_win_mail_candidates as _load_win_mail_candidates,
    save_win_mail_candidates as _save_win_mail_candidates,
    summarize_win_mail_candidates,
)
from .app.models import CAMPAIGN_HEADERS
from .app.paths import CAMPAIGNS_CSV, MAIL_SAMPLES_DIR, MAIL_SWEEPSTAKES_JSON, WIN_MAIL_CANDIDATES_JSONL
from .app.storage import ensure_csv, read_csv_rows, write_csv_rows

WIN_MAIL_KEYWORDS = ("当選", "おめでとうございます", "当選通知", "プレゼント発送", "賞品", "クーポン", "引換")
MAIL_KEYWORDS = ("懸賞", "プレゼント", "応募", "キャンペーン", "当選", "賞品", "本日限定", "無料", "メール懸賞", *WIN_MAIL_KEYWORDS)
DEADLINE_PATTERNS = (
    r"\d{4}年\d{1,2}月\d{1,2}日中",
    r"\d{4}年\d{1,2}月\d{1,2}日まで",
    r"\d{1,2}月\d{1,2}日まで",
    r"本日限定",
    r"明日まで",
    r"期間限定",
)
HIGH_RISK_TERMS = ("個人情報", "クレジットカード", "カード番号", "住所", "電話番号", "生年月日", "口座", "年齢確認")
URGENCY_TERMS = ("本日限定", "今すぐ", "先着", "急いで", "残りわずか", "締切", "終了間近")
SHORTENER_DOMAINS = {
    "bit.ly",
    "t.co",
    "tinyurl.com",
    "goo.gl",
    "is.gd",
    "x.gd",
    "cutt.ly",
}
CAMPAIGN_URL_TERMS = ("懸賞", "prize", "campaign", "present", "apply", "present", "entry")


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        normalized = url.strip().rstrip(".,;:）)］］】」』")
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def _extract_urls(text: str) -> list[str]:
    return _dedupe_urls(re.findall(r"https?://[^\s<>'\"）)】]+", text or "", flags=re.IGNORECASE))


def _extract_deadline_text(text: str) -> str:
    for pattern in DEADLINE_PATTERNS:
        match = re.search(pattern, text or "")
        if match:
            return match.group(0)
    return ""


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower()


def _score_campaign_url(url: str) -> int:
    score = 0
    text = url.lower()
    for term in CAMPAIGN_URL_TERMS:
        if term in text:
            score += 3
    if "http://" in text:
        score += 1
    if any(term in text for term in ("campaign", "prize", "present", "apply")):
        score += 3
    return score


def _choose_campaign_url(urls: list[str], text: str) -> str:
    if not urls:
        return ""
    ranked = sorted(urls, key=lambda url: (_score_campaign_url(url), len(url)), reverse=True)
    if ranked:
        return ranked[0]
    return urls[0]


def _deadline_state(deadline_text: str) -> str:
    text = _collapse(deadline_text)
    if not text:
        return "unknown"
    today = date.today()
    if "期限切れ" in text or "終了" in text or "締切切れ" in text:
        return "expired"
    if "本日限定" in text or "本日" in text or "今日" in text:
        return "today"
    if "明日まで" in text or "明日" in text:
        return "tomorrow"
    if "今週" in text or "週末" in text:
        return "this_week"
    match = re.search(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日(?:中|まで)?", text)
    if match:
        year = int(match.group(1) or today.year)
        month = int(match.group(2))
        day = int(match.group(3))
        try:
            target = date(year, month, day)
        except ValueError:
            return "unknown"
        delta = (target - today).days
        if delta < 0:
            return "expired"
        if delta == 0:
            return "today"
        if delta == 1:
            return "tomorrow"
        if delta <= 7:
            return "this_week"
        return "future"
    return "unknown"


def _deadline_sort_key(deadline_text: str) -> tuple[int, int, int]:
    state = _deadline_state(deadline_text)
    order = {
        "today": 0,
        "tomorrow": 1,
        "this_week": 2,
        "future": 3,
        "unknown": 4,
        "expired": 5,
    }.get(state, 4)
    match = re.search(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", deadline_text or "")
    if match:
        year = int(match.group(1) or date.today().year)
        return order, int(match.group(2)), int(match.group(3))
    return order, 99, 99


def _candidate_keywords(text: str) -> list[str]:
    hits = [keyword for keyword in MAIL_KEYWORDS if keyword in text]
    return hits


def _high_risk_reasons(subject: str, sender: str, body: str, urls: list[str], campaign_url: str) -> list[str]:
    reasons: list[str] = []
    text = f"{subject}\n{sender}\n{body}"
    if any(url.startswith("http://") for url in urls):
        reasons.append("httpのみのURL")
    if any(_domain(url) in SHORTENER_DOMAINS for url in urls):
        reasons.append("短縮URL")
    if campaign_url:
        campaign_domain = _domain(campaign_url)
        found_domains = {
            match.lower()
            for match in re.findall(r"(?:https?://)?([a-z0-9.-]+\.[a-z]{2,})", text, flags=re.IGNORECASE)
        }
        if found_domains and campaign_domain not in found_domains:
            reasons.append("本文表示ドメインと実URLのドメインが違う")
    if any(term in text for term in HIGH_RISK_TERMS):
        reasons.append("個人情報やカード入力を要求")
    if any(len(_domain(url).split(".")) >= 4 for url in urls):
        reasons.append("不自然なドメイン")
    return reasons


def _risk_level(subject: str, sender: str, body: str, urls: list[str], campaign_url: str) -> tuple[str, list[str]]:
    reasons = _high_risk_reasons(subject, sender, body, urls, campaign_url)
    if reasons:
        return "high", reasons
    text = f"{subject}\n{body}"
    urgency = [term for term in URGENCY_TERMS if term in text]
    if urgency:
        return "medium", ["締切を煽る文言"]
    if _candidate_keywords(text) or urls:
        if len(urls) > 1 or _extract_deadline_text(body):
            return "medium", ["懸賞候補だが複数条件を確認"]
        return "low", []
    return "low", []


def _parse_txt_like(path: Path) -> tuple[str, str, str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    headers, _, body = text.partition("\n\n")
    header_map: dict[str, str] = {}
    for line in headers.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            header_map[key.strip().lower()] = value.strip()
    subject = header_map.get("subject", path.stem)
    sender = header_map.get("from", "")
    received_at = header_map.get("date", header_map.get("received", ""))
    body = body.strip() if body else text.strip()
    return subject, sender, received_at, body


def _parse_html(path: Path) -> tuple[str, str, str, str]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    subject_tag = soup.find("meta", attrs={"name": re.compile("subject", re.I)})
    from_tag = soup.find("meta", attrs={"name": re.compile("from", re.I)})
    date_tag = soup.find("meta", attrs={"name": re.compile("date|received", re.I)})
    body_text = _collapse(soup.get_text(" ", strip=True))
    subject = subject_tag.get("content", "").strip() if subject_tag else title or path.stem
    sender = from_tag.get("content", "").strip() if from_tag else ""
    received_at = date_tag.get("content", "").strip() if date_tag else ""
    return subject, sender, received_at, body_text


def _parse_eml(path: Path) -> tuple[str, str, str, str]:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    subject = str(msg.get("Subject", "")).strip() or path.stem
    sender = str(msg.get("From", "")).strip()
    received_at = str(msg.get("Date", "")).strip()
    body_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body_parts.append(part.get_content())
                except Exception:
                    continue
            elif part.get_content_type() == "text/html" and not body_parts:
                try:
                    html = part.get_content()
                    body_parts.append(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
                except Exception:
                    continue
    else:
        try:
            body = msg.get_content()
            if msg.get_content_type() == "text/html":
                body_parts.append(BeautifulSoup(body, "html.parser").get_text(" ", strip=True))
            else:
                body_parts.append(str(body))
        except Exception:
            body_parts.append("")
    return subject, sender, received_at, _collapse(" ".join(body_parts))


def _parse_mail_file(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        subject, sender, received_at, body = _parse_html(path)
    elif suffix == ".eml":
        subject, sender, received_at, body = _parse_eml(path)
    else:
        subject, sender, received_at, body = _parse_txt_like(path)
    text = _collapse(f"{subject}\n{sender}\n{body}")
    urls = _extract_urls(body)
    campaign_url = _choose_campaign_url(urls, text)
    deadline_text = _extract_deadline_text(text)
    keywords = _candidate_keywords(text)
    risk_level, risk_reasons = _risk_level(subject, sender, body, urls, campaign_url)
    status = "ignored"
    if keywords:
        status = "danger" if risk_level == "high" else "candidate"
    if risk_level == "high" and not risk_reasons:
        risk_reasons = ["高リスク判定"]
    mail_id = hashlib.sha1(f"{path.stem}|{subject}|{sender}|{campaign_url}".encode("utf-8")).hexdigest()[:12]
    return {
        "mail_id": f"mail-{mail_id}",
        "source_file": str(path.as_posix()),
        "subject": subject,
        "sender": sender,
        "received_at": received_at,
        "body_excerpt": _collapse(body)[:180].strip(),
        "urls": urls,
        "campaign_url": campaign_url,
        "deadline_text": deadline_text,
        "deadline_state": _deadline_state(deadline_text),
        "deadline_sort_key": _deadline_sort_key(deadline_text),
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "status": status,
        "keyword_hits": keywords,
        "selected_by_user": False,
        "excluded_by_user": False,
        "added_at": "",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_mail_sweepstakes(path: Path = MAIL_SWEEPSTAKES_JSON) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_mail_sweepstakes(rows: list[dict[str, object]], path: Path = MAIL_SWEEPSTAKES_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_win_mail_candidates(path: Path = WIN_MAIL_CANDIDATES_JSONL) -> list[dict[str, object]]:
    return _load_win_mail_candidates(path)


def save_win_mail_candidates(rows: list[dict[str, object]], path: Path = WIN_MAIL_CANDIDATES_JSONL) -> None:
    _save_win_mail_candidates(rows, path)


def rescan_mail_sweepstakes(samples_dir: Path = MAIL_SAMPLES_DIR, output_path: Path = MAIL_SWEEPSTAKES_JSON) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen_urls: dict[str, str] = {}
    seen_pairs: dict[str, str] = {}
    if samples_dir.exists():
        for path in sorted(samples_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".txt", ".html", ".htm", ".eml"}:
                row = _parse_mail_file(path)
                duplicate_of = ""
                campaign_url = str(row.get("campaign_url", ""))
                subject = str(row.get("subject", ""))
                sender = str(row.get("sender", ""))
                pair_key = f"{subject.casefold()}|{sender.casefold()}"
                if campaign_url and campaign_url in seen_urls:
                    duplicate_of = seen_urls[campaign_url]
                    row["duplicate_reason"] = "campaign_urlが重複"
                elif pair_key in seen_pairs:
                    duplicate_of = seen_pairs[pair_key]
                    row["duplicate_reason"] = "subject+senderが重複"
                else:
                    if campaign_url:
                        seen_urls[campaign_url] = str(row["mail_id"])
                    if subject or sender:
                        seen_pairs[pair_key] = str(row["mail_id"])
                if duplicate_of:
                    row["status"] = "duplicate"
                    row["duplicate_of"] = duplicate_of
                    row["risk_level"] = "low"
                rows.append(row)
    save_mail_sweepstakes(rows, output_path)
    return rows


def rescan_win_mail_candidates(samples_dir: Path = MAIL_SAMPLES_DIR, output_path: Path = WIN_MAIL_CANDIDATES_JSONL) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if samples_dir.exists():
        for path in sorted(samples_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".txt", ".html", ".htm", ".eml"}:
                mail_item = _parse_mail_file(path)
                text = _collapse(
                    f"{mail_item.get('subject', '')}\n{mail_item.get('sender', '')}\n{mail_item.get('body_excerpt', '')}"
                )
                keyword_hits = [keyword for keyword in WIN_MAIL_KEYWORDS if keyword in text]
                if not keyword_hits and str(mail_item.get("status", "")) not in {"candidate", "danger", "duplicate"}:
                    continue
                row = build_win_mail_candidate(mail_item)
                row["keyword_hits"] = keyword_hits or list(mail_item.get("keyword_hits", []))
                row["status"] = str(mail_item.get("status", "candidate"))
                row["risk_level"] = str(mail_item.get("risk_level", "low"))
                row["risk_reasons"] = list(mail_item.get("risk_reasons", []))
                rows.append(row)
    save_win_mail_candidates(rows, output_path)
    return rows


def get_mail_sweepstake(mail_id: str, path: Path = MAIL_SWEEPSTAKES_JSON) -> dict[str, object]:
    for row in load_mail_sweepstakes(path):
        if row.get("mail_id") == mail_id:
            return row
    return {}


def update_mail_sweepstake(mail_id: str, updates: dict[str, object], path: Path = MAIL_SWEEPSTAKES_JSON) -> dict[str, object]:
    rows = load_mail_sweepstakes(path)
    updated: list[dict[str, object]] = []
    target: dict[str, object] = {}
    for row in rows:
        if row.get("mail_id") == mail_id:
            row = {**row, **updates, "updated_at": datetime.now().isoformat(timespec="seconds")}
            target = row
        updated.append(row)
    save_mail_sweepstakes(updated, path)
    return target


def mail_sweepstakes_summary(rows: list[dict[str, object]]) -> dict[str, int]:
    summary = {"total": len(rows), "candidate": 0, "danger": 0, "ignored": 0, "duplicate": 0, "added": 0}
    for row in rows:
        status = str(row.get("status", "ignored"))
        summary[status if status in summary else "ignored"] += 1
    return summary


def sort_mail_sweepstakes(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    def sort_key(row: dict[str, object]) -> tuple[int, int, int, str]:
        deadline = f"{row.get('subject', '')} {row.get('deadline_text', '')}"
        order, month, day = _deadline_sort_key(deadline)
        return order, month, day, str(row.get("subject", ""))

    return sorted(rows, key=sort_key)
