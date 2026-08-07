from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..paths import AGENT_ORG_JSON

DEFAULT_AGENT_ORG: dict[str, Any] = {
    "version": "0.4.4",
    "project": "kensho_assistant",
    "org_name": "Kensho Safe AI Team",
    "mission": "応募送信を自動化せず、安全な開発・診断・レビュー・リリース判断を支援する",
    "global_rules": [
        "自動送信しない",
        "submit / click による応募実行を追加しない",
        "X自動操作を追加しない",
        "メール送信を追加しない",
        "profile.enc を読まない",
        "PIIをログ・JSON・画面・レポートに出さない",
        "submitted_count_auto = 0 を維持する",
        "safe_to_submit を送信実行に使わない",
        "最後の応募判断は必ず人間が行う",
    ],
    "modes": {
        "normal": [
            "tech-lead",
            "backend-dev",
            "safety-director",
            "test-engineer",
            "release-gatekeeper",
        ],
        "release": [
            "tech-lead",
            "backend-dev",
            "frontend-dev",
            "desktop-ui-dev",
            "test-engineer",
            "debugger",
            "docs-writer",
            "safety-director",
            "privacy-guard",
            "no-submit-reviewer",
            "pii-auditor",
            "external-action-reviewer",
            "release-gatekeeper",
            "release-notes-manager",
            "zip-auditor",
            "support-docs",
        ],
    },
    "teams": [
        {
            "id": "engineering",
            "name": "エンジニアリング",
            "purpose": "実装・テスト・デバッグ・ドキュメント更新",
            "agents": [
                {
                    "id": "tech-lead",
                    "name": "tech-lead",
                    "role": "実装方針を決める",
                    "checks": ["変更範囲", "既存機能への影響", "最小変更"],
                },
                {
                    "id": "backend-dev",
                    "name": "backend-dev",
                    "role": "CLI / service / JSON / schema を実装する",
                    "checks": ["CLI設計", "JSON整合性", "service層"],
                },
                {
                    "id": "frontend-dev",
                    "name": "frontend-dev",
                    "role": "Web UI を実装する",
                    "checks": ["Web表示", "状態表示", "エラー表示"],
                },
                {
                    "id": "desktop-ui-dev",
                    "name": "desktop-ui-dev",
                    "role": "デスクトップUIを実装する",
                    "checks": ["desktop表示", "PySide6依存", "smoke test"],
                },
                {
                    "id": "test-engineer",
                    "name": "test-engineer",
                    "role": "pytest / smoke test を追加・実行する",
                    "checks": ["pytest", "compileall", "smoke test"],
                },
                {
                    "id": "debugger",
                    "name": "debugger",
                    "role": "失敗原因を切り分ける",
                    "checks": ["失敗分類", "環境依存", "回帰影響"],
                },
                {
                    "id": "docs-writer",
                    "name": "docs-writer",
                    "role": "README / docs / RELEASE_NOTES を更新する",
                    "checks": ["README", "docs", "release notes"],
                },
            ],
        },
        {
            "id": "safety",
            "name": "安全・審査",
            "purpose": "自動送信・PII漏えい・外部操作を防ぐ",
            "agents": [
                {
                    "id": "safety-director",
                    "name": "safety-director",
                    "role": "安全方針の最終確認",
                    "checks": ["安全制約", "禁止事項", "リスク判定"],
                },
                {
                    "id": "privacy-guard",
                    "name": "privacy-guard",
                    "role": "profile.enc / 個人情報まわりを確認",
                    "checks": ["profile.enc未読込", "PII非表示", "ログマスク"],
                },
                {
                    "id": "no-submit-reviewer",
                    "name": "no-submit-reviewer",
                    "role": "submit / click / auto_submit 混入を確認",
                    "checks": ["submit禁止", "click禁止", "auto_submit禁止"],
                },
                {
                    "id": "pii-auditor",
                    "name": "pii-auditor",
                    "role": "ログ・JSON・画面へのPII漏れを確認",
                    "checks": ["住所", "電話番号", "氏名", "メール本文"],
                },
                {
                    "id": "external-action-reviewer",
                    "name": "external-action-reviewer",
                    "role": "X / メール / 外部投稿の自動化混入を確認",
                    "checks": ["X操作なし", "メール送信なし", "requests.postなし"],
                },
                {
                    "id": "release-gatekeeper",
                    "name": "release-gatekeeper",
                    "role": "配布可否をYES/NOで判定する",
                    "checks": ["release_allowed", "残タスク", "配布可否"],
                },
            ],
        },
        {
            "id": "product_ux",
            "name": "商品化・UX",
            "purpose": "売れる形・初心者に伝わる形に整える",
            "agents": [
                {
                    "id": "product-director",
                    "name": "product-director",
                    "role": "商品価値と優先順位を決める",
                    "checks": ["価値訴求", "優先順位", "販売導線"],
                },
                {
                    "id": "ux-reviewer",
                    "name": "ux-reviewer",
                    "role": "初心者にも伝わる画面か確認する",
                    "checks": ["画面文言", "警告表示", "操作導線"],
                },
                {
                    "id": "beginner-voice",
                    "name": "beginner-voice",
                    "role": "PCが苦手な人目線で確認する",
                    "checks": ["わかりやすさ", "怖さの低減", "説明不足"],
                },
                {
                    "id": "trust-copywriter",
                    "name": "trust-copywriter",
                    "role": "安全性・手動確認・個人情報保護を伝える文章を作る",
                    "checks": ["信頼説明", "手動確認", "個人情報保護"],
                },
                {
                    "id": "pricing-strategy",
                    "name": "pricing-strategy",
                    "role": "無料版/有料版/販売導線を考える",
                    "checks": ["無料版", "有料版", "販売導線"],
                },
                {
                    "id": "support-docs",
                    "name": "support-docs",
                    "role": "使い方・FAQ・注意事項を整える",
                    "checks": ["FAQ", "注意事項", "サポート文書"],
                },
            ],
        },
        {
            "id": "operations",
            "name": "運用・リリース",
            "purpose": "毎回同じ品質でチェック・記録・配布判断する",
            "agents": [
                {
                    "id": "task-dispatch",
                    "name": "task-dispatch",
                    "role": "今回の作業を担当に割り振る",
                    "checks": ["タスク分解", "担当割当", "実行モード"],
                },
                {
                    "id": "morning-standup",
                    "name": "morning-standup",
                    "role": "今日やることを整理する",
                    "checks": ["今日の作業", "優先順位", "ブロッカー"],
                },
                {
                    "id": "agent-status-writer",
                    "name": "agent-status-writer",
                    "role": "agent_status.json を更新する",
                    "checks": ["JSON生成", "schema整合", "表示反映"],
                },
                {
                    "id": "release-notes-manager",
                    "name": "release-notes-manager",
                    "role": "リリースノートを整える",
                    "checks": ["変更内容", "安全制約", "既知の制限"],
                },
                {
                    "id": "zip-auditor",
                    "name": "zip-auditor",
                    "role": "配布ZIPに危険ファイルや個人情報が混入していないか確認する",
                    "checks": ["ZIP内容", "profile除外", "ログ除外"],
                },
                {
                    "id": "knowledge-sync",
                    "name": "knowledge-sync",
                    "role": "前回の決定事項を引き継ぐ",
                    "checks": ["前回の残タスク", "仕様引き継ぎ", "安全ルール"],
                },
            ],
        },
    ],
}

