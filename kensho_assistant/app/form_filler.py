from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .form_detector import detect_fields
from .models import DetectedField, FillResult
from .paths import BEFORE_SUBMIT_DIR
from .privacy_guard import mask_email, mask_name, mask_phone, redact_personal_info


MIN_FILL_CONFIDENCE = 0.75
NO_FILL_FIELD_NAMES = {
    "consent",
    "newsletter",
    "dm_opt_in",
    "free_text",
    "occupation",
    "income",
    "family",
    "interest",
    "password",
    "credit_card",
    "bank_account",
    "my_number",
    "identity_document",
    "age",
    "quiz_answer",
    "unknown",
}
OPTIONAL_FILL_FIELD_NAMES = {
    "phone",
    "phone_confirm",
}
NO_FILL_KEYWORDS = [
    "年収",
    "世帯年収",
    "職業",
    "家族構成",
    "子どもの有無",
    "趣味",
    "興味関心",
    "自由記述",
    "メルマガ",
    "規約",
    "プライバシーポリシー",
    "dm",
    "パスワード",
    "クレジットカード",
    "口座情報",
    "マイナンバー",
    "本人確認書類",
    "年齢",
    "クイズ",
    "問題",
    "回答",
]
DEFAULT_SKIP_REASONS = {
    "consent": "同意チェックボックスのため",
    "newsletter": "メルマガ登録のため",
    "dm_opt_in": "DM希望のため",
    "free_text": "自由記述のため",
    "occupation": "職業のため",
    "income": "年収のため",
    "family": "家族構成のため",
    "interest": "興味関心のため",
    "password": "パスワード欄のため",
    "credit_card": "クレジットカード欄のため",
    "bank_account": "口座情報のため",
    "my_number": "マイナンバーのため",
    "identity_document": "本人確認書類のため",
    "age": "年齢情報のため自動入力しない",
    "quiz_answer": "クイズ回答のため自動入力しない",
    "unknown": "confidence 0.00 のため",
}
DEFAULT_OPINION_TEXT = (
    "本県の農林水産物は品質が高く、生産者の皆様の丁寧な取り組みが感じられて大変魅力的だと思いました。"
    "ホームページも情報が整理されていて分かりやすく、旬の県産品や生産現場への関心が一層高まりました。"
    "今後も季節ごとの食材やおすすめの楽しみ方を発信していただけると嬉しいです。"
)


def _profile_value(profile: Mapping[str, str], field_name: str) -> str:
    mapping = {
        "last_name": profile.get("last_name", ""),
        "first_name": profile.get("first_name", ""),
        "full_name": " ".join(filter(None, [profile.get("last_name", ""), profile.get("first_name", "")])),
        "last_name_kana": profile.get("last_name_kana", ""),
        "first_name_kana": profile.get("first_name_kana", ""),
        "full_name_kana": " ".join(filter(None, [profile.get("last_name_kana", ""), profile.get("first_name_kana", "")])),
        "postal_code": profile.get("postal_code", ""),
        "prefecture": profile.get("prefecture", ""),
        "city": profile.get("city", ""),
        "address1": profile.get("address1", ""),
        "address2": profile.get("address2", ""),
        "phone": profile.get("phone", ""),
        "phone_confirm": profile.get("phone", ""),
        "email": profile.get("email", ""),
        "email_confirm": profile.get("email", ""),
        "gender": profile.get("gender", ""),
        "age": profile.get("age", ""),
        "birth_year": profile.get("birth_year", ""),
        "birth_month": profile.get("birth_month", ""),
        "birth_day": profile.get("birth_day", ""),
        "opinion": profile.get("opinion", "") or DEFAULT_OPINION_TEXT,
    }
    return mapping.get(field_name, "")


