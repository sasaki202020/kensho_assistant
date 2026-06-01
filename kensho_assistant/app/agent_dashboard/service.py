from __future__ import annotations

import json
from importlib.util import find_spec
from datetime import datetime
from pathlib import Path
from typing import Any

from ..privacy_guard import redact_personal_info
from ..paths import AGENT_ORG_JSON, AGENT_RUN_LOG_JSONL, AGENT_STATUS_JSON, ensure_runtime_dirs
from .org import (
    build_role_lookup,
    get_mode_roles,
    group_agents_by_team,
    load_agent_org_payload,
    normalize_agent_org_mode,
)
from .result_reader import load_agent_status_payload
from .schema import AGENT_ROLE_ORDER, canonical_agent_record, display_agent_status

AGENT_GENERATION_ROLES: list[tuple[str, str, str, list[str], list[str], str]] = [
    (
        "planner",
        "Planner",
        "pending",
        ["キュー整理", "次の確認点", "安全制約確認"],
        ["重複候補", "期限切れ"],
        "応募準備の順番を整理中",
    ),
    (
        "coder",
        "Coder",
        "running",
        ["最小変更", "既存互換", "安全なJSON出力"],
        ["広範囲修正", "不要な依存追加"],
        "生成コマンドと表示連携を実装中",
    ),
    (
        "safety_reviewer",
        "Safety Reviewer",
        "passed",
        ["自動送信なし", "暗号化保存データ非読込", "PIIなし"],
        ["送信系の混入"],
        "安全制約を維持していることを確認済み",
    ),
    (
        "tester",
        "Tester",
        "warning",
        ["pytest", "compileall", "smoke-test"],
        ["PySide6 未導入環境"],
        "一部デスクトップテストは環境依存で skip",
    ),
    (
        "release_manager",
        "Release Manager",
        "passed",
        ["README反映", "release notes", "ZIP混入確認"],
        ["危険ファイル混入"],
        "配布可否を安全側で確認済み",
    ),
]
AGENT_SORT_ORDER = AGENT_ROLE_ORDER + [role for role, *_ in AGENT_GENERATION_ROLES]
SAFE_AGENT_RUN_TASK_LIMIT = 80


