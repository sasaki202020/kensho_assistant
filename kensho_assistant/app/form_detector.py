from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .models import DetectedField


FIELD_SYNONYMS: dict[str, list[str]] = {
    "email_confirm": [
        "メールアドレス確認",
        "確認用メールアドレス",
        "email2",
        "mail_confirm",
        "email_confirm",
    ],
    "email": [
        "メール",
        "メールアドレス",
        "e-mail",
        "email",
        "mail",
        "連絡先メール",
        "email1",
    ],
    "last_name": ["姓", "お名前 姓", "氏名 姓", "苗字", "名字", "last_name", "family_name"],
    "first_name": ["名", "お名前 名", "氏名 名", "first_name", "given_name"],
    "full_name": ["お名前", "氏名", "名前", "ご氏名", "name", "fullname"],
    "last_name_kana": ["セイ", "フリガナ 姓", "カナ 姓", "last_name_kana"],
    "first_name_kana": ["メイ", "フリガナ 名", "カナ 名", "first_name_kana"],
    "full_name_kana": ["フリガナ", "ふりがな", "カナ", "お名前 フリガナ"],
    "postal_code": ["郵便番号", "郵便", "zip", "zipcode", "post_code", "postal", "yourcode"],
    "prefecture": ["都道府県", "prefecture", "pref", "region", "yourstate"],
    "city": ["市区町村", "市町村", "city", "address_city", "locality"],
    "address1": ["住所", "番地", "町名番地", "address", "address1", "street"],
    "address2": ["建物名", "マンション名", "部屋番号", "address2", "building"],
    "phone": ["電話番号", "電話", "携帯電話", "tel", "phone", "mobile"],
    "phone_confirm": ["電話番号確認", "確認用電話番号", "phone_confirm", "tel_confirm"],
    "birth_year": ["生年", "年", "birth_year"],
    "birth_month": ["生月", "月", "birth_month"],
    "birth_day": ["生日", "日", "birth_day"],
    "gender": ["性別", "gender"],
    "age": ["年齢", "age"],
}

CONSENT_TERMS = ["規約同意", "同意", "利用規約", "応募規約", "プライバシーポリシー"]
NEWSLETTER_TERMS = ["メルマガ登録", "メルマガ", "newsletter", "メール配信"]
DM_TERMS = ["dm希望", "dm 配信", "ダイレクトメール"]
OPINION_TERMS = ["御意見", "ご意見", "御感想", "ご感想", "意見", "感想"]
FREE_TEXT_TERMS = ["アンケート自由記述", "自由記述", "メッセージ", "コメント"]
BLOCKED_TERMS: dict[str, list[str]] = {
    "occupation": ["職業"],
    "income": ["年収", "世帯年収"],
    "family": ["家族構成", "子どもの有無"],
    "interest": ["趣味", "興味関心"],
    "password": ["パスワード", "password"],
    "credit_card": ["クレジットカード", "card number", "credit"],
    "bank_account": ["口座情報", "銀行口座", "account number"],
    "my_number": ["マイナンバー"],
    "identity_document": ["本人確認書類"],
    "age": ["年齢", "age"],
}

QUIZ_TERMS = [
    "クイズ",
    "問題",
    "選択肢",
    "正解",
    "アンケート",
    "回答",
    "お答えください",
    "次のうち",
    "どれでしょうか",
]
QUIZ_CONTAINER_SELECTORS = [
    "fieldset",
    ".question",
    ".quiz",
    ".qa",
    ".enq",
    ".questionnaire",
    "legend",
    "label",
    "p",
    "li",
    "dt",
    "dd",
    "section",
    "article",
    "div",
]


def _normalize(text: str) -> str:
    return " ".join((text or "").casefold().replace("　", " ").split())


def _matches_any(text: str, keywords: Iterable[str]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(keyword) in normalized for keyword in keywords)


