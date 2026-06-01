from __future__ import annotations

from .autopilot_shared import LeadRecord


_PLANS = [
    ("ミニ診断", "9,800円", "要点だけ見て、まずは優先課題を知りたい方向け"),
    ("標準改善案", "29,800円", "診断に加えて、具体的な改善順まで整理したい方向け"),
    ("改善指示書つき", "79,800円", "外注先にそのまま渡せる修正指示を作りたい方向け"),
    ("LP改善/WordPress修正", "150,000円〜", "実作業まで一気通貫で進めたい方向け"),
]


def choose_plan(score: int, lead: LeadRecord) -> tuple[str, str, str]:
    if score >= 80:
        return _PLANS[2]
    if score >= 65:
        return _PLANS[1]
    if lead.website_url:
        return _PLANS[0]
    return _PLANS[3]


def build_estimate_markdown(lead: LeadRecord, diagnostics: dict[str, object]) -> str:
    score = int(diagnostics.get("score", 0) or 0)
    plan_name, price, note = choose_plan(score, lead)
    secondary_name, secondary_price, secondary_note = _PLANS[1]
    return "\n".join(
        [
            "# estimate",
            f"- company: {lead.company_name}",
            f"- industry: {lead.industry}",
            f"- area: {lead.area}",
            f"- score: {score}",
            "",
            "## 推奨プラン",
            f"- {plan_name}: {price}",
            f"- {note}",
            "",
            "## 参考プラン",
            f"- {secondary_name}: {secondary_price}",
            f"- {secondary_note}",
            "",
            "## 追加メモ",
            "- まずは無料改善メモから始めても問題ありません",
            "- 実作業は人間確認のあとに進める前提です",
            "- 送信・応募・公開は自動化しません",
        ]
    ) + "\n"