LEGACY_ROLE_TEAM_MAP = {
    "queue_manager": "engineering",
    "campaign_researcher": "engineering",
    "form_diagnostician": "engineering",
    "safety_reviewer": "safety",
    "test_runner": "engineering",
    "docs_writer": "engineering",
    "planner": "engineering",
    "coder": "engineering",
    "tester": "engineering",
    "release_manager": "operations",
}


def default_agent_org_payload() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_AGENT_ORG, ensure_ascii=False))


def _coerce_text(value: object, default: str = "") -> str:
    text = str(value or default).strip()
    return text or default


def normalize_agent_org_mode(value: object) -> str:
    text = _coerce_text(value, "normal").casefold()
    return "release" if text == "release" else "normal"


def _coerce_team(team: Mapping[str, Any]) -> dict[str, Any]:
    agents = team.get("agents", [])
    if not isinstance(agents, list):
        agents = []
    safe_agents: list[dict[str, Any]] = []
    for agent in agents:
        if not isinstance(agent, Mapping):
            continue
        safe_agents.append(
            {
                "id": _coerce_text(agent.get("id")),
                "name": _coerce_text(agent.get("name")),
                "role": _coerce_text(agent.get("role")),
                "checks": [str(check) for check in agent.get("checks", []) if str(check).strip()],
            }
        )
    return {
        "id": _coerce_text(team.get("id")),
        "name": _coerce_text(team.get("name")),
        "purpose": _coerce_text(team.get("purpose")),
        "agents": safe_agents,
    }


