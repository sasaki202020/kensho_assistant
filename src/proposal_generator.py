from __future__ import annotations

from .autopilot_shared import LeadRecord, compact_text


_INDUSTRY_PHRASES = {
    "整骨院": "予約導線、症状説明、院内の安心感",
    "整体院": "施術内容の見え方、比較しやすさ、信頼感",
    "鍼灸院": "初診の不安解消、専門性の伝わり方、来院導線",
    "歯科": "症例紹介、予約導線、診療時間の分かりやすさ",
    "美容室": "メニュー比較、空き枠の見せ方、雰囲気訴求",
    "飲食": "メニュー訴求、写真、予約や問い合わせの分かりやすさ",
}


def _industry_phrase(industry: str) -> str:
    for key, phrase in _INDUSTRY_PHRASES.items():
        if key in industry:
            return phrase
    return "見やすい導線、安心材料、問い合わせのしやすさ"


def build_proposal_text(lead: LeadRecord, diagnostics: dict[str, object], *, fix_summary: str) -> str:
    weakness = compact_text(str(diagnostics.get("primary_weakness", "スマホでの見え方に改善余地があります")), 60)
    score = int(diagnostics.get("score", 0) or 0)
    rank = str(diagnostics.get("rank", "C"))
    phrase = _industry_phrase(lead.industry)
    body = (
        f"{lead.company_name}様のサイトを拝見しました。{phrase}の見せ方に少し工夫の余地があり、"
        f"特に「{weakness}」がもったいない状態です。"
        f"現状でも営業力はありますが、{score}点・{rank}評価のため、"
        f"訪問前に不安を減らすだけで問い合わせ率が伸びる可能性があります。"
        f"まずは無料で改善メモを1枚お渡しできます。"
        f"押し売りはせず、優先度の高い直し方だけを簡潔にまとめます。"
        f"必要であれば、その後に{fix_summary}まで整理します。"
    )
    text = body.strip()
    if len(text) < 300:
        text += " " + "。".join(
            [
                "写真の見せ方や導線の整理を少し整えるだけでも印象は変わります",
                "同じ内容でも、初見で伝わる順番を直すだけで反応が変わることがあります",
            ]
        )
    return text[:500]

