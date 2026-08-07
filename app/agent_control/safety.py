from __future__ import annotations

import re
from typing import Any, Mapping

from ..privacy_guard import detect_birthdate, detect_email, detect_phone, detect_postal_code, redact_personal_info

SUBMIT_LIKE_RE = re.compile(r"(?i)\b(submit|send|post|click|apply|like|follow|dm)\b")
URL_SCHEME_RE = re.compile(r"(?i)^(javascript|data):")
RISK_KEYWORDS = {
    "blocked": (
        "クレジットカード",
        "card number",
        "bank account",
        "銀行口座",
        "マイナンバー",
        "免許証",
        "パスポート",
        "健康保険証",
        "本人確認書類",
        "短縮url",
        "bit.ly",
        "t.co",
        "goo.gl",
        "tinyurl",
        "LINE誘導",
        "dm誘導",
    ),
    "needs_review": (
        "公式不明",
        "公式サイト不明",
        "official",
        "不明",
        "同意",
        "規約",
        "年齢",
        "生年月日",
        "クイズ",
    ),
}


def _join_metadata(metadata: Mapping[str, Any] | None, key: str) -> str:
    if not metadata:
        return ""
    value = metadata.get(key, "")
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _build_result(
    *,
    status: str,
    result_summary: str,
    safety_memo: str,
    pii_detected: bool,
    submit_attempted: bool = False,
    human_review_required: bool = False,
    blocked_reason: str = "",
    risk_level: str = "low",
    official_confidence: str = "unknown",
    form_check_summary: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "result_summary": result_summary,
        "safety_memo": safety_memo,
        "error_message": "",
        "pii_detected": pii_detected,
        "submit_attempted": submit_attempted,
        "safe_to_submit": False,
        "human_review_required": human_review_required,
        "blocked_reason": blocked_reason,
        "risk_level": risk_level,
        "official_confidence": official_confidence,
        "form_check_summary": form_check_summary,
    }


def detect_pii_like_text(*values: object) -> bool:
    text = " ".join(redact_personal_info(str(value or "")) for value in values)
    raw = " ".join(str(value or "") for value in values)
    return bool(
        detect_email(raw)
        or detect_phone(raw)
        or detect_postal_code(raw)
        or detect_birthdate(raw)
        or SUBMIT_LIKE_RE.search(text)
        or URL_SCHEME_RE.search(raw.strip())
    )


def sanitize_target_url(value: object) -> str:
    text = redact_personal_info(str(value or "")).strip()
    if URL_SCHEME_RE.search(text):
        return "[redacted]"
    return text


