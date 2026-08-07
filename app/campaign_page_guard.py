from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


ENDED_TERMS = (
    "応募は終了しました",
    "応募受付は終了しました",
    "募集は終了しました",
    "募集終了",
    "受付終了",
    "応募終了",
    "締め切りました",
    "キャンペーンは終了",
    "懸賞コーナーは閉鎖",
    "ページが見つかりません",
    "404 not found",
)

GENERIC_TITLE_TERMS = (
    "プレゼント",
    "キャンペーン",
    "懸賞",
    "抽選",
    "無料",
    "限定",
    "当たる",
    "応募",
    "名様",
)


@dataclass(frozen=True)
class CampaignPageGuardResult:
    safe_to_fill: bool
    reason: str
    matched_terms: tuple[str, ...] = ()


def _normalize(text: object) -> str:
    return re.sub(r"[^0-9a-z一-龯ぁ-んァ-ヶー]+", "", str(text or "").casefold())


def _title_terms(title: str) -> list[str]:
    value = str(title or "")
    for term in GENERIC_TITLE_TERMS:
        value = value.replace(term, " ")
    terms = [
        _normalize(part)
        for part in re.split(r"[\s　・/／【】\[\]（）()「」『』:：,，]+", value)
    ]
    return [term for term in terms if len(term) >= 4 and not term.isdigit()]


def evaluate_campaign_page(
    campaign: Mapping[str, object],
    body_text: str,
    *,
    page_title: str = "",
) -> CampaignPageGuardResult:
    combined = f"{page_title}\n{body_text}"
    normalized_page = _normalize(combined)
    if any(_normalize(term) in normalized_page for term in ENDED_TERMS):
        return CampaignPageGuardResult(False, "campaign_ended")

    campaign_title = str(campaign.get("campaign_name") or campaign.get("title") or campaign.get("prize") or "")
    normalized_title = _normalize(campaign_title)
    if normalized_title and normalized_title in normalized_page:
        return CampaignPageGuardResult(True, "matched", (campaign_title,))

    terms = _title_terms(campaign_title)
    matched = tuple(term for term in terms if term in normalized_page)
    has_identity_context = bool(str(campaign.get("provider") or "").strip() or str(campaign.get("prize") or "").strip())
    if has_identity_context and terms and not matched:
        return CampaignPageGuardResult(False, "campaign_mismatch")

    return CampaignPageGuardResult(True, "matched" if matched else "insufficient_evidence", matched)
