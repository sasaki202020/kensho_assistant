from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from .models import Estimate, Item, ItemImage, Job, MarketMemo, Report
from .schemas import (
    AnalysisRequest,
    AnalysisResponse,
    CalculationOptions,
    EstimateRead,
    EstimateResponse,
    ImageRead,
    ItemCreate,
    ItemDetailRead,
    ItemEstimateResponse,
    ItemRead,
    ItemUpdate,
    JobCreate,
    JobDetailRead,
    JobEstimateResponse,
    JobRead,
    JobUpdate,
    MarketMemoRead,
    MarketMemoUpsertRequest,
    ReportDraftRequest,
    ReportRead,
    ReportResponse,
    SafetyNotice,
    SearchLinkRequest,
    SearchLinkResponse,
)
from .services.analysis import MockVisionAnalysisService
from .services.common import LEGAL_DISCLAIMER, build_legal_notices, sanitize_filename
from .services.market import build_market_memo_defaults, build_market_query, build_search_links
from .services.reporting import build_report_payload
from .services.scoring import build_item_estimate_payload, build_job_estimate_payload
from .services.uploads import save_upload_bytes

router = APIRouter(tags=["field-assessment"])


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _settings(request: Request):
    return request.app.state.settings


def _analysis_service(request: Request) -> MockVisionAnalysisService:
    return request.app.state.analysis_service


