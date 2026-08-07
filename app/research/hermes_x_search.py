from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from ..paths import RESEARCH_X_DIR, RESEARCH_X_DIAGNOSTICS_JSON, RESEARCH_X_HARNESS_DIAGNOSTICS_JSON, ensure_runtime_dirs
from ..privacy_guard import mask_email, redact_personal_info
from ..storage import write_csv_rows
from .x_campaign_filter import apply_x_campaign_filter
from .x_campaign_parser import normalize_x_campaigns, x_campaign_fields


@dataclass
class HermesSearchError(RuntimeError):
    message: str
    command: list[str] | None = None
    timeout_sec: int | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def build_hermes_x_search_check_prompt() -> str:
    return (
        'x_searchを使って、Xで「from:tetumemo Hermes Agent」を検索してください。\n'
        "直近の関連投稿があれば、投稿URL、投稿者、要点をJSON配列だけで返してください。\n"
        "見つからなければ空配列 [] を返してください。\n"
        "Markdownは禁止です。"
    )


def _mask_secret_like_text(text: str) -> str:
    safe = redact_personal_info(text or "")
    safe = mask_email(safe)
    safe = re.sub(r"(?i)\b(api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|bearer\s+token|token)\b\s*[:=]\s*([^\s,;\"']+)", r"\1=[redacted]", safe)
    safe = re.sub(r"(?i)\b(sk-[A-Za-z0-9]{10,}|xox[baprs]-[A-Za-z0-9-]+|gh[pousr]_[A-Za-z0-9_]+)\b", "[redacted]", safe)
    return safe


def mask_hermes_output(text: str) -> str:
    return _mask_secret_like_text(text or "")


def _classify_hermes_failure(
    *,
    command: list[str],
    stdout: str,
    stderr: str,
    returncode: int | None = None,
    timed_out: bool = False,
    exc: BaseException | None = None,
    invalid_json: bool = False,
) -> tuple[str, str]:
    text = f"{stdout}\n{stderr}\n{exc or ''}".casefold()
    command_text = " ".join(command).casefold()
    if timed_out:
        return "timeout", "Hermes 呼び出しがタイムアウトしました"
    if isinstance(exc, FileNotFoundError):
        if command and command[0].casefold() == "wsl":
            return "wsl_not_found", "wsl コマンドが見つかりません"
        return "command_not_found", "Hermes 接続コマンドが見つかりません"
    if returncode == 127 and command_text.startswith("wsl "):
        return "hermes_not_found", "WSL 内で Hermes が見つかりません"
    if returncode == 127 and command_text.startswith("hermes "):
        return "hermes_not_found", "Hermes コマンドが見つかりません"
    if "x_search" in text and any(token in text for token in ("disabled", "not enabled", "tool unavailable", "unavailable")):
        return "x_search_disabled", "Hermes 側で x_search が無効です"
    if any(
        token in text
        for token in (
            "xai oauth",
            "xai-oauth",
            "oauth",
            "authentication required",
            "auth required",
            "login required",
            "unauthorized",
            "401",
            "isn't configured yet",
            "no api keys or providers found",
            "hermes setup",
        )
    ):
        return "xai_auth_missing", "XAI 認証が不足しています"
    if "hermes" in text and any(token in text for token in ("command not found", "not found", "no such file", "exit code 127")):
        return "hermes_not_found", "Hermes コマンドが見つかりません"
    if invalid_json:
        return "invalid_json", "Hermes の返答が JSON として解釈できません"
    return "unknown_error", "原因を特定できませんでした"


def _parse_json_array(text: str) -> list[object] | None:
    candidate = (text or "").strip()
    if not candidate:
        return []
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed
    return None


def save_hermes_x_search_check(report: dict[str, object]) -> Path:
    RESEARCH_X_DIAGNOSTICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_X_DIAGNOSTICS_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return RESEARCH_X_DIAGNOSTICS_JSON


def _normalize_day(day: str | date | None) -> str:
    if day is None:
        return date.today().strftime("%Y%m%d")
    if isinstance(day, date):
        return day.strftime("%Y%m%d")
    text = str(day).strip()
    if not text:
        return date.today().strftime("%Y%m%d")
    if "-" in text:
        try:
            return datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            return date.today().strftime("%Y%m%d")
    if len(text) == 8 and text.isdigit():
        return text
    return date.today().strftime("%Y%m%d")


def _normalize_timeout(timeout_sec: int | float | str | None = None) -> int:
    if timeout_sec is None:
        timeout_sec = os.getenv("KENSHO_HERMES_TIMEOUT_SEC", "60")
    try:
        value = int(float(timeout_sec))
    except (TypeError, ValueError):
        value = 60
    return max(5, value)


def _command_prefix(command: str | None = None) -> list[str]:
    value = command or os.getenv("KENSHO_HERMES_COMMAND", "").strip()
    if value:
        return shlex.split(value, posix=os.name != "nt")
    if os.name == "nt":
        return ["wsl", "hermes", "chat", "-q"]
    return ["hermes", "chat", "-q"]


def x_campaign_day_dir(day: str | date | None = None) -> Path:
    return RESEARCH_X_DIR / _normalize_day(day)


def x_campaign_candidates_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "hermes_candidates.json"


def x_campaign_csv_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "hermes_candidates.csv"


def x_campaign_run_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "hermes_run.json"


def x_campaign_queue_export_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "queue_export.json"


def x_campaign_selection_log_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "selection_log.jsonl"


def x_campaign_prepare_log_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "prepare_log.jsonl"


def x_campaign_csv_headers() -> list[str]:
    return list(x_campaign_fields)


DAILY_SAFE_PRESET_QUERIES = [
    "懸賞 プレゼントキャンペーン 締切 今週 食品",
    "懸賞 プレゼントキャンペーン 締切 今週 日用品",
    "懸賞 プレゼントキャンペーン 締切 今週 子育て",
    "フォロー リポスト キャンペーン 締切 食品",
    "プレゼント企画 公式 締切 メーカー",
    "キャンペーン 抽選 プレゼント 公式 日本国内",
]


def daily_safe_queries() -> list[str]:
    return list(DAILY_SAFE_PRESET_QUERIES)


