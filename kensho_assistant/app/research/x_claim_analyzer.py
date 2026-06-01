from __future__ import annotations

from typing import Any

from kensho_assistant.app.harness.safety_rules import (
    find_exaggeration_flags,
    requires_official_check,
)


OPPOSING_MARKERS = ("危ない", "言いすぎ", "反対", "慎重", "確認", "不足", "誤り")
SUPPORT_MARKERS = ("便利", "できます", "できる", "有効", "高い", "成功")


def analyze_x_claims(query: str, posts: list[dict[str, Any]]) -> dict[str, Any]:
    texts = [str(post.get("text", "")) for post in posts]
    related_posts = [
        {
            "author": post.get("author", ""),
            "handle": post.get("handle", ""),
            "post_url": post.get("post_url", ""),
            "text": post.get("text", ""),
            "engagement_hint": post.get("engagement_hint", ""),
        }
        for post in posts
    ]
    supporting = [text for text in texts if any(marker in text for marker in SUPPORT_MARKERS)]
    opposing = [text for text in texts if any(marker in text for marker in OPPOSING_MARKERS)]
    exaggeration_flags = find_exaggeration_flags(texts)
    missing_evidence = []
    if exaggeration_flags:
        missing_evidence.append("断定・誇張表現を裏付ける一次情報")
    if not any("公式" in text for text in texts):
        missing_evidence.append("公式情報または検証可能な根拠")
    credibility_score = max(0.0, min(1.0, 0.65 - 0.08 * len(exaggeration_flags) + 0.05 * len(opposing)))

    return {
        "topic": query,
        "main_claim": texts[0] if texts else query,
        "supporting_points": supporting[:5],
        "opposing_points": opposing[:5],
        "uncertain_points": ["投稿だけでは実現条件・再現性・失敗例が不足"] if texts else ["mock投稿が空"],
        "exaggeration_flags": exaggeration_flags,
        "missing_evidence": missing_evidence,
        "related_posts": related_posts,
        "source_urls": [str(post.get("post_url", "")) for post in posts if post.get("post_url")],
        "credibility_score": round(credibility_score, 2),
        "virality_reason": "強い断定表現とAI開発効率化への関心が拡散要因になりやすい",
        "official_check_required": requires_official_check(query, texts),
        "note_article_angles": [
            "AI駆動開発で任せられる範囲と人間が確認すべき範囲",
            "完全自動化という言葉が誤解を生む理由",
            "サブエージェント活用を安全に試す手順",
        ],
    }
