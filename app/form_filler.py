from __future__ import annotations

import re
from datetime import date
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
    "income",
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
    "last_name",
    "first_name",
    "full_name",
    "last_name_kana",
    "first_name_kana",
    "full_name_kana",
    "postal_code",
    "prefecture",
    "city",
    "address1",
    "address2",
    "phone",
    "phone_confirm",
    "email",
    "email_confirm",
    "gender",
    "opinion",
    "free_text",
    "age_group",
    "occupation",
    "marital_status",
    "children",
    "survey_choice",
    "prize_choice",
    "entry_count",
}
AI_ASSISTED_FIELD_NAMES = {
    "opinion",
    "free_text",
    "quiz_answer",
}
NO_FILL_KEYWORDS = [
    "年収",
    "世帯年収",
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
def _first_profile_value(profile: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = str(profile.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _profile_age(profile: Mapping[str, str]) -> str:
    explicit = _first_profile_value(profile, "age")
    if explicit:
        return explicit
    try:
        born = date(
            int(_first_profile_value(profile, "birth_year", "year_of_birth")),
            int(_first_profile_value(profile, "birth_month", "month_of_birth")),
            int(_first_profile_value(profile, "birth_day", "day_of_birth")),
        )
    except (TypeError, ValueError):
        return ""
    today = date.today()
    return str(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))


def _profile_value(profile: Mapping[str, str], field_name: str) -> str:
    last_name = _first_profile_value(profile, "last_name", "family_name", "surname")
    first_name = _first_profile_value(profile, "first_name", "given_name")
    last_name_kana = _first_profile_value(profile, "last_name_kana", "family_name_kana", "surname_kana")
    first_name_kana = _first_profile_value(profile, "first_name_kana", "given_name_kana")
    mapping = {
        "last_name": last_name,
        "first_name": first_name,
        "full_name": _first_profile_value(profile, "full_name", "name") or " ".join(filter(None, [last_name, first_name])),
        "last_name_kana": last_name_kana,
        "first_name_kana": first_name_kana,
        "full_name_kana": _first_profile_value(profile, "full_name_kana", "name_kana") or " ".join(filter(None, [last_name_kana, first_name_kana])),
        "postal_code": _first_profile_value(profile, "postal_code", "zipcode", "zip", "postal"),
        "prefecture": _first_profile_value(profile, "prefecture", "state", "region"),
        "city": _first_profile_value(profile, "city", "locality", "municipality"),
        "address1": _first_profile_value(profile, "address1", "address", "street_address"),
        "address2": _first_profile_value(profile, "address2", "building", "apartment"),
        "phone": _first_profile_value(profile, "phone", "tel", "telephone", "mobile"),
        "phone_confirm": _first_profile_value(profile, "phone", "tel", "telephone", "mobile"),
        "email": _first_profile_value(profile, "email", "mail", "email_address"),
        "email_confirm": _first_profile_value(profile, "email", "mail", "email_address"),
        "gender": profile.get("gender", ""),
        "age": _profile_age(profile),
        "birth_year": profile.get("birth_year", ""),
        "birth_month": profile.get("birth_month", ""),
        "birth_day": profile.get("birth_day", ""),
        "age_group": profile.get("age_group", ""),
        "occupation": profile.get("occupation", ""),
        "marital_status": profile.get("marital_status", ""),
        "children": profile.get("children", ""),
        "survey_choice": profile.get("survey_choice", ""),
        "prize_choice": profile.get("prize_choice", ""),
        "entry_count": profile.get("entry_count", "") or "1",
        "opinion": profile.get("opinion", ""),
    }
    return mapping.get(field_name, "")


def _override_value(answer_overrides: Mapping[str, str] | None, field_name: str) -> str:
    if not answer_overrides:
        return ""
    return str(answer_overrides.get(field_name, "")).strip()


def _field_value(
    profile: Mapping[str, str],
    field_name: str,
    answer_overrides: Mapping[str, str] | None = None,
    allow_ai_answer_fill: bool = False,
) -> str:
    override = _override_value(answer_overrides, field_name)
    if allow_ai_answer_fill and field_name in AI_ASSISTED_FIELD_NAMES and override:
        return override
    return _profile_value(profile, field_name)


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
    if field_name in {"age_group", "occupation", "marital_status", "children", "survey_choice", "prize_choice", "entry_count"}:
        return "***"
    return value


def _normalize_choice_text(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("　", " ").split())


def _component_value(field: DetectedField, fields: list[DetectedField], value: str) -> str:
    grouped = [item for item in fields if item.field_name == field.field_name]
    if len(grouped) <= 1:
        return value
    if field.field_name not in {"postal_code", "phone", "phone_confirm"}:
        return value
    identity_text = " ".join(
        f"{item.name} {item.element_id} {item.selector} {item.label}".casefold()
        for item in grouped
    )
    if field.field_name == "postal_code" and not re.search(r"zip\d|postal.*(?:sep|\d)", identity_text):
        return value
    if field.field_name in {"phone", "phone_confirm"} and not re.search(r"(?:tel|phone)\d|(?:tel|phone).*sep", identity_text):
        return value
    try:
        index = next(index for index, item in enumerate(grouped) if item is field)
    except StopIteration:
        index = grouped.index(field)
    explicit_parts = [part for part in re.split(r"\D+", value.strip()) if part]
    if len(explicit_parts) == len(grouped):
        return explicit_parts[index]
    digits = re.sub(r"\D", "", value)
    if field.field_name == "postal_code" and len(grouped) == 2 and len(digits) == 7:
        return (digits[:3], digits[3:])[index]
    if field.field_name in {"phone", "phone_confirm"} and len(grouped) == 3 and len(digits) == 11:
        return (digits[:3], digits[3:7], digits[7:])[index]
    return ""


def _choice_matches(candidate: str, option_text: str) -> bool:
    candidate_norm = _normalize_choice_text(candidate)
    option_norm = _normalize_choice_text(option_text)
    if not candidate_norm or not option_norm:
        return False
    return candidate_norm == option_norm or candidate_norm in option_norm or option_norm in candidate_norm


def _choice_aliases(field_name: str, value: str) -> list[str]:
    normalized = _normalize_choice_text(value)
    aliases = [value]
    if field_name == "gender":
        if any(token in normalized for token in ("male", "man", "男性", "男")):
            aliases.extend(["男性", "男", "male", "man"])
        elif any(token in normalized for token in ("female", "woman", "女性", "女")):
            aliases.extend(["女性", "女", "female", "woman"])
    elif field_name == "children":
        if any(token in normalized for token in ("なし", "無", "none", "no", "いない")):
            aliases.extend(["なし", "無", "いない", "none", "no"])
        elif any(token in normalized for token in ("あり", "有", "yes", "いる")):
            aliases.extend(["あり", "有", "いる", "yes"])
    elif field_name == "marital_status":
        if any(token in normalized for token in ("未婚", "独身", "single")):
            aliases.extend(["未婚", "独身", "single"])
        elif any(token in normalized for token in ("既婚", "結婚", "married")):
            aliases.extend(["既婚", "結婚", "married"])
    seen: set[str] = set()
    result: list[str] = []
    for alias in aliases:
        alias_text = str(alias).strip()
        if not alias_text or alias_text in seen:
            continue
        seen.add(alias_text)
        result.append(alias_text)
    return result


def _radio_option_index(locator, target_value: str, field_label: str = "", field_name: str = "") -> int | None:
    target_texts = [target_value]
    target_texts.extend(_choice_aliases(field_name, target_value))
    normalized_targets = [
        " ".join(str(text or "").casefold().replace("　", " ").split())
        for text in target_texts
        if str(text or "").strip()
    ]
    if not normalized_targets:
        return None
    try:
        candidates = locator.evaluate_all(
            """nodes => nodes.map((node, index) => {
                const clip = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const labelTexts = [];
                if (node.labels && node.labels.length) {
                    for (const label of Array.from(node.labels)) {
                        labelTexts.push(label.innerText || label.textContent || '');
                    }
                }
                const parentLabel = node.closest('label');
                const nearbyTexts = [
                    node.getAttribute('aria-label') || '',
                    node.getAttribute('title') || '',
                    node.value || '',
                    node.id || '',
                    node.name || '',
                    parentLabel ? parentLabel.innerText || '' : '',
                    labelTexts.join(' '),
                    node.parentElement ? node.parentElement.innerText || '' : ''
                ];
                return {index, text: clip(nearbyTexts.join(' '))};
            })"""
        )
    except Exception:
        return None
    for candidate_text in normalized_targets:
        for candidate in candidates:
            candidate_text_value = str(candidate.get("text", ""))
            if candidate_text and (candidate_text in candidate_text_value or candidate_text_value in candidate_text):
                try:
                    return int(candidate.get("index", -1))
                except Exception:
                    return None
    return None


def _select_option_value(locator, field: DetectedField, value: str) -> bool:
    try:
        locator.scroll_into_view_if_needed(timeout=1000)
    except Exception:
        pass
    try:
        options = locator.evaluate_all(
            """nodes => nodes.flatMap((node) => Array.from(node.options || []).map((option, index) => ({
                index,
                value: option.value || '',
                label: option.label || option.text || option.innerText || '',
                text: option.textContent || '',
                disabled: Boolean(option.disabled)
            })))"""
        )
    except Exception:
        options = []
    candidates = _choice_aliases(field.field_name, value)
    if field.label:
        candidates.append(field.label)
    seen: set[str] = set()
    ordered_candidates: list[str] = []
    for candidate in candidates:
        candidate_text = str(candidate).strip()
        if not candidate_text or candidate_text in seen:
            continue
        seen.add(candidate_text)
        ordered_candidates.append(candidate_text)
    for candidate in ordered_candidates:
        for option in options:
            if bool(option.get("disabled", False)):
                continue
            option_value = str(option.get("value", "")).strip()
            option_label = str(option.get("label", "")).strip()
            option_text = str(option.get("text", "")).strip()
            if not (option_value or option_label or option_text):
                continue
            if any(_choice_matches(candidate, text) for text in (option_label, option_text, option_value)):
                try:
                    if option_value:
                        locator.select_option(value=option_value)
                    elif option_label:
                        locator.select_option(label=option_label)
                    else:
                        locator.select_option(index=int(option.get("index", -1)))
                    return True
                except Exception:
                    try:
                        locator.select_option(index=int(option.get("index", -1)))
                        return True
                    except Exception:
                        continue
    try:
        locator.select_option(label=value)
        return True
    except Exception:
        pass
    try:
        locator.select_option(value=value)
        return True
    except Exception:
        return False


def plan_field_filling(fields: list[DetectedField], profile: Mapping[str, str]) -> list[DetectedField]:
    return plan_field_filling_with_age(fields, profile, allow_age_fill=False)


def plan_field_filling_with_age(
    fields: list[DetectedField],
    profile: Mapping[str, str],
    allow_age_fill: bool = False,
    answer_overrides: Mapping[str, str] | None = None,
    allow_ai_answer_fill: bool = False,
) -> list[DetectedField]:
    planned: list[DetectedField] = []
    for field in fields:
        value = _field_value(profile, field.field_name, answer_overrides=answer_overrides, allow_ai_answer_fill=allow_ai_answer_fill)
        value = _component_value(field, fields, value)
        lowered_label = (field.label or "").casefold()
        age_related = field.field_name in {"age", "birth_year", "birth_month", "birth_day"}
        ai_override_active = allow_ai_answer_fill and field.field_name in AI_ASSISTED_FIELD_NAMES and bool(_override_value(answer_overrides, field.field_name))
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
        elif ai_override_active:
            if field.confidence < MIN_FILL_CONFIDENCE:
                field.skip_reason = f"confidence {field.confidence:.2f} のため"
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
    lines.append("注意: 送信ボタンは押しません。確認画面または送信直前で止めます。")
    return "\n".join(lines)


def _fill_text_like(page, field: DetectedField, value: str) -> None:
    locator = page.locator(field.selector)
    if locator.count() == 0:
        return
    try:
        locator.scroll_into_view_if_needed(timeout=1000)
    except Exception:
        pass
    tag = field.kind.casefold()
    if tag == "textarea":
        locator.fill(value)
        return
    if tag == "select-one" or tag == "select":
        if _select_option_value(locator, field, value):
            return
    if tag == "radio" or tag == "checkbox":
        return
    locator.fill(value)


def apply_field_plan_with_overrides(
    page,
    fields: list[DetectedField],
    profile: Mapping[str, str],
    answer_overrides: Mapping[str, str] | None = None,
    allow_ai_answer_fill: bool = False,
) -> tuple[list[str], list[str]]:
    filled: list[str] = []
    missing: list[str] = []
    for field in fields:
        if not field.will_fill:
            continue
        value = _field_value(profile, field.field_name, answer_overrides=answer_overrides, allow_ai_answer_fill=allow_ai_answer_fill)
        value = _component_value(field, fields, value)
        if not value:
            missing.append(field.field_name)
            continue
        try:
            field_type = (field.input_type or field.kind).casefold()
            if field_type == "radio":
                locator = page.locator(field.selector)
                if locator.count():
                    selected_index = _radio_option_index(locator, value, field.label, field.field_name)
                    if selected_index is None:
                        missing.append(field.field_name)
                    else:
                        locator.nth(selected_index).check()
                        filled.append(field.field_name)
                else:
                    missing.append(field.field_name)
                continue
            _fill_text_like(page, field, value)
            filled.append(field.field_name)
        except Exception:
            missing.append(field.field_name)
    return filled, missing


def apply_field_plan(
    page,
    fields: list[DetectedField],
    profile: Mapping[str, str],
    answer_overrides: Mapping[str, str] | None = None,
    allow_ai_answer_fill: bool = False,
) -> tuple[list[str], list[str]]:
    return apply_field_plan_with_overrides(
        page,
        fields,
        profile,
        answer_overrides=answer_overrides,
        allow_ai_answer_fill=allow_ai_answer_fill,
    )


def fill_campaign_page(
    page,
    campaign: Mapping[str, str],
    profile: Mapping[str, str],
    screenshot_dir: Path | None = None,
    save_screenshot: bool = False,
    allow_age_fill: bool = False,
    auto_confirm_known_fields: bool = False,
    answer_overrides: Mapping[str, str] | None = None,
    allow_ai_answer_fill: bool = False,
) -> FillResult:
    screenshot_dir = screenshot_dir or BEFORE_SUBMIT_DIR
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    fields = plan_field_filling_with_age(
        detect_fields(page),
        profile,
        allow_age_fill=allow_age_fill,
        answer_overrides=answer_overrides,
        allow_ai_answer_fill=allow_ai_answer_fill,
    )
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
    filled_fields, missing_fields = apply_field_plan_with_overrides(
        page,
        fields,
        profile,
        answer_overrides=answer_overrides,
        allow_ai_answer_fill=allow_ai_answer_fill,
    )
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