def _mask_preview(field_name: str, value: str) -> str:
    if not value:
        return ""
    if field_name in {"phone", "phone_confirm"}:
        return mask_phone(value)
    if field_name in {"email", "email_confirm"}:
        return mask_email(value)
    if field_name == "full_name":
        return f"{value.split()[0]} **"
    if field_name in {"last_name", "first_name"}:
        return mask_name(value, "")
    if field_name == "full_name_kana":
        return f"{value.split()[0][:1]}**"
    if field_name in {"last_name_kana", "first_name_kana"}:
        return f"{value[:1]}**"
    if field_name == "postal_code":
        return f"{value[:3]}-****"
    if field_name in {"prefecture", "city", "address1", "address2"}:
        return "***"
    if field_name in {"birth_year", "birth_month", "birth_day"}:
        return "***"
    return value


def plan_field_filling(fields: list[DetectedField], profile: Mapping[str, str]) -> list[DetectedField]:
    return plan_field_filling_with_age(fields, profile, allow_age_fill=False)


def plan_field_filling_with_age(
    fields: list[DetectedField],
    profile: Mapping[str, str],
    allow_age_fill: bool = False,
) -> list[DetectedField]:
    planned: list[DetectedField] = []
    for field in fields:
        value = _profile_value(profile, field.field_name)
        lowered_label = (field.label or "").casefold()
        age_related = field.field_name in {"age", "birth_year", "birth_month", "birth_day"}
        if field.field_name.startswith("unknown_"):
            field.skip_reason = f"confidence {field.confidence:.2f} のため"
        elif age_related:
            if not allow_age_fill:
                field.skip_reason = DEFAULT_SKIP_REASONS.get(field.field_name, "年齢情報のため自動入力しない")
            elif field.confidence < MIN_FILL_CONFIDENCE:
                field.skip_reason = f"confidence {field.confidence:.2f} のため"
            elif not value.strip():
                field.skip_reason = "profile に対応値がないため"
            else:
                field.skip_reason = ""
        elif field.field_name in NO_FILL_FIELD_NAMES:
            field.skip_reason = field.reason or DEFAULT_SKIP_REASONS.get(field.field_name, "安全対象外の項目のため")
        elif any(keyword.casefold() in lowered_label for keyword in NO_FILL_KEYWORDS):
            field.skip_reason = field.reason or "安全対象外の項目のため"
        elif field.confidence < MIN_FILL_CONFIDENCE:
            field.skip_reason = f"confidence {field.confidence:.2f} のため"
        elif not field.required and field.field_name not in OPTIONAL_FILL_FIELD_NAMES:
            field.skip_reason = "任意項目のため"
        elif not value.strip():
            field.skip_reason = "profile に対応値がないため"
        else:
            field.skip_reason = ""
        blocked = bool(field.skip_reason)
        field.will_fill = not blocked
        field.value_preview = _mask_preview(field.field_name, value) if field.will_fill else ""
        planned.append(field)
    return planned


def build_input_review(
    campaign: Mapping[str, str],
    fields: list[DetectedField],
    profile: Mapping[str, str],
    risk_level: str,
    risk_reason: str,
) -> str:
    risk_label = risk_level or "SAFE_TO_FILL"
    risk_detail = (risk_reason or "").strip()
    duplicate_entry = "DUPLICATE_ENTRY" in risk_label or "DUPLICATE_ENTRY" in risk_detail
    if duplicate_entry:
        risk_label = "重複の可能性あり"
        if not risk_detail:
            risk_detail = "DUPLICATE_ENTRY"
    planned_lines: list[str] = []
    skipped_lines: list[str] = []
    field_counts: dict[str, int] = {}
    field_seen: dict[str, int] = {}
    for field in fields:
        field_counts[field.field_name] = field_counts.get(field.field_name, 0) + 1

    def display_name(field: DetectedField) -> str:
        field_seen[field.field_name] = field_seen.get(field.field_name, 0) + 1
        if field_counts[field.field_name] > 1:
            suffix = "required" if field.required else "optional"
            return f"{field.field_name}[{field_seen[field.field_name]}:{suffix}]"
        return f"{field.field_name}[{'required' if field.required else 'optional'}]"

    for field in fields:
        name = display_name(field)
        if field.will_fill:
            planned_lines.append(
                f"- {name}: {field.value_preview} / confidence {field.confidence:.2f} / reason: {field.reason}"
            )
        else:
            skipped_lines.append(f"- {name} / reason: {field.skip_reason or field.reason}")
    lines = [
        f"campaign_id: {campaign.get('campaign_id', '')}",
        f"campaign_name: {campaign.get('campaign_name', '')}",
        f"entry_url: {campaign.get('resolved_entry_url', '') or campaign.get('entry_url', '')}",
        f"risk_level: {risk_label}",
        f"risk_reason: {risk_detail or risk_reason}",
        "検出した入力欄一覧:",
    ]
    if duplicate_entry:
        lines.insert(5, "注意: 似た候補が見つかっています。必要なら詳細を確認してください。")
    field_seen.clear()
    for field in fields:
        lines.append(
            f"- {display_name(field)} | selector={field.selector} | from={','.join(field.detected_from) or 'unknown'} | "
            f"confidence={field.confidence:.2f} | required={field.required} | will_fill={field.will_fill} | reason={field.reason}"
        )
    lines.append("入力予定:")
    lines.extend(planned_lines or ["- なし"])
    lines.append("入力しない:")
    lines.extend(skipped_lines or ["- なし"])
    lines.append("注意: 同意チェックボックスは自動でチェックしません。")
    return "\n".join(lines)


