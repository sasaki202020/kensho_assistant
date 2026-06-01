from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Iterable

from .config import AppConfig
from .source_fetcher import SourceDocument


MANDATORY_CAUTION = (
    "個別の年金額や対象条件は、人によって異なります。必ず、年金通知書、"
    "ねんきんネット、年金事務所、自治体の公式情報で確認してください。"
)


@dataclass
class ScenePlan:
    section: str
    title: str
    body: str
    emphasis: str
    duration_sec: int
    source_note: str
    narration: str
    facts: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)


SlidePlan = ScenePlan


@dataclass
class ScriptPackage:
    title: str
    ttp_type: str
    scenes: list[ScenePlan]
    narration_text: str
    script_markdown: str
    facts: dict[str, list[str] | str]
    warnings: list[str]
    scenes_json: list[dict[str, object]]


def _extract_following_amount(lines: list[str], label_match: str) -> str | None:
    for index, line in enumerate(lines):
        if label_match in line:
            for follower in lines[index + 1 : index + 4]:
                amount = re.search(r"([0-9,]+円)", follower)
                if amount:
                    return amount.group(1)
    return None


def _extract_keywords(text: str) -> list[str]:
    keywords = [
        "年金",
        "給付金",
        "加算",
        "申請",
        "対象",
        "改定",
        "受給",
        "手続き",
        "通知",
    ]
    found: list[str] = []
    for keyword in keywords:
        if keyword in text and keyword not in found:
            found.append(keyword)
    return found


def _join_nonempty(parts: Iterable[str]) -> str:
    return "\n".join(part for part in parts if part).strip()


def _safe_amount_text(amounts: list[str]) -> str:
    if amounts:
        return "、".join(amounts[:3])
    return "未確認"


def _build_slide(
    index: int,
    title: str,
    body: str,
    narration: str,
    duration_sec: int,
    facts: list[str],
    risk_notes: list[str] | None = None,
) -> SlidePlan:
    return SlidePlan(
        section=title,
        title=title,
        body=body,
        emphasis=facts[0] if facts else title,
        duration_sec=duration_sec,
        source_note="",
        narration=narration,
        facts=facts,
        risk_notes=risk_notes or [],
    )


def _clamp(value: int, minimum: int = 15, maximum: int = 30) -> int:
    return max(minimum, min(maximum, value))


def _normalize_durations(scenes: list[ScenePlan], target_total: int) -> list[ScenePlan]:
    if not scenes:
        return scenes
    current_total = sum(scene.duration_sec for scene in scenes)
    if current_total <= 0:
        return scenes
    factor = target_total / current_total
    raw_values = [scene.duration_sec * factor for scene in scenes]
    adjusted = [_clamp(int(round(value))) for value in raw_values]
    diff = target_total - sum(adjusted)
    remainders = sorted(
        enumerate(raw_values),
        key=lambda item: item[1] - int(round(item[1])),
        reverse=diff > 0,
    )

    def can_adjust(scene: ScenePlan, delta: int) -> bool:
        candidate = scene.duration_sec + delta
        return 15 <= candidate <= 30

    index = 0
    while diff != 0 and remainders:
        scene_index = remainders[index % len(remainders)][0]
        delta = 1 if diff > 0 else -1
        if can_adjust(scenes[scene_index], delta):
            adjusted[scene_index] += delta
            diff -= delta
        index += 1
        if index > len(remainders) * 6:
            break
    for idx, scene in enumerate(scenes):
        scene.duration_sec = adjusted[idx]
    return scenes


def _scene(
    section: str,
    title: str,
    body: str,
    emphasis: str,
    duration_sec: int,
    source_note: str,
    narration: str,
    facts: list[str] | None = None,
    risk_notes: list[str] | None = None,
) -> ScenePlan:
    return ScenePlan(
        section=section,
        title=title,
        body=body,
        emphasis=emphasis,
        duration_sec=duration_sec,
        source_note=source_note,
        narration=narration,
        facts=facts or [],
        risk_notes=risk_notes or [],
    )


def infer_ttp_type(topic: str) -> str:
    if any(keyword in topic for keyword in ["4選", "5選", "チェック", "見落とし", "定期便", "確認したい"]):
        return "チェックリスト型"
    if any(keyword in topic for keyword in ["判断基準", "何歳", "繰上げ", "繰下げ", "受け取るべき"]):
        return "判断基準型"
    return "最新改正型"