def _exact_match(text: str, keywords: Iterable[str]) -> bool:
    normalized = _normalize(text)
    return any(normalized == _normalize(keyword) for keyword in keywords)


def _quiz_text_indicates_manual_review(text: str) -> bool:
    normalized = _normalize(text)
    return any(_normalize(keyword) in normalized for keyword in QUIZ_TERMS)


def _quiz_choice_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in re.split(r"[\r\n]+", text or ""):
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if _quiz_text_indicates_manual_review(line):
            continue
        if len(line) > 80:
            continue
        cleaned = re.sub(r"^[・●◯○\-–—\d０-９A-Za-zＡ-Ｚａ-ｚ][.)、．. ]+", "", line).strip()
        if cleaned and cleaned not in lines:
            lines.append(cleaned)
    return lines[:6]


def _question_line(text: str) -> str:
    lines = [re.sub(r"\s+", " ", raw).strip() for raw in re.split(r"[\r\n]+", text or "") if raw.strip()]
    heading_terms = {"クイズ", "問題", "アンケート", "回答", "選択肢"}
    for line in lines:
        if line in heading_terms:
            continue
        if _quiz_text_indicates_manual_review(line) or "?" in line or "？" in line:
            return line[:160]
    for line in lines:
        if line not in heading_terms:
            return line[:160]
    return lines[0][:160] if lines else ""


def _selector_for_element(element, index: int) -> str:
    return element.evaluate(
        """(node, index) => {
            if (node.id) return `#${CSS.escape(node.id)}`;
            if (node.name) return `${node.tagName.toLowerCase()}[name="${CSS.escape(node.name)}"]`;
            return `${node.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
        }""",
        index,
    )


def _metadata_from_element(element, index: int) -> dict[str, str | bool]:
    metadata = element.evaluate(
        """node => {
            const clip = (value) => (value || '').replace(/\\s+/g, ' ').trim().slice(0, 160);
            const id = node.id || '';
            const labelFor = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
            const parentLabel = node.closest('label');
            const previousLabel = node.previousElementSibling && node.previousElementSibling.tagName === 'LABEL'
                ? node.previousElementSibling : null;
            const cell = node.closest('td');
            const previousCell = cell ? cell.previousElementSibling : null;
            const container = node.closest('li, dd, dt, td, th, p');
            return {
                tag_name: node.tagName.toLowerCase(),
                input_type: (node.type || '').toLowerCase(),
                name: node.getAttribute('name') || '',
                id,
                placeholder: node.getAttribute('placeholder') || '',
                aria_label: node.getAttribute('aria-label') || '',
                class_name: node.getAttribute('class') || '',
                label_text: clip((labelFor || parentLabel || previousLabel)?.innerText || ''),
                parent_text: clip(parentLabel?.innerText || container?.innerText || ''),
                previous_cell_text: clip(previousCell?.innerText || ''),
                previous_label_text: clip(previousLabel?.innerText || ''),
                nearby_text: [
                    clip(labelFor?.innerText || ''),
                    clip(parentLabel?.innerText || ''),
                    clip(previousLabel?.innerText || ''),
                    clip(previousCell?.innerText || ''),
                    clip(container?.innerText || '')
                ].filter(Boolean).join(' '),
                required: Boolean(node.required || node.getAttribute('aria-required') === 'true')
            };
        }"""
    )
    selector = _selector_for_element(element, index)
    metadata["selector"] = selector
    return metadata


