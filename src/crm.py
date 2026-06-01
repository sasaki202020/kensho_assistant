from __future__ import annotations

from datetime import date
from pathlib import Path

from .autopilot_shared import LeadRecord, write_csv_rows

CRM_COLUMNS = [
    "date",
    "company_name",
    "industry",
    "area",
    "website_url",
    "lead_priority_score",
    "status",
    "next_action",
    "proposal_path",
    "report_path",
    "notes",
]


def build_crm_row(
    lead: LeadRecord,
    *,
    report_date: date,
    score: int,
    status: str,
    next_action: str,
    proposal_path: Path,
    report_path: Path,
    notes: str = "",
) -> dict[str, str]:
    return {
        "date": report_date.isoformat(),
        "company_name": lead.company_name,
        "industry": lead.industry,
        "area": lead.area,
        "website_url": lead.website_url,
        "lead_priority_score": str(score),
        "status": status,
        "next_action": next_action,
        "proposal_path": str(proposal_path),
        "report_path": str(report_path),
        "notes": notes,
    }


def write_crm_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    return write_csv_rows(path, rows, CRM_COLUMNS)

