from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from ..paths import RESEARCH_X_SEARCH_DIR, ensure_runtime_dirs
from ..privacy_guard import mask_email, redact_personal_info


XAI_BASE_URL = "https://api.x.ai/v1"
XAI_DEFAULT_MODEL = "grok-4.3"
XAI_AUTH_ENV_VARS = (
    "XAI_API_KEY",
    "XAI_AUTH_TOKEN",
    "XAI_ACCESS_TOKEN",
    "HERMES_XAI_TOKEN",
    "HERMES_XAI_ACCESS_TOKEN",
)
_TOKEN_FIELD_NAMES = {
    "access_token",
    "api_key",
    "bearer_token",
    "runtime_api_key",
    "token",
}


def _usable_secret(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower() in {"*", "**", "***", "placeholder", "example", "dummy", "none", "null"}:
        return ""
    return text


def _mask_log_text(text: str) -> str:
    safe = redact_personal_info(text or "")
    safe = mask_email(safe)
    safe = re.sub(r"(?i)\b(api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token|bearer\s+token|token)\b\s*[:=]\s*([^\s,;\"']+)", r"\1=[redacted]", safe)
    return safe


def _normalize_handles(values: Iterable[str] | None) -> list[str]:
    handles: list[str] = []
    for value in values or []:
        handle = str(value or "").strip()
        if not handle:
            continue
        if handle.startswith("@"):
            handle = handle[1:]
        handles.append(handle)
    return handles[:10]


def _slug_digest(query: str) -> str:
    return hashlib.sha1((query or "").encode("utf-8")).hexdigest()[:12]


def _day_stamp(day: str | _dt.date | None = None) -> str:
    if day is None:
        return _dt.date.today().strftime("%Y%m%d")
    if isinstance(day, _dt.date):
        return day.strftime("%Y%m%d")
    text = str(day).strip()
    if not text:
        return _dt.date.today().strftime("%Y%m%d")
    if len(text) == 8 and text.isdigit():
        return text
    if "-" in text:
        try:
            return _dt.datetime.strptime(text, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError:
            return _dt.date.today().strftime("%Y%m%d")
    return _dt.date.today().strftime("%Y%m%d")


def _timestamp() -> str:
    return _dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def build_x_search_prompt(query: str, *, note_mode: bool = False) -> str:
    query = (query or "").strip()
    if note_mode:
        return (
            "あなたはXリサーチ記事の下書きを作るアシスタントです。\n"
            "x_search を使って、以下の条件に合うX投稿を調べてください。\n\n"
            f"検索条件:\n{query}\n\n"
            "Markdownで、次の見出しを必ず含めてください。\n"
            "## 反応分類\n"
            "## 誤解\n"
            "## 炎上ポイント\n"
            "## 記事見出し案\n\n"
            "事実と推測を分け、断定しすぎないでください。\n"
            "投稿URLや引用元の有無がわかるようにしてください。"
        )
    return (
        "あなたはXリサーチ担当です。\n"
        "x_search を使って、以下の条件に合うX投稿を探してください。\n\n"
        f"検索条件:\n{query}\n\n"
        "必ず簡潔な日本語で答えてください。\n"
        "Markdownの装飾は不要です。\n"
        "事実と推測を分けてください。\n"
        "投稿URLや引用元の有無がわかるようにしてください。"
    )


def _load_auth_json() -> dict[str, Any]:
    hermes_home = os.getenv("HERMES_HOME", "").strip()
    candidates = []
    if hermes_home:
        candidates.append(Path(hermes_home) / "auth.json")
    candidates.append(Path.home() / ".hermes" / "auth.json")
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _find_token_in_payload(node: Any, *, provider_hint: bool = False) -> str:
    if isinstance(node, dict):
        text_haystack = " ".join(str(value) for value in node.values() if isinstance(value, (str, int, float, bool)))
        hint = provider_hint or any(token in text_haystack.casefold() for token in ("xai", "grok"))
        if any(key.casefold() in {"xai", "xai-oauth"} or "xai" in key.casefold() for key in node.keys()):
            hint = True
        for key in ("provider_id", "id", "provider", "name", "source"):
            value = node.get(key)
            if isinstance(value, str) and value.casefold() in {"xai", "xai-oauth", "xAI", "xAI Grok OAuth (SuperGrok Subscription)".casefold()}:
                hint = True
                break
        for key in _TOKEN_FIELD_NAMES:
            value = node.get(key)
            token = _usable_secret(value)
            if token and hint:
                return token
        for key, value in node.items():
            child_hint = hint or key.casefold() in {"xai", "xai-oauth"}
            token = _find_token_in_payload(value, provider_hint=child_hint)
            if token:
                return token
    elif isinstance(node, list):
        for value in node:
            token = _find_token_in_payload(value, provider_hint=provider_hint)
            if token:
                return token
    return ""


def resolve_x_search_token(*, auth_json: dict[str, Any] | None = None) -> tuple[str, str]:
    for env_var in XAI_AUTH_ENV_VARS:
        token = _usable_secret(os.getenv(env_var, ""))
        if token:
            return token, f"env:{env_var}"
    payload = auth_json if auth_json is not None else _load_auth_json()
    token = _find_token_in_payload(payload)
    if token:
        return token, "hermes_auth.json"
    return "", ""


def _x_search_tool_spec(
    *,
    allowed_x_handles: Iterable[str] | None = None,
    excluded_x_handles: Iterable[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    enable_image_understanding: bool = False,
    enable_video_understanding: bool = False,
) -> dict[str, Any]:
    tool: dict[str, Any] = {"type": "x_search"}
    allowed = _normalize_handles(allowed_x_handles)
    excluded = _normalize_handles(excluded_x_handles)
    if allowed and excluded:
        raise ValueError("allowed_x_handles と excluded_x_handles は同時に指定できません")
    if allowed:
        tool["allowed_x_handles"] = allowed
    if excluded:
        tool["excluded_x_handles"] = excluded
    if from_date:
        tool["from_date"] = from_date
    if to_date:
        tool["to_date"] = to_date
    if enable_image_understanding:
        tool["enable_image_understanding"] = True
    if enable_video_understanding:
        tool["enable_video_understanding"] = True
    return tool


def _extract_text_block(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "output_text", "value", "content", "answer"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
        if "annotations" in value and isinstance(value.get("text"), str):
            return str(value.get("text", ""))
    if isinstance(value, list):
        chunks = [_extract_text_block(item) for item in value]
        return "\n".join(chunk for chunk in chunks if chunk.strip())
    return ""


def extract_x_search_answer(response_json: dict[str, Any]) -> str:
    if isinstance(response_json.get("answer"), str) and response_json["answer"].strip():
        return str(response_json["answer"]).strip()
    if isinstance(response_json.get("output_text"), str) and response_json["output_text"].strip():
        return str(response_json["output_text"]).strip()
    output = response_json.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).casefold()
            if item_type in {"message", "output_text", "response_message", "text"}:
                text = _extract_text_block(item.get("content"))
                if not text:
                    text = _extract_text_block(item)
                if text.strip():
                    parts.append(text.strip())
        if parts:
            return "\n\n".join(parts).strip()
        for item in output:
            if isinstance(item, dict):
                text = _extract_text_block(item)
                if text.strip():
                    return text.strip()
    if isinstance(response_json.get("text"), str) and response_json["text"].strip():
        return str(response_json["text"]).strip()
    return ""


def _http_post_json(url: str, payload: dict[str, Any], token: str, timeout_sec: int) -> tuple[dict[str, Any], int]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        body = response.read().decode("utf-8", "replace")
        status_code = int(getattr(response, "status", 200))
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("xAI response is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("xAI response JSON must be an object")
    return parsed, status_code


def x_search_tool(
    query: str,
    *,
    note_mode: bool = False,
    allowed_x_handles: Iterable[str] | None = None,
    excluded_x_handles: Iterable[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    enable_image_understanding: bool = False,
    enable_video_understanding: bool = False,
    model: str = XAI_DEFAULT_MODEL,
    base_url: str = XAI_BASE_URL,
    timeout_sec: int = 120,
    api_key: str | None = None,
    auth_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    token = _usable_secret(api_key or "")
    token_source = "argument" if token else ""
    if not token:
        token, token_source = resolve_x_search_token(auth_json=auth_json)
    if not token:
        return {
            "status": "failed",
            "reason": "xai_auth_missing",
            "answer": "",
            "response": {},
            "citations": [],
            "inline_citations": [],
            "credential_source": "",
            "model": model,
            "query": query,
            "provider": "xai",
            "tool": "x_search",
            "prompt": build_x_search_prompt(query, note_mode=note_mode),
        }
    prompt = build_x_search_prompt(query, note_mode=note_mode)
    tool = _x_search_tool_spec(
        allowed_x_handles=allowed_x_handles,
        excluded_x_handles=excluded_x_handles,
        from_date=from_date,
        to_date=to_date,
        enable_image_understanding=enable_image_understanding,
        enable_video_understanding=enable_video_understanding,
    )
    payload = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
        "tools": [tool],
    }
    request_url = base_url.rstrip("/") + "/responses"
    requested_at = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        response_json, status_code = _http_post_json(request_url, payload, token, timeout_sec)
    except TimeoutError as exc:
        return {
            "status": "failed",
            "reason": "timeout",
            "answer": "",
            "response": {},
            "citations": [],
            "inline_citations": [],
            "credential_source": token_source,
            "model": model,
            "query": query,
            "provider": "xai",
            "tool": "x_search",
            "prompt": prompt,
            "request_url": request_url,
            "requested_at": requested_at,
            "error": _mask_log_text(str(exc)),
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if hasattr(exc, "read") else ""
        return {
            "status": "failed",
            "reason": "http_error",
            "answer": "",
            "response": {},
            "citations": [],
            "inline_citations": [],
            "credential_source": token_source,
            "model": model,
            "query": query,
            "provider": "xai",
            "tool": "x_search",
            "prompt": prompt,
            "request_url": request_url,
            "requested_at": requested_at,
            "http_status": getattr(exc, "code", 0),
            "error": _mask_log_text(body or str(exc)),
        }
    except urllib.error.URLError as exc:
        return {
            "status": "failed",
            "reason": "network_error",
            "answer": "",
            "response": {},
            "citations": [],
            "inline_citations": [],
            "credential_source": token_source,
            "model": model,
            "query": query,
            "provider": "xai",
            "tool": "x_search",
            "prompt": prompt,
            "request_url": request_url,
            "requested_at": requested_at,
            "error": _mask_log_text(str(exc)),
        }
    except ValueError as exc:
        return {
            "status": "failed",
            "reason": "invalid_json",
            "answer": "",
            "response": {},
            "citations": [],
            "inline_citations": [],
            "credential_source": token_source,
            "model": model,
            "query": query,
            "provider": "xai",
            "tool": "x_search",
            "prompt": prompt,
            "request_url": request_url,
            "requested_at": requested_at,
            "error": _mask_log_text(str(exc)),
        }
    answer = extract_x_search_answer(response_json)
    citations = response_json.get("citations", [])
    inline_citations = response_json.get("inline_citations", [])
    if not isinstance(citations, list):
        citations = []
    if not isinstance(inline_citations, list):
        inline_citations = []
    return {
        "status": "success",
        "reason": "ok",
        "answer": answer,
        "response": response_json,
        "citations": citations,
        "inline_citations": inline_citations,
        "credential_source": token_source,
        "model": model,
        "query": query,
        "provider": "xai",
        "tool": "x_search",
        "tool_spec": tool,
        "prompt": prompt,
        "request_url": request_url,
        "requested_at": requested_at,
        "http_status": status_code,
    }


def save_x_search_outputs(result: dict[str, Any], *, day: str | _dt.date | None = None) -> dict[str, Path]:
    ensure_runtime_dirs()
    day_stamp = _day_stamp(day)
    day_dir = RESEARCH_X_SEARCH_DIR / day_stamp
    day_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    digest = _slug_digest(str(result.get("query", "")))
    prefix = f"{stamp}_{digest}"
    response_path = day_dir / f"{prefix}.response.json"
    answer_path = day_dir / f"{prefix}.md"
    run_path = day_dir / f"{prefix}.run.json"
    response = result.get("response", {})
    if not isinstance(response, dict):
        response = {}
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    answer = str(result.get("answer", "") or "").strip()
    answer_path.write_text(answer + ("\n" if answer else ""), encoding="utf-8")
    run_payload = {
        "requested_at": result.get("requested_at", ""),
        "saved_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": result.get("status", "failed"),
        "reason": result.get("reason", ""),
        "query": result.get("query", ""),
        "note_mode": bool(result.get("note_mode", False)),
        "credential_source": result.get("credential_source", ""),
        "model": result.get("model", ""),
        "tool": result.get("tool", "x_search"),
        "http_status": result.get("http_status", 0),
        "response_path": str(response_path),
        "answer_path": str(answer_path),
        "response_keys": sorted(list(response.keys())),
        "answer_preview": answer[:200],
        "prompt": result.get("prompt", ""),
    }
    run_path.write_text(json.dumps(run_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "response_path": response_path,
        "answer_path": answer_path,
        "run_path": run_path,
        "day_dir": day_dir,
    }
