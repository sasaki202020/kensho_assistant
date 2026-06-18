from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict
from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from field_assessment_ai.services.common import normalize_text
from field_assessment_ai.services.uploads import save_upload_bytes

from .models import (
    ConfidenceScore,
    ConsumerReport,
    ConsumerItemCheck,
    FlyerCheck,
    OfficialInfo,
    QuoteCheck,
    RefusalPhrase,
    RiskJudgement,
)
from .schemas import (
    CheckCommonRead,
    ConsumerReportRead,
    ConsumerReportResponse,
    ConfidenceScoreRead,
    FlyerCheckCreate,
    FlyerCheckRead,
    FlyerCheckUpdate,
    ImageRefInput,
    ImageUploadResponse,
    ItemCheckCreate,
    ItemCheckRead,
    ItemCheckUpdate,
    MarketLinkGenerateRequest,
    MarketLinkResponse,
    OfficialInfoRead,
    QuoteCheckCreate,
    QuoteCheckRead,
    QuoteCheckUpdate,
    RiskJudgementGenerateRequest,
    RiskJudgementGenerateResponse,
    RiskJudgementRead,
)
from .services.common import (
    CHECK_TYPE_LABELS,
    CONSUMER_DISCLAIMER,
    CONSUMER_HOTLINE_NOTICE,
    build_consumer_market_links,
    build_consumer_market_query,
    unique_texts,
)
from .services.consumer_flyer_check_service import build_flyer_check_defaults
from .services.consumer_item_check_service import build_item_check_defaults
from .services.consumer_quote_check_service import build_quote_check_defaults
from .services.consumer_report_service import build_consumer_report_payload
from .services.consumer_risk_judgement_service import build_risk_judgement_context
from .services.official_info_service import ensure_official_info_seeded
from .services.refusal_phrase_service import ensure_refusal_phrases_seeded

router = APIRouter(tags=["consumer-check"])


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _settings(request: Request):
    return request.app.state.settings


def _ensure_reference_data(session: Session) -> None:
    ensure_official_info_seeded(session)
    ensure_refusal_phrases_seeded(session)


def _check_model(check_type: str):
    normalized = _require_check_type(check_type)
    return {
        "flyer": FlyerCheck,
        "item": ConsumerItemCheck,
        "quote": QuoteCheck,
    }[normalized]


def _check_read_model(check_type: str):
    normalized = _require_check_type(check_type)
    return {
        "flyer": FlyerCheckRead,
        "item": ItemCheckRead,
        "quote": QuoteCheckRead,
    }[normalized]


def _require_check_type(check_type: str) -> str:
    normalized = normalize_text(check_type).lower()
    if normalized not in {"flyer", "item", "quote"}:
        raise HTTPException(status_code=400, detail="check_type は flyer / item / quote のいずれかを指定してください")
    return normalized


def _input_payload_from_row(check_type: str, row: Any) -> dict[str, Any]:
    normalized = _require_check_type(check_type)
    image_refs = [dict(image_ref) for image_ref in list(getattr(row, "image_refs_json", []) or [])]
    if normalized == "flyer":
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
            "image_refs": image_refs,
        }
    if normalized == "quote":
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
            "image_refs": image_refs,
        }
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
        "image_refs": image_refs,
    }


def _confidence_read_from_row(row: ConfidenceScore) -> ConfidenceScoreRead:
    return ConfidenceScoreRead.model_validate(
        {
            "id": row.id,
            "check_type": row.check_type,
            "check_id": row.check_id,
            "score_value": row.score_value,
            "score_label": row.score_label,
            "reason": row.reason,
            "factors": list(row.factors_json or []),
            "check_snapshot": dict(row.check_snapshot_json or {}),
            "created_at": row.created_at,
        }
    )


def _official_info_read_from_row(row: OfficialInfo) -> OfficialInfoRead:
    return OfficialInfoRead.model_validate(
        {
            "id": row.id,
            "category": row.category,
            "title": row.title,
            "summary": row.summary,
            "content": row.content,
            "reference_links": list(row.reference_links_json or []),
            "caution_level": row.caution_level,
        }
    )


