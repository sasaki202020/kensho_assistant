from __future__ import annotations

from pathlib import Path

from .script_generator import MANDATORY_CAUTION, ScriptPackage
from .source_fetcher import SourceDocument


def build_youtube_meta(
    topic: str,
    source: SourceDocument,
    package: ScriptPackage,
) -> str:
    if package.ttp_type == "チェックリスト型":
        title_options = [
            f"【50歳以上必見】{topic}｜見落としやすいポイントを確認",
            f"【年金保存版】{topic}｜確認すべき項目を整理",
            f"{topic}｜見落とし注意のチェックリスト",
            f"{topic}｜ねんきん定期便だけで安心しないために",
            f"{topic}｜申請や確認が必要な項目を整理",
            f"{topic}｜50歳以上が確認したいポイント",
            f"{topic}｜確認先までやさしく解説",
            f"{topic}｜年金で見落としやすいこと",
            f"{topic}｜知らないと大損 [注意]",
            f"{topic}｜全員もらえる？ [注意]",
        ]
    elif package.ttp_type == "判断基準型":
        title_options = [
            f"【年金保存版】{topic}｜判断基準をやさしく整理",
            f"{topic}｜何を基準に決めるべき？",
            f"{topic}｜60歳・65歳・70歳の考え方",
            f"{topic}｜繰上げ・繰下げの注意点",
            f"{topic}｜自分に合う受け取り方の確認",
            f"{topic}｜やってはいけない判断",
            f"{topic}｜年金事務所で確認するポイント",
            f"{topic}｜判断前に見るチェックリスト",
            f"{topic}｜必ず得する受け取り方 [注意]",
            f"{topic}｜最強の受け取り方 [注意]",
        ]
    else:
        title_options = [
            f"【2026年最新】{topic}｜国民年金・厚生年金をやさしく解説",
            f"【年金保存版】{topic}｜公式情報をやさしく整理",
            f"{topic}｜自分はいくら増える？",
            f"{topic}｜国民年金・厚生年金の改定ポイント",
            f"{topic}｜夫婦世帯の標準額も確認",
            f"{topic}｜60代・70代向けにやさしく解説",
            f"{topic}｜通知書で確認する増額の見方",
            f"{topic}｜ねんきんネットと通知書で確認",
            f"{topic}｜見落としやすい注意点も確認",
            f"{topic}｜大きく増える人は誰？ [注意]",
        ]
    recommended_title = title_options[0]
    description = "\n".join(
        [
            f"テーマ: {topic}",
            f"動画タイプ: {package.ttp_type}",
            "",
            "この動画は、公式情報を優先して、年金・給付金の要点をやさしく整理したものです。",
            MANDATORY_CAUTION,
            "",
            f"参照URL: {source.official_url or 'なし'}",
            f"取得状況: {source.status}",
            "",
            "補足: 個別の年金額や対象条件は、通知書や公式窓口で確認してください。",
        ]
    )
    tags = [
        "年金",
        "給付金",
        "60代",
        "70代",
        "公式情報",
        topic,
    ]
    hashtags = [
        "#年金",
        "#年金改定",
        "#厚生年金",
        "#国民年金",
        "#給付金",
        "#シニア向け",
    ]
    fixed_comment = MANDATORY_CAUTION
    disclaimer = (
        "本動画は公式情報の要点整理であり、個別の受給額や申請要否を断定するものではありません。"
        "必要に応じて年金事務所または自治体の公式案内でご確認ください。"
    )
    return "\n".join(
        [
            f"recommended_title: {recommended_title}",
            "title_options:",
            *[f"- {title}" for title in title_options],
            "description:",
            description,
            "hashtags: " + ", ".join(hashtags),
            "tags: " + ", ".join(tags),
            "fixed_comment:",
            fixed_comment,
            "disclaimer:",
            disclaimer,
            f"official_url: {source.official_url or 'なし'}",
        ]
    )


def write_youtube_meta(output_dir: Path, topic: str, source: SourceDocument, package: ScriptPackage) -> Path:
    path = output_dir / "youtube_meta.txt"
    path.write_text(build_youtube_meta(topic, source, package) + "\n", encoding="utf-8")
    return path
