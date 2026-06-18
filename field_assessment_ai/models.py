from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    items: Mapped[list["Item"]] = relationship(back_populates="job", cascade="all, delete-orphan", passive_deletes=True)
    estimates: Mapped[list["Estimate"]] = relationship(back_populates="job", cascade="all, delete-orphan", passive_deletes=True)
    reports: Mapped[list["Report"]] = relationship(back_populates="job", cascade="all, delete-orphan", passive_deletes=True)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    condition_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    location_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    safety_flags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    job: Mapped[Job | None] = relationship(back_populates="items")
    images: Mapped[list[ItemImage]] = relationship(back_populates="item", cascade="all, delete-orphan", passive_deletes=True)
    market_memo: Mapped[MarketMemo | None] = relationship(back_populates="item", cascade="all, delete-orphan", uselist=False, passive_deletes=True)
    estimates: Mapped[list[Estimate]] = relationship(back_populates="item", cascade="all, delete-orphan", passive_deletes=True)


class ItemImage(Base):
    __tablename__ = "item_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    public_url: Mapped[str] = mapped_column(String(512), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    item: Mapped[Item] = relationship(back_populates="images")


class MarketMemo(Base):
    __tablename__ = "market_memos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    lowest_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    highest_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sold_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purchase_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marketplace_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    packing_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposal_fee_memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_urls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    item: Mapped[Item] = relationship(back_populates="market_memo")


class Estimate(Base):
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), nullable=True, index=True)
    resale_estimate_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resale_estimate_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purchase_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposal_fee_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_fee_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_possible_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_estimate_guide: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sale_value_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_candidate: Mapped[str | None] = mapped_column(String(2), nullable=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    job: Mapped[Job | None] = relationship(back_populates="estimates")
    item: Mapped[Item | None] = relationship(back_populates="estimates")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="json")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclaimer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    job: Mapped[Job] = relationship(back_populates="reports")