def _special_field(metadata: Mapping[str, str | bool]) -> tuple[str, float, list[str], str] | None:
    combined = " ".join(str(metadata.get(key, "")) for key in ("label_text", "aria_label", "placeholder", "parent_text", "nearby_text"))
    input_type = str(metadata.get("input_type", ""))
    if _matches_any(combined, QUIZ_TERMS):
        return "quiz_answer", 0.95, ["label_text", "nearby_text"], "クイズ回答欄のため"
    if input_type == "checkbox" and _matches_any(combined, CONSENT_TERMS):
        return "consent", 0.98, ["label_text", "nearby_text"], "同意チェックボックスのため"
    if input_type == "checkbox" and _matches_any(combined, NEWSLETTER_TERMS):
        return "newsletter", 0.96, ["label_text", "nearby_text"], "メルマガ登録のため"
    if input_type == "checkbox" and _matches_any(combined, DM_TERMS):
        return "dm_opt_in", 0.96, ["label_text", "nearby_text"], "DM希望のため"
    if _matches_any(combined, OPINION_TERMS):
        return "opinion", 0.90, ["label_text", "nearby_text"], "御意見・御感想欄"
    if _matches_any(combined, FREE_TEXT_TERMS):
        return "free_text", 0.90, ["label_text", "nearby_text"], "自由記述のため"
    for field_name, terms in BLOCKED_TERMS.items():
        if _matches_any(combined, terms):
            return field_name, 0.95, ["label_text", "nearby_text"], f"{terms[0]}のため"
    if input_type == "password":
        return "password", 0.99, ["input_type"], "パスワード欄のため"
    return None


def _candidate_score(
    field_name: str,
    metadata: Mapping[str, str | bool],
) -> tuple[float, list[str], str]:
    terms = FIELD_SYNONYMS[field_name]
    input_type = str(metadata.get("input_type", ""))
    name = str(metadata.get("name", ""))
    element_id = str(metadata.get("id", ""))
    placeholder = str(metadata.get("placeholder", ""))
    aria_label = str(metadata.get("aria_label", ""))
    label_text = str(metadata.get("label_text", ""))
    class_name = str(metadata.get("class_name", ""))
    required = bool(metadata.get("required", False))
    nearby_text = " ".join(
        str(metadata.get(key, ""))
        for key in ("parent_text", "previous_cell_text", "previous_label_text", "nearby_text")
    )

    has_explicit_match = any(
        _matches_any(str(metadata.get(key, "")), terms)
        for key in ("name", "id", "placeholder", "aria_label", "label_text", "class_name", "nearby_text")
    )
    if field_name in {"email", "email_confirm"} and input_type == "email":
        if _matches_any(f"{name} {element_id}", terms):
            return 0.95, ["input_type", "name_or_id"], "type=email + name/id match"
        if field_name == "email_confirm" and not has_explicit_match:
            return 0.0, [], "confidence 0.00 のため"
        return 0.90, ["input_type"], "type=email"
    if field_name in {"phone", "phone_confirm"} and input_type == "tel":
        if _matches_any(f"{name} {element_id}", terms):
            return 0.95, ["input_type", "name_or_id"], "type=tel + name/id match"
        if field_name == "phone_confirm" and not has_explicit_match:
            return 0.0, [], "confidence 0.00 のため"
        return 0.90, ["input_type"], "type=tel"
    if _exact_match(label_text, terms):
        score = 0.90 if required else 0.85
        return score, ["label_text"], f"label={label_text}"
    if _matches_any(placeholder, terms):
        return 0.85, ["placeholder"], f"placeholder={placeholder}"
    if _matches_any(aria_label, terms):
        return 0.85, ["aria_label"], f"aria-label={aria_label}"
    if _matches_any(f"{name} {element_id}", terms):
        return 0.80, ["name_or_id"], "name/id match"
    if _matches_any(class_name, terms):
        return 0.75, ["class_name"], "class match"
    nearby_terms = [term for term in terms if len(_normalize(term)) >= 2]
    if _matches_any(nearby_text, nearby_terms):
        return 0.65, ["nearby_text"], "nearby text match"
    return 0.0, [], "confidence 0.00 のため"


