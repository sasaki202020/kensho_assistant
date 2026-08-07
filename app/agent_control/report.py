from __future__ import annotations

from datetime import datetime
from typing import Any

from ..later_queue import load_later_queue
from .job_store import load_job_rows


def build_agent_control_report(jobs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = jobs if jobs is not None else load_job_rows()
    later_rows = load_later_queue()
    counts = {
        "pending": sum(1 for row in rows if row.get("status") == "pending"),
        "running": sum(1 for row in rows if row.get("status") == "running"),
        "needs_review": sum(1 for row in rows if row.get("status") == "needs_review"),
        "blocked": sum(1 for row in rows if row.get("status") == "blocked"),
        "done": sum(1 for row in rows if row.get("status") == "done"),
        "failed": sum(1 for row in rows if row.get("status") == "failed"),
        "cancelled": sum(1 for row in rows if row.get("status") == "cancelled"),
    }
    release_allowed = counts["pending"] == 0 and counts["running"] == 0 and counts["needs_review"] == 0 and counts["blocked"] == 0 and counts["failed"] == 0
    human_review_count = sum(1 for row in rows if row.get("status") in {"needs_review", "blocked"})
    return {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "counts": counts,
        "total_jobs": len(rows),
        "later_queue_total": len(later_rows),
        "today_added_url_count": sum(1 for row in later_rows if str(row.get("created_at", ""))[:10] == datetime.now().astimezone().isoformat(timespec="seconds")[:10]),
        "duplicate_skip_count": sum(1 for row in rows if row.get("agent_name") == "QueueAgent" and ("duplicate" in str(row.get("result_summary", "")).casefold() or "重複" in str(row.get("result_summary", "")))),
        "form_diagnosed_count": sum(1 for row in rows if row.get("agent_name") == "FormCheckAgent" and row.get("status") in {"done", "needs_review", "blocked"}),
        "human_review_count": human_review_count,
        "release_allowed": release_allowed,
        "release_reason": "全ジョブが完了し、警告・ブロックがありません" if release_allowed else "pending/running/needs_review/blocked/failed が残っています",
        "submitted_count_auto": 0,
        "safe_to_submit": False,
    }
