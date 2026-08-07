from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..paths import AGENT_STATUS_JSON
from .schema import canonical_agent_record, default_agent_records


def load_agent_status_payload(path: Path = AGENT_STATUS_JSON) -> dict[str, Any]:
    if not path.exists():
        return {"updated_at": "", "agents": default_agent_records(), "source_state": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"updated_at": "", "agents": default_agent_records(), "source_state": "invalid"}
    if not isinstance(payload, dict):
        return {"updated_at": "", "agents": default_agent_records(), "source_state": "invalid"}
    raw_agents = payload.get("agents", [])
    if not isinstance(raw_agents, list):
        raw_agents = []
    agents = [canonical_agent_record(agent if isinstance(agent, dict) else {}, default_role=None) for agent in raw_agents]
    if not agents:
        agents = default_agent_records()
    organization = payload.get("organization")
    if not isinstance(organization, dict):
        organization = {}
    return {
        "updated_at": str(payload.get("updated_at") or ""),
        "mode": str(payload.get("mode") or ""),
        "run_mode": str(payload.get("run_mode") or ""),
        "task": str(payload.get("task") or ""),
        "organization": organization,
        "agents": agents,
        "source_state": "json",
    }