def detect_field_from_metadata(metadata: Mapping[str, str | bool]) -> DetectedField:
    special = _special_field(metadata)
    if special:
        field_name, confidence, detected_from, reason = special
    else:
        best_name = "unknown"
        best_confidence = 0.0
        best_sources: list[str] = []
        best_reason = "confidence 0.00 のため"
        for candidate in FIELD_SYNONYMS:
            confidence, sources, reason = _candidate_score(candidate, metadata)
            if confidence > best_confidence:
                best_name = candidate
                best_confidence = confidence
                best_sources = sources
                best_reason = reason
        field_name = best_name
        confidence = best_confidence
        detected_from = best_sources
        reason = best_reason

    label = (
        str(metadata.get("label_text", ""))
        or str(metadata.get("placeholder", ""))
        or str(metadata.get("aria_label", ""))
        or str(metadata.get("name", ""))
        or str(metadata.get("id", ""))
    )
    return DetectedField(
        field_name=field_name,
        selector=str(metadata.get("selector", "")),
        label=label,
        kind=str(metadata.get("tag_name", "")) or str(metadata.get("input_type", "")),
        input_type=str(metadata.get("input_type", "")),
        aria_label=str(metadata.get("aria_label", "")),
        placeholder=str(metadata.get("placeholder", "")),
        name=str(metadata.get("name", "")),
        element_id=str(metadata.get("id", "")),
        nearby_text=str(metadata.get("nearby_text", "")),
        detected_from=detected_from,
        confidence=confidence,
        reason=reason,
        required=bool(metadata.get("required", False)),
        will_fill=False,
    )


def extract_quiz_items_from_text(text: str, source_hint_url: str = "") -> list[dict[str, object]]:
    normalized_lines = [re.sub(r"\s+", " ", raw).strip() for raw in re.split(r"[\r\n]+", text or "") if raw.strip()]
    if not any(_quiz_text_indicates_manual_review(line) for line in normalized_lines):
        return []
    question_text = _question_line(text)
    if not question_text:
        return []
    choices = _quiz_choice_lines(text)
    return [
        {
            "question_text": question_text,
            "choices": choices,
            "source_hint_url": source_hint_url,
            "answer_field_selector": "",
            "auto_fill_allowed": False,
            "manual_required": True,
        }
    ]


def extract_quiz_items(page, limit: int = 5) -> list[dict[str, object]]:
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body_text = ""
    if not _quiz_text_indicates_manual_review(body_text):
        return []
    items: list[dict[str, object]] = []
    seen_questions: set[str] = set()
    try:
        containers = page.locator(", ".join(QUIZ_CONTAINER_SELECTORS))
        total = min(containers.count(), 40)
    except Exception:
        containers = None
        total = 0
    if containers is not None:
        for index in range(total):
            try:
                element = containers.nth(index)
                text = element.inner_text(timeout=2000)
            except Exception:
                continue
            extracted = extract_quiz_items_from_text(text, source_hint_url=getattr(page, "url", ""))
            if not extracted:
                continue
            item = extracted[0]
            question = str(item.get("question_text", ""))
            if not question or question in seen_questions:
                continue
            try:
                answer_locator = element.locator("input, select, textarea").first
                item["answer_field_selector"] = _selector_for_element(answer_locator, 0)
            except Exception:
                item["answer_field_selector"] = ""
            items.append(item)
            seen_questions.add(question)
            if len(items) >= limit:
                return items
    if not items:
        items = extract_quiz_items_from_text(body_text, source_hint_url=getattr(page, "url", ""))[:limit]
    return items


def detect_fields(page) -> list[DetectedField]:
    fields: list[DetectedField] = []
    unknown_count = 0
    elements = page.locator('input:not([type="hidden"]), select, textarea')
    for index in range(elements.count()):
        element = elements.nth(index)
        try:
            field = detect_field_from_metadata(_metadata_from_element(element, index))
            if field.field_name == "unknown":
                unknown_count += 1
                field.field_name = f"unknown_{unknown_count}"
            fields.append(field)
        except Exception:
            continue
    return fields
