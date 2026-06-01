from __future__ import annotations

from dataclasses import dataclass, asdict
import base64
import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable


def today_key(run_date: date | None = None) -> str:
    return (run_date or date.today()).strftime("%Y%m%d")


def safe_filename(value: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー _().\-]+", "_", text)
    text = text.strip(" ._")
    return text or "unknown"


def slugify(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠ー]+", "-", (value or "").strip().casefold())
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        digest = hashlib.sha1((value or fallback).encode("utf-8")).hexdigest()[:8]
        return f"{fallback}-{digest}"
    return text[:80]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    return path


def compact_text(text: str, limit: int = 180) -> str:
    value = re.sub(r"\s+", " ", (text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def digest_text(*parts: str) -> str:
    payload = "|".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def transparent_png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO6n3a8AAAAASUVORK5CYII="
    )


def write_placeholder_png(path: Path, lines: list[str], size: tuple[int, int] = (1200, 800)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:
        path.write_bytes(transparent_png_bytes())
        return path

    width, height = size
    image = Image.new("RGB", size, color="#f4f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, width - 40, height - 40), radius=32, fill="#ffffff", outline="#c7d2e0", width=4)
    try:
        title_font = ImageFont.truetype("arial.ttf", 44)
        body_font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
    draw.text((80, 90), "Screenshot unavailable", fill="#102030", font=title_font)
    y = 170
    for line in lines[:12]:
        draw.text((80, y), line, fill="#304050", font=body_font)
        y += 42
    image.save(path)
    return path


@dataclass(slots=True)
class LeadRecord:
    company_name: str
    industry: str
    area: str
    website_url: str
    contact_url: str
    source_url: str
    source_type: str
    confidence: float
    status: str

    def to_row(self) -> dict[str, str]:
        data = asdict(self)
        data["confidence"] = f"{self.confidence:.2f}"
        return {key: str(value) for key, value in data.items()}

    @classmethod
    def from_row(cls, row: dict[str, str], *, default_industry: str = "", default_area: str = "") -> "LeadRecord":
        return cls(
            company_name=(row.get("company_name") or row.get("company") or "").strip(),
            industry=(row.get("industry") or default_industry).strip(),
            area=(row.get("area") or default_area).strip(),
            website_url=(row.get("website_url") or row.get("url") or "").strip(),
            contact_url=(row.get("contact_url") or "").strip(),
            source_url=(row.get("source_url") or row.get("source") or row.get("website_url") or "").strip(),
            source_type=(row.get("source_type") or "manual_csv").strip(),
            confidence=_coerce_float(row.get("confidence"), default=0.65),
            status=(row.get("status") or "new").strip(),
        )


def _coerce_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value not in {None, ""} else default
    except Exception:
        return default


def lead_name(lead: LeadRecord) -> str:
    return lead.company_name.strip() or lead.website_url.strip() or "unknown"


def safe_company_dir_name(lead: LeadRecord) -> str:
    return slugify(lead_name(lead), fallback="company")