def _canonicalize_org_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    teams_raw = payload.get("teams", [])
    if not isinstance(teams_raw, list):
        teams_raw = []
    return {
        "version": _coerce_text(payload.get("version"), "0.4.4"),
        "project": _coerce_text(payload.get("project"), "kensho_assistant"),
        "org_name": _coerce_text(payload.get("org_name"), "Kensho Safe AI Team"),
        "mission": _coerce_text(
            payload.get("mission"),
            "応募送信を自動化せず、安全な開発・診断・レビュー・リリース判断を支援する",
        ),
        "global_rules": [str(rule) for rule in payload.get("global_rules", []) if str(rule).strip()],
        "modes": {
            "normal": [
                str(role)
                for role in (payload.get("modes", {}) or {}).get("normal", [])
                if str(role).strip()
            ],
            "release": [
                str(role)
                for role in (payload.get("modes", {}) or {}).get("release", [])
                if str(role).strip()
            ],
        },
        "teams": [_coerce_team(team) for team in teams_raw if isinstance(team, Mapping)],
    }


def load_agent_org_payload(path: Path = AGENT_ORG_JSON) -> dict[str, Any]:
    if not path.exists():
        return {"source_state": "missing", **default_agent_org_payload()}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"source_state": "invalid", **default_agent_org_payload()}
    if not isinstance(payload, Mapping):
        return {"source_state": "invalid", **default_agent_org_payload()}
    return {"source_state": "json", **_canonicalize_org_payload(payload)}


def get_mode_roles(org_payload: Mapping[str, Any], mode: object = "normal") -> list[str]:
    modes = org_payload.get("modes", {})
    if not isinstance(modes, Mapping):
        modes = {}
    raw_roles = modes.get(normalize_agent_org_mode(mode), [])
    if not isinstance(raw_roles, list):
        raw_roles = []
    roles: list[str] = []
    for role in raw_roles:
        role_text = _coerce_text(role)
        if role_text and role_text not in roles:
            roles.append(role_text)
    return roles


def build_role_lookup(org_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for team in org_payload.get("teams", []):
        if not isinstance(team, Mapping):
            continue
        team_id = _coerce_text(team.get("id"))
        team_name = _coerce_text(team.get("name"), team_id)
        team_purpose = _coerce_text(team.get("purpose"))
        for agent in team.get("agents", []):
            if not isinstance(agent, Mapping):
                continue
            role = _coerce_text(agent.get("id"))
            if not role:
                continue
            lookup[role] = {
                "team_id": team_id,
                "team_name": team_name,
                "team_purpose": team_purpose,
                "name": _coerce_text(agent.get("name"), role),
                "role": _coerce_text(agent.get("role")),
                "checks": [str(check) for check in agent.get("checks", []) if str(check).strip()],
            }
    return lookup


def group_agents_by_team(
    agents: list[dict[str, Any]],
    org_payload: Mapping[str, Any],
    mode: object = "normal",
) -> list[dict[str, Any]]:
    role_lookup = build_role_lookup(org_payload)
    team_lookup: dict[str, dict[str, Any]] = {}
    grouped: list[dict[str, Any]] = []
    active_roles = set(get_mode_roles(org_payload, mode))
    for team in org_payload.get("teams", []):
        if not isinstance(team, Mapping):
            continue
        team_id = _coerce_text(team.get("id"))
        team_name = _coerce_text(team.get("name"), team_id)
        team_entry = {
            "id": team_id,
            "name": team_name,
            "purpose": _coerce_text(team.get("purpose")),
            "agents": [],
            "active_role_count": 0,
        }
        team_lookup[team_id] = team_entry
        grouped.append(team_entry)
    unknown_group = {"id": "unassigned", "name": "未割当", "purpose": "", "agents": [], "active_role_count": 0}
    for agent in agents:
        role = _coerce_text(agent.get("role"))
        meta = role_lookup.get(role)
        team_id = meta["team_id"] if meta else LEGACY_ROLE_TEAM_MAP.get(role, "")
        team_entry = team_lookup.get(team_id) if team_id else unknown_group
        if team_entry is unknown_group and unknown_group not in grouped:
            grouped.append(unknown_group)
        enriched = dict(agent)
        if meta:
            enriched.setdefault("team_id", meta["team_id"])
            enriched.setdefault("team_name", meta["team_name"])
            enriched.setdefault("team_purpose", meta["team_purpose"])
        elif team_id and team_id in team_lookup:
            enriched.setdefault("team_id", team_id)
            enriched.setdefault("team_name", team_lookup[team_id]["name"])
            enriched.setdefault("team_purpose", team_lookup[team_id]["purpose"])
        team_entry["agents"].append(enriched)
        if role in active_roles:
            team_entry["active_role_count"] += 1
    return [team for team in grouped if team["agents"]]