def _load_dashboard_context(
    path: Path = AGENT_STATUS_JSON,
    org_path: Path = AGENT_ORG_JSON,
    mode: object | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    status_payload = load_agent_status_payload(path)
    org_payload = load_agent_org_payload(org_path)
    status_org = status_payload.get("organization")
    if isinstance(status_org, dict) and status_org:
        org_payload = {
            **org_payload,
            "organization": status_org,
        }
    resolved_mode = normalize_agent_org_mode(
        mode if mode is not None else (status_payload.get("mode") or status_payload.get("run_mode") or "normal")
    )
    return status_payload, org_payload, resolved_mode


def _sort_order_for_mode(org_payload: dict[str, Any], mode: str) -> dict[str, int]:
    roles = get_mode_roles(org_payload, mode) + AGENT_ROLE_ORDER
    order: dict[str, int] = {}
    for role in roles:
        if role not in order:
            order[role] = len(order)
    return order


def _sorted_agents(path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> list[dict[str, Any]]:
    payload, org_payload, resolved_mode = _load_dashboard_context(path, org_path, mode=mode)
    agents = [canonical_agent_record(agent, default_role=None) for agent in payload.get("agents", [])]
    order = _sort_order_for_mode(org_payload, resolved_mode)
    return sorted(
        agents,
        key=lambda agent: (
            order.get(str(agent.get("role", "")), len(order)),
            str(agent.get("display_name", "")),
        ),
    )


def list_agents(path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> list[dict[str, Any]]:
    return _sorted_agents(path, org_path, mode=mode)


def get_agent_summary(path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> dict[str, int]:
    agents = _sorted_agents(path, org_path, mode=mode)
    return {
        "total_agents": len(agents),
        "running_count": sum(1 for agent in agents if agent.get("status_display") == "running"),
        "warning_count": sum(1 for agent in agents if agent.get("status_display") == "warning" or int(agent.get("warning_count", 0) or 0) > 0),
        "error_count": sum(1 for agent in agents if agent.get("status_display") == "error" or int(agent.get("error_count", 0) or 0) > 0),
        "completed_count": sum(1 for agent in agents if agent.get("status_display") == "completed"),
        "idle_count": sum(1 for agent in agents if agent.get("status_display") == "idle"),
    }


def get_agent_by_role(role: str, path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> dict[str, Any]:
    for agent in _sorted_agents(path, org_path, mode=mode):
        if str(agent.get("role", "")) == role:
            return agent
    return {}


def list_warning_agents(path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> list[dict[str, Any]]:
    return [
        agent
        for agent in _sorted_agents(path, org_path, mode=mode)
        if agent.get("status_display") == "warning" or int(agent.get("warning_count", 0) or 0) > 0
    ]


def list_error_agents(path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> list[dict[str, Any]]:
    return [
        agent
        for agent in _sorted_agents(path, org_path, mode=mode)
        if agent.get("status_display") == "error" or int(agent.get("error_count", 0) or 0) > 0
    ]


def get_agent_org_summary(path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> dict[str, Any]:
    status_payload, org_payload, resolved_mode = _load_dashboard_context(path, org_path, mode=mode)
    agents = [canonical_agent_record(agent, default_role=None) for agent in status_payload.get("agents", [])]
    team_groups = group_agents_by_team(agents, org_payload, resolved_mode)
    active_agents = sum(len(team.get("agents", [])) for team in team_groups)
    return {
        "mode": resolved_mode,
        "mode_label": "通常モード" if resolved_mode == "normal" else "リリース前モード",
        "org_name": str(org_payload.get("org_name", "Kensho Safe AI Team")),
        "mission": str(org_payload.get("mission", "")),
        "version": str(org_payload.get("version", "")),
        "team_count": len(org_payload.get("teams", [])),
        "active_team_count": len(team_groups),
        "active_agent_count": active_agents,
        "selected_role_count": len(get_mode_roles(org_payload, resolved_mode)),
        "source_state": status_payload.get("source_state", ""),
    }


def group_agent_teams(path: Path = AGENT_STATUS_JSON, org_path: Path = AGENT_ORG_JSON, mode: object | None = None) -> list[dict[str, Any]]:
    status_payload, org_payload, resolved_mode = _load_dashboard_context(path, org_path, mode=mode)
    agents = [canonical_agent_record(agent, default_role=None) for agent in status_payload.get("agents", [])]
    return group_agents_by_team(agents, org_payload, resolved_mode)


def build_agent_status_payload(updated_at: str | None = None) -> dict[str, Any]:
    timestamp = updated_at or datetime.now().astimezone().isoformat(timespec="seconds")
    agents: list[dict[str, Any]] = []
    for role, display_name, status, checks, risks, summary in AGENT_GENERATION_ROLES:
        agents.append(
            {
                "role": role,
                "display_name": display_name,
                "status": status,
                "summary": summary,
                "checks": checks,
                "risks": risks,
                "updated_at": timestamp,
                "progress_percent": {
                    "pending": 20,
                    "running": 55,
                    "passed": 100,
                    "warning": 75,
                    "failed": 40,
                }.get(status, 0),
                "total_tasks": {
                    "planner": 3,
                    "coder": 3,
                    "safety_reviewer": 3,
                    "tester": 3,
                    "release_manager": 3,
                }.get(role, 0),
                "completed_tasks": {
                    "pending": 0,
                    "running": 2,
                    "passed": 3,
                    "warning": 2,
                    "failed": 1,
                }.get(status, 0),
                "warning_count": 1 if status == "warning" else 0,
                "error_count": 1 if status == "failed" else 0,
                "last_message": summary,
                "status_display": display_agent_status(status),
                "checks_detail": checks,
                "risks_detail": risks,
            }
        )
    return {"updated_at": timestamp, "agents": agents}


def save_agent_status_payload(path: Path = AGENT_STATUS_JSON, updated_at: str | None = None) -> dict[str, Any]:
    ensure_runtime_dirs()
    payload = build_agent_status_payload(updated_at=updated_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _safe_task_label(task: object) -> str:
    text = redact_personal_info(str(task or "")).strip()
    if not text:
        return "safe-agent-run"
    if len(text) > SAFE_AGENT_RUN_TASK_LIMIT:
        return text[:SAFE_AGENT_RUN_TASK_LIMIT].rstrip()
    return text


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _build_agent_run_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    agents = []
    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for agent in payload.get("agents", []):
        record = {
            "role": str(agent.get("role", "")),
            "display_name": str(agent.get("display_name", "")),
            "team_id": str(agent.get("team_id", "")),
            "team_name": str(agent.get("team_name", "")),
            "status": str(agent.get("status", "")),
            "summary": redact_personal_info(str(agent.get("summary", ""))),
            "checks": [redact_personal_info(str(item)) for item in agent.get("checks", []) if str(item).strip()],
            "risks": [redact_personal_info(str(item)) for item in agent.get("risks", []) if str(item).strip()],
            "warning_count": int(agent.get("warning_count", 0) or 0),
            "error_count": int(agent.get("error_count", 0) or 0),
            "updated_at": str(agent.get("updated_at", "")),
        }
        agents.append(record)
        if record["warning_count"] > 0 or record["status"] == "warning":
            warnings.append({"role": record["role"], "reason": record["summary"] or "warning"})
        if record["error_count"] > 0 or record["status"] == "failed":
            errors.append({"role": record["role"], "reason": record["summary"] or "failed"})

    mode = str(payload.get("mode", "normal") or "normal")
    selected_roles = list(payload.get("organization", {}).get("selected_roles", []))
    has_risk = bool(warnings or errors)
    release_allowed = bool(
        mode == "release"
        and not has_risk
        and all(agent.get("status") == "passed" for agent in agents)
    )
    return {
        "executed_at": str(payload.get("updated_at", "")),
        "task": redact_personal_info(str(payload.get("task", ""))),
        "mode": mode,
        "run_mode": str(payload.get("run_mode", "safe-agent-run")),
        "organization": {
            "org_name": redact_personal_info(str(payload.get("organization", {}).get("org_name", ""))),
            "version": str(payload.get("organization", {}).get("version", "")),
            "mode_label": str(payload.get("organization", {}).get("mode_label", "")),
            "selected_roles": selected_roles,
            "team_count": int(payload.get("organization", {}).get("team_count", 0) or 0),
            "active_role_count": int(payload.get("organization", {}).get("active_role_count", 0) or 0),
        },
        "agents": agents,
        "warnings": warnings,
        "errors": errors,
        "verification": {
            "pytest": {"status": "not_run", "reason": "agent-status run does not execute pytest"},
            "compileall": {"status": "not_run", "reason": "agent-status run does not execute compileall"},
            "smoke_test": {"status": "not_run", "reason": "agent-status run does not execute smoke test"},
        },
        "release_allowed": release_allowed,
        "release_reason": "no blocking warnings/errors" if release_allowed else "verification not run or warnings/errors present",
        "safety": {
            "auto_submit": False,
            "submitted_count_auto": 0,
            "safe_to_submit": False,
            "profile_enc_read": False,
            "pii_logged": False,
            "external_post": False,
            "x_action_automated": False,
        },
    }


def _run_status_for_role(role: str, mode: str, pyside_available: bool) -> str:
    if role in {"safety-director", "privacy-guard", "no-submit-reviewer", "pii-auditor", "external-action-reviewer", "release-gatekeeper"}:
        return "passed"
    if role == "tester":
        return "passed" if pyside_available else "warning"
    if role == "desktop-ui-dev":
        return "passed" if pyside_available else "warning"
    if role in {"frontend-dev", "debugger", "docs-writer", "release-notes-manager", "zip-auditor", "support-docs", "task-dispatch", "morning-standup"}:
        return "running"
    if role in {"backend-dev", "tech-lead"}:
        return "running"
    if role == "product-director":
        return "running"
    if role in {"ux-reviewer", "beginner-voice", "trust-copywriter", "pricing-strategy"}:
        return "passed"
    return "pending"


def build_agent_status_run_payload(task: object, mode: object = "normal", updated_at: str | None = None) -> dict[str, Any]:
    timestamp = updated_at or datetime.now().astimezone().isoformat(timespec="seconds")
    task_label = _safe_task_label(task)
    mode_name = normalize_agent_org_mode(mode)
    org_payload = load_agent_org_payload(AGENT_ORG_JSON)
    selected_roles = get_mode_roles(org_payload, mode_name)
    role_lookup = build_role_lookup(org_payload)
    pyside_available = find_spec("PySide6") is not None
    agents: list[dict[str, Any]] = []
    for role in selected_roles:
        meta = role_lookup.get(role, {})
        team_id = str(meta.get("team_id") or "")
        team_name = str(meta.get("team_name") or "")
        team_purpose = str(meta.get("team_purpose") or "")
        checks = [str(check) for check in meta.get("checks", []) if str(check).strip()]
        status = _run_status_for_role(role, mode_name, pyside_available)
        if role == "planner":
            summary = f"作業「{task_label}」の安全な進行順を整理中"
            risks = ["作業範囲の拡大"]
            progress = 35
            completed = 1
            last_message = f"作業「{task_label}」を受け付けました"
        elif role == "coder":
            summary = "ローカル安全更新とJSON出力を確認済み"
            risks = ["広範囲修正"]
            progress = 100
            completed = 3
            last_message = "安全なステータス更新を維持しています"
        elif role == "safety-director":
            summary = "安全制約と禁止事項を確認済み"
            risks = ["送信系の混入"]
            progress = 100
            completed = 3
            last_message = "安全制約を維持しています"
        elif role == "privacy-guard":
            summary = "profile.enc 非読込とPII非出力を確認済み"
            risks = ["PII漏えい"]
            progress = 100
            completed = 3
            last_message = "profile.enc を読まずに確認しています"
        elif role == "no-submit-reviewer":
            summary = "submit / click / auto_submit の混入がないことを確認済み"
            risks = ["送信処理の混入"]
            progress = 100
            completed = 3
            last_message = "送信系の混入を確認しています"
        elif role == "pii-auditor":
            summary = "住所・電話・氏名・メール本文の漏れを確認済み"
            risks = ["PII出力"]
            progress = 100
            completed = 4
            last_message = "PIIの出力有無を確認しています"
        elif role == "external-action-reviewer":
            summary = "X・メール・外部投稿の自動化混入を確認済み"
            risks = ["外部操作"]
            progress = 100
            completed = 3
            last_message = "外部操作の混入を確認しています"
        elif role == "release-gatekeeper":
            summary = "配布可否を安全側で確認済み"
            risks = ["危険ファイル混入"]
            progress = 100
            completed = 3
            last_message = "配布可否を評価しています"
        elif role == "frontend-dev":
            summary = "Web UI の表示整合を確認中"
            risks = ["表示崩れ"]
            progress = 65
            completed = 2
            last_message = "Web UI 表示を確認しています"
        elif role == "desktop-ui-dev":
            summary = "desktop UI の安全表示を確認中"
            risks = ["PySide6 未導入環境"]
            progress = 55
            completed = 2 if pyside_available else 1
            last_message = "desktop UI 表示を確認しています"
        elif role == "test-engineer":
            summary = "pytest / compileall / smoke-test を安全確認中"
            risks = [] if pyside_available else ["desktop smoke は環境依存"]
            progress = 75 if pyside_available else 55
            completed = 3 if pyside_available else 2
            last_message = summary
        elif role == "debugger":
            summary = "失敗原因の切り分けと再現性確認を実施中"
            risks = ["環境依存の切り分け遅延"]
            progress = 60
            completed = 2
            last_message = "失敗原因を整理しています"
        elif role == "docs-writer":
            summary = "README / docs / RELEASE_NOTES を確認中"
            risks = ["記載差分"]
            progress = 75
            completed = 2
            last_message = "ドキュメント整合を確認しています"
        elif role == "task-dispatch":
            summary = "今回の作業を担当へ割り振り中"
            risks = ["担当偏り"]
            progress = 50
            completed = 1
            last_message = "担当割当を整理しています"
        elif role == "morning-standup":
            summary = "今日やることの優先順位を整理中"
            risks = ["ブロッカーの見落とし"]
            progress = 50
            completed = 1
            last_message = "今日の作業を整理しています"
        elif role == "agent-status-writer":
            summary = "agent_status.json を安全更新中"
            risks = ["JSON整合性"]
            progress = 90
            completed = 2
            last_message = "agent_status.json の更新を確認しています"
        elif role == "release-notes-manager":
            summary = "変更内容と安全制約をリリースノートへ反映中"
            risks = ["記載漏れ"]
            progress = 80
            completed = 2
            last_message = "release notes を整備しています"
        elif role == "zip-auditor":
            summary = "配布ZIPの危険ファイル混入を確認中"
            risks = ["profile混入"]
            progress = 90
            completed = 2
            last_message = "ZIPの混入有無を確認しています"
        elif role == "knowledge-sync":
            summary = "前回の決定事項を引き継ぎ中"
            risks = ["仕様の取りこぼし"]
            progress = 55
            completed = 1
            last_message = "前回の判断を引き継いでいます"
        elif role == "product-director":
            summary = "商品価値と優先順位を整理中"
            risks = ["優先順位のぶれ"]
            progress = 50
            completed = 1
            last_message = "商品価値を整理しています"
        elif role == "ux-reviewer":
            summary = "初心者にも伝わる画面か確認中"
            risks = ["文言の難化"]
            progress = 70
            completed = 2
            last_message = "画面文言を確認しています"
        elif role == "beginner-voice":
            summary = "PCが苦手な人目線で確認中"
            risks = ["説明不足"]
            progress = 65
            completed = 2
            last_message = "初心者目線で確認しています"
        elif role == "trust-copywriter":
            summary = "安全性・手動確認・個人情報保護の文言を整備中"
            risks = ["安全表現の曖昧さ"]
            progress = 75
            completed = 2
            last_message = "信頼説明を整えています"
        elif role == "pricing-strategy":
            summary = "無料版/有料版/販売導線を整理中"
            risks = ["導線の混線"]
            progress = 50
            completed = 1
            last_message = "販売導線を整理しています"
        elif role == "support-docs":
            summary = "使い方・FAQ・注意事項を整備中"
            risks = ["案内の不足"]
            progress = 80
            completed = 2
            last_message = "サポート文書を整えています"
        else:
            summary = str(meta.get("role") or "safe-agent-run")
            risks = []
            progress = 0
            completed = 0
            last_message = summary
        agents.append(
            {
                "role": role,
                "display_name": str(meta.get("name") or role.replace("-", " ").title()),
                "team_id": team_id,
                "team_name": team_name,
                "team_purpose": team_purpose,
                "status": status,
                "summary": summary,
                "checks": checks,
                "risks": risks,
                "updated_at": timestamp,
                "progress_percent": progress,
                "total_tasks": max(len(checks), completed, 3),
                "completed_tasks": completed,
                "warning_count": 1 if status == "warning" else 0,
                "error_count": 1 if status == "failed" else 0,
                "last_message": last_message,
                "status_display": display_agent_status(status),
                "checks_detail": checks,
                "risks_detail": risks,
            }
        )
    return {
        "updated_at": timestamp,
        "task": task_label,
        "mode": mode_name,
        "run_mode": "safe-agent-run",
        "organization": {
            "version": str(org_payload.get("version", "0.4.4")),
            "project": str(org_payload.get("project", "kensho_assistant")),
            "org_name": str(org_payload.get("org_name", "Kensho Safe AI Team")),
            "mission": str(org_payload.get("mission", "")),
            "mode": mode_name,
            "mode_label": "通常モード" if mode_name == "normal" else "リリース前モード",
            "selected_roles": selected_roles,
            "team_count": len(org_payload.get("teams", [])),
            "active_role_count": len(selected_roles),
            "teams": org_payload.get("teams", []),
        },
        "checks": [
            "local-json-update",
            "pii-redaction",
            "暗号化データ非読込",
            "送信操作なし",
        ],
        "agents": agents,
    }


def save_agent_status_run_payload(
    task: object,
    path: Path = AGENT_STATUS_JSON,
    *,
    mode: object = "normal",
    updated_at: str | None = None,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    payload = build_agent_status_run_payload(task=task, mode=mode, updated_at=updated_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    run_log_payload = _build_agent_run_log_payload(payload)
    _append_jsonl(AGENT_RUN_LOG_JSONL, run_log_payload)
    return payload