def build_hermes_prompt(query: str) -> str:
    return (
        "あなたは日本国内向けの懸賞リサーチ担当です。\n"
        "x_search を使って、以下の条件に合うX投稿を探してください。\n\n"
        f"検索条件:\n{query}\n\n"
        "必ず以下のJSON配列だけで返してください。\n"
        "Markdownや説明文は不要です。\n\n"
        "[\n"
        "  {\n"
        '    "title": "...",\n'
        '    "organizer": "...",\n'
        '    "account_handle": "...",\n'
        '    "post_url": "...",\n'
        '    "campaign_url": "...",\n'
        '    "prize": "...",\n'
        '    "deadline": "...",\n'
        '    "requirements": ["フォロー", "リポスト", "..."],\n'
        '    "eligibility": "...",\n'
        '    "age_requirement": "...",\n'
        '    "region_requirement": "...",\n'
        '    "risk_flags": [],\n'
        '    "confidence": 0.0\n'
        "  }\n"
        "]\n\n"
        "条件:\n"
        "- URLが確認できないものは除外\n"
        "- 現金配布、投資、FX、仮想通貨、LINE誘導、DMで個人情報要求は risk_flags に入れる\n"
        "- 日本国内から応募できそうなものを優先\n"
        "- 締切が近いものを優先\n"
        "- 公式企業アカウントや自治体、店舗、メーカーを優先\n"
        "- 怪しい個人アカウントは低confidenceにする\n"
    )


def _normalize_text_for_match(value: object) -> str:
    return re.sub(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠]+", "", str(value or "").casefold())


def _normalize_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text.casefold().rstrip("/")
    if not parsed.scheme and not parsed.netloc:
        return text.casefold().rstrip("/")
    cleaned = parsed._replace(query="", fragment="")
    return urlunsplit(cleaned).casefold().rstrip("/")


def _candidate_identity_text(candidate: dict[str, object]) -> str:
    return " ".join(
        [
            _normalize_text_for_match(candidate.get("title")),
            _normalize_text_for_match(candidate.get("organizer")),
            _normalize_text_for_match(candidate.get("prize")),
        ]
    )


def _candidate_score_tuple(candidate: dict[str, object]) -> tuple[int, int, int, float, int]:
    try:
        total_score = int(float(candidate.get("total_score", 0) or 0))
    except (TypeError, ValueError):
        total_score = 0
    try:
        safety_score = int(float(candidate.get("safety_score", 0) or 0))
    except (TypeError, ValueError):
        safety_score = 0
    try:
        trust_score = int(float(candidate.get("trust_score", 0) or 0))
    except (TypeError, ValueError):
        trust_score = 0
    try:
        confidence = float(candidate.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        deadline_score = int(float(candidate.get("deadline_score", 0) or 0))
    except (TypeError, ValueError):
        deadline_score = 0
    return (total_score, safety_score, trust_score, confidence, deadline_score)


def _candidate_sort_key(candidate: dict[str, object]) -> tuple[int, int, int, float, int, str, str]:
    total_score, safety_score, trust_score, confidence, deadline_score = _candidate_score_tuple(candidate)
    recommendation = str(candidate.get("recommendation", "watch"))
    recommendation_order = {"review": 0, "watch": 1, "skip": 2}.get(recommendation, 3)
    return (
        recommendation_order,
        -total_score,
        -safety_score,
        -trust_score,
        -confidence,
        -deadline_score,
        str(candidate.get("deadline", "")),
        str(candidate.get("title", "")),
    )


def _is_similar_candidate(base: dict[str, object], other: dict[str, object]) -> bool:
    base_text = _candidate_identity_text(base)
    other_text = _candidate_identity_text(other)
    if not base_text or not other_text:
        return False
    if base_text == other_text:
        return True
    ratio = SequenceMatcher(None, base_text, other_text).ratio()
    if ratio >= 0.88:
        return True
    base_tokens = set(re.findall(r"[0-9A-Za-zぁ-んァ-ヶ一-龠]+", base_text))
    other_tokens = set(re.findall(r"[0-9A-Za-zぁ-んァ-ヶ一-龠]+", other_text))
    if not base_tokens or not other_tokens:
        return False
    overlap = len(base_tokens & other_tokens) / max(len(base_tokens | other_tokens), 1)
    return overlap >= 0.75 and ratio >= 0.72


def x_campaign_raw_results_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "hermes_raw_results.json"


def x_campaign_deduped_candidates_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "hermes_deduped_candidates.json"


def x_campaign_duplicates_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "hermes_duplicates.json"


def x_campaign_quality_report_json_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "research_quality_report.json"


def x_campaign_quality_report_md_path(day: str | date | None = None) -> Path:
    return x_campaign_day_dir(day) / "research_quality_report.md"


def _run_command(command: list[str], timeout_sec: int) -> dict[str, object]:
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "status": "unavailable",
            "error": f"Hermes command not found: {exc}",
            "command": command,
            "stdout": "",
            "stderr": "",
            "returncode": 127,
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "status": "timeout",
            "error": f"Hermes command timed out after {timeout_sec} seconds",
            "command": command,
            "stdout": "",
            "stderr": "",
            "returncode": 124,
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }

    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    ok = completed.returncode == 0
    return {
        "ok": ok,
        "status": "ok" if ok else "error",
        "error": "" if ok else (completed.stderr.strip() or f"Hermes returned {completed.returncode}"),
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def run_hermes_x_search_check(
    *,
    command: str | None = None,
    timeout_sec: int | float | str | None = None,
) -> dict[str, object]:
    ensure_runtime_dirs()
    timeout_value = _normalize_timeout(timeout_sec or os.getenv("KENSHO_HERMES_TIMEOUT_SEC", "120"))
    command_parts = _command_prefix(command)
    prompt = build_hermes_x_search_check_prompt()
    full_command = [*command_parts, prompt]
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    raw_stdout = ""
    raw_stderr = ""
    returncode: int | None = None
    status = "failed"
    reason = "unknown_error"
    parsed: list[object] | None = None
    exception: BaseException | None = None
    try:
        completed = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_value,
            check=False,
        )
        returncode = completed.returncode
        raw_stdout = completed.stdout or ""
        raw_stderr = completed.stderr or ""
        parsed = _parse_json_array(raw_stdout)
        if completed.returncode == 0 and parsed is not None:
            status = "success"
            reason = "ok"
        else:
            reason, _ = _classify_hermes_failure(
                command=full_command,
                stdout=raw_stdout,
                stderr=raw_stderr,
                returncode=completed.returncode,
                invalid_json=parsed is None,
            )
    except FileNotFoundError as exc:
        exception = exc
        returncode = 127
        reason, _ = _classify_hermes_failure(command=full_command, stdout="", stderr="", exc=exc)
    except subprocess.TimeoutExpired as exc:
        exception = exc
        returncode = 124
        reason, _ = _classify_hermes_failure(command=full_command, stdout="", stderr="", timed_out=True, exc=exc)
    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    masked_stdout = mask_hermes_output(raw_stdout)
    masked_stderr = mask_hermes_output(raw_stderr)
    report = {
        "kind": "hermes_x_search_check",
        "checked_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "reason": reason,
        "command": full_command,
        "timeout_sec": timeout_value,
        "exit_code": returncode,
        "stdout": masked_stdout,
        "stderr": masked_stderr,
        "parsed_count": len(parsed) if isinstance(parsed, list) else 0,
        "output_file": str(RESEARCH_X_DIAGNOSTICS_JSON),
    }
    if exception is not None:
        report["exception"] = mask_hermes_output(str(exception))
    save_hermes_x_search_check(report)
    return report


