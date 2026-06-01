from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .apply_queue import _deadline_bucket
from .entry_url_resolver import has_resolved_form_url
from .knshow_scraper import (
    BASE_URL,
    build_keyword_search_url,
    collect_by_category,
    collect_by_keyword,
    get_category_links,
    get_top_keywords,
)
from .models import CAMPAIGN_HEADERS
from .paths import CAMPAIGNS_CSV, RESEARCH_REPORT_JSON, RESEARCH_REPORT_MD, ensure_runtime_dirs
from .release_report import latest_inspections
from .storage import ensure_csv, read_csv_rows, write_csv_rows


RESEARCH_CATEGORY_LABELS = [
    "大量当選",
    "締切間近",
    "食品",
    "飲料",
    "商品券",
    "家電",
    "日用品",
    "化粧品",
    "旅行",
    "映画・チケット",
    "Amazonギフト券",
    "QUOカード",
    "ビール",
    "コーヒー",
    "お菓子",
    "ゲーム",
    "スマホ",
    "防災用品",
]

RESEARCH_KEYWORDS = [
    "Amazonギフト券",
    "QUOカード",
    "商品券",
    "ビール",
    "お菓子",
    "コーヒー",
    "お米",
    "肉",
    "家電",
    "旅行券",
    "チケット",
    "大量当選",
    "現金",
    "ポイント",
]

POSITIVE_WEB_HINTS = ("webフォーム", "応募フォーム", "form", "google.com/forms", "form.run", "app-form.net", "cp-form.jp")
NEGATIVE_CHANNEL_HINTS = {
    "x": ("x.com", "twitter", "旧twitter", "X応募", "x応募"),
    "instagram": ("instagram", "インスタ"),
    "line": ("line",),
    "app": ("アプリ", "app store", "google play"),
}
NEGATIVE_RISK_HINTS = {
    "会員登録": ("会員登録", "member"),
    "ログイン": ("ログイン", "login"),
    "購入条件": ("購入", "purchase"),
    "レシート": ("レシート", "receipt"),
    "captcha": ("captcha",),
    "クイズ": ("クイズ",),
    "年齢確認": ("年齢", "生年月日", "birth"),
    "規約同意": ("利用規約", "規約", "同意"),
}


def _text(row: dict[str, str]) -> str:
    parts = [
        row.get("campaign_name", ""),
        row.get("prize", ""),
        row.get("provider", ""),
        row.get("deadline", ""),
        row.get("description", ""),
        row.get("category", ""),
        row.get("entry_type_raw", ""),
        row.get("status", ""),
        row.get("resolve_status", ""),
        row.get("resolve_reason", ""),
        row.get("form_readiness_status", ""),
        row.get("form_readiness_reason", ""),
        row.get("notes", ""),
        row.get("research_keyword", ""),
        row.get("research_category", ""),
    ]
    return " ".join(parts).casefold()


def _count_manual_fields(inspection: dict[str, object] | None) -> int:
    if not inspection:
        return 0
    value = inspection.get("manual_review_required_fields", "")
    if isinstance(value, list):
        return len([item for item in value if str(item).strip()])
    text = str(value or "")
    return len([part for part in re.split(r"[,\s、/]+", text) if part.strip()])


def _winner_count_score(text: str) -> int:
    match = re.search(r"(\d[\d,]*)\s*名", text)
    if not match:
        return 0
    try:
        value = int(match.group(1).replace(",", ""))
    except ValueError:
        return 0
    if value >= 1000:
        return 15
    if value >= 100:
        return 12
    if value >= 20:
        return 8
    if value >= 5:
        return 4
    return 0


def _deadline_score(deadline: str) -> int:
    bucket, _ = _deadline_bucket(deadline)
    if bucket == 0:
        return 8
    if bucket == 1:
        return 6
    if bucket == 2:
        return 4
    if bucket == 3:
        return 0
    return -8


def _risk_hits(text: str) -> list[str]:
    hits: list[str] = []
    for label, needles in NEGATIVE_CHANNEL_HINTS.items():
        if any(needle in text for needle in needles):
            hits.append(label)
    for label, needles in NEGATIVE_RISK_HINTS.items():
        if any(needle in text for needle in needles):
            hits.append(label)
    return hits


def _contains_x_channel(text: str) -> bool:
    if "x.com" in text or "twitter" in text:
        return True
    return bool(re.search(r"(?<![a-z0-9])x(?![a-z0-9])", text))


