from __future__ import annotations

from datetime import date, datetime
from typing import Iterable


HIGH_RISK_FLAGS = {
    "現金配布",
    "投資",
    "FX",
    "仮想通貨",
    "LINE誘導",
    "DMで個人情報要求",
    "成人向け",
}

RISK_PATTERNS = {
    "現金配布": ("現金", "cash", "お金がもらえる", "金券"),
    "投資": ("投資", "investment", "invest", "株式投資", "資産運用", "finance"),
    "FX": ("fx", "為替", "レバレッジ"),
    "仮想通貨": ("仮想通貨", "crypto", "暗号資産", "bitcoin", "btc"),
    "LINE誘導": ("line registration", "line register", "line add", "lineで", "line登録", "line追加", "line誘導", "ライン"),
    "DMで個人情報要求": ("dmで", "dmください", "個人情報", "住所", "電話番号", "メールアドレス"),
    "高額賞品": ("高額", "100万円", "100万", "50万円", "iPhone", "MacBook"),
    "フォロー数稼ぎ": ("フォロワー稼ぎ", "フォロワーを増やす", "懸賞垢", "懸賞アカウント"),
    "年齢条件不明": ("年齢不明", "年齢条件不明", "未成年不可", "18歳未満不可", "20歳未満不可"),
    "日本国外向け": ("海外", "国外", "worldwide", "global", "日本国外"),
    "締切不明": ("締切不明", "期限不明", "deadline unknown"),
    "投稿URL不明": ("url不明", "リンクなし", "投稿url不明"),
    "主催者不明": ("主催者不明", "運営不明", "organizer unknown"),
    "成人向け": ("成人向け", "r18", "18禁", "アダルト", "酒", "たばこ"),
}

FORM_WORDS = ("フォーム", "webフォーム", "応募フォーム", "入力", "記入")
SIMPLE_ACTION_WORDS = ("フォロー", "リポスト", "rt", "rp", "いいね", "rtで", "rpで")
OFFICIAL_WORDS = ("株式会社", "有限会社", "合同会社", "自治体", "市役所", "区役所", "町役場", "村役場", "公式", "メーカー", "店舗", "ショップ", "co., ltd", "co ltd", "ltd", "inc", "corp", "corporation", "company")
TRUST_WORDS = ("official", "pr", "campaign", "brand", "store")
VALUE_WORDS = ("食品", "日用品", "子育て", "商品券", "ギフト券", "quo", "amazon", "家電", "旅行", "コーヒー", "お菓子", "防災")


def _lower_text(value: object) -> str:
    return str(value or "").casefold()


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _list_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("、", ",").split(",") if part.strip()]


def _detect_risk_flags(candidate: dict[str, object]) -> list[str]:
    text = " ".join(
        [
            _lower_text(candidate.get("title")),
            _lower_text(candidate.get("organizer")),
            _lower_text(candidate.get("account_handle")),
            _lower_text(candidate.get("campaign_url")),
            _lower_text(candidate.get("prize")),
            _lower_text(candidate.get("eligibility")),
            _lower_text(candidate.get("age_requirement")),
            _lower_text(candidate.get("region_requirement")),
            " ".join(_lower_text(item) for item in _list_values(candidate.get("requirements"))),
        ]
    )
    flags: list[str] = []
    for label, needles in RISK_PATTERNS.items():
        if any(needle.casefold() in text for needle in needles):
            flags.append(label)
    if not candidate.get("post_url"):
        flags.append("投稿URL不明")
    if not candidate.get("deadline"):
        flags.append("締切不明")
    if not candidate.get("region_requirement"):
        flags.append("日本国外向け")
    organizer = _lower_text(candidate.get("organizer"))
    if not organizer or organizer in {"不明", "未取得", "unknown", "なし"}:
        flags.append("主催者不明")
    return list(dict.fromkeys(flags))


def _parse_deadline_days(value: object) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(text, fmt).date()
            return (dt - date.today()).days
        except ValueError:
            pass
    return None