def _csv_row(candidate: dict[str, object]) -> dict[str, object]:
    row = dict(candidate)
    for key in ("requirements", "risk_flags"):
        value = row.get(key, [])
        if isinstance(value, list):
            row[key] = json.dumps(value, ensure_ascii=False)
    return row


def _queue_export_row(
    candidate: dict[str, object],
    *,
    status: str,
    notes: str = "",
    selected_at: str = "",
    prepared_at: str = "",
    day: str | date | None = None,
) -> dict[str, object]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "id": str(candidate.get("candidate_id", "")),
        "source": str(candidate.get("source", "x_hermes")),
        "platform": str(candidate.get("platform", "x")),
        "title": str(candidate.get("title", "")),
        "organizer": str(candidate.get("organizer", "")),
        "account_handle": str(candidate.get("account_handle", "")),
        "post_url": str(candidate.get("post_url", "")),
        "campaign_url": str(candidate.get("campaign_url", "")),
        "prize": str(candidate.get("prize", "")),
        "deadline": str(candidate.get("deadline", "")),
        "requirements": list(candidate.get("requirements", [])) if isinstance(candidate.get("requirements", []), list) else [],
        "eligibility": str(candidate.get("eligibility", "")),
        "age_requirement": str(candidate.get("age_requirement", "")),
        "region_requirement": str(candidate.get("region_requirement", "")),
        "risk_flags": list(candidate.get("risk_flags", [])) if isinstance(candidate.get("risk_flags", []), list) else [],
        "safety_score": candidate.get("safety_score", 0),
        "trust_score": candidate.get("trust_score", 0),
        "ease_score": candidate.get("ease_score", 0),
        "value_score": candidate.get("value_score", 0),
        "total_score": candidate.get("total_score", 0),
        "recommendation": str(candidate.get("recommendation", "")),
        "recommendation_reason": str(candidate.get("recommendation_reason", "")),
        "status": status,
        "selected_at": selected_at,
        "prepared_at": prepared_at,
        "raw_source_path": str(x_campaign_deduped_candidates_path(day)),
        "notes": notes,
        "updated_at": now,
        "collected_at": str(candidate.get("collected_at", "")),
        "candidate_id": str(candidate.get("candidate_id", "")),
        "queue_status": status,
        "queue_reason": notes,
        "confidence": candidate.get("confidence", 0.0),
    }


