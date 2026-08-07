from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .paths import PREPARE_ALL_STATUS_JSON


def default_prepare_all_status() -> dict[str, object]:
    return {
        "status": "idle",
        "status_label": "未実行",
        "message": "一括入力補助は未実行です。",
        "total": 0,
        "done": 0,
        "ok": 0,
        "failed": 0,
        "progress_percent": 0,
        "current_index": 0,
        "current_campaign_id": "",
        "current_campaign_name": "",
        "current_queue_status": "",
        "submitted_count_auto": 0,
        "started_at": "",
        "updated_at": "",
        "finished_at": "",
    }


def build_prepare_all_status(
    *,
    status: str,
    total: int,
    done: int,
    ok: int,
    failed: int,
    current_index: int = 0,
    current_campaign_id: str = "",
    current_campaign_name: str = "",
    current_queue_status: str = "",
    message: str = "",
    started_at: str = "",
    finished_at: str = "",
    submitted_count_auto: int = 0,
) -> dict[str, object]:
    total = max(int(total), 0)
    done = max(int(done), 0)
    ok = max(int(ok), 0)
    failed = max(int(failed), 0)
    progress_percent = int(round((done / total) * 100)) if total else 0
    label_map = {
        "idle": "未実行",
        "running": "実行中",
        "success": "完了",
        "warning": "一部失敗",
        "failed": "失敗",
    }
    status_key = str(status or "idle").strip().lower()
    return {
        "status": status_key,
        "status_label": label_map.get(status_key, status_key or "未実行"),
        "message": message or default_prepare_all_status()["message"],
        "total": total,
        "done": done,
        "ok": ok,
        "failed": failed,
        "progress_percent": progress_percent,
        "current_index": current_index,
        "current_campaign_id": current_campaign_id,
        "current_campaign_name": current_campaign_name,
        "current_queue_status": current_queue_status,
        "submitted_count_auto": submitted_count_auto,
        "started_at": started_at,
        "updated_at": "",
        "finished_at": finished_at,
    }


def load_prepare_all_status() -> dict[str, object]:
    if not PREPARE_ALL_STATUS_JSON.exists():
        return default_prepare_all_status()
    try:
        data = json.loads(PREPARE_ALL_STATUS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return default_prepare_all_status()
    if not isinstance(data, dict):
        return default_prepare_all_status()
    payload = default_prepare_all_status()
    payload.update(data)
    return payload


def save_prepare_all_status(payload: dict[str, object]) -> Path:
    PREPARE_ALL_STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    data = dict(default_prepare_all_status())
    data.update(payload)
    data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if not data.get("started_at"):
        data["started_at"] = data["updated_at"]
    PREPARE_ALL_STATUS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return PREPARE_ALL_STATUS_JSON