def _opportunity_reason_parts(campaign: dict[str, str], inspection: dict[str, object] | None, score: int) -> list[str]:
    reasons: list[str] = []
    if has_resolved_form_url(campaign):
        reasons.append("URL解決済み")
    readiness = campaign.get("form_readiness_status", "")
    if readiness == "READY_FOR_FILL":
        reasons.append("フォーム診断済み")
    elif readiness == "REVIEW_ONLY":
        reasons.append("要確認だが診断済み")
    if "webフォーム" in _text(campaign) or any(hint in _text(campaign) for hint in POSITIVE_WEB_HINTS):
        reasons.append("Webフォーム応募")
    manual_fields = _count_manual_fields(inspection)
    if inspection and manual_fields <= 2:
        reasons.append("手動確認項目が少ない")
    if score >= 80:
        reasons.append("狙い目")
    elif score < 40:
        reasons.append("除外寄り")
    return reasons[:3]


def _recommendation_from_score(
    campaign: dict[str, str],
    inspection: dict[str, object] | None,
    score: int,
    risk_level: str,
    risk_reasons: list[str],
) -> tuple[str, str]:
    text = _text(campaign)
    readiness = campaign.get("form_readiness_status", "")
    if any(token in text for token in NEGATIVE_CHANNEL_HINTS["line"]):
        return "LINE応募のため自動操作対象外です。", "除外推奨"
    if any(token in text for token in NEGATIVE_CHANNEL_HINTS["instagram"]):
        return "Instagram応募のため自動操作対象外です。", "除外推奨"
    if _contains_x_channel(text):
        return "X応募のため自動操作対象外です。", "除外推奨"
    if any(token in text for token in NEGATIVE_CHANNEL_HINTS["app"]):
        return "アプリ応募のため自動操作対象外です。", "除外推奨"
    if any(token in text for token in NEGATIVE_RISK_HINTS["レシート"]):
        return "レシート応募のため除外推奨です。", "除外推奨"
    if any(token in text for token in NEGATIVE_RISK_HINTS["購入条件"]):
        return "購入条件ありのため手間が多いです。", "除外推奨"
    if any(token in text for token in NEGATIVE_RISK_HINTS["captcha"]):
        return "CAPTCHAがあるため自動化対象外です。", "除外推奨"
    if any(token in text for token in NEGATIVE_RISK_HINTS["ログイン"]):
        return "ログイン必須のため手動確認が必要です。", "手動確認"
    if any(token in text for token in NEGATIVE_RISK_HINTS["年齢確認"]):
        return "年齢確認があるため人間確認扱いです。", "要確認で確認"
    if readiness == "READY_FOR_FILL" and score >= 80:
        return "Webフォーム応募で、購入条件がなく、URL解決済みのため応募準備しやすいです。", "応募キューに追加"
    if readiness in {"READY_FOR_FILL", "REVIEW_ONLY"} and score >= 60:
        reason = "締切が近く、フォーム診断済みです。"
        if any(token in text for token in NEGATIVE_RISK_HINTS["規約同意"]):
            reason = "締切が近く、フォーム診断済みですが、規約確認が必要です。"
        if any(token in text for token in NEGATIVE_RISK_HINTS["クイズ"]):
            reason = "締切が近く、フォーム診断済みですが、クイズ回答は人間確認です。"
        return reason, "要確認で確認"
    if score >= 40:
        return "候補としては有望ですが、手動確認項目があります。", "手動確認"
    if risk_level == "high":
        return "危険要素が多いため除外推奨です。", "除外推奨"
    return "候補はありますが、優先度は低めです。", "要確認で確認"


