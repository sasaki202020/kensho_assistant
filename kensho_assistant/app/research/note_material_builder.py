from __future__ import annotations

from typing import Any


def _bullet(items: list[Any], fallback: str) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        values = [fallback]
    return "\n".join(f"- {value}" for value in values)


def build_note_material(analysis: dict[str, Any]) -> str:
    topic = str(analysis.get("topic", ""))
    source_urls = [str(url) for url in analysis.get("source_urls", [])]
    angles = [str(item) for item in analysis.get("note_article_angles", [])]
    return f"""# 調査テーマ
{topic}

## 結論
X上では関心が高い一方で、断定表現や再現条件の不足があり、記事化するなら期待値を調整する切り口が安全です。

## Xで話題になっている主張
{analysis.get("main_claim", "")}

## 信頼できそうな点
{_bullet(list(analysis.get("supporting_points", [])), "便利さや効率化の可能性はある")}

## 怪しい・確認が必要な点
{_bullet(list(analysis.get("exaggeration_flags", [])), "断定表現は少ないが根拠確認は必要")}
{_bullet(list(analysis.get("missing_evidence", [])), "検証可能な根拠")}

## 反対意見・補足
{_bullet(list(analysis.get("opposing_points", [])), "反対意見はmockデータ内では少ない")}

## note記事にするならこの切り口
{_bullet(angles, "期待値を上げすぎない実践レビュー")}

## 記事構成案
- 導入: Xで目立つ主張
- 検証: どこまで任せられるか
- 注意点: 誇張表現と確認不足
- 実践: 安全な使い方
- まとめ: 人間のレビューを残す

## 参考URL
{_bullet(source_urls, "参考URLなし")}

## サムネ文言案
- AI開発 完全自動は本当？
- Codex活用 注意点
- サブエージェントの現実

## X投稿案
- Xで話題のAI駆動開発について、便利な点と危ない誇張表現を分けて整理しました。
- 「完全自動」と言い切る前に、設計レビューとテスト確認をどこで残すかが重要です。
"""