def _score_deadline(value: object) -> tuple[int, list[str]]:
    days = _parse_deadline_days(value)
    if days is None:
        return 0, ["締切不明"]
    if days < 0:
        return 0, ["締切切れ"]
    if days <= 2:
        return 95, ["締切が非常に近い"]
    if days <= 7:
        return 82, ["締切が近い"]
    if days <= 14:
        return 68, []
    if days <= 30:
        return 52, []
    return 40, []


def _score_trust(candidate: dict[str, object], risk_flags: list[str]) -> tuple[int, list[str]]:
    score = 35
    reasons: list[str] = []
    organizer = _lower_text(candidate.get("organizer"))
    handle = _lower_text(candidate.get("account_handle"))
    if any(word.casefold() in organizer for word in OFFICIAL_WORDS):
        score += 35
        reasons.append("公式/法人")
    if any(word in handle for word in TRUST_WORDS):
        score += 10
    if any(flag in risk_flags for flag in {"主催者不明", "フォロー数稼ぎ", "日本国外向け"}):
        score -= 15
    if not organizer:
        score -= 10
    if organizer in {"不明", "未取得", "unknown", "なし"}:
        score -= 15
    return max(0, min(100, score)), reasons


def _score_ease(candidate: dict[str, object], risk_flags: list[str]) -> tuple[int, list[str], str]:
    requirements = [item.casefold() for item in _list_values(candidate.get("requirements"))]
    score = 45
    reasons: list[str] = []
    apply_difficulty = "medium"
    text = " ".join(requirements + [_lower_text(candidate.get("eligibility")), _lower_text(candidate.get("raw_text"))])
    if requirements and all(any(word in requirement for word in SIMPLE_ACTION_WORDS) for requirement in requirements):
        score += 35
        reasons.append("簡単な応募条件")
        apply_difficulty = "low"
    elif any(word in text for word in FORM_WORDS):
        score -= 10
        reasons.append("フォーム入力あり")
        apply_difficulty = "medium"
    if any(flag in risk_flags for flag in {"LINE誘導", "DMで個人情報要求"}):
        score -= 35
        apply_difficulty = "high"
    if len(requirements) <= 2:
        score += 10
    if len(requirements) >= 4:
        score -= 5
    if any(word in text for word in ("年齢確認", "本人確認", "身分証")):
        score -= 8
    return max(0, min(100, score)), reasons, apply_difficulty


def _score_value(candidate: dict[str, object]) -> tuple[int, list[str]]:
    score = 45
    reasons: list[str] = []
    text = " ".join(
        [
            _lower_text(candidate.get("prize")),
            _lower_text(candidate.get("title")),
            _lower_text(candidate.get("eligibility")),
        ]
    )
    if any(word.casefold() in text for word in VALUE_WORDS):
        score += 20
        reasons.append("実用性の高い賞品")
    if any(word in text for word in ("食品", "日用品", "子育て")):
        score += 10
    if any(word in text for word in ("商品券", "ギフト券", "quo", "amazon")):
        score += 10
    if any(word.casefold() in text for word in ("iPhone", "MacBook", "switch", "ps5", "家電")):
        score += 15
    if any(word in text for word in ("現金", "money", "cash")):
        score -= 25
    return max(0, min(100, score)), reasons


