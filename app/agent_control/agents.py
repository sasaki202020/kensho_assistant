from __future__ import annotations

from typing import Any

from .schema import AGENT_CONTROL_AGENT_DEFINITIONS


def list_agent_definitions() -> list[dict[str, str]]:
    return [dict(agent) for agent in AGENT_CONTROL_AGENT_DEFINITIONS]


def get_agent_definition(agent_name: str) -> dict[str, str]:
    for agent in AGENT_CONTROL_AGENT_DEFINITIONS:
        if agent["agent_name"] == agent_name:
            return dict(agent)
    return {}


def default_agent_action(agent_name: str) -> str:
    definition = get_agent_definition(agent_name)
    return definition.get("default_action", "dry_run")


def safe_agent_buttons(agent_name: str) -> list[dict[str, Any]]:
    return [
        {"label": "実行", "action": default_agent_action(agent_name)},
        {"label": "停止", "action": "cancel"},
        {"label": "ログ", "action": "log"},
        {"label": "結果", "action": "result"},
        {"label": "人間確認へ送る", "action": "human_review"},
    ]