def evaluate_control_job(agent_name: str, action: str, target_url: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    agent = str(agent_name or "").strip()
    action_name = str(action or "").strip()
    target = sanitize_target_url(target_url)
    meta = metadata or {}
    form_summary = redact_personal_info(_join_metadata(meta, "form_check_summary"))
    title = redact_personal_info(_join_metadata(meta, "title"))
    required_fields = redact_personal_info(_join_metadata(meta, "required_fields"))
    optional_fields = redact_personal_info(_join_metadata(meta, "optional_fields"))
    consent_fields = redact_personal_info(_join_metadata(meta, "consent_fields"))
    review_reason = redact_personal_info(_join_metadata(meta, "review_reason"))
    blocked_reason = redact_personal_info(_join_metadata(meta, "blocked_reason"))
    official_confidence = str(meta.get("official_confidence", "unknown") or "unknown")
    pii_detected = detect_pii_like_text(agent, action_name, target_url)
    submit_attempted = False
    if pii_detected:
        return {
            **_build_result(
                status="blocked",
                result_summary="PIIらしき入力を検出したためブロックしました",
                safety_memo="PII検出",
                pii_detected=True,
                submit_attempted=submit_attempted,
                blocked_reason="PII検出",
                risk_level="blocked",
                official_confidence=official_confidence,
                form_check_summary=form_summary,
            ),
            "target_url": target,
        }

    if URL_SCHEME_RE.search(str(target_url or "").strip()):
        return {
            **_build_result(
                status="blocked",
                result_summary="危険なURLスキームを検出しました",
                safety_memo="危険URL",
                pii_detected=False,
                submit_attempted=submit_attempted,
                blocked_reason="危険URL",
                risk_level="blocked",
                official_confidence=official_confidence,
                form_check_summary=form_summary,
            ),
            "target_url": target,
        }

    if agent == "HumanReviewAgent" or action_name == "human_review":
        return {
            **_build_result(
                status="needs_review",
                result_summary="人間確認が必要な案件として記録しました",
                safety_memo="人間確認へ送付",
                pii_detected=False,
                submit_attempted=submit_attempted,
                human_review_required=True,
                risk_level="medium",
                official_confidence=official_confidence,
                form_check_summary=form_summary,
            ),
            "target_url": target,
        }

    if agent == "SafetyAgent":
        text = " ".join([agent, action_name, target_url, title, required_fields, optional_fields, consent_fields]).casefold()
        if any(token.casefold() in text for token in RISK_KEYWORDS["blocked"]):
            reason = blocked_reason or "危険な入力項目を検出しました"
            return {
                **_build_result(
                    status="blocked",
                    result_summary=reason,
                    safety_memo="安全確認でブロック",
                    pii_detected=False,
                    submit_attempted=submit_attempted,
                    blocked_reason=reason,
                    risk_level="blocked",
                    official_confidence=official_confidence,
                    form_check_summary=form_summary,
                ),
                "target_url": target,
            }
        if any(token.casefold() in text for token in RISK_KEYWORDS["needs_review"]) or "unknown" in text:
            reason = review_reason or "人間確認が必要です"
            return {
                **_build_result(
                    status="needs_review",
                    result_summary=reason,
                    safety_memo="要確認",
                    pii_detected=False,
                    submit_attempted=submit_attempted,
                    human_review_required=True,
                    blocked_reason="",
                    risk_level="medium",
                    official_confidence=official_confidence,
                    form_check_summary=form_summary or reason,
                ),
                "target_url": target,
            }
        return {
            **_build_result(
                status="done",
                result_summary="危険な自動化は検出されませんでした",
                safety_memo="安全確認完了",
                pii_detected=False,
                submit_attempted=submit_attempted,
                blocked_reason="",
                risk_level="low",
                official_confidence=official_confidence,
                form_check_summary=form_summary,
            ),
            "target_url": target,
        }

    if agent == "ReportAgent":
        return {
            **_build_result(
                status="done",
                result_summary="集計レポートを更新しました",
                safety_memo="ローカル集計のみ",
                pii_detected=False,
                submit_attempted=submit_attempted,
                risk_level="low",
                official_confidence=official_confidence,
                form_check_summary=form_summary,
            ),
            "target_url": target,
        }

    if agent == "QueueAgent":
        queue_status = str(meta.get("queue_status", "") or "").casefold()
        if queue_status == "blocked":
            return {
                **_build_result(
                    status="blocked",
                    result_summary=blocked_reason or "安全上の理由で登録を保留しました",
                    safety_memo="blocked",
                    pii_detected=False,
                    submit_attempted=submit_attempted,
                    blocked_reason=blocked_reason or "blocked",
                    risk_level="blocked",
                    official_confidence=official_confidence,
                    form_check_summary=form_summary,
                ),
                "target_url": target,
            }
        if queue_status == "needs_review":
            return {
                **_build_result(
                    status="needs_review",
                    result_summary=review_reason or "要確認として登録しました",
                    safety_memo="needs_review",
                    pii_detected=False,
                    submit_attempted=submit_attempted,
                    human_review_required=True,
                    blocked_reason="",
                    risk_level="medium",
                    official_confidence=official_confidence,
                    form_check_summary=form_summary,
                ),
                "target_url": target,
            }
        return {
            **_build_result(
                status="done",
                result_summary="候補URLを安全に登録しました",
                safety_memo="ローカル登録のみ",
                pii_detected=False,
                submit_attempted=submit_attempted,
                risk_level="low",
                official_confidence=official_confidence,
                form_check_summary=form_summary,
            ),
            "target_url": target,
        }

    if agent == "FormCheckAgent":
        readiness_status = str(meta.get("readiness_status", "") or "").strip().upper()
        manual_fields = _join_metadata(meta, "manual_review_required_fields")
        blocked_fields = _join_metadata(meta, "blocked_auto_fill_fields")
        skipped_fields = _join_metadata(meta, "required_but_skipped_fields")
        summary_bits = [bit for bit in [form_summary, manual_fields, blocked_fields, skipped_fields] if bit]
        if readiness_status in {"BLOCKED_BY_SAFETY"}:
            return {
                **_build_result(
                    status="blocked",
                    result_summary=form_summary or "安全上の理由でブロックしました",
                    safety_memo="form check blocked",
                    pii_detected=False,
                    submit_attempted=submit_attempted,
                    blocked_reason=blocked_reason or "BLOCKED_BY_SAFETY",
                    risk_level="blocked",
                    official_confidence=official_confidence,
                    form_check_summary=form_summary,
                ),
                "target_url": target,
            }
        if readiness_status in {"REVIEW_ONLY", "LOW_CONFIDENCE", "SEARCH_ONLY", "LANDING_PAGE", "NO_FORM", "UNKNOWN"}:
            return {
                **_build_result(
                    status="needs_review",
                    result_summary=" / ".join(summary_bits) or "フォーム診断で要確認でした",
                    safety_memo="form check requires review",
                    pii_detected=False,
                    submit_attempted=submit_attempted,
                    human_review_required=True,
                    risk_level="medium",
                    official_confidence=official_confidence,
                    form_check_summary=form_summary or "要確認",
                ),
                "target_url": target,
            }
        return {
            **_build_result(
                status="done",
                result_summary=" / ".join(summary_bits) or "フォーム診断を記録しました",
                safety_memo="form check done",
                pii_detected=False,
                submit_attempted=submit_attempted,
                risk_level="low",
                official_confidence=official_confidence,
                form_check_summary=form_summary or "診断完了",
            ),
            "target_url": target,
        }

    return {
        **_build_result(
            status="done",
            result_summary="dry-run で安全な処理を記録しました",
            safety_memo="外部操作なし",
            pii_detected=False,
            submit_attempted=submit_attempted,
            risk_level="low",
            official_confidence=official_confidence,
            form_check_summary=form_summary,
        ),
        "target_url": target,
    }