def _recommendation_from_scores(
    *,
    safety_score: int,
    trust_score: int,
    ease_score: int,
    value_score: int,
    deadline_score: int,
    confidence: float,
    risk_flags: list[str],
) -> tuple[str, str, str]:
    confidence_penalty = max(0, int(round((1.0 - confidence) * 18)))
    total_score = max(
        0,
        min(
            100,
            int(round((safety_score * 0.34) + (trust_score * 0.18) + (ease_score * 0.16) + (value_score * 0.14) + (deadline_score * 0.18)))
            - confidence_penalty,
        ),
    )
    if safety_score < 45 or any(flag in HIGH_RISK_FLAGS for flag in risk_flags):
        recommendation = "skip"
        reason = " / ".join(dict.fromkeys(risk_flags[:3])) or "安全性が低い"
    elif deadline_score >= 90:
        recommendation = "watch"
        reason = "締切が非常に近い"
    elif total_score >= 65 and safety_score >= 60 and trust_score >= 55:
        recommendation = "review"
        reason = "公式性が高く、応募しやすい"
    elif total_score >= 58 and safety_score >= 55:
        recommendation = "watch"
        reason = "要件確認後に再評価"
    else:
        recommendation = "watch"
        reason = "スコアは中程度"
    if any(flag in risk_flags for flag in {"締切不明", "主催者不明"} ) and recommendation == "review":
        recommendation = "watch"
        reason = "締切または主催者の確認が必要"
    if confidence < 0.45 and recommendation == "review":
        recommendation = "watch"
        reason = "信頼度が低いため再確認"
    return recommendation, reason, str(total_score)


def score_x_campaign(candidate: dict[str, object]) -> dict[str, object]:
    risk_flags = list(dict.fromkeys(_list_values(candidate.get("risk_flags")) + _detect_risk_flags(candidate)))
    try:
        confidence_value = max(0.0, min(1.0, float(candidate.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence_value = 0.0

    safety_score = int(round(confidence_value * 100))
    for flag in risk_flags:
        if flag in HIGH_RISK_FLAGS:
            safety_score -= 35
        elif flag in {"高額賞品", "フォロー数稼ぎ", "成人向け"}:
            safety_score -= 25
        elif flag in {"年齢条件不明", "日本国外向け", "締切不明", "投稿URL不明", "主催者不明"}:
            safety_score -= 12

    trust_score, trust_reasons = _score_trust(candidate, risk_flags)
    ease_score, ease_reasons, apply_difficulty = _score_ease(candidate, risk_flags)
    value_score, value_reasons = _score_value(candidate)
    deadline_score, deadline_reasons = _score_deadline(candidate.get("deadline"))

    if not candidate.get("campaign_url"):
        safety_score -= 5
    if not candidate.get("post_url"):
        safety_score -= 50

    safety_score = max(0, min(100, safety_score))
    trust_score = max(0, min(100, trust_score))
    ease_score = max(0, min(100, ease_score))
    value_score = max(0, min(100, value_score))
    deadline_score = max(0, min(100, deadline_score))

    recommendation, recommendation_reason, total_score_text = _recommendation_from_scores(
        safety_score=safety_score,
        trust_score=trust_score,
        ease_score=ease_score,
        value_score=value_score,
        deadline_score=deadline_score,
        confidence=confidence_value,
        risk_flags=risk_flags,
    )
    total_score = int(total_score_text)
    if recommendation == "review" and deadline_score >= 90:
        recommendation = "watch"
        recommendation_reason = "締切が非常に近い"
    if recommendation == "skip":
        apply_difficulty = "high"
    queue_status = recommendation
    queue_reason = recommendation_reason
    if recommendation == "review":
        status = "research_found"
    elif recommendation == "watch":
        status = "research_found"
    else:
        status = "research_found"

    extra_reasons = [reason for reason in (*trust_reasons, *ease_reasons, *value_reasons, *deadline_reasons) if reason]
    if extra_reasons and recommendation != "skip":
        recommendation_reason = " / ".join(dict.fromkeys([recommendation_reason, *extra_reasons]))

    return {
        **candidate,
        "status": status,
        "risk_flags": risk_flags,
        "safety_score": safety_score,
        "trust_score": trust_score,
        "ease_score": ease_score,
        "value_score": value_score,
        "deadline_score": deadline_score,
        "total_score": total_score,
        "recommendation": recommendation,
        "recommendation_reason": recommendation_reason,
        "apply_difficulty": apply_difficulty,
        "queue_status": queue_status,
        "queue_reason": queue_reason,
        "confidence": confidence_value,
    }


def apply_x_campaign_filter(candidates: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return [score_x_campaign(candidate) for candidate in candidates]