def calculate_opportunity_score(
    campaign: dict[str, str],
    inspection: dict[str, object] | None = None,
) -> dict[str, object]:
    text = _text(campaign)
    score = 50
    reasons: list[str] = []
    risk_reasons: list[str] = []
    risk_score = 0

    if has_resolved_form_url(campaign):
        score += 12
        reasons.append("URL解決済み")
    if campaign.get("form_readiness_status") == "READY_FOR_FILL":
        score += 22
        reasons.append("READY_FOR_FILL")
    elif campaign.get("form_readiness_status") == "REVIEW_ONLY":
        score += 14
        reasons.append("REVIEW_ONLY")
    elif campaign.get("form_readiness_status") == "SEARCH_ONLY":
        score -= 16
        risk_reasons.append("SEARCH_ONLY")
        risk_score += 2
    elif campaign.get("form_readiness_status") == "LANDING_PAGE":
        score -= 18
        risk_reasons.append("LANDING_PAGE")
        risk_score += 3
    elif campaign.get("form_readiness_status") == "LOW_CONFIDENCE":
        score -= 20
        risk_reasons.append("LOW_CONFIDENCE")
        risk_score += 3

    if "web" in text or any(hint in text for hint in POSITIVE_WEB_HINTS):
        score += 12
        reasons.append("Webフォーム応募")

    score += _winner_count_score(text)
    deadline_bonus = _deadline_score(campaign.get("deadline", ""))
    score += deadline_bonus
    if deadline_bonus > 0:
        reasons.append("締切が近い")

    manual_fields = _count_manual_fields(inspection)
    if inspection and manual_fields == 0:
        score += 8
        reasons.append("手動確認項目が少ない")
    elif inspection and manual_fields <= 2:
        score += 5
        reasons.append("手動確認項目が少ない")
    elif manual_fields >= 4:
        score -= 8
        risk_reasons.append("manual_review_many")
        risk_score += 1

    if "purchase" not in text and "receipt" not in text and "login" not in text and "captcha" not in text:
        score += 5
        reasons.append("入力負担が軽い")

    for label, needles in NEGATIVE_CHANNEL_HINTS.items():
        if label == "x":
            hit = _contains_x_channel(text)
        else:
            hit = any(needle in text for needle in needles)
        if hit:
            score -= 24 if label in {"x", "instagram", "line"} else 18
            risk_reasons.append(label)
            risk_score += 3 if label in {"x", "instagram", "line"} else 2

    for label, needles in NEGATIVE_RISK_HINTS.items():
        if any(needle in text for needle in needles):
            if label == "クイズ":
                score -= 10
                risk_score += 2
            elif label == "年齢確認":
                score -= 8
                risk_score += 2
            elif label == "規約同意":
                score -= 4
                risk_score += 1
            else:
                score -= 14
                risk_score += 3
            risk_reasons.append(label)

    if "大量当選" in text:
        score += 6
        reasons.append("大量当選")

    score = max(0, min(100, score))
    if score >= 80:
        risk_level = "low"
    elif score >= 60:
        risk_level = "medium"
    else:
        risk_level = "high"
    if any(item in {"x", "instagram", "line", "app", "captcha", "購入条件", "レシート"} for item in risk_reasons):
        risk_level = "high"
    elif risk_level != "high" and risk_score >= 4:
        risk_level = "medium"

    opportunity_reason = " / ".join(dict.fromkeys(reasons[:4]))
    risk_reason_text = " / ".join(dict.fromkeys(risk_reasons[:4]))
    recommendation_reason, next_action = _recommendation_from_score(campaign, inspection, score, risk_level, risk_reasons)
    return {
        "opportunity_score": score,
        "opportunity_reason": opportunity_reason,
        "risk_level": risk_level,
        "risk_reasons": risk_reason_text,
        "recommendation_reason": recommendation_reason,
        "next_action": next_action,
    }


def _category_url(category: str) -> str:
    category = (category or "").strip()
    if not category:
        return BASE_URL
    for label, href in get_category_links(limit=50):
        if label == category or category in label:
            return href
    return build_keyword_search_url(category)