def _risk_read_from_row(session: Session, row: RiskJudgement) -> RiskJudgementRead:
    confidence = session.get(ConfidenceScore, row.confidence_score_id) if row.confidence_score_id else None
    official_infos = []
    if row.official_info_ids_json:
        official_infos_stmt = select(OfficialInfo).where(OfficialInfo.id.in_(list(row.official_info_ids_json)))
        official_infos_by_id = {info.id: info for info in session.scalars(official_infos_stmt).all()}
        for info_id in row.official_info_ids_json:
            info = official_infos_by_id.get(info_id)
            if info is not None:
                official_infos.append(_official_info_read_from_row(info))
    return RiskJudgementRead.model_validate(
        {
            "id": row.id,
            "check_type": row.check_type,
            "check_id": row.check_id,
            "judgement_result": row.judgement_result,
            "reason": row.reason,
            "missing_info": list(row.missing_info_json or []),
            "next_actions": list(row.next_actions_json or []),
            "official_info_ids": list(row.official_info_ids_json or []),
            "reference_links": list(row.reference_links_json or []),
            "confidence_score_id": row.confidence_score_id,
            "refusal_phrase": row.refusal_phrase,
            "caution_notes": list(row.caution_notes_json or []),
            "market_links": dict(row.market_links_json or {}),
            "check_snapshot": dict(row.check_snapshot_json or {}),
            "created_at": row.created_at,
            "confidence_score": _confidence_read_from_row(confidence) if confidence else None,
            "official_infos": official_infos,
        }
    )