def _load_json_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_json_list(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _mask_queue_notes(value: str) -> str:
    return mask_hermes_output(value or "")


def _candidate_lookup(rows: Iterable[dict[str, object]], candidate_id: str = "", post_url: str = "") -> dict[str, object]:
    normalized_post_url = _normalize_url(post_url)
    for candidate in rows:
        if candidate_id and str(candidate.get("candidate_id", "")) == candidate_id:
            return candidate
        if normalized_post_url and _normalize_url(candidate.get("post_url")) == normalized_post_url:
            return candidate
    return {}


def _queue_export_rows_from_candidates(
    candidates: Iterable[dict[str, object]],
    *,
    day: str | date | None = None,
    existing_rows: Iterable[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    existing_map: dict[str, dict[str, object]] = {}
    if existing_rows is not None:
        for row in existing_rows:
            if not isinstance(row, dict):
                continue
            key = str(row.get("candidate_id", "")) or _normalize_url(row.get("post_url"))
            if key:
                existing_map[key] = row
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        recommendation = str(candidate.get("recommendation", ""))
        if recommendation != "review":
            continue
        existing = existing_map.get(str(candidate.get("candidate_id", ""))) or existing_map.get(_normalize_url(candidate.get("post_url")))
        status = str(existing.get("status", "")) if existing else ""
        if status not in {"review_pending", "user_selected", "apply_prepare_only", "skipped"}:
            status = "review_pending"
        rows.append(
            _queue_export_row(
                candidate,
                status=status,
                notes=str(existing.get("notes", "")) if existing else (str(candidate.get("queue_reason", "")) or str(candidate.get("recommendation_reason", "")) or "人間確認へ送る"),
                selected_at=str(existing.get("selected_at", "")) if existing else str(candidate.get("selected_at", "")),
                prepared_at=str(existing.get("prepared_at", "")) if existing else str(candidate.get("prepared_at", "")),
                day=day,
            )
        )
    rows.sort(key=lambda row: (0 if row.get("status") == "review_pending" else 1 if row.get("status") == "user_selected" else 2 if row.get("status") == "apply_prepare_only" else 3, -int(float(row.get("total_score", 0) or 0)), -int(float(row.get("safety_score", 0) or 0)), str(row.get("deadline", "")), str(row.get("title", ""))))
    return rows


def load_x_campaign_queue_export(day: str | date | None = None) -> list[dict[str, object]]:
    normalized_day = _normalize_day(day if day is not None else latest_x_campaign_day())
    path = x_campaign_queue_export_path(normalized_day)
    rows = _load_json_list(path)
    if rows:
        return rows
    candidates = load_x_campaign_candidates(normalized_day)
    return _queue_export_rows_from_candidates(candidates, day=normalized_day)


def save_x_campaign_queue_export(rows: Iterable[dict[str, object]], day: str | date | None = None) -> Path:
    normalized_day = _normalize_day(day if day is not None else latest_x_campaign_day())
    path = x_campaign_queue_export_path(normalized_day)
    _write_json_list(path, list(rows))
    return path


def log_x_campaign_queue_action(
    *,
    day: str | date | None = None,
    action: str,
    candidate: dict[str, object],
    reason: str = "",
    target_url: str = "",
) -> Path:
    normalized_day = _normalize_day(day if day is not None else latest_x_campaign_day())
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    payload = {
        "timestamp": now,
        "action": action,
        "candidate_id": candidate.get("candidate_id", ""),
        "post_url": candidate.get("post_url", ""),
        "campaign_url": candidate.get("campaign_url", ""),
        "status": candidate.get("status", candidate.get("queue_status", "")),
        "risk_flags": candidate.get("risk_flags", []),
        "reason": _mask_queue_notes(reason),
        "target_url": target_url,
    }
    if action == "opened_prepare":
        path = x_campaign_prepare_log_path(normalized_day)
    else:
        path = x_campaign_selection_log_path(normalized_day)
    _append_jsonl(path, payload)
    return path


def _collect_raw_result(
    *,
    query: str,
    run: dict[str, object],
    raw_candidates: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "query": query,
        "status": run.get("status", "error"),
        "error": mask_hermes_output(str(run.get("error", ""))),
        "returncode": run.get("returncode"),
        "command": run.get("command", []),
        "started_at": run.get("started_at", ""),
        "finished_at": run.get("finished_at", ""),
        "stdout": mask_hermes_output(str(run.get("stdout", ""))),
        "stderr": mask_hermes_output(str(run.get("stderr", ""))),
        "parsed_count": len(raw_candidates),
        "candidates": raw_candidates,
    }


def dedupe_x_campaign_candidates(candidates: Iterable[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ordered = sorted(list(candidates), key=_candidate_sort_key)
    deduped: list[dict[str, object]] = []
    duplicates: list[dict[str, object]] = []
    by_post_url: dict[str, dict[str, object]] = {}
    by_campaign_url: dict[str, dict[str, object]] = {}
    for candidate in ordered:
        post_url = _normalize_url(candidate.get("post_url"))
        campaign_url = _normalize_url(candidate.get("campaign_url"))
        matched: dict[str, object] | None = None
        duplicate_reason = ""
        if post_url and post_url in by_post_url:
            matched = by_post_url[post_url]
            duplicate_reason = "post_url"
        elif campaign_url and campaign_url in by_campaign_url:
            matched = by_campaign_url[campaign_url]
            duplicate_reason = "campaign_url"
        else:
            for canonical in deduped:
                if _is_similar_candidate(canonical, candidate):
                    matched = canonical
                    duplicate_reason = "title_organizer_prize_similarity"
                    break
        if matched is not None:
            duplicates.append(
                {
                    **candidate,
                    "duplicate_of": matched.get("candidate_id", ""),
                    "duplicate_reason": duplicate_reason,
                }
            )
            continue
        deduped.append(candidate)
        if post_url:
            by_post_url[post_url] = candidate
        if campaign_url:
            by_campaign_url[campaign_url] = candidate
    return deduped, duplicates


def _count_reasons(items: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    counter: Counter[str] = Counter()
    for item in items:
        for flag in item.get("risk_flags", []) if isinstance(item.get("risk_flags"), list) else []:
            counter[str(flag)] += 1
        reason = str(item.get("duplicate_reason", "")).strip()
        if reason:
            counter[reason] += 1
        recommendation = str(item.get("recommendation_reason", "")).strip()
        if recommendation and item.get("recommendation") == "skip":
            counter[recommendation.split(" / ", 1)[0]] += 1
    return [{"reason": reason, "count": count} for reason, count in counter.most_common()]


def _top_examples(candidates: list[dict[str, object]], *, limit: int = 10) -> list[dict[str, object]]:
    examples: list[dict[str, object]] = []
    for candidate in candidates[:limit]:
        examples.append(
            {
                "candidate_id": candidate.get("candidate_id", ""),
                "title": candidate.get("title", ""),
                "organizer": candidate.get("organizer", ""),
                "prize": candidate.get("prize", ""),
                "deadline": candidate.get("deadline", ""),
                "recommendation": candidate.get("recommendation", ""),
                "recommendation_reason": candidate.get("recommendation_reason", ""),
                "total_score": candidate.get("total_score", 0),
                "safety_score": candidate.get("safety_score", 0),
                "risk_flags": candidate.get("risk_flags", []),
            }
        )
    return examples


def _improvement_queries(report: dict[str, object], queries: list[str]) -> list[str]:
    ranked_reasons = [str(item.get("reason", "")) for item in report.get("exclusion_reason_ranking", []) if str(item.get("reason", "")).strip()]
    suggestions = list(dict.fromkeys(queries))
    if "LINE誘導" in ranked_reasons or "DMで個人情報要求" in ranked_reasons:
        suggestions.append("懸賞 プレゼントキャンペーン 公式 フォロー リポスト 日本国内")
    if "締切不明" in ranked_reasons:
        suggestions.append("懸賞 プレゼントキャンペーン 締切 公式 今週")
    if "主催者不明" in ranked_reasons:
        suggestions.append("プレゼント企画 公式 メーカー 自治体")
    if "日本国外向け" in ranked_reasons:
        suggestions.append("懸賞 プレゼントキャンペーン 日本国内 公式")
    return list(dict.fromkeys(suggestions))[:8]


def build_x_campaign_quality_report(
    *,
    generated_at: str,
    day: str,
    queries: list[str],
    raw_results: list[dict[str, object]],
    raw_candidates: list[dict[str, object]],
    deduped_candidates: list[dict[str, object]],
    duplicates: list[dict[str, object]],
    hermes_failures: list[dict[str, object]],
) -> dict[str, object]:
    review_count = sum(1 for item in deduped_candidates if item.get("recommendation") == "review")
    watch_count = sum(1 for item in deduped_candidates if item.get("recommendation") == "watch")
    skip_count = sum(1 for item in deduped_candidates if item.get("recommendation") == "skip")
    report = {
        "generated_at": generated_at,
        "day": day,
        "queries": queries,
        "raw_count": len(raw_candidates),
        "deduped_count": len(deduped_candidates),
        "review_count": review_count,
        "watch_count": watch_count,
        "skip_count": skip_count,
        "duplicate_count": len(duplicates),
        "raw_results_count": len(raw_results),
        "hermes_failures": hermes_failures,
        "top_candidates": _top_examples(deduped_candidates),
        "suspicious_examples": _top_examples(
            [item for item in deduped_candidates if item.get("recommendation") == "skip" or int(float(item.get("safety_score", 0) or 0)) < 50]
        ),
        "exclusion_reason_ranking": _count_reasons([*duplicates, *[item for item in deduped_candidates if item.get("recommendation") == "skip"]]),
        "improvement_queries": [],
        "raw_results_path": str(x_campaign_raw_results_path(day)),
        "deduped_candidates_path": str(x_campaign_deduped_candidates_path(day)),
        "duplicates_path": str(x_campaign_duplicates_path(day)),
        "report_path": str(x_campaign_quality_report_json_path(day)),
    }
    report["improvement_queries"] = _improvement_queries(report, queries)
    return report


def _render_quality_report_md(report: dict[str, object]) -> str:
    lines = [
        "# X 懸賞リサーチ品質レポート",
        "",
        f"- 実行日時: {report.get('generated_at', '')}",
        f"- 対象日: {report.get('day', '')}",
        f"- raw件数: {report.get('raw_count', 0)}",
        f"- dedupe後件数: {report.get('deduped_count', 0)}",
        f"- review件数: {report.get('review_count', 0)}",
        f"- watch件数: {report.get('watch_count', 0)}",
        f"- skip件数: {report.get('skip_count', 0)}",
        "",
        "## 実行クエリ",
    ]
    for query in report.get("queries", []):
        lines.append(f"- {query}")
    lines.extend(["", "## 除外理由ランキング"])
    for item in report.get("exclusion_reason_ranking", [])[:10]:
        lines.append(f"- {item.get('reason', '')}: {item.get('count', 0)}")
    lines.extend(["", "## 上位10候補"])
    for item in report.get("top_candidates", [])[:10]:
        lines.append(f"- {item.get('title', '')} / {item.get('organizer', '')} / {item.get('recommendation', '')} / {item.get('total_score', 0)}")
    lines.extend(["", "## 怪しい候補の例"])
    for item in report.get("suspicious_examples", [])[:10]:
        lines.append(f"- {item.get('title', '')} / {item.get('recommendation_reason', '')}")
    lines.extend(["", "## 次に改善すべき検索クエリ"])
    for query in report.get("improvement_queries", [])[:10]:
        lines.append(f"- {query}")
    return "\n".join(lines) + "\n"


def save_x_campaign_outputs(
    candidates: Iterable[dict[str, object]],
    run_report: dict[str, object],
    *,
    day: str | date | None = None,
    raw_results: list[dict[str, object]] | None = None,
    duplicates: list[dict[str, object]] | None = None,
    quality_report: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    ensure_runtime_dirs()
    day_dir = x_campaign_day_dir(day)
    day_dir.mkdir(parents=True, exist_ok=True)
    candidates_list = list(candidates)
    candidates_path = x_campaign_candidates_path(day)
    deduped_candidates_path = x_campaign_deduped_candidates_path(day)
    raw_results_path = x_campaign_raw_results_path(day)
    duplicates_path = x_campaign_duplicates_path(day)
    report_json_path = x_campaign_quality_report_json_path(day)
    report_md_path = x_campaign_quality_report_md_path(day)
    queue_export_path = x_campaign_queue_export_path(day)
    csv_path = x_campaign_csv_path(day)
    run_path = x_campaign_run_path(day)
    existing_queue_rows = _load_json_list(queue_export_path)
    candidates_path.write_text(json.dumps(candidates_list, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    deduped_candidates_path.write_text(json.dumps(candidates_list, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv_rows(csv_path, [_csv_row(candidate) for candidate in candidates_list], x_campaign_csv_headers())
    run_path.write_text(json.dumps(run_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if raw_results is not None:
        raw_results_path.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if duplicates is not None:
        duplicates_path.write_text(json.dumps(duplicates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if quality_report is not None:
        report_json_path.write_text(json.dumps(quality_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_md_path.write_text(_render_quality_report_md(quality_report), encoding="utf-8")
    _write_json_list(queue_export_path, _queue_export_rows_from_candidates(candidates_list, day=day, existing_rows=existing_queue_rows))
    return candidates_path, csv_path, run_path


def research_x_campaigns_for_queries(
    queries: Iterable[str],
    *,
    limit: int = 20,
    day: str | date | None = None,
    timeout_sec: int | float | str | None = None,
    command: str | None = None,
    preset: str = "",
) -> dict[str, object]:
    ensure_runtime_dirs()
    timeout_value = _normalize_timeout(timeout_sec)
    command_parts = _command_prefix(command)
    normalized_queries = [str(query).strip() for query in queries if str(query).strip()]
    raw_results: list[dict[str, object]] = []
    scored_candidates: list[dict[str, object]] = []
    hermes_failures: list[dict[str, object]] = []
    for query in normalized_queries:
        prompt = build_hermes_prompt(query)
        full_command = [*command_parts, prompt]
        run = _run_command(full_command, timeout_value)
        raw_text = str(run.get("stdout", "")) if run.get("ok") else ""
        parsed_candidates = normalize_x_campaigns(raw_text, query=query)
        scored = apply_x_campaign_filter(parsed_candidates)
        scored_candidates.extend(scored)
        raw_results.append(_collect_raw_result(query=query, run=run, raw_candidates=scored))
        if run.get("status") != "ok" or not run.get("ok"):
            reason, _ = _classify_hermes_failure(
                command=full_command,
                stdout=str(run.get("stdout", "")),
                stderr=str(run.get("stderr", "")),
                returncode=int(run.get("returncode", 0) or 0) if run.get("returncode") is not None else None,
            )
            hermes_failures.append(
                {
                    "query": query,
                    "reason": reason,
                    "returncode": run.get("returncode"),
                    "error": mask_hermes_output(str(run.get("error", ""))),
                }
            )
    deduped_candidates, duplicates = dedupe_x_campaign_candidates(scored_candidates)
    deduped_candidates.sort(key=_candidate_sort_key)
    if limit > 0:
        deduped_candidates = deduped_candidates[:limit]
    failure_reasons = {str(item.get("reason", "")) for item in hermes_failures}
    if hermes_failures and scored_candidates:
        overall_status = "partial"
    elif hermes_failures and not scored_candidates:
        if failure_reasons & {"command_not_found", "wsl_not_found", "hermes_not_found"}:
            overall_status = "unavailable"
        else:
            overall_status = "failed"
    else:
        overall_status = "ok"
    run_report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "query": normalized_queries[0] if len(normalized_queries) == 1 else "",
        "queries": normalized_queries,
        "preset": preset,
        "limit": limit,
        "day": _normalize_day(day),
        "timeout_sec": timeout_value,
        "status": overall_status,
        "error": "" if overall_status not in {"failed", "unavailable"} else (hermes_failures[0]["reason"] if hermes_failures else "unknown_error"),
        "returncode": None,
        "command": command_parts,
        "started_at": raw_results[0]["started_at"] if raw_results else "",
        "finished_at": raw_results[-1]["finished_at"] if raw_results else "",
        "candidate_count": len(deduped_candidates),
        "raw_count": len(scored_candidates),
        "duplicate_count": len(duplicates),
        "review_count": sum(1 for item in deduped_candidates if item.get("recommendation") == "review"),
        "watch_count": sum(1 for item in deduped_candidates if item.get("recommendation") == "watch"),
        "skip_count": sum(1 for item in deduped_candidates if item.get("recommendation") == "skip"),
        "human_review_count": sum(1 for item in deduped_candidates if item.get("recommendation") == "review"),
        "blocked_count": sum(1 for item in deduped_candidates if item.get("recommendation") == "skip"),
        "source": "hermes_x_search",
        "hermes_failures": hermes_failures,
        "report_path": str(x_campaign_quality_report_json_path(day)),
    }
    quality_report = build_x_campaign_quality_report(
        generated_at=run_report["generated_at"],
        day=run_report["day"],
        queries=normalized_queries,
        raw_results=raw_results,
        raw_candidates=scored_candidates,
        deduped_candidates=deduped_candidates,
        duplicates=duplicates,
        hermes_failures=hermes_failures,
    )
    run_report["report_path"] = quality_report["report_path"]
    save_x_campaign_outputs(
        deduped_candidates,
        run_report,
        day=day,
        raw_results=raw_results,
        duplicates=duplicates,
        quality_report=quality_report,
    )
    return {
        "run": run_report,
        "candidates": deduped_candidates,
        "raw_results": raw_results,
        "duplicates": duplicates,
        "quality_report": quality_report,
    }


def research_x_campaigns(
    query: str,
    *,
    limit: int = 20,
    day: str | date | None = None,
    timeout_sec: int | float | str | None = None,
    command: str | None = None,
) -> dict[str, object]:
    return research_x_campaigns_for_queries([query], limit=limit, day=day, timeout_sec=timeout_sec, command=command)


def load_x_campaign_candidates(day: str | date | None = None) -> list[dict[str, object]]:
    normalized_day = _normalize_day(day if day is not None else latest_x_campaign_day())
    path = x_campaign_deduped_candidates_path(normalized_day)
    if not path.exists():
        path = x_campaign_candidates_path(normalized_day)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    candidates = [item for item in data if isinstance(item, dict)]
    candidates.sort(key=_candidate_sort_key)
    return candidates


def load_x_campaign_quality_report(day: str | date | None = None) -> dict[str, object]:
    normalized_day = _normalize_day(day if day is not None else latest_x_campaign_day())
    path = x_campaign_quality_report_json_path(normalized_day)
    if not path.exists():
        return {
            "generated_at": "",
            "day": normalized_day,
            "queries": [],
            "raw_count": 0,
            "deduped_count": 0,
            "review_count": 0,
            "watch_count": 0,
            "skip_count": 0,
            "duplicate_count": 0,
            "raw_results_count": 0,
            "hermes_failures": [],
            "top_candidates": [],
            "suspicious_examples": [],
            "exclusion_reason_ranking": [],
            "improvement_queries": [],
            "raw_results_path": str(x_campaign_raw_results_path(normalized_day)),
            "deduped_candidates_path": str(x_campaign_deduped_candidates_path(normalized_day)),
            "duplicates_path": str(x_campaign_duplicates_path(normalized_day)),
            "report_path": str(path),
        }
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "generated_at": "",
            "day": normalized_day,
            "queries": [],
            "raw_count": 0,
            "deduped_count": 0,
            "review_count": 0,
            "watch_count": 0,
            "skip_count": 0,
            "duplicate_count": 0,
            "raw_results_count": 0,
            "hermes_failures": [],
            "top_candidates": [],
            "suspicious_examples": [],
            "exclusion_reason_ranking": [],
            "improvement_queries": [],
            "raw_results_path": str(x_campaign_raw_results_path(normalized_day)),
            "deduped_candidates_path": str(x_campaign_deduped_candidates_path(normalized_day)),
            "duplicates_path": str(x_campaign_duplicates_path(normalized_day)),
            "report_path": str(path),
        }
    if not isinstance(report, dict):
        return {}
    return report


def load_x_campaign_run(day: str | date | None = None) -> dict[str, object]:
    normalized_day = _normalize_day(day if day is not None else latest_x_campaign_day())
    path = x_campaign_run_path(normalized_day)
    if not path.exists():
        return {
            "generated_at": "",
            "day": normalized_day,
            "status": "pending",
            "error": "",
            "returncode": None,
            "command": [],
            "started_at": "",
            "finished_at": "",
            "candidate_count": 0,
            "raw_count": 0,
            "duplicate_count": 0,
            "review_count": 0,
            "human_review_count": 0,
            "watch_count": 0,
            "skip_count": 0,
            "blocked_count": 0,
            "source": "hermes_x_search",
            "queries": [],
            "preset": "",
            "hermes_failures": [],
            "report_path": str(x_campaign_quality_report_json_path(normalized_day)),
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "generated_at": "",
            "day": normalized_day,
            "status": "unavailable",
            "error": "run file parse error",
            "returncode": None,
            "command": [],
            "started_at": "",
            "finished_at": "",
            "candidate_count": 0,
            "raw_count": 0,
            "duplicate_count": 0,
            "review_count": 0,
            "human_review_count": 0,
            "watch_count": 0,
            "skip_count": 0,
            "blocked_count": 0,
            "source": "hermes_x_search",
            "queries": [],
            "preset": "",
            "hermes_failures": [],
            "report_path": str(x_campaign_quality_report_json_path(normalized_day)),
        }


def available_x_campaign_days() -> list[str]:
    if not RESEARCH_X_DIR.exists():
        return []
    days = [path.name for path in RESEARCH_X_DIR.iterdir() if path.is_dir() and len(path.name) == 8 and path.name.isdigit()]
    days.sort()
    return days


def latest_x_campaign_day() -> str:
    days = available_x_campaign_days()
    return days[-1] if days else date.today().strftime("%Y%m%d")


def update_x_campaign_queue_state(
    candidate_id: str,
    *,
    day: str | date | None = None,
    queue_status: str,
    queue_reason: str = "",
    post_url: str = "",
) -> bool:
    day_value = _normalize_day(day if day is not None else latest_x_campaign_day())
    candidates = load_x_campaign_candidates(day_value)
    queue_rows = load_x_campaign_queue_export(day_value)
    updated = False
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    status_priority = {"review_pending": 0, "user_selected": 1, "apply_prepare_only": 2, "skipped": 3}
    candidate = _candidate_lookup(queue_rows or candidates, candidate_id=candidate_id, post_url=post_url)
    if not candidate:
        candidate = _candidate_lookup(candidates, candidate_id=candidate_id, post_url=post_url)
    if not candidate:
        return False
    normalized_status = queue_status or "review_pending"
    if normalized_status == "human_review":
        normalized_status = "review_pending"
    if normalized_status == "review_pending" and candidate.get("recommendation") != "review":
        return False
    if normalized_status == "user_selected" and candidate.get("recommendation") != "review":
        return False
    if normalized_status == "apply_prepare_only" and candidate.get("status") not in {"user_selected", "apply_prepare_only"}:
        return False
    for row in queue_rows:
        if str(row.get("candidate_id", "")) == str(candidate.get("candidate_id", "")) or _normalize_url(row.get("post_url")) == _normalize_url(candidate.get("post_url")):
            existing_status = str(row.get("status", ""))
            if status_priority.get(existing_status, 0) > status_priority.get(normalized_status, 0):
                normalized_status = existing_status
            row["status"] = normalized_status
            row["queue_status"] = normalized_status
            row["queue_reason"] = _mask_queue_notes(queue_reason or row.get("queue_reason", "") or "人間確認へ送る")
            row["notes"] = _mask_queue_notes(queue_reason or row.get("notes", "") or "")
            row["updated_at"] = now
            if normalized_status == "user_selected":
                row["selected_at"] = row.get("selected_at", "") or now
            if normalized_status == "apply_prepare_only":
                row["prepared_at"] = now
            updated = True
            break
    if not updated:
        queue_rows.append(
            _queue_export_row(
                candidate,
                status=normalized_status,
                notes=_mask_queue_notes(queue_reason or ""),
                selected_at=now if normalized_status == "user_selected" else "",
                prepared_at=now if normalized_status == "apply_prepare_only" else "",
            )
        )
        updated = True
    save_x_campaign_queue_export(queue_rows, day_value)
    log_x_campaign_queue_action(
        day=day_value,
        action="opened_prepare" if normalized_status == "apply_prepare_only" else "skipped" if normalized_status == "skipped" else "selected",
        candidate={**candidate, "status": normalized_status, "queue_status": normalized_status},
        reason=queue_reason,
        target_url=str(candidate.get("campaign_url", "")) or str(candidate.get("post_url", "")),
    )
    run = load_x_campaign_run(day_value)
    if run:
        run["human_review_count"] = sum(1 for item in queue_rows if item.get("status") == "review_pending")
        run["watch_count"] = sum(1 for item in queue_rows if item.get("status") == "apply_prepare_only")
        run["blocked_count"] = sum(1 for item in queue_rows if item.get("status") == "skipped")
        run["review_count"] = sum(1 for item in queue_rows if item.get("status") in {"review_pending", "user_selected", "apply_prepare_only"} and item.get("recommendation") == "review")
        run["skip_count"] = sum(1 for item in queue_rows if item.get("status") == "skipped")
        run["candidate_count"] = len(candidates)
        run["updated_at"] = now
    save_x_campaign_outputs(candidates, run or {"updated_at": now, "candidate_count": len(candidates)}, day=day_value)
    return True


X_RESEARCH_HERMES_DEFAULT_COMMAND = [
    "wsl",
    "-d",
    "Ubuntu",
    "--",
    "/home/goo10/.local/bin/hermes",
    "chat",
    "-q",
]
X_RESEARCH_HERMES_DEFAULT_TIMEOUT_SEC = 300
X_RESEARCH_HERMES_FIXED_QUERY = "Hermes Agent"


def build_hermes_x_search_diagnostic_prompt(query: str = X_RESEARCH_HERMES_FIXED_QUERY) -> str:
    return (
        f"x_searchを使って「{query}」をXで1件だけ検索してください。"
        '結果はJSON配列だけで返してください。形式は [{"post_url":"...","summary":"..."}]。'
        "見つからなければ [] を返してください。"
    )


def build_hermes_x_research_prompt(query: str) -> str:
    return (
        "あなたはX上の話題を調査するリサーチ担当です。\n"
        "x_searchを使って、次のテーマについて関連投稿を調べてください。\n\n"
        f"調査テーマ:\n{query}\n\n"
        "目的:\n"
        "- 関連投稿をURL付きで集める\n"
        "- 主張の要点を整理する\n"
        "- 誇張・怪しい点・確認不足を指摘する\n"
        "- 反対意見や補足情報も探す\n"
        "- note記事化に使える論点を抽出する\n\n"
        "必ずJSONだけで返してください。\n"
        "Markdownは禁止です。\n\n"
        "{\n"
        '  "topic": "...",\n'
        '  "related_posts": [\n'
        "    {\n"
        '      "author": "...",\n'
        '      "handle": "...",\n'
        '      "post_url": "...",\n'
        '      "text": "...",\n'
        '      "summary": "...",\n'
        '      "claim": "...",\n'
        '      "evidence_level": "high/medium/low",\n'
        '      "risk_flags": []\n'
        "    }\n"
        "  ],\n"
        '  "source_urls": []\n'
        "}\n"
    )


def _resolve_x_research_command(command: str | None = None) -> list[str]:
    for value in (
        os.getenv("X_RESEARCH_HERMES_COMMAND", "").strip(),
        os.getenv("KENSHO_HERMES_COMMAND", "").strip(),
        command or "",
    ):
        if value:
            return shlex.split(value, posix=True)
    if os.name == "nt":
        return list(X_RESEARCH_HERMES_DEFAULT_COMMAND)
    return ["hermes", "chat", "-q"]


def _resolve_x_research_timeout(timeout_sec: int | float | str | None = None) -> int:
    value = timeout_sec
    if value is None:
        value = os.getenv("X_RESEARCH_HERMES_TIMEOUT_SEC", os.getenv("KENSHO_HERMES_TIMEOUT_SEC", str(X_RESEARCH_HERMES_DEFAULT_TIMEOUT_SEC)))
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = X_RESEARCH_HERMES_DEFAULT_TIMEOUT_SEC
    return max(5, parsed)


def _balanced_json_fragments(text: str, opener: str, closer: str) -> Iterable[str]:
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text or ""):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == opener:
            if depth == 0:
                start = index
            depth += 1
        elif char == closer and depth:
            depth -= 1
            if depth == 0 and start != -1:
                yield text[start : index + 1]
                start = -1


def _extract_json_fragment(text: str, *, prefer_array: bool = False) -> str:
    candidate = (text or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("[") or (candidate.startswith("{") and not prefer_array):
        return candidate
    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    for block in fenced_blocks:
        block = block.strip()
        if block.startswith("[") or (block.startswith("{") and not prefer_array):
            return block
    if prefer_array:
        for fragment in _balanced_json_fragments(candidate, "[", "]"):
            return fragment
    else:
        fragments = sorted(
            [*_balanced_json_fragments(candidate, "{", "}"), *_balanced_json_fragments(candidate, "[", "]")],
            key=lambda value: candidate.find(value),
        )
        for fragment in fragments:
            return fragment
    return ""


def _normalize_related_posts(payload: Any, query: str) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = {"topic": query, "related_posts": payload}
    if not isinstance(payload, dict):
        return {}
    related_posts_raw = payload.get("related_posts", [])
    if isinstance(related_posts_raw, dict):
        related_posts_raw = [related_posts_raw]
    if not isinstance(related_posts_raw, list):
        related_posts_raw = []
    related_posts: list[dict[str, object]] = []
    source_urls: list[str] = []
    for item in related_posts_raw:
        if not isinstance(item, dict):
            continue
        post_url = _mask_secret_like_text(str(item.get("post_url", "")))
        source_url = _mask_secret_like_text(str(item.get("source_url", "")))
        normalized = {
            "author": _mask_secret_like_text(str(item.get("author", ""))),
            "handle": _mask_secret_like_text(str(item.get("handle", ""))),
            "post_url": post_url,
            "text": _mask_secret_like_text(str(item.get("text", ""))),
            "summary": _mask_secret_like_text(str(item.get("summary", ""))),
            "claim": _mask_secret_like_text(str(item.get("claim", ""))),
            "evidence_level": _mask_secret_like_text(str(item.get("evidence_level", ""))) or "unknown",
            "risk_flags": [str(flag) for flag in item.get("risk_flags", []) if str(flag).strip()] if isinstance(item.get("risk_flags", []), list) else [],
        }
        if post_url:
            source_urls.append(post_url)
        if source_url:
            source_urls.append(source_url)
        related_posts.append(normalized)
    deduped_urls = list(dict.fromkeys(url for url in source_urls if url))
    return {
        "topic": _mask_secret_like_text(str(payload.get("topic", query))) or query,
        "related_posts": related_posts,
        "source_urls": deduped_urls,
    }


def run_hermes_x_search(
    query: str,
    *,
    command: str | None = None,
    timeout_sec: int | float | str | None = None,
    prompt: str | None = None,
    prefer_array: bool = False,
    allow_empty_success: bool = False,
) -> dict[str, object]:
    ensure_runtime_dirs()
    prompt = prompt or build_hermes_x_research_prompt(query)
    command_parts = _resolve_x_research_command(command)
    timeout_value = _resolve_x_research_timeout(timeout_sec)
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    started_monotonic = datetime.now().timestamp()
    full_command = [*command_parts, prompt]
    raw_stdout = ""
    raw_stderr = ""
    returncode: int | None = None
    status = "failed"
    reason = "unknown_error"
    error_type = "unknown_error"
    response: dict[str, object] = {}
    raw_result_count = 0
    parsed_result_count = 0
    exception: BaseException | None = None
    try:
        completed = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_value,
            check=False,
        )
        returncode = completed.returncode
        raw_stdout = completed.stdout or ""
        raw_stderr = completed.stderr or ""
        fragment = _extract_json_fragment(raw_stdout, prefer_array=prefer_array)
        parsed: Any = None
        if fragment:
            try:
                parsed = json.loads(fragment)
            except json.JSONDecodeError:
                parsed = None
        if completed.returncode == 0 and not raw_stdout.strip():
            reason = "empty_result"
            error_type = "empty_result"
        elif completed.returncode == 0 and parsed is not None:
            response = _normalize_related_posts(parsed, query)
            parsed_result_count = len(response.get("related_posts", [])) if isinstance(response.get("related_posts", []), list) else 0
            raw_result_count = parsed_result_count
            if parsed_result_count or allow_empty_success:
                status = "success"
                reason = "ok"
                error_type = ""
            else:
                reason = "empty_result"
                error_type = "empty_result"
        else:
            if parsed is not None:
                response = _normalize_related_posts(parsed, query)
                parsed_result_count = len(response.get("related_posts", [])) if isinstance(response.get("related_posts", []), list) else 0
            reason, error_type = _classify_hermes_failure(
                command=full_command,
                stdout=raw_stdout,
                stderr=raw_stderr,
                returncode=completed.returncode,
                invalid_json=parsed is None and bool(raw_stdout.strip()),
            )
            if reason == "unknown_error" and completed.returncode == 0 and not fragment.strip():
                reason = "empty_result"
                error_type = "empty_result"
    except FileNotFoundError as exc:
        exception = exc
        returncode = 127
        reason, error_type = _classify_hermes_failure(command=full_command, stdout="", stderr="", exc=exc)
    except subprocess.TimeoutExpired as exc:
        exception = exc
        returncode = 124
        reason = "x_search_timeout" if "x_search" in prompt.casefold() else "timeout"
        error_type = reason
    finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
    duration_sec = round(datetime.now().timestamp() - started_monotonic, 3)
    if status != "success":
        error_type = reason
    result = {
        "provider": "hermes",
        "status": status,
        "reason": reason,
        "error_type": error_type,
        "command": full_command,
        "timeout_sec": timeout_value,
        "returncode": returncode,
        "stdout": mask_hermes_output(raw_stdout),
        "stderr": mask_hermes_output(raw_stderr),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "query": query,
        "prompt": prompt,
        "response": response,
        "raw_result_count": raw_result_count,
        "parsed_result_count": parsed_result_count,
    }
    if exception is not None:
        result["exception"] = mask_hermes_output(str(exception))
    if status == "success":
        result["error_type"] = ""
    return result


def save_x_research_harness_check(report: dict[str, object]) -> Path:
    RESEARCH_X_HARNESS_DIAGNOSTICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_X_HARNESS_DIAGNOSTICS_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return RESEARCH_X_HARNESS_DIAGNOSTICS_JSON


def _x_research_next_action(reason: object) -> str:
    reason_text = str(reason or "")
    actions = {
        "ok": 'py scripts/run_x_research_harness.py --query "Hermes Agent" --mode quick --provider hermes',
        "wsl_not_found": "管理者 PowerShell で wsl --install -d Ubuntu を実行してください",
        "hermes_not_found": "PowerShell で scripts/setup_hermes_wsl.ps1 を実行してください",
        "command_not_found": "X_RESEARCH_HERMES_COMMAND を確認してください",
        "xai_auth_missing": "WSL Ubuntu で hermes model、hermes auth add xai-oauth、hermes tools を順番に実行してください",
        "x_search_disabled": "WSL Ubuntu で hermes tools を開き X Search / x_search を ON にしてください",
        "timeout": "X_RESEARCH_HERMES_TIMEOUT_SEC=300 にして再実行してください",
        "x_search_timeout": "X Search が時間切れです。X_RESEARCH_HERMES_TIMEOUT_SEC=300 以上で再実行してください",
        "invalid_json": "Hermes の返答が JSON ではありません。診断 JSON の stdout_masked を確認してください",
        "empty_result": "検索結果が空です。x_search 設定とクエリを確認してください",
    }
    return actions.get(reason_text, "Hermes / WSL / x_search の状態を確認してください")


def run_x_research_harness_check(
    *,
    query: str | None = None,
    command: str | None = None,
    timeout_sec: int | float | str | None = None,
) -> dict[str, object]:
    target_query = (query or X_RESEARCH_HERMES_FIXED_QUERY).strip()
    prompt = build_hermes_x_search_diagnostic_prompt(target_query)
    result = run_hermes_x_search(
        target_query,
        command=command,
        timeout_sec=timeout_sec,
        prompt=prompt,
        prefer_array=True,
        allow_empty_success=True,
    )
    report = {
        "status": result["status"],
        "reason": result["reason"],
        "command": result["command"],
        "returncode": result["returncode"],
        "stdout_masked": result["stdout"],
        "stderr_masked": result["stderr"],
        "started_at": result["started_at"],
        "finished_at": result["finished_at"],
        "duration_sec": result["duration_sec"],
        "next_action": _x_research_next_action(result["reason"]),
        "output_file": str(RESEARCH_X_HARNESS_DIAGNOSTICS_JSON),
        "query": target_query,
        "provider": "hermes",
        "error_type": result.get("error_type", ""),
        "raw_result_count": result.get("raw_result_count", 0),
        "parsed_result_count": result.get("parsed_result_count", 0),
        "fallback_used": False,
        "diagnostic_type": "x_search",
        "timeout_sec": result.get("timeout_sec", X_RESEARCH_HERMES_DEFAULT_TIMEOUT_SEC),
    }
    save_x_research_harness_check(report)
    return report