def collect_research_campaigns(
    *,
    keyword: str = "",
    category: str = "",
    limit: int = 30,
) -> list[dict[str, str]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    rows: list[dict[str, str]] = []
    if keyword:
        collected = collect_by_keyword(keyword, limit=limit)
        for row in collected:
            row = dict(row)
            row["research_keyword"] = keyword
            row["research_category"] = category or row.get("category", "")
            row["research_source"] = "keyword"
            row["discovered_at"] = timestamp
            rows.append(row)
    elif category:
        collected = collect_by_category(_category_url(category), limit=limit)
        for row in collected:
            row = dict(row)
            row["research_keyword"] = ""
            row["research_category"] = category
            row["research_source"] = "category"
            row["discovered_at"] = timestamp
            rows.append(row)
    else:
        for keyword_value in get_top_keywords(limit=min(limit, len(RESEARCH_KEYWORDS))):
            collected = collect_by_keyword(keyword_value, limit=max(1, limit // 4))
            for row in collected:
                row = dict(row)
                row["research_keyword"] = keyword_value
                row["research_category"] = row.get("category", "")
                row["research_source"] = "keyword"
                row["discovered_at"] = timestamp
                rows.append(row)

    unique_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        key = row.get("campaign_id", "") or row.get("knshow_url", "") or row.get("entry_url", "")
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows[:limit]


def annotate_research_rows(rows: Iterable[dict[str, str]], inspections: dict[str, dict[str, object]] | None = None) -> list[dict[str, str]]:
    inspection_rows = inspections if inspections is not None else latest_inspections()
    annotated: list[dict[str, str]] = []
    source_rows = list(rows)
    scored = []
    for row in source_rows:
        campaign_id = row.get("campaign_id", "")
        inspection = inspection_rows.get(campaign_id, {})
        metrics = calculate_opportunity_score(row, inspection)
        scored.append((row, metrics))
    scored.sort(key=lambda item: (-int(item[1]["opportunity_score"]), item[0].get("deadline", ""), item[0].get("campaign_name", "")))
    for rank, (row, metrics) in enumerate(scored, start=1):
        updated = dict(row)
        updated.update(
            {
                "opportunity_score": str(metrics["opportunity_score"]),
                "opportunity_rank": str(rank),
                "opportunity_reason": str(metrics["opportunity_reason"]),
                "risk_level": str(metrics["risk_level"]),
                "risk_reasons": str(metrics["risk_reasons"]),
                "recommendation_reason": str(metrics["recommendation_reason"]),
                "next_action": str(metrics["next_action"]),
            }
        )
        annotated.append(updated)
    return annotated


def refresh_campaign_research_fields(path: Path = CAMPAIGNS_CSV) -> list[dict[str, str]]:
    ensure_runtime_dirs()
    rows = read_csv_rows(path)
    annotated = annotate_research_rows(rows)
    by_id = {row.get("campaign_id", ""): row for row in annotated}
    updated: list[dict[str, str]] = []
    for row in rows:
        campaign_id = row.get("campaign_id", "")
        merged = dict(row)
        metrics = by_id.get(campaign_id, {})
        merged.update(metrics)
        updated.append(merged)
    if updated:
        ensure_csv(path, CAMPAIGN_HEADERS)
        write_csv_rows(path, updated, CAMPAIGN_HEADERS)
    return updated


def build_research_report(rows: Iterable[dict[str, str]] | None = None) -> dict[str, object]:
    source_rows = list(rows) if rows is not None else refresh_campaign_research_fields()
    annotated = annotate_research_rows(source_rows)
    total = len(source_rows)
    score_bins = {
        "80_plus": sum(1 for row in annotated if int(row.get("opportunity_score", "0") or 0) >= 80),
        "60_79": sum(1 for row in annotated if 60 <= int(row.get("opportunity_score", "0") or 0) <= 79),
        "40_59": sum(1 for row in annotated if 40 <= int(row.get("opportunity_score", "0") or 0) <= 59),
        "0_39": sum(1 for row in annotated if int(row.get("opportunity_score", "0") or 0) < 40),
    }
    category_counts = Counter((row.get("research_category") or row.get("category") or "未分類") for row in annotated)
    keyword_counts = Counter((row.get("research_keyword") or "未指定") for row in annotated if row.get("research_keyword"))
    risk_counts = Counter((row.get("risk_reasons") or "なし") for row in annotated)
    deadline_soon = sum(1 for row in annotated if _deadline_bucket(row.get("deadline", ""))[0] in {0, 1, 2})
    top_rows = annotated[:10]
    next_rows = [
        row
        for row in annotated
        if row.get("next_action") in {"応募キューに追加", "要確認で確認", "手動確認"}
    ][:10]
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": total,
        "category_counts": dict(category_counts.most_common()),
        "keyword_counts": dict(keyword_counts.most_common()),
        "score_bins": score_bins,
        "deadline_soon_count": deadline_soon,
        "top_candidates": top_rows,
        "exclude_reasons": dict(risk_counts.most_common()),
        "next_candidates": next_rows,
        "research_keywords": RESEARCH_KEYWORDS,
        "research_categories": RESEARCH_CATEGORY_LABELS,
    }
    return report


def render_research_report(report: dict[str, object]) -> str:
    lines = [
        "# Research report latest",
        f"- generated_at: {report['generated_at']}",
        f"- total: {report['total']}",
        f"- score_80_plus: {report['score_bins']['80_plus']}",
        f"- score_60_79: {report['score_bins']['60_79']}",
        f"- score_40_59: {report['score_bins']['40_59']}",
        f"- score_0_39: {report['score_bins']['0_39']}",
        f"- deadline_soon_count: {report['deadline_soon_count']}",
        "",
        "## カテゴリ別件数",
    ]
    for label, count in report["category_counts"].items():
        lines.append(f"- {label}: {count}")
    lines.extend(["", "## キーワード別件数"])
    for label, count in report["keyword_counts"].items():
        lines.append(f"- {label}: {count}")
    lines.extend(["", "## 上位おすすめ懸賞"])
    for row in report["top_candidates"]:
        lines.append(
            f"- {row.get('opportunity_score', '')} / {row.get('campaign_name', '')} / {row.get('recommendation_reason', '')}"
        )
    lines.extend(["", "## 除外理由ランキング"])
    for label, count in report["exclude_reasons"].items():
        lines.append(f"- {label}: {count}")
    lines.extend(["", "## 次に見るべき候補"])
    for row in report["next_candidates"]:
        lines.append(
            f"- {row.get('opportunity_score', '')} / {row.get('campaign_name', '')} / {row.get('next_action', '')}"
        )
    return "\n".join(lines) + "\n"


def save_research_report(report: dict[str, object]) -> tuple[Path, Path]:
    RESEARCH_REPORT_MD.write_text(render_research_report(report), encoding="utf-8")
    RESEARCH_REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return RESEARCH_REPORT_MD, RESEARCH_REPORT_JSON