def _fill_text_like(page, field: DetectedField, value: str) -> None:
    locator = page.locator(field.selector)
    if locator.count() == 0:
        return
    tag = field.kind.casefold()
    if tag == "textarea":
        locator.fill(value)
        return
    if tag == "select-one" or tag == "select":
        try:
            locator.select_option(label=value)
            return
        except Exception:
            try:
                locator.select_option(value=value)
                return
            except Exception:
                pass
    if tag == "radio" or tag == "checkbox":
        return
    locator.fill(value)


def apply_field_plan(page, fields: list[DetectedField], profile: Mapping[str, str]) -> tuple[list[str], list[str]]:
    filled: list[str] = []
    missing: list[str] = []
    for field in fields:
        if not field.will_fill:
            continue
        value = _profile_value(profile, field.field_name)
        if not value:
            missing.append(field.field_name)
            continue
        try:
            if field.kind.casefold() == "radio":
                locator = page.locator(field.selector)
                if locator.count():
                    locator.check()
                    filled.append(field.field_name)
                else:
                    missing.append(field.field_name)
                continue
            _fill_text_like(page, field, value)
            filled.append(field.field_name)
        except Exception:
            missing.append(field.field_name)
    return filled, missing


def fill_campaign_page(
    page,
    campaign: Mapping[str, str],
    profile: Mapping[str, str],
    screenshot_dir: Path | None = None,
    save_screenshot: bool = False,
    allow_age_fill: bool = False,
    auto_confirm_known_fields: bool = False,
) -> FillResult:
    screenshot_dir = screenshot_dir or BEFORE_SUBMIT_DIR
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    fields = plan_field_filling_with_age(detect_fields(page), profile, allow_age_fill=allow_age_fill)
    review = build_input_review(campaign, fields, profile, campaign.get("status", ""), campaign.get("notes", ""))
    print(review)
    choice = "y" if auto_confirm_known_fields else input("y/n/hold/open/quit > ").strip().lower()
    result = FillResult(campaign_id=str(campaign.get("campaign_id", "")), decision=choice)
    if choice == "quit":
        raise SystemExit(0)
    if choice in {"hold", "open", "n"}:
        return result
    if choice != "y":
        return result
    filled_fields, missing_fields = apply_field_plan(page, fields, profile)
    consent_fields = [field.field_name for field in fields if field.field_name in {"consent", "newsletter"}]
    result.filled_fields = filled_fields
    result.missing_fields = missing_fields
    result.consent_fields = consent_fields
    if save_screenshot:
        screenshot_path = screenshot_dir / f"{campaign.get('campaign_id', 'campaign')}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        result.screenshot_before = str(screenshot_path)
    result.notes = redact_personal_info(f"profile_masked={mask_name(profile.get('last_name', ''), profile.get('first_name', ''))}")
    result.decision = "fill"
    return result