def _report_read_from_row(row: ConsumerReport) -> ConsumerReportRead:
    return ConsumerReportRead.model_validate(
        {
            "id": row.id,
            "check_type": row.check_type,
            "check_id": row.check_id,
            "title": row.title,
            "format": row.format,
            "summary": row.summary,
            "content_json": dict(row.content_json or {}),
            "content_html": row.content_html,
            "disclaimer": row.disclaimer,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _risk_context_from_read(risk_read: RiskJudgementRead) -> dict[str, Any]:
    return {
        "check_type": risk_read.check_type,
        "judgement_result": risk_read.judgement_result,
        "reason": risk_read.reason,
        "missing_info": list(risk_read.missing_info or []),
        "next_actions": list(risk_read.next_actions or []),
        "official_infos": [info.model_dump() for info in list(risk_read.official_infos or [])],
        "reference_links": list(risk_read.reference_links or []),
        "confidence_score": risk_read.confidence_score.score_value if risk_read.confidence_score else 0,
        "confidence_label": risk_read.confidence_score.score_label if risk_read.confidence_score else "",
        "refusal_phrase": risk_read.refusal_phrase,
        "caution_notes": list(risk_read.caution_notes or []),
        "market_links": dict(risk_read.market_links or {}),
        "hotline_notice": CONSUMER_HOTLINE_NOTICE,
        "disclaimer": CONSUMER_DISCLAIMER,
        "analysis": None,
        "query": None,
        "check_points": list((risk_read.check_snapshot or {}).get("check_points") or []),
        "extra_photo_requests": list((risk_read.check_snapshot or {}).get("extra_photo_requests") or []),
    }


def _append_image_ref(row: Any, image_ref: dict[str, Any]) -> None:
    refs = list(row.image_refs_json or [])
    refs.append(image_ref)
    row.image_refs_json = refs


def _store_image_ref(
    request: Request,
    *,
    check_type: str,
    check_id: int,
    file: UploadFile,
    caption: str | None,
    sort_order: int,
) -> ImageUploadResponse:
    settings = _settings(request)
    contents = file.file.read()
    if isinstance(contents, str):
        contents = contents.encode("utf-8")
    saved = save_upload_bytes(
        settings.upload_dir,
        relative_dir=f"consumer/{check_type}/{check_id}",
        original_filename=file.filename or "upload.bin",
        contents=contents,
        mime_type=file.content_type,
        prefix=f"{check_type}_{check_id}",
    )
    payload = ImageUploadResponse.model_validate(
        {
            **asdict(saved),
            "caption": caption,
            "sort_order": sort_order,
            "check_type": check_type,
            "check_id": check_id,
        }
    )
    return payload


def _persist_generated_risk(session: Session, check_type: str, check_id: int, risk_context: dict[str, Any]) -> RiskJudgementRead:
    confidence = ConfidenceScore(
        check_type=check_type,
        check_id=check_id,
        score_value=int(risk_context.get("confidence_score") or 0),
        score_label=risk_context.get("confidence_label"),
        reason=risk_context.get("reason"),
        factors_json=list(risk_context.get("caution_notes") or []),
        check_snapshot_json=asdict(risk_context.get("analysis")) if risk_context.get("analysis") else {},
    )
    session.add(confidence)
    session.commit()
    session.refresh(confidence)

    judgement = RiskJudgement(
        check_type=check_type,
        check_id=check_id,
        judgement_result=risk_context.get("judgement_result") or "確認推奨",
        reason=risk_context.get("reason"),
        missing_info_json=list(risk_context.get("missing_info") or []),
        next_actions_json=list(risk_context.get("next_actions") or []),
        official_info_ids_json=[int(info.get("id")) for info in risk_context.get("official_infos") or [] if info.get("id") is not None],
        reference_links_json=list(risk_context.get("reference_links") or []),
        confidence_score_id=confidence.id,
        refusal_phrase=risk_context.get("refusal_phrase"),
        caution_notes_json=list(risk_context.get("caution_notes") or []),
        market_links_json=dict(risk_context.get("market_links") or {}),
        check_snapshot_json={
            "query": risk_context.get("query"),
            "analysis": asdict(risk_context.get("analysis")) if risk_context.get("analysis") else {},
            "check_points": list(risk_context.get("check_points") or []),
            "extra_photo_requests": list(risk_context.get("extra_photo_requests") or []),
        },
    )
    session.add(judgement)
    session.commit()
    session.refresh(judgement)

    check = session.get(_check_model(check_type), check_id)
    if check is not None:
        check.judgement_result = judgement.judgement_result
        check.reason = judgement.reason
        check.missing_info_json = list(judgement.missing_info_json or [])
        check.next_actions_json = list(judgement.next_actions_json or [])
        check.official_info_ids_json = list(judgement.official_info_ids_json or [])
        check.reference_links_json = list(judgement.reference_links_json or [])
        check.confidence_score_value = confidence.score_value
        check.confidence_label = confidence.score_label
        check.refusal_phrase = judgement.refusal_phrase
        check.note_text = " / ".join(judgement.caution_notes_json[:3]) if judgement.caution_notes_json else CONSUMER_DISCLAIMER
        check.market_links_json = dict(judgement.market_links_json or {})
        check.market_query = risk_context.get("query")
        check.caution_points_json = list(judgement.caution_notes_json or [])
        check.check_points_json = list(risk_context.get("check_points") or [])
        check.photo_requests_json = list(risk_context.get("extra_photo_requests") or [])
        check.latest_confidence_score_id = confidence.id
        check.latest_risk_judgement_id = judgement.id
        session.commit()

    official_infos = [info for info in risk_context.get("official_infos") or []]
    return RiskJudgementRead.model_validate(
        {
            "id": judgement.id,
            "check_type": judgement.check_type,
            "check_id": judgement.check_id,
            "judgement_result": judgement.judgement_result,
            "reason": judgement.reason,
            "missing_info": list(judgement.missing_info_json or []),
            "next_actions": list(judgement.next_actions_json or []),
            "official_info_ids": list(judgement.official_info_ids_json or []),
            "reference_links": list(judgement.reference_links_json or []),
            "confidence_score_id": judgement.confidence_score_id,
            "refusal_phrase": judgement.refusal_phrase,
            "caution_notes": list(judgement.caution_notes_json or []),
            "market_links": dict(judgement.market_links_json or {}),
            "check_snapshot": dict(judgement.check_snapshot_json or {}),
            "created_at": judgement.created_at,
            "confidence_score": _confidence_read_from_row(confidence),
            "official_infos": [
                _official_info_read_from_row(info) for info in session.scalars(
                    select(OfficialInfo).where(OfficialInfo.id.in_(list(judgement.official_info_ids_json or [0])))
                ).all()
            ]
            if judgement.official_info_ids_json
            else [],
        }
    )


def _attach_related_payloads(session: Session, check_type: str, row: Any) -> dict[str, Any]:
    payload = _input_payload_from_row(check_type, row)
    latest_risk = session.get(RiskJudgement, row.latest_risk_judgement_id) if row.latest_risk_judgement_id else None
    latest_confidence = session.get(ConfidenceScore, row.latest_confidence_score_id) if row.latest_confidence_score_id else None
    latest_report = session.get(ConsumerReport, row.latest_report_id) if row.latest_report_id else None
    official_infos: list[OfficialInfoRead] = []
    if row.official_info_ids_json:
        info_stmt = select(OfficialInfo).where(OfficialInfo.id.in_(list(row.official_info_ids_json)))
        infos_by_id = {info.id: info for info in session.scalars(info_stmt).all()}
        for info_id in row.official_info_ids_json:
            info = infos_by_id.get(info_id)
            if info is not None:
                official_infos.append(_official_info_read_from_row(info))

    base: dict[str, Any] = {
        **payload,
        "id": row.id,
        "image_refs": [ImageRefInput.model_validate(value) for value in list(row.image_refs_json or [])],
        "market_query": row.market_query,
        "market_links": dict(row.market_links_json or {}),
        "caution_points": list(row.caution_points_json or []),
        "check_points": list(row.check_points_json or []),
        "photo_requests": list(row.photo_requests_json or []),
        "judgement_result": row.judgement_result,
        "reason": row.reason,
        "missing_info": list(row.missing_info_json or []),
        "next_actions": list(row.next_actions_json or []),
        "official_info_ids": list(row.official_info_ids_json or []),
        "reference_links": list(row.reference_links_json or []),
        "confidence_score_value": row.confidence_score_value,
        "confidence_label": row.confidence_label,
        "refusal_phrase": row.refusal_phrase,
        "note_text": row.note_text,
        "latest_risk_judgement_id": row.latest_risk_judgement_id,
        "latest_confidence_score_id": row.latest_confidence_score_id,
        "latest_report_id": row.latest_report_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "official_infos": official_infos,
        "latest_risk_judgement": _risk_read_from_row(session, latest_risk) if latest_risk else None,
        "latest_confidence_score": _confidence_read_from_row(latest_confidence) if latest_confidence else None,
        "latest_report": _report_read_from_row(latest_report) if latest_report else None,
    }
    return base


def _ensure_check(session: Session, check_type: str, check_id: int):
    model = _check_model(check_type)
    row = session.get(model, check_id)
    if row is None:
        raise HTTPException(status_code=404, detail="チェックが見つかりません")
    return row


def _delete_check_files(request: Request, image_refs: list[dict[str, Any]]) -> None:
    settings = _settings(request)
    for image_ref in image_refs:
        relative_path = image_ref.get("relative_path")
        if not relative_path:
            continue
        file_path = settings.upload_dir / str(relative_path)
        if file_path.exists():
            file_path.unlink()


def _response_model_for_type(check_type: str):
    normalized = _require_check_type(check_type)
    return {
        "flyer": FlyerCheckRead,
        "item": ItemCheckRead,
        "quote": QuoteCheckRead,
    }[normalized]


def _build_check_response(session: Session, check_type: str, row: Any):
    response_model = _response_model_for_type(check_type)
    return response_model.model_validate(_attach_related_payloads(session, check_type, row))


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    settings = _settings(request)
    return {
        "status": "ok",
        "service": settings.app_name,
        "api_prefix": settings.api_prefix,
    }


@router.post("/images/upload", response_model=ImageUploadResponse, status_code=201)
async def upload_image(
    request: Request,
    check_type: str = Form(...),
    check_id: int = Form(...),
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
) -> ImageUploadResponse:
    normalized = _require_check_type(check_type)
    check = _ensure_check(db, normalized, check_id)
    saved = _store_image_ref(request, check_type=normalized, check_id=check_id, file=file, caption=caption, sort_order=sort_order)
    _append_image_ref(check, saved.model_dump())
    db.commit()
    return saved


def _create_check(
    request: Request,
    db: Session,
    check_type: str,
    payload: dict[str, Any],
):
    normalized = _require_check_type(check_type)
    if normalized == "flyer":
        data = build_flyer_check_defaults(payload)
        row = FlyerCheck(**data)
    elif normalized == "quote":
        data = build_quote_check_defaults(payload)
        row = QuoteCheck(**data)
    else:
        data = build_item_check_defaults(payload)
        row = ConsumerItemCheck(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    risk_context = build_risk_judgement_context(
        normalized,
        _input_payload_from_row(normalized, row),
        db.scalars(select(OfficialInfo)).all(),
        db.scalars(select(RefusalPhrase)).all(),
    )
    _persist_generated_risk(db, normalized, row.id, risk_context)
    db.refresh(row)
    return _build_check_response(db, normalized, row)


def _update_check(
    request: Request,
    db: Session,
    check_type: str,
    check_id: int,
    payload: dict[str, Any],
):
    normalized = _require_check_type(check_type)
    row = _ensure_check(db, normalized, check_id)
    merged_payload = _input_payload_from_row(normalized, row)
    merged_payload.update(payload)
    if normalized == "flyer":
        updates = build_flyer_check_defaults(merged_payload)
    elif normalized == "quote":
        updates = build_quote_check_defaults(merged_payload)
    else:
        updates = build_item_check_defaults(merged_payload)
    for key, value in updates.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    risk_context = build_risk_judgement_context(
        normalized,
        _input_payload_from_row(normalized, row),
        db.scalars(select(OfficialInfo)).all(),
        db.scalars(select(RefusalPhrase)).all(),
    )
    _persist_generated_risk(db, normalized, row.id, risk_context)
    db.refresh(row)
    return _build_check_response(db, normalized, row)


@router.post("/flyer-checks", response_model=FlyerCheckRead, status_code=201)
def create_flyer_check(payload: FlyerCheckCreate, request: Request, db: Session = Depends(get_db)) -> FlyerCheckRead:
    _ensure_reference_data(db)
    return _create_check(request, db, "flyer", payload.model_dump())


@router.get("/flyer-checks", response_model=list[FlyerCheckRead])
def list_flyer_checks(db: Session = Depends(get_db), skip: int = 0, limit: int = 100) -> list[FlyerCheckRead]:
    stmt = select(FlyerCheck).order_by(desc(FlyerCheck.created_at), desc(FlyerCheck.id)).offset(skip).limit(limit)
    rows = db.scalars(stmt).all()
    return [_build_check_response(db, "flyer", row) for row in rows]


@router.get("/flyer-checks/{check_id}", response_model=FlyerCheckRead)
def get_flyer_check(check_id: int, db: Session = Depends(get_db)) -> FlyerCheckRead:
    row = _ensure_check(db, "flyer", check_id)
    return _build_check_response(db, "flyer", row)


@router.patch("/flyer-checks/{check_id}", response_model=FlyerCheckRead)
def update_flyer_check(check_id: int, payload: FlyerCheckUpdate, request: Request, db: Session = Depends(get_db)) -> FlyerCheckRead:
    _ensure_reference_data(db)
    return _update_check(request, db, "flyer", check_id, payload.model_dump(exclude_unset=True))


@router.delete("/flyer-checks/{check_id}")
def delete_flyer_check(check_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = _ensure_check(db, "flyer", check_id)
    _delete_check_files(request, list(row.image_refs_json or []))
    db.query(RiskJudgement).filter(RiskJudgement.check_type == "flyer", RiskJudgement.check_id == check_id).delete()
    db.query(ConfidenceScore).filter(ConfidenceScore.check_type == "flyer", ConfidenceScore.check_id == check_id).delete()
    db.query(ConsumerReport).filter(ConsumerReport.check_type == "flyer", ConsumerReport.check_id == check_id).delete()
    db.delete(row)
    db.commit()
    return {"deleted": True, "check_type": "flyer", "check_id": check_id}


@router.post("/item-checks", response_model=ItemCheckRead, status_code=201)
def create_item_check(payload: ItemCheckCreate, request: Request, db: Session = Depends(get_db)) -> ItemCheckRead:
    _ensure_reference_data(db)
    return _create_check(request, db, "item", payload.model_dump())


@router.get("/item-checks", response_model=list[ItemCheckRead])
def list_item_checks(db: Session = Depends(get_db), skip: int = 0, limit: int = 100) -> list[ItemCheckRead]:
    stmt = select(ConsumerItemCheck).order_by(desc(ConsumerItemCheck.created_at), desc(ConsumerItemCheck.id)).offset(skip).limit(limit)
    rows = db.scalars(stmt).all()
    return [_build_check_response(db, "item", row) for row in rows]


@router.get("/item-checks/{check_id}", response_model=ItemCheckRead)
def get_item_check(check_id: int, db: Session = Depends(get_db)) -> ItemCheckRead:
    row = _ensure_check(db, "item", check_id)
    return _build_check_response(db, "item", row)


@router.patch("/item-checks/{check_id}", response_model=ItemCheckRead)
def update_item_check(check_id: int, payload: ItemCheckUpdate, request: Request, db: Session = Depends(get_db)) -> ItemCheckRead:
    _ensure_reference_data(db)
    return _update_check(request, db, "item", check_id, payload.model_dump(exclude_unset=True))


@router.delete("/item-checks/{check_id}")
def delete_item_check(check_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = _ensure_check(db, "item", check_id)
    _delete_check_files(request, list(row.image_refs_json or []))
    db.query(RiskJudgement).filter(RiskJudgement.check_type == "item", RiskJudgement.check_id == check_id).delete()
    db.query(ConfidenceScore).filter(ConfidenceScore.check_type == "item", ConfidenceScore.check_id == check_id).delete()
    db.query(ConsumerReport).filter(ConsumerReport.check_type == "item", ConsumerReport.check_id == check_id).delete()
    db.delete(row)
    db.commit()
    return {"deleted": True, "check_type": "item", "check_id": check_id}


@router.post("/quote-checks", response_model=QuoteCheckRead, status_code=201)
def create_quote_check(payload: QuoteCheckCreate, request: Request, db: Session = Depends(get_db)) -> QuoteCheckRead:
    _ensure_reference_data(db)
    return _create_check(request, db, "quote", payload.model_dump())


@router.get("/quote-checks", response_model=list[QuoteCheckRead])
def list_quote_checks(db: Session = Depends(get_db), skip: int = 0, limit: int = 100) -> list[QuoteCheckRead]:
    stmt = select(QuoteCheck).order_by(desc(QuoteCheck.created_at), desc(QuoteCheck.id)).offset(skip).limit(limit)
    rows = db.scalars(stmt).all()
    return [_build_check_response(db, "quote", row) for row in rows]


@router.get("/quote-checks/{check_id}", response_model=QuoteCheckRead)
def get_quote_check(check_id: int, db: Session = Depends(get_db)) -> QuoteCheckRead:
    row = _ensure_check(db, "quote", check_id)
    return _build_check_response(db, "quote", row)


@router.patch("/quote-checks/{check_id}", response_model=QuoteCheckRead)
def update_quote_check(check_id: int, payload: QuoteCheckUpdate, request: Request, db: Session = Depends(get_db)) -> QuoteCheckRead:
    _ensure_reference_data(db)
    return _update_check(request, db, "quote", check_id, payload.model_dump(exclude_unset=True))


@router.delete("/quote-checks/{check_id}")
def delete_quote_check(check_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = _ensure_check(db, "quote", check_id)
    _delete_check_files(request, list(row.image_refs_json or []))
    db.query(RiskJudgement).filter(RiskJudgement.check_type == "quote", RiskJudgement.check_id == check_id).delete()
    db.query(ConfidenceScore).filter(ConfidenceScore.check_type == "quote", ConfidenceScore.check_id == check_id).delete()
    db.query(ConsumerReport).filter(ConsumerReport.check_type == "quote", ConsumerReport.check_id == check_id).delete()
    db.delete(row)
    db.commit()
    return {"deleted": True, "check_type": "quote", "check_id": check_id}


@router.post("/market-links/generate", response_model=MarketLinkResponse)
def generate_market_links(payload: MarketLinkGenerateRequest, db: Session = Depends(get_db)) -> MarketLinkResponse:
    query = payload.product_name or ""
    if payload.check_id is not None and payload.check_type:
        normalized_check_type = _require_check_type(payload.check_type)
        row = _ensure_check(db, normalized_check_type, payload.check_id)
        if normalized_check_type == "flyer":
            query = build_consumer_market_query(row.company_name, row.flyer_text, row.inducement_text, row.memo, payload.extra_keywords)
        elif normalized_check_type == "quote":
            query = build_consumer_market_query("不用品回収", row.memo, row.additional_charge_conditions, payload.category, payload.extra_keywords)
        else:
            query = build_consumer_market_query(row.item_name, row.brand, row.model_number, row.item_category, payload.extra_keywords)
    else:
        query = build_consumer_market_query(payload.product_name, payload.brand, payload.model_number, payload.category, payload.extra_keywords)
    links = build_consumer_market_links(query or "売る前チェック 相場")
    notes = [
        "検索URL生成のみ。自動出品・自動購入・自動ログイン・スクレイピングは実行しない。",
        "サイト仕様変更に備えて、リンク先は都度確認すること。",
    ]
    return MarketLinkResponse(query=query, search_links=links, notes=notes)


@router.post("/risk-judgements/generate", response_model=RiskJudgementGenerateResponse)
def generate_risk_judgement(payload: RiskJudgementGenerateRequest, request: Request, db: Session = Depends(get_db)) -> RiskJudgementGenerateResponse:
    _ensure_reference_data(db)
    normalized = _require_check_type(payload.check_type)
    row = _ensure_check(db, normalized, payload.check_id)
    risk_context = build_risk_judgement_context(
        normalized,
        _input_payload_from_row(normalized, row),
        db.scalars(select(OfficialInfo)).all(),
        db.scalars(select(RefusalPhrase)).all(),
    )
    risk_read = _persist_generated_risk(db, normalized, row.id, risk_context)
    db.refresh(row)
    return RiskJudgementGenerateResponse(
        check_type=normalized,
        check_id=row.id,
        judgement=risk_read,
        check=_build_check_response(db, normalized, row),
        official_infos=risk_read.official_infos,
        market_links=dict(risk_context.get("market_links") or {}),
        hotline_notice=risk_context.get("hotline_notice"),
    )


@router.get("/official-info", response_model=list[OfficialInfoRead])
def list_official_info(db: Session = Depends(get_db), category: str | None = None) -> list[OfficialInfoRead]:
    _ensure_reference_data(db)
    stmt = select(OfficialInfo).order_by(OfficialInfo.category.asc(), OfficialInfo.id.asc())
    if category:
        stmt = stmt.where(OfficialInfo.category == category)
    rows = db.scalars(stmt).all()
    return [_official_info_read_from_row(row) for row in rows]


@router.get("/official-info/{info_id}", response_model=OfficialInfoRead)
def get_official_info(info_id: int, db: Session = Depends(get_db)) -> OfficialInfoRead:
    _ensure_reference_data(db)
    row = db.get(OfficialInfo, info_id)
    if row is None:
        raise HTTPException(status_code=404, detail="公式情報が見つかりません")
    return _official_info_read_from_row(row)


def _load_report_context(check_type: str, check_id: int, db: Session) -> tuple[Any, dict[str, Any], RiskJudgementRead]:
    normalized = _require_check_type(check_type)
    row = _ensure_check(db, normalized, check_id)
    if row.latest_risk_judgement_id:
        risk_row = db.get(RiskJudgement, row.latest_risk_judgement_id)
        risk_read = _risk_read_from_row(db, risk_row) if risk_row else None
    else:
        risk_read = None
    if risk_read is None:
        risk_context = build_risk_judgement_context(
            normalized,
            _input_payload_from_row(normalized, row),
            db.scalars(select(OfficialInfo)).all(),
            db.scalars(select(RefusalPhrase)).all(),
        )
        risk_read = _persist_generated_risk(db, normalized, row.id, risk_context)
    check_payload = _attach_related_payloads(db, normalized, row)
    return row, check_payload, risk_read


@router.get("/reports/{check_type}/{check_id}", response_model=ConsumerReportResponse)
def get_report(check_type: str, check_id: int, request: Request, db: Session = Depends(get_db)) -> ConsumerReportResponse:
    _ensure_reference_data(db)
    normalized = _require_check_type(check_type)
    row, check_payload, risk_read = _load_report_context(normalized, check_id, db)
    report_risk_context = _risk_context_from_read(risk_read)
    report_payload = build_consumer_report_payload(
        normalized,
        check_payload,
        report_risk_context,
        title=f"{CHECK_TYPE_LABELS.get(normalized, normalized)}のチェックレポート",
        format="json",
    )
    report = ConsumerReport(
        check_type=normalized,
        check_id=row.id,
        title=report_payload["title"],
        format="json",
        summary=report_payload["summary_text"],
        content_json=jsonable_encoder(report_payload["content_json"]),
        content_html=report_payload["content_html"],
        disclaimer=report_payload["content_json"].get("disclaimer"),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    row.latest_report_id = report.id
    db.commit()
    return ConsumerReportResponse(
        report=_report_read_from_row(report),
        html=report.content_html,
        content_json=report_payload["content_json"],
        legal_notices=report_payload["legal_notices"],
    )


@router.get("/reports/{check_type}/{check_id}/html", response_class=HTMLResponse)
def get_report_html(check_type: str, check_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    report = get_report(check_type, check_id, request=request, db=db)
    html = report.html or "<html><body><p>HTMLはありません</p></body></html>"
    return HTMLResponse(content=html)
