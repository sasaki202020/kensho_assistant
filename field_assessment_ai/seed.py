from __future__ import annotations

import argparse
import base64
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import select

from .config import load_settings
from .database import bootstrap_database
from .models import Estimate, Item, ItemImage, Job, MarketMemo
from .routes import _estimate_payload, _item_payload, _job_payload, _market_memo_payload, _persist_estimate
from .services.analysis import MockVisionAnalysisService
from .services.market import build_market_memo_defaults
from .services.uploads import save_upload_bytes
from .services.scoring import build_item_estimate_payload, build_job_estimate_payload
from sell_before_check_ai.models import (
    ConfidenceScore,
    ConsumerItemCheck,
    ConsumerReport,
    FlyerCheck,
    OfficialInfo,
    QuoteCheck,
    RefusalPhrase,
    RiskJudgement,
)
from sell_before_check_ai.services.consumer_flyer_check_service import analyze_flyer_check
from sell_before_check_ai.services.consumer_item_check_service import analyze_item_check
from sell_before_check_ai.services.consumer_quote_check_service import analyze_quote_check
from sell_before_check_ai.services.consumer_report_service import build_consumer_report_payload
from sell_before_check_ai.services.consumer_risk_judgement_service import build_risk_judgement_context
from sell_before_check_ai.services.official_info_service import ensure_official_info_seeded
from sell_before_check_ai.services.refusal_phrase_service import ensure_refusal_phrases_seeded


SAMPLE_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA"
    "AAC0lEQVR42mP8/x8AAwMCAO3Zs7kAAAAASUVORK5CYII="
)


def _sample_bytes() -> bytes:
    return base64.b64decode(SAMPLE_PNG_BASE64)


