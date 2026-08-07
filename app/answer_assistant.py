from __future__ import annotations

import re
from collections.abc import Mapping

from .form_detector import extract_quiz_items
from .site_templates import SiteTemplate


DEFAULT_COMMENT_TEXT = (
    "応募内容が分かりやすく、ページも見やすいと感じました。"
    "今後も旬の情報や企画の案内を楽しみにしています。"
)

STOPWORDS = {
    "クイズ",
    "問題",
    "回答",
    "答え",
    "次のうち",
    "どれ",
    "ですか",
    "でしょうか",
    "ください",
    "お答え",
    "選んで",
    "ヒント",
}

GENERIC_QUIZ_CHOICES = {
    "選択してください",
    "選んでください",
    "選んでください。",
    "未選択",
    "なし",
    "なしを選択",
    "--",
    "—",
    "ー",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").casefold().replace("　", " ").split())


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z0-9一-龠ぁ-んァ-ヶー]+", text or ""))
    return {token for token in tokens if token and token not in STOPWORDS}


def build_comment_text(
    campaign: Mapping[str, str],
    profile: Mapping[str, str],
    site_template: SiteTemplate | None = None,
    body_text: str = "",
) -> str:
    campaign_name = str(campaign.get("campaign_name", "")).strip()
    prize = str(campaign.get("prize", "")).strip()
    provider = str(campaign.get("provider", "")).strip()
    template_id = site_template.template_id if site_template else ""
    template_label = site_template.label if site_template else ""

    if template_id == "fs_fukuoka_present" or "福岡" in template_label or "農林水産" in body_text:
        return (
            "福岡県産の農林水産物は品質の高さと旬の魅力が伝わり、"
            "ホームページも情報が整理されていて分かりやすいと感じました。"
            "今後も季節ごとの食材や生産者の取り組みを楽しみにしています。"
        )
    if template_id == "tenkaippin_smashing" or "天下一品" in campaign_name:
        return (
            "キャンペーンの内容が分かりやすく、応募への導線も見やすいと感じました。"
            "今後もこうした企画や特典の案内を楽しみにしています。"
        )

    parts = [part for part in [campaign_name, prize, provider] if part]
    if parts:
        return (
            f"{parts[0]}の企画は分かりやすく、"
            "応募ページも見やすくて参考になりました。"
            "今後も新しい案内を楽しみにしています。"
        )
    return DEFAULT_COMMENT_TEXT


def suggest_quiz_answer(
    question_text: str,
    choices: list[str],
    body_text: str,
    campaign: Mapping[str, str],
    site_template: SiteTemplate | None = None,
) -> dict[str, object]:
    normalized_question = _normalize(question_text)
    normalized_body = _normalize(body_text)
    question_tokens = _tokenize(question_text)
    body_tokens = _tokenize(body_text)
    template_tokens = _tokenize(site_template.label if site_template else "") | _tokenize(" ".join(site_template.notes if site_template else []))
    if site_template is not None:
        template_tokens |= _tokenize(site_template.site_name)
        template_tokens |= _tokenize(" ".join(site_template.known_form_labels))
        template_tokens |= _tokenize(" ".join(site_template.known_required_fields))
        template_tokens |= _tokenize(" ".join(site_template.known_radio_groups))
        template_tokens |= _tokenize(" ".join(site_template.confirmation_button_texts))
        template_tokens |= _tokenize(" ".join(site_template.submit_button_texts))
        template_tokens |= _tokenize(" ".join(site_template.skip_rules))
        template_tokens |= _tokenize(" ".join(site_template.safety_notes))
        template_tokens |= _tokenize(" ".join(option for options in site_template.known_select_options.values() for option in options))

    best_answer = ""
    best_score = 0.0
    second_score = 0.0
    best_reason = ""

    for choice in choices:
        normalized_choice = _normalize(choice)
        if not normalized_choice:
            continue
        if normalized_choice in GENERIC_QUIZ_CHOICES or normalized_choice.startswith("選択") and len(normalized_choice) <= 8:
            continue
        score = 0.0
        if normalized_choice in normalized_body:
            score += 5.0
        if normalized_choice in normalized_question:
            score += 3.0
        choice_tokens = _tokenize(choice)
        overlap_question = len(choice_tokens & question_tokens)
        overlap_body = len(choice_tokens & body_tokens)
        overlap_template = len(choice_tokens & template_tokens)
        score += overlap_question * 1.5
        score += overlap_body * 1.2
        score += overlap_template * 1.0
        if "ヒント" in normalized_body and normalized_choice in normalized_body:
            score += 2.0
        if str(campaign.get("campaign_name", "")).strip() and normalized_choice in _normalize(str(campaign.get("campaign_name", ""))):
            score += 0.5
        if score > best_score:
            second_score = best_score
            best_score = score
            best_answer = choice
            best_reason = f"score={score:.2f}, overlap_q={overlap_question}, overlap_body={overlap_body}"
        elif score > second_score:
            second_score = score

    confidence = 0.0
    if best_answer and best_score >= 3.5 and best_score - second_score >= 1.0:
        confidence = min(0.99, 0.55 + best_score / 10.0)
    else:
        best_answer = ""

    return {
        "suggested_answer": best_answer,
        "confidence": round(confidence, 2),
        "reason": best_reason or "candidate not confident enough",
        "choices": choices,
        "question_text": question_text,
    }


def build_answer_pack(
    page,
    campaign: Mapping[str, str],
    profile: Mapping[str, str],
    site_template: SiteTemplate | None = None,
) -> dict[str, object]:
    try:
        body_text = page.locator("body").inner_text(timeout=5000) if page.locator("body").count() else ""
    except Exception:
        body_text = ""
    quiz_items = extract_quiz_items(page, limit=5)
    comment_text = build_comment_text(campaign, profile, site_template=site_template, body_text=body_text)
    quiz_suggestions: list[dict[str, object]] = []
    top_quiz_answer = ""
    top_quiz_confidence = 0.0

    for item in quiz_items:
        suggestion = suggest_quiz_answer(
            str(item.get("question_text", "")),
            [str(choice) for choice in item.get("choices", []) if str(choice).strip()],
            body_text,
            campaign,
            site_template=site_template,
        )
        merged = dict(item)
        merged.update(suggestion)
        quiz_suggestions.append(merged)
        if suggestion.get("suggested_answer") and float(suggestion.get("confidence", 0.0)) >= top_quiz_confidence:
            top_quiz_answer = str(suggestion.get("suggested_answer", "")).strip()
            top_quiz_confidence = float(suggestion.get("confidence", 0.0))

    answer_overrides = {
        "opinion": comment_text,
        "free_text": comment_text,
    }
    confident_answers = [item for item in quiz_suggestions if str(item.get("suggested_answer", "")).strip() and float(item.get("confidence", 0.0) or 0.0) >= 0.7]
    if top_quiz_answer and len(confident_answers) == 1 and top_quiz_confidence >= 0.7:
        answer_overrides["quiz_answer"] = top_quiz_answer
    return {
        "body_text": body_text,
        "quiz_items": quiz_items,
        "quiz_suggestions": quiz_suggestions,
        "quiz_answer": answer_overrides.get("quiz_answer", ""),
        "quiz_answer_confidence": top_quiz_confidence,
        "comment_text": comment_text,
        "answer_overrides": answer_overrides,
    }