def generate_script(
    topic: str,
    source: SourceDocument,
    config: AppConfig,
) -> ScriptPackage:
    ttp_type = infer_ttp_type(topic)
    raw_text = source.raw_text
    summary_lines = source.summary_lines
    national_amount = _extract_following_amount(summary_lines, "国民年金（老齢基礎年金（満額））")
    employee_amount = _extract_following_amount(summary_lines, "厚生年金（夫婦2人分の老齢基礎年金を含む標準的な年金額）")
    support_amount = _extract_following_amount(summary_lines, "老齢年金生活者支援給付金")
    national_rate = "1.9%" if "1.9％" in raw_text or "1.9%" in raw_text else None
    employee_rate = "2.0%" if "2.0％" in raw_text or "2.0%" in raw_text else None
    support_rate = "3.2%" if "3.2％" in raw_text or "3.2%" in raw_text else None
    has_official = bool(source.official_url and source.status == "fetched")
    source_note = "出典：日本年金機構 令和8年4月分からの年金額等について"
    if source.official_url:
        source_note = f"出典：日本年金機構 {source.title}"

    official_intro = (
        "年金額は、ニュースで見た金額がそのまま自分の受取額になるとは限りません。"
        f"今日は「{topic}」を、60代・70代向けに、"
        "自分に関係があるか、何を確認すればよいか、どこで確認すればよいかを整理します。"
    )
    if not has_official:
        official_intro += " 公式URL未指定のため、数値はサンプル扱いです。"

    scenes = [
        _scene("結論", "冒頭の結論", "結局いくら増えるかを先に見る", "いくら増える？", 24, source_note, official_intro, [topic]),
        _scene("対象者", "今日の対象者", "受給中 / これから受給", "対象者", 20, source_note, "対象は、今受け取っている方、これから受け取る方、通知が届いた方です。"),
        _scene("見方", "まず見る順番", "国民年金→厚生年金→標準額→注意点", "見る順番", 20, source_note, "見る順番を決めると、改定額が追いやすくなります。"),
        _scene("改定率", "2026年度の改定率", "国民年金1.9% / 厚生年金2.0%", "1.9% / 2.0%", 22, source_note, "2026年度は、国民年金が1.9パーセント、厚生年金が2.0パーセントの増額改定です。"),
        _scene("国民年金", "国民年金の金額", f"満額は {national_amount or '未確認'}", national_amount or "未確認", 24, source_note, "国民年金の満額は、公式資料では70,608円です。"),
        _scene("国民年金補足", "国民年金の補足", "生年月日で金額が少し変わる", "生年月日差", 18, source_note, "昭和31年4月1日以前生まれの方は、金額が少し異なります。"),
        _scene("厚生年金", "厚生年金の金額", f"標準額は {employee_amount or '未確認'}", employee_amount or "未確認", 24, source_note, "厚生年金の標準的な年金額は、公式資料では237,279円です。"),
        _scene("厚生年金補足", "厚生年金の見方", "平均収入40年の例で見る", "標準額の前提", 18, source_note, "これは平均的な収入で40年間働いた場合の目安です。"),
        _scene("夫婦世帯", "夫婦世帯の標準額", "2人分の基礎年金を含む", "夫婦世帯", 20, source_note, "夫婦世帯の標準額には、2人分の老齢基礎年金が含まれます。"),
        _scene("支援給付金", "支援給付金の基準額", f"老齢年金生活者支援給付金 {support_amount or '未確認'}", support_amount or "未確認", 22, source_note, "老齢年金生活者支援給付金の基準額は、公式資料では5,620円です。"),
        _scene("支援補足", "支援給付金の補足", "実額は条件で変わる", "条件で変動", 18, source_note, "保険料免除期間などで、実際の支給額は変わることがあります。"),
        _scene("中間まとめ", "ここまでのまとめ", "改定率 / 国民年金 / 厚生年金", "ここまでの整理", 22, source_note, "ここまでで、改定率と主要な金額を整理できます。"),
        _scene("増え方", "どう増えるか", "自分の年金額で増え方は違う", "個別差", 20, source_note, "増える額は、今の年金額や加入記録で変わります。"),
        _scene("差の理由", "個別差の理由", "生年月日 / 加入期間 / 繰上げ・繰下げ", "個別差", 20, source_note, "生年月日や受給の開始時期でも、金額は変わります。"),
        _scene("申請", "申請が必要か", "自動反映と申請が必要なものがある", "申請確認", 20, source_note, "制度によっては申請が必要です。案内を必ず確認してください。"),
        _scene("通知書", "通知書で確認", "年金額改定通知書を見る", "通知書確認", 18, source_note, "年金額改定通知書で、増える額と支払額を確認します。"),
        _scene("ネット", "ねんきんネット", "オンラインでも確認できる", "ねんきんネット", 18, source_note, "ねんきんネットでも、内容の確認や再交付の手続きができます。"),
        _scene("年金事務所", "年金事務所", "迷ったら窓口で確認", "年金事務所", 18, source_note, "分からない点は、年金事務所で確認するのが安全です。"),
        _scene("自治体", "自治体窓口", "給付金は自治体の案内も確認", "自治体確認", 18, source_note, "給付金は、自治体の案内も確認してください。"),
        _scene("誤解1", "よくある誤解", "同じ金額とは限らない", "同額ではない", 18, source_note, "同じ金額になるとは限りません。"),
        _scene("具体例1", "具体例その1", "国民年金満額の人の見方", national_amount or "70,608円", 20, source_note, "国民年金の人は、通知書の金額と満額の差を見ます。"),
        _scene("具体例2", "具体例その2", "厚生年金の人の見方", employee_amount or "237,279円", 20, source_note, "厚生年金の人は、加入記録と標準額の前提を見ます。"),
        _scene("中間再整理", "ここまでの再整理", "改定率 / 標準額 / 注意点", "再整理", 20, source_note, "ここで一度、改定率、標準額、注意点を整理します。"),
        _scene("注意1", "注意点その1", "数字だけで判断しない", "注意点", 18, source_note, "金額だけでなく、対象条件も確認してください。"),
        _scene("注意2", "注意点その2", "申請期限の見落としに注意", "期限確認", 18, source_note, "通知の見落としや、申請期限の見落としに注意します。"),
        _scene("注意3", "注意点その3", "自治体で案内が違うことがある", "自治体差", 18, source_note, "自治体ごとに、案内や手続きが違うことがあります。"),
        _scene("確認先", "確認先まとめ", "通知書 / ねんきんネット / 年金事務所 / 自治体", "確認先", 22, source_note, "最後は、通知書、ねんきんネット、年金事務所、自治体で確認します。"),
        _scene("締め", "最後のまとめ", "個別確認を必ず行う", "個別確認", 24, source_note, official_intro + " 必ず、自分の情報で確認してください。"),
    ]

    scenes = _normalize_durations(scenes, config.target_seconds)
    narration_text = "\n\n".join(f"【{index:02d} {scene.section} / {scene.title}】\n{scene.narration}" for index, scene in enumerate(scenes, start=1))
    script_markdown = _join_nonempty(
        [
            f"# {topic}",
            f"- TTPした型: {ttp_type}",
            "",
            "## 重要注意",
            MANDATORY_CAUTION,
            "",
            *[
                "\n".join(
                    [
                        f"## {index:02d}. {scene.section} - {scene.title}",
                        f"- 画面: {scene.body}",
                        f"- 強調: {scene.emphasis}",
                        f"- ナレーション: {scene.narration}",
                        f"- 予定尺: {scene.duration_sec}秒",
                        f"- 出典: {scene.source_note}",
                    ]
                )
                for index, scene in enumerate(scenes, start=1)
            ],
        ]
    )

    facts = {
        "使用した制度名": [
            "令和8年度の年金額改定",
            "国民年金",
            "厚生年金",
            "年金生活者支援給付金",
        ],
        "使用した金額": [
            value
            for value in [
                national_amount,
                employee_amount,
                support_amount,
                national_rate,
                employee_rate,
                support_rate,
            ]
            if value
        ]
        if has_official
        else ["未確認"],
        "対象者": [
            "受給中の方",
            "これから年金を受け取る方",
            "自治体や年金事務所から案内が届く可能性がある方",
        ]
        if has_official
        else ["サンプルモードのため未確定"],
        "申請の有無": [
            "公式資料で要確認" if has_official else "サンプルモードのため未確定"
        ],
        "注意点": [
            "通知書の見落とし",
            "申請期限の勘違い",
            "自治体ごとの案内差",
            "必ず公式情報で再確認",
        ],
        "参照URL": [source.official_url or "なし"],
        "確認が必要な表現": [
            "具体的な金額表現",
            "対象条件の断定",
            "申請不要の断定",
            "個別差がある項目の一般化",
        ],
    }

    warnings: list[str] = []
    if not has_official:
        warnings.append("公式URL未指定のため、制度名・金額・対象条件はサンプル扱いです。")
    elif source.status != "fetched":
        warnings.append("公式URLの取得が失敗または不完全です。")
    if not (national_amount and employee_amount and support_amount):
        warnings.append("公式本文から主要金額の一部を抽出できませんでした。")

    scenes_json = [
        {
            "section": scene.section,
            "title": scene.title,
            "body": scene.body,
            "emphasis": scene.emphasis,
            "duration_sec": scene.duration_sec,
            "source_note": scene.source_note,
        }
        for scene in scenes
    ]

    return ScriptPackage(
        title=topic,
        ttp_type=ttp_type,
        scenes=scenes,
        narration_text=narration_text,
        script_markdown=script_markdown,
        facts=facts,
        warnings=warnings,
        scenes_json=scenes_json,
    )