def _seed_business_sample_data(session, settings) -> dict[str, int]:
    if session.query(Job).count() > 0:
        return {
            "jobs": session.query(Job).count(),
            "items": session.query(Item).count(),
            "images": session.query(ItemImage).count(),
            "market_memos": session.query(MarketMemo).count(),
            "estimates": session.query(Estimate).count(),
        }

    job = Job(
        title="札幌市中央区 3LDK 片付け案件",
        customer_name="サンプル顧客",
        address="北海道札幌市中央区",
        contact_name="担当者A",
        contact_phone="000-0000-0000",
        status="draft",
        memo="サンプル案件。遺品整理と不用品回収を想定。",
        safety_notes="バッテリー類は別仕分け。",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    items = [
        Item(
            job_id=job.id,
            name="SONY 43V型液晶テレビ",
            category="テレビ",
            brand="SONY",
            model_number="KJ-43W730E",
            condition_note="中古・動作確認済み・リモコンあり",
            quantity=1,
            location_note="リビング",
            memo="家電リサイクル確認",
            status="active",
            safety_flags_json=["家電リサイクル注意"],
        ),
        Item(
            job_id=job.id,
            name="Canon EOS Kiss X7 レンズキット",
            category="カメラ",
            brand="Canon",
            model_number="EOS Kiss X7",
            condition_note="美品・付属品あり",
            quantity=1,
            location_note="寝室",
            memo="箱あり",
            status="active",
            safety_flags_json=[],
        ),
        Item(
            job_id=job.id,
            name="Nintendo Switch 本体",
            category="ゲーム",
            brand="Nintendo",
            model_number="HAC-001",
            condition_note="箱あり・動作確認済み",
            quantity=1,
            location_note="収納棚",
            memo="人気商品候補",
            status="active",
            safety_flags_json=[],
        ),
        Item(
            job_id=job.id,
            name="リチウムイオンバッテリー 2個",
            category="危険物",
            brand=None,
            model_number=None,
            condition_note="使用済み・膨張の有無要確認",
            quantity=2,
            location_note="工具箱",
            memo="危険物として個別確認",
            status="active",
            safety_flags_json=["危険物注意"],
        ),
    ]
    session.add_all(items)
    session.commit()
    for item in items:
        session.refresh(item)

    saved = save_upload_bytes(
        settings.upload_dir,
        relative_dir=f"items/{items[1].id}",
        original_filename="seed_camera.png",
        contents=_sample_bytes(),
        mime_type="image/png",
        prefix=f"{items[1].id}",
    )
    session.add(
        ItemImage(
            item_id=items[1].id,
            original_filename=saved.original_filename,
            stored_filename=saved.stored_filename,
            relative_path=saved.relative_path,
            public_url=saved.public_url,
            thumbnail_url=None,
            mime_type=saved.mime_type,
            file_size_bytes=saved.file_size_bytes,
            sort_order=0,
            caption="サンプル画像",
        )
    )
    session.commit()

    analysis_service = MockVisionAnalysisService()
    item_estimates: list[dict[str, int | str | None | dict]] = []
    for item in items:
        image_count = 1 if item.id == items[1].id else 0
        item_payload = _item_payload(item, image_count=image_count)
        analysis = analysis_service.analyze(item_payload)
        market_memo = build_market_memo_defaults(item_payload, analysis)
        memo_row = MarketMemo(
            item_id=item.id,
            **{
                key: market_memo[key]
                for key in [
                    "lowest_price",
                    "median_price",
                    "highest_price",
                    "sold_count",
                    "purchase_price",
                    "shipping_fee",
                    "marketplace_fee",
                    "packing_fee",
                    "disposal_fee_memo",
                    "internal_memo",
                    "search_keyword",
                    "source_urls",
                ]
            },
        )
        session.add(memo_row)
        session.commit()
        session.refresh(memo_row)
        estimate_payload = build_item_estimate_payload(item_payload, market_memo=market_memo, analysis=analysis)
        estimate = _persist_estimate(session, estimate_payload)
        item_estimates.append({**estimate_payload, "analysis": analysis, "market_memo": market_memo, "item": item_payload})

    job_estimate_payload = build_job_estimate_payload(_job_payload(job), item_estimates)
    _persist_estimate(session, job_estimate_payload)
    return {
        "jobs": session.query(Job).count(),
        "items": session.query(Item).count(),
        "images": session.query(ItemImage).count(),
        "market_memos": session.query(MarketMemo).count(),
        "estimates": session.query(Estimate).count(),
    }


def _consumer_image_ref(settings, check_type: str, check_id: int, filename: str) -> dict[str, Any]:
    saved = save_upload_bytes(
        settings.upload_dir,
        relative_dir=f"consumer/{check_type}/{check_id}",
        original_filename=filename,
        contents=_sample_bytes(),
        mime_type="image/png",
        prefix=f"{check_type}_{check_id}",
    )
    return {
        **asdict(saved),
        "caption": f"{check_type}サンプル",
    }


def _flyer_payload(row: FlyerCheck) -> dict[str, Any]:
    return {
        "company_name": row.company_name,
        "phone_number": row.phone_number,
        "flyer_text": row.flyer_text,
        "outcall_fee_text": row.outcall_fee_text,
        "cancellation_fee_text": row.cancellation_fee_text,
        "high_price_text": row.high_price_text,
        "same_day_cash_text": row.same_day_cash_text,
        "inducement_text": row.inducement_text,
        "memo": row.memo,
        "image_refs": list(row.image_refs_json or []),
    }


def _item_payload_consumer(row: ConsumerItemCheck) -> dict[str, Any]:
    return {
        "item_category": row.item_category,
        "item_name": row.item_name,
        "brand": row.brand,
        "model_number": row.model_number,
        "condition_note": row.condition_note,
        "accessories": row.accessories,
        "offered_price": row.offered_price,
        "market_memo": row.market_memo,
        "additional_photo_requests": row.additional_photo_requests_text,
        "check_points": row.check_points_text,
        "memo": row.memo,
        "image_refs": list(row.image_refs_json or []),
    }


def _quote_payload(row: QuoteCheck) -> dict[str, Any]:
    return {
        "offered_price": row.offered_price,
        "work_fee": row.work_fee,
        "disposal_fee": row.disposal_fee,
        "outcall_fee": row.outcall_fee,
        "appraisal_fee": row.appraisal_fee,
        "cancellation_fee": row.cancellation_fee,
        "home_appliance_recycling_fee": row.home_appliance_recycling_fee,
        "additional_charge_conditions": row.additional_charge_conditions,
        "package_price": row.package_price,
        "same_day_extra_charge": row.same_day_extra_charge,
        "estimate_sheet_present": row.estimate_sheet_present,
        "memo": row.memo,
        "image_refs": list(row.image_refs_json or []),
    }


def _persist_consumer_risk(session, check_type: str, check_row, payload: dict[str, Any]) -> None:
    analysis_context = build_risk_judgement_context(
        check_type,
        payload,
        session.scalars(select(OfficialInfo)).all(),
        session.scalars(select(RefusalPhrase)).all(),
    )
    confidence = ConfidenceScore(
        check_type=check_type,
        check_id=check_row.id,
        score_value=int(analysis_context.get("confidence_score") or 0),
        score_label=analysis_context.get("confidence_label"),
        reason=analysis_context.get("reason"),
        factors_json=list(analysis_context.get("caution_notes") or []),
        check_snapshot_json={"analysis": asdict(analysis_context["analysis"]), "query": analysis_context.get("query")},
    )
    session.add(confidence)
    session.commit()
    session.refresh(confidence)

    judgement = RiskJudgement(
        check_type=check_type,
        check_id=check_row.id,
        judgement_result=analysis_context.get("judgement_result") or "確認推奨",
        reason=analysis_context.get("reason"),
        missing_info_json=list(analysis_context.get("missing_info") or []),
        next_actions_json=list(analysis_context.get("next_actions") or []),
        official_info_ids_json=[int(info["id"]) for info in analysis_context.get("official_infos") or [] if info.get("id") is not None],
        reference_links_json=list(analysis_context.get("reference_links") or []),
        confidence_score_id=confidence.id,
        refusal_phrase=analysis_context.get("refusal_phrase"),
        caution_notes_json=list(analysis_context.get("caution_notes") or []),
        market_links_json=dict(analysis_context.get("market_links") or {}),
        check_snapshot_json={
            "analysis": asdict(analysis_context["analysis"]),
            "query": analysis_context.get("query"),
            "check_points": list(analysis_context.get("check_points") or []),
            "extra_photo_requests": list(analysis_context.get("extra_photo_requests") or []),
        },
    )
    session.add(judgement)
    session.commit()
    session.refresh(judgement)

    check_row.judgement_result = judgement.judgement_result
    check_row.reason = judgement.reason
    check_row.missing_info_json = list(judgement.missing_info_json or [])
    check_row.next_actions_json = list(judgement.next_actions_json or [])
    check_row.official_info_ids_json = list(judgement.official_info_ids_json or [])
    check_row.reference_links_json = list(judgement.reference_links_json or [])
    check_row.confidence_score_value = confidence.score_value
    check_row.confidence_label = confidence.score_label
    check_row.refusal_phrase = judgement.refusal_phrase
    check_row.note_text = " / ".join(judgement.caution_notes_json[:3]) if judgement.caution_notes_json else "参考判定"
    check_row.market_links_json = dict(judgement.market_links_json or {})
    check_row.market_query = analysis_context.get("query")
    check_row.caution_points_json = list(judgement.caution_notes_json or [])
    check_row.check_points_json = list(analysis_context.get("check_points") or [])
    check_row.photo_requests_json = list(analysis_context.get("extra_photo_requests") or [])
    check_row.latest_confidence_score_id = confidence.id
    check_row.latest_risk_judgement_id = judgement.id
    session.commit()

    report_payload = build_consumer_report_payload(check_type, payload, analysis_context, title=None, format="json")
    report = ConsumerReport(
        check_type=check_type,
        check_id=check_row.id,
        title=report_payload["title"],
        format="json",
        summary=report_payload["summary_text"],
        content_json=report_payload["content_json"],
        content_html=report_payload["content_html"],
        disclaimer=report_payload["content_json"].get("disclaimer"),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    check_row.latest_report_id = report.id
    session.commit()


def _seed_consumer_sample_data(session, settings) -> dict[str, int]:
    ensure_official_info_seeded(session)
    ensure_refusal_phrases_seeded(session)

    if session.query(FlyerCheck).count() == 0:
        flyer = FlyerCheck(
            company_name="サンプル訪問買取",
            phone_number="000-1111-2222",
            flyer_text="着物高価買取 / 出張査定無料 / 即日現金化",
            outcall_fee_text="出張費無料",
            cancellation_fee_text="キャンセル料無料",
            high_price_text="高価買取",
            same_day_cash_text="即日現金化",
            inducement_text="貴金属も査定 / ブランド品も査定",
            memo="サンプルチラシ",
        )
        session.add(flyer)
        session.commit()
        session.refresh(flyer)
        flyer.image_refs_json = [_consumer_image_ref(settings, "flyer", flyer.id, "flyer_sample.png")]
        session.commit()
        _persist_consumer_risk(session, "flyer", flyer, _flyer_payload(flyer))

    if session.query(ConsumerItemCheck).count() == 0:
        sewing = ConsumerItemCheck(
            item_category="ミシン",
            item_name="JUKI ミシン",
            brand="JUKI",
            model_number=None,
            condition_note="動作未確認",
            accessories="フットコントローラーなし",
            offered_price=1000,
            market_memo="型番不明",
            additional_photo_requests_text=None,
            check_points_text=None,
            memo="サンプル商品チェック",
        )
        session.add(sewing)
        session.commit()
        session.refresh(sewing)
        sewing.image_refs_json = [_consumer_image_ref(settings, "item", sewing.id, "sewing_sample.png")]
        session.commit()
        _persist_consumer_risk(session, "item", sewing, _item_payload_consumer(sewing))

        ring = ConsumerItemCheck(
            item_category="貴金属",
            item_name="K18らしき指輪",
            brand=None,
            model_number=None,
            condition_note="刻印未確認",
            accessories="なし",
            offered_price=5000,
            market_memo="刻印と重量が未確認",
            additional_photo_requests_text=None,
            check_points_text=None,
            memo="サンプル貴金属チェック",
        )
        session.add(ring)
        session.commit()
        session.refresh(ring)
        ring.image_refs_json = [_consumer_image_ref(settings, "item", ring.id, "gold_sample.png")]
        session.commit()
        _persist_consumer_risk(session, "item", ring, _item_payload_consumer(ring))

    if session.query(QuoteCheck).count() == 0:
        quote = QuoteCheck(
            offered_price=9800,
            work_fee=0,
            disposal_fee=0,
            outcall_fee=0,
            appraisal_fee=0,
            cancellation_fee=0,
            home_appliance_recycling_fee=None,
            additional_charge_conditions="当日追加請求あり",
            package_price=9800,
            same_day_extra_charge=80000,
            estimate_sheet_present=False,
            memo="軽トラックパック9,800円の案内",
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        quote.image_refs_json = [_consumer_image_ref(settings, "quote", quote.id, "quote_sample.png")]
        session.commit()
        _persist_consumer_risk(session, "quote", quote, _quote_payload(quote))

    return {
        "flyer_checks": session.query(FlyerCheck).count(),
        "consumer_item_checks": session.query(ConsumerItemCheck).count(),
        "quote_checks": session.query(QuoteCheck).count(),
        "official_infos": session.query(OfficialInfo).count(),
        "risk_judgements": session.query(RiskJudgement).count(),
        "confidence_scores": session.query(ConfidenceScore).count(),
        "refusal_phrases": session.query(RefusalPhrase).count(),
        "consumer_reports": session.query(ConsumerReport).count(),
    }


def seed_sample_data(reset: bool = False) -> dict[str, int]:
    settings = load_settings()
    if reset and settings.runtime_root.exists():
        db_path = settings.database_path
        if db_path.exists():
            db_path.unlink()
        if settings.upload_dir.exists():
            shutil.rmtree(settings.upload_dir)
    _, session_factory = bootstrap_database(settings)
    session = session_factory()
    try:
        stats: dict[str, int] = {}
        stats.update(_seed_business_sample_data(session, settings))
        stats.update(_seed_consumer_sample_data(session, settings))
        return stats
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed sample data for the two backend services")
    parser.add_argument("--reset", action="store_true", help="delete existing SQLite DB and uploads before seeding")
    args = parser.parse_args(argv)
    stats = seed_sample_data(reset=args.reset)
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