def _item_payload(item: Item, *, image_count: int | None = None) -> dict[str, Any]:
    if image_count is None:
        image_count = len(item.images)
    return {
        "id": item.id,
        "job_id": item.job_id,
        "name": item.name,
        "category": item.category,
        "brand": item.brand,
        "model_number": item.model_number,
        "condition_note": item.condition_note,
        "quantity": item.quantity,
        "location_note": item.location_note,
        "memo": item.memo,
        "status": item.status,
        "safety_flags": list(item.safety_flags_json or []),
        "image_count": image_count,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _job_payload(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "title": job.title,
        "customer_name": job.customer_name,
        "address": job.address,
        "contact_name": job.contact_name,
        "contact_phone": job.contact_phone,
        "status": job.status,
        "memo": job.memo,
        "safety_notes": job.safety_notes,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _market_memo_payload(memo: MarketMemo) -> dict[str, Any]:
    return {
        "id": memo.id,
        "item_id": memo.item_id,
        "lowest_price": memo.lowest_price,
        "median_price": memo.median_price,
        "highest_price": memo.highest_price,
        "sold_count": memo.sold_count,
        "purchase_price": memo.purchase_price,
        "shipping_fee": memo.shipping_fee,
        "marketplace_fee": memo.marketplace_fee,
        "packing_fee": memo.packing_fee,
        "disposal_fee_memo": memo.disposal_fee_memo,
        "internal_memo": memo.internal_memo,
        "search_keyword": memo.search_keyword,
        "source_urls": list(memo.source_urls or []),
        "created_at": memo.created_at,
        "updated_at": memo.updated_at,
    }


def _estimate_payload(estimate: Estimate) -> dict[str, Any]:
    return {
        "id": estimate.id,
        "scope_type": estimate.scope_type,
        "job_id": estimate.job_id,
        "item_id": estimate.item_id,
        "resale_estimate_min": estimate.resale_estimate_min,
        "resale_estimate_max": estimate.resale_estimate_max,
        "purchase_estimate": estimate.purchase_estimate,
        "disposal_fee_estimate": estimate.disposal_fee_estimate,
        "work_fee_estimate": estimate.work_fee_estimate,
        "discount_possible_amount": estimate.discount_possible_amount,
        "final_estimate_guide": estimate.final_estimate_guide,
        "sale_value_score": estimate.sale_value_score,
        "rank_candidate": estimate.rank_candidate,
        "details": dict(estimate.details_json or {}),
        "created_at": estimate.created_at,
        "updated_at": estimate.updated_at,
    }


def _report_payload(report: Report) -> dict[str, Any]:
    return {
        "id": report.id,
        "job_id": report.job_id,
        "title": report.title,
        "format": report.format,
        "summary": report.summary,
        "content_json": dict(report.content_json or {}),
        "content_html": report.content_html,
        "disclaimer": report.disclaimer,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


def _image_payload(image: ItemImage) -> dict[str, Any]:
    return {
        "id": image.id,
        "item_id": image.item_id,
        "original_filename": image.original_filename,
        "stored_filename": image.stored_filename,
        "relative_path": image.relative_path,
        "public_url": image.public_url,
        "thumbnail_url": image.thumbnail_url,
        "mime_type": image.mime_type,
        "file_size_bytes": image.file_size_bytes,
        "sort_order": image.sort_order,
        "caption": image.caption,
        "created_at": image.created_at,
    }


def _analysis_payload_to_response(payload: dict[str, Any]) -> AnalysisResponse:
    return AnalysisResponse.model_validate(payload)


def _estimate_to_response(payload: dict[str, Any]) -> EstimateRead:
    return EstimateRead.model_validate(payload)


def _market_memo_to_response(payload: dict[str, Any]) -> MarketMemoRead:
    return MarketMemoRead.model_validate(payload)


def _image_to_response(payload: dict[str, Any]) -> ImageRead:
    return ImageRead.model_validate(payload)


def _item_to_read(item: Item) -> ItemRead:
    return ItemRead.model_validate(_item_payload(item, image_count=len(item.images)))


def _job_to_read(job: Job) -> JobRead:
    return JobRead.model_validate(
        {
            **_job_payload(job),
            "item_count": len(job.items),
        }
    )


def _flags_to_notices(flags: list[str]) -> list[dict[str, Any]]:
    notices: list[dict[str, Any]] = []
    for flag in flags:
        notices.append(
            {
                "code": f"ITEM_FLAG_{sanitize_filename(flag).upper()}",
                "severity": "warning",
                "title": flag,
                "message": f"商品フラグ: {flag}",
                "category": None,
                "legal_hint": "現場確認時にフラグ内容を再確認すること。",
            }
        )
    return notices


def _merge_notices(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for notice in group:
            code = str(notice.get("code") or notice.get("title") or len(merged))
            if code in seen:
                continue
            seen.add(code)
            merged.append(notice)
    return merged


def _latest_estimate(session: Session, *, item_id: int | None = None, job_id: int | None = None) -> Estimate | None:
    stmt = select(Estimate).order_by(desc(Estimate.created_at), desc(Estimate.id))
    if item_id is not None:
        stmt = stmt.where(Estimate.scope_type == "item", Estimate.item_id == item_id)
    if job_id is not None:
        stmt = stmt.where(Estimate.scope_type == "job", Estimate.job_id == job_id)
    return session.scalar(stmt.limit(1))


def _ensure_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="案件が見つかりません")
    return job


def _ensure_item(session: Session, item_id: int) -> Item:
    stmt = (
        select(Item)
        .options(selectinload(Item.images), selectinload(Item.market_memo), selectinload(Item.job))
        .where(Item.id == item_id)
    )
    item = session.scalar(stmt)
    if item is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    return item


def _ensure_job_with_items(session: Session, job_id: int) -> Job:
    stmt = (
        select(Job)
        .options(selectinload(Job.items).selectinload(Item.images), selectinload(Job.items).selectinload(Item.market_memo))
        .where(Job.id == job_id)
    )
    job = session.scalar(stmt)
    if job is None:
        raise HTTPException(status_code=404, detail="案件が見つかりません")
    return job


def _build_item_snapshot(request: Request, item: Item) -> dict[str, Any]:
    analysis_service = _analysis_service(request)
    item_payload = _item_payload(item, image_count=len(item.images))
    analysis = analysis_service.analyze(item_payload)
    safety_notices = _merge_notices(
        analysis.get("legal_notices", []),
        _flags_to_notices(item_payload.get("safety_flags", [])),
    )
    return {
        "item": item_payload,
        "analysis": analysis,
        "market_memo": _market_memo_payload(item.market_memo) if item.market_memo else None,
        "safety_notices": safety_notices,
    }


def _persist_estimate(session: Session, estimate_payload: dict[str, Any]) -> Estimate:
    estimate = Estimate(
        scope_type=estimate_payload["scope_type"],
        job_id=estimate_payload.get("job_id"),
        item_id=estimate_payload.get("item_id"),
        resale_estimate_min=estimate_payload.get("resale_estimate_min"),
        resale_estimate_max=estimate_payload.get("resale_estimate_max"),
        purchase_estimate=estimate_payload.get("purchase_estimate"),
        disposal_fee_estimate=estimate_payload.get("disposal_fee_estimate"),
        work_fee_estimate=estimate_payload.get("work_fee_estimate"),
        discount_possible_amount=estimate_payload.get("discount_possible_amount"),
        final_estimate_guide=estimate_payload.get("final_estimate_guide"),
        sale_value_score=estimate_payload.get("sale_value_score"),
        rank_candidate=estimate_payload.get("rank_candidate"),
        details_json=estimate_payload.get("details_json") or {},
    )
    session.add(estimate)
    session.commit()
    session.refresh(estimate)
    return estimate


def _build_item_estimate_and_persist(
    request: Request,
    session: Session,
    item: Item,
    *,
    options: CalculationOptions | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Estimate]:
    analysis_service = _analysis_service(request)
    item_payload = _item_payload(item, image_count=len(item.images))
    analysis = analysis_service.analyze(item_payload)
    market_memo = item.market_memo
    if market_memo is None:
        market_memo_payload = build_market_memo_defaults(item_payload, analysis)
    else:
        market_memo_payload = _market_memo_payload(market_memo)
    estimate_payload = build_item_estimate_payload(
        item_payload,
        market_memo=market_memo_payload,
        analysis=analysis,
        options=options.model_dump() if options else None,
    )
    estimate = _persist_estimate(session, estimate_payload)
    return item_payload, analysis, market_memo_payload, estimate


def _build_job_estimate_and_persist(
    request: Request,
    session: Session,
    job: Job,
    *,
    options: CalculationOptions | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], Estimate]:
    item_estimates_payload: list[dict[str, Any]] = []
    item_snapshots: list[dict[str, Any]] = []
    for item in job.items:
        item_payload, analysis, market_memo_payload, estimate = _build_item_estimate_and_persist(
            request,
            session,
            item,
            options=options,
        )
        estimate_payload = _estimate_payload(estimate)
        estimate_payload["analysis"] = analysis
        estimate_payload["market_memo"] = market_memo_payload
        estimate_payload["item"] = item_payload
        item_estimates_payload.append(estimate_payload)
        item_snapshots.append(
            {
                "item": item_payload,
                "analysis": analysis,
                "market_memo": market_memo_payload,
                "estimate": estimate_payload,
                "safety_notices": _merge_notices(
                    analysis.get("legal_notices", []),
                    _flags_to_notices(item_payload.get("safety_flags", [])),
                ),
            }
        )
    job_payload = _job_payload(job)
    job_estimate_payload = build_job_estimate_payload(job_payload, item_estimates_payload, options=options.model_dump() if options else None)
    job_estimate = _persist_estimate(session, job_estimate_payload)
    return job_payload, item_snapshots, job_estimate_payload, job_estimate


@router.get("/")
def root(request: Request) -> dict[str, Any]:
    settings = _settings(request)
    return {
        "service": settings.app_name,
        "version": settings.version,
        "status": "ok",
        "api_prefix": settings.api_prefix,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "safety": [
            "自動出品なし",
            "自動購入なし",
            "自動入札なし",
            "ログイン情報保存なし",
            "ログイン自動化なし",
            "スクレイピングなし",
            "検索URL生成のみ",
        ],
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    request: Request,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> list[JobRead]:
    stmt = (
        select(Job)
        .options(selectinload(Job.items))
        .order_by(desc(Job.created_at), desc(Job.id))
        .offset(skip)
        .limit(limit)
    )
    jobs = db.scalars(stmt).all()
    return [_job_to_read(job) for job in jobs]


@router.post("/jobs", response_model=JobRead, status_code=201)
def create_job(request: Request, payload: JobCreate, db: Session = Depends(get_db)) -> JobRead:
    job = Job(
        title=payload.title,
        customer_name=payload.customer_name,
        address=payload.address,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        status=payload.status,
        memo=payload.memo,
        safety_notes=payload.safety_notes,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_to_read(job)


@router.get("/jobs/{job_id}", response_model=JobDetailRead)
def get_job(job_id: int, request: Request, db: Session = Depends(get_db)) -> JobDetailRead:
    job = _ensure_job_with_items(db, job_id)
    latest_estimate = _latest_estimate(db, job_id=job.id)
    report_count = db.scalar(select(func.count(Report.id)).where(Report.job_id == job.id)) or 0
    summary = {
        "item_count": len(job.items),
        "linked_item_count": len(job.items),
        "total_quantity": sum(item.quantity for item in job.items),
        "items_with_flags": sum(1 for item in job.items if item.safety_flags_json),
    }
    safety_notices = _merge_notices(
        (
            [
                {
                    "code": "JOB_MEMO",
                    "severity": "info",
                    "title": "案件メモ",
                    "message": job.safety_notes,
                    "category": None,
                    "legal_hint": "案件メモは現場確認用。",
                }
            ]
            if job.safety_notes
            else []
        ),
        build_legal_notices(job.title, None, None),
    )
    payload = {
        **_job_payload(job),
        "item_count": len(job.items),
        "items": [_item_to_read(item) for item in job.items],
        "latest_estimate": _estimate_to_response(_estimate_payload(latest_estimate)) if latest_estimate else None,
        "report_count": report_count,
        "safety_notices": safety_notices,
        "summary": summary,
    }
    return JobDetailRead.model_validate(payload)


@router.patch("/jobs/{job_id}", response_model=JobRead)
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)) -> JobRead:
    job = _ensure_job(db, job_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return _job_to_read(job)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = _ensure_job(db, job_id)
    db.delete(job)
    db.commit()
    return {"deleted": True, "job_id": job_id}


@router.get("/items", response_model=list[ItemRead])
def list_items(
    request: Request,
    db: Session = Depends(get_db),
    job_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[ItemRead]:
    stmt = select(Item).options(selectinload(Item.images), selectinload(Item.market_memo))
    if job_id is not None:
        stmt = stmt.where(Item.job_id == job_id)
    stmt = stmt.order_by(desc(Item.created_at), desc(Item.id)).offset(skip).limit(limit)
    items = db.scalars(stmt).all()
    return [_item_to_read(item) for item in items]


@router.post("/items", response_model=ItemRead, status_code=201)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> ItemRead:
    if payload.job_id is not None:
        _ensure_job(db, payload.job_id)
    item = Item(
        job_id=payload.job_id,
        name=payload.name,
        category=payload.category,
        brand=payload.brand,
        model_number=payload.model_number,
        condition_note=payload.condition_note,
        quantity=max(1, payload.quantity),
        location_note=payload.location_note,
        memo=payload.memo,
        status=payload.status,
        safety_flags_json=list(payload.safety_flags or []),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_to_read(item)


@router.get("/items/{item_id}", response_model=ItemDetailRead)
def get_item(item_id: int, request: Request, db: Session = Depends(get_db)) -> ItemDetailRead:
    item = _ensure_item(db, item_id)
    analysis = _analysis_service(request).analyze(_item_payload(item, image_count=len(item.images)))
    latest_estimate = _latest_estimate(db, item_id=item.id)
    safety_notices = _merge_notices(
        analysis.get("legal_notices", []),
        _flags_to_notices(list(item.safety_flags_json or [])),
    )
    payload = {
        **_item_payload(item, image_count=len(item.images)),
        "images": [_image_to_response(_image_payload(image)) for image in sorted(item.images, key=lambda row: (row.sort_order, row.id))],
        "market_memo": _market_memo_to_response(_market_memo_payload(item.market_memo)) if item.market_memo else None,
        "analysis": _analysis_payload_to_response(analysis),
        "latest_estimate": _estimate_to_response(_estimate_payload(latest_estimate)) if latest_estimate else None,
        "safety_notices": [SafetyNotice.model_validate(notice) for notice in safety_notices],
    }
    return ItemDetailRead.model_validate(payload)


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(item_id: int, payload: ItemUpdate, db: Session = Depends(get_db)) -> ItemRead:
    item = _ensure_item(db, item_id)
    updates = payload.model_dump(exclude_unset=True)
    if "job_id" in updates and updates["job_id"] is not None:
        _ensure_job(db, int(updates["job_id"]))
    for key, value in updates.items():
        if key == "safety_flags":
            item.safety_flags_json = list(value or [])
            continue
        if key == "quantity" and value is not None:
            value = max(1, int(value))
        setattr(item, key if key != "safety_flags" else "safety_flags_json", value)
    db.commit()
    db.refresh(item)
    return _item_to_read(item)


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = _ensure_item(db, item_id)
    db.delete(item)
    db.commit()
    return {"deleted": True, "item_id": item_id}


@router.post("/jobs/{job_id}/items/{item_id}/link", response_model=ItemRead)
def link_item_to_job(job_id: int, item_id: int, db: Session = Depends(get_db)) -> ItemRead:
    job = _ensure_job(db, job_id)
    item = _ensure_item(db, item_id)
    item.job_id = job.id
    db.commit()
    db.refresh(item)
    return _item_to_read(item)


@router.post("/items/{item_id}/images", response_model=ImageRead, status_code=201)
async def upload_item_image(
    item_id: int,
    request: Request,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
) -> ImageRead:
    item = _ensure_item(db, item_id)
    settings = _settings(request)
    contents = await file.read()
    saved = save_upload_bytes(
        settings.upload_dir,
        relative_dir=f"items/{item.id}",
        original_filename=file.filename or "upload.bin",
        contents=contents,
        mime_type=file.content_type,
        prefix=str(item.id),
    )
    image = ItemImage(
        item_id=item.id,
        original_filename=saved.original_filename,
        stored_filename=saved.stored_filename,
        relative_path=saved.relative_path,
        public_url=saved.public_url,
        thumbnail_url=None,
        mime_type=file.content_type,
        file_size_bytes=saved.file_size_bytes,
        sort_order=sort_order,
        caption=caption,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return _image_to_response(_image_payload(image))


@router.get("/items/{item_id}/images", response_model=list[ImageRead])
def list_item_images(item_id: int, db: Session = Depends(get_db)) -> list[ImageRead]:
    item = _ensure_item(db, item_id)
    return [_image_to_response(_image_payload(image)) for image in sorted(item.images, key=lambda row: (row.sort_order, row.id))]


@router.delete("/images/{image_id}")
def delete_image(image_id: int, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    image = db.get(ItemImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="画像が見つかりません")
    file_path = _settings(request).upload_dir / image.relative_path
    if file_path.exists():
        file_path.unlink()
    db.delete(image)
    db.commit()
    return {"deleted": True, "image_id": image_id}


@router.get("/items/{item_id}/market-memo", response_model=MarketMemoRead)
def get_item_market_memo(item_id: int, db: Session = Depends(get_db)) -> MarketMemoRead:
    item = _ensure_item(db, item_id)
    if item.market_memo is None:
        raise HTTPException(status_code=404, detail="相場メモがありません")
    return _market_memo_to_response(_market_memo_payload(item.market_memo))


@router.put("/items/{item_id}/market-memo", response_model=MarketMemoRead, status_code=201)
def upsert_item_market_memo(
    item_id: int,
    request: Request,
    payload: MarketMemoUpsertRequest,
    db: Session = Depends(get_db),
) -> MarketMemoRead:
    item = _ensure_item(db, item_id)
    analysis = _analysis_service(request).analyze(_item_payload(item, image_count=len(item.images)))
    defaults = build_market_memo_defaults(_item_payload(item, image_count=len(item.images)), analysis)
    provided = payload.model_dump(exclude_unset=True)
    merged: dict[str, Any] = {**defaults, **provided}
    if not merged.get("search_keyword"):
        merged["search_keyword"] = defaults["search_keyword"]
    if not merged.get("source_urls"):
        merged["source_urls"] = defaults["source_urls"]
    if item.market_memo is None:
        memo = MarketMemo(item_id=item.id)
        db.add(memo)
    else:
        memo = item.market_memo
    memo.lowest_price = merged.get("lowest_price")
    memo.median_price = merged.get("median_price")
    memo.highest_price = merged.get("highest_price")
    memo.sold_count = merged.get("sold_count")
    memo.purchase_price = merged.get("purchase_price")
    memo.shipping_fee = merged.get("shipping_fee")
    memo.marketplace_fee = merged.get("marketplace_fee")
    memo.packing_fee = merged.get("packing_fee")
    memo.disposal_fee_memo = merged.get("disposal_fee_memo")
    memo.internal_memo = merged.get("internal_memo")
    memo.search_keyword = merged.get("search_keyword")
    memo.source_urls = list(merged.get("source_urls") or [])
    db.commit()
    db.refresh(memo)
    return _market_memo_to_response(_market_memo_payload(memo))


@router.post("/ai/mock-assess", response_model=AnalysisResponse)
def mock_assess(request: Request, payload: AnalysisRequest, db: Session = Depends(get_db)) -> AnalysisResponse:
    analysis_service = _analysis_service(request)
    data: dict[str, Any] = payload.model_dump()
    if payload.item_id is not None:
        item = _ensure_item(db, payload.item_id)
        item_payload = _item_payload(item, image_count=len(item.images))
        for key in ["name", "category", "brand", "model_number", "condition_note", "quantity", "memo"]:
            if data.get(key) not in (None, "", []):
                item_payload[key] = data[key]
    else:
        if not data.get("name") and not data.get("category") and not data.get("brand") and not data.get("model_number"):
            raise HTTPException(status_code=400, detail="item_id か商品情報のいずれかが必要です")
        item_payload = {
            "id": None,
            "job_id": None,
            "name": data.get("name"),
            "category": data.get("category"),
            "brand": data.get("brand"),
            "model_number": data.get("model_number"),
            "condition_note": data.get("condition_note"),
            "quantity": data.get("quantity") or 1,
            "location_note": None,
            "memo": data.get("memo"),
            "status": "active",
            "safety_flags": [],
            "image_count": len(data.get("image_ids") or []),
        }
    response = analysis_service.analyze(item_payload)
    return _analysis_payload_to_response(response)


@router.post("/search-links", response_model=SearchLinkResponse)
def search_links(request: Request, payload: SearchLinkRequest, db: Session = Depends(get_db)) -> SearchLinkResponse:
    if payload.item_id is not None:
        item = _ensure_item(db, payload.item_id)
        query = build_market_query(
            payload.product_name or item.name,
            payload.brand or item.brand,
            payload.model_number or item.model_number,
            payload.category or item.category,
            payload.extra_keywords,
        )
    else:
        query = build_market_query(
            payload.product_name,
            payload.brand,
            payload.model_number,
            payload.category,
            payload.extra_keywords,
        )
    if not query:
        raise HTTPException(status_code=400, detail="検索キーワードが空です")
    links = build_search_links(query)
    notes = [
        "検索URL生成のみ。自動出品・自動購入・自動ログイン・スクレイピングは実行しない。",
        "サイトの検索仕様変更に備え、リンク先は都度確認すること。",
    ]
    return SearchLinkResponse(query=query, search_links=links, notes=notes)


@router.post("/calculations/items/{item_id}", response_model=ItemEstimateResponse)
def calculate_item_estimate(
    item_id: int,
    request: Request,
    options: CalculationOptions | None = None,
    db: Session = Depends(get_db),
) -> ItemEstimateResponse:
    item = _ensure_item(db, item_id)
    item_payload, analysis, market_memo_payload, estimate = _build_item_estimate_and_persist(request, db, item, options=options)
    response = {
        "estimate": _estimate_to_response(_estimate_payload(estimate)),
        "analysis": _analysis_payload_to_response(analysis),
        "market_memo": _market_memo_to_response(market_memo_payload),
        "legal_notices": [
            SafetyNotice.model_validate(notice)
            for notice in _merge_notices(
                analysis.get("legal_notices", []),
                _flags_to_notices(list(item.safety_flags_json or [])),
            )
        ],
        "summary": estimate.details_json.get("summary", {}),
        "item": _item_to_read(item),
    }
    return ItemEstimateResponse.model_validate(response)


@router.post("/calculations/jobs/{job_id}", response_model=JobEstimateResponse)
def calculate_job_estimate(
    job_id: int,
    request: Request,
    options: CalculationOptions | None = None,
    db: Session = Depends(get_db),
) -> JobEstimateResponse:
    job = _ensure_job_with_items(db, job_id)
    job_payload, item_snapshots, job_estimate_payload, job_estimate = _build_job_estimate_and_persist(request, db, job, options=options)
    response = {
        "estimate": _estimate_to_response(_estimate_payload(job_estimate)),
        "analysis": None,
        "market_memo": None,
        "legal_notices": [SafetyNotice.model_validate(notice) for notice in job_estimate_payload.get("legal_notices", [])],
        "summary": job_estimate_payload.get("summary", {}),
        "job": JobDetailRead.model_validate(
            {
                **job_payload,
                "item_count": len(job.items),
                "items": [_item_to_read(item) for item in job.items],
                "latest_estimate": _estimate_to_response(_estimate_payload(job_estimate)),
                "report_count": db.scalar(select(func.count(Report.id)).where(Report.job_id == job.id)) or 0,
                "safety_notices": [SafetyNotice.model_validate(notice) for notice in job_estimate_payload.get("legal_notices", [])],
                "summary": job_estimate_payload.get("summary", {}),
            }
        ),
    }
    return JobEstimateResponse.model_validate(response)


@router.get("/estimates/items/{item_id}/latest", response_model=ItemEstimateResponse)
def get_latest_item_estimate(item_id: int, request: Request, db: Session = Depends(get_db)) -> ItemEstimateResponse:
    item = _ensure_item(db, item_id)
    latest = _latest_estimate(db, item_id=item.id)
    if latest is None:
        raise HTTPException(status_code=404, detail="商品の見積もりがありません")
    analysis = _analysis_service(request).analyze(_item_payload(item, image_count=len(item.images)))
    market_memo_payload = _market_memo_payload(item.market_memo) if item.market_memo else build_market_memo_defaults(_item_payload(item, image_count=len(item.images)), analysis)
    response = {
        "estimate": _estimate_to_response(_estimate_payload(latest)),
        "analysis": _analysis_payload_to_response(analysis),
        "market_memo": _market_memo_to_response(market_memo_payload),
        "legal_notices": [
            SafetyNotice.model_validate(notice)
            for notice in _merge_notices(
                analysis.get("legal_notices", []),
                _flags_to_notices(list(item.safety_flags_json or [])),
            )
        ],
        "summary": latest.details_json.get("summary", {}),
        "item": _item_to_read(item),
    }
    return ItemEstimateResponse.model_validate(response)


@router.get("/estimates/jobs/{job_id}/latest", response_model=JobEstimateResponse)
def get_latest_job_estimate(job_id: int, request: Request, db: Session = Depends(get_db)) -> JobEstimateResponse:
    job = _ensure_job_with_items(db, job_id)
    latest = _latest_estimate(db, job_id=job.id)
    if latest is None:
        raise HTTPException(status_code=404, detail="案件の見積もりがありません")
    response = {
        "estimate": _estimate_to_response(_estimate_payload(latest)),
        "analysis": None,
        "market_memo": None,
        "legal_notices": [SafetyNotice.model_validate(notice) for notice in latest.details_json.get("legal_notices", [])],
        "summary": latest.details_json.get("summary", {}),
        "job": JobDetailRead.model_validate(
            {
                **_job_payload(job),
                "item_count": len(job.items),
                "items": [_item_to_read(item) for item in job.items],
                "latest_estimate": _estimate_to_response(_estimate_payload(latest)),
                "report_count": db.scalar(select(func.count(Report.id)).where(Report.job_id == job.id)) or 0,
                "safety_notices": [SafetyNotice.model_validate(notice) for notice in latest.details_json.get("legal_notices", [])],
                "summary": latest.details_json.get("summary", {}),
            }
        ),
    }
    return JobEstimateResponse.model_validate(response)


@router.post("/reports/draft", response_model=ReportResponse)
def draft_report(
    request: Request,
    payload: ReportDraftRequest,
    db: Session = Depends(get_db),
) -> ReportResponse:
    job = _ensure_job_with_items(db, payload.job_id)
    item_snapshots: list[dict[str, Any]] = []
    transient_item_estimates: list[dict[str, Any]] = []

    for item in job.items:
        item_payload = _item_payload(item, image_count=len(item.images))
        analysis = _analysis_service(request).analyze(item_payload)
        market_memo_payload = _market_memo_payload(item.market_memo) if item.market_memo else build_market_memo_defaults(item_payload, analysis)
        estimate_payload = build_item_estimate_payload(item_payload, market_memo=market_memo_payload, analysis=analysis)
        item_estimate_payload = {**estimate_payload, "analysis": analysis, "market_memo": market_memo_payload, "item": item_payload}
        transient_item_estimates.append(estimate_payload)
        item_snapshots.append(
            {
                "item": item_payload,
                "analysis": analysis,
                "market_memo": market_memo_payload,
                "estimate": estimate_payload,
                "safety_notices": _merge_notices(
                    analysis.get("legal_notices", []),
                    _flags_to_notices(item_payload.get("safety_flags", [])),
                ),
            }
        )

    job_estimate_payload = build_job_estimate_payload(_job_payload(job), transient_item_estimates)
    title = payload.title or f"{job.title} お客様向けレポート下書き"
    report_payload = build_report_payload(_job_payload(job), item_snapshots, job_estimate_payload, title=title, format=payload.format)
    report = Report(
        job_id=job.id,
        title=title,
        format=payload.format,
        summary=report_payload["summary_text"],
        content_json=jsonable_encoder(report_payload["content_json"]),
        content_html=report_payload["content_html"],
        disclaimer=LEGAL_DISCLAIMER,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    report_read = ReportRead.model_validate(_report_payload(report))
    return ReportResponse(
        report=report_read,
        html=report.content_html,
        content_json=report_payload["content_json"],
        legal_notices=[SafetyNotice.model_validate(notice) for notice in report_payload["legal_notices"]],
    )


@router.get("/reports", response_model=list[ReportRead])
def list_reports(
    job_id: int | None = None,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> list[ReportRead]:
    stmt = select(Report)
    if job_id is not None:
        stmt = stmt.where(Report.job_id == job_id)
    stmt = stmt.order_by(desc(Report.created_at), desc(Report.id)).offset(skip).limit(limit)
    reports = db.scalars(stmt).all()
    return [ReportRead.model_validate(_report_payload(report)) for report in reports]


@router.get("/reports/{report_id}", response_model=ReportRead)
def get_report(report_id: int, db: Session = Depends(get_db)) -> ReportRead:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="レポートが見つかりません")
    return ReportRead.model_validate(_report_payload(report))


@router.get("/reports/{report_id}/html", response_class=HTMLResponse)
def get_report_html(report_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="レポートが見つかりません")
    html = report.content_html or "<html><body><p>HTMLはありません</p></body></html>"
    return HTMLResponse(content=html)
